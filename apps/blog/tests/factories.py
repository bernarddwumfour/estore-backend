"""
Test data factories for the blog app test-suite.

Plain helper functions that build valid model instances.
"""

import uuid

from django.contrib.auth import get_user_model

from apps.blog.models import BlogCategory, BlogPost

User = get_user_model()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_user(role: str = "customer", **kwargs):
    email = kwargs.pop("email", f"{_unique('user')}@example.com")
    password = kwargs.pop("password", "Str0ng-Pass!23")
    return User.objects.create_user(email=email, password=password, role=role, **kwargs)


def make_admin(**kwargs):
    return make_user(role="admin", **kwargs)


def make_blog_category(name: str = None, **kwargs) -> BlogCategory:
    name = name or _unique("Blog Category")
    slug = kwargs.pop("slug", None) or _unique("blog-cat")
    return BlogCategory.objects.create(name=name, slug=slug, **kwargs)


def make_blog_post(category: BlogCategory = None, **kwargs) -> BlogPost:
    if category is None and "category" not in kwargs:
        category = make_blog_category()
    title = kwargs.pop("title", None) or _unique("Blog Post")
    slug = kwargs.pop("slug", None) or _unique("blog-post")
    content = kwargs.pop("content", "Test content for the blog post.")
    return BlogPost.objects.create(
        title=title,
        slug=slug,
        content=content,
        category=kwargs.pop("category", category),
        **kwargs,
    )
