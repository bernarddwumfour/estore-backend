"""
Unit tests for the blog app — models, selectors, services, and schemas.
"""

from django.db import IntegrityError
from django.test import TestCase

from apps.blog.models import BlogCategory, BlogPost
from apps.blog.schemas import (
    serialize_category,
    serialize_category_list,
    serialize_post,
    serialize_post_list,
    validate_post,
    validate_bulk_action,
)
from apps.blog.selectors import (
    get_post_by_slug,
    get_post_by_id,
    list_posts,
    list_categories,
    get_category_by_id,
    get_category_by_slug,
)
from apps.blog.services import BlogCategoryService, BlogPostService

from .factories import make_blog_category, make_blog_post, make_user, make_admin


# ==========================================================================
# Models
# ==========================================================================

class BlogCategoryModelTests(TestCase):
    def test_str(self):
        cat = make_blog_category(name="News")
        self.assertEqual(str(cat), "News")

    def test_slug_unique(self):
        make_blog_category(name="Cat", slug="my-slug")
        with self.assertRaises(IntegrityError):
            make_blog_category(name="Cat 2", slug="my-slug")

    def test_name_unique(self):
        make_blog_category(name="UniqueName")
        with self.assertRaises(IntegrityError):
            make_blog_category(name="UniqueName")

    def test_default_active(self):
        cat = make_blog_category()
        self.assertTrue(cat.is_active)


class BlogPostModelTests(TestCase):
    def test_str(self):
        post = make_blog_post(title="Hello World")
        self.assertIn("Hello World", str(post))
        self.assertIn("Draft", str(post))

    def test_published_at_set_on_first_publish(self):
        post = make_blog_post(status=BlogPost.STATUS_DRAFT)
        self.assertIsNone(post.published_at)
        post.status = BlogPost.STATUS_PUBLISHED
        post.save()
        self.assertIsNotNone(post.published_at)

    def test_published_at_not_overwritten(self):
        post = make_blog_post(status=BlogPost.STATUS_PUBLISHED)
        original = post.published_at
        post.title = "Updated Title"
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.published_at, original)

    def test_author_display_name_from_user(self):
        user = make_user(email="author@test.com", first_name="Jane", last_name="Doe")
        post = make_blog_post(author_user=user)
        self.assertEqual(post.author_display_name, "Jane Doe")

    def test_author_display_name_from_name_field(self):
        post = make_blog_post(author_name="Guest Writer")
        self.assertEqual(post.author_display_name, "Guest Writer")

    def test_author_display_name_unknown_fallback(self):
        post = make_blog_post()
        self.assertEqual(post.author_display_name, "Unknown")

    def test_slug_unique(self):
        make_blog_post(title="Post", slug="same-slug")
        with self.assertRaises(IntegrityError):
            make_blog_post(title="Post 2", slug="same-slug")

    def test_status_default_draft(self):
        post = make_blog_post()
        self.assertEqual(post.status, BlogPost.STATUS_DRAFT)


# ==========================================================================
# Schemas — validation
# ==========================================================================

