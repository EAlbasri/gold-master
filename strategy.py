import MetaTrader5 as mt5
import pandas as pd

from config import (
    BUY_ONLY,
    ENABLE_BREAKOUT_CONTINUATION,
    ENABLE_BREAKOUT_RETEST,
    ENABLE_FAILED_BOUNCE_CONTINUATION,
    ENABLE_IMPULSE_CONTINUATION,
    ENABLE_LIQUIDITY_REVERSAL,
    ENABLE_STRUCTURE_BREAK_RETEST,
    ENABLE_TREND_PULLBACK,
    MIN_RR,
    TP_RR,
)
from mt5_client import get_rates, get_tick


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def atr(df, period=14):
    data = df.copy()
    data["prev_close"] = data["close"].shift(1)
    data["tr"] = data.apply(
        lambda row: max(
            row["high"] - row["low"],
            abs(row["high"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0,
            abs(row["low"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0,
        ),
        axis=1,
    )
    value = data["tr"].rolling(period).mean().iloc[-1]
    return round(float(value), 2) if pd.notna(value) else 0.0


def candle_body(df, idx=-1):
    return abs(float(df["close"].iloc[idx]) - float(df["open"].iloc[idx]))


def avg_body(df, n=10):
    sample = df.iloc[-n:]
    return float((sample["close"] - sample["open"]).abs().mean())


def get_intraday_vwap(df):
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["tick_volume"].replace(0, 1)
    return (typical_price * volume).cumsum() / volume.cumsum()


def spread_ok(symbol, max_spread_points):
    tick = get_tick(symbol)
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    spread_points = int((tick.ask - tick.bid) / info.point)
    return spread_points <= max_spread_points


def market_bias(symbol):
    d1 = get_rates(symbol, mt5.TIMEFRAME_D1, 250)
    h4 = get_rates(symbol, mt5.TIMEFRAME_H4, 250)

    d1["ema20"] = ema(d1["close"], 20)
    d1["ema50"] = ema(d1["close"], 50)
    d1["ema200"] = ema(d1["close"], 200)
    h4["ema20"] = ema(h4["close"], 20)
    h4["ema50"] = ema(h4["close"], 50)

    bullish = (
        d1["ema20"].iloc[-1] > d1["ema50"].iloc[-1] > d1["ema200"].iloc[-1]
        and h4["close"].iloc[-1] > h4["ema20"].iloc[-1] > h4["ema50"].iloc[-1]
    )
    bearish = (
        d1["ema20"].iloc[-1] < d1["ema50"].iloc[-1] < d1["ema200"].iloc[-1]
        and h4["close"].iloc[-1] < h4["ema20"].iloc[-1] < h4["ema50"].iloc[-1]
    )

    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "sideways"


def classify_regime(symbol):
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 80)
    bias = market_bias(symbol)

    recent_high = float(m15["high"].iloc[-21:-1].max())
    recent_low = float(m15["low"].iloc[-21:-1].min())
    last_close = float(m15["close"].iloc[-1])
    last_body = candle_body(m15, -1)
    mean_body = avg_body(m15, 12)
    compression_pct = ((recent_high - recent_low) / max(last_close, 1.0)) * 100.0

    if bias == "bullish" and last_close > recent_high and last_body > mean_body * 1.25:
        return "bullish_expansion"
    if bias == "bearish" and last_close < recent_low and last_body > mean_body * 1.25:
        return "bearish_expansion"
    if compression_pct < 0.9:
        return "sideways_compression"
    if bias == "bullish":
        return "bullish_trend"
    if bias == "bearish":
        return "bearish_trend"
    return "sideways"


def vwap_reclaim(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 80).copy()
    vwap = get_intraday_vwap(m5)
    last_close = float(m5["close"].iloc[-1])
    last_vwap = float(vwap.iloc[-1])
    if direction == "buy":
        return last_close > last_vwap
    return last_close < last_vwap


def reversal_confirmed(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 10)

    prev_open = float(m5["open"].iloc[-2])
    prev_close = float(m5["close"].iloc[-2])
    curr_open = float(m5["open"].iloc[-1])
    curr_close = float(m5["close"].iloc[-1])

    if direction == "buy":
        return prev_close < prev_open and curr_close > curr_open and curr_close > prev_open and curr_open < prev_close
    return prev_close > prev_open and curr_close < curr_open and curr_close < prev_open and curr_open > prev_close


def find_liquidity_sweep(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 40)
    context = m5.iloc[-14:-2]
    if len(context) < 5:
        return {"swept": False}

    if direction == "buy":
        prior_low = float(context["low"].min())
        last_low = float(m5["low"].iloc[-1])
        last_close = float(m5["close"].iloc[-1])
        swept = last_low < prior_low and last_close > prior_low
        return {
            "swept": swept,
            "sweep_level": round(prior_low, 2),
            "last_extreme": round(last_low, 2),
            "close_after_sweep": round(last_close, 2),
        }

    prior_high = float(context["high"].max())
    last_high = float(m5["high"].iloc[-1])
    last_close = float(m5["close"].iloc[-1])
    swept = last_high > prior_high and last_close < prior_high
    return {
        "swept": swept,
        "sweep_level": round(prior_high, 2),
        "last_extreme": round(last_high, 2),
        "close_after_sweep": round(last_close, 2),
    }


def find_latest_fvg(symbol, direction):
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 50)
    if len(m15) < 5:
        return {"found": False}

    for i in range(len(m15) - 1, 2, -1):
        c1 = m15.iloc[i - 2]
        c2 = m15.iloc[i - 1]
        c3 = m15.iloc[i]

        if direction == "buy":
            if float(c1["high"]) < float(c3["low"]):
                gap_low = float(c1["high"])
                gap_high = float(c3["low"])
                return {
                    "found": True,
                    "type": "bullish",
                    "gap_low": round(gap_low, 2),
                    "gap_high": round(gap_high, 2),
                    "mid": round((gap_low + gap_high) / 2.0, 2),
                    "reference_time": str(c2["time"]),
                }
        else:
            if float(c1["low"]) > float(c3["high"]):
                gap_low = float(c3["high"])
                gap_high = float(c1["low"])
                return {
                    "found": True,
                    "type": "bearish",
                    "gap_low": round(gap_low, 2),
                    "gap_high": round(gap_high, 2),
                    "mid": round((gap_low + gap_high) / 2.0, 2),
                    "reference_time": str(c2["time"]),
                }
    return {"found": False}


def _get_recent_levels(m15):
    return {
        "range_high_20": float(m15["high"].iloc[-21:-1].max()),
        "range_low_20": float(m15["low"].iloc[-21:-1].min()),
        "range_high_10": float(m15["high"].iloc[-11:-1].max()),
        "range_low_10": float(m15["low"].iloc[-11:-1].min()),
    }


def _make_candidate(setup_type, direction, trigger_level, invalidation_level, target_level, notes, regime):
    return {
        "setup_type": setup_type,
        "direction": direction,
        "trigger_level": round(float(trigger_level), 2),
        "invalidation_level": round(float(invalidation_level), 2),
        "target_level": round(float(target_level), 2),
        "notes": notes,
        "regime": regime,
    }


def detect_breakout_continuation(symbol, direction, regime):
    if not ENABLE_BREAKOUT_CONTINUATION:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 70)
    levels = _get_recent_levels(m15)
    last = m15.iloc[-1]
    range_high = levels["range_high_20"]
    range_low = levels["range_low_20"]
    width = max(range_high - range_low, 8.0)
    body = candle_body(m15, -1)
    mean_body = avg_body(m15, 12)

    if direction == "buy":
        if float(last["close"]) > range_high and body > mean_body * 1.25 and float(last["close"]) > float(last["open"]):
            return _make_candidate(
                "breakout_continuation",
                "buy",
                float(last["close"]),
                min(float(last["low"]), range_high),
                float(last["close"]) + width,
                "Strong M15 upside displacement through recent range high.",
                regime,
            )
    else:
        if float(last["close"]) < range_low and body > mean_body * 1.25 and float(last["close"]) < float(last["open"]):
            return _make_candidate(
                "breakout_continuation",
                "sell",
                float(last["close"]),
                max(float(last["high"]), range_low),
                float(last["close"]) - width,
                "Strong M15 downside displacement through recent range low.",
                regime,
            )
    return None


def detect_breakout_retest(symbol, direction, regime):
    if not ENABLE_BREAKOUT_RETEST:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 70)
    levels = _get_recent_levels(m15)
    last = m15.iloc[-1]
    prev = m15.iloc[-2]
    prev2 = m15.iloc[-3]
    range_high = levels["range_high_20"]
    range_low = levels["range_low_20"]
    width = max(range_high - range_low, 8.0)
    tolerance = max(width * 0.12, 4.0)

    if direction == "buy":
        breakout = float(prev2["close"]) > range_high or float(prev["close"]) > range_high
        retest = float(last["low"]) <= range_high + tolerance and float(last["close"]) > range_high
        if breakout and retest:
            return _make_candidate(
                "breakout_retest",
                "buy",
                float(last["close"]),
                min(float(last["low"]), range_high),
                float(last["close"]) + width,
                "M15 breakout held and retested successfully from above.",
                regime,
            )
    else:
        breakout = float(prev2["close"]) < range_low or float(prev["close"]) < range_low
        retest = float(last["high"]) >= range_low - tolerance and float(last["close"]) < range_low
        if breakout and retest:
            return _make_candidate(
                "breakout_retest",
                "sell",
                float(last["close"]),
                max(float(last["high"]), range_low),
                float(last["close"]) - width,
                "M15 breakdown held and retested successfully from below.",
                regime,
            )
    return None


