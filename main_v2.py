# main_v2.py
# 升級版主程式：整合微結構 + 籌碼雙層訊號

import argparse
import time
from loguru import logger
import shioaji as sj

import config as cfg
from core.market_state import MarketState, TickRecord
from core.indicators import VPINCalculator, classify_tick
from core.signal_engine_v2 import SignalEngineV2
from core.order_executor import OrderExecutor
from core.chip_signal import ChipSignalEngine
from core.chip_dashboard import print_chip_dashboard
from data.tick_logger import TickLogger


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default=cfg.SYMBOL)
    parser.add_argument('--mode', default=cfg.MODE, choices=['paper', 'live'])
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info(f"Starting TW DayTrade Bot v2 | symbol={args.symbol} mode={args.mode}")

    # === 初始化 ===
    state = MarketState(vpin_bucket_size=cfg.VPIN_BUCKET_SIZE, vpin_window=cfg.VPIN_WINDOW)
    state.vpin_calc = VPINCalculator(bucket_size=cfg.VPIN_BUCKET_SIZE, window=cfg.VPIN_WINDOW)
    tick_logger = TickLogger(args.symbol) if cfg.LOG_TICKS else None

    # === 籌碼引擎（開盤前先取一次）===
    chip_engine = ChipSignalEngine(
        token=cfg.FINMIND_TOKEN,
        refresh_interval_sec=cfg.CHIP_REFRESH_INTERVAL_SEC
    )
    chip_engine.get_chip_score(args.symbol, force_refresh=True)
    print_chip_dashboard(args.symbol, chip_engine)

    # === Shioaji 連線 ===
    api = sj.Shioaji()
    api.login(api_key=cfg.API_KEY, secret_key=cfg.API_SECRET, fetch_contract=True)
    logger.info("Shioaji logged in")

    executor = OrderExecutor(state, mode=args.mode, api=api)
    executor.setup_contract(args.symbol)
    signal_engine = SignalEngineV2(state, executor, chip_engine, args.symbol)

    contract = api.Contracts.Stocks[args.symbol]
    prev_price = [None]

    @api.on_tick_stk_v1()
    def on_tick(exchange, tick):
        price = float(tick.close)
        volume = float(tick.volume)
        bid1 = state.bid_prices[0] if state.bid_prices else price
        ask1 = state.ask_prices[0] if state.ask_prices else price
        p_prev = prev_price[0] if prev_price[0] else price
        buy_r, sell_r = classify_tick(price, p_prev, bid1, ask1)
        prev_price[0] = price
        tick_rec = TickRecord(
            price=price, volume=volume,
            buy_vol=buy_r * volume,
            sell_vol=sell_r * volume,
            ts=tick.datetime
        )
        state.add_tick(tick_rec)
        state.vpin_calc.update(buy_r * volume, sell_r * volume, volume)
        signal_engine.evaluate(price)

    @api.on_bidask_stk_v1()
    def on_bidask(exchange, bidask):
        state.update_bidask(
            bidask.bid_price, bidask.bid_volume,
            bidask.ask_price, bidask.ask_volume
        )

    api.quote.subscribe(contract, quote_type=sj.constant.QuoteType.Tick, version=sj.constant.QuoteVersion.v1)
    api.quote.subscribe(contract, quote_type=sj.constant.QuoteType.BidAsk, version=sj.constant.QuoteVersion.v1)
    logger.info(f"Subscribed {args.symbol}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if tick_logger:
            tick_logger.close()
        if state.trade_log:
            import pandas as pd
            df = pd.DataFrame(state.trade_log)
            print(df.to_string())
            df.to_csv(f"logs/{args.symbol}_trades.csv", index=False)
        api.logout()


if __name__ == '__main__':
    main()
