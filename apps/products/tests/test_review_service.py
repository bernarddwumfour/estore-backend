"""Unit tests for ReviewService.create_product_review business logic."""

from django.test import TestCase

from apps.products.models import Product, ProductReview
from apps.products.services.review_service import ReviewService
from .factories import make_user, make_product


class CreateProductReviewTests(TestCase):
    def setUp(self):
        self.user = make_user()
        # Reviews resolve products by slug and only published products are found.
        self.product = make_product(slug="reviewable", status=Product.STATUS_PUBLISHED)

    def test_create_review(self):
        review, error = ReviewService.create_product_review(
            user=self.user,
            product_slug="reviewable",
            rating=5,
            comment="Excellent!",
            title="Love it",
        )
        self.assertIsNone(error)
        self.assertIsNotNone(review)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.product, self.product)

    def test_duplicate_review_rejected(self):
        ReviewService.create_product_review(
            user=self.user, product_slug="reviewable", rating=4, comment="ok"
        )
        review, error = ReviewService.create_product_review(
            user=self.user, product_slug="reviewable", rating=3, comment="again"
        )
        self.assertIsNone(review)
        self.assertIn("review", error)

    def test_review_on_missing_product(self):
        review, error = ReviewService.create_product_review(
            user=self.user, product_slug="no-such-product", rating=5, comment="x"
        )
        self.assertIsNone(review)
        self.assertIn("product", error)

    def test_review_on_unpublished_product_not_found(self):
        make_product(slug="draft-product", status=Product.STATUS_DRAFT)
        review, error = ReviewService.create_product_review(
            user=self.user, product_slug="draft-product", rating=5, comment="x"
        )
        self.assertIsNone(review)
        self.assertIn("product", error)

    def test_title_truncated_to_200_chars(self):
        review, error = ReviewService.create_product_review(
            user=self.user,
            product_slug="reviewable",
            rating=4,
            comment="ok",
            title="x" * 300,
        )
        self.assertIsNone(error)
        self.assertEqual(len(review.title), 200)