def detect_structure_break_retest(symbol, direction, regime):
    if not ENABLE_STRUCTURE_BREAK_RETEST:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 90)
    levels = _get_recent_levels(m15)
    width = max(levels["range_high_20"] - levels["range_low_20"], 8.0)
    swings = m15.iloc[-12:-2]
    last = m15.iloc[-1]
    prev = m15.iloc[-2]

    if direction == "buy":
        structure_level = float(swings["high"].max())
        broke = float(prev["close"]) > structure_level or float(last["close"]) > structure_level
        retest = float(last["low"]) <= structure_level + max(width * 0.10, 4.0) and float(last["close"]) > structure_level
        if broke and retest:
            return _make_candidate(
                "structure_break_retest",
                "buy",
                float(last["close"]),
                min(float(last["low"]), structure_level),
                float(last["close"]) + width,
                "Bullish BOS retest held; SMC-style continuation candidate.",
                regime,
            )
    else:
        structure_level = float(swings["low"].min())
        broke = float(prev["close"]) < structure_level or float(last["close"]) < structure_level
        retest = float(last["high"]) >= structure_level - max(width * 0.10, 4.0) and float(last["close"]) < structure_level
        if broke and retest:
            return _make_candidate(
                "structure_break_retest",
                "sell",
                float(last["close"]),
                max(float(last["high"]), structure_level),
                float(last["close"]) - width,
                "Bearish BOS retest held; SMC-style continuation candidate.",
                regime,
            )
    return None


