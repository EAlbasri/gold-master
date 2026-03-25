import MetaTrader5 as mt5
import pandas as pd
from config import BUY_ONLY, ENABLE_BREAKOUT_CONTINUATION, ENABLE_BREAKOUT_RETEST, ENABLE_IMPULSE_CONTINUATION, ENABLE_LIQUIDITY_REVERSAL, ENABLE_TREND_PULLBACK, TP_RR
from mt5_client import get_rates, get_tick

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def atr(df, period=14):
    data = df.copy()
    data["prev_close"] = data["close"].shift(1)
    data["tr"] = data.apply(lambda row: max(row["high"] - row["low"], abs(row["high"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0, abs(row["low"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0), axis=1)
    value = data["tr"].rolling(period).mean().iloc[-1]
    return round(float(value), 2) if pd.notna(value) else 0.0

def candle_body(df, idx=-1):
    return abs(float(df["close"].iloc[idx]) - float(df["open"].iloc[idx]))

def avg_body(df, n=10):
    sample = df.iloc[-n:]
    return float((sample["close"] - sample["open"]).abs().mean())

def spread_ok(symbol, max_spread_points):
    tick = get_tick(symbol)
    info = mt5.symbol_info(symbol)
    if info is None:
        return False
    spread_points = int((tick.ask - tick.bid) / info.point)
    return spread_points <= max_spread_points

def get_intraday_vwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = df["tick_volume"].replace(0, 1)
    return (typical * volume).cumsum() / volume.cumsum()

def vwap_position(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 80).copy()
    vwap = get_intraday_vwap(m5)
    last_close = float(m5["close"].iloc[-1])
    last_vwap = float(vwap.iloc[-1])
    return last_close > last_vwap if direction == "buy" else last_close < last_vwap

def market_bias(symbol):
    d1 = get_rates(symbol, mt5.TIMEFRAME_D1, 250)
    h4 = get_rates(symbol, mt5.TIMEFRAME_H4, 250)
    d1["ema20"] = ema(d1["close"], 20)
    d1["ema50"] = ema(d1["close"], 50)
    d1["ema200"] = ema(d1["close"], 200)
    h4["ema20"] = ema(h4["close"], 20)
    h4["ema50"] = ema(h4["close"], 50)
    bullish = d1["ema20"].iloc[-1] > d1["ema50"].iloc[-1] > d1["ema200"].iloc[-1] and h4["close"].iloc[-1] > h4["ema20"].iloc[-1] > h4["ema50"].iloc[-1]
    bearish = d1["ema20"].iloc[-1] < d1["ema50"].iloc[-1] < d1["ema200"].iloc[-1] and h4["close"].iloc[-1] < h4["ema20"].iloc[-1] < h4["ema50"].iloc[-1]
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "sideways"

def classify_regime(symbol):
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 90)
    bias = market_bias(symbol)
    range_high = float(m15["high"].iloc[-21:-1].max())
    range_low = float(m15["low"].iloc[-21:-1].min())
    last_close = float(m15["close"].iloc[-1])
    last_body = candle_body(m15, -1)
    mean_body = avg_body(m15, 12)
    compression_pct = ((range_high - range_low) / max(last_close, 1.0)) * 100.0
    if bias == "bullish" and last_close > range_high and last_body > mean_body * 1.25:
        return "bullish_expansion"
    if bias == "bearish" and last_close < range_low and last_body > mean_body * 1.25:
        return "bearish_expansion"
    if compression_pct < 0.80:
        return "sideways_compression"
    if bias == "bullish":
        return "bullish_trend"
    if bias == "bearish":
        return "bearish_trend"
    return "sideways"

def find_latest_fvg(symbol, direction):
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 50)
    for i in range(len(m15) - 1, 2, -1):
        c1 = m15.iloc[i - 2]
        c2 = m15.iloc[i - 1]
        c3 = m15.iloc[i]
        if direction == "buy":
            if float(c1["high"]) < float(c3["low"]):
                low = float(c1["high"]); high = float(c3["low"])
                return {"found": True, "type": "bullish", "gap_low": round(low,2), "gap_high": round(high,2), "mid": round((low+high)/2.0,2), "reference_time": str(c2["time"])}
        else:
            if float(c1["low"]) > float(c3["high"]):
                low = float(c3["high"]); high = float(c1["low"])
                return {"found": True, "type": "bearish", "gap_low": round(low,2), "gap_high": round(high,2), "mid": round((low+high)/2.0,2), "reference_time": str(c2["time"])}
    return {"found": False}

def find_liquidity_sweep(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 50)
    context = m5.iloc[-16:-2]
    if len(context) < 5:
        return {"swept": False}
    if direction == "buy":
        prior_low = float(context["low"].min())
        last_low = float(m5["low"].iloc[-1])
        last_close = float(m5["close"].iloc[-1])
        swept = last_low < prior_low and last_close > prior_low
        return {"swept": swept, "sweep_level": round(prior_low,2), "last_extreme": round(last_low,2), "close_after_sweep": round(last_close,2)}
    prior_high = float(context["high"].max())
    last_high = float(m5["high"].iloc[-1])
    last_close = float(m5["close"].iloc[-1])
    swept = last_high > prior_high and last_close < prior_high
    return {"swept": swept, "sweep_level": round(prior_high,2), "last_extreme": round(last_high,2), "close_after_sweep": round(last_close,2)}

def break_of_micro_structure(symbol, direction):
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 20)
    last_close = float(m5["close"].iloc[-1])
    if direction == "buy":
        return last_close > float(m5["high"].iloc[-6:-1].max())
    return last_close < float(m5["low"].iloc[-6:-1].min())

def _recent_levels(m15):
    return {"range_high_20": float(m15["high"].iloc[-21:-1].max()), "range_low_20": float(m15["low"].iloc[-21:-1].min())}

def _make_candidate(setup_type, direction, trigger_level, invalidation_level, target_level, notes, regime, local_score):
    return {"setup_type": setup_type, "direction": direction, "trigger_level": round(float(trigger_level),2), "invalidation_level": round(float(invalidation_level),2), "target_level": round(float(target_level),2), "notes": notes, "regime": regime, "local_score": int(local_score)}

def detect_breakout_continuation(symbol, direction, regime):
    if not ENABLE_BREAKOUT_CONTINUATION:
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 70)
    last = m15.iloc[-1]
    levels = _recent_levels(m15)
    mean_body = avg_body(m15, 12)
    body = candle_body(m15, -1)
    width = max(levels["range_high_20"] - levels["range_low_20"], 8.0)
    if direction == "buy" and float(last["close"]) > levels["range_high_20"] and body > mean_body * 1.3 and vwap_position(symbol, "buy"):
        return _make_candidate("breakout_continuation", "buy", float(last["close"]), min(float(last["low"]), levels["range_high_20"]), float(last["close"]) + width, "M15 bullish breakout with displacement and acceptance above prior range.", regime, 88 if regime in ["bullish_expansion","bullish_trend"] else 80)
    if direction == "sell" and float(last["close"]) < levels["range_low_20"] and body > mean_body * 1.3 and vwap_position(symbol, "sell"):
        return _make_candidate("breakout_continuation", "sell", float(last["close"]), max(float(last["high"]), levels["range_low_20"]), float(last["close"]) - width, "M15 bearish breakout with displacement and acceptance below prior range.", regime, 88 if regime in ["bearish_expansion","bearish_trend"] else 80)
    return None

