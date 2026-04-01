import json
import os
from datetime import datetime, timedelta

from config import REJECTION_COOLDOWN_MINUTES, STATE_FILE_PATH, SYMBOLS


def _default_state():
    return {
        "last_analysis": {},
        "watched_levels": {},
        "last_macro_headline": "",
        "last_signal": {},
        "last_market_closed_note": "",
        "last_market_open_note": "",
        "symbols": {s: {"last_m5_bar_time": "", "rejected_candidates": {}} for s in SYMBOLS},
    }


def load_state():
    if not os.path.exists(STATE_FILE_PATH):
        return _default_state()
    try:
        with open(STATE_FILE_PATH, "r") as f:
            data = json.load(f)
        state = _default_state()
        state.update(data)
        for s in SYMBOLS:
            state.setdefault("symbols", {}).setdefault(s, {"last_m5_bar_time": "", "rejected_candidates": {}})
        return state
    except Exception:
        return _default_state()


def save_state(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def symbol_state(state, symbol):
    state.setdefault("symbols", {})
    state["symbols"].setdefault(symbol, {"last_m5_bar_time": "", "rejected_candidates": {}})
    return state["symbols"][symbol]


def candidate_fingerprint(candidate):
    return "{0}:{1}:{2}:{3}".format(
        candidate.get("setup_type", ""),
        candidate.get("direction", ""),
        round(float(candidate.get("trigger_level", 0)), 1),
        round(float(candidate.get("invalidation_level", 0)), 1),
    )


def is_candidate_on_cooldown(state, symbol, candidate, now_dt):
    fp = candidate_fingerprint(candidate)
    item = symbol_state(state, symbol).get("rejected_candidates", {}).get(fp)
    if not item:
        return False
    try:
        ts = datetime.fromisoformat(item["timestamp"])
    except Exception:
        return False
    return now_dt - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES)


def mark_candidate_rejected(state, symbol, candidate, now_dt, reason="rejected"):
    fp = candidate_fingerprint(candidate)
    symbol_state(state, symbol).setdefault("rejected_candidates", {})[fp] = {
        "timestamp": now_dt.isoformat(),
        "reason": reason,
    }


def prune_rejections(state, now_dt):
    for symbol in SYMBOLS:
        sstate = symbol_state(state, symbol)
        kept = {}
        for fp, item in sstate.get("rejected_candidates", {}).items():
            try:
                ts = datetime.fromisoformat(item.get("timestamp", ""))
            except Exception:
                continue
            if now_dt - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES):
                kept[fp] = item
        sstate["rejected_candidates"] = kept
    return state
