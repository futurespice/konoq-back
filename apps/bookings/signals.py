from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Booking

import threading
import logging
logger = logging.getLogger(__name__)

@receiver(pre_save, sender=Booking)
def notify_whatsapp_on_confirm(sender, instance, **kwargs):
    if not instance.pk:
        return
        
    try:
        old_status = Booking.objects.get(pk=instance.pk).status
    except Booking.DoesNotExist:
        return
        
    if old_status != Booking.Status.CONFIRMED and instance.status == Booking.Status.CONFIRMED:
        if instance.source == Booking.Source.WHATSAPP:
            def _send():
                try:
                    from apps.wa_bot.meta_api import send_wa_message
                    branch_name = instance.branch.name if instance.branch else 'Konoq'
                    msg = f"🎉 Ваша бронь #{instance.id} подтверждена администратором!\n\nОтель: {branch_name}\nДаты: {instance.checkin} — {instance.checkout}\nГости: {instance.guests}\n\nС нетерпением ждём вас! 😊"
                    send_wa_message(instance.phone, msg)
                except Exception as e:
                    logger.error("Не удалось отправить WA на %s: %s", instance.phone, e)
            
            threading.Thread(target=_send, daemon=True).start()

    elif old_status != Booking.Status.CANCELLED and instance.status == Booking.Status.CANCELLED:
        if instance.source == Booking.Source.WHATSAPP:
            def _send_cancel():
                try:
                    from apps.wa_bot.meta_api import send_wa_message
                    msg = f"😔 К сожалению, менеджер отклонил вашу заявку #{instance.id} (нет мест на выбранные даты).\n\nНапишите любое сообщение, чтобы выбрать другие даты."
                    send_wa_message(instance.phone, msg)
                except Exception as e:
                    logger.error("Не удалось отправить WA отмену на %s: %s", instance.phone, e)
            
            threading.Thread(target=_send_cancel, daemon=True).start()
