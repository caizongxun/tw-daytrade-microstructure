# config.example.py
# 複製此檔案為 config.py 並填入真實資訊

# === Shioaji 永豐金 API ===
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
PERSON_ID = "your_person_id"
PASSWORD = "your_password"

# === 交易標的 ===
SYMBOL = "2330"          # 台積電
EXCHANGE = "TSE"         # 上市

# === OBI 參數 ===
OBI_LEVELS = 5            # 用幾檔委買委賣
OBI_THRESHOLD = 0.25      # 進場閾值

# === VPIN 參數 ===
VPIN_BUCKET_SIZE = 500    # 每桶成交量（張）
VPIN_WINDOW = 50          # 計算 VPIN 的桶數
VPIN_THRESHOLD = 0.6      # 超過此值視為流動性風險，不進場

# === Trade Imbalance 參數 ===
TI_WINDOW = 20            # 最近幾筆 tick
TI_THRESHOLD = 0.25       # 進場閾值

# === 風控 ===
STOP_LOSS_PCT = 0.005     # 0.5% 停損
TAKE_PROFIT_PCT = 0.012   # 1.2% 停利
MAX_POSITION = 1          # 最大持倉（張）
FORCE_CLOSE_HOUR = 13
FORCE_CLOSE_MINUTE = 20

# === 模式 ===
MODE = "paper"            # "paper" 模擬 | "live" 真實
LOG_TICKS = True          # 是否記錄 tick 到 CSV
