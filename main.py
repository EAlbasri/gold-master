import time
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import MetaTrader5 as mt5
from anthropic_client import review_trade_candidate
from config import AUTO_EXECUTE, CLAUDE_REVIEW_ON_NEW_M5_ONLY, COOLDOWN_MINUTES, ENABLE_MACRO_UPDATES, ENABLE_PULSE_UPDATES, ENABLE_SESSION_UPDATES, ENABLE_STARTUP_UPDATE, LOCAL_REVIEW_THRESHOLD, MAX_CANDIDATES_PER_SCAN, MAX_DAILY_LOSS, MAX_OPEN_TRADES, MAX_SPREAD_POINTS, MIN_EXECUTION_SCORE, MIN_SIGNAL_SCORE, NEWS_STYLE_UPDATE_MINUTES, PULSE_UPDATE_MINUTES, RISK_PER_TRADE, SCAN_INTERVAL_SECONDS, SESSION_WINDOW_MINUTES, SIGNAL_MACRO_VETO_THRESHOLD, SYMBOL
from mt5_client import connect, ensure_connection, get_account_info, get_open_positions, place_buy, place_sell, shutdown, get_rates
from openai_client import generate_macro_brief, generate_market_commentary
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
LAST_MACRO_AT = None

def now_bahrain():
    return datetime.now(BHR_TZ)

def current_session_name():
    bhr = now_bahrain(); tokyo = bhr.astimezone(SESSION_DEFS["Asia"]["tz"]); london = bhr.astimezone(SESSION_DEFS["London"]["tz"]); ny = bhr.astimezone(SESSION_DEFS["New York"]["tz"])
    if 9 <= tokyo.hour < 17:
        return "Asia"
    if 8 <= london.hour < 16:
        return "London"
    if 8 <= ny.hour < 17:
        return "New York"
    return "Off-session"

def last_closed_m5_time():
    m5 = get_rates(SYMBOL, mt5.TIMEFRAME_M5, 3)
    return str(m5["time"].iloc[-2])

def daily_loss_limit_hit():
    account = get_account_info()
    drawdown = (account.balance - account.equity) / max(account.balance, 1.0)
    return drawdown >= MAX_DAILY_LOSS

def can_review_with_claude():
    if not CLAUDE_REVIEW_ON_NEW_M5_ONLY:
        return True
    state = load_state()
    last_reviewed = state.get("last_reviewed_m5_time", "")
    current_closed = last_closed_m5_time()
    if current_closed != last_reviewed:
        state["last_reviewed_m5_time"] = current_closed
        save_state(state)
        return True
    return False

def build_commentary_bundle(context, use_web):
    state = load_state(); snapshot = get_market_snapshot(SYMBOL)
    payload = {
        "market_snapshot": snapshot,
        "context": context,
        "persistent_state": {"last_analysis": state.get("last_analysis", {}), "watched_levels": state.get("watched_levels", {}), "last_signal": state.get("last_signal", {}), "session": current_session_name()},
    }
    analysis = generate_market_commentary(payload, use_web=use_web)
    state["last_analysis"] = {"context": context, "timestamp": now_bahrain().isoformat(), "bias": analysis.get("bias"), "summary": analysis.get("summary")}
    state["watched_levels"] = {"key_level_up": analysis.get("key_level_up"), "key_level_down": analysis.get("key_level_down"), "expected_high": analysis.get("expected_high"), "expected_low": analysis.get("expected_low")}
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
    snapshot = bundle["snapshot"]; analysis = bundle["analysis"]
    return ("{0} everyone — Gold Master here.\n\nI’m live and watching XAUUSD from here.\n\nCurrent market read:\nBias: {1}\nRegime: {2}\nExpected high today: {3}\nExpected low today: {4}\nKey upside level: {5}\nKey downside level: {6}\nCurrent bid/ask: {7} / {8}\n\nMy read:\n{9}").format(get_time_greeting(), analysis.get("bias", "sideways").upper(), snapshot.get("regime", "unknown"), analysis.get("expected_high", "N/A"), analysis.get("expected_low", "N/A"), analysis.get("key_level_up", "N/A"), analysis.get("key_level_down", "N/A"), snapshot.get("current_bid"), snapshot.get("current_ask"), analysis.get("summary", "I’m watching structure and session flow before I get aggressive."))

