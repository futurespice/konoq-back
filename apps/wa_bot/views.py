import json
import logging
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .handlers import handle_message

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
            logger.debug("SendPulse WA webhook: %s", body)

            # SendPulse формат входящего сообщения:
            # {
            #   "event": "incoming",
            #   "contact": {"phone": "996XXXXXXXXX"},
            #   "message": {"type": "text", "text": {"body": "..."}}
            # }

            event = body.get("event")
            if event != "incoming":
                return JsonResponse({"status": "ignored"}, status=200)

            contact = body.get("contact", {})
            message = body.get("message", {})

            phone = contact.get("phone", "")
            msg_type = message.get("type", "")

            if phone and msg_type == "text":
                text = message.get("text", {}).get("body", "")
                if text:
                    handle_message(phone, text)

            return JsonResponse({"status": "ok"}, status=200)

        except Exception as exc:
            logger.error("Ошибка SendPulse WA Webhook: %s", exc, exc_info=True)
            return HttpResponse(status=500)