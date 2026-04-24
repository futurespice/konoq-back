import datetime
import logging

from rest_framework.exceptions import ValidationError

from apps.bookings.models import Booking
from apps.bookings.selectors import get_availability_summary
from apps.bookings.services import (
    auto_assign_beds,
    calculate_booking_total,
    create_booking_with_beds,
)
from apps.rooms.models import Bed, Branch, Room

from .models import WhatsAppSession
from .sendpulse_api import send_wa_message

logger = logging.getLogger(__name__)

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
        "ask_private": (
            "🔑 Хотите забронировать комнату целиком (чужих не подсадят)?\n\n"
            "1️⃣ Да, приватно\n"
            "2️⃣ Нет, обычная бронь"
        ),
        "private_invalid": "⚠️ Ответьте 1 (да) или 2 (нет).",
        "select_room": "🛏 Выберите тип номера — ответьте цифрой:",
        "room_bath_private": "🚿 свой санузел",
        "room_bath_shared": "🚿 общий санузел",
        "preview_dorm": (
            "✨ Подобрали: комната №{room_number}, {n_beds} шконок(и).\n"
            "💰 Цена: {total} {currency} за {nights} ночей.\n\n"
            "1️⃣ Подтвердить\n"
            "2️⃣ Выбрать другую комнату\n"
            "3️⃣ Отмена"
        ),
        "preview_private": (
            "✨ Подобрали: вся комната №{room_number} ({n_beds} мест).\n"
            "💰 Цена: {total} {currency} за {nights} ночей.\n\n"
            "1️⃣ Подтвердить\n"
            "2️⃣ Выбрать другую комнату\n"
            "3️⃣ Отмена"
        ),
        "private_fallback": (
            "😔 Сейчас нет свободных комнат этого типа целиком на ваши даты.\n\n"
            "✨ Можете взять {n_beds} шконок(и) (обычный подбор):\n"
            "💰 {total} {currency} за {nights} ночей.\n\n"
            "1️⃣ Подтвердить\n"
            "2️⃣ Отмена"
        ),
        "no_availability_dates": "😔 На эти даты мест нет.\nНапишите нам, чтобы подобрать другие.",
        "choose_room": "🏠 Выберите комнату — ответьте цифрой:",
        "room_option": "{idx}️⃣ №{number} · свободно {free_beds}",
        "bed_confirm_invalid": "⚠️ Ответьте 1, 2 или 3.",
        "bed_confirm_invalid_2": "⚠️ Ответьте 1 или 2.",
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
        "ask_private": (
            "🔑 Want to book the whole room (no one else added)?\n\n"
            "1️⃣ Yes, private\n"
            "2️⃣ No, regular booking"
        ),
        "private_invalid": "⚠️ Reply 1 (yes) or 2 (no).",
        "select_room": "🛏 Select room type — reply with a number:",
        "room_bath_private": "🚿 private bathroom",
        "room_bath_shared": "🚿 shared bathroom",
        "preview_dorm": (
            "✨ We picked: room #{room_number}, {n_beds} bed(s).\n"
            "💰 Price: {total} {currency} for {nights} nights.\n\n"
            "1️⃣ Confirm\n"
            "2️⃣ Choose another room\n"
            "3️⃣ Cancel"
        ),
        "preview_private": (
            "✨ We picked: entire room #{room_number} ({n_beds} beds).\n"
            "💰 Price: {total} {currency} for {nights} nights.\n\n"
            "1️⃣ Confirm\n"
            "2️⃣ Choose another room\n"
            "3️⃣ Cancel"
        ),
        "private_fallback": (
            "😔 No whole rooms of this type are free on your dates.\n\n"
            "✨ You can take {n_beds} bed(s) (shared):\n"
            "💰 {total} {currency} for {nights} nights.\n\n"
            "1️⃣ Confirm\n"
            "2️⃣ Cancel"
        ),
        "no_availability_dates": "😔 No free spots on these dates.\nWrite us to try other dates.",
        "choose_room": "🏠 Pick a room — reply with a number:",
        "room_option": "{idx}️⃣ #{number} · {free_beds} free",
        "bed_confirm_invalid": "⚠️ Reply 1, 2 or 3.",
        "bed_confirm_invalid_2": "⚠️ Reply 1 or 2.",
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
    try:
        send_wa_message(phone, text, contact_id)
    except Exception as exc:
        logger.error("WA send failed phone=%s: %s", phone, exc)


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


