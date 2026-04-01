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
from symbol_profiles import SYMBOL_PROFILES


def get_profile(symbol):
    return SYMBOL_PROFILES.get(symbol, SYMBOL_PROFILES["XAUUSD"])


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
    return round(float(value), 5) if pd.notna(value) else 0.0


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
    compression_pct = ((recent_high - recent_low) / max(abs(last_close), 1e-6)) * 100.0

    if bias == "bullish" and last_close > recent_high and last_body > mean_body * 1.25:
        return "bullish_expansion"
    if bias == "bearish" and last_close < recent_low and last_body > mean_body * 1.25:
        return "bearish_expansion"
    if compression_pct < 0.8:
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
    return last_close > last_vwap if direction == "buy" else last_close < last_vwap


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
        return {"swept": swept, "sweep_level": round(prior_low, 5), "last_extreme": round(last_low, 5), "close_after_sweep": round(last_close, 5)}

    prior_high = float(context["high"].max())
    last_high = float(m5["high"].iloc[-1])
    last_close = float(m5["close"].iloc[-1])
    swept = last_high > prior_high and last_close < prior_high
    return {"swept": swept, "sweep_level": round(prior_high, 5), "last_extreme": round(last_high, 5), "close_after_sweep": round(last_close, 5)}


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
                return {"found": True, "type": "bullish", "gap_low": round(gap_low, 5), "gap_high": round(gap_high, 5), "mid": round((gap_low + gap_high) / 2.0, 5), "reference_time": str(c2["time"])}
        else:
            if float(c1["low"]) > float(c3["high"]):
                gap_low = float(c3["high"])
                gap_high = float(c1["low"])
                return {"found": True, "type": "bearish", "gap_low": round(gap_low, 5), "gap_high": round(gap_high, 5), "mid": round((gap_low + gap_high) / 2.0, 5), "reference_time": str(c2["time"])}
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
        "trigger_level": round(float(trigger_level), 5),
        "invalidation_level": round(float(invalidation_level), 5),
        "target_level": round(float(target_level), 5),
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
    width = max(range_high - range_low, max(abs(float(last["close"])) * 0.0012, 0.0008))
    body = candle_body(m15, -1)
    mean_body = avg_body(m15, 12)

    if direction == "buy":
        if float(last["close"]) > range_high and body > mean_body * 1.2 and float(last["close"]) > float(last["open"]):
            return _make_candidate("breakout_continuation", "buy", float(last["close"]), min(float(last["low"]), range_high), float(last["close"]) + width, "Strong M15 upside displacement through recent range high.", regime)
    else:
        if float(last["close"]) < range_low and body > mean_body * 1.2 and float(last["close"]) < float(last["open"]):
            return _make_candidate("breakout_continuation", "sell", float(last["close"]), max(float(last["high"]), range_low), float(last["close"]) - width, "Strong M15 downside displacement through recent range low.", regime)
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
    width = max(range_high - range_low, max(abs(float(last["close"])) * 0.0012, 0.0008))
    tolerance = max(width * 0.12, abs(float(last["close"])) * 0.0003)

    if direction == "buy":
        breakout = float(prev2["close"]) > range_high or float(prev["close"]) > range_high
        retest = float(last["low"]) <= range_high + tolerance and float(last["close"]) > range_high
        if breakout and retest:
            return _make_candidate("breakout_retest", "buy", float(last["close"]), min(float(last["low"]), range_high), float(last["close"]) + width, "Breakout held and retested from above.", regime)
    else:
        breakout = float(prev2["close"]) < range_low or float(prev["close"]) < range_low
        retest = float(last["high"]) >= range_low - tolerance and float(last["close"]) < range_low
        if breakout and retest:
            return _make_candidate("breakout_retest", "sell", float(last["close"]), max(float(last["high"]), range_low), float(last["close"]) - width, "Breakdown held and retested from below.", regime)
    return None


