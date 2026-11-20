from copy import deepcopy
from django.test import TestCase
from apps.products.tests.factories import make_admin
from apps.templates.models import TemplateCategory
from apps.templates.services import save_template, save_instance, save_group, RevisionConflict
from apps.templates.schemas import resolve, serialize_template, validate_template


class TemplateTests(TestCase):
    def setUp(self):
        self.user = make_admin()
        self.data = {'name': 'Announcement', 'type': 'text', 'status': 'active', 'content': {'text': '{{headline}} / {{headline}}'}, 'slots': [{'key': 'headline', 'label': 'Heading', 'type': 'text', 'default_value': 'Hello', 'required': True}]}

    def test_shared_slot_resolves_every_occurrence(self):
        self.assertEqual(resolve(self.data, {'headline': 'Welcome'})['content']['text'], 'Welcome / Welcome')
        self.assertEqual(self.data['content']['text'], '{{headline}} / {{headline}}')

    def test_required_and_unknown_values_rejected(self):
        for values in ({'headline': ''}, {'unknown': 'value'}):
            with self.assertRaises(ValueError):
                resolve(self.data, values)

    def test_slot_definitions_validate(self):
        for change in ({'slots': self.data['slots'] * 2}, {'content': {'text': '{{undefined}}'}}):
            with self.assertRaises(ValueError):
                validate_template({**self.data, **change})

    def test_snapshot_survives_source_edits_and_conflicts(self):
        template = save_template(self.data, self.user)
        instance = save_instance({'template_id': str(template.id), 'template_revision': 1, 'values': {'headline': 'Original'}}, self.user)
        changed = {**self.data, 'revision': 1, 'content': {'text': 'Edited {{headline}}'}}
        save_template(changed, self.user, template.id)
        updated = save_instance({'revision': 1, 'values': {'headline': 'Again'}}, self.user, instance.id)
        self.assertEqual(updated.resolved['content']['text'], 'Again / Again')
        with self.assertRaises(RevisionConflict):
            save_template(changed, self.user, template.id)
        with self.assertRaises(RevisionConflict):
            save_instance({'template_id': str(template.id), 'template_revision': 1}, self.user)

    def test_multiple_categories_and_reusable_ordered_groups(self):
        categories = [TemplateCategory.objects.create(name=name) for name in ['Email', 'Announcements']]
        first = save_template({**self.data, 'category_ids': [str(c.id) for c in categories]}, self.user)
        second = save_template({**self.data, 'name': 'Second'}, self.user)
        group = save_group({'name': 'Pack', 'template_ids': [str(second.id), str(first.id)]})
        self.assertEqual(first.categories.count(), 2)
        self.assertEqual(list(group.items.values_list('template_id', flat=True)), [second.id, first.id])
        self.assertEqual(serialize_template(first)['groups'][0]['name'], 'Pack')

    def test_canvas_slots_are_independent_of_layer_names(self):
        data = {'type': 'image', 'slots': deepcopy(self.data['slots']), 'content': {'width': 720, 'height': 720, 'json': {'objects': [{'type': 'Textbox', 'name': 'Any layer name', 'templateSlot': 'headline', 'text': 'Hello'}]}}}
        validate_template(data)
        data['content']['json']['objects'][0]['templateSlot'] = 'missing'
        with self.assertRaises(ValueError):
            validate_template(data)

    def test_admin_api_requires_auth_and_returns_product_style_pagination(self):
        from apps.users.utils.token_utils import generate_jwt_token
        from unittest.mock import patch
        url = '/api/templates/admin/templates'
        self.assertEqual(self.client.get(url).status_code, 401)
        token = generate_jwt_token(self.user)
        with patch('apps.templates.views.common.log_action'):
            response = self.client.post(url, self.data, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {token}')
            self.assertEqual(response.status_code, 201, response.content)
            result = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {token}')
            self.assertEqual(result.status_code, 200, result.content)
            self.assertEqual(result.json()['data']['pagination']['current_page'], 1)
            self.assertEqual(result.json()['data']['total'], 1)

    def test_group_values_do_not_leak_between_members_and_writes_are_atomic(self):
        from apps.templates.services.group_service import create_group_instances
        from apps.templates.models import TemplateInstance
        first = save_template(self.data, self.user)
        second = save_template({**self.data, 'name': 'Second'}, self.user)
        group = save_group({'name': 'Pack', 'template_ids': [str(first.id), str(second.id)]})
        items = [{'template_id': str(t.id), 'template_revision': 1, 'values': {'headline': value}} for t, value in [(first, 'One'), (second, 'Two')]]
        result = create_group_instances(group.id, {'revision': 1, 'items': items}, self.user)
        self.assertEqual([i['resolved']['content']['text'] for i in result['instances']], ['One / One', 'Two / Two'])
        items[1]['values']['headline'] = ''
        with self.assertRaises(ValueError):
            create_group_instances(group.id, {'revision': 1, 'items': items}, self.user)
        self.assertEqual(TemplateInstance.objects.count(), 2)
