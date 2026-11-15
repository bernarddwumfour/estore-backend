"""Refresh cached service pages and clean up deleted catalog images."""
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.common.revalidation import notify_storefronts, storefront_revalidation_url
from .models import Service, ServiceCategory, ServiceImage, ServiceOption


@receiver(post_save, sender=Service)
@receiver(post_delete, sender=Service)
@receiver(post_save, sender=ServiceCategory)
@receiver(post_delete, sender=ServiceCategory)
@receiver(post_save, sender=ServiceOption)
@receiver(post_delete, sender=ServiceOption)
@receiver(post_save, sender=ServiceImage)
@receiver(post_delete, sender=ServiceImage)
def revalidate_services(sender, instance, using, **kwargs):
    url = storefront_revalidation_url("services")
    if url and settings.REVALIDATE_SECRET:
        transaction.on_commit(lambda: notify_storefronts([url], {}), using=using, robust=True)


@receiver(post_delete, sender=ServiceImage)
@receiver(post_delete, sender=ServiceCategory)
def delete_stored_image(sender, instance, using, **kwargs):
    image = instance.image
    if image and image.name:
        transaction.on_commit(lambda: image.storage.delete(image.name), using=using, robust=True)