def detect_failed_bounce_continuation(symbol, direction, regime):
    if not ENABLE_FAILED_BOUNCE_CONTINUATION:
        return None

    if regime not in ["bullish_trend", "bullish_expansion", "bearish_trend", "bearish_expansion"]:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 80).copy()
    m15["ema20"] = ema(m15["close"], 20)
    recent = m15.iloc[-6:]
    last = m15.iloc[-1]
    prev = m15.iloc[-2]

    if direction == "sell":
        bounced = float(recent["high"].max()) >= float(m15["ema20"].iloc[-1]) - 2.0
        reject = float(last["close"]) < float(prev["low"])
        if bounced and reject:
            target = float(m15["low"].iloc[-25:-1].min())
            return _make_candidate(
                "failed_bounce_continuation",
                "sell",
                float(last["close"]),
                float(recent["high"].max()),
                min(target, float(last["close"]) - 12.0),
                "Bearish bounce failed into value, continuation lower confirmed.",
                regime,
            )
    else:
        dipped = float(recent["low"].min()) <= float(m15["ema20"].iloc[-1]) + 2.0
        reject = float(last["close"]) > float(prev["high"])
        if dipped and reject:
            target = float(m15["high"].iloc[-25:-1].max())
            return _make_candidate(
                "failed_bounce_continuation",
                "buy",
                float(last["close"]),
                float(recent["low"].min()),
                max(target, float(last["close"]) + 12.0),
                "Bullish dip failed lower into value, continuation higher confirmed.",
                regime,
            )
    return None


