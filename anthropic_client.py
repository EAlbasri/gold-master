import json
import re
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, CLAUDE_REVIEW_MAX_TOKENS

client = Anthropic(api_key=ANTHROPIC_API_KEY)

def _extract_json(text):
    if not text:
        raise ValueError("Empty response from Claude")
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Could not parse Claude JSON response: {0}".format(cleaned))
    return json.loads(match.group(0))

def review_trade_candidate(payload):
    prompt = """
You are the final trade reviewer for Gold Master, a disciplined XAUUSD day-trading system.

You review a PRE-BUILT intraday gold trade candidate. You do not invent trades.
You reject weak, late, low-RR, or structurally poor setups.

Review using:
- intraday market structure
- setup type suitability for gold day trading
- breakout quality or retest quality
- liquidity sweep quality
- impulse continuation quality
- VWAP relationship
- session timing
- whether the move is already too stretched
- whether the stop-loss is logically placed
- whether TP is realistic for same-day trading

Important:
- Gold often rewards breakout continuation, breakout retest, liquidity reversal, and event-driven impulse continuation.
- Be strict.
- If the setup is merely decent but not high quality, reject it.
- If SL or TP are poor, flag them.

Return JSON only:
{
  "trade": true_or_false,
  "direction": "buy|sell|none",
  "score": 0,
  "regime": "trend_pullback|breakout_continuation|breakout_retest|liquidity_reversal|impulse_continuation|sideways|unclear",
  "reason": "brief plain-English explanation",
  "sl_valid": true_or_false,
  "tp_valid": true_or_false
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=CLAUDE_REVIEW_MAX_TOKENS,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
    result = _extract_json(text)
    result.setdefault("trade", False)
    result.setdefault("direction", "none")
    result.setdefault("score", 0)
    result.setdefault("regime", "unclear")
    result.setdefault("reason", "No reason returned.")
    result.setdefault("sl_valid", False)
    result.setdefault("tp_valid", False)
    return result
