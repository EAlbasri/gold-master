import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from anthropic_client import daily_market_analysis, evaluate_setup, macro_news_brief
from config import (
    AUTO_EXECUTE,
    CLOSED_LOOP_SLEEP_SECONDS,
    COOLDOWN_MINUTES,
    ENABLE_WEB_NEWS_STYLE_UPDATE,
    ENABLE_WEB_PULSE_UPDATE,
    ENABLE_WEB_SESSION_UPDATE,
    ENABLE_WEB_SIGNAL_VETO,
    ENABLE_WEB_STARTUP_UPDATE,
    LOCAL_REVIEW_MIN_SCORE,
    MARKET_CLOSE_FRIDAY_UTC,
    MARKET_OPEN_SUNDAY_UTC,
    MAX_CANDIDATES_PER_SYMBOL,
    MAX_DAILY_LOSS,
    MAX_OPEN_TRADES,
    MAX_REVIEWS_PER_CYCLE,
    MIN_EXECUTION_SCORE,
    MIN_RR,
    MIN_SIGNAL_SCORE,
    NEWS_STYLE_UPDATE_MINUTES,
    PULSE_UPDATE_MINUTES,
    RISK_PER_TRADE,
    SCAN_INTERVAL_SECONDS,
    SESSION_WINDOW_MINUTES,
    SIGNAL_MACRO_VETO_THRESHOLD,
    SYMBOLS,
)
from mt5_client import connect, ensure_connection, get_account_info, get_open_positions, place_buy, place_sell, shutdown
from risk import calc_lot_size
from state_store import is_candidate_on_cooldown, load_state, mark_candidate_rejected, prune_rejections, save_state, symbol_state
from strategy import generate_setup_candidates, get_market_snapshot, get_profile, spread_ok
from telegram_client import send_human_update, send_structured_signal


BHR_TZ = ZoneInfo("Asia/Bahrain")
UTC_TZ = ZoneInfo("UTC")

SESSION_DEFS = {
    "Asia": {"tz": ZoneInfo("Asia/Tokyo"), "hour": 9, "minute": 0},
    "London": {"tz": ZoneInfo("Europe/London"), "hour": 8, "minute": 0},
    "New York": {"tz": ZoneInfo("America/New_York"), "hour": 8, "minute": 0},
}

LAST_SIGNAL_AT = None
LAST_SIGNAL_KEY = None
LAST_PULSE_AT = None
LAST_NEWS_STYLE_AT = None
LAST_SESSION_SENT = {}


def now_bahrain():
    return datetime.now(BHR_TZ)


def now_utc():
    return datetime.now(UTC_TZ)


def _parse_hhmm(value):
    parts = value.split(":")
    return int(parts[0]), int(parts[1])


def market_is_open(dt_utc=None):
    dt_utc = dt_utc or now_utc()
    weekday = dt_utc.weekday()  # Mon=0 Sun=6
    sun_h, sun_m = _parse_hhmm(MARKET_OPEN_SUNDAY_UTC)
    fri_h, fri_m = _parse_hhmm(MARKET_CLOSE_FRIDAY_UTC)
    minutes = dt_utc.hour * 60 + dt_utc.minute

    if weekday == 5:
        return False
    if weekday == 6:
        return minutes >= (sun_h * 60 + sun_m)
    if weekday == 4:
        return minutes < (fri_h * 60 + fri_m)
    return True


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
    primary = SYMBOLS[0]
    snapshot = get_market_snapshot(primary)
    payload = {
        "market_snapshot": snapshot,
        "context": context,
        "tracked_symbols": SYMBOLS,
        "persistent_state": {
            "last_analysis": state.get("last_analysis", {}),
            "watched_levels": state.get("watched_levels", {}),
            "last_signal": state.get("last_signal", {}),
            "session": current_session_name(),
            "market_open": market_is_open(),
        },
    }
    analysis = daily_market_analysis(payload, use_web=use_web)
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
        "I'm live and watching: {1}.\n\n"
        "Current market read (lead symbol: {2}):\n"
        "Bias: {3}\n"
        "Regime: {4}\n"
        "Expected high today: {5}\n"
        "Expected low today: {6}\n"
        "Key upside level: {7}\n"
        "Key downside level: {8}\n"
        "Current bid/ask: {9} / {10}\n\n"
        "My read:\n"
        "{11}"
    ).format(
        get_time_greeting(),
        ", ".join(SYMBOLS),
        snapshot["symbol"],
        analysis.get("bias", "sideways").upper(),
        snapshot.get("regime", "unknown"),
        analysis.get("expected_high", "N/A"),
        analysis.get("expected_low", "N/A"),
        analysis.get("key_level_up", "N/A"),
        analysis.get("key_level_down", "N/A"),
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("summary", "I'm watching structure, regime, and session flow before I get aggressive."),
    )


