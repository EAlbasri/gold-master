import os
from dotenv import load_dotenv

load_dotenv()

# MT5
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# Claude / Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
USE_CLAUDE_WEB_SEARCH = os.getenv("USE_CLAUDE_WEB_SEARCH", "true").lower() == "true"
ENABLE_WEB_STARTUP_UPDATE = os.getenv("ENABLE_WEB_STARTUP_UPDATE", "true").lower() == "true"
ENABLE_WEB_SESSION_UPDATE = os.getenv("ENABLE_WEB_SESSION_UPDATE", "true").lower() == "true"
ENABLE_WEB_PULSE_UPDATE = os.getenv("ENABLE_WEB_PULSE_UPDATE", "false").lower() == "true"
ENABLE_WEB_MACRO_UPDATE = os.getenv("ENABLE_WEB_MACRO_UPDATE", "true").lower() == "true"
ENABLE_SIGNAL_MACRO_VETO = os.getenv("ENABLE_SIGNAL_MACRO_VETO", "true").lower() == "true"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Trading / behavior
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
BUY_ONLY = os.getenv("BUY_ONLY", "false").lower() == "true"
AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"

RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.015"))
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "80"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "1"))
MIN_RR = float(os.getenv("MIN_RR", "1.4"))
TP_RR = float(os.getenv("TP_RR", "2.0"))

MIN_SIGNAL_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "84"))
MIN_EXECUTION_SCORE = int(os.getenv("MIN_EXECUTION_SCORE", "90"))
SIGNAL_MACRO_VETO_THRESHOLD = int(os.getenv("SIGNAL_MACRO_VETO_THRESHOLD", "88"))

SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))
REJECTION_COOLDOWN_MINUTES = int(os.getenv("REJECTION_COOLDOWN_MINUTES", "30"))
MAX_CANDIDATES_PER_SCAN = int(os.getenv("MAX_CANDIDATES_PER_SCAN", "2"))
M5_REVIEW_ON_NEW_BAR_ONLY = os.getenv("M5_REVIEW_ON_NEW_BAR_ONLY", "true").lower() == "true"

STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "gold_master_state.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Commentary cadence
SESSION_WINDOW_MINUTES = int(os.getenv("SESSION_WINDOW_MINUTES", "20"))
PULSE_UPDATE_MINUTES = int(os.getenv("PULSE_UPDATE_MINUTES", "240"))
MACRO_UPDATE_MINUTES = int(os.getenv("MACRO_UPDATE_MINUTES", "180"))
ENABLE_PULSE_UPDATES = os.getenv("ENABLE_PULSE_UPDATES", "false").lower() == "true"
ENABLE_SESSION_UPDATES = os.getenv("ENABLE_SESSION_UPDATES", "true").lower() == "true"
ENABLE_MACRO_UPDATES = os.getenv("ENABLE_MACRO_UPDATES", "true").lower() == "true"
ENABLE_STARTUP_UPDATE = os.getenv("ENABLE_STARTUP_UPDATE", "true").lower() == "true"

# Strategy toggles
ENABLE_BREAKOUT_CONTINUATION = os.getenv("ENABLE_BREAKOUT_CONTINUATION", "true").lower() == "true"
ENABLE_BREAKOUT_RETEST = os.getenv("ENABLE_BREAKOUT_RETEST", "true").lower() == "true"
ENABLE_LIQUIDITY_REVERSAL = os.getenv("ENABLE_LIQUIDITY_REVERSAL", "true").lower() == "true"
ENABLE_TREND_PULLBACK = os.getenv("ENABLE_TREND_PULLBACK", "true").lower() == "true"
ENABLE_FAILED_BOUNCE_CONTINUATION = os.getenv("ENABLE_FAILED_BOUNCE_CONTINUATION", "true").lower() == "true"
ENABLE_IMPULSE_CONTINUATION = os.getenv("ENABLE_IMPULSE_CONTINUATION", "true").lower() == "true"