def detect_breakout_retest(symbol, direction, regime):
    if not ENABLE_BREAKOUT_RETEST:
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 70)
    prev2 = m15.iloc[-2]; last = m15.iloc[-1]
    levels = _recent_levels(m15)
    width = max(levels["range_high_20"] - levels["range_low_20"], 8.0)
    tolerance = max(width * 0.18, 4.0)
    if direction == "buy":
        breakout = float(prev2["close"]) > levels["range_high_20"]
        retest = float(last["low"]) <= levels["range_high_20"] + tolerance and float(last["close"]) > levels["range_high_20"]
        if breakout and retest and vwap_position(symbol, "buy"):
            return _make_candidate("breakout_retest", "buy", float(last["close"]), min(float(last["low"]), levels["range_high_20"]), float(last["close"]) + width, "Bullish breakout retest holding above the broken range high.", regime, 90 if regime in ["bullish_expansion","bullish_trend"] else 82)
    else:
        breakout = float(prev2["close"]) < levels["range_low_20"]
        retest = float(last["high"]) >= levels["range_low_20"] - tolerance and float(last["close"]) < levels["range_low_20"]
        if breakout and retest and vwap_position(symbol, "sell"):
            return _make_candidate("breakout_retest", "sell", float(last["close"]), max(float(last["high"]), levels["range_low_20"]), float(last["close"]) - width, "Bearish breakout retest holding below the broken range low.", regime, 90 if regime in ["bearish_expansion","bearish_trend"] else 82)
    return None

