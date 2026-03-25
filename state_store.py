import json
import os
from config import STATE_FILE_PATH

DEFAULT_STATE = {
    "last_analysis": {},
    "watched_levels": {},
    "last_macro_headline": "",
    "last_signal": {},
    "last_sent_session_keys": {},
    "last_reviewed_m5_time": "",
    "last_commentary": {},
}

def load_state():
    if not os.path.exists(STATE_FILE_PATH):
        return DEFAULT_STATE.copy()
    try:
        with open(STATE_FILE_PATH, "r") as f:
            data = json.load(f)
        merged = DEFAULT_STATE.copy()
        merged.update(data)
        return merged
    except Exception:
        return DEFAULT_STATE.copy()

def save_state(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)
