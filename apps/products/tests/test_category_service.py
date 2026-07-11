"""Unit tests for CategoryService business logic."""

from django.test import TestCase

from apps.products.models import Category, Product
from apps.products.services.category_service import CategoryService
from .factories import make_admin, make_category, make_product


class CreateCategoryTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_create_basic(self):
        category, error = CategoryService.create_category(name="Books", user=self.admin)
        self.assertIsNone(error)
        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Books")
        self.assertEqual(category.slug, "books")

    def test_create_generates_unique_slug_on_collision(self):
        make_category(name="Phones", slug="phones")
        category, error = CategoryService.create_category(name="Phones!", user=self.admin)
        # slugify("Phones!") -> "phones", which collides -> "phones-1"
        self.assertIsNone(error)
        self.assertEqual(category.slug, "phones-1")

    def test_create_with_valid_parent(self):
        parent = make_category(name="Parent")
        category, error = CategoryService.create_category(
            name="Child", parent_id=str(parent.id), user=self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(category.parent_id, parent.id)

    def test_create_with_missing_parent_returns_error(self):
        import uuid

        category, error = CategoryService.create_category(
            name="Orphan", parent_id=str(uuid.uuid4()), user=self.admin
        )
        self.assertIsNone(category)
        self.assertIn("parent_id", error)

    def test_create_treats_null_parent_as_none(self):
        category, error = CategoryService.create_category(
            name="TopLevel", parent_id="null", user=self.admin
        )
        self.assertIsNone(error)
        self.assertIsNone(category.parent)


class UpdateCategoryTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_update_name_regenerates_slug(self):
        category = make_category(name="Old", slug="old")
        updated, error = CategoryService.update_category(
            str(category.id), {"name": "Brand New"}, user=self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(updated.name, "Brand New")
        self.assertEqual(updated.slug, "brand-new")

    def test_update_missing_category(self):
        import uuid

        updated, error = CategoryService.update_category(
            str(uuid.uuid4()), {"name": "x"}, user=self.admin
        )
        self.assertIsNone(updated)
        self.assertIn("category", error)

    def test_category_cannot_be_its_own_parent(self):
        category = make_category()
        updated, error = CategoryService.update_category(
            str(category.id), {"parent_id": str(category.id)}, user=self.admin
        )
        self.assertIsNone(updated)
        self.assertIn("parent_id", error)

    def test_update_other_fields(self):
        category = make_category(is_active=True, is_hidden=False)
        updated, error = CategoryService.update_category(
            str(category.id),
            {"is_active": False, "is_hidden": True, "description": "desc"},
            user=self.admin,
        )
        self.assertIsNone(error)
        self.assertFalse(updated.is_active)
        self.assertTrue(updated.is_hidden)
        self.assertEqual(updated.description, "desc")


class BulkActionCategoryTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_bulk_delete_success(self):
        c1 = make_category()
        c2 = make_category()
        results, error = CategoryService.bulk_action_categories(
            [str(c1.id), str(c2.id)], "delete", user=self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(len(results["success"]), 2)
        self.assertEqual(Category.objects.count(), 0)

    def test_bulk_delete_blocked_by_subcategories(self):
        parent = make_category()
        make_category(parent=parent)
        results, error = CategoryService.bulk_action_categories(
            [str(parent.id)], "delete", user=self.admin
        )
        self.assertEqual(len(results["failed"]), 1)
        self.assertIn("subcategories", results["failed"][0]["reason"])
        self.assertTrue(Category.objects.filter(id=parent.id).exists())

    def test_bulk_delete_blocked_by_products(self):
        category = make_category()
        make_product(category=category)
        results, error = CategoryService.bulk_action_categories(
            [str(category.id)], "delete", user=self.admin
        )
        self.assertEqual(len(results["failed"]), 1)
        self.assertIn("products", results["failed"][0]["reason"])

    def test_bulk_activate_deactivate(self):
        c1 = make_category(is_active=True)
        c2 = make_category(is_active=True)
        results, error = CategoryService.bulk_action_categories(
            [str(c1.id), str(c2.id)], "deactivate", user=self.admin
        )
        self.assertIsNone(error)
        c1.refresh_from_db()
        c2.refresh_from_db()
        self.assertFalse(c1.is_active)
        self.assertFalse(c2.is_active)

    def test_bulk_unknown_action(self):
        category = make_category()
        results, error = CategoryService.bulk_action_categories(
            [str(category.id)], "frobnicate", user=self.admin
        )
        self.assertIsNone(results)
        self.assertIn("action", error)
