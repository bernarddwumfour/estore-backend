from estore.utils.responses import APIResponse
from apps.templates.models import TemplateInstance
from apps.templates.schemas import serialize_instance
from apps.templates.services import save_instance
from .common import endpoint
from apps.templates.selectors.template_selectors import page, template_queryset

@endpoint(['GET', 'POST'])
def instances(request):
    if request.method == 'GET':
        qs = TemplateInstance.objects.all()
        if request.GET.get('batch_id'):
            qs = qs.filter(batch_id=request.GET['batch_id'])
        return page(request, qs, serialize_instance, 'instances')
    return APIResponse.created({'instance': serialize_instance(save_instance(request.template_data, request.user))})


@endpoint(['GET', 'PATCH', 'DELETE'])
def instance_detail(request, pk):
    obj = TemplateInstance.objects.get(pk=pk)
    if request.method == 'DELETE':
        obj.delete()
        return APIResponse.no_content()
    if request.method == 'PATCH':
        obj = save_instance(request.template_data, request.user, pk)
    return APIResponse.success({'instance': serialize_instance(obj)})

