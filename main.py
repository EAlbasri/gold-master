import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from config import (
    AUTO_EXECUTE,
    COOLDOWN_MINUTES,
    ENABLE_WEB_NEWS_STYLE_UPDATE,
    ENABLE_WEB_PULSE_UPDATE,
    ENABLE_WEB_SESSION_UPDATE,
    ENABLE_WEB_SIGNAL_VETO,
    ENABLE_WEB_STARTUP_UPDATE,
    MAX_CANDIDATES_PER_SCAN,
    MAX_DAILY_LOSS,
    MAX_OPEN_TRADES,
    MAX_SPREAD_POINTS,
    MIN_EXECUTION_SCORE,
    MIN_SIGNAL_SCORE,
    NEWS_STYLE_UPDATE_MINUTES,
    PULSE_UPDATE_MINUTES,
    RISK_PER_TRADE,
    SCAN_INTERVAL_SECONDS,
    SESSION_WINDOW_MINUTES,
    SIGNAL_MACRO_VETO_THRESHOLD,
    SYMBOL,
    USE_CLAUDE_WEB_SEARCH,
)
from llm_claude import daily_market_analysis, evaluate_setup, macro_news_brief, macro_veto_for_setup
from mt5_client import connect, ensure_connection, get_account_info, get_open_positions, place_buy, place_sell, shutdown
from risk import calc_lot_size
from state_store import load_state, save_state
from strategy import generate_setup_candidates, get_market_snapshot, spread_ok
from telegram_client import send_human_update, send_structured_signal


BHR_TZ = ZoneInfo("Asia/Bahrain")

SESSION_DEFS = {
    "Asia": {"tz": ZoneInfo("Asia/Tokyo"), "hour": 9, "minute": 0},
    "London": {"tz": ZoneInfo("Europe/London"), "hour": 8, "minute": 0},
    "New York": {"tz": ZoneInfo("America/New_York"), "hour": 8, "minute": 0},
}

LAST_SIGNAL_AT = None
LAST_SIGNAL_SIDE = None
LAST_PULSE_AT = None
LAST_NEWS_STYLE_AT = None
LAST_SESSION_SENT = {}


def now_bahrain():
    return datetime.now(BHR_TZ)


def current_session_name():
    bhr = now_bahrain()
    tokyo = bhr.astimezone(SESSION_DEFS["Asia"]["tz"])
    london = bhr.astimezone(SESSION_DEFS["London"]["tz"])
    ny = bhr.astimezone(SESSION_DEFS["New York"]["tz"])

    if 9 <= tokyo.hour < 17:
        return "Asia"
    if 8 <= london.hour < 16:
        return "London"
    if 8 <= ny.hour < 17:
        return "New York"
    return "Off-session"


def build_analysis_bundle(context, use_web):
    state = load_state()
    snapshot = get_market_snapshot(SYMBOL)

    payload = {
        "market_snapshot": snapshot,
        "context": context,
        "persistent_state": {
            "last_analysis": state.get("last_analysis", {}),
            "watched_levels": state.get("watched_levels", {}),
            "last_signal": state.get("last_signal", {}),
            "session": current_session_name(),
        },
    }

    analysis = daily_market_analysis(payload, use_web=bool(use_web and USE_CLAUDE_WEB_SEARCH))

    state["last_analysis"] = {
        "context": context,
        "timestamp": now_bahrain().isoformat(),
        "bias": analysis.get("bias"),
        "summary": analysis.get("summary"),
    }
    state["watched_levels"] = {
        "key_level_up": analysis.get("key_level_up"),
        "key_level_down": analysis.get("key_level_down"),
        "expected_high": analysis.get("expected_high"),
        "expected_low": analysis.get("expected_low"),
    }
    save_state(state)

    return {"snapshot": snapshot, "analysis": analysis, "state": state}