def detect_structure_break_retest(symbol, direction, regime):
    if not ENABLE_STRUCTURE_BREAK_RETEST:
        return None
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 80)
    recent_high = float(m5["high"].iloc[-18:-3].max())
    recent_low = float(m5["low"].iloc[-18:-3].min())
    prev = m5.iloc[-2]
    last = m5.iloc[-1]
    width = max(recent_high - recent_low, max(abs(float(last["close"])) * 0.0009, 0.0006))

    if direction == "buy":
        break_ok = float(prev["close"]) > recent_high
        retest_ok = float(last["low"]) <= recent_high and float(last["close"]) > recent_high
        if break_ok and retest_ok:
            return _make_candidate("structure_break_retest", "buy", float(last["close"]), min(float(last["low"]), recent_high), float(last["close"]) + width, "M5 structure break held on retest.", regime)
    else:
        break_ok = float(prev["close"]) < recent_low
        retest_ok = float(last["high"]) >= recent_low and float(last["close"]) < recent_low
        if break_ok and retest_ok:
            return _make_candidate("structure_break_retest", "sell", float(last["close"]), max(float(last["high"]), recent_low), float(last["close"]) - width, "M5 structure break held on retest.", regime)
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
        bounced = float(recent["high"].max()) >= float(m15["ema20"].iloc[-1]) - abs(float(last["close"])) * 0.0002
        reject = float(last["close"]) < float(prev["low"])
        if bounced and reject:
            target = float(m15["low"].iloc[-25:-1].min())
            return _make_candidate("failed_bounce_continuation", "sell", float(last["close"]), float(recent["high"].max()), min(target, float(last["close"]) - abs(float(last["close"])) * 0.001), "Bearish bounce failed into value, continuation lower confirmed.", regime)
    else:
        dipped = float(recent["low"].min()) <= float(m15["ema20"].iloc[-1]) + abs(float(last["close"])) * 0.0002
        reject = float(last["close"]) > float(prev["high"])
        if dipped and reject:
            target = float(m15["high"].iloc[-25:-1].max())
            return _make_candidate("failed_bounce_continuation", "buy", float(last["close"]), float(recent["low"].min()), max(target, float(last["close"]) + abs(float(last["close"])) * 0.001), "Bullish dip failed lower into value, continuation higher confirmed.", regime)
    return None


def detect_trend_pullback(symbol, direction, regime):
    if not ENABLE_TREND_PULLBACK or regime in ["sideways", "sideways_compression"]:
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
        touched = float(recent["low"].min()) <= float(m15["ema20"].iloc[-1]) + abs(float(last["close"])) * 0.0003
        confirm = float(last["close"]) > float(prev["high"])
        if trend_ok and touched and confirm:
            invalidation = float(recent["low"].min())
            if fvg.get("found"):
                invalidation = min(invalidation, float(fvg.get("gap_low", invalidation)))
            target = float(m15["high"].iloc[-25:-1].max())
            return _make_candidate("trend_pullback", "buy", float(last["close"]), invalidation, max(target, float(last["close"]) + abs(float(last["close"])) * 0.0009), "Trend pullback into M15 value zone.", regime)
    else:
        trend_ok = float(m15["ema20"].iloc[-1]) < float(m15["ema50"].iloc[-1])
        touched = float(recent["high"].max()) >= float(m15["ema20"].iloc[-1]) - abs(float(last["close"])) * 0.0003
        confirm = float(last["close"]) < float(prev["low"])
        if trend_ok and touched and confirm:
            invalidation = float(recent["high"].max())
            if fvg.get("found"):
                invalidation = max(invalidation, float(fvg.get("gap_high", invalidation)))
            target = float(m15["low"].iloc[-25:-1].min())
            return _make_candidate("trend_pullback", "sell", float(last["close"]), invalidation, min(target, float(last["close"]) - abs(float(last["close"])) * 0.0009), "Trend pullback into M15 value zone.", regime)
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

    return _make_candidate("liquidity_reversal", direction, float(sweep["close_after_sweep"]), invalidation, target, "Liquidity sweep reclaimed with VWAP and reversal confirmation.", regime)


