from django.core.cache import cache
from django.test import TestCase

from apps.common.models import GeneralConfig
from apps.products.schemas.validators import validate_variant_create
from apps.products.selectors.product_selectors import get_products_filtered
from apps.products.tests.factories import make_product, make_variant


def set_config(**overrides) -> GeneralConfig:
    config = GeneralConfig.get()
    for field, value in overrides.items():
        setattr(config, field, value)
    config.save()
    return config


class LowStockThresholdDefaultTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()

    def test_config_default_applies_when_omitted(self):
        set_config(default_low_stock_threshold=12)
        cleaned, errors = validate_variant_create({
            "sku": "SKU-TEST-1",
            "price": "50.00",
            "stock": 3,
        }, is_admin=True)
        self.assertIsNone(errors)
        self.assertEqual(cleaned["low_stock_threshold"], 12)

    def test_explicit_value_wins(self):
        set_config(default_low_stock_threshold=12)
        cleaned, errors = validate_variant_create({
            "sku": "SKU-TEST-2",
            "price": "50.00",
            "stock": 3,
            "low_stock_threshold": 2,
        }, is_admin=True)
        self.assertIsNone(errors)
        self.assertEqual(cleaned["low_stock_threshold"], 2)


class HideOutOfStockTests(TestCase):
    def setUp(self):
        cache.clear()
        GeneralConfig.get()
        self.in_stock = make_product(status="published")
        make_variant(product=self.in_stock, stock=5)
        self.out_of_stock = make_product(status="published")
        make_variant(product=self.out_of_stock, stock=0)

    def _public_ids(self, **kwargs):
        products, _total, _meta = get_products_filtered(**kwargs)
        return {p.id for p in products}

    def test_hidden_when_enabled(self):
        ids = self._public_ids()
        self.assertIn(self.out_of_stock.id, ids)

        set_config(hide_out_of_stock=True)
        ids = self._public_ids()
        self.assertIn(self.in_stock.id, ids)
        self.assertNotIn(self.out_of_stock.id, ids)

    def test_explicit_stock_filter_still_respected(self):
        set_config(hide_out_of_stock=True)
        ids = self._public_ids(in_stock=False)
        self.assertIn(self.out_of_stock.id, ids)
