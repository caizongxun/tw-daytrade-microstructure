# core/chip_fetcher.py
# 籌碼資料抓取：三大法人 / 融資融券 / 集保分散表 / 外資期貨未平倉
# 資料源：FinMind API (免費，需申請 token)

import requests
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger
from typing import Optional

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class ChipFetcher:
    def __init__(self, token: str = ""):
        """
        token: FinMind API token，免費版每天 600 次請求
        申請：https://finmindtrade.com/analysis/#/Signin
        不填 token 也可用，但請求上限較低
        """
        self.token = token
        self.session = requests.Session()

    def _query(self, dataset: str, stock_id: str, start_date: str, end_date: str = None) -> pd.DataFrame:
        end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        params = {
            "dataset": dataset,
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token,
        }
        try:
            resp = self.session.get(FINMIND_URL, params=params, timeout=10)
            data = resp.json()
            if data.get("status") == 200 and data.get("data"):
                return pd.DataFrame(data["data"])
            else:
                logger.warning(f"FinMind [{dataset}] no data: {data.get('msg')}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"FinMind fetch error [{dataset}]: {e}")
            return pd.DataFrame()

    # ============================================================
    # 1. 三大法人買賣超
    # ============================================================
    def get_institutional_investors(self, stock_id: str, days: int = 10) -> pd.DataFrame:
        """
        三大法人買賣超（外資、投信、自營商）
        欄位：date, name(外資/投信/自營), buy, sell, diff(買賣超)
        """
        start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        df = self._query("TaiwanStockInstitutionalInvestorsBuySell", stock_id, start)
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        df['diff'] = df['buy'].astype(float) - df['sell'].astype(float)
        return df.sort_values('date')

    def get_institutional_summary(self, stock_id: str, days: int = 5) -> dict:
        """
        取得最新 N 日的三大法人累計買賣超方向
        回傳 {'foreign': +/-, 'trust': +/-, 'dealer': +/-, 'composite_score': float}
        """
        df = self.get_institutional_investors(stock_id, days=days + 5)
        if df.empty:
            return {}
        recent = df[df['date'] >= df['date'].max() - timedelta(days=days)]
        result = {}
        name_map = {
            '外資': 'foreign',
            '外資自營商': 'foreign',
            '投信': 'trust',
            '自營商': 'dealer',
        }
        for chi_name, eng_name in name_map.items():
            sub = recent[recent['name'] == chi_name]
            if not sub.empty:
                result[eng_name] = float(sub['diff'].sum())
        # 複合方向分數：外資權重最高
        foreign = result.get('foreign', 0)
        trust = result.get('trust', 0)
        dealer = result.get('dealer', 0)
        # 正規化到 -1~1（以 10 萬張為基準）
        norm = 100_000
        score = (foreign * 0.6 + trust * 0.3 + dealer * 0.1) / norm
        result['composite_score'] = float(max(-1.0, min(1.0, score)))
        logger.info(f"[ChipFetcher] {stock_id} institutional score={result['composite_score']:.3f}")
        return result

    # ============================================================
    # 2. 融資融券
    # ============================================================
    def get_margin_trading(self, stock_id: str, days: int = 10) -> pd.DataFrame:
        """
        融資餘額 / 融券餘額
        欄位：date, MarginPurchaseTodayBalance(融資餘額), ShortSaleTodayBalance(融券餘額)
        """
        start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        df = self._query("TaiwanStockMarginPurchaseShortSale", stock_id, start)
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date')

    def get_margin_signal(self, stock_id: str, days: int = 5) -> dict:
        """
        融資/融券訊號分析
        - 融資增加 + 股價漲 = 散戶追高，偏空（反指標）
        - 融券增加 = 市場放空壓力
        - 券資比高 = 軋空機會
        """
        df = self.get_margin_trading(stock_id, days=days + 5)
        if df.empty:
            return {}
        recent = df.tail(days)
        margin_latest = float(recent['MarginPurchaseTodayBalance'].iloc[-1])
        margin_change = float(recent['MarginPurchaseTodayBalance'].diff().tail(3).mean())
        short_latest = float(recent['ShortSaleTodayBalance'].iloc[-1])
        short_change = float(recent['ShortSaleTodayBalance'].diff().tail(3).mean())
        ratio = short_latest / margin_latest if margin_latest > 0 else 0
        # 融資增加 = 散戶過熱 = 偏空信號
        margin_signal = -1 if margin_change > 0 else 1
        # 券資比高 = 可能軋空 = 偏多
        squeeze_signal = 1 if ratio > 0.3 else 0
        return {
            'margin_balance': margin_latest,
            'margin_change_3d': margin_change,
            'short_balance': short_latest,
            'short_change_3d': short_change,
            'short_to_margin_ratio': ratio,
            'margin_signal': margin_signal,   # -1=散戶過熱偏空, +1=散戶縮手偏多
            'squeeze_potential': squeeze_signal,
        }

    # ============================================================
    # 3. 集保股權分散表（大戶 vs 散戶）
    # ============================================================
    def get_shareholding_distribution(self, stock_id: str, weeks: int = 8) -> pd.DataFrame:
        """
        集保股權分散表
        欄位：date, HoldingSharesLevel(持股區間), people(人數), percent(比例)
        每週六更新
        """
        start = (datetime.now() - timedelta(weeks=weeks + 2)).strftime("%Y-%m-%d")
        df = self._query("TaiwanStockHoldingSharesPer", stock_id, start)
        if df.empty:
            return df
        df['date'] = pd.to_datetime(df['date'])
        return df.sort_values('date')

    def get_whale_retail_signal(self, stock_id: str) -> dict:
        """
        大戶（>=1000張）vs 散戶（1-10張）持股比例變化
        大戶比例上升 = 籌碼集中 = 偏多
        散戶比例上升 = 籌碼分散 = 偏空
        """
        df = self.get_shareholding_distribution(stock_id, weeks=8)
        if df.empty:
            return {}

        # 定義大戶：持股 >= 1000 張的區間
        whale_levels = ['1000-5000張', '5000張以上']
        retail_levels = ['1-5張', '5-10張']

        result = {}
        dates = sorted(df['date'].unique())[-2:]  # 最近兩期
        if len(dates) < 2:
            return {}

        def get_pct(date, levels):
            sub = df[(df['date'] == date) & (df['HoldingSharesLevel'].isin(levels))]
            return sub['percent'].astype(float).sum()

        whale_now = get_pct(dates[-1], whale_levels)
        whale_prev = get_pct(dates[-2], whale_levels)
        retail_now = get_pct(dates[-1], retail_levels)
        retail_prev = get_pct(dates[-2], retail_levels)

        whale_change = whale_now - whale_prev
        retail_change = retail_now - retail_prev

        # 大戶增加/散戶減少 = 籌碼集中訊號（偏多）
        concentration_score = whale_change - retail_change

        result = {
            'whale_pct': whale_now,
            'whale_change': whale_change,
            'retail_pct': retail_now,
            'retail_change': retail_change,
            'concentration_score': float(concentration_score),  # 正=集中偏多, 負=分散偏空
        }
        logger.info(f"[ChipFetcher] {stock_id} whale={whale_now:.1f}% change={whale_change:+.2f}%")
        return result

    # ============================================================
    # 4. 外資期貨未平倉（最強前瞻指標）
    # ============================================================
    def get_futures_institutional(self, days: int = 10) -> pd.DataFrame:
        """
        三大法人台指期未平倉口數
        外資期貨淨多 = 機構看多台股，領先現貨 1-3 日
        """
        start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        params = {
            "dataset": "TaiwanFuturesInstitutionalInvestors",
            "data_id": "TX",  # 台指期
            "start_date": start,
            "token": self.token,
        }
        try:
            resp = self.session.get(FINMIND_URL, params=params, timeout=10)
            data = resp.json()
            if data.get("status") == 200 and data.get("data"):
                df = pd.DataFrame(data["data"])
                df['date'] = pd.to_datetime(df['date'])
                return df.sort_values('date')
        except Exception as e:
            logger.error(f"Futures fetch error: {e}")
        return pd.DataFrame()

    def get_futures_signal(self, days: int = 3) -> dict:
        """
        外資期貨淨部位方向
        淨多口數增加 = 外資看多，偏多
        淨空口數增加 = 外資看空，偏空
        """
        df = self.get_futures_institutional(days=days + 5)
        if df.empty:
            return {}
        foreign = df[df['name'] == '外資']
        if foreign.empty:
            return {}
        recent = foreign.tail(days)
        net_oi = recent['long_open_interest_balance'].astype(float) - recent['short_open_interest_balance'].astype(float)
        net_oi_change = float(net_oi.diff().tail(3).mean())
        net_latest = float(net_oi.iloc[-1]) if not net_oi.empty else 0
        return {
            'foreign_futures_net_oi': net_latest,
            'foreign_futures_oi_change': net_oi_change,
            'futures_signal': 1 if net_oi_change > 0 else -1,  # +1=外資加多, -1=外資加空
        }

    # ============================================================
    # 5. 借券賣出（機構放空前兆）
    # ============================================================
    def get_securities_lending(self, stock_id: str, days: int = 10) -> dict:
        """
        借券賣出餘額
        借券快速增加 = 機構佈空，偏空信號
        """
        start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y-%m-%d")
        df = self._query("TaiwanStockSecuritiesLending", stock_id, start)
        if df.empty:
            return {}
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        latest = float(df['SalesBalance'].iloc[-1])
        change = float(df['SalesBalance'].diff().tail(3).mean())
        return {
            'lending_balance': latest,
            'lending_change_3d': change,
            'lending_signal': -1 if change > 0 else 1,  # 借券增加=偏空
        }
