"""
apps/bookings/services.py

Единственная точка создания Booking. Все входы (сайт, WA-бот, iCal) проходят
через сервис с блокировкой комнат и проверкой вместимости в одной транзакции.
"""
import asyncio
import logging
import threading
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework.exceptions import ValidationError

from apps.rooms.models import Bed, Room
from .models import Booking, BookingBed
from .selectors import get_available_beds

logger = logging.getLogger(__name__)


def calculate_booking_price(
    *,
    room: Room,
    guests: int,
    nights: int,
) -> tuple[Decimal, Decimal]:
    """
    Возвращает (price_per_night, total_price).

    Для дормов (`price_is_per_bed=True`) цена умножается на число гостей.
    Ночей <0 считается как 0 — для защиты от некорректных дат.
    """
    per_night = (
        room.price_per_night * guests
        if room.price_is_per_bed
        else room.price_per_night
    )
    total = per_night * Decimal(max(nights, 0))
    return per_night, total


def create_booking_with_capacity_check(
    *,
    branch_id: int,
    room_type: str,
    checkin: date,
    checkout: date,
    guests: int,
    name: str,
    phone: str,
    surname: str = "",
    source: str = Booking.Source.DIRECT,
    status: str = Booking.Status.PENDING,
    **extra_fields,
) -> Booking:
    """
    Создание бронирования с защитой от race condition.

    1. Guard-проверки (даты, гости) — ДО transaction.atomic().
    2. Внутри транзакции: select_for_update() на Room(branch, room_type) →
       параллельные создатели встают в очередь.
    3. Пересчёт занятых мест по активным броням на пересекающихся датах.
    4. Если booked + guests > capacity → ValidationError ПОСЛЕ выхода из atomic
       (через raise — транзакция откатится, соединение чистое).

    extra_fields: email, comment, country, purpose, и т.п.
    """
    # ── Guard-проверки ДО atomic ────────────────────────────────────────
    if checkin >= checkout:
        raise ValidationError({"checkout": "Дата выезда должна быть позже даты заезда."})
    if checkin < date.today():
        raise ValidationError({"checkin": "Дата заезда не может быть в прошлом."})
    if guests < 1 or guests > 20:
        raise ValidationError({"guests": "Количество гостей должно быть от 1 до 20."})
    if not name:
        raise ValidationError({"name": "Имя обязательно."})

    # ── Критическая секция ──────────────────────────────────────────────
    with transaction.atomic():
        rooms = list(
            Room.objects
                .select_for_update()
                .filter(branch_id=branch_id, room_type=room_type, is_active=True)
        )
        if not rooms:
            raise ValidationError("Нет активных номеров этого типа.")

        total_capacity = sum(r.capacity for r in rooms)

        booked = (
            Booking.objects
                .filter(
                    branch_id=branch_id,
                    room=room_type,
                    status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
                    checkin__lt=checkout,
                    checkout__gt=checkin,
                )
                .aggregate(s=Sum("guests"))["s"]
            or 0
        )
        if booked + guests > total_capacity:
            raise ValidationError("Нет свободных мест на выбранные даты.")

        nights = (checkout - checkin).days
        per_night, total = calculate_booking_price(
            room=rooms[0], guests=guests, nights=nights,
        )

        booking = Booking.objects.create(
            branch_id=branch_id,
            room=room_type,
            checkin=checkin,
            checkout=checkout,
            guests=guests,
            name=name,
            surname=surname,
            phone=phone,
            source=source,
            status=status,
            price_per_night=per_night,
            total_price=total,
            **extra_fields,
        )
        _sync_bookingbeds_for_legacy_booking(booking)
        return booking


