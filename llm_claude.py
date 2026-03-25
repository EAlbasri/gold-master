import json
import re

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, USE_CLAUDE_WEB_SEARCH


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


def _collect_text(response):
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def _basic_call(prompt, max_tokens=900):
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(_collect_text(response))


def _web_call(prompt, max_tokens=900):
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }
        ],
    )
    return _extract_json(_collect_text(response))


def _call_json(prompt, max_tokens=900, use_web=False):
    if use_web and USE_CLAUDE_WEB_SEARCH:
        try:
            return _web_call(prompt, max_tokens=max_tokens)
        except Exception:
            return _basic_call(prompt, max_tokens=max_tokens)
    return _basic_call(prompt, max_tokens=max_tokens)


def evaluate_setup(payload):
    prompt = """
You are Gold Master's professional XAUUSD execution reviewer.

You are reviewing a PRE-BUILT intraday trade candidate.
You do not invent trades.
You must reject weak, late, overextended, or low-quality setups.

Review using:
- overall market bias
- current regime
- setup type
- breakout quality
- retest quality
- liquidity sweep quality
- impulse quality
- VWAP relationship
- whether stop-loss is logically placed
- whether TP is realistic for intraday gold
- whether the setup is too late after expansion
- whether RR is acceptable

Approve only clean, high-quality intraday setups.
If uncertain, reject.

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

    result = _call_json(prompt, max_tokens=900, use_web=False)
    result.setdefault("trade", False)
    result.setdefault("direction", "none")
    result.setdefault("score", 0)
    result.setdefault("regime", "unclear")
    result.setdefault("reason", "No reason returned.")
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

Use web search if available to verify fresh macro, news, and geopolitical context relevant to gold.
Focus only on meaningful drivers such as:
- Federal Reserve / central bank comments
- US dollar direction
- Treasury yields / real yields
- CPI / PCE / payrolls / FOMC
- geopolitical escalation or de-escalation
- risk-on / risk-off shifts

You are NOT choosing the trade from scratch.
You are only deciding whether fresh macro context should veto, reduce confidence, or support an already strong technical setup.

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

    result = _call_json(prompt, max_tokens=800, use_web=use_web)
    result.setdefault("allow_trade", True)
    result.setdefault("adjusted_score", 0)
    result.setdefault("headline", "")
    result.setdefault("macro_reason", "")
    result.setdefault("risk_flag", "none")

    if not isinstance(result["allow_trade"], bool):
        result["allow_trade"] = True
    try:
        result["adjusted_score"] = int(result["adjusted_score"])
    except Exception:
        result["adjusted_score"] = 0
    if result["risk_flag"] not in ["none", "caution", "veto"]:
        result["risk_flag"] = "none"
    return result


def daily_market_analysis(payload, use_web=False):
    prompt = """
You are Gold Master's XAUUSD market analyst.

You are given:
- a structured market snapshot
- the bot's persistent state from earlier updates
- a context such as startup, session_open, pulse_update, or macro_update

If web search is available, use it only to verify fresh macro context relevant to gold, the US dollar, yields, inflation, central banks, or major geopolitical developments.

Your task:
1. Decide whether the market currently looks bullish, bearish, or sideways.
2. Keep continuity with prior watched levels if they still matter.
3. Give a concise trader-friendly summary.
4. Estimate an expected high and expected low as intraday scenario levels.
5. Provide one key upside level and one key downside level.
6. Keep the tone human and practical.

Return JSON only:
{
  "bias": "bullish|bearish|sideways",
  "summary": "2-4 short sentences in natural human language",
  "expected_high": 0,
  "expected_low": 0,
  "key_level_up": 0,
  "key_level_down": 0
}

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))

    result = _call_json(prompt, max_tokens=900, use_web=use_web)
    result.setdefault("bias", "sideways")
    result.setdefault("summary", "Gold is mixed for now, so I'm waiting for cleaner structure before leaning too hard either way.")
    result.setdefault("expected_high", 0)
    result.setdefault("expected_low", 0)
    result.setdefault("key_level_up", 0)
    result.setdefault("key_level_down", 0)
    if result["bias"] not in ["bullish", "bearish", "sideways"]:
        result["bias"] = "sideways"
    for key in ["expected_high", "expected_low", "key_level_up", "key_level_down"]:
        try:
            result[key] = float(result[key])
        except Exception:
            result[key] = 0.0
    return result


def macro_news_brief(payload, use_web=True):
    prompt = """
You are Gold Master's macro commentator for XAUUSD.

Use web search if available to check for fresh macro or geopolitical developments relevant to gold.
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

    result = _call_json(prompt, max_tokens=700, use_web=use_web)
    result.setdefault("has_update", False)
    result.setdefault("headline", "")
    result.setdefault("impact_note", "")
    if not isinstance(result["has_update"], bool):
        result["has_update"] = False
    return result
