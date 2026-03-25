import json
import re
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_COMMENTARY_MODEL, OPENAI_COMMENTARY_MAX_TOKENS, OPENAI_MACRO_MAX_TOKENS, OPENAI_WEB_SEARCH

client = OpenAI(api_key=OPENAI_API_KEY)

def _extract_json(text):
    if not text:
        raise ValueError("Empty response from OpenAI")
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("Could not parse OpenAI JSON response: {0}".format(cleaned))
    return json.loads(match.group(0))

def _response_to_text(response):
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text
    try:
        parts = []
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    except Exception:
        return ""

def _call_json(prompt, max_tokens, use_web=False):
    kwargs = {
        "model": OPENAI_COMMENTARY_MODEL,
        "input": prompt,
        "max_output_tokens": max_tokens,
    }
    if use_web and OPENAI_WEB_SEARCH:
        kwargs["tools"] = [{"type": "web_search_preview"}]
        kwargs["tool_choice"] = "auto"
        kwargs["max_tool_calls"] = 2
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
    result = _call_json(prompt, OPENAI_COMMENTARY_MAX_TOKENS, use_web=use_web)
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
    result = _call_json(prompt, OPENAI_MACRO_MAX_TOKENS, use_web=use_web)
    result.setdefault("has_update", False)
    result.setdefault("headline", "")
    result.setdefault("impact_note", "")
    return result
