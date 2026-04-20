import datetime
from django.db.transaction import atomic
from apps.rooms.models import Branch, Room
from apps.bookings.models import Booking
from .models import WhatsAppSession
from .sendpulse_api import send_wa_message

def _send(phone, text, session=None):
    contact_id = session.data.get('contact_id', '') if session else ''
    import threading
    threading.Thread(target=send_wa_message, args=(phone, text, contact_id), daemon=True).start()

def _reset_session(session):
    session.state = WhatsAppSession.State.START
    session.data = {}
    session.save()

@atomic
def handle_message(phone: str, text: str, contact_id: str = ""):
    text = text.strip()
    session, created = WhatsAppSession.objects.get_or_create(phone=phone)

    # Всегда обновляем contact_id если он пришёл
    if contact_id and session.data.get('contact_id') != contact_id:
        session.data['contact_id'] = contact_id
        session.save()

    if not created and session.state != WhatsAppSession.State.START:
        from django.utils import timezone
        diff = timezone.now() - session.updated_at
        if diff > datetime.timedelta(hours=3):
            _reset_session(session)
            _send(phone, "⏳ Ваша сессия истекла (прошло более 3 часов). Давайте начнем заново.", session)
            return

    if text.lower() in ("отмена", "cancel", "стоп"):
        _reset_session(session)
        _send(phone, "❌ Бронирование отменено.\n\nЧтобы начать заново — просто напишите нам.", session)
        return

    if session.state == WhatsAppSession.State.START:
        branches = Branch.objects.filter(is_active=True).order_by("id")
        if not branches.exists():
            _send(phone, "К сожалению, сейчас нет доступных отелей. Попробуйте позже.", session)
            return

        if len(branches) == 1:
            b = branches[0]
            session.data['branch_id'] = b.id
            session.state = WhatsAppSession.State.AWAIT_DATES
            session.save()
            _send(phone,
                f"👋 Здравствуйте! Добро пожаловать в *{b.name}*!\n\n"
                f"📅 Напишите даты заезда и выезда через пробел:\n"
                f"Формат: ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
                f"Пример: 15.05.2026 17.05.2026\n\n"
                f"Чтобы отменить — напишите *Отмена*",
                session
            )
        else:
            msg = "👋 Здравствуйте! Добро пожаловать!\n\n🏨 Выберите филиал — ответьте цифрой:\n\n"
            for i, b in enumerate(branches, 1):
                msg += f"{i}️⃣ {b.name}\n"
            session.data['branches'] = {str(i): b.id for i, b in enumerate(branches, 1)}
            session.state = WhatsAppSession.State.AWAIT_BRANCH
            session.save()
            _send(phone, msg, session)
        return

    elif session.state == WhatsAppSession.State.AWAIT_BRANCH:
        branch_id = session.data.get('branches', {}).get(text)
        if not branch_id:
            count = len(session.data.get('branches', {}))
            _send(phone, f"Пожалуйста, ответьте цифрой от 1 до {count}.", session)
            return

        branch_name = Branch.objects.filter(id=branch_id).values_list('name', flat=True).first()
        session.data['branch_id'] = branch_id
        session.state = WhatsAppSession.State.AWAIT_DATES
        session.save()
        _send(phone,
            f"✅ Вы выбрали: *{branch_name}*\n\n"
            f"📅 Напишите даты заезда и выезда через пробел:\n"
            f"Формат: ДД.ММ.ГГГГ ДД.ММ.ГГГГ\n"
            f"Пример: 15.05.2026 17.05.2026\n\n"
            f"Чтобы отменить — напишите *Отмена*",
            session
        )
        return

    elif session.state == WhatsAppSession.State.AWAIT_DATES:
        parts = text.split()
        if len(parts) != 2:
            _send(phone, "⚠️ Пожалуйста, напишите две даты через пробел.\nПример: 15.05.2026 17.05.2026", session)
            return
        try:
            def parse_date(s):
                for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
                    try:
                        return datetime.datetime.strptime(s, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"Неверный формат: {s}")

            checkin = parse_date(parts[0])
            checkout = parse_date(parts[1])
            if checkin >= checkout:
                _send(phone, "⚠️ Дата выезда должна быть позже даты заезда. Попробуйте ещё раз.", session)
                return
            if checkin < datetime.date.today():
                _send(phone, "⚠️ Дата заезда не может быть в прошлом. Попробуйте ещё раз.", session)
                return
        except ValueError:
            _send(phone, "⚠️ Не удалось распознать даты. Используйте формат ДД.ММ.ГГГГ\nПример: 15.05.2026 17.05.2026", session)
            return

        nights = (checkout - checkin).days
        session.data['checkin'] = str(checkin)
        session.data['checkout'] = str(checkout)
        session.state = WhatsAppSession.State.AWAIT_GUESTS
        session.save()
        _send(phone,
            f"✅ Даты:\n"
            f"🛬 Заезд: {checkin.strftime('%d.%m.%Y')}\n"
            f"🛫 Выезд: {checkout.strftime('%d.%m.%Y')}\n"
            f"🌙 Ночей: {nights}\n\n"
            f"👥 Сколько будет гостей? Напишите число.",
            session
        )
        return

    elif session.state == WhatsAppSession.State.AWAIT_GUESTS:
        if not text.isdigit() or int(text) < 1 or int(text) > 20:
            _send(phone, "⚠️ Пожалуйста, напишите число гостей от 1 до 20.", session)
            return

        guests = int(text)
        session.data['guests'] = guests

        rooms = Room.objects.filter(branch_id=session.data['branch_id'], is_active=True)
        if not rooms.exists():
            _send(phone, "😔 Извините, в этом отеле сейчас нет доступных номеров.\n\nНапишите *Отмена* и попробуйте другой филиал.", session)
            return

        types = set()
        mapping = {}
        idx = 1
        lines = []
        for r in rooms:
            if r.room_type not in types:
                types.add(r.room_type)
                mapping[str(idx)] = r.room_type
                bath = "🚿 свой санузел" if r.has_bathroom else "🚿 общий санузел"
                lines.append(f"{idx}️⃣ {r.get_room_type_display()}\n   💰 {r.price_per_night:.0f} сом/ночь · {bath}")
                idx += 1

        room_list_msg = "🛏 Выберите тип номера — ответьте цифрой:\n\n" + "\n\n".join(lines)
        session.data['rooms_map'] = mapping
        session.state = WhatsAppSession.State.AWAIT_ROOM
        session.save()
        _send(phone, room_list_msg, session)
        return

    elif session.state == WhatsAppSession.State.AWAIT_ROOM:
        room_type = session.data.get('rooms_map', {}).get(text)
        if not room_type:
            count = len(session.data.get('rooms_map', {}))
            _send(phone, f"⚠️ Пожалуйста, ответьте цифрой от 1 до {count}.", session)
            return

        session.data['room_type'] = room_type
        session.state = WhatsAppSession.State.AWAIT_NAME
        session.save()
        _send(phone,
            f"✅ Отличный выбор!\n\n"
            f"👤 Напишите ваше *имя и фамилию* через пробел.\n"
            f"Пример: Азат Муrzaev",
            session
        )
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
            _send(phone, "😔 Извините! Пока оформляли заявку, последние места уже забронировали.\n\nНапишите нам чтобы выбрать другие даты или номер.", session)
            return

        nights = (checkout_obj - checkin_obj).days
        b = Booking.objects.create(
            name=name,
            surname=surname,
            phone="+" + phone if not phone.startswith("+") else phone,
            country="Чат WhatsApp",
            purpose=Booking.Purpose.OTHER,
            source=Booking.Source.WHATSAPP,
            branch_id=branch_id,
            checkin=checkin_obj,
            checkout=checkout_obj,
            guests=guests_n,
            room=r_type,
            status=Booking.Status.PENDING
        )

        _reset_session(session)
        _send(phone,
            f"✅ *Заявка принята!*\n\n"
            f"📋 Номер заявки: #{b.id}\n"
            f"👤 Гость: {name} {surname}\n"
            f"🛬 Заезд: {checkin_obj.strftime('%d.%m.%Y')}\n"
            f"🛫 Выезд: {checkout_obj.strftime('%d.%m.%Y')}\n"
            f"🌙 Ночей: {nights}\n"
            f"👥 Гостей: {guests_n}\n\n"
            f"Администратор скоро свяжется с вами для подтверждения. 🙏",
            session
        )

        try:
            from apps.bookings.views import _send_tg_notification
            _send_tg_notification(b)
        except Exception:
            pass
        return

    _reset_session(session)
    _send(phone, "Напишите нам, чтобы начать бронирование. 😊", session)
