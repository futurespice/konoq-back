"""
apps/bookings/ical_views.py
"""
import datetime
import icalendar
import requests
import uuid
import logging
from django.http import HttpResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.bookings.models import Booking, ICalLink
from apps.rooms.models import Room
from apps.bookings.serializers import ICalLinkSerializer

logger = logging.getLogger(__name__)


class ICalLinkListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["ical"], summary="Список iCal ссылок менеджера", responses={200: ICalLinkSerializer(many=True)})
    def get(self, request):
        links = ICalLink.objects.all()
        return Response(ICalLinkSerializer(links, many=True).data)

    @extend_schema(tags=["ical"], summary="Добавить iCal ссылку", request=ICalLinkSerializer, responses={201: ICalLinkSerializer})
    def post(self, request):
        ser = ICalLinkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        link = ser.save()
        return Response(ICalLinkSerializer(link).data, status=status.HTTP_201_CREATED)


class ICalLinkDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return ICalLink.objects.get(pk=pk)
        except ICalLink.DoesNotExist:
            return None

    @extend_schema(tags=["ical"], summary="Удалить iCal ссылку", responses={204: None})
    def delete(self, request, pk):
        link = self._get(pk)
        if not link:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ICalExportView(APIView):
    """
    Экспорт календаря для Airbnb / Booking.com.
    Отдает .ics файл, где занятые дни помечены как недоступные.
    Публичный доступ без токена (т.к. агрегаторы не шлют Bearer токен).
    """
    permission_classes = [AllowAny]

    @extend_schema(tags=["ical"], summary="Скачать .ics календарь типа номера", responses={200: OpenApiResponse(description="Файл .ics")})
    def get(self, request, branch_id, room_type):
        from apps.bookings.selectors import get_booked_guests_by_type

        cal = icalendar.Calendar()
        cal.add('prodid', '-//Konoq Hostel Sync//konoq.com//')
        cal.add('version', '2.0')

        # We need to block dates where total_booked >= capacity.
        # Since we don't have a timeline model, we approximate by finding upcoming bookings 
        # and checking those specific dates.
        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=180) # Check next 6 months
        
        # Get capacity of this room type
        rooms = Room.objects.filter(branch_id=branch_id, room_type=room_type, is_active=True)
        total_capacity = sum(r.capacity for r in rooms)
        
        if total_capacity > 0:
            # We will iterate day-by-day (inefficient but accurate for hostels)
            # Find unavailable dates
            unavailable_dates = []
            curr = today
            while curr <= end_date:
                booked = get_booked_guests_by_type(
                    checkin=curr,
                    checkout=curr + datetime.timedelta(days=1),
                    branch_id=branch_id,
                )
                if booked.get(room_type, 0) >= total_capacity:
                    unavailable_dates.append(curr)
                curr += datetime.timedelta(days=1)
            
            # Group consecutive dates into single VEVENTs
            if unavailable_dates:
                start_block = unavailable_dates[0]
                prev_block = unavailable_dates[0]
                
                for i in range(1, len(unavailable_dates)):
                    current = unavailable_dates[i]
                    if (current - prev_block).days > 1:
                        # Break in block, export the previous block
                        event = icalendar.Event()
                        event.add('summary', 'Reserved (Konoq)')
                        event.add('dtstart', start_block)
                        event.add('dtend', prev_block + datetime.timedelta(days=1))
                        event.add('uid', str(uuid.uuid4()))
                        cal.add_component(event)
                        start_block = current
                    prev_block = current
                
                # Export the last block
                event = icalendar.Event()
                event.add('summary', 'Reserved (Konoq)')
                event.add('dtstart', start_block)
                event.add('dtend', prev_block + datetime.timedelta(days=1))
                event.add('uid', str(uuid.uuid4()))
                cal.add_component(event)

        response = HttpResponse(cal.to_ical(), content_type="text/calendar")
        response['Content-Disposition'] = f'attachment; filename="konoq_{branch_id}_{room_type}.ics"'
        return response


class ICalSyncView(APIView):
    """
    Принудительно скачивает .ics календари по всем ICalLink и создает Booking "заглушки".
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["ical"], summary="Принудительно синхронизировать все календари", responses={200: OpenApiResponse(description="Success")})
    def post(self, request):
        from apps.bookings.models import ICalLink
        from apps.bookings.services import create_ical_booking
        import django.utils.timezone as tz

        links = ICalLink.objects.all()
        synced_count = 0
        new_bookings = 0

        for link in links:
            try:
                resp = requests.get(link.url, timeout=10)
                if resp.status_code != 200:
                    continue

                cal = icalendar.Calendar.from_ical(resp.content)
                for component in cal.walk('vevent'):
                    dtstart = component.get('dtstart')
                    dtend = component.get('dtend')
                    if not dtstart or not dtend:
                        continue

                    start_date = dtstart.dt
                    end_date = dtend.dt

                    if isinstance(start_date, datetime.datetime):
                        start_date = start_date.date()
                    if isinstance(end_date, datetime.datetime):
                        end_date = end_date.date()

                    if start_date < datetime.date.today():
                        continue

                    uid = str(component.get('uid'))
                    created = create_ical_booking(
                        link_branch_id=link.branch_id,
                        room_type=link.room_type,
                        checkin=start_date,
                        checkout=end_date,
                        uid=uid,
                        source=link.source,
                        source_display=link.get_source_display(),
                    )
                    if created:
                        new_bookings += 1

                link.last_synced_at = tz.now()
                link.save()
                synced_count += 1
            except Exception as e:
                logger.error(f"ICal Sync error for {link.id}: {e}")

        return Response({
            "message": f"Синхронизация завершена: {synced_count} календарей обработано, {new_bookings} новых блокировок."
        })
