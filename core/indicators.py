# core/indicators.py
# OBI / VPIN / Trade Imbalance 計算

import numpy as np
from typing import List, Optional


# ============================================================
# OBI - Order Book Imbalance
# ============================================================

def compute_obi(bid_volumes: List[float], ask_volumes: List[float], levels: int = 5) -> float:
    """
    Order Book Imbalance (OBI)
    OBI = (sum_bid - sum_ask) / (sum_bid + sum_ask)

    正值 = 買壓 > 賣壓（看多）
    負值 = 賣壓 > 買壓（看空）
    值域 [-1, 1]
    """
    if not bid_volumes or not ask_volumes:
        return 0.0
    bid_v = sum(bid_volumes[:levels])
    ask_v = sum(ask_volumes[:levels])
    total = bid_v + ask_v
    if total == 0:
        return 0.0
    return (bid_v - ask_v) / total


def compute_weighted_obi(bid_prices: List[float], bid_volumes: List[float],
                         ask_prices: List[float], ask_volumes: List[float],
                         mid_price: float, levels: int = 5) -> float:
    """
    加權 OBI：距離 mid price 越近的檔位權重越高
    更精準反映即將成交的委託壓力
    """
    if mid_price is None or mid_price == 0:
        return compute_obi(bid_volumes, ask_volumes, levels)

    bid_weighted = 0.0
    ask_weighted = 0.0

    for i in range(min(levels, len(bid_prices))):
        dist = abs(mid_price - bid_prices[i]) / mid_price
        weight = np.exp(-dist * 100)  # 距離越近，指數衰減越小
        bid_weighted += bid_volumes[i] * weight

    for i in range(min(levels, len(ask_prices))):
        dist = abs(ask_prices[i] - mid_price) / mid_price
        weight = np.exp(-dist * 100)
        ask_weighted += ask_volumes[i] * weight

    total = bid_weighted + ask_weighted
    if total == 0:
        return 0.0
    return (bid_weighted - ask_weighted) / total


# ============================================================
# Lee-Ready Tick Classification
# ============================================================

def classify_tick(price: float, prev_price: float, bid1: float, ask1: float) -> tuple:
    """
    Lee-Ready Rule：
    1. price > mid → 主動買
    2. price < mid → 主動賣
    3. price == mid → tick test（看漲跌）

    回傳 (buy_ratio, sell_ratio) 各佔比
    """
    mid = (bid1 + ask1) / 2
    if price > mid:
        return 1.0, 0.0
    elif price < mid:
        return 0.0, 1.0
    else:
        # tick test
        if price > prev_price:
            return 1.0, 0.0
        elif price < prev_price:
            return 0.0, 1.0
        else:
            return 0.5, 0.5


# ============================================================
# Trade Imbalance
# ============================================================

def compute_trade_imbalance(ticks: list, window: int = 20) -> float:
    """
    短期成交流量不均衡
    TI = (buy_vol - sell_vol) / (buy_vol + sell_vol)
    用最近 window 筆 tick 計算
    """
    recent = ticks[-window:] if len(ticks) >= window else ticks
    if not recent:
        return 0.0
    buy_sum = sum(t.buy_vol for t in recent)
    sell_sum = sum(t.sell_vol for t in recent)
    total = buy_sum + sell_sum
    if total == 0:
        return 0.0
    return (buy_sum - sell_sum) / total


# ============================================================
# VPIN - Volume-Synchronized Probability of Informed Trading
# ============================================================

class VPINCalculator:
    """
    VPIN 計算器

    原理：
    以固定成交量（bucket_size）為一桶，
    每桶統計主動買量與主動賣量的差異程度。
    VPIN = E[|buy_vol - sell_vol|] / bucket_size

    VPIN 高 → 資訊交易者活躍 → 流動性風險高 → 價格大幅波動機率高
    """

    def __init__(self, bucket_size: int = 500, window: int = 50):
        self.bucket_size = bucket_size
        self.window = window
        self.current_buy = 0.0
        self.current_sell = 0.0
        self.current_total = 0.0
        self.buckets = []
        self.completed_buckets = 0

    def update(self, buy_vol: float, sell_vol: float, total_vol: float) -> Optional[float]:
        """
        更新一筆 tick，若完成一桶則回傳最新 VPIN，否則回傳 None
        """
        remaining = total_vol
        new_vpin = None

        while remaining > 0:
            space = self.bucket_size - self.current_total
            fill = min(remaining, space)
            fill_ratio = fill / total_vol if total_vol > 0 else 0.5

            self.current_buy += buy_vol * fill_ratio
            self.current_sell += sell_vol * fill_ratio
            self.current_total += fill
            remaining -= fill

            if self.current_total >= self.bucket_size:
                imbalance = abs(self.current_buy - self.current_sell) / self.bucket_size
                self.buckets.append(imbalance)
                self.completed_buckets += 1
                # 重置當前桶
                self.current_buy = 0.0
                self.current_sell = 0.0
                self.current_total = 0.0
                # 計算滾動 VPIN
                recent = self.buckets[-self.window:]
                new_vpin = float(np.mean(recent))

        return new_vpin

    def get_vpin(self) -> float:
        if len(self.buckets) < 5:
            return 0.0
        recent = self.buckets[-self.window:]
        return float(np.mean(recent))

    def get_bucket_count(self) -> int:
        return self.completed_buckets


# ============================================================
# 複合指標分數
# ============================================================

def compute_composite_score(obi: float, vpin: float, ti: float,
                             obi_w: float = 0.4, ti_w: float = 0.4, vpin_w: float = 0.2) -> float:
    """
    複合訊號分數（-1 到 1）
    OBI 和 TI 方向性指標加權；VPIN 作為懲罰項（高 VPIN 壓低分數）

    score > 0  看多
    score < 0  看空
    abs(score) 越大越強
    """
    direction_score = obi * obi_w + ti * ti_w
    vpin_penalty = vpin * vpin_w  # VPIN 高 → 不確定性高 → 壓低方向信心
    # 懲罰：高 VPIN 時縮小 direction_score
    adjusted = direction_score * (1 - vpin_penalty)
    return float(np.clip(adjusted, -1.0, 1.0))
