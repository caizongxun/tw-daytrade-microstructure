# core/signal_engine.py
# 進出場訊號邏輯

from datetime import datetime
from loguru import logger
import config as cfg
from core.indicators import compute_obi, compute_weighted_obi, compute_trade_imbalance, compute_composite_score


class SignalEngine:
    def __init__(self, state, executor):
        self.state = state
        self.executor = executor

    def evaluate(self, price: float):
        """每筆 tick 後呼叫，評估當前市場狀態並決策"""
        now = datetime.now()
        snap = self.state.get_snapshot()

        # === 計算指標 ===
        obi = compute_weighted_obi(
            snap['bid_prices'], snap['bid_volumes'],
            snap['ask_prices'], snap['ask_volumes'],
            snap['mid_price'],
            levels=cfg.OBI_LEVELS
        )
        vpin = self.state.vpin_calc.get_vpin() if hasattr(self.state, 'vpin_calc') else 0.0
        ti = compute_trade_imbalance(snap['ticks'], window=cfg.TI_WINDOW)
        score = compute_composite_score(obi, vpin, ti)

        # 更新歷史
        with self.state.lock:
            self.state.obi_history.append(obi)
            self.state.vpin_history.append(vpin)
            self.state.ti_history.append(ti)

        logger.debug(f"OBI={obi:.3f} VPIN={vpin:.3f} TI={ti:.3f} score={score:.3f} pos={snap['position']}")

        # === 強制平倉（13:20）===
        force_close_min = cfg.FORCE_CLOSE_HOUR * 60 + cfg.FORCE_CLOSE_MINUTE
        current_min = now.hour * 60 + now.minute
        if current_min >= force_close_min and snap['position'] != 0:
            logger.info(f"[FORCE CLOSE] time={now.strftime('%H:%M:%S')} price={price}")
            self.executor.close_position(price, reason="force_close")
            return

        # 只在開盤後 9:05 到 13:20 交易
        if not (9 * 60 + 5 <= current_min < force_close_min):
            return

        # === 出場邏輯 ===
        if snap['position'] != 0 and snap['entry_price']:
            pnl = (price - snap['entry_price']) / snap['entry_price'] * snap['position']
            if pnl <= -cfg.STOP_LOSS_PCT:
                logger.warning(f"[STOP LOSS] pnl={pnl:.3%} price={price}")
                self.executor.close_position(price, reason="stop_loss")
                return
            if pnl >= cfg.TAKE_PROFIT_PCT:
                logger.success(f"[TAKE PROFIT] pnl={pnl:.3%} price={price}")
                self.executor.close_position(price, reason="take_profit")
                return
            # 反向 OBI 出場（趨勢反轉）
            if snap['position'] > 0 and score < -cfg.OBI_THRESHOLD:
                logger.info(f"[REVERSE EXIT LONG] score={score:.3f}")
                self.executor.close_position(price, reason="signal_reversal")
                return
            if snap['position'] < 0 and score > cfg.OBI_THRESHOLD:
                logger.info(f"[REVERSE EXIT SHORT] score={score:.3f}")
                self.executor.close_position(price, reason="signal_reversal")
                return

        # === 進場邏輯 ===
        if snap['position'] == 0:
            if vpin > cfg.VPIN_THRESHOLD:
                logger.debug(f"[SKIP] VPIN={vpin:.3f} > threshold, flow toxicity too high")
                return
            if score > cfg.OBI_THRESHOLD and ti > cfg.TI_THRESHOLD:
                logger.info(f"[BUY] score={score:.3f} OBI={obi:.3f} TI={ti:.3f} VPIN={vpin:.3f}")
                self.executor.open_long(price)
            elif score < -cfg.OBI_THRESHOLD and ti < -cfg.TI_THRESHOLD:
                logger.info(f"[SELL SHORT] score={score:.3f} OBI={obi:.3f} TI={ti:.3f} VPIN={vpin:.3f}")
                self.executor.open_short(price)
