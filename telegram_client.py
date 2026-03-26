import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

TELEGRAM_BASE_URL = "https://api.telegram.org/bot{0}".format(TELEGRAM_BOT_TOKEN)

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
    except Exception as e:
        print("Telegram send failed: {0}".format(e))
        return False

def send_human_update(text):
    if not text:
        return False
    return _send({"chat_id": TELEGRAM_CHAT_ID, "text": str(text), "disable_web_page_preview": True})

def send_structured_signal(title, lines):
    body = [str(title).strip(), ""]
    body.extend([str(line).strip() for line in lines if str(line).strip()])
    return send_human_update("\n".join(body))
