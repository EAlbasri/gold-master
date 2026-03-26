import os
import time
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from anthropic_client import daily_market_analysis, evaluate_setup, macro_news_brief, signal_macro_veto
from config import (
    AUTO_EXECUTE,
    COOLDOWN_MINUTES,
    ENABLE_MACRO_UPDATES,
    ENABLE_PULSE_UPDATES,
    ENABLE_SESSION_UPDATES,
    ENABLE_SIGNAL_MACRO_VETO,
    ENABLE_STARTUP_UPDATE,
    ENABLE_WEB_MACRO_UPDATE,
    ENABLE_WEB_PULSE_UPDATE,
    ENABLE_WEB_SESSION_UPDATE,
    ENABLE_WEB_STARTUP_UPDATE,
    LOG_LEVEL,
    M5_REVIEW_ON_NEW_BAR_ONLY,
    MACRO_UPDATE_MINUTES,
    MAX_CANDIDATES_PER_SCAN,
    MAX_DAILY_LOSS,
    MAX_OPEN_TRADES,
    MAX_SPREAD_POINTS,
    MIN_EXECUTION_SCORE,
    MIN_RR,
    MIN_SIGNAL_SCORE,
    PULSE_UPDATE_MINUTES,
    RISK_PER_TRADE,
    SCAN_INTERVAL_SECONDS,
    SESSION_WINDOW_MINUTES,
    SIGNAL_MACRO_VETO_THRESHOLD,
    SYMBOL,
)
from mt5_client import connect, ensure_connection, get_account_info, get_open_positions, place_buy, place_sell, shutdown
from risk import calc_lot_size
from state_store import candidate_fingerprint, is_rejection_cooled_down, load_state, prune_rejections, remember_rejection, save_state
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
LAST_MACRO_AT = None
LAST_SESSION_SENT = {}


def now_bahrain():
    return datetime.now(BHR_TZ)


def log(message):
    if LOG_LEVEL.upper() == "DEBUG":
        print(message)


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


