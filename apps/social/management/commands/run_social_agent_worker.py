"""Process durable social inbox events without a Redis broker."""
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from apps.social.models import SocialAgentMessage, SocialAgentWorker
from apps.social.tasks import flag_interrupted_social_messages, process_social_conversation


class Command(BaseCommand):
    help = "Process social agent messages from the database (without Redis)."

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=float, default=3)
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        interval = max(1, options['interval'])
        self.stdout.write('Social agent database worker started. Press Ctrl+C to stop.')
        try:
            while True:
                close_old_connections()
                SocialAgentWorker.objects.update_or_create(pk=1, defaults={})
                flag_interrupted_social_messages()
                threads = list(SocialAgentMessage.objects.filter(
                    status='pending', conversation__paused=False,
                ).order_by().values_list('conversation_id', flat=True).distinct()[:50])
                for thread_id in threads:
                    process_social_conversation.run(thread_id)
                    SocialAgentWorker.objects.update_or_create(pk=1, defaults={})
                if options['once']:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write('Social agent worker stopped.')
        finally:
            close_old_connections()