def build_market_closed_message():
    return "Gold Master here.\n\nThe market is closed right now, so I'm standing down on fresh trade calls and commentary until the next open."


def build_market_reopen_message(bundle):
    snapshot = bundle["snapshot"]
    analysis = bundle["analysis"]
    return (
        "Gold Master is back on the desk — the market is open again.\n\n"
        "Current bid/ask ({0}): {1} / {2}\n"
        "Bias: {3}\n"
        "Regime: {4}\n\n"
        "{5}"
    ).format(
        snapshot["symbol"],
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("bias", "sideways").upper(),
        snapshot.get("regime", "unknown"),
        analysis.get("summary", "I'm re-checking structure and macro context before leaning into anything."),
    )


def build_session_message(session_name, bundle):
    analysis = bundle["analysis"]
    snapshot = bundle["snapshot"]
    return (
        "Gold Master here — {0} session is opening now.\n\n"
        "What I'm watching ({1}):\n"
        "Bias: {2}\n"
        "Regime: {3}\n"
        "Current bid/ask: {4} / {5}\n"
        "Expected session focus: {6} to {7}\n\n"
        "My take:\n"
        "{8}"
    ).format(
        session_name,
        snapshot["symbol"],
        analysis.get("bias", "sideways").upper(),
        snapshot.get("regime", "unknown"),
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("expected_low", "N/A"),
        analysis.get("expected_high", "N/A"),
        analysis.get("summary", "The market is still shaping up, so I'm waiting for cleaner structure."),
    )


def build_pulse_message(symbol, snapshot):
    return (
        "Quick check-in from Gold Master.\n\n"
        "{0} is trading around {1} / {2}.\n"
        "Bias: {3}\n"
        "Regime: {4}\n"
        "Recent range: {5}"
    ).format(
        symbol,
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        snapshot.get("bias", "sideways"),
        snapshot.get("regime", "unknown"),
        snapshot.get("recent_structure", {}).get("recent_range", 0),
    )


def build_macro_note(brief):
    return "Gold Master note:\n\n{0}\n\n{1}".format(
        brief.get("headline", "Fresh macro movement is on the radar."),
        brief.get("impact_note", "I'm watching how price responds before leaning too hard either way."),
    )


def build_signal_lines(setup):
    verdict = setup["verdict"]
    return [
        "{0} {1}".format(setup["symbol"], setup["direction"].upper()),
        "Setup type: {0}".format(setup["setup_type"]),
        "Regime: {0}".format(setup["snapshot"]["regime"]),
        "Local score: {0}".format(setup.get("local_score")),
        "Confidence score: {0}".format(verdict.get("score", 0)),
        "Entry: {0}".format(setup["entry"]),
        "Stop loss: {0}".format(setup["sl"]),
        "Take profit 1: {0}".format(setup["tp"]),
        "Take profit 2: {0}".format(setup["tp2"]),
        "",
        "Note: {0}".format(verdict.get("reason", setup.get("notes", "Gold Master likes the structure here."))),
    ]