def detect_trend_pullback(symbol, direction, regime):
    if not ENABLE_TREND_PULLBACK:
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 90).copy(); m15["ema20"] = ema(m15["close"],20); m15["ema50"] = ema(m15["close"],50)
    recent = m15.iloc[-6:]; last = m15.iloc[-1]; prev = m15.iloc[-2]; fvg = find_latest_fvg(symbol, direction)
    if direction == "buy":
        trend_ok = float(m15["ema20"].iloc[-1]) > float(m15["ema50"].iloc[-1])
        touched = float(recent["low"].min()) <= float(m15["ema20"].iloc[-1]) + 4.0
        confirm = float(last["close"]) > float(prev["high"]) or break_of_micro_structure(symbol, "buy")
        if trend_ok and touched and confirm:
            invalidation = float(recent["low"].min())
            if fvg.get("found"): invalidation = min(invalidation, float(fvg.get("gap_low", invalidation)))
            target = float(m15["high"].iloc[-25:-1].max())
            return _make_candidate("trend_pullback", "buy", float(last["close"]), invalidation, max(target, float(last["close"]) + 10.0), "Bull trend pullback into value with continuation confirmation.", regime, 84)
    else:
        trend_ok = float(m15["ema20"].iloc[-1]) < float(m15["ema50"].iloc[-1])
        touched = float(recent["high"].max()) >= float(m15["ema20"].iloc[-1]) - 4.0
        confirm = float(last["close"]) < float(prev["low"]) or break_of_micro_structure(symbol, "sell")
        if trend_ok and touched and confirm:
            invalidation = float(recent["high"].max())
            if fvg.get("found"): invalidation = max(invalidation, float(fvg.get("gap_high", invalidation)))
            target = float(m15["low"].iloc[-25:-1].min())
            return _make_candidate("trend_pullback", "sell", float(last["close"]), invalidation, min(target, float(last["close"]) - 10.0), "Bear trend pullback into value with continuation confirmation.", regime, 84)
    return None

def detect_liquidity_reversal(symbol, direction, regime):
    if not ENABLE_LIQUIDITY_REVERSAL:
        return None
    sweep = find_liquidity_sweep(symbol, direction)
    fvg = find_latest_fvg(symbol, direction)
    if not (sweep.get("swept") and vwap_position(symbol, direction) and break_of_micro_structure(symbol, direction)):
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 50)
    if direction == "buy":
        target = float(m15["high"].iloc[-20:-1].max()); invalidation = min(float(sweep["last_extreme"]), float(fvg.get("gap_low", sweep["last_extreme"]))); score = 86 if regime in ["sideways","sideways_compression","bullish_trend"] else 80
    else:
        target = float(m15["low"].iloc[-20:-1].min()); invalidation = max(float(sweep["last_extreme"]), float(fvg.get("gap_high", sweep["last_extreme"]))); score = 86 if regime in ["sideways","sideways_compression","bearish_trend"] else 80
    return _make_candidate("liquidity_reversal", direction, float(sweep["close_after_sweep"]), invalidation, target, "Liquidity sweep reclaimed with VWAP alignment and micro-structure shift.", regime, score)

def detect_impulse_continuation(symbol, direction, regime):
    if not ENABLE_IMPULSE_CONTINUATION:
        return None
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 70).copy(); m15["ema20"] = ema(m15["close"], 20)
    mean_body = avg_body(m15, 12)
    impulse_idx = None
    for idx in range(-6, -2):
        body = abs(float(m15["close"].iloc[idx]) - float(m15["open"].iloc[idx]))
        if direction == "buy" and float(m15["close"].iloc[idx]) > float(m15["open"].iloc[idx]) and body > mean_body * 1.8:
            impulse_idx = idx; break
        if direction == "sell" and float(m15["close"].iloc[idx]) < float(m15["open"].iloc[idx]) and body > mean_body * 1.8:
            impulse_idx = idx; break
    if impulse_idx is None:
        return None
    impulse_open = float(m15["open"].iloc[impulse_idx]); impulse_close = float(m15["close"].iloc[impulse_idx]); impulse_high = float(m15["high"].iloc[impulse_idx]); impulse_low = float(m15["low"].iloc[impulse_idx])
    recent = m15.iloc[impulse_idx + 1:]; last = m15.iloc[-1]
    if direction == "buy":
        retrace_low = float(recent["low"].min()); max_retrace = impulse_close - ((impulse_close - impulse_open) * 0.5)
        if retrace_low >= max_retrace and float(last["close"]) > float(m15["ema20"].iloc[-1]) and vwap_position(symbol, "buy"):
            return _make_candidate("impulse_continuation", "buy", float(last["close"]), retrace_low, impulse_high + max(impulse_high - impulse_low, 10.0), "Strong upside impulse followed by shallow retracement and continuation hold.", regime, 88 if regime in ["bullish_expansion","bullish_trend"] else 80)
    else:
        retrace_high = float(recent["high"].max()); max_retrace = impulse_close + ((impulse_open - impulse_close) * 0.5)
        if retrace_high <= max_retrace and float(last["close"]) < float(m15["ema20"].iloc[-1]) and vwap_position(symbol, "sell"):
            return _make_candidate("impulse_continuation", "sell", float(last["close"]), retrace_high, impulse_low - max(impulse_high - impulse_low, 10.0), "Strong downside impulse followed by shallow retracement and continuation hold.", regime, 88 if regime in ["bearish_expansion","bearish_trend"] else 80)
    return None