def detect_trend_pullback(symbol, direction, regime):
    if not ENABLE_TREND_PULLBACK:
        return None
    if regime in ["sideways", "sideways_compression"]:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 80).copy()
    m15["ema20"] = ema(m15["close"], 20)
    m15["ema50"] = ema(m15["close"], 50)
    fvg = find_latest_fvg(symbol, direction)
    recent = m15.iloc[-6:]
    last = m15.iloc[-1]
    prev = m15.iloc[-2]

    if direction == "buy":
        trend_ok = float(m15["ema20"].iloc[-1]) > float(m15["ema50"].iloc[-1])
        touched = float(recent["low"].min()) <= float(m15["ema20"].iloc[-1]) + 3.0
        confirm = float(last["close"]) > float(prev["high"])
        if trend_ok and touched and confirm:
            invalidation = float(recent["low"].min())
            if fvg.get("found"):
                invalidation = min(invalidation, float(fvg.get("gap_low", invalidation)))
            target = float(m15["high"].iloc[-25:-1].max())
            return _make_candidate(
                "trend_pullback",
                "buy",
                float(last["close"]),
                invalidation,
                max(target, float(last["close"]) + 10.0),
                "Bull trend pullback into M15 value zone with continuation confirmation.",
                regime,
            )
    else:
        trend_ok = float(m15["ema20"].iloc[-1]) < float(m15["ema50"].iloc[-1])
        touched = float(recent["high"].max()) >= float(m15["ema20"].iloc[-1]) - 3.0
        confirm = float(last["close"]) < float(prev["low"])
        if trend_ok and touched and confirm:
            invalidation = float(recent["high"].max())
            if fvg.get("found"):
                invalidation = max(invalidation, float(fvg.get("gap_high", invalidation)))
            target = float(m15["low"].iloc[-25:-1].min())
            return _make_candidate(
                "trend_pullback",
                "sell",
                float(last["close"]),
                invalidation,
                min(target, float(last["close"]) - 10.0),
                "Bear trend pullback into M15 value zone with continuation confirmation.",
                regime,
            )
    return None


def detect_liquidity_reversal(symbol, direction, regime):
    if not ENABLE_LIQUIDITY_REVERSAL:
        return None

    sweep = find_liquidity_sweep(symbol, direction)
    fvg = find_latest_fvg(symbol, direction)
    vwap_ok = vwap_reclaim(symbol, direction)
    reversal_ok = reversal_confirmed(symbol, direction)

    if not (sweep.get("swept") and vwap_ok and reversal_ok):
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 40)
    if direction == "buy":
        target = float(m15["high"].iloc[-20:-1].max())
        invalidation = min(float(sweep["last_extreme"]), float(fvg.get("gap_low", sweep["last_extreme"])))
    else:
        target = float(m15["low"].iloc[-20:-1].min())
        invalidation = max(float(sweep["last_extreme"]), float(fvg.get("gap_high", sweep["last_extreme"])))

    return _make_candidate(
        "liquidity_reversal",
        direction,
        float(sweep["close_after_sweep"]),
        invalidation,
        target,
        "Liquidity sweep reclaimed with VWAP and reversal confirmation.",
        regime,
    )


def detect_impulse_continuation(symbol, direction, regime):
    if not ENABLE_IMPULSE_CONTINUATION:
        return None
    if regime in ["sideways", "sideways_compression"]:
        return None

    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 60).copy()
    m15["ema20"] = ema(m15["close"], 20)
    mean_body = avg_body(m15, 12)
    impulse_idx = None

    for idx in range(-6, -2):
        body = abs(float(m15["close"].iloc[idx]) - float(m15["open"].iloc[idx]))
        if direction == "buy" and float(m15["close"].iloc[idx]) > float(m15["open"].iloc[idx]) and body > mean_body * 1.8:
            impulse_idx = idx
            break
        if direction == "sell" and float(m15["close"].iloc[idx]) < float(m15["open"].iloc[idx]) and body > mean_body * 1.8:
            impulse_idx = idx
            break

    if impulse_idx is None:
        return None

    impulse_open = float(m15["open"].iloc[impulse_idx])
    impulse_close = float(m15["close"].iloc[impulse_idx])
    impulse_high = float(m15["high"].iloc[impulse_idx])
    impulse_low = float(m15["low"].iloc[impulse_idx])

    recent = m15.iloc[impulse_idx + 1:]
    last = m15.iloc[-1]
    if len(recent) == 0:
        return None

    if direction == "buy":
        retrace_low = float(recent["low"].min())
        max_retrace = impulse_close - ((impulse_close - impulse_open) * 0.55)
        shallow = retrace_low >= max_retrace
        confirm = float(last["close"]) > float(m15["ema20"].iloc[-1])
        if shallow and confirm:
            return _make_candidate(
                "impulse_continuation",
                "buy",
                float(last["close"]),
                retrace_low,
                impulse_high + max(impulse_high - impulse_low, 10.0),
                "Strong upside impulse followed by shallow retracement and hold.",
                regime,
            )
    else:
        retrace_high = float(recent["high"].max())
        max_retrace = impulse_close + ((impulse_open - impulse_close) * 0.55)
        shallow = retrace_high <= max_retrace
        confirm = float(last["close"]) < float(m15["ema20"].iloc[-1])
        if shallow and confirm:
            return _make_candidate(
                "impulse_continuation",
                "sell",
                float(last["close"]),
                retrace_high,
                impulse_low - max(impulse_high - impulse_low, 10.0),
                "Strong downside impulse followed by shallow retracement and hold.",
                regime,
            )
    return None


