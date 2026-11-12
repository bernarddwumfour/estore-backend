"""Public product routes accept stored product slugs containing tyre sizes."""

from django.test import SimpleTestCase, TestCase
from django.urls import resolve

from apps.products.models import Product
from .factories import make_product, make_variant


class ProductUrlTests(SimpleTestCase):
    def test_dotted_product_slug_reaches_detail_and_reviews(self):
        slug = "tyrepapa-12r22.5"
        paths = {
            f"/api/products/{slug}": "product-detail",
            f"/api/products/{slug}/reviews": "product-reviews-list",
            f"/api/products/{slug}/reviews/create": "product-review-create",
        }

        for path, name in paths.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.url_name, name)
                self.assertEqual(match.kwargs["slug"], slug)


class DottedProductDetailTests(TestCase):
    def test_detail_returns_the_variant_for_a_dotted_product_slug(self):
        product = make_product(
            slug="tyrepapa-12r22.5",
            status=Product.STATUS_PUBLISHED,
        )
        variant = make_variant(product=product, slug="tp-12r225-tri", is_default=True)

        response = self.client.get("/api/products/tyrepapa-12r22.5")

        self.assertEqual(response.status_code, 200)
        self.assertIn(variant.slug, [item["slug"] for item in response.json()["data"]["variants"]])
