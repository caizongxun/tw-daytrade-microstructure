# main.py
# 主程式：連線 Shioaji，訂閱即時資料，啟動策略

import argparse
import time
from loguru import logger
import shioaji as sj

import config as cfg
from core.market_state import MarketState, TickRecord
from core.indicators import VPINCalculator, classify_tick
from core.signal_engine import SignalEngine
from core.order_executor import OrderExecutor
from data.tick_logger import TickLogger


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default=cfg.SYMBOL)
    parser.add_argument('--mode', default=cfg.MODE, choices=['paper', 'live'])
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info(f"Starting TW DayTrade Bot | symbol={args.symbol} mode={args.mode}")

    # === 初始化 ===
    state = MarketState(vpin_bucket_size=cfg.VPIN_BUCKET_SIZE, vpin_window=cfg.VPIN_WINDOW)
    state.vpin_calc = VPINCalculator(bucket_size=cfg.VPIN_BUCKET_SIZE, window=cfg.VPIN_WINDOW)
    tick_logger = TickLogger(args.symbol) if cfg.LOG_TICKS else None

    # === Shioaji 連線 ===
    api = sj.Shioaji()
    api.login(
        api_key=cfg.API_KEY,
        secret_key=cfg.API_SECRET,
        fetch_contract=True,
    )
    logger.info("Shioaji logged in")

    executor = OrderExecutor(state, mode=args.mode, api=api)
    executor.setup_contract(args.symbol)
    signal_engine = SignalEngine(state, executor)

    contract = api.Contracts.Stocks[args.symbol]
    prev_price = [None]  # mutable for closure

    # === Tick 回調 ===
    @api.on_tick_stk_v1()
    def on_tick(exchange, tick):
        price = float(tick.close)
        volume = float(tick.volume)

        # Lee-Ready 分類
        bid1 = state.bid_prices[0] if state.bid_prices else price
        ask1 = state.ask_prices[0] if state.ask_prices else price
        p_prev = prev_price[0] if prev_price[0] else price
        buy_r, sell_r = classify_tick(price, p_prev, bid1, ask1)
        prev_price[0] = price

        buy_vol = buy_r * volume
        sell_vol = sell_r * volume

        tick_rec = TickRecord(price=price, volume=volume,
                               buy_vol=buy_vol, sell_vol=sell_vol,
                               ts=tick.datetime)
        state.add_tick(tick_rec)

        # 更新 VPIN
        state.vpin_calc.update(buy_vol, sell_vol, volume)
        vpin = state.vpin_calc.get_vpin()

        # 記錄 tick
        if tick_logger:
            from core.indicators import compute_weighted_obi, compute_trade_imbalance, compute_composite_score
            snap = state.get_snapshot()
            obi = compute_weighted_obi(snap['bid_prices'], snap['bid_volumes'],
                                       snap['ask_prices'], snap['ask_volumes'],
                                       snap['mid_price'])
            ti = compute_trade_imbalance(snap['ticks'])
            mid = snap['mid_price'] or price
            tick_logger.log(tick.datetime, price, volume, buy_vol, sell_vol,
                             bid1, ask1, mid, obi, vpin, ti)

        # 訊號評估
        signal_engine.evaluate(price)

    # === BidAsk 回調 ===
    @api.on_bidask_stk_v1()
    def on_bidask(exchange, bidask):
        state.update_bidask(
            bidask.bid_price, bidask.bid_volume,
            bidask.ask_price, bidask.ask_volume
        )

    # === 訂閱 ===
    api.quote.subscribe(contract, quote_type=sj.constant.QuoteType.Tick, version=sj.constant.QuoteVersion.v1)
    api.quote.subscribe(contract, quote_type=sj.constant.QuoteType.BidAsk, version=sj.constant.QuoteVersion.v1)
    logger.info(f"Subscribed to {args.symbol} tick + bidask")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if tick_logger:
            tick_logger.close()
        # 印出交易記錄
        if state.trade_log:
            import pandas as pd
            df = pd.DataFrame(state.trade_log)
            logger.info(f"\nTrade Summary:\n{df.to_string()}")
            df.to_csv(f"logs/{args.symbol}_trades.csv", index=False)
        api.logout()


if __name__ == '__main__':
    main()