def _priority(candidate):
    order = {"breakout_retest": 1, "breakout_continuation": 2, "impulse_continuation": 3, "liquidity_reversal": 4, "trend_pullback": 5}
    return order.get(candidate["setup_type"], 99)

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
        tp1 = max(float(candidate["target_level"]), entry + risk * TP_RR)
        tp2 = max(tp1 + risk * 0.8, entry + risk * (TP_RR + 0.8))
    else:
        sl = float(candidate["invalidation_level"]) + buffer_size
        risk = max(sl - entry, 0.5)
        tp1 = min(float(candidate["target_level"]), entry - risk * TP_RR)
        tp2 = min(tp1 - risk * 0.8, entry - risk * (TP_RR + 0.8))
    candidate["entry"] = round(entry, 2)
    candidate["sl"] = round(sl, 2)
    candidate["tp"] = round(tp1, 2)
    candidate["tp2"] = round(tp2, 2)
    candidate["rr"] = round(abs(candidate["tp"] - candidate["entry"]) / max(abs(candidate["entry"] - candidate["sl"]), 0.01), 2)
    return candidate

def get_market_snapshot(symbol):
    d1 = get_rates(symbol, mt5.TIMEFRAME_D1, 90)
    h4 = get_rates(symbol, mt5.TIMEFRAME_H4, 90)
    m15 = get_rates(symbol, mt5.TIMEFRAME_M15, 140)
    m5 = get_rates(symbol, mt5.TIMEFRAME_M5, 140)
    tick = get_tick(symbol)
    vwap = get_intraday_vwap(m5)
    recent_high = float(m15["high"].iloc[-20:].max()); recent_low = float(m15["low"].iloc[-20:].min())
    return {"symbol": symbol, "current_bid": round(float(tick.bid),2), "current_ask": round(float(tick.ask),2), "bias": market_bias(symbol), "regime": classify_regime(symbol), "today_open": round(float(d1["open"].iloc[-1]),2), "today_high": round(float(d1["high"].iloc[-1]),2), "today_low": round(float(d1["low"].iloc[-1]),2), "m15_last_close": round(float(m15["close"].iloc[-1]),2), "m5_last_close": round(float(m5["close"].iloc[-1]),2), "m5_vwap": round(float(vwap.iloc[-1]),2), "daily_atr_14": atr(d1,14), "h4_atr_14": atr(h4,14), "recent_structure": {"recent_high": round(recent_high,2), "recent_low": round(recent_low,2), "recent_range": round(recent_high - recent_low,2)}}

def generate_setup_candidates(symbol):
    snapshot = get_market_snapshot(symbol)
    regime = snapshot["regime"]; bias = snapshot["bias"]
    directions = []
    if bias == "bullish":
        directions.append("buy")
    elif bias == "bearish" and not BUY_ONLY:
        directions.append("sell")
    elif bias == "sideways" and not BUY_ONLY:
        directions.extend(["buy", "sell"])
    elif bias == "sideways" and BUY_ONLY:
        directions.append("buy")
    candidates = []
    detectors = [detect_breakout_retest, detect_breakout_continuation, detect_impulse_continuation, detect_liquidity_reversal, detect_trend_pullback]
    for direction in directions:
        for detector in detectors:
            candidate = detector(symbol, direction, regime)
            if candidate:
                candidates.append(build_trade_plan(candidate, snapshot))
    candidates = [c for c in candidates if c.get("rr", 0) >= 1.5]
    candidates.sort(key=lambda x: (_priority(x), -x.get("local_score", 0)))
    return snapshot, candidates
