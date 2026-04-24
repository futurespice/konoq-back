import logging
import datetime
import requests
import icalendar
from django.core.management.base import BaseCommand
import django.utils.timezone as tz
from apps.bookings.models import ICalLink
from apps.bookings.services import create_ical_booking

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Download all linked iCalendar files from OTA (Booking, Airbnb) and update bookings."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting iCal background synchronization..."))
        links = ICalLink.objects.all()
        synced_count = 0
        new_bookings = 0

        for link in links:
            try:
                resp = requests.get(link.url, timeout=15)
                if resp.status_code != 200:
                    self.stdout.write(self.style.ERROR(f"Failed to fetch {link.url} - Status {resp.status_code}"))
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
                self.stdout.write(self.style.ERROR(f"Error syncing link ID {link.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete. {synced_count} links processed. {new_bookings} new blocks imported."
        ))