def detect_impulse_continuation(symbol, direction, regime):
    if not ENABLE_IMPULSE_CONTINUATION or regime in ["sideways", "sideways_compression"]:
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 60).copy()
    m15["ema20"] = ema(m15["close"], 20)
    mean_body = avg_body(m15, 12)
    impulse_idx = None

    for idx in range(-6, -2):
        body = abs(float(m15["close"].iloc[idx]) - float(m15["open"].iloc[idx]))
        if direction == "buy" and float(m15["close"].iloc[idx]) > float(m15["open"].iloc[idx]) and body > mean_body * 1.7:
            impulse_idx = idx
            break
        if direction == "sell" and float(m15["close"].iloc[idx]) < float(m15["open"].iloc[idx]) and body > mean_body * 1.7:
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
        max_retrace = impulse_close - ((impulse_close - impulse_open) * 0.5)
        shallow = retrace_low >= max_retrace
        confirm = float(last["close"]) > float(m15["ema20"].iloc[-1])
        if shallow and confirm:
            return _make_candidate("impulse_continuation", "buy", float(last["close"]), retrace_low, impulse_high + max(impulse_high - impulse_low, abs(float(last["close"])) * 0.001), "Strong upside impulse followed by shallow retracement and hold.", regime)
    else:
        retrace_high = float(recent["high"].max())
        max_retrace = impulse_close + ((impulse_open - impulse_close) * 0.5)
        shallow = retrace_high <= max_retrace
        confirm = float(last["close"]) < float(m15["ema20"].iloc[-1])
        if shallow and confirm:
            return _make_candidate("impulse_continuation", "sell", float(last["close"]), retrace_high, impulse_low - max(impulse_high - impulse_low, abs(float(last["close"])) * 0.001), "Strong downside impulse followed by shallow retracement and hold.", regime)
    return None


def build_trade_plan(candidate, snapshot):
    tick = get_tick(snapshot["symbol"])
    direction = candidate["direction"]
    entry = float(tick.ask if direction == "buy" else tick.bid)
    daily_atr = float(snapshot["daily_atr_14"])
    h4_atr = float(snapshot["h4_atr_14"])
    buffer_size = max(daily_atr * 0.08, h4_atr * 0.12, abs(entry) * 0.00015)

    if direction == "buy":
        sl = float(candidate["invalidation_level"]) - buffer_size
        risk = max(entry - sl, abs(entry) * 0.0002)
        tp_anchor = max(float(candidate["target_level"]), entry + risk * TP_RR)
        tp2 = max(tp_anchor + risk * 0.8, entry + risk * (TP_RR + 0.8))
    else:
        sl = float(candidate["invalidation_level"]) + buffer_size
        risk = max(sl - entry, abs(entry) * 0.0002)
        tp_anchor = min(float(candidate["target_level"]), entry - risk * TP_RR)
        tp2 = min(tp_anchor - risk * 0.8, entry - risk * (TP_RR + 0.8))

    candidate["entry"] = round(entry, 5)
    candidate["sl"] = round(sl, 5)
    candidate["tp"] = round(tp_anchor, 5)
    candidate["tp2"] = round(tp2, 5)
    return candidate