def get_time_greeting():
    hour = now_bahrain().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def build_welcome_message(bundle):
    snapshot = bundle["snapshot"]
    analysis = bundle["analysis"]
    return (
        "{0} everyone — Gold Master here.\n\n"
        "I’m live and watching XAUUSD from here.\n\n"
        "Current market read:\n"
        "Bias: {1}\n"
        "Regime: {2}\n"
        "Expected high today: {3}\n"
        "Expected low today: {4}\n"
        "Key upside level: {5}\n"
        "Key downside level: {6}\n"
        "Current bid/ask: {7} / {8}\n\n"
        "My read:\n{9}"
    ).format(
        get_time_greeting(),
        analysis.get("bias", "sideways").upper(),
        snapshot.get("regime", "unknown"),
        analysis.get("expected_high", "N/A"),
        analysis.get("expected_low", "N/A"),
        analysis.get("key_level_up", "N/A"),
        analysis.get("key_level_down", "N/A"),
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("summary", "I’m watching structure, regime, and session flow before I get aggressive."),
    )


def build_session_message(session_name, bundle):
    analysis = bundle["analysis"]
    snapshot = bundle["snapshot"]
    return (
        "Gold Master here — {0} session is opening now.\n\n"
        "What I’m watching:\n"
        "Bias: {1}\n"
        "Regime: {2}\n"
        "Current bid/ask: {3} / {4}\n"
        "Expected session focus: {5} to {6}\n\n"
        "My take:\n{7}"
    ).format(
        session_name,
        analysis.get("bias", "sideways").upper(),
        snapshot.get("regime", "unknown"),
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("expected_low", "N/A"),
        analysis.get("expected_high", "N/A"),
        analysis.get("summary", "The market is still shaping up, so I’m waiting for cleaner structure."),
    )


def build_pulse_message(bundle):
    analysis = bundle["analysis"]
    snapshot = bundle["snapshot"]
    return (
        "Quick check-in from Gold Master.\n\n"
        "Gold is currently trading around {0} / {1}, and the broader tone still looks {2}.\n"
        "The current regime reads as {3}.\n"
        "{4}"
    ).format(
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("bias", "sideways"),
        snapshot.get("regime", "unknown"),
        analysis.get("summary", "I’m staying patient and waiting for the cleanest structure."),
    )


def build_macro_note(brief):
    return "Gold Master note:\n\n{0}\n\n{1}".format(
        brief.get("headline", "Fresh macro movement is on the radar."),
        brief.get("impact_note", "I’m watching how price responds before leaning too hard either way."),
    )


def build_signal_lines(setup):
    verdict = setup["verdict"]
    lines = [
        "XAUUSD {0}".format(setup["direction"].upper()),
        "Setup type: {0}".format(setup["setup_type"]),
        "Regime: {0}".format(setup["snapshot"]["regime"]),
        "Entry: {0:.2f}".format(setup["entry"]),
        "Stop loss: {0:.2f}".format(setup["sl"]),
        "Take profit 1: {0:.2f}".format(setup["tp"]),
        "Take profit 2: {0:.2f}".format(setup["tp2"]),
        "",
        "Confidence score: {0}".format(verdict.get("score", 0)),
        "Trigger level: {0}".format(setup.get("trigger_level")),
        "RR: {0}".format(setup.get("rr", "N/A")),
        "",
        "Note: {0}".format(verdict.get("reason", setup.get("notes", "Gold Master likes the structure here."))),
    ]
    if setup.get("macro_note"):
        lines.extend(["", "Macro check: {0}".format(setup["macro_note"])])
    return lines


def build_execution_lines(setup, lot, result):
    return [
        "XAUUSD {0}".format(setup["direction"].upper()),
        "Setup type: {0}".format(setup["setup_type"]),
        "Volume: {0}".format(lot),
        "Entry: {0:.2f}".format(setup["entry"]),
        "Stop loss: {0:.2f}".format(setup["sl"]),
        "Take profit: {0:.2f}".format(setup["tp"]),
        "",
        "Broker retcode: {0}".format(getattr(result, "retcode", "N/A")),
    ]


def get_session_open_bahrain(session_name, current_bhr):
    session = SESSION_DEFS[session_name]
    local_now = current_bhr.astimezone(session["tz"])
    local_open = local_now.replace(hour=session["hour"], minute=session["minute"], second=0, microsecond=0)
    return local_open.astimezone(BHR_TZ)


