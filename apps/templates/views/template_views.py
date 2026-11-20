from estore.utils.responses import APIResponse
from apps.templates.models import Template
from apps.templates.schemas import serialize_template, resolve
from apps.templates.services import save_template, check_revision
from .common import endpoint
from apps.templates.selectors.template_selectors import page, template_queryset

@endpoint(['GET', 'POST'])
def templates(request):
    if request.method == 'POST':
        return APIResponse.created({'template': serialize_template(save_template(request.template_data, request.user))})
    qs = template_queryset()
    if request.GET.get('type'):
        qs = qs.filter(type=request.GET['type'])
    categories = request.GET.getlist('category')
    if categories:
        qs = qs.filter(categories__id__in=categories).distinct()
    return page(request, qs, serialize_template, 'templates')


@endpoint(['GET', 'PATCH'])
def template_detail(request, pk):
    obj = Template.objects.get(pk=pk) if request.method == 'GET' else save_template(request.template_data, request.user, pk)
    return APIResponse.success({'template': serialize_template(obj)})


@endpoint(['POST'])
def duplicate_template(request, pk):
    data = serialize_template(Template.objects.get(pk=pk))
    data.update(name=f'{data["name"][:190]} copy', status='draft')
    return APIResponse.created({'template': serialize_template(save_template(data, request.user))})


@endpoint(['POST'])
def preview(request, pk):
    obj = Template.objects.get(pk=pk)
    check_revision(obj, {'revision': request.template_data.get('template_revision')})
    return APIResponse.success({'preview': resolve(serialize_template(obj), request.template_data.get('values', {}), required=False)})