def local_candidate_score(candidate, snapshot, session_name):
    profile = get_profile(snapshot["symbol"])
    setup_weight = profile["setup_weight"].get(candidate["setup_type"], 1.0)
    session_weight = profile["session_weight"].get(session_name, 0.4)

    entry = float(candidate["entry"])
    sl = float(candidate["sl"])
    tp = float(candidate["tp"])
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0.0

    base = 52.0
    base += (setup_weight - 1.0) * 24.0
    base += (session_weight - 1.0) * 18.0

    regime = snapshot.get("regime", "sideways")
    if regime in ["bullish_expansion", "bearish_expansion"] and candidate["setup_type"] in ["breakout_continuation", "failed_bounce_continuation", "impulse_continuation"]:
        base += 8
    if regime in ["bullish_trend", "bearish_trend"] and candidate["setup_type"] in ["trend_pullback", "breakout_retest", "structure_break_retest"]:
        base += 6
    if regime in ["sideways", "sideways_compression"] and candidate["setup_type"] in ["trend_pullback", "impulse_continuation"]:
        base -= 12

    if rr >= MIN_RR:
        base += min((rr - MIN_RR) * 10.0, 12.0)
    else:
        base -= 20

    vwap = float(snapshot.get("m5_vwap", entry))
    vwap_distance = abs(entry - vwap)
    daily_atr = max(float(snapshot.get("daily_atr_14", 0.0)), abs(entry) * 0.001)
    if vwap_distance <= daily_atr * 0.12:
        base += 5
    elif vwap_distance >= daily_atr * 0.35:
        base -= 8

    recent_range = float(snapshot.get("recent_structure", {}).get("recent_range", 0.0))
    if candidate["setup_type"] in ["breakout_continuation", "breakout_retest"] and recent_range > daily_atr * 0.35:
        base += 4

    return round(max(0.0, min(100.0, base)), 1)


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
        "current_bid": round(float(tick.bid), 5),
        "current_ask": round(float(tick.ask), 5),
        "bias": bias,
        "regime": regime,
        "today_open": round(float(d1["open"].iloc[-1]), 5),
        "today_high": round(float(d1["high"].iloc[-1]), 5),
        "today_low": round(float(d1["low"].iloc[-1]), 5),
        "m15_last_close": round(float(m15["close"].iloc[-1]), 5),
        "m15_last_high": round(float(m15["high"].iloc[-1]), 5),
        "m15_last_low": round(float(m15["low"].iloc[-1]), 5),
        "m5_last_close": round(float(m5["close"].iloc[-1]), 5),
        "m5_last_bar_time": str(m5["time"].iloc[-1]),
        "m5_vwap": round(float(m5_vwap.iloc[-1]), 5),
        "daily_atr_14": d1_atr,
        "h4_atr_14": h4_atr,
        "recent_structure": {
            "recent_high": round(recent_high, 5),
            "recent_low": round(recent_low, 5),
            "recent_range": round(recent_range, 5),
        },
    }


def generate_setup_candidates(symbol, session_name):
    snapshot = get_market_snapshot(symbol)
    regime = snapshot["regime"]
    bias = snapshot["bias"]

    directions = []
    if bias == "bullish":
        directions.extend(["buy", "sell"] if not BUY_ONLY else ["buy"])
    elif bias == "bearish":
        directions.extend(["sell", "buy"] if not BUY_ONLY else ["buy"])
    else:
        directions.extend(["buy"] if BUY_ONLY else ["buy", "sell"])

    detectors = [
        detect_breakout_retest,
        detect_structure_break_retest,
        detect_breakout_continuation,
        detect_failed_bounce_continuation,
        detect_liquidity_reversal,
        detect_trend_pullback,
        detect_impulse_continuation,
    ]

    candidates = []
    seen = set()
    for direction in directions:
        for detector in detectors:
            candidate = detector(symbol, direction, regime)
            if candidate:
                candidate = build_trade_plan(candidate, snapshot)
                fp = (candidate["setup_type"], candidate["direction"], round(candidate["trigger_level"], 5), round(candidate["invalidation_level"], 5))
                if fp in seen:
                    continue
                seen.add(fp)
                candidate["local_score"] = local_candidate_score(candidate, snapshot, session_name)
                candidates.append(candidate)

    candidates.sort(key=lambda x: (-x.get("local_score", 0), x.get("setup_type", "")))
    return snapshot, candidates
