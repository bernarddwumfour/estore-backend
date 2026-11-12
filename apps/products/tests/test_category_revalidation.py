"""Product category changes refresh storefront category sections after commit."""

from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, override_settings

from apps.common.revalidation import capture_revalidation, revalidation_status
from apps.products.models import Category


@override_settings(
    STOREFRONT_BASE_URL="https://store.example",
    REVALIDATE_SECRET="test-secret",
)
class CategoryRevalidationTests(TestCase):
    @patch("apps.products.signals.notify_storefronts")
    def test_create_edit_and_delete_schedule_callbacks(self, notify):
        with self.captureOnCommitCallbacks(execute=True):
            category = Category.objects.create(name="SUVs", slug="suvs")
        notify.assert_called_once_with(
            ["https://store.example/api/revalidate/categories"], {}
        )

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            category.name = "SUV tyres"
            category.save()
        notify.assert_called_once()

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            category.delete()
        notify.assert_called_once()

    @override_settings(STOREFRONT_BASE_URL="")
    @patch("apps.products.signals.notify_storefronts")
    def test_unconfigured_callback_is_skipped(self, notify):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            Category.objects.create(name="Wheels", slug="wheels")
        self.assertEqual(callbacks, [])
        notify.assert_not_called()


@override_settings(
    STOREFRONT_BASE_URL="https://store.example",
    REVALIDATE_SECRET="test-secret",
)
class CategoryCallbackOutcomeTests(TransactionTestCase):
    @patch("apps.common.revalidation.requests.post")
    def test_edit_reports_accepted_callback(self, post):
        category = Category.objects.create(name="SUVs", slug="suvs")
        with capture_revalidation() as results:
            category.name = "SUV tyres"
            category.save()
        self.assertEqual(revalidation_status(results, configured=True), "accepted")
        post.assert_called()

    @patch("apps.common.revalidation.requests.post")
    def test_edit_reports_failed_callback(self, post):
        import requests

        category = Category.objects.create(name="SUVs", slug="suvs")
        post.side_effect = requests.Timeout("storefront unavailable")
        with capture_revalidation() as results:
            category.name = "SUV tyres"
            category.save()
        self.assertEqual(revalidation_status(results, configured=True), "failed")
