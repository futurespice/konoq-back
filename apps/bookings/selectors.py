"""
apps/bookings/selectors.py

Read-only выборки по Booking. Без побочных эффектов, без transaction.
"""
from datetime import date

from django.db.models import Count, Q, QuerySet, Sum

from apps.rooms.models import Bed

from .models import Booking, BookingBed


def get_booked_guests_by_type(
    *,
    checkin: date,
    checkout: date,
    branch_id: int | None = None,
) -> dict[str, int]:
    """
    Суммарное число гостей в активных бронях, пересекающихся с периодом
    [checkin, checkout), по типу комнаты.

    Пересечение: `checkin__lt=checkout AND checkout__gt=checkin`.
    Активные статусы: pending + confirmed.
    """
    qs = Booking.objects.filter(
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        checkin__lt=checkout,
        checkout__gt=checkin,
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return {
        row["room"]: row["total_guests"]
        for row in qs.values("room").annotate(total_guests=Sum("guests"))
    }


def list_bookings(
    *,
    status: str | None = None,
    source: str | None = None,
    branch_id: int | str | None = None,
    search: str | None = None,
    checkin_from: date | str | None = None,
) -> QuerySet[Booking]:
    """QuerySet бронирований с фильтрами для списка менеджера."""
    qs = Booking.objects.select_related("branch")
    if status:
        qs = qs.filter(status=status)
    if source:
        qs = qs.filter(source=source)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(surname__icontains=search)
            | Q(phone__icontains=search)
            | Q(country__icontains=search)
        )
    if checkin_from:
        qs = qs.filter(checkin__gte=checkin_from)
    return qs


def get_booking_stats(*, branch_id: int | str | None = None) -> dict:
    """Один SQL-запрос вместо 4 count()."""
    qs = Booking.objects.all()
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        confirmed=Count("id", filter=Q(status=Booking.Status.CONFIRMED)),
        cancelled=Count("id", filter=Q(status=Booking.Status.CANCELLED)),
    )


def get_booking_by_id(*, pk: int) -> Booking | None:
    """Получить одну бронь с branch для деталей. None если не найдено."""
    try:
        return Booking.objects.select_related("branch").get(pk=pk)
    except Booking.DoesNotExist:
        return None


def get_available_beds(
    *,
    branch_id: int,
    checkin: date,
    checkout: date,
    room_type: str | None = None,
) -> QuerySet[Bed]:
    """
    Шконки свободные на период [checkin, checkout) в филиале.

    Исключает:
    - Bed с пересекающейся BookingBed активной брони (pending/confirmed)
    - все Bed комнаты, где есть активная is_private_booking бронь на эти даты
    - Bed.is_active=False и Room.is_active=False
    """
    active = [Booking.Status.PENDING, Booking.Status.CONFIRMED]

    busy_bed_ids = BookingBed.objects.filter(
        booking__status__in=active,
        checkin__lt=checkout,
        checkout__gt=checkin,
    ).values("bed_id")

    private_room_ids = BookingBed.objects.filter(
        booking__status__in=active,
        booking__is_private_booking=True,
        checkin__lt=checkout,
        checkout__gt=checkin,
    ).values("bed__room_id")

    qs = (
        Bed.objects
            .select_related("room")
            .filter(
                is_active=True,
                room__is_active=True,
                room__branch_id=branch_id,
            )
            .exclude(id__in=busy_bed_ids)
            .exclude(room_id__in=private_room_ids)
    )

    if room_type:
        qs = qs.filter(room__room_type=room_type)

    return qs


def get_availability_summary(
    *,
    branch_id: int,
    checkin: date,
    checkout: date,
) -> dict:
    """
    Сводка доступности по типам номеров в филиале на период [checkin, checkout).

    Группирует свободные Bed по room_type → по Room. Для каждой Room считает
    возможность забрать целиком и цену за всю комнату.
    """
    available = list(
        get_available_beds(
            branch_id=branch_id,
            checkin=checkin,
            checkout=checkout,
        )
    )

    by_room: dict[int, list] = {}
    for bed in available:
        by_room.setdefault(bed.room_id, []).append(bed)

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

    nights = (checkout - checkin).days
    by_type: dict[str, list] = {}

    for room_id, beds in by_room.items():
        room = beds[0].room
        total_active = totals.get(room_id, len(beds))
        can_whole = len(beds) == total_active and total_active > 0
        if can_whole:
            if room.price_is_per_bed:
                whole_price = room.price_per_night * total_active * nights
            else:
                whole_price = room.price_per_night * nights
        else:
            whole_price = None

        by_type.setdefault(room.room_type, []).append({
            "room_id": room.id,
            "room_number": room.number,
            "free_beds": len(beds),
            "beds": [{"id": b.id, "label": b.label} for b in beds],
            "price_per_bed_night": room.price_per_night,
            "can_take_whole_room": can_whole,
            "whole_room_price": whole_price,
        })

    types = [
        {
            "room_type": rt,
            "total_free_beds": sum(o["free_beds"] for o in opts),
            "options": opts,
        }
        for rt, opts in by_type.items()
    ]

    return {
        "branch_id": branch_id,
        "checkin": checkin,
        "checkout": checkout,
        "nights": nights,
        "types": types,
    }