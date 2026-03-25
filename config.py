import os
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
CLAUDE_REVIEW_MAX_TOKENS = int(os.getenv("CLAUDE_REVIEW_MAX_TOKENS", "260"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_COMMENTARY_MODEL = os.getenv("OPENAI_COMMENTARY_MODEL", "gpt-5-mini")
OPENAI_WEB_SEARCH = os.getenv("OPENAI_WEB_SEARCH", "true").lower() == "true"
OPENAI_COMMENTARY_MAX_TOKENS = int(os.getenv("OPENAI_COMMENTARY_MAX_TOKENS", "320"))
OPENAI_MACRO_MAX_TOKENS = int(os.getenv("OPENAI_MACRO_MAX_TOKENS", "220"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SYMBOL = os.getenv("SYMBOL", "XAUUSD")

RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.015"))
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "80"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "1"))
MIN_RR = float(os.getenv("MIN_RR", "1.5"))
TP_RR = float(os.getenv("TP_RR", "2.0"))

AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"
MIN_SIGNAL_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "84"))
MIN_EXECUTION_SCORE = int(os.getenv("MIN_EXECUTION_SCORE", "90"))
LOCAL_REVIEW_THRESHOLD = int(os.getenv("LOCAL_REVIEW_THRESHOLD", "78"))
SIGNAL_MACRO_VETO_THRESHOLD = int(os.getenv("SIGNAL_MACRO_VETO_THRESHOLD", "88"))
BUY_ONLY = os.getenv("BUY_ONLY", "false").lower() == "true"

SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
CLAUDE_REVIEW_ON_NEW_M5_ONLY = os.getenv("CLAUDE_REVIEW_ON_NEW_M5_ONLY", "true").lower() == "true"
COMMENTARY_ONLY_ON_SESSION_EVENTS = os.getenv("COMMENTARY_ONLY_ON_SESSION_EVENTS", "true").lower() == "true"
MAX_CANDIDATES_PER_SCAN = int(os.getenv("MAX_CANDIDATES_PER_SCAN", "2"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "gold_master_state.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

SESSION_WINDOW_MINUTES = int(os.getenv("SESSION_WINDOW_MINUTES", "20"))
PULSE_UPDATE_MINUTES = int(os.getenv("PULSE_UPDATE_MINUTES", "240"))
NEWS_STYLE_UPDATE_MINUTES = int(os.getenv("NEWS_STYLE_UPDATE_MINUTES", "180"))

ENABLE_STARTUP_UPDATE = os.getenv("ENABLE_STARTUP_UPDATE", "true").lower() == "true"
ENABLE_SESSION_UPDATES = os.getenv("ENABLE_SESSION_UPDATES", "true").lower() == "true"
ENABLE_PULSE_UPDATES = os.getenv("ENABLE_PULSE_UPDATES", "false").lower() == "true"
ENABLE_MACRO_UPDATES = os.getenv("ENABLE_MACRO_UPDATES", "true").lower() == "true"

ENABLE_TREND_PULLBACK = os.getenv("ENABLE_TREND_PULLBACK", "true").lower() == "true"
ENABLE_BREAKOUT_CONTINUATION = os.getenv("ENABLE_BREAKOUT_CONTINUATION", "true").lower() == "true"
ENABLE_BREAKOUT_RETEST = os.getenv("ENABLE_BREAKOUT_RETEST", "true").lower() == "true"
ENABLE_LIQUIDITY_REVERSAL = os.getenv("ENABLE_LIQUIDITY_REVERSAL", "true").lower() == "true"
ENABLE_IMPULSE_CONTINUATION = os.getenv("ENABLE_IMPULSE_CONTINUATION", "true").lower() == "true"
