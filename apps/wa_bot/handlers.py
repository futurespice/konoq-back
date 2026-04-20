import datetime
from django.db.transaction import atomic
from apps.rooms.models import Branch, Room
from apps.bookings.models import Booking
from .models import WhatsAppSession
from .sendpulse_api import send_wa_message

# Тексты на двух языках
T = {
    "ru": {
        "expired": "⏳ Сессия истекла (более 3 часов). Напишите нам, чтобы начать заново.",
        "cancelled": "❌ Бронирование отменено.\n\nЧтобы начать заново — просто напишите нам.",
        "no_hotels": "К сожалению, сейчас нет доступных отелей. Попробуйте позже.",
        "select_branch": "🏨 Выберите филиал — ответьте цифрой:",
        "branch_selected": "✅ Вы выбрали: *{name}*",
        "wrong_choice": "⚠️ Ответьте цифрой от 1 до {count}.",
        "ask_dates": (
            "📅 Напишите даты заезда и выезда через пробел:\n"
            "Формат: ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
            "Пример: 15.05.2026 17.05.2026\n\n"
            "Для отмены — напишите *Отмена*"
        ),
        "dates_bad_format": "⚠️ Напишите две даты через пробел.\nПример: 15.05.2026 17.05.2026",
        "dates_checkout_before": "⚠️ Дата выезда должна быть позже даты заезда.",
        "dates_past": "⚠️ Дата заезда не может быть в прошлом.",
        "dates_invalid": "⚠️ Неверный формат. Используйте ДД.ММ.ГГГГ\nПример: 15.05.2026 17.05.2026",
        "dates_confirmed": "✅ Даты:\n🛬 Заезд: {checkin}\n🛫 Выезд: {checkout}\n🌙 Ночей: {nights}\n\n👥 Сколько будет гостей? Напишите число.",
        "guests_invalid": "⚠️ Напишите число гостей от 1 до 20.",
        "no_rooms": "😔 Извините, в этом отеле нет доступных номеров.\nНапишите *Отмена*.",
        "select_room": "🛏 Выберите тип номера — ответьте цифрой:",
        "room_bath_private": "🚿 свой санузел",
        "room_bath_shared": "🚿 общий санузел",
        "ask_name": "✅ Отличный выбор!\n\n👤 Напишите ваше *имя и фамилию* через пробел.\nПример: Азат Мурзаев",
        "no_availability": "😔 Извините! Пока оформляли заявку, последние места уже забронировали.\nНапишите нам, чтобы выбрать другие даты.",
        "booking_confirmed": (
            "✅ *Заявка принята!*\n\n"
            "📋 Номер заявки: #{id}\n"
            "👤 Гость: {name}\n"
            "🛬 Заезд: {checkin}\n"
            "🛫 Выезд: {checkout}\n"
            "🌙 Ночей: {nights}\n"
            "👥 Гостей: {guests}\n\n"
            "Администратор скоро свяжется с вами для подтверждения. 🙏"
        ),
        "fallback": "Напишите нам, чтобы начать бронирование. 😊",
        "currency": "сом",
        "cancel_words": ("отмена", "cancel", "стоп", "stop"),
    },
    "en": {
        "expired": "⏳ Your session has expired (over 3 hours). Write us to start again.",
        "cancelled": "❌ Booking cancelled.\n\nWrite us anytime to start a new booking.",
        "no_hotels": "Sorry, no hotels available right now. Please try later.",
        "select_branch": "🏨 Select a branch — reply with a number:",
        "branch_selected": "✅ You selected: *{name}*",
        "wrong_choice": "⚠️ Please reply with a number from 1 to {count}.",
        "ask_dates": (
            "📅 Enter check-in and check-out dates separated by a space:\n"
            "Format: DD.MM.YYYY DD.MM.YYYY\n"
            "Example: 15.05.2026 17.05.2026\n\n"
            "To cancel — write *Cancel*"
        ),
        "dates_bad_format": "⚠️ Please enter two dates separated by a space.\nExample: 15.05.2026 17.05.2026",
        "dates_checkout_before": "⚠️ Check-out date must be after check-in date.",
        "dates_past": "⚠️ Check-in date cannot be in the past.",
        "dates_invalid": "⚠️ Invalid format. Use DD.MM.YYYY\nExample: 15.05.2026 17.05.2026",
        "dates_confirmed": "✅ Dates:\n🛬 Check-in: {checkin}\n🛫 Check-out: {checkout}\n🌙 Nights: {nights}\n\n👥 How many guests? Enter a number.",
        "guests_invalid": "⚠️ Please enter number of guests from 1 to 20.",
        "no_rooms": "😔 Sorry, no rooms available in this hotel.\nWrite *Cancel* to go back.",
        "select_room": "🛏 Select room type — reply with a number:",
        "room_bath_private": "🚿 private bathroom",
        "room_bath_shared": "🚿 shared bathroom",
        "ask_name": "✅ Great choice!\n\n👤 Please enter your *first and last name* separated by a space.\nExample: John Smith",
        "no_availability": "😔 Sorry! The last spots were just booked while we were processing.\nWrite us to choose different dates.",
        "booking_confirmed": (
            "✅ *Booking received!*\n\n"
            "📋 Booking #: #{id}\n"
            "👤 Guest: {name}\n"
            "🛬 Check-in: {checkin}\n"
            "🛫 Check-out: {checkout}\n"
            "🌙 Nights: {nights}\n"
            "👥 Guests: {guests}\n\n"
            "Our administrator will contact you shortly to confirm. 🙏"
        ),
        "fallback": "Write us to start a booking. 😊",
        "currency": "som",
        "cancel_words": ("cancel", "отмена", "stop"),
    },
}


