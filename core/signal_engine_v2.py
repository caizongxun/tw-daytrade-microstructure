# core/signal_engine_v2.py
# 升級版訊號引擎：整合微結構（OBI/VPIN/TI）+ 籌碼（法人/融資/大戶/期貨）

from datetime import datetime
from loguru import logger
import config as cfg
from core.indicators import compute_weighted_obi, compute_trade_imbalance, compute_composite_score
from core.chip_signal import ChipSignalEngine


class SignalEngineV2:
    """
    雙層訊號架構：

    Layer 1 - 籌碼偏向（T+1，低頻，決定今天做多還是做空）
      外資期貨未平倉 / 三大法人 / 大戶持股 / 融資 / 借券
      -> chip_score: -1 ~ +1

    Layer 2 - 微結構時機（即時，決定何時下單）
      OBI + VPIN + Trade Imbalance
      -> micro_score: -1 ~ +1

    進場條件：chip 與 micro 方向一致 + VPIN 未超標
    出場條件：停損 / 停利 / 反向微結構 / 強制 13:20
    """

    def __init__(self, state, executor, chip_engine: ChipSignalEngine, symbol: str):
        self.state = state
        self.executor = executor
        self.chip = chip_engine
        self.symbol = symbol
        self._chip_cache = None
        self._chip_fetch_time = None

    def _get_chip_score(self) -> float:
        """每 30 分鐘重新取一次籌碼分數"""
        now = datetime.now()
        if (self._chip_fetch_time is None or
                (now - self._chip_fetch_time).total_seconds() > 1800):
            result = self.chip.get_chip_score(self.symbol)
            self._chip_cache = result
            self._chip_fetch_time = now
        return self._chip_cache.get('chip_score', 0.0) if self._chip_cache else 0.0

    def evaluate(self, price: float):
        now = datetime.now()
        snap = self.state.get_snapshot()

        # === Layer 2：計算即時微結構指標 ===
        obi = compute_weighted_obi(
            snap['bid_prices'], snap['bid_volumes'],
            snap['ask_prices'], snap['ask_volumes'],
            snap['mid_price'], levels=cfg.OBI_LEVELS
        )
        vpin = self.state.vpin_calc.get_vpin() if hasattr(self.state, 'vpin_calc') else 0.0
        ti = compute_trade_imbalance(snap['ticks'], window=cfg.TI_WINDOW)
        micro_score = compute_composite_score(obi, vpin, ti)

        # === Layer 1：取籌碼偏向 ===
        chip_score = self._get_chip_score()

        # 更新歷史
        with self.state.lock:
            self.state.obi_history.append(obi)
            self.state.vpin_history.append(vpin)
            self.state.ti_history.append(ti)

        logger.debug(
            f"chip={chip_score:+.3f} micro={micro_score:+.3f} "
            f"OBI={obi:+.3f} VPIN={vpin:.3f} TI={ti:+.3f} pos={snap['position']}"
        )

        # === 強制平倉 13:20 ===
        force_min = cfg.FORCE_CLOSE_HOUR * 60 + cfg.FORCE_CLOSE_MINUTE
        cur_min = now.hour * 60 + now.minute
        if cur_min >= force_min and snap['position'] != 0:
            logger.info(f"[FORCE CLOSE] {now.strftime('%H:%M:%S')} price={price}")
            self.executor.close_position(price, reason="force_close")
            return

        # 只在 9:05~13:20 交易
        if not (9 * 60 + 5 <= cur_min < force_min):
            return

        # === 出場邏輯 ===
        if snap['position'] != 0 and snap['entry_price']:
            pnl = (price - snap['entry_price']) / snap['entry_price'] * snap['position']
            if pnl <= -cfg.STOP_LOSS_PCT:
                logger.warning(f"[STOP LOSS] pnl={pnl:.3%}")
                self.executor.close_position(price, reason="stop_loss")
                return
            if pnl >= cfg.TAKE_PROFIT_PCT:
                logger.success(f"[TAKE PROFIT] pnl={pnl:.3%}")
                self.executor.close_position(price, reason="take_profit")
                return
            # 微結構反向（快速出場）
            if snap['position'] > 0 and micro_score < -cfg.OBI_THRESHOLD:
                logger.info(f"[MICRO REVERSE EXIT LONG] micro={micro_score:.3f}")
                self.executor.close_position(price, reason="micro_reversal")
                return
            if snap['position'] < 0 and micro_score > cfg.OBI_THRESHOLD:
                logger.info(f"[MICRO REVERSE EXIT SHORT] micro={micro_score:.3f}")
                self.executor.close_position(price, reason="micro_reversal")
                return

        # === 進場邏輯 ===
        if snap['position'] == 0:
            # VPIN 過高不進場
            if vpin > cfg.VPIN_THRESHOLD:
                return

            # 多頭：籌碼偏多 + 微結構偏多，方向一致
            if chip_score > 0.1 and micro_score > cfg.OBI_THRESHOLD and ti > cfg.TI_THRESHOLD:
                logger.info(
                    f"[BUY] chip={chip_score:+.3f} micro={micro_score:+.3f} "
                    f"OBI={obi:+.3f} TI={ti:+.3f} VPIN={vpin:.3f}"
                )
                self.executor.open_long(price)

            # 空頭：籌碼偏空 + 微結構偏空，方向一致
            elif chip_score < -0.1 and micro_score < -cfg.OBI_THRESHOLD and ti < -cfg.TI_THRESHOLD:
                logger.info(
                    f"[SELL SHORT] chip={chip_score:+.3f} micro={micro_score:+.3f} "
                    f"OBI={obi:+.3f} TI={ti:+.3f} VPIN={vpin:.3f}"
                )
                self.executor.open_short(price)
