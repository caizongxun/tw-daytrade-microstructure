# core/market_state.py
# Thread-safe 市場狀態管理

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TickRecord:
    price: float
    volume: float
    buy_vol: float
    sell_vol: float
    ts: object  # datetime


class MarketState:
    def __init__(self, vpin_bucket_size: int = 500, vpin_window: int = 50):
        self.lock = threading.Lock()

        # === Order Book 快照 ===
        self.bid_prices: List[float] = []
        self.bid_volumes: List[float] = []
        self.ask_prices: List[float] = []
        self.ask_volumes: List[float] = []
        self.mid_price: Optional[float] = None
        self.last_price: Optional[float] = None

        # === Tick 串流 ===
        self.ticks: deque = deque(maxlen=1000)

        # === VPIN 桶狀態 ===
        self.vpin_bucket_size = vpin_bucket_size
        self.current_bucket_buy = 0.0
        self.current_bucket_sell = 0.0
        self.current_bucket_total = 0.0
        self.vpin_buckets: deque = deque(maxlen=vpin_window)

        # === 指標歷史 ===
        self.obi_history: deque = deque(maxlen=200)
        self.vpin_history: deque = deque(maxlen=200)
        self.ti_history: deque = deque(maxlen=200)

        # === 持倉狀態 ===
        self.position: int = 0           # +1 多, -1 空, 0 空手
        self.entry_price: Optional[float] = None
        self.entry_time = None
        self.trade_log: List[dict] = []

    def update_bidask(self, bid_prices, bid_volumes, ask_prices, ask_volumes):
        with self.lock:
            self.bid_prices = list(bid_prices)
            self.bid_volumes = list(bid_volumes)
            self.ask_prices = list(ask_prices)
            self.ask_volumes = list(ask_volumes)
            if self.bid_prices and self.ask_prices:
                self.mid_price = (self.bid_prices[0] + self.ask_prices[0]) / 2

    def add_tick(self, tick: TickRecord):
        with self.lock:
            self.ticks.append(tick)
            self.last_price = tick.price

    def get_snapshot(self):
        """取得當前狀態快照（用於訊號計算）"""
        with self.lock:
            return {
                'bid_prices': list(self.bid_prices),
                'bid_volumes': list(self.bid_volumes),
                'ask_prices': list(self.ask_prices),
                'ask_volumes': list(self.ask_volumes),
                'mid_price': self.mid_price,
                'last_price': self.last_price,
                'ticks': list(self.ticks),
                'vpin_buckets': list(self.vpin_buckets),
                'position': self.position,
                'entry_price': self.entry_price,
            }
