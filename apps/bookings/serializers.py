"""
apps/bookings/serializers.py
"""
from rest_framework import serializers

from apps.rooms.models import Bed, Branch, Room

from .models import Booking
from .services import create_booking_with_capacity_check


class BookingCreateSerializer(serializers.ModelSerializer):
    """
    Публичный сериализатор — используется для создания бронирования с фронта.

    Фронт может отправить либо:
      - fullname: "Иван Иванов"  (одно поле — как сейчас в Booking-компоненте)
      - name + surname раздельно (старый формат / Swagger)

    Статус гость не передаёт — он всегда 'pending'.
    source передаётся опционально (для walk-in, telegram и т.д.).
    """
    fullname = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Полное имя (если отправляется одним полем вместо name+surname)",
    )

    class Meta:
        model  = Booking
        fields = [
            "fullname",
            "name", "surname",
            "phone", "email",
            "checkin", "checkout", "guests", "room",
            "country", "purpose",
            "source", "branch",
        ]
        extra_kwargs = {
            "name":    {"required": False, "allow_blank": True},
            "surname": {"required": False, "allow_blank": True},
            "purpose": {"required": False, "default": "other", "allow_blank": True},
            "source":  {"required": False},
            "branch":  {"required": False},
        }

    def validate(self, attrs):
        # ── fullname → name + surname ──────────────────────────────
        fullname = attrs.pop("fullname", None)
        if fullname:
            parts = fullname.strip().split(None, 1)
            attrs["name"]    = parts[0]
            attrs["surname"] = parts[1] if len(parts) > 1 else ""

        if not attrs.get("name"):
            raise serializers.ValidationError(
                {"fullname": "Укажите имя (поле fullname или name)."}
            )

        # ── Пустой purpose (фронт может прислать "") → значение по умолчанию ──────
        if not attrs.get("purpose"):
            attrs["purpose"] = "other"

        # ── Проверка дат ───────────────────────────────────────────
        if attrs["checkin"] >= attrs["checkout"]:
            raise serializers.ValidationError(
                {"checkout": "Дата выезда должна быть позже даты заезда."}
            )

        # ── Проверка кол-ва гостей ────────────────────────────────
        if attrs["guests"] < 1 or attrs["guests"] > 20:
            raise serializers.ValidationError(
                {"guests": "Количество гостей должно быть от 1 до 20."}
            )

        return attrs

    def create(self, validated_data):
        branch = validated_data.pop("branch", None)
        if branch is None:
            raise serializers.ValidationError(
                {"branch": "Укажите филиал."}
            )
        room_type = validated_data.pop("room", "")
        if not room_type:
            raise serializers.ValidationError(
                {"room": "Укажите тип номера."}
            )

        return create_booking_with_capacity_check(
            branch_id=branch.id,
            room_type=room_type,
            checkin=validated_data.pop("checkin"),
            checkout=validated_data.pop("checkout"),
            guests=validated_data.pop("guests"),
            name=validated_data.pop("name"),
            surname=validated_data.pop("surname", ""),
            phone=validated_data.pop("phone"),
            source=validated_data.pop("source", Booking.Source.DIRECT),
            **validated_data,
        )


class BookingListSerializer(serializers.ModelSerializer):
    """
    Список бронирований для дашборда менеджера — все поля + вычисляемые.
    """
    status_display  = serializers.CharField(source="get_status_display",  read_only=True)
    room_display    = serializers.CharField(source="get_room_display",     read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display",  read_only=True)
    source_display  = serializers.CharField(source="get_source_display",   read_only=True)
    branch_name     = serializers.CharField(source="branch.name",          read_only=True)
    nights          = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Booking
        fields = [
            "id",
            "name", "surname", "phone", "email",
            "checkin", "checkout", "nights", "guests",
            "room", "room_display",
            "comment",
            "country",
            "purpose", "purpose_display",
            "source", "source_display",
            "branch", "branch_name",
            "status", "status_display",
            "created_at", "updated_at",
        ]


class BookingStatusUpdateSerializer(serializers.ModelSerializer):
    """Только для менеджера — смена статуса бронирования."""
    class Meta:
        model  = Booking
        fields = ["status"]

    def validate_status(self, value):
        allowed = [Booking.Status.CONFIRMED, Booking.Status.CANCELLED, Booking.Status.PENDING]
        if value not in allowed:
            raise serializers.ValidationError("Недопустимый статус.")
        return value


class BookingStatsSerializer(serializers.Serializer):
    """Статистика для дашборда — только для Swagger документации."""
    total     = serializers.IntegerField()
    pending   = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    cancelled = serializers.IntegerField()


# ── Bed-level API v2 (Этап 2b) ───────────────────────────────────────────────

class BookingBedOutSerializer(serializers.Serializer):
    """Одна шконка в ответе брони."""
    id = serializers.IntegerField(source="bed.id", read_only=True)
    room_number = serializers.CharField(source="bed.room.number", read_only=True)
    room_type = serializers.CharField(source="bed.room.room_type", read_only=True)
    label = serializers.CharField(source="bed.label", read_only=True)
    price_per_night = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True,
    )


