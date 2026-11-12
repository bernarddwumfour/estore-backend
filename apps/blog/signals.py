"""Invalidate storefront blog caches for model writes, including Django admin."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import BlogPost
from .revalidation import schedule_blog_revalidation


@receiver(pre_save, sender=BlogPost)
def remember_public_post(sender, instance, using, **kwargs):
    previous = None
    if instance.pk:
        previous = sender.objects.using(using).filter(pk=instance.pk).values("slug", "status").first()
    instance._previous_public_slug = (
        previous["slug"] if previous and previous["status"] == BlogPost.STATUS_PUBLISHED else None
    )


@receiver(post_save, sender=BlogPost)
def revalidate_saved_post(sender, instance, using, **kwargs):
    previous_slug = getattr(instance, "_previous_public_slug", None)
    if previous_slug or instance.status == BlogPost.STATUS_PUBLISHED:
        schedule_blog_revalidation(
            {slug for slug in (previous_slug, instance.slug) if slug},
            using=using,
        )


@receiver(post_delete, sender=BlogPost)
def revalidate_deleted_post(sender, instance, using, **kwargs):
    if instance.status == BlogPost.STATUS_PUBLISHED:
        schedule_blog_revalidation((instance.slug,), using=using)