def handle_message(phone: str, text: str, contact_id: str = ""):
    text = text.strip()
    session, created = WhatsAppSession.objects.get_or_create(phone=phone)

    if contact_id and session.data.get('contact_id') != contact_id:
        session.data['contact_id'] = contact_id
        session.save()

    if not created and session.state != WhatsAppSession.State.START:
        from django.utils import timezone
        if timezone.now() - session.updated_at > datetime.timedelta(hours=3):
            _reset_session(session)
            _send(phone, _t(session, 'expired'), session)
            return

    if text.lower() in _t(session, 'cancel_words'):
        _reset_session(session)
        _send(phone, _t(session, 'cancelled'), session)
        return

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

    if session.state == WhatsAppSession.State.AWAIT_BRANCH:
        _handle_branch(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_DATES:
        _handle_dates(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_GUESTS:
        _handle_guests(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_PRIVATE_CHOICE:
        _handle_private_choice(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_ROOM:
        _handle_room(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_BED_CONFIRM:
        _handle_bed_confirm(phone, text, session)
    elif session.state == WhatsAppSession.State.AWAIT_ROOM_CHOICE:
        _handle_room_choice(phone, text, session)
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

    rooms_exist = Room.objects.filter(
        branch_id=session.data['branch_id'], is_active=True,
    ).exists()
    if not rooms_exist:
        _send(phone, _t(session, 'no_rooms'), session)
        return

    if guests == 1:
        # Одному гостю приватность не нужна — пропускаем шаг
        session.data['want_private_room'] = False
        session.save()
        _show_room_types(phone, session)
        return

    session.state = WhatsAppSession.State.AWAIT_PRIVATE_CHOICE
    session.save()
    _send(phone, _t(session, 'ask_private'), session)


def _handle_private_choice(phone, text, session):
    if text == '1':
        session.data['want_private_room'] = True
    elif text == '2':
        session.data['want_private_room'] = False
    else:
        _send(phone, _t(session, 'private_invalid'), session)
        return
    session.save()
    _show_room_types(phone, session)


def _show_room_types(phone, session):
    rooms = Room.objects.filter(
        branch_id=session.data['branch_id'], is_active=True,
    )
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
            lines.append(
                f"{idx}️⃣ {r.get_room_type_display()}\n"
                f"   💰 {r.price_per_night:.0f} {currency} · {bath}"
            )
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
    session.save()

    _try_preview(phone, session, want_private=session.data.get('want_private_room', False))


def _try_preview(phone, session, *, want_private: bool):
    """Автоподбор + показ preview. На ValidationError — fallback или отказ."""
    branch_id = session.data['branch_id']
    room_type = session.data['room_type']
    checkin = datetime.date.fromisoformat(session.data['checkin'])
    checkout = datetime.date.fromisoformat(session.data['checkout'])
    guests = session.data['guests']
    nights = (checkout - checkin).days

    try:
        beds = auto_assign_beds(
            branch_id=branch_id, room_type=room_type,
            checkin=checkin, checkout=checkout, guests=guests,
            want_private_room=want_private,
        )
    except ValidationError:
        if want_private:
            _try_fallback_after_private_fail(
                phone, session,
                branch_id=branch_id, room_type=room_type,
                checkin=checkin, checkout=checkout,
                guests=guests, nights=nights,
            )
            return
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability_dates'), session)
        return

    total = calculate_booking_total(beds=beds, nights=nights)
    session.data['preview_bed_ids'] = [b.id for b in beds]
    session.data['preview_total'] = str(total)
    session.data['is_fallback'] = False
    session.state = WhatsAppSession.State.AWAIT_BED_CONFIRM
    session.save()

    room_number = beds[0].room.number
    key = 'preview_private' if want_private else 'preview_dorm'
    _send(phone,
        _t(session, key,
           room_number=room_number, n_beds=len(beds),
           total=f"{total:.0f}", currency=_t(session, 'currency'),
           nights=nights),
        session)


def _try_fallback_after_private_fail(
    phone, session, *,
    branch_id, room_type, checkin, checkout, guests, nights,
):
    """§8.5 вариант A: private не вышел → предложить обычный подбор."""
    try:
        beds = auto_assign_beds(
            branch_id=branch_id, room_type=room_type,
            checkin=checkin, checkout=checkout, guests=guests,
            want_private_room=False,
        )
    except ValidationError:
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability_dates'), session)
        return

    total = calculate_booking_total(beds=beds, nights=nights)
    session.data['preview_bed_ids'] = [b.id for b in beds]
    session.data['preview_total'] = str(total)
    session.data['is_fallback'] = True
    session.data['want_private_room'] = False
    session.state = WhatsAppSession.State.AWAIT_BED_CONFIRM
    session.save()

    _send(phone,
        _t(session, 'private_fallback',
           n_beds=len(beds), total=f"{total:.0f}",
           currency=_t(session, 'currency'), nights=nights),
        session)


def _handle_bed_confirm(phone, text, session):
    is_fallback = session.data.get('is_fallback', False)

    if is_fallback:
        if text not in ('1', '2'):
            _send(phone, _t(session, 'bed_confirm_invalid_2'), session)
            return
        if text == '1':
            session.state = WhatsAppSession.State.AWAIT_NAME
            session.save()
            _send(phone, _t(session, 'ask_name'), session)
            return
        # text == '2' — отмена
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'cancelled'), session)
        return

    if text not in ('1', '2', '3'):
        _send(phone, _t(session, 'bed_confirm_invalid'), session)
        return

    if text == '1':
        session.state = WhatsAppSession.State.AWAIT_NAME
        session.save()
        _send(phone, _t(session, 'ask_name'), session)
        return

    if text == '2':
        _show_room_choice(phone, session)
        return

    # text == '3' — отмена
    _reset_session(session, keep_lang=True)
    _send(phone, _t(session, 'cancelled'), session)


def _show_room_choice(phone, session):
    branch_id = session.data['branch_id']
    room_type = session.data['room_type']
    guests = session.data['guests']
    checkin = datetime.date.fromisoformat(session.data['checkin'])
    checkout = datetime.date.fromisoformat(session.data['checkout'])

    summary = get_availability_summary(
        branch_id=branch_id, checkin=checkin, checkout=checkout,
    )
    want_private = session.data.get('want_private_room', False)
    options = []
    for t in summary['types']:
        if t['room_type'] != room_type:
            continue
        for o in t['options']:
            if o['free_beds'] < guests:
                continue
            if want_private and not o['can_take_whole_room']:
                continue
            options.append(o)

    if not options:
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability_dates'), session)
        return

    mapping = {}
    lines = []
    for i, o in enumerate(options, 1):
        mapping[str(i)] = {
            'room_id': o['room_id'],
            'number': o['room_number'],
            'bed_ids': [b['id'] for b in o['beds']],
        }
        lines.append(_t(session, 'room_option',
                        idx=i, number=o['room_number'],
                        free_beds=o['free_beds']))

    session.data['room_choices'] = mapping
    session.state = WhatsAppSession.State.AWAIT_ROOM_CHOICE
    session.save()
    _send(phone, _t(session, 'choose_room') + "\n\n" + "\n".join(lines), session)


def _handle_room_choice(phone, text, session):
    choices = session.data.get('room_choices', {})
    choice = choices.get(text)
    if not choice:
        count = len(choices)
        _send(phone, _t(session, 'wrong_choice', count=count), session)
        return

    guests = session.data['guests']
    all_bed_ids = choice['bed_ids']
    if len(all_bed_ids) < guests:
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability_dates'), session)
        return

    bed_ids = all_bed_ids[:guests]
    checkin = datetime.date.fromisoformat(session.data['checkin'])
    checkout = datetime.date.fromisoformat(session.data['checkout'])
    nights = (checkout - checkin).days

    beds = list(Bed.objects.select_related('room').filter(id__in=bed_ids))
    total = calculate_booking_total(beds=beds, nights=nights)

    session.data['preview_bed_ids'] = bed_ids
    session.data['preview_total'] = str(total)
    session.data['is_fallback'] = False
    session.state = WhatsAppSession.State.AWAIT_BED_CONFIRM
    session.save()

    want_private = session.data.get('want_private_room', False)
    key = 'preview_private' if want_private else 'preview_dorm'
    _send(phone,
        _t(session, key,
           room_number=choice['number'], n_beds=len(bed_ids),
           total=f"{total:.0f}", currency=_t(session, 'currency'),
           nights=nights),
        session)


def _handle_name(phone, text, session):
    parts = text.split(None, 1)
    name = parts[0]
    surname = parts[1] if len(parts) > 1 else ""

    branch_id = session.data['branch_id']
    checkin_obj = datetime.date.fromisoformat(session.data['checkin'])
    checkout_obj = datetime.date.fromisoformat(session.data['checkout'])
    guests_n = session.data['guests']
    bed_ids = session.data.get('preview_bed_ids', [])

    beds = list(Bed.objects.select_related('room').filter(id__in=bed_ids))
    if len(beds) != len(bed_ids):
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability'), session)
        return

    is_private = session.data.get('want_private_room', False)

    try:
        b = create_booking_with_beds(
            branch_id=branch_id,
            beds=beds,
            checkin=checkin_obj,
            checkout=checkout_obj,
            name=name,
            surname=surname,
            phone="+" + phone if not phone.startswith("+") else phone,
            source=Booking.Source.WHATSAPP,
            country="Chat WhatsApp",
            purpose=Booking.Purpose.OTHER,
            status=Booking.Status.PENDING,
            is_private_booking=is_private,
        )
    except ValidationError:
        _reset_session(session, keep_lang=True)
        _send(phone, _t(session, 'no_availability'), session)
        return

    nights = (checkout_obj - checkin_obj).days
    lang = session.lang
    _reset_session(session, keep_lang=True)
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
        from apps.bookings.services import notify_new_booking
        notify_new_booking(b)
    except Exception:
        pass
