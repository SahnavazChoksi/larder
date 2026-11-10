"""Send scheduled alerts (missed checklists, out-of-stock items, critical issues left open).

Schedule it hourly:
  Linux/macOS cron:      0 * * * *  cd /path/to/backend && .venv/bin/python manage.py send_alerts
  Windows Task Scheduler: run  .venv\\Scripts\\python.exe manage.py send_alerts  every hour
Each alert is sent once per person, so running it often is safe.
"""
from django.core.management.base import BaseCommand

from ops.services import daily_alerts


class Command(BaseCommand):
    help = "Send scheduled Larder alerts to managers (in-app + email)."

    def handle(self, *args, **options):
        sent = daily_alerts()
        self.stdout.write(self.style.SUCCESS(f"{sent} notification(s) sent."))