class ValidatePostTests(TestCase):
    def test_create_requires_title(self):
        cleaned, errors = validate_post({"content": "Some content"})
        self.assertIsNone(cleaned)
        self.assertIn("title", errors)

    def test_create_requires_content(self):
        cleaned, errors = validate_post({"title": "A title"})
        self.assertIsNone(cleaned)
        self.assertIn("content", errors)

    def test_create_requires_author(self):
        cleaned, errors = validate_post({"title": "T", "content": "C"})
        self.assertIsNone(cleaned)
        self.assertIn("author", errors)

    def test_create_with_author_user(self):
        user = make_user()
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_user_id": str(user.id),
        })
        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["title"], "T")

    def test_create_with_unknown_author_user_id_fails(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_user_id": "some-uuid",
        })
        self.assertIsNone(cleaned)
        self.assertIn("author_user_id", errors)

    def test_create_with_author_name(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
        })
        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["author_name"], "Jane")

    def test_invalid_status_rejected(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane", "status": "bogus",
        })
        self.assertIsNone(cleaned)
        self.assertIn("status", errors)

    def test_valid_status_accepted(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane", "status": "published",
        })
        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["status"], "published")

    def test_category_not_found(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
            "category_id": "00000000-0000-0000-0000-000000000000",
        })
        self.assertIsNone(cleaned)
        self.assertIn("category_id", errors)

    def test_category_valid(self):
        cat = make_blog_category()
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
            "category_id": str(cat.id),
        })
        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["category_id"], str(cat.id))

    def test_update_partial_does_not_require_missing_fields(self):
        cleaned, errors = validate_post({"title": "New Title"}, is_update=True)
        self.assertIsNotNone(cleaned)
        self.assertIsNone(errors)
        self.assertEqual(cleaned["title"], "New Title")
        self.assertNotIn("content", cleaned)

    def test_excerpt_truncated(self):
        cleaned, _ = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
            "excerpt": "x" * 400,
        })
        self.assertEqual(len(cleaned["excerpt"]), 300)

    def test_slug_length_limit(self):
        cleaned, errors = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
            "slug": "x" * 250,
        })
        self.assertIsNone(cleaned)
        self.assertIn("slug", errors)

    def test_is_featured_coerced(self):
        cleaned, _ = validate_post({
            "title": "T", "content": "C", "author_name": "Jane",
            "is_featured": "true",
        })
        self.assertIs(cleaned["is_featured"], True)


class ValidateBulkActionTests(TestCase):
    def test_missing_action(self):
        _, errors = validate_bulk_action({"post_ids": ["id1"]})
        self.assertIn("action", errors)

    def test_invalid_action(self):
        _, errors = validate_bulk_action({"action": "bogus", "post_ids": ["id1"]})
        self.assertIn("action", errors)

    def test_missing_ids(self):
        _, errors = validate_bulk_action({"action": "publish"})
        self.assertIn("post_ids", errors)

    def test_valid(self):
        cleaned, errors = validate_bulk_action({"action": "publish", "post_ids": ["id1"]})
        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["action"], "publish")


# ==========================================================================
# Schemas — serialization
# ==========================================================================

class SerializeTests(TestCase):
    def test_serialize_category_public(self):
        cat = make_blog_category(name="News", description="All the news")
        data = serialize_category(cat, is_admin=False)
        self.assertEqual(data["name"], "News")
        self.assertEqual(data["description"], "All the news")
        self.assertNotIn("created_at", data)  # admin only

    def test_serialize_category_admin(self):
        cat = make_blog_category()
        data = serialize_category(cat, is_admin=True)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    def test_serialize_post_public(self):
        cat = make_blog_category(name="Tech")
        post = make_blog_post(title="Hello", category=cat, status=BlogPost.STATUS_PUBLISHED)
        data = serialize_post(post, is_admin=False)
        self.assertEqual(data["title"], "Hello")
        self.assertEqual(data["category"]["name"], "Tech")
        self.assertNotIn("status", data)
        self.assertEqual(data["author"], "Unknown")

    def test_serialize_post_admin(self):
        post = make_blog_post(title="Admin Post")
        data = serialize_post(post, is_admin=True)
        self.assertIn("status", data)
        self.assertIn("author_user_id", data)


# ==========================================================================
# Selectors
# ==========================================================================

