import os
from dotenv import load_dotenv

load_dotenv()

# MT5 / Broker
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
ENABLE_WEB_NEWS_STYLE_UPDATE = os.getenv("ENABLE_WEB_NEWS_STYLE_UPDATE", "true").lower() == "true"
ENABLE_WEB_SIGNAL_VETO = os.getenv("ENABLE_WEB_SIGNAL_VETO", "true").lower() == "true"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Trading
SYMBOL = os.getenv("SYMBOL", "XAUUSD")

# Risk / Execution
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.015"))
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "80"))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "1"))
MIN_RR = float(os.getenv("MIN_RR", "1.5"))
TP_RR = float(os.getenv("TP_RR", "2.0"))

AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"
MIN_SIGNAL_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "84"))
MIN_EXECUTION_SCORE = int(os.getenv("MIN_EXECUTION_SCORE", "90"))
SIGNAL_MACRO_VETO_THRESHOLD = int(os.getenv("SIGNAL_MACRO_VETO_THRESHOLD", "88"))
BUY_ONLY = os.getenv("BUY_ONLY", "false").lower() == "true"

# Bot behavior
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
CLOSED_LOOP_SLEEP_SECONDS = int(os.getenv("CLOSED_LOOP_SLEEP_SECONDS", "300"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))
REJECTION_COOLDOWN_MINUTES = int(os.getenv("REJECTION_COOLDOWN_MINUTES", "25"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "gold_master_state.json")

# Session / commentary cadence
SESSION_WINDOW_MINUTES = int(os.getenv("SESSION_WINDOW_MINUTES", "20"))
PULSE_UPDATE_MINUTES = int(os.getenv("PULSE_UPDATE_MINUTES", "240"))
NEWS_STYLE_UPDATE_MINUTES = int(os.getenv("NEWS_STYLE_UPDATE_MINUTES", "180"))

# Market hours (UTC, configurable per broker)
MARKET_OPEN_SUNDAY_UTC = os.getenv("MARKET_OPEN_SUNDAY_UTC", "22:05")
MARKET_CLOSE_FRIDAY_UTC = os.getenv("MARKET_CLOSE_FRIDAY_UTC", "21:55")

# Strategy toggles
ENABLE_TREND_PULLBACK = os.getenv("ENABLE_TREND_PULLBACK", "true").lower() == "true"
ENABLE_BREAKOUT_CONTINUATION = os.getenv("ENABLE_BREAKOUT_CONTINUATION", "true").lower() == "true"
ENABLE_BREAKOUT_RETEST = os.getenv("ENABLE_BREAKOUT_RETEST", "true").lower() == "true"
ENABLE_LIQUIDITY_REVERSAL = os.getenv("ENABLE_LIQUIDITY_REVERSAL", "true").lower() == "true"
ENABLE_IMPULSE_CONTINUATION = os.getenv("ENABLE_IMPULSE_CONTINUATION", "true").lower() == "true"
ENABLE_FAILED_BOUNCE_CONTINUATION = os.getenv("ENABLE_FAILED_BOUNCE_CONTINUATION", "true").lower() == "true"

MAX_CANDIDATES_PER_SCAN = int(os.getenv("MAX_CANDIDATES_PER_SCAN", "2"))