def build_session_message(session_name, bundle):
    analysis = bundle["analysis"]; snapshot = bundle["snapshot"]
    return ("Gold Master here — {0} session is opening now.\n\nWhat I’m watching:\nBias: {1}\nRegime: {2}\nCurrent bid/ask: {3} / {4}\nExpected session focus: {5} to {6}\n\nMy take:\n{7}").format(session_name, analysis.get("bias", "sideways").upper(), snapshot.get("regime", "unknown"), snapshot.get("current_bid"), snapshot.get("current_ask"), analysis.get("expected_low", "N/A"), analysis.get("expected_high", "N/A"), analysis.get("summary", "The market is still shaping up, so I’m waiting for cleaner structure."))

def build_pulse_message(bundle):
    analysis = bundle["analysis"]; snapshot = bundle["snapshot"]
    return ("Quick check-in from Gold Master.\n\nGold is currently trading around {0} / {1} and the broader tone looks {2}.\nThe current regime reads as {3}.\n{4}").format(snapshot.get("current_bid"), snapshot.get("current_ask"), analysis.get("bias", "sideways"), snapshot.get("regime", "unknown"), analysis.get("summary", "I’m staying patient and waiting for the cleanest structure."))

def build_macro_note(brief):
    return ("Gold Master note:\n\n{0}\n\n{1}").format(brief.get("headline", "Fresh macro movement is on the radar."), brief.get("impact_note", "I’m watching price reaction before leaning too hard either way."))

def build_signal_lines(setup):
    verdict = setup["verdict"]
    return ["XAUUSD {0}".format(setup["direction"].upper()), "Setup type: {0}".format(setup["setup_type"]), "Regime: {0}".format(setup["snapshot"]["regime"]), "Entry: {0:.2f}".format(setup["entry"]), "Stop loss: {0:.2f}".format(setup["sl"]), "Take profit 1: {0:.2f}".format(setup["tp"]), "Take profit 2: {0:.2f}".format(setup["tp2"]), "", "Local score: {0}".format(setup.get("local_score")), "Claude score: {0}".format(verdict.get("score", 0)), "", "Note: {0}".format(verdict.get("reason", setup.get("notes", "Gold Master likes the structure here.")))]

def build_execution_lines(setup, lot, result):
    return ["XAUUSD {0}".format(setup["direction"].upper()), "Setup type: {0}".format(setup["setup_type"]), "Volume: {0}".format(lot), "Entry: {0:.2f}".format(setup["entry"]), "Stop loss: {0:.2f}".format(setup["sl"]), "Take profit: {0:.2f}".format(setup["tp"]), "", "Broker retcode: {0}".format(getattr(result, "retcode", "N/A"))]

def get_session_open_bahrain(session_name, current_bhr):
    session = SESSION_DEFS[session_name]
    local_now = current_bhr.astimezone(session["tz"])
    local_open = local_now.replace(hour=session["hour"], minute=session["minute"], second=0, microsecond=0)
    return local_open.astimezone(BHR_TZ)

def maybe_send_session_updates():
    if not ENABLE_SESSION_UPDATES:
        return
    current_bhr = now_bahrain(); state = load_state(); sent_marks = state.get("last_sent_session_keys", {})
    for session_name in SESSION_DEFS:
        open_bhr = get_session_open_bahrain(session_name, current_bhr)
        session_key = "{0}:{1}".format(session_name, open_bhr.strftime("%Y-%m-%d %H:%M"))
        in_window = open_bhr <= current_bhr < open_bhr + timedelta(minutes=SESSION_WINDOW_MINUTES)
        already_sent = sent_marks.get(session_key, False)
        if in_window and not already_sent:
            bundle = build_commentary_bundle(context="{0}_session_open".format(session_name.lower()), use_web=True)
            send_human_update(build_session_message(session_name, bundle))
            sent_marks[session_key] = True; state["last_sent_session_keys"] = sent_marks; save_state(state)

