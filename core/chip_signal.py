# core/chip_signal.py
# 籌碼複合訊號引擎
# 整合：三大法人 / 融資融券 / 集保大戶散戶 / 外資期貨 / 借券
# 輸出：-1.0 ~ +1.0 的方向偏向分數

from loguru import logger
from core.chip_fetcher import ChipFetcher
from datetime import datetime
import threading


class ChipSignalEngine:
    def __init__(self, token: str = "", refresh_interval_sec: int = 1800):
        """
        refresh_interval_sec: 籌碼資料刷新間隔（秒）
        預設 30 分鐘刷新一次，避免過度請求
        """
        self.fetcher = ChipFetcher(token=token)
        self.refresh_interval = refresh_interval_sec
        self._cache = {}       # {stock_id: {signal_dict}}
        self._last_fetch = {}  # {stock_id: datetime}
        self._lock = threading.Lock()

    def get_chip_score(self, stock_id: str, force_refresh: bool = False) -> dict:
        """
        取得籌碼方向分數（有快取，避免重複請求）
        
        回傳 dict:
        {
          'chip_score': float,         # -1~+1，最終方向偏向
          'institutional_score': float, # 三大法人
          'margin_signal': int,         # 融資信號
          'whale_score': float,         # 大戶集中度
          'futures_signal': int,        # 外資期貨
          'lending_signal': int,        # 借券放空
          'details': dict               # 所有原始數據
        }
        """
        with self._lock:
            last = self._last_fetch.get(stock_id)
            if not force_refresh and last:
                elapsed = (datetime.now() - last).total_seconds()
                if elapsed < self.refresh_interval and stock_id in self._cache:
                    logger.debug(f"[ChipSignal] cache hit {stock_id} (age={elapsed:.0f}s)")
                    return self._cache[stock_id]

        logger.info(f"[ChipSignal] fetching chip data for {stock_id}...")
        details = {}

        # 1. 三大法人
        inst = self.fetcher.get_institutional_summary(stock_id, days=5)
        details['institutional'] = inst
        inst_score = inst.get('composite_score', 0.0)

        # 2. 融資融券
        margin = self.fetcher.get_margin_signal(stock_id, days=5)
        details['margin'] = margin
        margin_sig = margin.get('margin_signal', 0)      # -1 / +1
        squeeze_sig = margin.get('squeeze_potential', 0) # 0 / +1

        # 3. 集保大戶散戶
        whale = self.fetcher.get_whale_retail_signal(stock_id)
        details['whale'] = whale
        concentration = whale.get('concentration_score', 0.0)
        # 正規化：concentration_score 通常在 -5 ~ +5%
        whale_score = float(max(-1.0, min(1.0, concentration / 3.0)))

        # 4. 外資期貨未平倉
        futures = self.fetcher.get_futures_signal(days=3)
        details['futures'] = futures
        futures_sig = futures.get('futures_signal', 0)  # -1 / +1

        # 5. 借券
        lending = self.fetcher.get_securities_lending(stock_id, days=5)
        details['lending'] = lending
        lending_sig = lending.get('lending_signal', 0)  # -1 / +1

        # ============================================================
        # 加權複合分數
        # 外資期貨：最強前瞻指標，權重最高
        # 三大法人現貨：第二
        # 集保大戶：第三（週頻，較慢）
        # 融資：反指標，較小權重
        # 借券：強放空信號，中權重
        # ============================================================
        chip_score = (
            futures_sig    * 0.35 +
            inst_score     * 0.30 +
            whale_score    * 0.15 +
            lending_sig    * 0.12 +
            margin_sig     * 0.08
        )
        chip_score = float(max(-1.0, min(1.0, chip_score)))

        result = {
            'chip_score': chip_score,
            'institutional_score': inst_score,
            'margin_signal': margin_sig,
            'squeeze_potential': squeeze_sig,
            'whale_score': whale_score,
            'futures_signal': futures_sig,
            'lending_signal': lending_sig,
            'details': details,
        }

        with self._lock:
            self._cache[stock_id] = result
            self._last_fetch[stock_id] = datetime.now()

        logger.info(
            f"[ChipSignal] {stock_id} chip_score={chip_score:+.3f} "
            f"inst={inst_score:+.3f} whale={whale_score:+.3f} "
            f"futures={futures_sig} margin={margin_sig} lending={lending_sig}"
        )
        return result

    def is_favorable(self, stock_id: str, direction: int) -> bool:
        """
        判斷籌碼面是否支持進場方向
        direction: +1=多頭進場, -1=空頭進場
        """
        result = self.get_chip_score(stock_id)
        score = result.get('chip_score', 0.0)
        if direction == 1:
            return score > 0.1   # 籌碼偏多才做多
        elif direction == -1:
            return score < -0.1  # 籌碼偏空才做空
        return False
