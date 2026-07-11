"""
Test data factories/helpers for the products app test-suite.

Plain helper functions (no external deps) that build valid model instances so
each test stays focused on the behaviour under test rather than fixture setup.
"""

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.products.models import (
    Category,
    Product,
    ProductVariant,
    ProductReview,
    Wishlist,
)

User = get_user_model()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_user(role: str = "customer", **kwargs) -> "User":
    email = kwargs.pop("email", f"{_unique('user')}@example.com")
    password = kwargs.pop("password", "Str0ng-Pass!23")
    return User.objects.create_user(
        email=email,
        password=password,
        role=role,
        **kwargs,
    )


def make_admin(**kwargs) -> "User":
    return make_user(role="admin", **kwargs)


def make_category(name: str = None, **kwargs) -> Category:
    name = name or _unique("Category")
    slug = kwargs.pop("slug", None) or _unique("cat")
    return Category.objects.create(name=name, slug=slug, **kwargs)


def make_product(category: Category = None, **kwargs) -> Product:
    if category is None and "category" not in kwargs:
        category = make_category()
    title = kwargs.pop("title", None) or _unique("Product")
    slug = kwargs.pop("slug", None) or _unique("prod")
    description = kwargs.pop("description", "A test product description.")
    return Product.objects.create(
        title=title,
        slug=slug,
        description=description,
        category=kwargs.pop("category", category),
        **kwargs,
    )


def make_variant(product: Product = None, **kwargs) -> ProductVariant:
    if product is None:
        product = make_product()
    sku = kwargs.pop("sku", None) or _unique("SKU")
    price = kwargs.pop("price", Decimal("100.00"))
    return ProductVariant.objects.create(
        product=product,
        sku=sku,
        price=Decimal(str(price)),
        stock=kwargs.pop("stock", 10),
        **kwargs,
    )


def make_review(product: Product = None, user: "User" = None, **kwargs) -> ProductReview:
    product = product or make_product()
    user = user or make_user()
    return ProductReview.objects.create(
        product=product,
        user=user,
        rating=kwargs.pop("rating", 5),
        comment=kwargs.pop("comment", "Great product."),
        **kwargs,
    )


def make_wishlist(user: "User" = None, variant: ProductVariant = None) -> Wishlist:
    user = user or make_user()
    variant = variant or make_variant()
    return Wishlist.objects.create(user=user, variant=variant)