def create_ical_booking(
    *,
    link_branch_id: int,
    room_type: str,
    checkin: date,
    checkout: date,
    uid: str,
    source: str,
    source_display: str,
) -> Booking | None:
    """
    Идемпотентное создание брони-блокировки из внешнего iCal (Booking/Airbnb).

    Не проверяет вместимость: агрегатор уже продал этот юнит, наша задача —
    зафиксировать блок. Но создание идёт в atomic + select_for_update на Room,
    чтобы пересекающееся прямое создание встало в очередь за нами.

    Возвращает созданный Booking или None, если запись с этим UID уже есть.
    """
    with transaction.atomic():
        # Блокируем комнаты этого типа — прямое бронирование подождёт.
        list(
            Room.objects
                .select_for_update()
                .filter(branch_id=link_branch_id, room_type=room_type, is_active=True)
        )

        if Booking.objects.filter(comment__contains=uid).exists():
            return None

        return Booking.objects.create(
            name=f"Синхронизация {source_display}",
            surname="",
            phone="",
            checkin=checkin,
            checkout=checkout,
            guests=1,
            room=room_type,
            branch_id=link_branch_id,
            source=source,
            status=Booking.Status.CONFIRMED,
            comment=f"Auto-synced UID: {uid}",
            country="Неизвестно",
            purpose=Booking.Purpose.OTHER,
        )


def update_booking_status(*, booking_id: int, new_status: str) -> Booking:
    """
    Сменить статус брони. Поднимает Booking.DoesNotExist если не найдено.

    select_for_update() чтобы параллельный patch не перезаписал.
    WA-уведомление клиенту планируется через transaction.on_commit — если
    транзакция откатится, сообщение клиенту не уходит.
    """
    allowed = {
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.CANCELLED,
    }
    if new_status not in allowed:
        raise ValidationError({"status": "Недопустимый статус."})

    with transaction.atomic():
        booking = (
            Booking.objects
                .select_for_update()
                .select_related("branch")
                .get(id=booking_id)
        )
        old_status = booking.status
        if old_status != new_status:
            booking.status = new_status
            booking.save(update_fields=["status", "updated_at"])
            transaction.on_commit(
                lambda: _notify_whatsapp_on_status_change(
                    booking, old_status, new_status,
                )
            )
        return booking


def _wa_confirm_msg(lang: str, booking: Booking) -> str:
    branch_name = booking.branch.name if booking.branch_id else "Konoq"
    checkin = booking.checkin.strftime("%d.%m.%Y") if booking.checkin else ""
    checkout = booking.checkout.strftime("%d.%m.%Y") if booking.checkout else ""
    if lang == "en":
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


def _wa_cancel_msg(lang: str, booking: Booking) -> str:
    if lang == "en":
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


def _notify_whatsapp_on_status_change(
    booking: Booking,
    old_status: str,
    new_status: str,
) -> None:
    """
    Синхронно шлёт WA-уведомление клиенту при смене статуса брони.
    Вызывается через transaction.on_commit — БД уже закоммитила новый статус.

    Тихо выходит, если бронь не WHATSAPP-источника или сессия не найдена.
    Ошибки SendPulse логируются, не пробрасываются (колбэк on_commit не должен
    ронять внешний код).
    """
    if booking.source != Booking.Source.WHATSAPP:
        return

    # Ленивый импорт: wa_bot ссылается на bookings.services, избегаем цикла
    from apps.wa_bot.models import WhatsAppSession
    from apps.wa_bot.sendpulse_api import send_wa_message

    raw_phone = booking.phone or ""
    phone_key = raw_phone.lstrip("+")
    if not phone_key:
        return

    session = WhatsAppSession.objects.filter(phone=phone_key).first()
    if session is None:
        return

    contact_id = (session.data or {}).get("contact_id", "")
    lang = session.lang or "ru"

    if old_status != Booking.Status.CONFIRMED and new_status == Booking.Status.CONFIRMED:
        msg = _wa_confirm_msg(lang, booking)
    elif old_status != Booking.Status.CANCELLED and new_status == Booking.Status.CANCELLED:
        msg = _wa_cancel_msg(lang, booking)
    else:
        return

    try:
        send_wa_message(raw_phone, msg, contact_id)
    except Exception as exc:
        logger.error(
            "WA status-change notify failed booking=%s: %s", booking.id, exc,
        )


def delete_booking(*, booking_id: int) -> bool:
    """True если строка удалена, False если её не было."""
    deleted, _ = Booking.objects.filter(id=booking_id).delete()
    return deleted > 0


