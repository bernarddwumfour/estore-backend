import copy
import re
from urllib.parse import urlparse

KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
TOKEN = re.compile(r'{{\s*([A-Za-z][A-Za-z0-9_]*)\s*}}')


def validate_values(data, values, required=True):
    if not isinstance(values, dict):
        raise ValueError('Slot values must be an object.')
    definitions = {s['key']: s for s in data['slots']}
    if set(values) - set(definitions):
        raise ValueError('Values contain an unknown slot.')
    result = {}
    for key, slot in definitions.items():
        value = values.get(key, slot.get('default_value', ''))
        if not isinstance(value, str):
            raise ValueError(f'{key}: supply text or an image URL.')
        if required and slot.get('required') and not value.strip():
            raise ValueError(f'{slot["label"]} is required.')
        if slot['type'] == 'image' and value and not valid_image_url(value):
            raise ValueError(f'{key}: upload an image or use an HTTP(S) image URL.')
        result[key] = value
    return result


def valid_image_url(value):
    return isinstance(value, str) and (value.startswith('/') and not value.startswith('//') or urlparse(value).scheme in ('https', 'http'))


def validate_template(data):
    if data.get('type') not in ('text', 'image'):
        raise ValueError('Select a text or image template.')
    slots = data.get('slots', [])
    if not isinstance(slots, list):
        raise ValueError('Slots must be a list.')
    keys = set()
    for slot in slots:
        if not isinstance(slot, dict) or not isinstance(slot.get('key'), str) or not KEY.fullmatch(slot['key']):
            raise ValueError('Slot keys must start with a letter and contain letters, digits or underscores.')
        if slot['key'] in keys:
            raise ValueError('Slot keys must be unique within the template.')
        keys.add(slot['key'])
        if slot.get('type') not in ('text', 'image') or not isinstance(slot.get('label'), str) or not slot['label'].strip():
            raise ValueError('Each slot needs a label and text/image type.')
        if 'required' in slot and not isinstance(slot['required'], bool):
            raise ValueError('Required must be a boolean.')
    content = data.get('content')
    if not isinstance(content, dict):
        raise ValueError('Template content must be an object.')
    definitions = {s['key']: s for s in slots}
    if data['type'] == 'text':
        if not isinstance(content.get('text'), str):
            raise ValueError('Text templates need a text body.')
        if any(s['type'] != 'text' for s in slots):
            raise ValueError('Plain text templates support text slots. Use image templates for image slots.')
        if set(TOKEN.findall(content['text'])) - keys:
            raise ValueError('The text references undefined slots.')
    else:
        for dimension in ('width', 'height'):
            value = content.get(dimension)
            if type(value) is not int or not 1 <= value <= 8192:
                raise ValueError('Canvas dimensions must be between 1 and 8192 pixels.')
        canvas = content.get('json')
        if not isinstance(canvas, dict) or not isinstance(canvas.get('objects'), list):
            raise ValueError('An image template needs Fabric canvas JSON.')
        def inspect(node):
            if isinstance(node, dict):
                key = node.get('templateSlot')
                if key:
                    if key not in definitions:
                        raise ValueError('A canvas element references an undefined slot.')
                    kind = str(node.get('type', '')).lower()
                    if definitions[key]['type'] == 'text' and kind not in ('textbox', 'text', 'i-text'):
                        raise ValueError('Text slots must reference text elements.')
                    if definitions[key]['type'] == 'image' and kind not in ('image', 'rect', 'textbox'):
                        raise ValueError('Image slots must reference images or image placeholders.')
                if 'src' in node and not valid_image_url(node['src']):
                    raise ValueError('Upload embedded images before saving the template.')
                for value in node.values():
                    inspect(value)
            elif isinstance(node, list):
                for value in node:
                    inspect(value)
        inspect(canvas)
    validate_values(data, {}, required=False)
    return data


def resolve(data, values, required=True):
    values = validate_values(data, values, required=required)
    content = copy.deepcopy(data['content'])
    if data['type'] == 'text':
        content['text'] = TOKEN.sub(lambda match: values[match.group(1)], content['text'])
    # Image values are applied by the browser renderer, using explicit templateSlot metadata.
    return {'type': data['type'], 'content': content, 'slots': data['slots'], 'values': values}


def serialize_template(obj):
    return dict(id=str(obj.id), name=obj.name, description=obj.description, type=obj.type,
                status=obj.status, content=obj.content, slots=obj.slots, revision=obj.revision,
                schema_version=obj.schema_version, category_ids=[str(c.id) for c in obj.categories.all()],
                updated_at=obj.updated_at.isoformat(), groups=[{'id': str(i.group_id), 'name': i.group.name} for i in obj.group_items.select_related('group').all()])


def serialize_group(obj):
    return dict(id=str(obj.id), name=obj.name, description=obj.description, status=obj.status,
                revision=obj.revision, template_ids=[str(i.template_id) for i in obj.items.all()])


def serialize_instance(obj):
    return dict(id=str(obj.id), name=obj.name, snapshot=obj.snapshot, values=obj.values,
                resolved=obj.resolved, revision=obj.revision, batch_id=str(obj.batch_id) if obj.batch_id else None,
                group_name=obj.group_name, updated_at=obj.updated_at.isoformat())
