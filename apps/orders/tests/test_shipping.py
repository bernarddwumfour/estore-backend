import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase

from apps.orders.models import Order, ShippingConfig
from apps.orders.order_service import OrderService
from apps.orders.schemas.shipping_schemas import validate_shipping_config_update
from apps.orders.shipping_calculator import ShippingCalculator
from apps.orders.shipping_quote_service import ShippingQuoteService
from apps.orders.terminal_africa_service import TerminalAfricaService
from apps.orders.tests.factories import (
    TA_RATES,
    make_admin,
    make_product,
    make_shipping_config,
    make_user,
    make_variant,
    shipping_address_data,
)


from apps.users.utils.token_utils import generate_jwt_token


def make_published_variant(**kwargs):
    product = make_product(status="published")
    return make_variant(product=product, **kwargs)


def ta_configured(func):
    return patch.object(TerminalAfricaService, "API_KEY", "sk_ta_test")(func)


def ta_unconfigured(func):
    return patch.object(TerminalAfricaService, "API_KEY", "")(func)


class ShippingConfigModelTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_singleton_and_seeded_defaults(self):
        config = ShippingConfig.get()
        again = ShippingConfig.get()
        self.assertEqual(config.pk, 1)
        self.assertEqual(again.pk, 1)
        self.assertEqual(ShippingConfig.objects.count(), 1)
        self.assertIn("DEFAULT", config.fallback_rates)
        self.assertEqual(config.fallback_rates["GH"]["base"], "15.00")
        self.assertIn("standard", config.shipping_methods)
        self.assertTrue(config.use_carrier_rates)
        self.assertFalse(config.free_shipping_all)

    def test_cache_invalidated_on_save(self):
        config = ShippingConfig.get_cached()
        self.assertFalse(config.pickup_enabled)
        make_shipping_config(pickup_enabled=True)
        self.assertTrue(ShippingConfig.get_cached().pickup_enabled)


class ShippingCalculatorTests(TestCase):
    def setUp(self):
        cache.clear()
        ShippingConfig.get()

    def test_full_country_name_normalized_to_gh_rates(self):
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="Ghana", total_weight_kg=Decimal("1"), subtotal=Decimal("100"),
        )
        # GH: base 15 + 1kg*5 = 20 (not DEFAULT's 30+10=40)
        self.assertEqual(result["cost"], Decimal("20.00"))

    def test_per_country_threshold_free(self):
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("600"),
        )
        self.assertEqual(result["cost"], Decimal("0.00"))

    def test_global_threshold_overrides(self):
        make_shipping_config(free_shipping_threshold=Decimal("50"))
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("60"),
        )
        self.assertEqual(result["cost"], Decimal("0.00"))

    def test_free_shipping_all(self):
        make_shipping_config(free_shipping_all=True)
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="US", total_weight_kg=Decimal("10"), subtotal=Decimal("5"),
        )
        self.assertEqual(result["cost"], Decimal("0.00"))
        self.assertIn("all orders", result["reason"])

    def test_zero_thresholds_are_disabled_not_free(self):
        make_shipping_config(
            free_shipping_threshold=Decimal("0"),
            fallback_rates={
                "GH": {"base": "15.00", "per_kg": "5.00", "free_shipping_threshold": "0"},
                "DEFAULT": {"base": "30.00", "per_kg": "10.00", "free_shipping_threshold": "0"},
            },
        )
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("100"),
        )
        self.assertEqual(result["cost"], Decimal("20.00"))

    def test_free_reasons_distinguish_rules(self):
        make_shipping_config(free_shipping_threshold=Decimal("50"))
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("60"),
        )
        self.assertIn("GHS 50", result["reason"])

        make_shipping_config(free_shipping_threshold=None)
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("600"),
        )
        self.assertIn("GH rate rule", result["reason"])

    def test_config_driven_rates(self):
        make_shipping_config(fallback_rates={
            "GH": {"base": "9.00", "per_kg": "1.00", "free_shipping_threshold": "1000"},
            "DEFAULT": {"base": "50.00", "per_kg": "5.00", "free_shipping_threshold": "1000"},
        })
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("2"), subtotal=Decimal("100"),
        )
        self.assertEqual(result["cost"], Decimal("11.00"))

    def test_malformed_config_falls_back_to_defaults(self):
        make_shipping_config(fallback_rates={"GH": {"base": "not-a-number"}})
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("100"),
        )
        self.assertEqual(result["cost"], Decimal("20.00"))

    def test_express_multiplier(self):
        result = ShippingCalculator.calculate_shipping_cost(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("100"),
            shipping_method="express",
        )
        self.assertEqual(result["cost"], Decimal("40.00"))

    def test_disabled_methods_hidden_from_options(self):
        make_shipping_config(shipping_methods={
            "standard": {"name": "Standard Shipping", "multiplier": "1.0",
                         "estimated_days": "3-7 business days", "enabled": True},
            "express": {"name": "Express Shipping", "multiplier": "2.0",
                        "estimated_days": "1-3 business days", "enabled": False},
        })
        options = ShippingCalculator.get_shipping_options(
            country_code="GH", total_weight_kg=Decimal("1"), subtotal=Decimal("100"),
        )
        self.assertEqual([o["id"] for o in options], ["standard"])