def build_execution_lines(setup, lot, result):
    return [
        "{0} {1}".format(setup["symbol"], setup["direction"].upper()),
        "Setup type: {0}".format(setup["setup_type"]),
        "Volume: {0}".format(lot),
        "Entry: {0}".format(setup["entry"]),
        "Stop loss: {0}".format(setup["sl"]),
        "Take profit: {0}".format(setup["tp"]),
        "",
        "Broker retcode: {0}".format(getattr(result, "retcode", "N/A")),
    ]


def get_session_open_bahrain(session_name, current_bhr):
    session = SESSION_DEFS[session_name]
    local_now = current_bhr.astimezone(session["tz"])
    local_open = local_now.replace(hour=session["hour"], minute=session["minute"], second=0, microsecond=0)
    return local_open.astimezone(BHR_TZ)


def maybe_send_market_open_close_notes():
    state = load_state()
    market_open = market_is_open()
    current_day = now_utc().strftime("%Y-%m-%d")

    if not market_open and state.get("last_market_closed_note") != current_day:
        send_human_update(build_market_closed_message())
        state["last_market_closed_note"] = current_day
        save_state(state)

    if market_open and state.get("last_market_open_note") != current_day:
        bundle = build_analysis_bundle(context="market_reopen", use_web=ENABLE_WEB_STARTUP_UPDATE)
        send_human_update(build_market_reopen_message(bundle))
        state["last_market_open_note"] = current_day
        save_state(state)


def maybe_send_session_updates():
    if not market_is_open():
        return
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
    if not market_is_open() or current_session_name() == "Off-session":
        return
    current_bhr = now_bahrain()
    if LAST_PULSE_AT and current_bhr - LAST_PULSE_AT < timedelta(minutes=PULSE_UPDATE_MINUTES):
        return
    primary = SYMBOLS[0]
    snapshot = get_market_snapshot(primary)
    send_human_update(build_pulse_message(primary, snapshot))
    LAST_PULSE_AT = current_bhr


def maybe_send_macro_note():
    global LAST_NEWS_STYLE_AT
    if not market_is_open() or current_session_name() == "Off-session":
        return
    current_bhr = now_bahrain()
    if LAST_NEWS_STYLE_AT and current_bhr - LAST_NEWS_STYLE_AT < timedelta(minutes=NEWS_STYLE_UPDATE_MINUTES):
        return
    state = load_state()
    primary = SYMBOLS[0]
    snapshot = get_market_snapshot(primary)
    brief = macro_news_brief(
        {"symbol": primary, "market_snapshot": snapshot, "persistent_state": state, "context": "macro_update"},
        use_web=ENABLE_WEB_NEWS_STYLE_UPDATE,
    )
    if brief.get("has_update", False):
        headline = brief.get("headline", "")
        if headline and headline != state.get("last_macro_headline", ""):
            send_human_update(build_macro_note(brief))
            state["last_macro_headline"] = headline
            save_state(state)
    LAST_NEWS_STYLE_AT = current_bhr


def can_send_signal(signal_key):
    global LAST_SIGNAL_AT, LAST_SIGNAL_KEY
    if LAST_SIGNAL_AT is None:
        return True
    if LAST_SIGNAL_KEY != signal_key:
        return True
    return now_bahrain() - LAST_SIGNAL_AT >= timedelta(minutes=COOLDOWN_MINUTES)