def maybe_send_session_updates():
    current_bhr = now_bahrain()
    for session_name in SESSION_DEFS:
        open_bhr = get_session_open_bahrain(session_name, current_bhr)
        session_key = "{0}:{1}".format(session_name, open_bhr.strftime("%Y-%m-%d %H:%M"))
        in_window = open_bhr <= current_bhr < open_bhr + timedelta(minutes=SESSION_WINDOW_MINUTES)
        already_sent = LAST_SESSION_SENT.get(session_key, False)
        if in_window and not already_sent:
            bundle = build_analysis_bundle(context="{0}_session_open".format(session_name.lower()), use_web=ENABLE_WEB_SESSION_UPDATE)
            send_human_update(build_session_message(session_name, bundle))
            LAST_SESSION_SENT[session_key] = True


def maybe_send_pulse_update():
    global LAST_PULSE_AT
    current_bhr = now_bahrain()
    if LAST_PULSE_AT and current_bhr - LAST_PULSE_AT < timedelta(minutes=PULSE_UPDATE_MINUTES):
        return
    bundle = build_analysis_bundle(context="pulse_update", use_web=ENABLE_WEB_PULSE_UPDATE)
    send_human_update(build_pulse_message(bundle))
    LAST_PULSE_AT = current_bhr


def maybe_send_macro_note():
    global LAST_NEWS_STYLE_AT
    current_bhr = now_bahrain()
    if LAST_NEWS_STYLE_AT and current_bhr - LAST_NEWS_STYLE_AT < timedelta(minutes=NEWS_STYLE_UPDATE_MINUTES):
        return
    state = load_state()
    snapshot = get_market_snapshot(SYMBOL)
    brief = macro_news_brief(
        {"symbol": SYMBOL, "market_snapshot": snapshot, "persistent_state": state, "context": "macro_update"},
        use_web=ENABLE_WEB_NEWS_STYLE_UPDATE,
    )
    if brief.get("has_update", False):
        headline = brief.get("headline", "")
        if headline and headline != state.get("last_macro_headline", ""):
            send_human_update(build_macro_note(brief))
            state["last_macro_headline"] = headline
            save_state(state)
    LAST_NEWS_STYLE_AT = current_bhr


def can_send_signal(direction):
    global LAST_SIGNAL_AT, LAST_SIGNAL_SIDE
    if LAST_SIGNAL_AT is None:
        return True
    if LAST_SIGNAL_SIDE != direction:
        return True
    return now_bahrain() - LAST_SIGNAL_AT >= timedelta(minutes=COOLDOWN_MINUTES)


def mark_signal_sent(direction, setup):
    global LAST_SIGNAL_AT, LAST_SIGNAL_SIDE
    LAST_SIGNAL_AT = now_bahrain()
    LAST_SIGNAL_SIDE = direction
    state = load_state()
    state["last_signal"] = {
        "timestamp": LAST_SIGNAL_AT.isoformat(),
        "direction": direction,
        "setup_type": setup["setup_type"],
        "entry": setup["entry"],
        "sl": setup["sl"],
        "tp": setup["tp"],
        "tp2": setup["tp2"],
    }
    save_state(state)


def daily_loss_limit_hit():
    account = get_account_info()
    drawdown = (account.balance - account.equity) / max(account.balance, 1.0)
    return drawdown >= MAX_DAILY_LOSS


def _run_macro_veto(candidate, snapshot, state):
    verdict = candidate["verdict"]
    score = int(verdict.get("score", 0))
    if score < SIGNAL_MACRO_VETO_THRESHOLD:
        return candidate
    if not ENABLE_WEB_SIGNAL_VETO:
        return candidate

    payload = {
        "symbol": SYMBOL,
        "market_snapshot": snapshot,
        "candidate": candidate,
        "persistent_state": {
            "last_analysis": state.get("last_analysis", {}),
            "watched_levels": state.get("watched_levels", {}),
            "last_signal": state.get("last_signal", {}),
            "session": current_session_name(),
        },
        "context": "signal_macro_veto",
    }
    veto = macro_veto_for_setup(payload, use_web=True)
    candidate["macro_veto"] = veto
    candidate["macro_note"] = veto.get("macro_reason", "")

    adjusted_score = int(veto.get("adjusted_score", score)) if veto.get("adjusted_score") else score
    candidate["verdict"]["score"] = adjusted_score
    if not veto.get("allow_trade", True) or veto.get("risk_flag") == "veto":
        candidate["verdict"]["trade"] = False
    return candidate


