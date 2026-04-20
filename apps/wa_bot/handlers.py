import datetime
from django.db.transaction import atomic
from apps.rooms.models import Branch, Room
from apps.bookings.models import Booking
from .models import WhatsAppSession
from .sendpulse_api import send_wa_message

def _send(phone, text):
    import threading
    threading.Thread(target=send_wa_message, args=(phone, text), daemon=True).start()

def _reset_session(session):
    session.state = WhatsAppSession.State.START
    session.data = {}
    session.save()

@atomic
def handle_message(phone: str, text: str):
    text = text.strip()
    session, created = WhatsAppSession.objects.get_or_create(phone=phone)

    if not created and session.state != WhatsAppSession.State.START:
        from django.utils import timezone
        diff = timezone.now() - session.updated_at
        if diff > datetime.timedelta(hours=3):
            _reset_session(session)
            _send(phone, "⏳ Ваша сессия истекла (прошло более 3 часов). Давайте начнем заново.")
            return

    if text.lower() in ("отмена", "cancel", "стоп"):
        _reset_session(session)
        _send(phone, "Бронирование отменено. Напишите что-нибудь, чтобы начать заново.")
        return

    if session.state == WhatsAppSession.State.START:
        branches = Branch.objects.filter(is_active=True).order_by("id")
        if not branches.exists():
            _send(phone, "К сожалению, сейчас нет доступных отелей.")
            return
        
        msg = "👋 Здравствуйте! Добро пожаловать.\nВыберите филиал (отправьте цифру):\n"
        for i, b in enumerate(branches, 1):
            msg += f"{i}. {b.name}\n"
        
        session.data['branches'] = {str(i): b.id for i, b in enumerate(branches, 1)}
        session.state = WhatsAppSession.State.AWAIT_BRANCH
        session.save()
        _send(phone, msg)
        return

    elif session.state == WhatsAppSession.State.AWAIT_BRANCH:
        branch_id = session.data.get('branches', {}).get(text)
        if not branch_id:
            _send(phone, "Пожалуйста, отправьте номер филиала из списка.")
            return
        
        session.data['branch_id'] = branch_id
        session.state = WhatsAppSession.State.AWAIT_DATES
        session.save()
        _send(phone, "Отлично!\nНапишите даты заезда и выезда в формате: YYYY-MM-DD YYYY-MM-DD\nПример: 2026-05-10 2026-05-15\n\nИли напишите *Отмена*, чтобы прервать.")
        return

    elif session.state == WhatsAppSession.State.AWAIT_DATES:
        parts = text.split()
        if len(parts) != 2:
            _send(phone, "Ожидается две даты через пробел. Пример: 2026-05-10 2026-05-15")
            return
        try:
            checkin = datetime.date.fromisoformat(parts[0])
            checkout = datetime.date.fromisoformat(parts[1])
            if checkin >= checkout:
                _send(phone, "Дата выезда должна быть позже даты заезда.")
                return
            if checkin < datetime.date.today():
                _send(phone, "Дата заезда не может быть в прошлом.")
                return
        except ValueError:
            _send(phone, "Неверный формат даты. Убедитесь, что используете формат YYYY-MM-DD. Пример: 2026-05-10 2026-05-15")
            return

        session.data['checkin'] = str(checkin)
        session.data['checkout'] = str(checkout)
        session.state = WhatsAppSession.State.AWAIT_GUESTS
        session.save()
        _send(phone, f"Даты: {checkin} — {checkout}.\nСколько будет гостей? Напишите число.")
        return

    elif session.state == WhatsAppSession.State.AWAIT_GUESTS:
        if not text.isdigit() or int(text) < 1 or int(text) > 20:
            _send(phone, "Пожалуйста, введите корректное число гостей (от 1 до 20).")
            return
        
        guests = int(text)
        session.data['guests'] = guests
        
        rooms = Room.objects.filter(branch_id=session.data['branch_id'], is_active=True)
        if not rooms.exists():
            _send(phone, "Извините, в этом отеле нет свободных номеров. Напишите *Отмена*.")
            return

        types = set()
        room_list_msg = "Выберите тип номера (отправьте номер):\n"
        mapping = {}
        idx = 1
        for r in rooms:
            if r.room_type not in types:
                types.add(r.room_type)
                mapping[str(idx)] = r.room_type
                bath = "санузел: да" if r.has_bathroom else "санузел: общий"
                room_list_msg += f"{idx}. {r.get_room_type_display()} ({r.price_per_night} сом) - {bath}\n"
                idx += 1
        
        session.data['rooms_map'] = mapping
        session.state = WhatsAppSession.State.AWAIT_ROOM
        session.save()
        _send(phone, room_list_msg)
        return

    elif session.state == WhatsAppSession.State.AWAIT_ROOM:
        room_type = session.data.get('rooms_map', {}).get(text)
        if not room_type:
            _send(phone, "Пожалуйста, отправьте цифру выбранного номера.")
            return
        
        session.data['room_type'] = room_type
        session.state = WhatsAppSession.State.AWAIT_NAME
        session.save()
        _send(phone, "Отличный выбор!\nКак вас зовут? Напишите Ваше Имя и Фамилию через пробел.")
        return

    elif session.state == WhatsAppSession.State.AWAIT_NAME:
        parts = text.split(None, 1)
        name = parts[0]
        surname = parts[1] if len(parts) > 1 else ""

        branch_id = session.data['branch_id']
        checkin_d = session.data['checkin']
        checkout_d = session.data['checkout']
        guests_n = session.data['guests']
        r_type = session.data['room_type']

        from apps.rooms.views import _get_booked_guests
        checkin_obj = datetime.date.fromisoformat(checkin_d)
        checkout_obj = datetime.date.fromisoformat(checkout_d)
        booked_guests_by_type = _get_booked_guests(checkin_obj, checkout_obj, branch_id)
        current_booked = booked_guests_by_type.get(r_type, 0)
        
        rooms_of_type = Room.objects.filter(branch_id=branch_id, room_type=r_type, is_active=True)
        total_capacity = sum(r.capacity for r in rooms_of_type)

        if current_booked + guests_n > total_capacity:
            _reset_session(session)
            _send(phone, "😔 Извините! Пока мы заполняли заявку, последние свободные места в этом номере уже забрали. Напишите «Привет», чтобы выбрать другие даты.")
            return

        b = Booking.objects.create(
            name=name,
            surname=surname,
            phone="+" + phone if not phone.startswith("+") else phone,
            country="Чат WhatsApp",
            purpose=Booking.Purpose.OTHER,
            source=Booking.Source.WHATSAPP,
            branch_id=branch_id,
            checkin=checkin_d,
            checkout=checkout_d,
            guests=guests_n,
            room=r_type,
            status=Booking.Status.PENDING
        )

        _reset_session(session)
        _send(phone, f"✅ Спасибо! Ваша заявка #{b.id} создана и отправлена администратору. Как только номер будет подтвержден, мы напишем вам сюда.")

        try:
            from apps.bookings.views import _send_tg_notification
            _send_tg_notification(b)
        except Exception:
            pass
        return

    _reset_session(session)
    _send(phone, "Программе не удалось понять сообщение. Давайте начнем заново.")
