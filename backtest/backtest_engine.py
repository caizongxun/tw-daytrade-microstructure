# backtest/backtest_engine.py
# 用錄製的 tick CSV 回測策略

import pandas as pd
import numpy as np
from loguru import logger
from core.indicators import (
    compute_weighted_obi, compute_trade_imbalance,
    VPINCalculator, compute_composite_score
)
from core.market_state import MarketState, TickRecord
import config as cfg


class BacktestEngine:
    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(self.df)} ticks from {csv_path}")
        self.vpin_calc = VPINCalculator(bucket_size=cfg.VPIN_BUCKET_SIZE, window=cfg.VPIN_WINDOW)
        self.trades = []
        self.position = 0
        self.entry_price = None

    def run(self):
        ticks_buf = []

        for i, row in self.df.iterrows():
            price = row['price']
            volume = row['volume']
            buy_vol = row['buy_vol']
            sell_vol = row['sell_vol']
            bid1 = row.get('bid1', price)
            ask1 = row.get('ask1', price)
            mid = row.get('mid', (bid1 + ask1) / 2)

            tick = TickRecord(price=price, volume=volume, buy_vol=buy_vol,
                               sell_vol=sell_vol, ts=row.get('timestamp'))
            ticks_buf.append(tick)

            # VPIN 更新
            self.vpin_calc.update(buy_vol, sell_vol, volume)
            vpin = self.vpin_calc.get_vpin()

            # OBI（簡化：只用 bid1/ask1 作為單檔計算，實際應有五檔）
            obi_simple = (bid1 - ask1) / (bid1 + ask1) if (bid1 + ask1) > 0 else 0.0

            ti = compute_trade_imbalance(ticks_buf, window=cfg.TI_WINDOW)
            score = compute_composite_score(obi_simple, vpin, ti)

            # 出場
            if self.position != 0 and self.entry_price:
                pnl = (price - self.entry_price) / self.entry_price * self.position
                if pnl <= -cfg.STOP_LOSS_PCT or pnl >= cfg.TAKE_PROFIT_PCT:
                    self.trades.append({'entry': self.entry_price, 'exit': price,
                                         'pos': self.position, 'pnl': pnl})
                    self.position = 0
                    self.entry_price = None
                    continue

            # 進場
            if self.position == 0 and vpin <= cfg.VPIN_THRESHOLD:
                if score > cfg.OBI_THRESHOLD and ti > cfg.TI_THRESHOLD:
                    self.position = 1
                    self.entry_price = price
                elif score < -cfg.OBI_THRESHOLD and ti < -cfg.TI_THRESHOLD:
                    self.position = -1
                    self.entry_price = price

        return self.summary()

    def summary(self):
        if not self.trades:
            logger.warning("No trades executed")
            return {}
        df = pd.DataFrame(self.trades)
        total = len(df)
        wins = (df['pnl'] > 0).sum()
        result = {
            'total_trades': total,
            'win_rate': wins / total,
            'avg_pnl': df['pnl'].mean(),
            'total_pnl': df['pnl'].sum(),
            'max_drawdown': df['pnl'].min(),
            'sharpe': df['pnl'].mean() / df['pnl'].std() if df['pnl'].std() > 0 else 0,
        }
        logger.info(f"Backtest Result: {result}")
        return result
