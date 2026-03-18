# data/tick_logger.py
# 將即時 tick 資料記錄到 CSV，供事後回測

import csv
import os
from datetime import datetime
from loguru import logger


class TickLogger:
    def __init__(self, symbol: str, log_dir: str = "logs"):
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        self.filepath = os.path.join(log_dir, f"{symbol}_{date_str}_ticks.csv")
        self.file = open(self.filepath, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['timestamp', 'price', 'volume', 'buy_vol', 'sell_vol',
                               'bid1', 'ask1', 'mid', 'obi', 'vpin', 'ti'])
        logger.info(f"TickLogger writing to {self.filepath}")

    def log(self, ts, price, volume, buy_vol, sell_vol,
            bid1, ask1, mid, obi, vpin, ti):
        self.writer.writerow([ts, price, volume, buy_vol, sell_vol,
                               bid1, ask1, mid, obi, vpin, ti])

    def close(self):
        self.file.close()
        logger.info(f"TickLogger closed: {self.filepath}")
