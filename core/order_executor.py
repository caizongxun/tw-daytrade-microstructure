# core/order_executor.py
# 下單執行器：支援 paper（模擬）和 live（真實 Shioaji）

from datetime import datetime
from loguru import logger
import config as cfg


class OrderExecutor:
    def __init__(self, state, mode: str = "paper", api=None):
        self.state = state
        self.mode = mode
        self.api = api   # shioaji api instance
        self.contract = None

    def setup_contract(self, symbol: str):
        """設定交易合約（shioaji）"""
        if self.api:
            self.contract = self.api.Contracts.Stocks[symbol]
            logger.info(f"Contract loaded: {self.contract}")

    def open_long(self, price: float):
        logger.info(f"[OPEN LONG] price={price} mode={self.mode}")
        if self.mode == "live" and self.api and self.contract:
            import shioaji as sj
            order = self.api.Order(
                price=price,
                quantity=cfg.MAX_POSITION,
                action=sj.constant.Action.Buy,
                price_type=sj.constant.StockPriceType.LMT,
                order_type=sj.constant.OrderType.IOC,
                daytrade_short=False,
                account=self.api.stock_account,
            )
            trade = self.api.place_order(self.contract, order)
            logger.info(f"Order placed: {trade}")
        with self.state.lock:
            self.state.position = 1
            self.state.entry_price = price
            self.state.entry_time = datetime.now()

    def open_short(self, price: float):
        logger.info(f"[OPEN SHORT] price={price} mode={self.mode}")
        if self.mode == "live" and self.api and self.contract:
            import shioaji as sj
            order = self.api.Order(
                price=price,
                quantity=cfg.MAX_POSITION,
                action=sj.constant.Action.Sell,
                price_type=sj.constant.StockPriceType.LMT,
                order_type=sj.constant.OrderType.IOC,
                daytrade_short=True,  # 當沖融券賣出
                account=self.api.stock_account,
            )
            trade = self.api.place_order(self.contract, order)
            logger.info(f"Order placed: {trade}")
        with self.state.lock:
            self.state.position = -1
            self.state.entry_price = price
            self.state.entry_time = datetime.now()

    def close_position(self, price: float, reason: str = ""):
        snap_pos = self.state.position
        if snap_pos == 0:
            return
        logger.info(f"[CLOSE] pos={snap_pos} price={price} reason={reason}")
        if self.mode == "live" and self.api and self.contract:
            import shioaji as sj
            action = sj.constant.Action.Sell if snap_pos > 0 else sj.constant.Action.Buy
            order = self.api.Order(
                price=price,
                quantity=cfg.MAX_POSITION,
                action=action,
                price_type=sj.constant.StockPriceType.LMT,
                order_type=sj.constant.OrderType.IOC,
                daytrade_short=snap_pos < 0,
                account=self.api.stock_account,
            )
            trade = self.api.place_order(self.contract, order)
            logger.info(f"Close order placed: {trade}")
        pnl = 0.0
        if self.state.entry_price:
            pnl = (price - self.state.entry_price) / self.state.entry_price * snap_pos
        self.state.trade_log.append({
            'entry_price': self.state.entry_price,
            'exit_price': price,
            'position': snap_pos,
            'pnl_pct': pnl,
            'reason': reason,
            'entry_time': self.state.entry_time,
            'exit_time': datetime.now(),
        })
        with self.state.lock:
            self.state.position = 0
            self.state.entry_price = None
            self.state.entry_time = None
        logger.info(f"Trade closed. PnL={pnl:.3%}")