def build_trade_plan(candidate, snapshot):
    tick = get_tick(snapshot["symbol"])
    direction = candidate["direction"]
    entry = float(tick.ask if direction == "buy" else tick.bid)
    daily_atr = float(snapshot["daily_atr_14"])
    h4_atr = float(snapshot["h4_atr_14"])
    buffer_size = max(daily_atr * 0.08, h4_atr * 0.12, 0.5)

    if direction == "buy":
        sl = float(candidate["invalidation_level"]) - buffer_size
        risk = max(entry - sl, 0.5)
        tp_anchor = max(float(candidate["target_level"]), entry + risk * TP_RR)
        tp2 = max(tp_anchor + risk * 0.8, entry + risk * (TP_RR + 0.8))
    else:
        sl = float(candidate["invalidation_level"]) + buffer_size
        risk = max(sl - entry, 0.5)
        tp_anchor = min(float(candidate["target_level"]), entry - risk * TP_RR)
        tp2 = min(tp_anchor - risk * 0.8, entry - risk * (TP_RR + 0.8))

    candidate["entry"] = round(entry, 2)
    candidate["sl"] = round(sl, 2)
    candidate["tp"] = round(tp_anchor, 2)
    candidate["tp2"] = round(tp2, 2)
    return candidate


def score_candidate(candidate, snapshot, session_name):
    score = 50
    setup_type = candidate.get("setup_type", "")
    regime = snapshot.get("regime", "sideways")
    bias = snapshot.get("bias", "sideways")
    direction = candidate.get("direction", "")
    entry = float(candidate.get("entry", 0))
    sl = float(candidate.get("sl", 0))
    tp = float(candidate.get("tp", 0))
    vwap = float(snapshot.get("m5_vwap", 0))
    recent_range = float(snapshot.get("recent_structure", {}).get("recent_range", 0))
    trigger = float(candidate.get("trigger_level", entry))

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0

    if rr >= 2.0:
        score += 12
    elif rr >= MIN_RR:
        score += 8
    else:
        score -= 18

    if regime == "bullish_expansion" and direction == "buy":
        score += 10
    if regime == "bearish_expansion" and direction == "sell":
        score += 10
    if regime == "bullish_trend" and direction == "buy":
        score += 8
    if regime == "bearish_trend" and direction == "sell":
        score += 8
    if regime in ["sideways", "sideways_compression"] and setup_type in ["trend_pullback", "impulse_continuation", "failed_bounce_continuation"]:
        score -= 20

    if session_name == "New York":
        score += 5
    elif session_name == "London":
        score += 4
    elif session_name == "Asia" and setup_type in ["breakout_continuation", "failed_bounce_continuation", "impulse_continuation"]:
        score -= 8
    elif session_name == "Off-session":
        score -= 15

    if setup_type == "breakout_retest":
        score += 9
    elif setup_type == "structure_break_retest":
        score += 9
    elif setup_type == "breakout_continuation":
        score += 7
    elif setup_type == "failed_bounce_continuation":
        score += 7
    elif setup_type == "liquidity_reversal":
        score += 5
    elif setup_type == "trend_pullback":
        score += 4
    elif setup_type == "impulse_continuation":
        score += 2

    vwap_distance = abs(entry - vwap)
    if regime in ["bullish_expansion", "bearish_expansion"]:
        if vwap_distance <= max(snapshot.get("daily_atr_14", 0) * 0.35, 24):
            score += 4
        else:
            score -= 6
    else:
        if vwap_distance <= max(snapshot.get("daily_atr_14", 0) * 0.22, 16):
            score += 4
        else:
            score -= 8

    if setup_type in ["breakout_continuation", "breakout_retest", "structure_break_retest"]:
        if abs(entry - trigger) <= max(risk * 1.2, 18):
            score += 4
        else:
            score -= 10

    if recent_range < 16 and setup_type in ["breakout_continuation", "breakout_retest", "structure_break_retest"]:
        score -= 8

    if bias == "bullish" and direction == "buy":
        score += 4
    if bias == "bearish" and direction == "sell":
        score += 4

    return max(0, min(100, int(score)))