def mark_signal_sent(signal_key, setup):
    global LAST_SIGNAL_AT, LAST_SIGNAL_KEY
    LAST_SIGNAL_AT = now_bahrain()
    LAST_SIGNAL_KEY = signal_key
    state = load_state()
    state["last_signal"] = {
        "timestamp": LAST_SIGNAL_AT.isoformat(),
        "symbol": setup["symbol"],
        "direction": setup["direction"],
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


def is_new_m5_bar(state, symbol, snapshot):
    current_bar = snapshot.get("m5_last_bar_time", "")
    sstate = symbol_state(state, symbol)
    last_bar = sstate.get("last_m5_bar_time", "")
    if current_bar != last_bar:
        sstate["last_m5_bar_time"] = current_bar
        save_state(state)
        return True
    return False


def should_send_candidate_to_claude(candidate, snapshot):
    regime = snapshot.get("regime", "sideways")
    setup_type = candidate.get("setup_type", "")
    direction = candidate.get("direction", "")
    entry = float(candidate.get("entry", 0))
    sl = float(candidate.get("sl", 0))
    tp = float(candidate.get("tp", 0))
    vwap = float(snapshot.get("m5_vwap", 0))
    recent_range = float(snapshot.get("recent_structure", {}).get("recent_range", 0))
    session_name = current_session_name()

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0.0

    if risk <= 0 or reward <= 0:
        return False, "bad_geometry"
    if rr < MIN_RR:
        return False, "rr_too_low"
    if candidate.get("local_score", 0) < LOCAL_REVIEW_MIN_SCORE:
        return False, "local_score_too_low"

    if regime in ["sideways", "sideways_compression"] and setup_type in ["trend_pullback", "impulse_continuation"]:
        return False, "wrong_regime"
    if session_name == "Off-session" and setup_type in ["breakout_continuation", "failed_bounce_continuation", "impulse_continuation"]:
        return False, "off_session"

    daily_atr = max(float(snapshot.get("daily_atr_14", 0.0)), abs(entry) * 0.001)
    vwap_distance = abs(entry - vwap)
    if setup_type not in ["breakout_continuation", "failed_bounce_continuation"] and vwap_distance > daily_atr * 0.28:
        return False, "too_far_from_vwap"
    if setup_type in ["breakout_continuation", "failed_bounce_continuation"] and vwap_distance > daily_atr * 0.42:
        return False, "too_far_from_vwap"

    if risk > max(daily_atr * 0.50, abs(entry) * 0.0014):
        return False, "risk_too_wide"
    if setup_type == "breakout_continuation":
        trigger = float(candidate.get("trigger_level", entry))
        if abs(entry - trigger) > max(risk * 1.4, daily_atr * 0.18):
            return False, "late_breakout"
    if setup_type == "breakout_retest" and recent_range < daily_atr * 0.18:
        return False, "range_too_small"

    return True, "ok"


def gather_candidates():
    state = load_state()
    state = prune_rejections(state, now_bahrain())
    save_state(state)

    session_name = current_session_name()
    candidates = []

    for symbol in SYMBOLS:
        profile = get_profile(symbol)
        if not spread_ok(symbol, profile["max_spread_points"]):
            continue
        snapshot, symbol_candidates = generate_setup_candidates(symbol, session_name)
        if not is_new_m5_bar(state, symbol, snapshot):
            continue
        for candidate in symbol_candidates[:MAX_CANDIDATES_PER_SYMBOL]:
            candidate["symbol"] = symbol
            candidate["snapshot"] = snapshot
            if is_candidate_on_cooldown(state, symbol, candidate, now_bahrain()):
                continue
            ok, reject_reason = should_send_candidate_to_claude(candidate, snapshot)
            if not ok:
                mark_candidate_rejected(state, symbol, candidate, now_bahrain(), reject_reason)
                continue
            candidates.append(candidate)

    save_state(state)
    candidates.sort(key=lambda x: (-x.get("local_score", 0), x["symbol"], x["setup_type"]))
    return candidates[:MAX_REVIEWS_PER_CYCLE]


def maybe_macro_veto(setup):
    if not ENABLE_WEB_SIGNAL_VETO:
        return True
    score = int(setup["verdict"].get("score", 0))
    if score < SIGNAL_MACRO_VETO_THRESHOLD:
        return True
    if setup["symbol"] not in ["XAUUSD", "USDJPY", "EURUSD"]:
        return True

    brief = macro_news_brief(
        {
            "symbol": setup["symbol"],
            "market_snapshot": setup["snapshot"],
            "candidate": {
                "setup_type": setup["setup_type"],
                "direction": setup["direction"],
                "entry": setup["entry"],
                "sl": setup["sl"],
                "tp": setup["tp"],
            },
            "context": "signal_veto",
        },
        use_web=True,
    )
    impact = brief.get("impact_note", "").lower()
    direction = setup["direction"]
    if direction == "buy" and any(x in impact for x in ["bearish", "stronger dollar", "higher yields", "risk-off for euro", "yen strength"]):
        return False
    if direction == "sell" and any(x in impact for x in ["bullish", "weaker dollar", "falling yields", "euro support", "yen weakness"]):
        return False
    return True


def review_and_select():
    reviewed = []
    state = load_state()
    for candidate in gather_candidates():
        payload = {
            "symbol": candidate["symbol"],
            "setup_type": candidate["setup_type"],
            "direction_candidate": candidate["direction"],
            "market_snapshot": candidate["snapshot"],
            "candidate": candidate,
            "persistent_state": {
                "last_analysis": state.get("last_analysis", {}),
                "watched_levels": state.get("watched_levels", {}),
                "last_signal": state.get("last_signal", {}),
                "session": current_session_name(),
                "market_open": market_is_open(),
            },
        }
        verdict = evaluate_setup(payload)
        candidate["verdict"] = verdict
        if not bool(verdict.get("trade", False)):
            mark_candidate_rejected(state, candidate["symbol"], candidate, now_bahrain(), "claude_reject")
            continue
        if int(verdict.get("score", 0)) < MIN_SIGNAL_SCORE:
            mark_candidate_rejected(state, candidate["symbol"], candidate, now_bahrain(), "score_too_low")
            continue
        reviewed.append(candidate)

    save_state(state)
    reviewed.sort(key=lambda x: (-int(x["verdict"].get("score", 0)), -x.get("local_score", 0)))
    return reviewed


def maybe_execute_trade(setup):
    verdict = setup["verdict"]
    direction = setup["direction"]
    signal_key = "{0}:{1}:{2}".format(setup["symbol"], setup["setup_type"], direction)
    score = int(verdict.get("score", 0))
    sl_valid = verdict.get("sl_valid", True)
    tp_valid = verdict.get("tp_valid", True)

    if score >= MIN_SIGNAL_SCORE and can_send_signal(signal_key):
        send_structured_signal("Gold Master signal", build_signal_lines(setup))
        mark_signal_sent(signal_key, setup)

    if not AUTO_EXECUTE:
        return
    if daily_loss_limit_hit():
        return
    if score < MIN_EXECUTION_SCORE or not sl_valid or not tp_valid:
        return
    if not maybe_macro_veto(setup):
        return

    open_positions = get_open_positions(setup["symbol"])
    if len(open_positions) >= MAX_OPEN_TRADES:
        return

    account = get_account_info()
    lot = calc_lot_size(setup["symbol"], setup["entry"], setup["sl"], account.balance, RISK_PER_TRADE)
    if lot <= 0:
        return

    if direction == "buy":
        result = place_buy(setup["symbol"], lot=lot, sl=setup["sl"], tp=setup["tp"], comment="gold_master_buy")
    else:
        result = place_sell(setup["symbol"], lot=lot, sl=setup["sl"], tp=setup["tp"], comment="gold_master_sell")

    send_structured_signal(
        "Gold Master update — order is in",
        build_execution_lines(setup, lot, result),
    )


def send_welcome_message():
    if not market_is_open():
        return
    bundle = build_analysis_bundle(context="startup", use_web=ENABLE_WEB_STARTUP_UPDATE)
    send_human_update(build_welcome_message(bundle))


def run_forever():
    connect()
    print("Gold Master multi-symbol engine connected to MT5.")

    try:
        send_welcome_message()
    except Exception as e:
        print("Startup message failed: {0}".format(e))

    while True:
        try:
            ensure_connection()
            maybe_send_market_open_close_notes()

            if not market_is_open():
                time.sleep(max(CLOSED_LOOP_SLEEP_SECONDS, 60))
                continue

            maybe_send_session_updates()
            maybe_send_macro_note()
            maybe_send_pulse_update()

            reviewed = review_and_select()
            for setup in reviewed:
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
            time.sleep(15)

    shutdown()


if __name__ == "__main__":
    run_forever()
