import json
import logging
from django.conf import settings
from django.http import HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .handlers import handle_message

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):
    def get(self, request):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        expected_token = getattr(settings, "WA_VERIFY_TOKEN", "")

        if mode and token:
            if mode == "subscribe" and token == expected_token:
                logger.info("WA WEBHOOK VERIFIED")
                return HttpResponse(challenge, status=200)
            else:
                return HttpResponse(status=403)
        return HttpResponse(status=400)

    def post(self, request):
        try:
            body = json.loads(request.body)
            if body.get("object") == "whatsapp_business_account":
                for entry in body.get("entry", []):
                    for change in entry.get("changes", []):
                        value = change.get("value", {})
                        if "messages" in value:
                            for msg in value["messages"]:
                                if msg.get("type") == "text":
                                    phone = msg["from"]
                                    text = msg["text"]["body"]
                                    # Delegate to handler
                                    handle_message(phone, text)
            return HttpResponse("ok", status=200)
        except Exception as exc:
            logger.error("Ошибка WA Webhook: %s", exc, exc_info=True)
            return HttpResponse(status=500)
