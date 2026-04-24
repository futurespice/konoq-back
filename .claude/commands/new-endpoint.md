# Добавить новый API endpoint

Добавь endpoint `$ARGUMENTS` строго по правилам проекта Konoq.

## Формат `$ARGUMENTS`:
`<module> <action> <description>`

Примеры:
- `bookings list список броней за период`
- `rooms create добавление комнаты`
- `finance monthly-revenue выручка по месяцам`

## Чеклист:

### 1. Думай перед кодом (Think Before Coding)
- Это GET или write? Нужен `atomic` + `select_for_update`?
- Публичный (`AllowAny`) или менеджеру (`IsAuthenticated`) или админу (`IsAdmin`)?
- Есть ли уже похожий endpoint — не дублируй.
- Если уточнение требуется (например: какая пагинация? какие фильтры?) — **спроси**, не угадывай.

### 2. Selector (если это GET со списком)
В `apps/<module>/selectors.py` добавь функцию:
```python
def get_<entity>_list(*, filters: dict, user: User) -> QuerySet:
    qs = <Model>.objects.select_related(...).prefetch_related(...)
    if filters.get("branch_id"):
        qs = qs.filter(branch_id=filters["branch_id"])
    return qs
```

Правила:
- keyword-only аргументы
- `select_related` / `prefetch_related` для FK
- Никакой HTTP-логики
- Возвращает `QuerySet`, не список — пагинация снаружи

### 3. Service (если это POST/PATCH/DELETE)
В `apps/<module>/services.py` добавь функцию:
```python
def create_<entity>(*, param1: int, param2: str, ...) -> <Model>:
    # Guard-проверки ДО atomic
    if param1 < 1:
        raise ValidationError(...)

    with transaction.atomic():
        # select_for_update на модели, которую блокируем от конкурентных изменений
        ...
        return <Model>.objects.create(...)
```

Правила:
- keyword-only аргументы
- `transaction.atomic()` если несколько write ИЛИ нужен `select_for_update`
- `ValidationError` ДО `atomic`, не внутри
- Никакой HTTP-логики

### 4. Serializer
В `apps/<module>/serializers.py`:
- **Input serializer** для валидации входящих данных (`<Entity>CreateSerializer`)
- **Output serializer** для ответа (`<Entity>ListSerializer` / `<Entity>DetailSerializer`)
- Не используй один serializer для input и output — их назначение разное.

### 5. Permission
В `apps/<module>/permissions.py` (создай если нет) или переиспользуй существующие:
- `IsAuthenticated` — менеджеры и админы
- `IsAdmin` (из `apps/users/permissions.py`) — только админ
- `AllowAny` — публично (только для чтения справочников и формы брони)

**Финансы (`apps/finance/`) → всегда `IsAdmin`.**

### 6. View
В `apps/<module>/views.py`:
```python
class <Entity>ListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["<module>"],
        summary="...",
        parameters=[
            OpenApiParameter("branch", OpenApiTypes.INT, description="..."),
        ],
        responses={200: <Entity>ListSerializer(many=True)},
    )
    def get(self, request):
        qs = get_<entity>_list(
            filters={"branch_id": request.query_params.get("branch")},
            user=request.user,
        )
        return Response(<Entity>ListSerializer(qs, many=True).data)
```

Правила:
- Только `permission_classes`, `serializer_class`, вызов service/selector
- `@extend_schema(tags=[...], summary=..., responses=...)` обязательно
- Никакой бизнес-логики в view

### 7. URL
В `apps/<module>/urls.py` добавь маршрут. Следуй существующему паттерну
(`BookingListView.as_view()`).

## Правила валидации:

- Числовые поля (`price`, `guests`, `capacity`): `if X is not None`, **не** `if X`
- Денежные поля: `DecimalField(max_digits=..., decimal_places=2)`
- Даты: проверка `checkin < checkout`, `checkin >= today`
- Пересечение дат: `checkin__lt=other.checkout AND checkout__gt=other.checkin`
- При write-операциях на брони → ВСЕГДА проверка доступности в `atomic` с
  `select_for_update` на Room

## Если endpoint меняет/создаёт бронь:
Читай `CLAUDE.md` секцию **"Race condition при бронировании"**. Проверка вместимости и
create — в одном `atomic` + `select_for_update` на `Room` этого branch+type.
