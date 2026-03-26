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
        "last_reviewed_m5_bar": "",
        "candidate_rejections": {},
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


def remember_rejection(state, candidate, reason):
    state["candidate_rejections"][candidate_fingerprint(candidate)] = {
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat(),
    }


def is_rejection_cooled_down(state, candidate):
    fp = candidate_fingerprint(candidate)
    data = state.get("candidate_rejections", {}).get(fp)
    if not data:
        return False
    try:
        ts = datetime.fromisoformat(data["timestamp"])
    except Exception:
        return False
    return datetime.utcnow() - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES)


def prune_rejections(state):
    pruned = {}
    for fp, data in state.get("candidate_rejections", {}).items():
        try:
            ts = datetime.fromisoformat(data["timestamp"])
            if datetime.utcnow() - ts < timedelta(minutes=REJECTION_COOLDOWN_MINUTES):
                pruned[fp] = data
        except Exception:
            continue
    state["candidate_rejections"] = pruned
    return state