class ConfigValidatorTests(TestCase):
    def test_happy_partial_update(self):
        cleaned, errors = validate_shipping_config_update({
            "pickup_enabled": True,
            "free_shipping_threshold": "250.00",
            "popular_addresses": [
                {"name": "University of Ghana - Legon", "region": "Greater Accra",
                 "country": "gh", "price": "0.00"},
            ],
        })
        self.assertIsNone(errors)
        self.assertTrue(cleaned["pickup_enabled"])
        self.assertEqual(cleaned["free_shipping_threshold"], Decimal("250.00"))
        addr = cleaned["popular_addresses"][0]
        self.assertEqual(addr["country"], "GH")
        self.assertTrue(addr["id"])
        self.assertTrue(addr["active"])

    def test_rejections(self):
        cases = [
            ({"free_shipping_threshold": "abc"}, "free_shipping_threshold"),
            ({"free_shipping_threshold": "0"}, "free_shipping_threshold"),
            ({"handling_fee": "-2"}, "handling_fee"),
            ({"fallback_surcharge_percent": "150"}, "fallback_surcharge_percent"),
            ({"fallback_rates": {"GH": {"base": "1", "per_kg": "1"}}}, "fallback_rates"),
            ({"allowed_countries": [{"code": "GHA", "name": "Ghana"}]}, "allowed_countries"),
            ({"shipping_methods": {}}, "shipping_methods"),
            ({"shipping_methods": {"standard": {"name": "S", "multiplier": "0"}}}, "shipping_methods"),
            ({"shipping_methods": {"standard": {"name": "S", "multiplier": "1", "enabled": False}}}, "shipping_methods"),
            ({"popular_addresses": [{"name": "X", "region": "", "country": "GH"}]}, "popular_addresses"),
            ({"pickup_enabled": "yes"}, "pickup_enabled"),
            ({}, "general"),
        ]
        for payload, field in cases:
            cleaned, errors = validate_shipping_config_update(payload)
            self.assertIsNone(cleaned, payload)
            self.assertIn(field, errors, payload)

    def test_duplicate_popular_address_ids_rejected(self):
        cleaned, errors = validate_shipping_config_update({
            "popular_addresses": [
                {"id": "a1", "name": "X", "region": "R", "country": "GH"},
                {"id": "a1", "name": "Y", "region": "R", "country": "GH"},
            ]
        })
        self.assertIsNone(cleaned)
        self.assertIn("popular_addresses", errors)


