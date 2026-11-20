from estore.utils.responses import APIResponse
from apps.templates.models import TemplateCategory
from apps.templates.services.category_service import save_category
from .common import endpoint
from apps.templates.selectors.template_selectors import page, template_queryset

def category_json(obj):
    return dict(id=str(obj.id), name=obj.name, description=obj.description, is_active=obj.is_active)


@endpoint(['GET', 'POST'])
def categories(request):
    if request.method == 'GET':
        return page(request, TemplateCategory.objects.all(), category_json, 'categories')
    return APIResponse.created({'category': category_json(save_category(request.template_data))})




@endpoint(['PATCH'])
def category_detail(request, pk):
    return APIResponse.success({'category': category_json(save_category(request.template_data, pk))})


