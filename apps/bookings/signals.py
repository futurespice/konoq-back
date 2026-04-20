from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Booking

import threading
import logging
logger = logging.getLogger(__name__)


def _get_contact_id_for_phone(phone: str) -> str:
    """Get SendPulse contact_id from WhatsApp session by phone number"""
    try:
        from apps.wa_bot.models import WhatsAppSession
        clean = phone.lstrip('+')
        session = WhatsAppSession.objects.filter(phone=clean).first()
        if session:
            return session.data.get('contact_id', '')
    except Exception:
        pass
    return ''


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
            phone = instance.phone
            contact_id = _get_contact_id_for_phone(phone)

            def _send():
                try:
                    from apps.wa_bot.sendpulse_api import send_wa_message
                    branch_name = instance.branch.name if instance.branch else 'Konoq'
                    checkin = instance.checkin.strftime('%d.%m.%Y') if instance.checkin else ''
                    checkout = instance.checkout.strftime('%d.%m.%Y') if instance.checkout else ''
                    msg = (
                        f"🎉 Ваша бронь #{instance.id} подтверждена!"
                        f"\n\n🏨 {branch_name}"
                        f"\n🛬 Заезд: {checkin}"
                        f"\n🛫 Выезд: {checkout}"
                        f"\n👥 Гостей: {instance.guests}"
                        f"\n\nС нетерпением ждём вас! 😊"
                    )
                    send_wa_message(phone, msg, contact_id)
                except Exception as e:
                    logger.error("Не удалось отправить WA подтверждение на %s: %s", phone, e)

            threading.Thread(target=_send, daemon=True).start()

    elif old_status != Booking.Status.CANCELLED and instance.status == Booking.Status.CANCELLED:
        if instance.source == Booking.Source.WHATSAPP:
            phone = instance.phone
            contact_id = _get_contact_id_for_phone(phone)

            def _send_cancel():
                try:
                    from apps.wa_bot.sendpulse_api import send_wa_message
                    msg = (
                        f"😔 К сожалению, ваша заявка #{instance.id} отклонена."
                        f"\nПричина: нет свободных мест на выбранные даты."
                        f"\n\nНапишите нам, чтобы выбрать другие даты."
                    )
                    send_wa_message(phone, msg, contact_id)
                except Exception as e:
                    logger.error("Не удалось отправить WA отмену на %s: %s", phone, e)

            threading.Thread(target=_send_cancel, daemon=True).start()
