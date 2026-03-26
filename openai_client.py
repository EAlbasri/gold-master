import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_COMMENTARY_MODEL, OPENAI_COMMENTARY_MAX_TOKENS, OPENAI_MACRO_MAX_TOKENS, OPENAI_WEB_SEARCH

client = OpenAI(api_key=OPENAI_API_KEY)

def _extract_json(text):
    if not text:
        raise ValueError("Empty response from OpenAI")
    cleaned = str(text).strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Could not parse OpenAI JSON response: {0}".format(cleaned))
    return json.loads(match.group(0))

def _get_attr_or_key(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)

def _response_to_text(response):
    direct = _get_attr_or_key(response, "output_text", "")
    if direct:
        return direct.strip()
    parts = []
    try:
        for item in _get_attr_or_key(response, "output", []):
            for content in _get_attr_or_key(item, "content", []):
                if _get_attr_or_key(content, "type", "") == "output_text":
                    text = _get_attr_or_key(content, "text", "")
                    if text:
                        parts.append(text)
    except Exception:
        pass
    joined = "\n".join([p for p in parts if p]).strip()
    if joined:
        return joined
    raise ValueError("Empty response from OpenAI")

def _call_json(prompt, max_tokens, use_web=False):
    kwargs = {
        "model": OPENAI_COMMENTARY_MODEL,
        "input": prompt,
        "max_output_tokens": max_tokens,
        "text": {"format": {"type": "json_object"}},
    }
    if use_web and OPENAI_WEB_SEARCH:
        kwargs["tools"] = [{"type": "web_search_preview", "search_context_size": "low"}]
        kwargs["tool_choice"] = "auto"
    response = client.responses.create(**kwargs)
    return _extract_json(_response_to_text(response))

def generate_market_commentary(payload, use_web=False):
    prompt = """
You are Gold Master, a human-sounding intraday XAUUSD market commentator.

You are given:
- a structured market snapshot
- persistent prior context from the local state store
- a context such as startup, session_open, pulse_update, or macro_update

If web search is available, use it only when it adds fresh macro or geopolitical information relevant to gold day trading.

Tasks:
1. State whether gold looks bullish, bearish, or sideways right now.
2. Keep continuity with earlier watched levels if they still matter.
3. Produce a concise human-style market note.
4. Estimate same-day expected high and low as scenario levels, not guarantees.
5. Provide one key upside level and one key downside level.

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
    try:
        result = _call_json(prompt, OPENAI_COMMENTARY_MAX_TOKENS, use_web=use_web)
    except Exception:
        return {"bias": "sideways", "summary": "Gold is mixed for now, so I’m waiting for cleaner structure before leaning too hard either way.", "expected_high": 0, "expected_low": 0, "key_level_up": 0, "key_level_down": 0}
    result.setdefault("bias", "sideways")
    result.setdefault("summary", "Gold is still mixed for now, so I’m waiting for cleaner structure.")
    result.setdefault("expected_high", 0)
    result.setdefault("expected_low", 0)
    result.setdefault("key_level_up", 0)
    result.setdefault("key_level_down", 0)
    return result

def generate_macro_brief(payload, use_web=True):
    prompt = """
You are Gold Master's macro update writer for XAUUSD.

If web search is available, check only for fresh, material items relevant to intraday gold:
- Federal Reserve
- US dollar
- Treasury yields
- CPI / PCE / payrolls / FOMC
- major wars / geopolitical escalations
- central bank remarks
- broad risk-on / risk-off shocks

Return JSON only:
{
  "has_update": true_or_false,
  "headline": "short headline-style line",
  "impact_note": "1-2 short sentences on likely intraday gold impact"
}

If there is no meaningful fresh update, return has_update=false.

Payload:
{payload_json}
""".replace("{payload_json}", json.dumps(payload, indent=2))
    try:
        result = _call_json(prompt, OPENAI_MACRO_MAX_TOKENS, use_web=use_web)
    except Exception:
        return {"has_update": False, "headline": "", "impact_note": ""}
    result.setdefault("has_update", False)
    result.setdefault("headline", "")
    result.setdefault("impact_note", "")
    return result
