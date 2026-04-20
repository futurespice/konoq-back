from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Booking

import threading
import logging
logger = logging.getLogger(__name__)


def _get_session_for_phone(phone: str):
    """Get WhatsApp session by phone number"""
    try:
        from apps.wa_bot.models import WhatsAppSession
        clean = phone.lstrip('+')
        return WhatsAppSession.objects.filter(phone=clean).first()
    except Exception:
        return None


def _get_contact_id_for_phone(phone: str) -> str:
    session = _get_session_for_phone(phone)
    return session.data.get('contact_id', '') if session else ''


def _wa_confirm_msg(lang: str, booking) -> str:
    branch_name = booking.branch.name if booking.branch else 'Konoq'
    checkin = booking.checkin.strftime('%d.%m.%Y') if booking.checkin else ''
    checkout = booking.checkout.strftime('%d.%m.%Y') if booking.checkout else ''
    if lang == 'en':
        return (
            f"🎉 Your booking #{booking.id} is confirmed!"
            f"\n\n🏨 {branch_name}"
            f"\n🛬 Check-in: {checkin}"
            f"\n🛫 Check-out: {checkout}"
            f"\n👥 Guests: {booking.guests}"
            f"\n\nWe look forward to welcoming you! 😊"
        )
    return (
        f"🎉 Ваша бронь #{booking.id} подтверждена!"
        f"\n\n🏨 {branch_name}"
        f"\n🛬 Заезд: {checkin}"
        f"\n🛫 Выезд: {checkout}"
        f"\n👥 Гостей: {booking.guests}"
        f"\n\nС нетерпением ждём вас! 😊"
    )


def _wa_cancel_msg(lang: str, booking) -> str:
    if lang == 'en':
        return (
            f"😔 Unfortunately, your booking #{booking.id} has been declined."
            f"\nReason: no available rooms for the selected dates."
            f"\n\nWrite us to choose different dates."
        )
    return (
        f"😔 К сожалению, ваша заявка #{booking.id} отклонена."
        f"\nПричина: нет свободных мест на выбранные даты."
        f"\n\nНапишите нам, чтобы выбрать другие даты."
    )


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
            session = _get_session_for_phone(phone)
            contact_id = session.data.get('contact_id', '') if session else ''
            lang = session.lang if session else 'ru'
            booking_snapshot = instance

            def _send():
                try:
                    from apps.wa_bot.sendpulse_api import send_wa_message
                    msg = _wa_confirm_msg(lang, booking_snapshot)
                    send_wa_message(phone, msg, contact_id)
                except Exception as e:
                    logger.error("Не удалось отправить WA подтверждение на %s: %s", phone, e)

            threading.Thread(target=_send, daemon=True).start()

    elif old_status != Booking.Status.CANCELLED and instance.status == Booking.Status.CANCELLED:
        if instance.source == Booking.Source.WHATSAPP:
            phone = instance.phone
            session = _get_session_for_phone(phone)
            contact_id = session.data.get('contact_id', '') if session else ''
            lang = session.lang if session else 'ru'
            booking_snapshot = instance

            def _send_cancel():
                try:
                    from apps.wa_bot.sendpulse_api import send_wa_message
                    msg = _wa_cancel_msg(lang, booking_snapshot)
                    send_wa_message(phone, msg, contact_id)
                except Exception as e:
                    logger.error("Не удалось отправить WA отмену на %s: %s", phone, e)

            threading.Thread(target=_send_cancel, daemon=True).start()