class ResolveSelectedOptionTests(TestCase):
    def setUp(self):
        cache.clear()
        ShippingConfig.get()
        self.destination = {
            "country": "Ghana", "state": "Greater Accra", "city": "Accra",
            "postal_code": "00233", "address": "12 Osu Lane",
        }

    def _resolve(self, method_id="", popular_id="", subtotal=Decimal("100")):
        return ShippingQuoteService.resolve_selected_option(
            shipping_method_id=method_id,
            popular_address_id=popular_id,
            destination=self.destination,
            items=[],
            subtotal=subtotal,
            total_weight=Decimal("1"),
        )

    def test_country_gate_blocks_unlisted_destination(self):
        make_shipping_config(allowed_countries=[{"code": "NG", "name": "Nigeria"}])
        result, error = self._resolve()
        self.assertIsNone(result)
        self.assertIn("shipping_address", error)

    def test_country_gate_allows_listed_and_empty(self):
        result, error = self._resolve()
        self.assertIsNone(error)
        make_shipping_config(allowed_countries=[{"code": "GH", "name": "Ghana"}])
        result, error = self._resolve()
        self.assertIsNone(error)

    def test_free_shipping_all(self):
        make_shipping_config(free_shipping_all=True)
        result, error = self._resolve(method_id="ta_whatever")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("0.00"))

    def test_free_popular_address(self):
        make_shipping_config(popular_addresses=[{
            "id": "legon", "name": "University of Ghana - Legon",
            "region": "Greater Accra", "country": "GH", "price": "0.00", "active": True,
        }])
        result, error = self._resolve(popular_id="legon")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("0.00"))
        self.assertEqual(result["method_name"], "Free delivery — University of Ghana - Legon")

    def test_paid_popular_address_charges_exact_price(self):
        make_shipping_config(popular_addresses=[{
            "id": "knust", "name": "KNUST Campus", "region": "Ashanti",
            "country": "GH", "price": "10.00", "active": True,
        }])
        result, error = self._resolve(popular_id="knust")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("10.00"))
        self.assertEqual(result["method_name"], "Delivery — KNUST Campus")

    def test_inactive_or_wrong_country_popular_address_rejected(self):
        make_shipping_config(popular_addresses=[
            {"id": "off", "name": "Off", "region": "R", "country": "GH",
             "price": "0.00", "active": False},
            {"id": "ng", "name": "Lagos Hub", "region": "Lagos", "country": "NG",
             "price": "0.00", "active": True},
        ])
        for popular_id in ("off", "ng", "missing"):
            result, error = self._resolve(popular_id=popular_id)
            self.assertIsNone(result, popular_id)
            self.assertIn("popular_address_id", error)

    def test_pickup(self):
        result, error = self._resolve(method_id="pickup")
        self.assertIn("shipping_method", error)  # disabled by default
        make_shipping_config(pickup_enabled=True)
        result, error = self._resolve(method_id="pickup")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("0.00"))
        self.assertTrue(result["is_pickup"])

    def test_global_threshold(self):
        make_shipping_config(free_shipping_threshold=Decimal("50"))
        result, error = self._resolve(method_id="standard", subtotal=Decimal("60"))
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("0.00"))

    @ta_configured
    def test_carrier_rate_id_matched(self):
        with patch.object(
            TerminalAfricaService, "get_shipping_rates", return_value=(TA_RATES, None)
        ):
            result, error = self._resolve(method_id="ta_rate_abc")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("42.50"))
        self.assertEqual(result["method_name"], "DHL Express")

    @ta_configured
    def test_stale_carrier_rate_id_rejected(self):
        with patch.object(
            TerminalAfricaService, "get_shipping_rates", return_value=(TA_RATES, None)
        ):
            result, error = self._resolve(method_id="ta_gone")
        self.assertIsNone(result)
        self.assertIn("shipping_method", error)

    @ta_unconfigured
    def test_carrier_rate_id_without_ta_rejected(self):
        result, error = self._resolve(method_id="ta_rate_abc")
        self.assertIsNone(result)
        self.assertIn("shipping_method", error)

    def test_internal_express_honored(self):
        result, error = self._resolve(method_id="express")
        self.assertIsNone(error)
        # GH: (15 + 1*5) * 2 = 40
        self.assertEqual(result["cost"], Decimal("40.00"))
        self.assertEqual(result["method_name"], "Express Shipping")

    def test_unknown_method_falls_back_to_standard(self):
        result, error = self._resolve(method_id="warp-drive")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("20.00"))

    def test_disabled_method_selection_rejected(self):
        make_shipping_config(shipping_methods={
            "standard": {"name": "Standard Shipping", "multiplier": "1.0",
                         "estimated_days": "3-7 business days", "enabled": True},
            "express": {"name": "Express Shipping", "multiplier": "2.0",
                        "estimated_days": "1-3 business days", "enabled": False},
        })
        result, error = self._resolve(method_id="express")
        self.assertIsNone(result)
        self.assertIn("shipping_method", error)
        # enabled method still works
        result, error = self._resolve(method_id="standard")
        self.assertIsNone(error)
        self.assertEqual(result["cost"], Decimal("20.00"))

    def test_handling_fee_and_cap_applied(self):
        make_shipping_config(handling_fee=Decimal("5.00"), max_shipping_cap=Decimal("22.00"))
        result, error = self._resolve(method_id="standard")
        self.assertIsNone(error)
        # 20 + 5 handling = 25 → capped at 22
        self.assertEqual(result["cost"], Decimal("22.00"))