def notify_new_booking(booking: Booking) -> None:
    """
    Асинхронная отправка Telegram-уведомления владельцу о новой брони.

    NB: Текущая реализация — daemon-thread (антипаттерн, известный). При рестарте
    Gunicorn сообщение теряется. Заменить на очередь (Celery/RQ) — отдельная задача.
    """
    def _run():
        try:
            from apps.tg_bot.bot import notify_owner_new_booking
            asyncio.run(notify_owner_new_booking(booking))
        except Exception as exc:
            logger.warning("Не удалось отправить TG-уведомление: %s", exc)

    threading.Thread(target=_run, daemon=True).start()


def _sync_bookingbeds_for_legacy_booking(booking: Booking) -> None:
    """
    Адаптер Этапа 2: после создания брони старым путём (через
    create_booking_with_capacity_check) создать соответствующие BookingBed.
    Это двойная запись — старая схема (Booking.room + guests) + новые шконки —
    пока клиенты не переключились на /v2/.

    Best-effort: если свободных Bed меньше чем guests, бронь остаётся без
    BookingBed и пишется warning. Snoes на Этапе 3 когда все пишут через /v2/.
    """
    if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
        return
    if not booking.room or booking.beds.exists():
        return

    available = list(
        get_available_beds(
            branch_id=booking.branch_id,
            checkin=booking.checkin,
            checkout=booking.checkout,
            room_type=booking.room,
        )[:booking.guests]
    )
    if len(available) < booking.guests:
        logger.warning(
            "legacy booking %s: expected %d beds, got %d — BookingBed пропущен",
            booking.id, booking.guests, len(available),
        )
        return

    BookingBed.objects.bulk_create([
        BookingBed(
            booking=booking,
            bed=bed,
            checkin=booking.checkin,
            checkout=booking.checkout,
            price_per_night=bed.room.price_per_night,
        )
        for bed in available
    ])


# ── Bed-level сервисы (Этап 2a) ──────────────────────────────────────────────

def calculate_booking_total(
    *,
    beds: list[Bed],
    nights: int,
) -> Decimal:
    """
    Итоговая сумма брони по списку шконок.

    Дорм (price_is_per_bed=True): Σ bed.room.price_per_night × nights.
    Приватная (price_is_per_bed=False): room.price_per_night × nights — за всю
    комнату, НЕ умножая на число шконок.

    Контракт: все beds одного price_is_per_bed (валидируется в вызывающем сервисе).
    """
    if not beds:
        return Decimal("0")
    nights_d = Decimal(max(nights, 0))
    if beds[0].room.price_is_per_bed:
        total = Decimal("0")
        for b in beds:
            total += b.room.price_per_night
        return total * nights_d
    return beds[0].room.price_per_night * nights_d


def auto_assign_beds(
    *,
    branch_id: int,
    room_type: str,
    checkin: date,
    checkout: date,
    guests: int,
    want_private_room: bool = False,
) -> list[Bed]:
    """
    Автоматический подбор шконок под запрос.

    Guards ДО запросов. Не блокирует шконки — это делает create_booking_with_beds.
    """
    if checkin >= checkout:
        raise ValidationError({"checkout": "Дата выезда должна быть позже даты заезда."})
    if checkin < date.today():
        raise ValidationError({"checkin": "Дата заезда не может быть в прошлом."})
    if guests < 1:
        raise ValidationError({"guests": "Количество гостей должно быть не меньше 1."})

    available = list(
        get_available_beds(
            branch_id=branch_id,
            checkin=checkin,
            checkout=checkout,
            room_type=room_type,
        )
    )

    by_room: dict[int, list[Bed]] = {}
    for bed in available:
        by_room.setdefault(bed.room_id, []).append(bed)

    if want_private_room:
        totals = dict(
            Bed.objects
                .filter(
                    room_id__in=list(by_room.keys()),
                    is_active=True,
                    room__is_active=True,
                )
                .values("room_id")
                .annotate(total=Count("id"))
                .values_list("room_id", "total")
        )
        whole_rooms = [
            beds for room_id, beds in by_room.items()
            if len(beds) == totals.get(room_id, 0) and len(beds) >= guests
        ]
        if not whole_rooms:
            raise ValidationError("Нет свободных комнат целиком на эти даты.")
        whole_rooms.sort(key=len)
        return whole_rooms[0][:guests]

    sorted_rooms = sorted(by_room.values(), key=len, reverse=True)
    result: list[Bed] = []
    for free_beds in sorted_rooms:
        for bed in free_beds:
            result.append(bed)
            if len(result) >= guests:
                return result[:guests]
    raise ValidationError("Нет свободных мест на эти даты.")


