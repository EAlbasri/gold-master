import json
import os

from config import STATE_FILE_PATH


def default_state():
    return {
        "last_analysis": {},
        "watched_levels": {},
        "last_macro_headline": "",
        "last_signal": {},
        "daily_loss_lock_date": "",
    }


def load_state():
    if not os.path.exists(STATE_FILE_PATH):
        return default_state()
    try:
        with open(STATE_FILE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return default_state()


def save_state(state):
    with open(STATE_FILE_PATH, "w") as f:
        json.dump(state, f, indent=2)
