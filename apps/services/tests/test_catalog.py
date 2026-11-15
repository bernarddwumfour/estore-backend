from django.test import TestCase
from apps.services.models import Service, ServiceCategory, ServiceOption
from apps.services.schemas.service_schemas import _service_payload, category_payload
from apps.services.selectors.service_selectors import public_services, admin_services_queryset
from apps.services.services.service_service import delete_option


class ServiceCatalogTests(TestCase):
    def test_hidden_category_is_not_public(self):
        category = ServiceCategory.objects.create(name='Hidden', slug='hidden', is_hidden=True)
        service = Service.objects.create(title='Service', slug='service', category=category, status=Service.PUBLISHED)
        self.assertFalse(public_services().filter(pk=service.pk).exists())
        self.assertTrue(admin_services_queryset().filter(pk=service.pk).exists())

    def test_category_can_be_cleared(self):
        service = Service.objects.create(title='Service', slug='service')
        self.assertIsNone(_service_payload({'category_id': None}, service)['category'])

    def test_category_cycle_rejected(self):
        parent = ServiceCategory.objects.create(name='Parent', slug='parent')
        child = ServiceCategory.objects.create(name='Child', slug='child', parent=parent)
        with self.assertRaises(ValueError):
            category_payload({'parent_id': str(child.pk)}, parent)

    def test_last_active_option_cannot_be_deleted(self):
        service = Service.objects.create(title='Service', slug='service', status=Service.PUBLISHED)
        option = ServiceOption.objects.create(service=service, name='Basic', slug='basic', price=10)
        with self.assertRaises(ValueError):
            delete_option(option)