def create_booking_with_beds(
    *,
    branch_id: int,
    beds: list[Bed],
    checkin: date,
    checkout: date,
    name: str,
    phone: str,
    is_private_booking: bool = False,
    surname: str = "",
    source: str = Booking.Source.DIRECT,
    status: str = Booking.Status.PENDING,
    **extra_fields,
) -> Booking:
    """
    Создать бронь на заданный список шконок.

    Guards ДО atomic. Внутри atomic: select_for_update на Bed, проверка
    пересечений, проверка is_private_booking, создание Booking + BookingBed.
    Snapshot Room.price_per_night в BookingBed.price_per_night.
    Для приватных комнат (price_is_per_bed=False) флаг is_private_booking
    игнорируется (пишется False) — см. §8.3 спеки.
    """
    if checkin >= checkout:
        raise ValidationError({"checkout": "Дата выезда должна быть позже даты заезда."})
    if not beds:
        raise ValidationError("Необходимо выбрать хотя бы одну шконку.")
    bed_ids = [b.id for b in beds]
    if len(set(bed_ids)) != len(bed_ids):
        raise ValidationError("Дублирующиеся шконки в списке.")
    if not name:
        raise ValidationError({"name": "Имя обязательно."})

    with transaction.atomic():
        locked = list(
            Bed.objects
                .select_for_update()
                .select_related("room")
                .filter(id__in=bed_ids, is_active=True, room__is_active=True)
        )
        if len(locked) != len(bed_ids):
            raise ValidationError("Одна или несколько шконок недоступны.")

        branches_of_beds = {b.room.branch_id for b in locked}
        if branches_of_beds != {branch_id}:
            raise ValidationError("Все шконки должны принадлежать одному филиалу.")

        per_bed_flags = {b.room.price_is_per_bed for b in locked}
        if len(per_bed_flags) != 1:
            raise ValidationError(
                "Нельзя смешивать шконки дормов и приватных комнат в одной брони."
            )
        is_dorm = next(iter(per_bed_flags))

        active = [Booking.Status.PENDING, Booking.Status.CONFIRMED]

        conflict = BookingBed.objects.filter(
            bed_id__in=bed_ids,
            booking__status__in=active,
            checkin__lt=checkout,
            checkout__gt=checkin,
        ).exists()
        if conflict:
            raise ValidationError("Одна или несколько шконок уже заняты на эти даты.")

        store_private = bool(is_private_booking) and is_dorm
        if store_private:
            room_ids = {b.room_id for b in locked}
            other_in_room = (
                BookingBed.objects
                    .filter(
                        bed__room_id__in=room_ids,
                        booking__status__in=active,
                        checkin__lt=checkout,
                        checkout__gt=checkin,
                    )
                    .exclude(bed_id__in=bed_ids)
                    .exists()
            )
            if other_in_room:
                raise ValidationError(
                    "Невозможно занять комнату целиком — есть другие брони."
                )

        booking = Booking.objects.create(
            name=name,
            surname=surname,
            phone=phone,
            branch_id=branch_id,
            checkin=checkin,
            checkout=checkout,
            guests=len(locked),
            source=source,
            status=status,
            is_private_booking=store_private,
            total_price=Decimal("0"),
            **extra_fields,
        )

        BookingBed.objects.bulk_create([
            BookingBed(
                booking=booking,
                bed=bed,
                checkin=checkin,
                checkout=checkout,
                price_per_night=bed.room.price_per_night,
            )
            for bed in locked
        ])

        nights = (checkout - checkin).days
        booking.total_price = calculate_booking_total(beds=locked, nights=nights)
        booking.save(update_fields=["total_price"])

        return booking
