"""
Management command to cancel stale unpaid orders and release their stock.
The window comes from GeneralConfig.auto_cancel_unpaid_hours (0 = disabled).
Usage: python manage.py cancel_unpaid_orders [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.common.models import GeneralConfig
from apps.orders.models import Order
from apps.orders.order_service import OrderService


class Command(BaseCommand):
    help = 'Cancel pending online-payment orders left unpaid past the configured window'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show how many orders would be cancelled without cancelling them',
        )

    def handle(self, *args, **options):
        hours = GeneralConfig.get_cached().auto_cancel_unpaid_hours
        if not hours:
            self.stdout.write('Auto-cancel is disabled (auto_cancel_unpaid_hours = 0)')
            return

        if options['dry_run']:
            cutoff = timezone.now() - timedelta(hours=hours)
            count = (
                Order.objects.filter(
                    status=Order.STATUS_PENDING,
                    payment_status=Order.PAYMENT_PENDING,
                    created_at__lt=cutoff,
                )
                .exclude(payment_method='pod')
                .count()
            )
            self.stdout.write(f'Would cancel {count} unpaid order(s) older than {hours}h')
            return

        cancelled, failed = OrderService.cancel_stale_unpaid_orders()
        self.stdout.write(
            self.style.SUCCESS(f'Cancelled {cancelled} order(s), {failed} failed')
        )
