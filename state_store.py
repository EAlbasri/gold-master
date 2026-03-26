import json
import os
from datetime import datetime, timedelta
from config import REJECTION_COOLDOWN_MINUTES, STATE_FILE_PATH

def default_state():
    return {
        "last_analysis": {},
        "watched_levels": {},
        "last_macro_headline": "",
        "last_signal": {},
        "rejection_cache": {},
        "last_reviewed_m5_bar": "",
    }

def load_state():
    if not os.path.exists(STATE_FILE_PATH):
        return default_state()
    try:
        with open(STATE_FILE_PATH, "r") as f:
            state = json.load(f)
    except Exception:
        state = default_state()
    for key, value in default_state().items():
        state.setdefault(key, value)
    return state

def save_state(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def candidate_fingerprint(candidate):
    return "{0}:{1}:{2}:{3}".format(
        candidate.get("setup_type"),
        candidate.get("direction"),
        round(float(candidate.get("trigger_level", 0)), 1),
        round(float(candidate.get("invalidation_level", 0)), 1),
    )

def is_rejection_cooled_down(state, candidate, now_iso):
    cache = state.get("rejection_cache", {})
    fp = candidate_fingerprint(candidate)
    ts = cache.get(fp)
    if not ts:
        return False
    try:
        old = datetime.fromisoformat(ts)
        now = datetime.fromisoformat(now_iso)
        return now - old < timedelta(minutes=REJECTION_COOLDOWN_MINUTES)
    except Exception:
        return False

def mark_rejection(state, candidate, now_iso):
    state.setdefault("rejection_cache", {})
    state["rejection_cache"][candidate_fingerprint(candidate)] = now_iso
    return state

def prune_rejections(state, now_iso):
    cache = state.get("rejection_cache", {})
    fresh = {}
    try:
        now = datetime.fromisoformat(now_iso)
    except Exception:
        return state
    for fp, ts in cache.items():
        try:
            old = datetime.fromisoformat(ts)
            if now - old < timedelta(minutes=REJECTION_COOLDOWN_MINUTES):
                fresh[fp] = ts
        except Exception:
            continue
    state["rejection_cache"] = fresh
    return state
