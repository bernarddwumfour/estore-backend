"""
Management command to clean up old logs
Usage: python manage.py cleanup_logs --days 30
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.common.models import SystemLog


class Command(BaseCommand):
    help = 'Delete old system logs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to keep (default: 30)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_logs = SystemLog.objects.filter(created_at__lt=cutoff_date)
        count = old_logs.count()
        
        self.stdout.write(f"Found {count} logs older than {days} days")
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run - would delete {count} logs"))
            return
        
        if count > 0:
            old_logs.delete()
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {count} logs"))
        else:
            self.stdout.write(self.style.SUCCESS("No old logs to delete"))