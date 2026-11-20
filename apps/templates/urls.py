from django.urls import path
from . import views

app_name = 'templates'
urlpatterns = [
    path('/admin/templates', views.templates, name="admin-templates"),
    path('/admin/templates/<uuid:pk>', views.template_detail, name="admin-template-detail"),
    path('/admin/templates/<uuid:pk>/duplicate', views.duplicate_template, name="admin-duplicate-template"),
    path('/admin/templates/<uuid:pk>/preview', views.preview, name="admin-preview"),
    path('/admin/categories', views.categories, name="admin-categories"),
    path('/admin/categories/<uuid:pk>', views.category_detail, name="admin-category-detail"),
    path('/admin/groups', views.groups, name="admin-groups"),
    path('/admin/groups/<uuid:pk>', views.group_detail, name="admin-group-detail"),
    path('/admin/groups/<uuid:pk>/duplicate', views.duplicate_group, name="admin-duplicate-group"),
    path('/admin/groups/<uuid:pk>/use', views.use_group, name="admin-use-group"),
    path('/admin/instances', views.instances, name="admin-instances"),
    path('/admin/instances/<uuid:pk>', views.instance_detail, name="admin-instance-detail"),
    path('/admin/assets', views.assets, name="admin-assets"),
]