class OrderCreationShippingTests(TestCase):
    """End-to-end: OrderService.create_order charges what the customer selected"""

    def setUp(self):
        cache.clear()
        ShippingConfig.get()
        self.user = make_user()
        self.variant = make_published_variant(price=Decimal("100.00"), stock=10, weight=1)

    def _create(self, **kwargs):
        return OrderService.create_order(
            user=self.user,
            items=[{"variant_id": str(self.variant.id), "quantity": 1,
                    "price": float(self.variant.price)}],
            shipping_address_data=shipping_address_data(),
            payment_method="paystack",
            **kwargs,
        )

    def test_express_selection_charged_express_rate(self):
        order, error = self._create(shipping_method_id="express")
        self.assertIsNone(error)
        order.refresh_from_db()
        # GH: (15 + 1kg*5) * 2 = 40
        self.assertEqual(order.shipping_cost, Decimal("40.00"))
        self.assertEqual(order.shipping_method, "Express Shipping")
        self.assertEqual(order.total, Decimal("140.00"))

    def test_legacy_empty_method_defaults_to_standard(self):
        order, error = self._create()
        self.assertIsNone(error)
        self.assertEqual(order.shipping_cost, Decimal("20.00"))

    def test_pickup_order(self):
        make_shipping_config(pickup_enabled=True)
        order, error = self._create(shipping_method_id="pickup")
        self.assertIsNone(error)
        self.assertTrue(order.is_pickup)
        self.assertEqual(order.shipping_cost, Decimal("0.00"))

    def test_popular_address_order(self):
        make_shipping_config(popular_addresses=[{
            "id": "legon", "name": "University of Ghana - Legon",
            "region": "Greater Accra", "country": "GH", "price": "0.00", "active": True,
        }])
        order, error = self._create(popular_address_id="legon")
        self.assertIsNone(error)
        self.assertEqual(order.shipping_cost, Decimal("0.00"))
        self.assertEqual(order.shipping_method, "Free delivery — University of Ghana - Legon")

    def test_order_to_unlisted_country_rejected(self):
        make_shipping_config(allowed_countries=[{"code": "NG", "name": "Nigeria"}])
        order, error = self._create()
        self.assertIsNone(order)
        self.assertIn("shipping_address", error)


class ShippingEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        ShippingConfig.get()
        self.client = Client()
        self.admin = make_admin()
        self.user = make_user()
        self.variant = make_published_variant(price=Decimal("100.00"), stock=5, weight=1)

    def _auth(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_meta_public(self):
        make_shipping_config(
            pickup_enabled=True,
            allowed_countries=[{"code": "GH", "name": "Ghana"}],
        )
        response = self.client.get("/api/orders/shipping/meta")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["pickup_enabled"])
        self.assertEqual(data["allowed_countries"][0]["code"], "GH")

    def test_popular_addresses_filtering(self):
        make_shipping_config(popular_addresses=[
            {"id": "a", "name": "Legon", "region": "Greater Accra", "country": "GH",
             "price": "0.00", "active": True},
            {"id": "b", "name": "KNUST", "region": "Ashanti", "country": "GH",
             "price": "10.00", "active": True},
            {"id": "c", "name": "Hidden", "region": "Ashanti", "country": "GH",
             "price": "0.00", "active": False},
        ])
        response = self.client.get(
            "/api/orders/shipping/popular-addresses?country=Ghana&region=Ashanti"
        )
        self.assertEqual(response.status_code, 200)
        addresses = response.json()["data"]["addresses"]
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]["name"], "KNUST")
        self.assertFalse(addresses[0]["is_free"])

    def test_admin_config_requires_admin(self):
        response = self.client.get("/api/orders/admin/shipping/config")
        self.assertEqual(response.status_code, 401)
        response = self.client.get(
            "/api/orders/admin/shipping/config", **self._auth(self.user)
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_config_get_and_update(self):
        response = self.client.get(
            "/api/orders/admin/shipping/config", **self._auth(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("fallback_rates", response.json()["data"])

        response = self.client.post(
            "/api/orders/admin/shipping/config",
            data=json.dumps({"pickup_enabled": True, "free_shipping_threshold": "300"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["pickup_enabled"])
        self.assertTrue(ShippingConfig.get().pickup_enabled)

    def test_admin_config_validation_error(self):
        response = self.client.post(
            "/api/orders/admin/shipping/config",
            data=json.dumps({"free_shipping_threshold": "abc"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 422)

    @ta_configured
    def test_options_endpoint_carrier_first(self):
        with patch.object(
            TerminalAfricaService, "get_shipping_rates", return_value=(TA_RATES, None)
        ):
            response = self.client.post(
                "/api/orders/shipping/options",
                data=json.dumps({
                    "country_code": "Ghana",
                    "items": [{"variant_id": str(self.variant.id), "quantity": 1}],
                }),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["source"], "terminal_africa")
        ids = [o["id"] for o in data["options"]]
        self.assertIn("ta_rate_abc", ids)

    @ta_unconfigured
    def test_options_endpoint_internal_fallback_and_pickup(self):
        make_shipping_config(pickup_enabled=True)
        response = self.client.post(
            "/api/orders/shipping/options",
            data=json.dumps({
                "country_code": "Ghana",
                "items": [{"variant_id": str(self.variant.id), "quantity": 1}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["source"], "internal")
        ids = [o["id"] for o in data["options"]]
        self.assertEqual(ids[0], "pickup")
        self.assertIn("standard", ids)
        standard = next(o for o in data["options"] if o["id"] == "standard")
        # "Ghana" normalized to GH: base 15 + 1kg*5 = 20 (regression for country-name bug)
        self.assertEqual(standard["cost"], 20.0)

    @ta_unconfigured
    def test_options_endpoint_free_threshold_carries_reason(self):
        make_shipping_config(free_shipping_threshold=Decimal("50"))
        response = self.client.post(
            "/api/orders/shipping/options",
            data=json.dumps({
                "country_code": "Ghana",
                "items": [{"variant_id": str(self.variant.id), "quantity": 1}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["source"], "free")
        self.assertIn("GHS 50", data["options"][0]["reason"])
