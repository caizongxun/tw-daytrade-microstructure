# tw-daytrade-microstructure

台股當沖機器人：整合市場微結構指標

## 核心指標

- **OBI (Order Book Imbalance)**：五檔委買委賣壓力不均衡
- **VPIN (Volume-Synchronized PIN)**：資訊交易毒性，預測波動爆發
- **Trade Imbalance**：Lee-Ready 主動買賣方向分類
- **Composite Signal**：三指標融合進出場

## 架構

```
tw-daytrade-microstructure/
├── main.py                  # 主程式入口
├── config.py                # 參數設定
├── core/
│   ├── market_state.py      # 市場狀態管理（thread-safe）
│   ├── indicators.py        # OBI / VPIN / Trade Imbalance
│   ├── signal_engine.py     # 進出場訊號邏輯
│   └── order_executor.py    # Shioaji 下單執行
├── data/
│   └── tick_logger.py       # Tick 資料記錄（CSV）
├── backtest/
│   └── backtest_engine.py   # 回測引擎
└── requirements.txt
```

## 安裝

```bash
pip install -r requirements.txt
```

## 設定

複製 `config.example.py` 為 `config.py`，填入永豐金帳號資訊：

```python
API_KEY = "your_shioaji_api_key"
API_SECRET = "your_shioaji_secret"
PERSON_ID = "your_id"
PASSWORD = "your_password"
```

## 使用

```bash
python main.py --symbol 2330 --mode paper  # 模擬單
python main.py --symbol 2330 --mode live   # 真實下單
```

## 指標邏輯

### OBI
```
OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)
```
值域 [-1, 1]，>0.25 買壓強，<-0.25 賣壓強

### VPIN
以固定成交量為一桶，計算每桶 |buy - sell| / bucket_size，取最近 N 桶平均。
VPIN > 0.6 代表資訊交易者活躍，流動性風險高，不進場。

### Trade Imbalance
Lee-Ready Rule：tick price > mid → 主動買；< mid → 主動賣。
取最近 20 筆 tick 的方向加權比例。

## 進場條件

- 多頭：`OBI > 0.25 AND TI > 0.25 AND VPIN < 0.6`
- 空頭：`OBI < -0.25 AND TI < -0.25 AND VPIN < 0.6`
- 強制 13:20 前平倉
