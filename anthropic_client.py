import json
import re
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, USE_CLAUDE_WEB_SEARCH

client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _extract_json(text):
    if not text:
        raise ValueError("Empty response from Claude")
    cleaned = str(text).strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Could not parse Claude JSON response: {0}".format(cleaned))
    raw = match.group(0)
    if raw.count("{") > raw.count("}"):
        raw = raw + ("}" * (raw.count("{") - raw.count("}")))
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    return json.loads(raw)

def _basic_call(prompt, max_tokens=220):
    response = client.messages.create(model=CLAUDE_MODEL, max_tokens=max_tokens, temperature=0, messages=[{"role": "user", "content": prompt}])
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
    return _extract_json(text)

def _web_call(prompt, max_tokens=220):
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
    return _extract_json(text)

def _call_json(prompt, max_tokens=220, use_web=False):
    try:
        if use_web and USE_CLAUDE_WEB_SEARCH:
            return _web_call(prompt, max_tokens=max_tokens)
        return _basic_call(prompt, max_tokens=max_tokens)
    except Exception:
        return {"trade": False, "direction": "none", "score": 0, "regime": "unclear", "reason": "Model reply was unclear, so Gold Master stands aside.", "sl_valid": False, "tp_valid": False}

def evaluate_setup(payload):
    prompt = """
You are Gold Master's professional XAUUSD execution reviewer.

You are reviewing one PRE-BUILT intraday gold trade candidate.
You do not invent trades.
You must reject weak, late, overstretched, sideways, low-RR, or structurally poor setups.

Critical review rules:
- Reject trend_pullback if regime is sideways.
- Reject impulse_continuation if regime is sideways or price is already stretched.
- Reject breakout_continuation if move is already too extended from VWAP or breakout level.
- Reject setups with poor stop-loss placement.
- Reject setups with unrealistic same-day targets.
- Reject off-session setups unless structure is exceptionally clean.
- If uncertain, reject.

Return JSON only.
Keep the reason VERY short: maximum 18 words.

Return exactly:
{
  "trade": true_or_false,
  "direction": "buy|sell|none",
  "score": 0,
  "regime": "trend_pullback|breakout_continuation|breakout_retest|liquidity_reversal|impulse_continuation|sideways|unclear",
  "reason": "max 18 words",
  "sl_valid": true_or_false,
  "tp_valid": true_or_false
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))
    result = _call_json(prompt, max_tokens=220, use_web=False)
    result.setdefault("trade", False)
    result.setdefault("direction", "none")
    result.setdefault("score", 0)
    result.setdefault("regime", "unclear")
    result.setdefault("reason", "No trade.")
    result.setdefault("sl_valid", False)
    result.setdefault("tp_valid", False)
    if result["direction"] not in ["buy", "sell", "none"]:
        result["direction"] = "none"
    try:
        result["score"] = int(result["score"])
    except Exception:
        result["score"] = 0
    result["score"] = max(0, min(100, result["score"]))
    if not isinstance(result["trade"], bool):
        result["trade"] = False
    if not isinstance(result["sl_valid"], bool):
        result["sl_valid"] = False
    if not isinstance(result["tp_valid"], bool):
        result["tp_valid"] = False
    return result
