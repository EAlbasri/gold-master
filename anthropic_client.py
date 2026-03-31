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


def _collect_text(response):
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def _basic_call(prompt, max_tokens=220):
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(_collect_text(response))


def _web_call(prompt, max_tokens=240):
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 2,
            }
        ],
    )
    return _extract_json(_collect_text(response))


def _call_json(prompt, max_tokens=220, use_web=False, fallback=None):
    try:
        if use_web and USE_CLAUDE_WEB_SEARCH:
            return _web_call(prompt, max_tokens=max_tokens)
        return _basic_call(prompt, max_tokens=max_tokens)
    except Exception:
        if fallback is not None:
            return fallback
        raise


def evaluate_setup(payload):
    prompt = """
You are Gold Master's professional XAUUSD execution reviewer.

You are reviewing one PRE-BUILT intraday gold trade candidate.
You do not invent trades.
You must reject weak, late, overstretched, low-RR, off-session, or structurally poor setups.

Important:
- A candidate belongs to one setup family. Other setup families do NOT need to agree.
- Review the candidate on its own merits.
- Be especially strict with breakout continuation when price is late.
- Be especially strict with impulse continuation in sideways conditions.
- Be strict about stop placement and same-day target realism.
- Keep the reason very short: maximum 16 words.

Return JSON only:
{
  "trade": true_or_false,
  "direction": "buy|sell|none",
  "score": 0,
  "regime": "trend_pullback|breakout_continuation|breakout_retest|structure_break_retest|failed_bounce_continuation|liquidity_reversal|impulse_continuation|sideways|unclear",
  "reason": "max 16 words",
  "sl_valid": true_or_false,
  "tp_valid": true_or_false
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))

    fallback = {
        "trade": False,
        "direction": "none",
        "score": 0,
        "regime": "unclear",
        "reason": "No trade.",
        "sl_valid": False,
        "tp_valid": False,
    }

    result = _call_json(prompt, max_tokens=180, use_web=False, fallback=fallback)
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


def macro_veto_for_setup(payload, use_web=True):
    prompt = """
You are Gold Master's macro veto layer for XAUUSD intraday trading.

Use web search if available only to verify fresh macro, news, and geopolitical context relevant to gold.
You are not choosing the trade from scratch.
You are deciding whether fresh macro context should allow, caution, or veto an already strong technical setup.

Return JSON only:
{
  "allow_trade": true_or_false,
  "adjusted_score": 0,
  "headline": "short headline-style line or empty",
  "macro_reason": "1-2 short sentences",
  "risk_flag": "none|caution|veto"
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))

    fallback = {
        "allow_trade": True,
        "adjusted_score": 0,
        "headline": "",
        "macro_reason": "",
        "risk_flag": "none",
    }

    result = _call_json(prompt, max_tokens=220, use_web=use_web, fallback=fallback)
    result.setdefault("allow_trade", True)
    result.setdefault("adjusted_score", 0)
    result.setdefault("headline", "")
    result.setdefault("macro_reason", "")
    result.setdefault("risk_flag", "none")
    return result


def daily_market_analysis(payload, use_web=False):
    prompt = """
You are Gold Master's XAUUSD market analyst.

You are given:
- a structured market snapshot
- persistent prior context from the local state store
- a context such as startup, session_open, pulse_update, or market_closed

If web search is available, use it only to verify fresh macro context relevant to gold.

Tasks:
1. Decide whether the market currently looks bullish, bearish, sideways, or closed.
2. Keep continuity with earlier watched levels if they still matter.
3. Give a concise trader-friendly summary.
4. Estimate expected intraday high and low only if the market is open.
5. Provide one key upside level and one key downside level.

Return JSON only:
{
  "bias": "bullish|bearish|sideways|closed",
  "summary": "2-4 short sentences in natural human language",
  "expected_high": 0,
  "expected_low": 0,
  "key_level_up": 0,
  "key_level_down": 0
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))

    fallback = {
        "bias": "sideways",
        "summary": "Gold is mixed for now, so I’m waiting for cleaner structure before leaning too hard either way.",
        "expected_high": 0,
        "expected_low": 0,
        "key_level_up": 0,
        "key_level_down": 0,
    }

    result = _call_json(prompt, max_tokens=220, use_web=use_web, fallback=fallback)
    result.setdefault("bias", "sideways")
    result.setdefault("summary", fallback["summary"])
    result.setdefault("expected_high", 0)
    result.setdefault("expected_low", 0)
    result.setdefault("key_level_up", 0)
    result.setdefault("key_level_down", 0)
    return result


def macro_news_brief(payload, use_web=True):
    prompt = """
You are Gold Master's macro commentator for XAUUSD.

Use web search if available to check for fresh macro or geopolitical developments relevant to intraday gold.
Focus only on meaningful drivers:
- Federal Reserve
- US dollar
- Treasury yields
- CPI / PCE / payrolls
- wars / geopolitical shocks
- central bank commentary
- major risk-on / risk-off moves

Return JSON only:
{
  "has_update": true_or_false,
  "headline": "short headline-style line",
  "impact_note": "1-2 short sentences on likely gold impact"
}

If there is no meaningful fresh update, return has_update=false.

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))

    fallback = {"has_update": False, "headline": "", "impact_note": ""}

    result = _call_json(prompt, max_tokens=180, use_web=use_web, fallback=fallback)
    result.setdefault("has_update", False)
    result.setdefault("headline", "")
    result.setdefault("impact_note", "")
    return result
