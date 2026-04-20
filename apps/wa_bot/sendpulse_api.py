import json
import urllib.request
import urllib.parse
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_token_cache = {}


def _get_access_token() -> str:
    """Получаем OAuth2 токен от SendPulse (кэшируем)"""
    import time
    cached = _token_cache.get("token")
    expires_at = _token_cache.get("expires_at", 0)

    if cached and time.time() < expires_at:
        return cached

    client_id = getattr(settings, "SENDPULSE_CLIENT_ID", "")
    client_secret = getattr(settings, "SENDPULSE_CLIENT_SECRET", "")

    url = "https://api.sendpulse.com/oauth/access_token"
    payload = json.dumps({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    return token


def send_wa_message(phone: str, text: str):
    """Отправка сообщения через SendPulse WhatsApp"""
    phone_number = getattr(settings, "SENDPULSE_PHONE", "")

    if not phone_number:
        logger.warning("SENDPULSE_PHONE не настроен.")
        return

    clean_phone = ''.join(filter(str.isdigit, phone))

    try:
        token = _get_access_token()
    except Exception as e:
        logger.error("Не удалось получить токен SendPulse: %s", e)
        return

    url = "https://api.sendpulse.com/whatsapp/contacts/sendByPhone"
    payload = json.dumps({
        "phone": phone_number,  # твой номер отправителя
        "contact_phone": clean_phone,  # получатель
        "messages": [
            {
                "type": "text",
                "text": {"body": text}
            }
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            logger.info("SendPulse WA sent: %s", result)
            return result
    except Exception as exc:
        if hasattr(exc, "read"):
            err = exc.read().decode()
            logger.error("SendPulse WA ошибка: %s", err)
        else:
            logger.error("SendPulse WA неизвестная ошибка: %s", exc)