import re
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


TELEGRAM_BASE_URL = "https://api.telegram.org/bot{0}".format(TELEGRAM_BOT_TOKEN)


def escape_markdown_v2(text):
    if text is None:
        return ""
    text = str(text)
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(r"([%s])" % re.escape(special_chars), r"\\\1", text)


def _send(payload):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured.")
        return False

    url = "{0}/sendMessage".format(TELEGRAM_BASE_URL)
    try:
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            print("Telegram API error: {0}".format(data))
            return False
        return True
    except requests.RequestException as e:
        print("Telegram request failed: {0}".format(e))
        return False
    except Exception as e:
        print("Telegram send failed: {0}".format(e))
        return False


def send_telegram_message(text, use_markdown=False):
    if not text:
        return False

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": escape_markdown_v2(text) if use_markdown else str(text),
        "disable_web_page_preview": True,
    }
    if use_markdown:
        payload["parse_mode"] = "MarkdownV2"
    return _send(payload)


def send_human_update(text):
    return send_telegram_message(text, use_markdown=False)


def send_structured_signal(title, lines):
    body = [str(title).strip(), ""]
    body.extend([str(line).strip() for line in lines if str(line).strip()])
    return send_telegram_message("\n".join(body), use_markdown=False)
