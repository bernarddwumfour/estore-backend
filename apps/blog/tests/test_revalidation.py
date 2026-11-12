"""Public blog writes invalidate the relevant storefront cache after commit."""

from unittest.mock import patch

import requests
from django.test import TestCase, override_settings

from apps.blog.models import BlogPost
from apps.blog.revalidation import notify_blog_change
from .factories import make_blog_post


@override_settings(
    STOREFRONT_BASE_URL="https://store.example",
    REVALIDATE_SECRET="test-secret",
)
class BlogRevalidationTests(TestCase):
    @patch("apps.blog.revalidation.notify_blog_change")
    def test_draft_changes_do_not_invalidate(self, notify):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            post = make_blog_post(status=BlogPost.STATUS_DRAFT)
            post.title = "Changed draft"
            post.save()

        self.assertEqual(callbacks, [])
        notify.assert_not_called()

    @patch("apps.blog.revalidation.notify_blog_change")
    def test_publish_edit_rename_archive_and_delete(self, notify):
        post = make_blog_post(slug="original", status=BlogPost.STATUS_DRAFT)

        with self.captureOnCommitCallbacks(execute=True):
            post.status = BlogPost.STATUS_PUBLISHED
            post.save()
        notify.assert_called_once_with(("original",))

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            post.slug = "renamed"
            post.save()
        notify.assert_called_once_with(("original", "renamed"))

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            post.status = BlogPost.STATUS_ARCHIVED
            post.save()
        notify.assert_called_once_with(("renamed",))

        notify.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            post.delete()
        notify.assert_not_called()

    @patch("apps.blog.revalidation.notify_blog_change")
    def test_deleting_published_post_invalidates(self, notify):
        post = make_blog_post(slug="to-delete", status=BlogPost.STATUS_PUBLISHED)
        with self.captureOnCommitCallbacks(execute=True):
            post.delete()
        notify.assert_called_once_with(("to-delete",))

    @patch("apps.common.revalidation.requests.post")
    def test_failed_callback_does_not_raise(self, post):
        post.side_effect = requests.Timeout("storefront unavailable")
        notify_blog_change(("example",))
        post.assert_called_once()