def scan_for_setup():
    if not spread_ok(SYMBOL, MAX_SPREAD_POINTS):
        return None
    snapshot, candidates = generate_setup_candidates(SYMBOL)
    if not candidates:
        return None

    state = load_state()
    best = None
    for candidate in candidates[:MAX_CANDIDATES_PER_SCAN]:
        payload = {
            "symbol": SYMBOL,
            "setup_type": candidate["setup_type"],
            "direction_candidate": candidate["direction"],
            "market_snapshot": snapshot,
            "candidate": candidate,
            "persistent_state": {
                "last_analysis": state.get("last_analysis", {}),
                "watched_levels": state.get("watched_levels", {}),
                "last_signal": state.get("last_signal", {}),
                "session": current_session_name(),
            },
        }
        verdict = evaluate_setup(payload)
        candidate["verdict"] = verdict
        candidate["snapshot"] = snapshot

        if not bool(verdict.get("trade", False)):
            continue
        if int(verdict.get("score", 0)) < MIN_SIGNAL_SCORE:
            continue

        candidate = _run_macro_veto(candidate, snapshot, state)
        if not bool(candidate["verdict"].get("trade", False)):
            continue
        if int(candidate["verdict"].get("score", 0)) < MIN_SIGNAL_SCORE:
            continue

        if best is None or int(candidate["verdict"].get("score", 0)) > int(best["verdict"].get("score", 0)):
            best = candidate
    return best


def maybe_execute_trade(setup):
    verdict = setup["verdict"]
    direction = setup["direction"]
    score = int(verdict.get("score", 0))
    sl_valid = verdict.get("sl_valid", True)
    tp_valid = verdict.get("tp_valid", True)

    if score >= MIN_SIGNAL_SCORE and can_send_signal(direction):
        send_structured_signal("Gold Master signal", build_signal_lines(setup))
        mark_signal_sent(direction, setup)

    if not AUTO_EXECUTE:
        return
    if daily_loss_limit_hit():
        return
    if score < MIN_EXECUTION_SCORE or not sl_valid or not tp_valid:
        return

    open_positions = get_open_positions(SYMBOL)
    if len(open_positions) >= MAX_OPEN_TRADES:
        return

    account = get_account_info()
    lot = calc_lot_size(SYMBOL, setup["entry"], setup["sl"], account.balance, RISK_PER_TRADE)
    if lot <= 0:
        return

    if direction == "buy":
        result = place_buy(SYMBOL, lot=lot, sl=setup["sl"], tp=setup["tp"], comment="gold_master_buy")
    else:
        result = place_sell(SYMBOL, lot=lot, sl=setup["sl"], tp=setup["tp"], comment="gold_master_sell")

    send_structured_signal("Gold Master update — order is in", build_execution_lines(setup, lot, result))


def send_welcome_message():
    bundle = build_analysis_bundle(context="startup", use_web=ENABLE_WEB_STARTUP_UPDATE)
    send_human_update(build_welcome_message(bundle))


def run_forever():
    connect()
    print("Gold Master connected to MT5.")

    try:
        send_welcome_message()
    except Exception as e:
        print("Startup message failed: {0}".format(e))

    while True:
        try:
            ensure_connection()
            maybe_send_session_updates()
            maybe_send_macro_note()
            maybe_send_pulse_update()

            setup = scan_for_setup()
            if setup:
                maybe_execute_trade(setup)

            time.sleep(max(SCAN_INTERVAL_SECONDS, 5))
        except KeyboardInterrupt:
            print("Gold Master stopped manually.")
            try:
                send_human_update("Gold Master signing off for now.")
            except Exception:
                pass
            break
        except Exception as e:
            print("Loop error: {0}".format(e))
            try:
                send_human_update("Gold Master note: I hit a temporary connection or processing issue and I’m reconnecting.")
            except Exception:
                pass
            time.sleep(15)

    shutdown()


if __name__ == "__main__":
    run_forever()