def get_time_greeting():
    hour = now_bahrain().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


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
    analysis = daily_market_analysis(payload, use_web=use_web)

    state["last_analysis"] = {
        "timestamp": now_bahrain().isoformat(),
        "context": context,
        "bias": analysis.get("bias"),
        "summary": analysis.get("summary"),
    }
    state["watched_levels"] = {
        "expected_high": analysis.get("expected_high"),
        "expected_low": analysis.get("expected_low"),
        "key_level_up": analysis.get("key_level_up"),
        "key_level_down": analysis.get("key_level_down"),
    }
    save_state(state)

    return {"snapshot": snapshot, "analysis": analysis}


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
        "My read:\n"
        "{9}"
    ).format(
        get_time_greeting(),
        analysis.get("bias", snapshot.get("bias", "sideways")).upper(),
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
        "My take:\n"
        "{7}"
    ).format(
        session_name,
        analysis.get("bias", snapshot.get("bias", "sideways")).upper(),
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
        "Gold is trading around {0} / {1} and the broader tone looks {2}.\n"
        "Current regime: {3}.\n"
        "{4}"
    ).format(
        snapshot.get("current_bid"),
        snapshot.get("current_ask"),
        analysis.get("bias", snapshot.get("bias", "sideways")),
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
    return [
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
        "",
        "Note: {0}".format(verdict.get("reason", setup.get("notes", "Gold Master likes the structure here."))),
    ]


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
    if not ENABLE_SESSION_UPDATES:
        return
    current_bhr = now_bahrain()
    for session_name in SESSION_DEFS:
        open_bhr = get_session_open_bahrain(session_name, current_bhr)
        session_key = "{0}:{1}".format(session_name, open_bhr.strftime("%Y-%m-%d %H:%M"))
        in_window = open_bhr <= current_bhr < open_bhr + timedelta(minutes=SESSION_WINDOW_MINUTES)
        if in_window and not LAST_SESSION_SENT.get(session_key, False):
            bundle = build_analysis_bundle("{0}_session_open".format(session_name.lower()), ENABLE_WEB_SESSION_UPDATE)
            send_human_update(build_session_message(session_name, bundle))
            LAST_SESSION_SENT[session_key] = True


def maybe_send_pulse_update():
    global LAST_PULSE_AT
    if not ENABLE_PULSE_UPDATES:
        return
    current_bhr = now_bahrain()
    if LAST_PULSE_AT and current_bhr - LAST_PULSE_AT < timedelta(minutes=PULSE_UPDATE_MINUTES):
        return
    bundle = build_analysis_bundle("pulse_update", ENABLE_WEB_PULSE_UPDATE)
    send_human_update(build_pulse_message(bundle))
    LAST_PULSE_AT = current_bhr


def maybe_send_macro_note():
    global LAST_MACRO_AT
    if not ENABLE_MACRO_UPDATES:
        return
    current_bhr = now_bahrain()
    if LAST_MACRO_AT and current_bhr - LAST_MACRO_AT < timedelta(minutes=MACRO_UPDATE_MINUTES):
        return

    state = load_state()
    snapshot = get_market_snapshot(SYMBOL)
    brief = macro_news_brief(
        {
            "symbol": SYMBOL,
            "market_snapshot": snapshot,
            "persistent_state": state,
            "context": "macro_update",
        },
        use_web=ENABLE_WEB_MACRO_UPDATE,
    )
    if brief.get("has_update", False):
        headline = brief.get("headline", "")
        if headline and headline != state.get("last_macro_headline", ""):
            send_human_update(build_macro_note(brief))
            state["last_macro_headline"] = headline
            save_state(state)
    LAST_MACRO_AT = current_bhr


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


def should_send_candidate_to_claude(candidate, snapshot):
    regime = snapshot.get("regime", "sideways")
    setup_type = candidate.get("setup_type", "")
    direction = candidate.get("direction", "")
    entry = float(candidate.get("entry", 0))
    sl = float(candidate.get("sl", 0))
    tp = float(candidate.get("tp", 0))
    vwap = float(snapshot.get("m5_vwap", 0))
    recent_range = float(snapshot.get("recent_structure", {}).get("recent_range", 0))
    current_price = float(snapshot.get("current_ask") if direction == "buy" else snapshot.get("current_bid"))

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0
    if rr < MIN_RR:
        return False, "rr_too_low"

    if regime in ["sideways", "sideways_compression"]:
        if setup_type in ["trend_pullback", "impulse_continuation", "failed_bounce_continuation"]:
            return False, "wrong_regime"
        if recent_range < 18 and setup_type == "breakout_continuation":
            return False, "range_too_small"

    if direction == "buy" and current_price > vwap + 45 and setup_type == "breakout_continuation":
        return False, "too_far_above_vwap"
    if direction == "sell" and current_price < vwap - 45 and setup_type == "breakout_continuation":
        return False, "too_far_below_vwap"

    if risk > max(snapshot.get("daily_atr_14", 0) * 0.45, 22):
        return False, "risk_too_wide"

    if current_session_name() == "Off-session" and setup_type not in ["breakout_retest", "liquidity_reversal"]:
        return False, "off_session"

    return True, "ok"


def review_candidates(snapshot, candidates):
    state = prune_rejections(load_state())
    save_state(state)

    if M5_REVIEW_ON_NEW_BAR_ONLY:
        current_bar = snapshot.get("m5_last_bar_time", "")
        last_reviewed = state.get("last_reviewed_m5_bar", "")
        if current_bar and current_bar == last_reviewed:
            return None
        state["last_reviewed_m5_bar"] = current_bar
        save_state(state)

    best = None
    for candidate in candidates[:MAX_CANDIDATES_PER_SCAN]:
        if is_rejection_cooled_down(state, candidate):
            continue

        ok, local_reason = should_send_candidate_to_claude(candidate, snapshot)
        if not ok:
            remember_rejection(state, candidate, local_reason)
            save_state(state)
            continue

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
            remember_rejection(state, candidate, verdict.get("reason", "rejected"))
            save_state(state)
            continue
        if int(verdict.get("score", 0)) < MIN_SIGNAL_SCORE:
            remember_rejection(state, candidate, "score_too_low")
            save_state(state)
            continue
        if best is None or int(verdict.get("score", 0)) > int(best["verdict"].get("score", 0)):
            best = candidate

    return best


def maybe_apply_macro_veto(setup):
    if not ENABLE_SIGNAL_MACRO_VETO:
        return False, ""
    if int(setup["verdict"].get("score", 0)) < SIGNAL_MACRO_VETO_THRESHOLD:
        return False, ""

    state = load_state()
    result = signal_macro_veto(
        {
            "symbol": SYMBOL,
            "market_snapshot": setup["snapshot"],
            "candidate": setup,
            "persistent_state": state,
            "context": "signal_macro_veto",
        },
        use_web=True,
    )
    return result.get("block_trade", False), result.get("reason", "")


def maybe_execute_trade(setup):
    verdict = setup["verdict"]
    direction = setup["direction"]
    score = int(verdict.get("score", 0))
    sl_valid = verdict.get("sl_valid", True)
    tp_valid = verdict.get("tp_valid", True)

    if score >= MIN_SIGNAL_SCORE and can_send_signal(direction):
        blocked, reason = maybe_apply_macro_veto(setup)
        if blocked:
            state = load_state()
            remember_rejection(state, setup, "macro_veto:{0}".format(reason))
            save_state(state)
            return
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
    if not ENABLE_STARTUP_UPDATE:
        return
    bundle = build_analysis_bundle("startup", ENABLE_WEB_STARTUP_UPDATE)
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

            if spread_ok(SYMBOL, MAX_SPREAD_POINTS):
                snapshot, candidates = generate_setup_candidates(SYMBOL)
                if candidates:
                    setup = review_candidates(snapshot, candidates)
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
