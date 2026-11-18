from django.test import TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, RequestFactory, encode_multipart
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import resolve
from django.contrib.auth import get_user_model
from unittest.mock import patch
from apps.services.models import Service, ServiceCategory, ServiceOption
from apps.services.schemas.service_schemas import _service_payload, category_payload
from apps.services.selectors.service_selectors import public_services, admin_services_queryset
from apps.services.services.service_service import delete_option
from apps.services.views.category_views import category_request_data


class ServiceCatalogTests(TestCase):
    @patch('apps.users.decorators.auth.validate_jwt_token')
    def test_admin_options_list_searches_across_services(self, validate):
        admin = get_user_model().objects.create_user(email='catalog-admin@example.com', password='password123', role='admin')
        repair = Service.objects.create(title='Phone Repair', slug='phone-repair')
        cleaning = Service.objects.create(title='Device Cleaning', slug='device-cleaning')
        ServiceOption.objects.create(service=repair, name='Screen', slug='screen', pricing_type='quote')
        ServiceOption.objects.create(service=cleaning, name='Basic', slug='basic', price=20)
        validate.return_value = (True, {'type': 'access', 'user_id': str(admin.pk)})
        response = self.client.get('/api/services/admin/options', {'search': 'Phone'}, HTTP_AUTHORIZATION='Bearer test')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['options'][0]['name'], 'Screen')
        self.assertEqual(data['options'][0]['service']['id'], str(repair.pk))

    def test_catalog_routes_have_services_prefix(self):
        self.assertEqual(resolve('/api/services/admin/services').url_name, 'admin-services')
        self.assertEqual(resolve('/api/services/admin/categories').url_name, 'admin-categories')
        self.assertEqual(resolve('/api/services/admin/options').url_name, 'admin-all-service-options')
        self.assertEqual(resolve('/api/services/categories').url_name, 'category-list')
        self.assertEqual(resolve('/api/services/screen-repair').url_name, 'service-detail')

    def test_multipart_category_patch_reads_fields_and_image(self):
        upload = SimpleUploadedFile('category.png', b'example', content_type='image/png')
        body = encode_multipart(BOUNDARY, {'name': 'Repairs', 'image': upload})
        request = RequestFactory().patch('/api/services/admin/categories/test', body, content_type=MULTIPART_CONTENT)
        fields, image = category_request_data(request)
        self.assertEqual(fields['name'], 'Repairs')
        self.assertEqual(image.name, 'category.png')

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