def get_market_snapshot(symbol):
    d1 = get_rates(symbol, mt5.TIMEFRAME_D1, 80)
    h4 = get_rates(symbol, mt5.TIMEFRAME_H4, 80)
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 120)
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 120)
    tick = get_tick(symbol)
    d1_atr = atr(d1, 14)
    h4_atr = atr(h4, 14)
    m5_vwap = get_intraday_vwap(m5)
    regime = classify_regime(symbol)
    bias = market_bias(symbol)
    recent_high = float(m15["high"].iloc[-20:].max())
    recent_low = float(m15["low"].iloc[-20:].min())
    recent_range = recent_high - recent_low

    return {
        "symbol": symbol,
        "current_bid": round(float(tick.bid), 2),
        "current_ask": round(float(tick.ask), 2),
        "bias": bias,
        "regime": regime,
        "today_open": round(float(d1["open"].iloc[-1]), 2),
        "today_high": round(float(d1["high"].iloc[-1]), 2),
        "today_low": round(float(d1["low"].iloc[-1]), 2),
        "m15_last_close": round(float(m15["close"].iloc[-1]), 2),
        "m15_last_high": round(float(m15["high"].iloc[-1]), 2),
        "m15_last_low": round(float(m15["low"].iloc[-1]), 2),
        "m5_last_close": round(float(m5["close"].iloc[-1]), 2),
        "m5_last_bar_time": str(m5["time"].iloc[-1]),
        "m5_vwap": round(float(m5_vwap.iloc[-1]), 2),
        "daily_atr_14": d1_atr,
        "h4_atr_14": h4_atr,
        "recent_structure": {
            "recent_high": round(recent_high, 2),
            "recent_low": round(recent_low, 2),
            "recent_range": round(recent_range, 2),
        },
    }


def generate_setup_candidates(symbol, session_name):
    snapshot = get_market_snapshot(symbol)
    regime = snapshot["regime"]
    bias = snapshot["bias"]

    directions = []
    if bias == "bullish":
        directions.append("buy")
        if regime in ["bearish_expansion"] and not BUY_ONLY:
            directions.append("sell")
    elif bias == "bearish" and not BUY_ONLY:
        directions.append("sell")
        if regime in ["bullish_expansion"]:
            directions.append("buy")
    elif bias == "sideways" and not BUY_ONLY:
        directions.extend(["buy", "sell"])
    elif bias == "sideways" and BUY_ONLY:
        directions.append("buy")

    # dedupe preserve order
    seen = set()
    final_directions = []
    for d in directions:
        if d not in seen:
            seen.add(d)
            final_directions.append(d)

    candidates = []
    detectors = [
        detect_breakout_retest,
        detect_structure_break_retest,
        detect_breakout_continuation,
        detect_failed_bounce_continuation,
        detect_liquidity_reversal,
        detect_trend_pullback,
        detect_impulse_continuation,
    ]

    for direction in final_directions:
        for detector in detectors:
            candidate = detector(symbol, direction, regime)
            if candidate:
                candidate = build_trade_plan(candidate, snapshot)
                candidate["local_score"] = score_candidate(candidate, snapshot, session_name)
                candidates.append(candidate)

    candidates.sort(key=lambda c: c.get("local_score", 0), reverse=True)
    return snapshot, candidates
