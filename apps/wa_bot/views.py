import json
import logging
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .handlers import handle_message
from .models import WhatsAppProcessedEvent

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):

    def get(self, request):
        """
        SendPulse не делает GET-верификацию как Meta,
        но оставляем на случай совместимости.
        """
        return HttpResponse("ok", status=200)

    def post(self, request):
        try:
            body = json.loads(request.body)
            logger.info("SendPulse RAW: %s", json.dumps(body, ensure_ascii=False))

            # SendPulse шлёт список событий
            events = body if isinstance(body, list) else [body]

            for event_data in events:
                title = event_data.get("title")
                if title != "incoming_message":
                    continue

                contact = event_data.get("contact", {})
                phone = str(contact.get("phone", ""))
                contact_id = contact.get("id", "")

                # Текст вложен в info.message.channel_data.message
                try:
                    msg = event_data["info"]["message"]["channel_data"]["message"]
                except (KeyError, TypeError):
                    continue

                msg_type = msg.get("type", "")
                if phone and contact_id and msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                    if not text:
                        continue

                    event_id = str(event_data.get("id") or "") or f"{msg.get('id', '')}:{contact_id}"
                    if event_id == ":":
                        logger.warning("SendPulse event без id — пропускаем идемпотентность")
                    else:
                        try:
                            _, created = WhatsAppProcessedEvent.objects.get_or_create(event_id=event_id)
                        except IntegrityError:
                            created = False
                        if not created:
                            logger.info("SendPulse WA duplicate event skipped: %s", event_id)
                            continue

                    handle_message(phone, text, contact_id)

            return JsonResponse({"status": "ok"}, status=200)

        except Exception as exc:
            logger.error("Ошибка SendPulse WA Webhook: %s", exc, exc_info=True)
            return HttpResponse(status=500)