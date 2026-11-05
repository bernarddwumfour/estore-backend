import logging

from django.core.management.base import BaseCommand

from apps.products.models import Product
from apps.ai_assistant.models import ProductEmbedding
from apps.ai_assistant.embeddings.indexer import index_product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate semantic embeddings for published products"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild all embeddings",
        )

    def handle(self, *args, **options):
        force = options["force"]

        if force:
            ProductEmbedding.objects.all().delete()

        product_ids = (
            Product.objects
            .filter(status=Product.STATUS_PUBLISHED)
            .order_by("id")
            .values_list("id", flat=True)
        )

        stats = {
            "indexed": 0,
            "unchanged": 0,
            "failed": 0,
        }

        for product_id in product_ids.iterator():
            try:
                result = index_product(str(product_id))
                status = result["status"]

                if status in stats:
                    stats[status] += 1

                self.stdout.write(
                    f"{product_id}: {status}"
                )

            except Exception:
                stats["failed"] += 1

                logger.exception(
                    "Failed indexing product %s",
                    product_id,
                )

                self.stderr.write(
                    f"Failed indexing product {product_id}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Indexed: {stats['indexed']}, "
                f"Unchanged: {stats['unchanged']}, "
                f"Failed: {stats['failed']}"
            )
        )