def _t(session, key, **kwargs):
    """Get translated string for session language"""
    lang = getattr(session, 'lang', 'ru')
    text = T.get(lang, T['ru']).get(key, T['ru'].get(key, key))
    return text.format(**kwargs) if kwargs else text


def _send(phone, text, session=None):
    contact_id = session.data.get('contact_id', '') if session else ''
    import threading
    threading.Thread(target=send_wa_message, args=(phone, text, contact_id), daemon=True).start()


def _reset_session(session, keep_lang=False):
    contact_id = session.data.get('contact_id', '')
    lang = session.lang
    session.state = WhatsAppSession.State.START
    session.lang = WhatsAppSession.Lang.RU
    session.data = {}
    if contact_id:
        session.data['contact_id'] = contact_id
    if keep_lang:
        session.lang = lang
    session.save()


def _parse_date(s):
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {s}")


@atomic
def handle_message(phone: str, text: str, contact_id: str = ""):
    text = text.strip()
    session, created = WhatsAppSession.objects.get_or_create(phone=phone)

    # Всегда обновляем contact_id
    if contact_id and session.data.get('contact_id') != contact_id:
        session.data['contact_id'] = contact_id
        session.save()

    # Проверка истечения сессии
    if not created and session.state != WhatsAppSession.State.START:
        from django.utils import timezone
        if timezone.now() - session.updated_at > datetime.timedelta(hours=3):
            _reset_session(session)
            _send(phone, _t(session, 'expired'), session)
            return

    # Отмена
    if text.lower() in _t(session, 'cancel_words'):
        _reset_session(session)
        _send(phone, _t(session, 'cancelled'), session)
        return

    # Шаг 0 — выбор языка
    if session.state == WhatsAppSession.State.START:
        session.state = WhatsAppSession.State.AWAIT_LANG
        session.save()
        _send(phone,
            "👋 Здравствуйте! Выберите язык / Please select language:\n\n"
            "1️⃣ Русский\n"
            "2️⃣ English\n\n"
            "Reply with 1 or 2",
            session
        )
        return

    # Шаг 1 — обработка языка
    if session.state == WhatsAppSession.State.AWAIT_LANG:
        if text == '1':
            session.lang = WhatsAppSession.Lang.RU
        elif text == '2':
            session.lang = WhatsAppSession.Lang.EN
        else:
            _send(phone, "⚠️ Ответьте 1 или 2 / Please reply with 1 or 2", session)
            return
        session.save()
        _start_booking(phone, session)
        return

    # Дальнейшие шаги на выбранном языке
    if session.state == WhatsAppSession.State.AWAIT_BRANCH:
        _handle_branch(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_DATES:
        _handle_dates(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_GUESTS:
        _handle_guests(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_ROOM:
        _handle_room(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_NAME:
        _handle_name(phone, text, session)
    else:
        _reset_session(session)
        _send(phone, _t(session, 'fallback'), session)


def _start_booking(phone, session):
    branches = Branch.objects.filter(is_active=True).order_by('id')
    if not branches.exists():
        _send(phone, _t(session, 'no_hotels'), session)
        return

    if len(branches) == 1:
        b = branches[0]
        session.data['branch_id'] = b.id
        session.state = WhatsAppSession.State.AWAIT_DATES
        session.save()
        _send(phone,
            f"👋 {'Welcome to' if session.lang == 'en' else 'Добро пожаловать в'} *{b.name}*!\n\n"
            + _t(session, 'ask_dates'),
            session
        )
    else:
        lines = []
        mapping = {}
        for i, b in enumerate(branches, 1):
            mapping[str(i)] = b.id
            lines.append(f"{i}️⃣ {b.name}")
        session.data['branches'] = mapping
        session.state = WhatsAppSession.State.AWAIT_BRANCH
        session.save()
        msg = _t(session, 'select_branch') + "\n\n" + "\n".join(lines)
        _send(phone, msg, session)


def _handle_branch(phone, text, session):
    branch_id = session.data.get('branches', {}).get(text)
    if not branch_id:
        count = len(session.data.get('branches', {}))
        _send(phone, _t(session, 'wrong_choice', count=count), session)
        return
    branch_name = Branch.objects.filter(id=branch_id).values_list('name', flat=True).first()
    session.data['branch_id'] = branch_id
    session.state = WhatsAppSession.State.AWAIT_DATES
    session.save()
    _send(phone,
        _t(session, 'branch_selected', name=branch_name) + "\n\n" + _t(session, 'ask_dates'),
        session
    )


def _handle_dates(phone, text, session):
    parts = text.split()
    if len(parts) != 2:
        _send(phone, _t(session, 'dates_bad_format'), session)
        return
    try:
        checkin = _parse_date(parts[0])
        checkout = _parse_date(parts[1])
        if checkin >= checkout:
            _send(phone, _t(session, 'dates_checkout_before'), session)
            return
        if checkin < datetime.date.today():
            _send(phone, _t(session, 'dates_past'), session)
            return
    except ValueError:
        _send(phone, _t(session, 'dates_invalid'), session)
        return

    nights = (checkout - checkin).days
    session.data['checkin'] = str(checkin)
    session.data['checkout'] = str(checkout)
    session.state = WhatsAppSession.State.AWAIT_GUESTS
    session.save()
    _send(phone,
        _t(session, 'dates_confirmed',
           checkin=checkin.strftime('%d.%m.%Y'),
           checkout=checkout.strftime('%d.%m.%Y'),
           nights=nights),
        session
    )


def _handle_guests(phone, text, session):
    if not text.isdigit() or int(text) < 1 or int(text) > 20:
        _send(phone, _t(session, 'guests_invalid'), session)
        return

    guests = int(text)
    session.data['guests'] = guests

    rooms = Room.objects.filter(branch_id=session.data['branch_id'], is_active=True)
    if not rooms.exists():
        _send(phone, _t(session, 'no_rooms'), session)
        return

    types = set()
    mapping = {}
    idx = 1
    lines = []
    for r in rooms:
        if r.room_type not in types:
            types.add(r.room_type)
            mapping[str(idx)] = r.room_type
            bath = _t(session, 'room_bath_private') if r.has_bathroom else _t(session, 'room_bath_shared')
            currency = _t(session, 'currency')
            lines.append(f"{idx}️⃣ {r.get_room_type_display()}\n   💰 {r.price_per_night:.0f} {currency} · {bath}")
            idx += 1

    session.data['rooms_map'] = mapping
    session.state = WhatsAppSession.State.AWAIT_ROOM
    session.save()
    msg = _t(session, 'select_room') + "\n\n" + "\n\n".join(lines)
    _send(phone, msg, session)


def _handle_room(phone, text, session):
    room_type = session.data.get('rooms_map', {}).get(text)
    if not room_type:
        count = len(session.data.get('rooms_map', {}))
        _send(phone, _t(session, 'wrong_choice', count=count), session)
        return
    session.data['room_type'] = room_type
    session.state = WhatsAppSession.State.AWAIT_NAME
    session.save()
    _send(phone, _t(session, 'ask_name'), session)


def _handle_name(phone, text, session):
    parts = text.split(None, 1)
    name = parts[0]
    surname = parts[1] if len(parts) > 1 else ""

    branch_id = session.data['branch_id']
    checkin_obj = datetime.date.fromisoformat(session.data['checkin'])
    checkout_obj = datetime.date.fromisoformat(session.data['checkout'])
    guests_n = session.data['guests']
    r_type = session.data['room_type']

    from apps.rooms.views import _get_booked_guests
    booked_guests_by_type = _get_booked_guests(checkin_obj, checkout_obj, branch_id)
    current_booked = booked_guests_by_type.get(r_type, 0)
    rooms_of_type = Room.objects.filter(branch_id=branch_id, room_type=r_type, is_active=True)
    total_capacity = sum(r.capacity for r in rooms_of_type)

    if current_booked + guests_n > total_capacity:
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability'), session)
        return

    nights = (checkout_obj - checkin_obj).days
    b = Booking.objects.create(
        name=name,
        surname=surname,
        phone="+" + phone if not phone.startswith("+") else phone,
        country="Chat WhatsApp",
        purpose=Booking.Purpose.OTHER,
        source=Booking.Source.WHATSAPP,
        branch_id=branch_id,
        checkin=checkin_obj,
        checkout=checkout_obj,
        guests=guests_n,
        room=r_type,
        status=Booking.Status.PENDING
    )

    # Сохраняем язык до сброса сессии
    lang = session.lang
    _reset_session(session, keep_lang=True)

    # Сохраняем язык в данных бронирования для сигнала
    b.wa_lang = lang

    _send(phone,
        _t(session, 'booking_confirmed',
           id=b.id,
           name=f"{name} {surname}".strip(),
           checkin=checkin_obj.strftime('%d.%m.%Y'),
           checkout=checkout_obj.strftime('%d.%m.%Y'),
           nights=nights,
           guests=guests_n),
        session
    )

    try:
        from apps.bookings.views import _send_tg_notification
        _send_tg_notification(b)
    except Exception:
        pass


