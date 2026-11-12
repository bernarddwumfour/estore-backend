"""Catalog changes refresh product caches without reacting to order stock writes."""

from unittest.mock import patch

import requests
from django.test import TestCase, override_settings

from apps.products.models import Product, VariantImage
from apps.products.revalidation import notify_product_change
from .factories import make_category, make_product, make_variant


@override_settings(
    STOREFRONT_BASE_URL="https://store.example",
    REVALIDATE_SECRET="test-secret",
)
class ProductRevalidationTests(TestCase):
    def setUp(self):
        embedding_refresh = patch("apps.ai_assistant.signals.schedule_refresh")
        embedding_refresh.start()
        self.addCleanup(embedding_refresh.stop)

    @patch("apps.products.revalidation.notify_product_change")
    def test_publish_edit_move_archive_and_delete(self, notify):
        product = make_product(status=Product.STATUS_DRAFT)

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            product.title = "Draft edit"
            product.save()
        self.assertEqual(callbacks, [])

        with self.captureOnCommitCallbacks(execute=True):
            product.status = Product.STATUS_PUBLISHED
            product.save()
        notify.assert_called_once_with(True)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            product.title = "Published edit"
            product.save()
        notify.assert_called_once_with(False)

        notify.reset_mock()
        new_category = make_category()
        with self.captureOnCommitCallbacks(execute=True):
            product.category = new_category
            product.save()
        notify.assert_called_once_with(True)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            product.status = Product.STATUS_ARCHIVED
            product.save()
        notify.assert_called_once_with(True)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            product.delete()
        notify.assert_not_called()

    @patch("apps.products.revalidation.notify_product_change")
    def test_deleting_published_product_refreshes_counts(self, notify):
        product = make_product(status=Product.STATUS_PUBLISHED)
        with self.captureOnCommitCallbacks(execute=True):
            product.delete()
        notify.assert_called_once_with(True)

    @patch("apps.products.revalidation.notify_product_change")
    def test_variant_and_image_changes_refresh_product_list(self, notify):
        product = make_product(status=Product.STATUS_PUBLISHED)
        with self.captureOnCommitCallbacks(execute=True):
            variant = make_variant(product=product)
        notify.assert_called_once_with(False)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            variant.price = 125
            variant.save()
        notify.assert_called_once_with(False)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            image = VariantImage.objects.create(variant=variant, image="products/test.jpg")
        notify.assert_called_once_with(False)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            image.delete()
        notify.assert_called_once_with(False)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            variant.delete()
        notify.assert_called_once_with(False)

    @patch("apps.products.revalidation.notify_product_change")
    def test_order_stock_update_does_not_trigger_callback(self, notify):
        variant = make_variant(product=make_product(status=Product.STATUS_PUBLISHED), stock=10)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            variant.reduce_stock(1)
        self.assertEqual(callbacks, [])
        notify.assert_not_called()

    @patch("apps.products.revalidation.notify_product_change")
    def test_stock_crossing_zero_refreshes_listings(self, notify):
        variant = make_variant(product=make_product(status=Product.STATUS_PUBLISHED), stock=1)
        with self.captureOnCommitCallbacks(execute=True):
            variant.reduce_stock(1)
        notify.assert_called_once_with(False)

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            variant.increase_stock(1)
        notify.assert_called_once_with(False)

    @patch("apps.common.revalidation.requests.post")
    def test_failed_storefront_callback_does_not_raise(self, post):
        post.side_effect = requests.Timeout("storefront unavailable")
        notify_product_change(categories_changed=True)
        post.assert_called_once_with(
            "https://store.example/api/revalidate/products",
            json={"categories_changed": True},
            headers={"Authorization": "Bearer test-secret"},
            timeout=3,
        )
