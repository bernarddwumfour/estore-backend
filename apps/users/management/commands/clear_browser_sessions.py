from django.core.management.base import BaseCommand
from apps.users.services.browser_session_service import clear_expired_sessions


class Command(BaseCommand):
    help = 'Delete expired BFF browser sessions; safe to run daily for each store.'

    def handle(self, *args, **options):
        count = clear_expired_sessions()
        self.stdout.write(f'Deleted {count} expired browser sessions.')
