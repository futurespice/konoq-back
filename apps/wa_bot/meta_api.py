import json
import urllib.request
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_wa_message(phone: str, text: str):
    token = getattr(settings, "WA_TOKEN", "")
    phone_id = getattr(settings, "WA_PHONE_NUMBER_ID", "")

    if not token or not phone_id:
        logger.warning("WA API credentials не настроены.")
        return

    clean_phone = ''.join(filter(str.isdigit, phone))

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    data = json.dumps(payload).encode('utf-8')
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res = response.read()
            logger.info("WA message sent. Status: %s", response.status)
            return json.loads(res)
    except Exception as exc:
        if hasattr(exc, "read"):
            logger.error("Ошибка при отправке WA: %s", exc.read().decode())
        else:
            logger.error("Неизвестная ошибка при отправке WA: %s", exc)