class BookingV2OutSerializer(serializers.ModelSerializer):
    """Ответ v2: бронь + привязанные шконки."""
    beds = BookingBedOutSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    nights = serializers.IntegerField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "status",
            "checkin", "checkout", "nights", "guests",
            "total_price", "is_private_booking",
            "branch", "branch_name",
            "beds",
        ]


class BookingPreviewSerializer(serializers.Serializer):
    """Вход для /v2/preview/ — только режим А (автоподбор без создания)."""
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    room_type = serializers.ChoiceField(choices=Room.RoomType.choices)
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    guests = serializers.IntegerField(min_value=1, max_value=20)
    want_private_room = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["checkin"] >= attrs["checkout"]:
            raise serializers.ValidationError(
                {"checkout": "Дата выезда должна быть позже даты заезда."}
            )
        return attrs


class BookingV2CreateSerializer(serializers.Serializer):
    """
    Вход для /v2/ — создание брони. Два взаимоисключающих режима:
      Режим А: room_type + guests (+ want_private_room) — автоподбор
      Режим Б: bed_ids — явный выбор шконок
    """
    # Гостевые поля
    fullname = serializers.CharField(required=False, allow_blank=True, write_only=True)
    name = serializers.CharField(required=False, allow_blank=True)
    surname = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    country = serializers.CharField()
    purpose = serializers.ChoiceField(
        choices=Booking.Purpose.choices,
        required=False,
        default=Booking.Purpose.OTHER,
    )
    comment = serializers.CharField(required=False, allow_blank=True)

    # Общие поля брони
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    source = serializers.ChoiceField(
        choices=Booking.Source.choices,
        required=False,
        default=Booking.Source.DIRECT,
    )

    # Режим А
    room_type = serializers.ChoiceField(
        choices=Room.RoomType.choices, required=False,
    )
    guests = serializers.IntegerField(
        required=False, min_value=1, max_value=20,
    )
    want_private_room = serializers.BooleanField(required=False, default=False)

    # Режим Б
    bed_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )

    def validate(self, attrs):
        fullname = attrs.pop("fullname", None)
        if fullname:
            parts = fullname.strip().split(None, 1)
            attrs["name"] = parts[0]
            attrs["surname"] = parts[1] if len(parts) > 1 else ""
        if not attrs.get("name"):
            raise serializers.ValidationError(
                {"fullname": "Укажите имя (поле fullname или name)."}
            )

        if not attrs.get("purpose"):
            attrs["purpose"] = Booking.Purpose.OTHER

        if attrs["checkin"] >= attrs["checkout"]:
            raise serializers.ValidationError(
                {"checkout": "Дата выезда должна быть позже даты заезда."}
            )

        has_a = bool(attrs.get("room_type")) and attrs.get("guests") is not None
        has_b = bool(attrs.get("bed_ids"))
        if has_a and has_b:
            raise serializers.ValidationError(
                "Передайте либо (room_type+guests), либо bed_ids — не оба сразу."
            )
        if not has_a and not has_b:
            raise serializers.ValidationError(
                "Укажите либо (room_type+guests), либо bed_ids."
            )

        if has_b:
            bed_ids = attrs["bed_ids"]
            if len(set(bed_ids)) != len(bed_ids):
                raise serializers.ValidationError(
                    {"bed_ids": "Дублирующиеся идентификаторы шконок."}
                )
            beds = list(
                Bed.objects.select_related("room").filter(id__in=bed_ids)
            )
            if len(beds) != len(bed_ids):
                raise serializers.ValidationError(
                    {"bed_ids": "Не все шконки найдены."}
                )
            branch = attrs["branch"]
            if any(b.room.branch_id != branch.id for b in beds):
                raise serializers.ValidationError(
                    {"bed_ids": "Все шконки должны принадлежать выбранному филиалу."}
                )
            modes = {b.room.price_is_per_bed for b in beds}
            if len(modes) > 1:
                raise serializers.ValidationError(
                    {"bed_ids": "Нельзя смешивать шконки дормов и приватных комнат."}
                )
            attrs["_beds"] = beds

        return attrs


class ICalLinkSerializer(serializers.ModelSerializer):
    """Сериализатор для работы со ссылками iCal (менеджер)."""
    room_type_display = serializers.CharField(source="get_room_type_display", read_only=True)
    source_display    = serializers.CharField(source="get_source_display",    read_only=True)
    branch_name       = serializers.CharField(source="branch.name",           read_only=True)

    class Meta:
        model  = __import__("apps.bookings.models", fromlist=["ICalLink"]).ICalLink
        fields = [
            "id", "branch", "branch_name",
            "room_type", "room_type_display",
            "url", "source", "source_display",
            "last_synced_at"
        ]
        read_only_fields = ["last_synced_at"]
