"""Unit tests for ProductVariant service (create) business logic."""

import json
import uuid
from decimal import Decimal

from django.http import JsonResponse
from django.test import RequestFactory, TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from apps.products.schemas import validate_variant_update
from apps.products.services.product_service import AdminProductService
from apps.products.services.variant_service import AdminVariantService
from apps.users.decorators.auth import multipart_request_allowed
from .factories import make_admin, make_product, make_variant


class CreateVariantTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def _data(self, **overrides):
        data = {
            "sku": f"SKU-{uuid.uuid4().hex[:6]}",
            "attributes": {},
            "price": Decimal("120.00"),
            "stock": 5,
        }
        data.update(overrides)
        return data

    def test_create_basic(self):
        product = make_product()
        variant, error = AdminVariantService.create_variant(
            str(product.id), self._data(), self.admin
        )
        self.assertIsNone(error)
        self.assertIsNotNone(variant)
        self.assertEqual(variant.product_id, product.id)
        self.assertEqual(variant.stock, 5)

    def test_first_variant_becomes_default(self):
        product = make_product()
        variant, error = AdminVariantService.create_variant(
            str(product.id), self._data(is_default=False), self.admin
        )
        self.assertIsNone(error)
        self.assertTrue(variant.is_default)

    def test_setting_new_default_unsets_previous(self):
        product = make_product()
        first = make_variant(product, is_default=True, sku="first")
        variant, error = AdminVariantService.create_variant(
            str(product.id), self._data(is_default=True), self.admin
        )
        self.assertIsNone(error)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(variant.is_default)

    def test_duplicate_sku_rejected(self):
        product = make_product()
        make_variant(product, sku="TAKEN")
        variant, error = AdminVariantService.create_variant(
            str(product.id), self._data(sku="TAKEN"), self.admin
        )
        self.assertIsNone(variant)
        self.assertIn("sku", error)

    def test_missing_product_rejected(self):
        variant, error = AdminVariantService.create_variant(
            str(uuid.uuid4()), self._data(), self.admin
        )
        self.assertIsNone(variant)
        self.assertIn("product", error)

    def test_attribute_must_match_product_options(self):
        product = make_product(options={"color": ["black", "white"]})
        variant, error = AdminVariantService.create_variant(
            str(product.id),
            self._data(attributes={"size": "L"}),
            self.admin,
        )
        self.assertIsNone(variant)
        self.assertTrue(any("size" in k for k in error.keys()))

    def test_valid_attribute_accepted(self):
        product = make_product(options={"color": ["black", "white"]})
        variant, error = AdminVariantService.create_variant(
            str(product.id),
            self._data(attributes={"color": "black"}),
            self.admin,
        )
        self.assertIsNone(error)
        self.assertEqual(variant.attributes, {"color": "black"})


class UpdateVariantTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_form_data_values_are_normalized_before_update(self):
        variant = make_variant(
            price=Decimal("100.00"),
            stock=10,
            is_default=True,
            is_active=True,
            low_stock_threshold=5,
            discount_amount=Decimal("0.00"),
            attributes={"color": "black"},
        )

        cleaned, errors = validate_variant_update(
            {
                "sku": "UPDATED-SKU",
                "price": "75.50",
                "stock": "3",
                "discount_amount": "5.25",
                "is_default": "false",
                "is_active": "false",
                "low_stock_threshold": "2",
                "attributes": {"color": "white"},
            },
            is_admin=True,
        )
        self.assertIsNone(errors)

        updated, service_errors = AdminProductService.update_variant(
            str(variant.id), cleaned, self.admin
        )
        self.assertIsNone(service_errors)
        self.assertEqual(updated.sku, "UPDATED-SKU")
        self.assertEqual(updated.price, Decimal("75.50"))
        self.assertEqual(updated.stock, 3)
        self.assertEqual(updated.discount_amount, Decimal("5.25"))
        self.assertFalse(updated.is_default)
        self.assertFalse(updated.is_active)
        self.assertEqual(updated.low_stock_threshold, 2)
        self.assertEqual(updated.attributes, {"color": "white"})


class MultipartRequestAllowedTests(TestCase):
    def test_put_multipart_body_is_parsed_into_json_data(self):
        @multipart_request_allowed
        def view(request):
            return JsonResponse({"data": request.json_data})

        request = RequestFactory().put(
            "/variants/example/update",
            encode_multipart(
                BOUNDARY,
                {
                    "sku": "UPDATED-SKU",
                    "price": "75.50",
                    "is_active": "false",
                    "attributes": json.dumps({"color": "white"}),
                },
            ),
            content_type=MULTIPART_CONTENT,
        )

        response = view(request)
        payload = json.loads(response.content)

        self.assertEqual(payload["data"]["sku"], "UPDATED-SKU")
        self.assertEqual(payload["data"]["price"], "75.50")
        self.assertEqual(payload["data"]["is_active"], "false")
        self.assertEqual(payload["data"]["attributes"], {"color": "white"})
