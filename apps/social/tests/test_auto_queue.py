from unittest.mock import patch

from django.test import TestCase

from apps.products.models import Product
from apps.products.services.product_service import AdminProductService, ProductService
from apps.products.tests.factories import make_admin, make_product, make_variant
from apps.promotions.services import PromotionService
from apps.promotions.tests.factories import make_promotion
from apps.social.models import SocialPost
from apps.social.services import SocialPostService
from apps.social.zernio_service import ZernioService


def configured(func):
    return patch.object(ZernioService, "API_KEY", "sk_test")(func)


class ProductPublishQueueTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    @configured
    def test_publish_transition_queues_pending_post(self):
        product = make_product(status=Product.STATUS_DRAFT)
        make_variant(product=product)

        with self.captureOnCommitCallbacks(execute=True):
            updated, error = AdminProductService.update_product(
                str(product.id), {"status": Product.STATUS_PUBLISHED}, self.admin
            )
        self.assertIsNone(error)

        post = SocialPost.objects.get()
        self.assertEqual(post.source, SocialPost.SOURCE_PRODUCT)
        self.assertEqual(post.object_id, product.id)
        self.assertEqual(post.status, SocialPost.STATUS_PENDING_APPROVAL)
        self.assertIn(product.title, post.caption)
        self.assertIn(f"/products/{product.slug}", post.caption)

    @configured
    def test_ordinary_edit_does_not_queue(self):
        product = make_product(status=Product.STATUS_DRAFT)
        with self.captureOnCommitCallbacks(execute=True):
            AdminProductService.update_product(
                str(product.id), {"description": "Updated"}, self.admin
            )
        self.assertEqual(SocialPost.objects.count(), 0)

    @configured
    def test_republish_does_not_queue_again(self):
        product = make_product(status=Product.STATUS_DRAFT)
        with self.captureOnCommitCallbacks(execute=True):
            AdminProductService.update_product(
                str(product.id), {"status": Product.STATUS_PUBLISHED}, self.admin
            )
        # already published (published_at set) — editing again must not re-queue
        with self.captureOnCommitCallbacks(execute=True):
            AdminProductService.update_product(
                str(product.id), {"status": Product.STATUS_PUBLISHED}, self.admin
            )
        self.assertEqual(SocialPost.objects.count(), 1)

    @configured
    def test_create_published_product_queues(self):
        from apps.products.tests.factories import make_category

        category = make_category()
        with self.captureOnCommitCallbacks(execute=True):
            product, error = AdminProductService.create_product(
                {
                    "title": "Fresh Kicks",
                    "description": "Nice shoes",
                    "category_id": str(category.id),
                    "status": Product.STATUS_PUBLISHED,
                },
                self.admin,
            )
        self.assertIsNone(error)
        self.assertEqual(
            SocialPost.objects.filter(object_id=product.id).count(), 1
        )

    @configured
    def test_bulk_publish_queues(self):
        product = make_product(status=Product.STATUS_DRAFT)
        with self.captureOnCommitCallbacks(execute=True):
            results, error = ProductService.bulk_action_products(
                [str(product.id)], "publish", self.admin
            )
        self.assertIsNone(error)
        self.assertEqual(SocialPost.objects.filter(object_id=product.id).count(), 1)

    def test_unconfigured_is_noop(self):
        product = make_product(status=Product.STATUS_DRAFT)
        with patch.object(ZernioService, "API_KEY", ""):
            with self.captureOnCommitCallbacks(execute=True):
                AdminProductService.update_product(
                    str(product.id), {"status": Product.STATUS_PUBLISHED}, self.admin
                )
        self.assertEqual(SocialPost.objects.count(), 0)

    @configured
    def test_queue_failure_never_breaks_publish(self):
        product = make_product(status=Product.STATUS_DRAFT)
        with patch(
            "apps.social.services.build_product_caption",
            side_effect=RuntimeError("boom"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                updated, error = AdminProductService.update_product(
                    str(product.id), {"status": Product.STATUS_PUBLISHED}, self.admin
                )
        self.assertIsNone(error)
        updated.refresh_from_db()
        self.assertEqual(updated.status, Product.STATUS_PUBLISHED)
        self.assertEqual(SocialPost.objects.count(), 0)


class PromotionActivateQueueTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    @configured
    def test_activation_queues_pending_post(self):
        promotion = make_promotion(status="draft")
        with self.captureOnCommitCallbacks(execute=True):
            success, error = PromotionService.activate_promotion(
                str(promotion.id), self.admin
            )
        self.assertTrue(success)

        post = SocialPost.objects.get()
        self.assertEqual(post.source, SocialPost.SOURCE_PROMOTION)
        self.assertEqual(post.object_id, promotion.id)
        self.assertEqual(post.status, SocialPost.STATUS_PENDING_APPROVAL)
        self.assertIn(promotion.name, post.caption)

    @configured
    def test_idempotent_when_pending_exists(self):
        promotion = make_promotion(status="draft")
        SocialPost.objects.create(
            source=SocialPost.SOURCE_PROMOTION,
            object_id=promotion.id,
            caption="existing",
            status=SocialPost.STATUS_PENDING_APPROVAL,
        )
        with self.captureOnCommitCallbacks(execute=True):
            PromotionService.activate_promotion(str(promotion.id), self.admin)
        self.assertEqual(SocialPost.objects.count(), 1)
