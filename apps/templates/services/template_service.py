import copy
from django.db import transaction
from apps.templates.models import Template, TemplateCategory, TemplateGroup, TemplateGroupItem, TemplateInstance
from apps.templates.schemas import validate_template, resolve, serialize_template


class RevisionConflict(Exception):
    pass


def check_revision(obj, data):
    if data.get('revision') != obj.revision:
        raise RevisionConflict('This record changed. Reload it before saving again.')


def fields(data):
    name = data.get('name')
    description = data.get('description', '')
    status = data.get('status', 'draft')
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('A name of up to 200 characters is required.')
    if not isinstance(description, str) or status not in ('draft', 'active', 'archived'):
        raise ValueError('Invalid description or status.')
    return dict(name=name.strip(), description=description, status=status)


def related_ids(model, ids):
    if not isinstance(ids, list) or len(set(map(str, ids))) != len(ids):
        raise ValueError('Supply a list of unique IDs.')
    objects = list(model.objects.filter(id__in=ids))
    if len(objects) != len(ids):
        raise ValueError('One or more selected records no longer exist.')
    return objects


@transaction.atomic
def save_template(data, user, pk=None):
    cleaned = fields(data)
    validate_template(data)
    categories = related_ids(TemplateCategory, data.get('category_ids', []))
    if pk:
        obj = Template.objects.select_for_update().get(pk=pk)
        check_revision(obj, data)
        if obj.type != data['type']:
            raise ValueError('A template type cannot be changed after creation.')
        obj.revision += 1
    else:
        obj = Template(created_by=user)
    for key, value in {**cleaned, 'type': data['type'], 'content': data['content'], 'slots': data.get('slots', [])}.items():
        setattr(obj, key, value)
    obj.save()
    obj.categories.set(categories)
    return obj


@transaction.atomic
def save_group(data, pk=None):
    cleaned = fields(data)
    ids = data.get('template_ids', [])
    related_ids(Template, ids)
    if pk:
        obj = TemplateGroup.objects.select_for_update().get(pk=pk)
        check_revision(obj, data)
        obj.revision += 1
    else:
        obj = TemplateGroup()
    for key, value in cleaned.items():
        setattr(obj, key, value)
    obj.save()
    obj.items.all().delete()
    TemplateGroupItem.objects.bulk_create([TemplateGroupItem(group=obj, template_id=pk, position=i) for i, pk in enumerate(ids)])
    return obj


@transaction.atomic
def save_instance(data, user, pk=None):
    if pk:
        obj = TemplateInstance.objects.select_for_update().get(pk=pk)
        check_revision(obj, data)
        obj.revision += 1
    else:
        template = Template.objects.select_for_update().get(pk=data.get('template_id'))
        check_revision(template, {'revision': data.get('template_revision')})
        if template.status == 'archived':
            raise ValueError('Archived templates cannot be used for new results.')
        obj = TemplateInstance(template=template, created_by=user, snapshot=copy.deepcopy(serialize_template(template)))
    obj.name = fields({'name': data.get('name', obj.snapshot['name'])})['name']
    obj.resolved = resolve(obj.snapshot, data.get('values', {}))
    obj.values = obj.resolved['values']
    obj.save()
    return obj