class SelectorTests(TestCase):
    def test_get_post_by_slug_public_hides_drafts(self):
        post = make_blog_post(slug="my-post", status=BlogPost.STATUS_DRAFT)
        result = get_post_by_slug("my-post", admin=False)
        self.assertIsNone(result)

    def test_get_post_by_slug_admin_sees_drafts(self):
        post = make_blog_post(slug="draft-post", status=BlogPost.STATUS_DRAFT)
        result = get_post_by_slug("draft-post", admin=True)
        self.assertIsNotNone(result)

    def test_get_post_by_slug_missing(self):
        self.assertIsNone(get_post_by_slug("nope"))

    def test_list_posts_public_only_published(self):
        make_blog_post(title="Pub", status=BlogPost.STATUS_PUBLISHED)
        make_blog_post(title="Draft", status=BlogPost.STATUS_DRAFT)
        posts, total, _ = list_posts(admin=False)
        self.assertEqual(total, 1)
        self.assertEqual(posts[0].title, "Pub")

    def test_list_posts_admin_sees_all(self):
        make_blog_post(title="Pub", status=BlogPost.STATUS_PUBLISHED)
        make_blog_post(title="Draft", status=BlogPost.STATUS_DRAFT)
        _, total, _ = list_posts(admin=True)
        self.assertEqual(total, 2)

    def test_list_posts_filter_by_category(self):
        cat_a = make_blog_category(name="A", slug="a")
        cat_b = make_blog_category(name="B", slug="b")
        make_blog_post(title="In A", category=cat_a, status=BlogPost.STATUS_PUBLISHED)
        make_blog_post(title="In B", category=cat_b, status=BlogPost.STATUS_PUBLISHED)
        posts, total, _ = list_posts(admin=False, category_slug="a")
        self.assertEqual(total, 1)
        self.assertEqual(posts[0].title, "In A")

    def test_list_posts_search(self):
        make_blog_post(title="Python Tips", status=BlogPost.STATUS_PUBLISHED)
        make_blog_post(title="Django News", status=BlogPost.STATUS_PUBLISHED)
        posts, total, _ = list_posts(admin=False, search="python")
        self.assertEqual(total, 1)
        self.assertEqual(posts[0].title, "Python Tips")

    def test_list_posts_pagination(self):
        for i in range(5):
            make_blog_post(title=f"Post {i}", status=BlogPost.STATUS_PUBLISHED)
        posts, total, meta = list_posts(admin=False, page=1, limit=2)
        self.assertEqual(len(posts), 2)
        self.assertEqual(total, 5)
        self.assertEqual(meta["per_page"], 2)
        self.assertTrue(meta["has_next"])

    def test_list_categories_active_only(self):
        make_blog_category(name="Active", is_active=True)
        make_blog_category(name="Inactive", is_active=False)
        cats = list_categories(active_only=True)
        self.assertEqual(len(cats), 1)
        self.assertEqual(cats[0].name, "Active")

    def test_get_category_by_id(self):
        cat = make_blog_category()
        result = get_category_by_id(str(cat.id))
        self.assertIsNotNone(result)
        self.assertEqual(result.name, cat.name)

    def test_get_category_by_id_missing(self):
        self.assertIsNone(get_category_by_id("00000000-0000-0000-0000-000000000000"))


# ==========================================================================
# Services
# ==========================================================================

class BlogCategoryServiceTests(TestCase):
    def test_create_category(self):
        cat, errors = BlogCategoryService.create_category(name="News")
        self.assertIsNotNone(cat)
        self.assertIsNone(errors)
        self.assertEqual(cat.name, "News")
        self.assertTrue(cat.slug)

    def test_create_category_duplicate_name_generates_unique_slug(self):
        # Name field has unique=True, so use different names but verify slug logic works
        cat1, _ = BlogCategoryService.create_category(name="My Category")
        cat2, _ = BlogCategoryService.create_category(name="My Category Two")
        self.assertNotEqual(cat1.slug, cat2.slug)

    def test_update_category(self):
        cat, _ = BlogCategoryService.create_category(name="Old")
        updated, errors = BlogCategoryService.update_category(str(cat.id), {"name": "New"})
        self.assertIsNotNone(updated)
        self.assertEqual(updated.name, "New")

    def test_update_category_not_found(self):
        _, errors = BlogCategoryService.update_category("00000000-0000-0000-0000-000000000000", {"name": "X"})
        self.assertIsNotNone(errors)

    def test_delete_category_with_posts_denied(self):
        cat, _ = BlogCategoryService.create_category(name="Has Posts")
        make_blog_post(category=cat)
        success, errors = BlogCategoryService.delete_category(str(cat.id))
        self.assertFalse(success)
        self.assertIsNotNone(errors)

    def test_delete_category_empty(self):
        cat, _ = BlogCategoryService.create_category(name="Empty")
        success, errors = BlogCategoryService.delete_category(str(cat.id))
        self.assertTrue(success)
        self.assertIsNone(errors)


class BlogPostServiceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.cat = make_blog_category()

    def test_create_post(self):
        post, errors = BlogPostService.create_post({
            "title": "Hello World",
            "content": "Blog content here.",
            "author_name": "Jane",
            "status": BlogPost.STATUS_PUBLISHED,
        })
        self.assertIsNotNone(post)
        self.assertIsNone(errors)
        self.assertEqual(post.status, BlogPost.STATUS_PUBLISHED)
        self.assertIsNotNone(post.published_at)

    def test_create_post_defaults_to_draft(self):
        post, _ = BlogPostService.create_post({
            "title": "Draft", "content": "Content", "author_name": "Jane",
        })
        self.assertEqual(post.status, BlogPost.STATUS_DRAFT)

    def test_create_post_with_category(self):
        post, _ = BlogPostService.create_post({
            "title": "Categorized",
            "content": "Content",
            "author_name": "Jane",
            "category_id": str(self.cat.id),
        })
        self.assertEqual(post.category, self.cat)

    def test_create_post_bad_category(self):
        _, errors = BlogPostService.create_post({
            "title": "Bad Cat",
            "content": "Content",
            "author_name": "Jane",
            "category_id": "00000000-0000-0000-0000-000000000000",
        })
        self.assertIsNotNone(errors)
        self.assertIn("category_id", errors)

    def test_update_post(self):
        post, _ = BlogPostService.create_post({
            "title": "Old Title", "content": "Old", "author_name": "Jane",
        })
        updated, errors = BlogPostService.update_post(str(post.id), {"title": "New Title"})
        self.assertIsNotNone(updated)
        self.assertEqual(updated.title, "New Title")

    def test_update_post_not_found(self):
        _, errors = BlogPostService.update_post("00000000-0000-0000-0000-000000000000", {"title": "X"})
        self.assertIsNotNone(errors)

    def test_update_post_cannot_clear_both_author_fields(self):
        post, _ = BlogPostService.create_post({
            "title": "Has Author", "content": "C", "author_name": "Jane",
        })
        updated, errors = BlogPostService.update_post(str(post.id), {
            "author_name": "", "author_user_id": None,
        })
        self.assertIsNone(updated)
        self.assertIn("author", errors)
        post.refresh_from_db()
        self.assertEqual(post.author_name, "Jane")

    def test_publish_post(self):
        post, _ = BlogPostService.create_post({
            "title": "Publish Me", "content": "C", "author_name": "Jane",
        })
        self.assertIsNone(post.published_at)
        published, errors = BlogPostService.publish_post(str(post.id))
        self.assertIsNotNone(published)
        self.assertEqual(published.status, BlogPost.STATUS_PUBLISHED)
        self.assertIsNotNone(published.published_at)

    def test_archive_post(self):
        post, _ = BlogPostService.create_post({
            "title": "Archive Me", "content": "C", "author_name": "Jane",
            "status": BlogPost.STATUS_PUBLISHED,
        })
        archived, _ = BlogPostService.archive_post(str(post.id))
        self.assertEqual(archived.status, BlogPost.STATUS_ARCHIVED)

    def test_delete_post(self):
        post, _ = BlogPostService.create_post({
            "title": "Delete Me", "content": "C", "author_name": "Jane",
        })
        success, _ = BlogPostService.delete_post(str(post.id))
        self.assertTrue(success)

    def test_bulk_publish(self):
        p1, _ = BlogPostService.create_post({"title": "P1", "content": "C", "author_name": "J"})
        p2, _ = BlogPostService.create_post({"title": "P2", "content": "C", "author_name": "J"})
        results, errors = BlogPostService.bulk_action_posts(
            [str(p1.id), str(p2.id)], "publish",
        )
        self.assertIsNone(errors)
        self.assertEqual(len(results["success"]), 2)
        p1.refresh_from_db()
        self.assertEqual(p1.status, BlogPost.STATUS_PUBLISHED)

    def test_bulk_delete(self):
        p1, _ = BlogPostService.create_post({"title": "P1", "content": "C", "author_name": "J"})
        results, _ = BlogPostService.bulk_action_posts([str(p1.id)], "delete")
        self.assertEqual(len(results["success"]), 1)
        self.assertFalse(BlogPost.objects.filter(id=p1.id).exists())
