from estore.utils.responses import APIResponse
from apps.templates.models import TemplateGroup
from apps.templates.schemas import serialize_group
from apps.templates.services import save_group
from apps.templates.services.group_service import create_group_instances
from .common import endpoint
from apps.templates.selectors.template_selectors import page, template_queryset

@endpoint(['GET', 'POST'])
def groups(request):
    if request.method == 'GET':
        return page(request, TemplateGroup.objects.prefetch_related('items'), serialize_group, 'groups')
    return APIResponse.created({'group': serialize_group(save_group(request.template_data))})


@endpoint(['GET', 'PATCH'])
def group_detail(request, pk):
    obj = TemplateGroup.objects.get(pk=pk) if request.method == 'GET' else save_group(request.template_data, pk)
    return APIResponse.success({'group': serialize_group(obj)})


@endpoint(['POST'])
def duplicate_group(request, pk):
    data = serialize_group(TemplateGroup.objects.get(pk=pk))
    data.update(name=f'{data["name"][:190]} copy', status='draft')
    return APIResponse.created({'group': serialize_group(save_group(data))})


@endpoint(['POST'])
def use_group(request, pk):
    return APIResponse.created(create_group_instances(pk, request.template_data, request.user))
