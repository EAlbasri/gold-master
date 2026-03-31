import json
import os
from datetime import datetime, timedelta

from config import REJECTION_COOLDOWN_MINUTES, STATE_FILE_PATH


def _default_state():
    return {
        "last_analysis": {},
        "watched_levels": {},
        "last_macro_headline": "",
        "last_signal": {},
        "session_marks": {},
        "last_m5_bar_time": "",
        "rejected_candidates": {},
        "last_market_closed_note": "",
        "last_market_open_note": "",
        "last_reviewed_fingerprint": "",
    }


def load_state():
    if not os.path.exists(STATE_FILE_PATH):
        return _default_state()
    try:
        with open(STATE_FILE_PATH, "r") as f:
            data = json.load(f)
        base = _default_state()
        base.update(data)
        return base
    except Exception:
        return _default_state()


def save_state(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def candidate_fingerprint(candidate):
    return "{0}:{1}:{2}:{3}".format(
        candidate.get("setup_type", ""),
        candidate.get("direction", ""),
        round(float(candidate.get("trigger_level", 0)), 1),
        round(float(candidate.get("invalidation_level", 0)), 1),
    )


def is_candidate_on_cooldown(state, candidate, now_dt):
    fp = candidate_fingerprint(candidate)
    item = state.get("rejected_candidates", {}).get(fp)
    if not item:
        return False
    try:
        ts = datetime.fromisoformat(item["timestamp"])
    except Exception:
        return False
    return now_dt - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES)


def mark_candidate_rejected(state, candidate, now_dt, reason="rejected"):
    fp = candidate_fingerprint(candidate)
    if "rejected_candidates" not in state:
        state["rejected_candidates"] = {}
    state["rejected_candidates"][fp] = {
        "timestamp": now_dt.isoformat(),
        "reason": reason,
    }


def prune_rejections(state, now_dt):
    kept = {}
    for fp, item in state.get("rejected_candidates", {}).items():
        try:
            ts = datetime.fromisoformat(item.get("timestamp", ""))
        except Exception:
            continue
        if now_dt - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES):
            kept[fp] = item
    state["rejected_candidates"] = kept
    return state
