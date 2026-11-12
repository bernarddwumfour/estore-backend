"""Refresh storefront category sections after category writes commit."""

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.common.revalidation import notify_storefronts, storefront_revalidation_url
from .models import Category, Product, ProductVariant, VariantImage
from .revalidation import schedule_product_revalidation


def schedule_category_revalidation(using):
    url = storefront_revalidation_url("categories")
    if not url or not settings.REVALIDATE_SECRET:
        return
    transaction.on_commit(
        lambda: notify_storefronts([url], {}),
        using=using,
        robust=True,
    )


@receiver(post_save, sender=Category)
def revalidate_saved_category(sender, instance, using, **kwargs):
    schedule_category_revalidation(using)


@receiver(post_delete, sender=Category)
def revalidate_deleted_category(sender, instance, using, **kwargs):
    schedule_category_revalidation(using)


@receiver(pre_save, sender=Product)
def remember_public_product(sender, instance, using, **kwargs):
    previous = None
    if instance.pk:
        previous = sender.objects.using(using).filter(pk=instance.pk).values("status", "category_id").first()
    instance._previous_public_category_id = (
        previous["category_id"] if previous and previous["status"] == Product.STATUS_PUBLISHED else None
    )
    instance._was_public = bool(previous and previous["status"] == Product.STATUS_PUBLISHED)


@receiver(post_save, sender=Product)
def revalidate_saved_product(sender, instance, using, **kwargs):
    was_public = getattr(instance, "_was_public", False)
    is_public = instance.status == Product.STATUS_PUBLISHED
    if not (was_public or is_public):
        return

    old_category = getattr(instance, "_previous_public_category_id", None)
    new_category = instance.category_id if is_public else None
    schedule_product_revalidation(
        categories_changed=old_category != new_category,
        using=using,
    )


@receiver(post_delete, sender=Product)
def revalidate_deleted_product(sender, instance, using, **kwargs):
    if instance.status == Product.STATUS_PUBLISHED:
        schedule_product_revalidation(
            categories_changed=instance.category_id is not None,
            using=using,
        )


def _variant_is_public(product_id, using):
    return Product.objects.using(using).filter(
        pk=product_id, status=Product.STATUS_PUBLISHED
    ).exists()


@receiver(post_save, sender=ProductVariant)
@receiver(post_delete, sender=ProductVariant)
def revalidate_variant(sender, instance, using, **kwargs):
    if _variant_is_public(instance.product_id, using):
        schedule_product_revalidation(using=using)


@receiver(post_save, sender=VariantImage)
@receiver(post_delete, sender=VariantImage)
def revalidate_variant_image(sender, instance, using, **kwargs):
    product_id = ProductVariant.objects.using(using).filter(
        pk=instance.variant_id
    ).values_list("product_id", flat=True).first()
    if product_id and _variant_is_public(product_id, using):
        schedule_product_revalidation(using=using)
