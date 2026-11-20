"""Template database read operations and admin pagination."""
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from apps.common.utils import sanitize_search_query
from apps.templates.models import Template, TemplateGroupItem
from estore.utils.responses import APIResponse


def template_queryset():
    return Template.objects.prefetch_related('categories', Prefetch('group_items', queryset=TemplateGroupItem.objects.select_related('group')))


def page(request, queryset, serializer, key):
    search = sanitize_search_query(request.GET.get('search', ''))
    if search:
        queryset = queryset.filter(Q(name__icontains=search))
    status = request.GET.get('status')
    if status and hasattr(queryset.model, 'status'):
        queryset = queryset.filter(status=status)
    elif status and hasattr(queryset.model, 'is_active'):
        queryset = queryset.filter(is_active=status == 'active')
    sort_by = request.GET.get('sort_by', 'name')
    allowed = {'name', 'updated_at'} if hasattr(queryset.model, 'updated_at') else {'name'}
    if sort_by not in allowed:
        raise ValueError('Invalid sort field.')
    queryset = queryset.order_by(('-' if request.GET.get('sort_order') == 'desc' else '') + sort_by, 'pk')
    paginator = Paginator(queryset, max(1, min(100, int(request.GET.get('limit', 20)))))
    result = paginator.get_page(max(1, int(request.GET.get('page', 1))))
    pagination = {'current_page': result.number, 'per_page': paginator.per_page,
        'total': paginator.count, 'total_pages': paginator.num_pages,
        'has_next': result.has_next(), 'has_previous': result.has_previous(),
        'next_page': result.next_page_number() if result.has_next() else None,
        'previous_page': result.previous_page_number() if result.has_previous() else None,
        'start_index': result.start_index(), 'end_index': result.end_index()}
    return APIResponse.success({key: [serializer(o) for o in result], 'pagination': pagination, 'total': paginator.count})
