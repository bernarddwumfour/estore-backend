import uuid
from django.db import transaction
from apps.templates.models import TemplateGroup
from apps.templates.services.template_service import check_revision, save_instance
from apps.templates.schemas import serialize_instance

@transaction.atomic
def create_group_instances(pk, data, user):
    group = TemplateGroup.objects.select_for_update().get(pk=pk)
    check_revision(group, data)
    if group.status == 'archived':
        raise ValueError('This group is archived.')
    submitted = data.get('items', [])
    if not isinstance(submitted, list) or any(not isinstance(i, dict) for i in submitted):
        raise ValueError('Supply the values for each group member.')
    ids = [str(i.template_id) for i in group.items.all()]
    if len(submitted) != len(ids) or set(i.get('template_id') for i in submitted) != set(ids):
        raise ValueError('Supply every group member exactly once.')
    batch = uuid.uuid4()
    instances = []
    for data in submitted:
        obj = save_instance(data, user)
        obj.batch_id, obj.group_name = batch, group.name
        obj.save(update_fields=['batch_id', 'group_name'])
        instances.append(serialize_instance(obj))
    return {'instances': instances, 'batch_id': str(batch)}

