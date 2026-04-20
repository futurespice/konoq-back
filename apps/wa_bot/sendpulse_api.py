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

    if not client_id or not client_secret:
        raise ValueError("SENDPULSE_CLIENT_ID / SENDPULSE_CLIENT_SECRET не заданы")

    url = "https://api.sendpulse.com/oauth/access_token"
    payload = json.dumps({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        if hasattr(exc, "read"):
            raise RuntimeError(f"SendPulse OAuth error: {exc.read().decode()}")
        raise

    token = data["access_token"]
    _token_cache["token"] = token
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    logger.info("SendPulse OAuth token получен успешно")
    return token


def send_wa_message(phone: str, text: str):
    """Отправка сообщения через SendPulse WhatsApp Bot API"""
    bot_id = getattr(settings, "SENDPULSE_BOT_ID", "")

    if not bot_id:
        logger.warning("SENDPULSE_BOT_ID не настроен.")
        return

    clean_phone = ''.join(filter(str.isdigit, phone))

    try:
        token = _get_access_token()
    except Exception as e:
        logger.error("Не удалось получить токен SendPulse: %s", e)
        return

    # Шаг 1 — получаем contact_id по номеру телефона
    contact_id = _get_contact_id(token, bot_id, clean_phone)
    if not contact_id:
        logger.error("Контакт не найден в SendPulse для номера %s", clean_phone)
        return

    # Шаг 2 — отправляем сообщение
    url = "https://api.sendpulse.com/whatsapp/contacts/send"
    payload = json.dumps({
        "contact_id": contact_id,
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
            logger.error("SendPulse WA ошибка отправки: %s", err)
        else:
            logger.error("SendPulse WA неизвестная ошибка: %s", exc)


def _get_contact_id(token: str, bot_id: str, phone: str) -> str | None:
    """Ищем contact_id по номеру телефона в SendPulse (берём контакт с type=2 — реальный пользователь)"""
    url = f"https://api.sendpulse.com/whatsapp/contacts?bot_id={bot_id}&phone={phone}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            contacts = data if isinstance(data, list) else data.get("data", [])
            # type=2 — реальный пользователь, type=1 — сам бот
            user_contact = next((c for c in contacts if c.get("type") == 2), None)
            if user_contact:
                logger.info("SendPulse contact найден: %s", user_contact.get("id"))
                return user_contact.get("id")
            logger.warning("SendPulse: контакт type=2 не найден среди %d записей", len(contacts))
    except Exception as exc:
        if hasattr(exc, "read"):
            logger.error("SendPulse get_contact error: %s", exc.read().decode())
        else:
            logger.error("SendPulse get_contact error: %s", exc)
    return None