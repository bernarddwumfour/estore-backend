from apps.templates.models import TemplateCategory

def save_category(data, pk=None):
    if not isinstance(data.get('name'), str) or not data['name'].strip() or len(data['name']) > 120:
        raise ValueError('A category name of up to 120 characters is required.')
    if not isinstance(data.get('description', ''), str) or not isinstance(data.get('is_active', True), bool):
        raise ValueError('Invalid category fields.')
    obj = TemplateCategory.objects.get(pk=pk) if pk else TemplateCategory()
    obj.name, obj.description, obj.is_active = data['name'].strip(), data.get('description', ''), data.get('is_active', True)
    obj.save()
    return obj