def maybe_send_pulse_update():
    global LAST_PULSE_AT
    if not ENABLE_PULSE_UPDATES:
        return
    current_bhr = now_bahrain()
    if LAST_PULSE_AT and current_bhr - LAST_PULSE_AT < timedelta(minutes=PULSE_UPDATE_MINUTES):
        return
    bundle = build_commentary_bundle(context="pulse_update", use_web=False)
    send_human_update(build_pulse_message(bundle))
    LAST_PULSE_AT = current_bhr

def maybe_send_macro_note():
    global LAST_MACRO_AT
    if not ENABLE_MACRO_UPDATES:
        return
    current_bhr = now_bahrain()
    if LAST_MACRO_AT and current_bhr - LAST_MACRO_AT < timedelta(minutes=NEWS_STYLE_UPDATE_MINUTES):
        return
    state = load_state(); snapshot = get_market_snapshot(SYMBOL)
    brief = generate_macro_brief({"symbol": SYMBOL, "market_snapshot": snapshot, "persistent_state": state, "context": "macro_update"}, use_web=True)
    if brief.get("has_update", False):
        headline = brief.get("headline", "")
        if headline and headline != state.get("last_macro_headline", ""):
            send_human_update(build_macro_note(brief))
            state["last_macro_headline"] = headline; save_state(state)
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
    LAST_SIGNAL_AT = now_bahrain(); LAST_SIGNAL_SIDE = direction
    state = load_state()
    state["last_signal"] = {"timestamp": LAST_SIGNAL_AT.isoformat(), "direction": direction, "setup_type": setup["setup_type"], "entry": setup["entry"], "sl": setup["sl"], "tp": setup["tp"], "tp2": setup["tp2"]}
    save_state(state)

def startup_message():
    if not ENABLE_STARTUP_UPDATE:
        return
    bundle = build_commentary_bundle(context="startup", use_web=True)
    send_human_update(build_welcome_message(bundle))

def scan_for_setup():
    if not spread_ok(SYMBOL, MAX_SPREAD_POINTS):
        return None
    snapshot, candidates = generate_setup_candidates(SYMBOL)
    if not candidates:
        return None
    if not can_review_with_claude():
        return None
    state = load_state(); best = None
    for candidate in candidates[:MAX_CANDIDATES_PER_SCAN]:
        if int(candidate.get("local_score", 0)) < LOCAL_REVIEW_THRESHOLD:
            continue
        payload = {"symbol": SYMBOL, "setup_type": candidate["setup_type"], "direction_candidate": candidate["direction"], "market_snapshot": snapshot, "candidate": candidate, "persistent_state": {"last_analysis": state.get("last_analysis", {}), "watched_levels": state.get("watched_levels", {}), "last_signal": state.get("last_signal", {}), "session": current_session_name()}}
        verdict = review_trade_candidate(payload)
        candidate["verdict"] = verdict; candidate["snapshot"] = snapshot
        if not bool(verdict.get("trade", False)):
            continue
        if int(verdict.get("score", 0)) < MIN_SIGNAL_SCORE:
            continue
        if best is None or int(verdict.get("score", 0)) > int(best["verdict"].get("score", 0)):
            best = candidate
    if best and int(best["verdict"].get("score", 0)) >= SIGNAL_MACRO_VETO_THRESHOLD:
        state = load_state()
        macro = generate_macro_brief({"symbol": SYMBOL, "candidate": {"setup_type": best["setup_type"], "direction": best["direction"], "entry": best["entry"], "sl": best["sl"], "tp": best["tp"]}, "market_snapshot": snapshot, "persistent_state": state, "context": "signal_macro_veto"}, use_web=True)
        best["macro_brief"] = macro
        text = (macro.get("impact_note") or "").lower()
        if best["direction"] == "buy" and ("careful with longs" in text or "heavy for gold" in text):
            return None
        if best["direction"] == "sell" and ("supportive for gold" in text or "dips may attract buying" in text):
            return None
    return best

def maybe_execute_trade(setup):
    verdict = setup["verdict"]; direction = setup["direction"]; score = int(verdict.get("score", 0)); sl_valid = verdict.get("sl_valid", True); tp_valid = verdict.get("tp_valid", True)
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

def run_forever():
    connect(); print("Gold Master hybrid engine connected to MT5.")
    try:
        startup_message()
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
