SYMBOL_PROFILES = {
    "XAUUSD": {
        "display": "Gold",
        "max_spread_points": 80,
        "session_weight": {"Asia": 0.9, "London": 1.2, "New York": 1.25, "Off-session": 0.35},
        "setup_weight": {
            "breakout_retest": 1.30,
            "breakout_continuation": 1.20,
            "failed_bounce_continuation": 1.15,
            "structure_break_retest": 1.15,
            "liquidity_reversal": 1.00,
            "trend_pullback": 0.95,
            "impulse_continuation": 1.10,
        },
    },
    "EURUSD": {
        "display": "EUR/USD",
        "max_spread_points": 35,
        "session_weight": {"Asia": 0.7, "London": 1.30, "New York": 1.15, "Off-session": 0.20},
        "setup_weight": {
            "breakout_retest": 1.25,
            "breakout_continuation": 1.05,
            "failed_bounce_continuation": 0.95,
            "structure_break_retest": 1.20,
            "liquidity_reversal": 0.95,
            "trend_pullback": 1.10,
            "impulse_continuation": 0.95,
        },
    },
    "USDJPY": {
        "display": "USD/JPY",
        "max_spread_points": 40,
        "session_weight": {"Asia": 1.20, "London": 0.95, "New York": 1.05, "Off-session": 0.25},
        "setup_weight": {
            "breakout_retest": 1.15,
            "breakout_continuation": 1.15,
            "failed_bounce_continuation": 1.20,
            "structure_break_retest": 1.05,
            "liquidity_reversal": 0.90,
            "trend_pullback": 1.05,
            "impulse_continuation": 1.10,
        },
    },
}
