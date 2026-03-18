# config.example.py
# 複製此檔案為 config.py 並填入真實資訊

# === Shioaji 永豐金 API ===
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
PERSON_ID = "your_person_id"
PASSWORD = "your_password"

# === FinMind API Token ===
# 申請：https://finmindtrade.com/analysis/#/Signin
FINMIND_TOKEN = ""  # 免費版每天 600 次請求

# === 交易標的 ===
SYMBOL = "2330"          # 台積電
EXCHANGE = "TSE"         # 上市

# === OBI 參數 ===
OBI_LEVELS = 5
OBI_THRESHOLD = 0.25

# === VPIN 參數 ===
VPIN_BUCKET_SIZE = 500
VPIN_WINDOW = 50
VPIN_THRESHOLD = 0.6

# === Trade Imbalance 參數 ===
TI_WINDOW = 20
TI_THRESHOLD = 0.25

# === 風控 ===
STOP_LOSS_PCT = 0.005
TAKE_PROFIT_PCT = 0.012
MAX_POSITION = 1
FORCE_CLOSE_HOUR = 13
FORCE_CLOSE_MINUTE = 20

# === 模式 ===
MODE = "paper"
LOG_TICKS = True

# === 籌碼引擎 ===
CHIP_REFRESH_INTERVAL_SEC = 1800  # 每 30 分鐘刷新一次籌碼
