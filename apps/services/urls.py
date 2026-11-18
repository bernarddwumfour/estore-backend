from django.urls import path
from .views.service_views import service_list, service_detail, admin_services, admin_service_detail
from .views.category_views import category_list, category_detail, admin_service_categories, admin_service_category_detail
from .views.option_views import admin_all_service_options, admin_service_options, admin_service_option_detail
from .views.image_views import admin_service_images, admin_service_image_delete
from .views.logging import log_service_request
from .views.request_views import service_requests, admin_service_requests
from .views.booking_views import slots, appointments, appointment_detail, booking_settings, admin_appointments, admin_appointment_detail, booking_exceptions

app_name = "services"

urlpatterns = [
    path("/availability", slots, name="availability"),
    path("/appointments", appointments, name="appointments"),
    path("/appointments/<uuid:appointment_id>", appointment_detail, name="appointment-detail"),
    path("/admin/booking-exceptions", booking_exceptions, name="booking-exceptions"),
    path("/admin/booking-settings", booking_settings, name="booking-settings"),
    path("/admin/appointments", admin_appointments, name="admin-appointments"),
    path("/admin/appointments/<uuid:appointment_id>", admin_appointment_detail, name="admin-appointment-detail"),
    path("/requests", service_requests, name="service-requests"),
    path("/admin/requests", admin_service_requests, name="admin-service-requests"),
    path("", service_list, name="service-list"),
    path("/categories", category_list, name="category-list"),
    path("/categories/<slug:slug>", category_detail, name="category-detail"),
    path("/admin/services", admin_services, name="admin-services"),
    path("/admin/options", admin_all_service_options, name="admin-all-service-options"),
    path("/admin/services/<uuid:service_id>", admin_service_detail, name="admin-service-detail"),
    path("/admin/services/<uuid:service_id>/options", admin_service_options, name="admin-service-options"),
    path("/admin/services/<uuid:service_id>/options/<uuid:option_id>", admin_service_option_detail, name="admin-service-option-detail"),
    path("/admin/services/<uuid:service_id>/images", admin_service_images, name="admin-service-images"),
    path("/admin/services/<uuid:service_id>/images/<uuid:image_id>", admin_service_image_delete, name="admin-service-image-delete"),
    path("/admin/categories", admin_service_categories, name="admin-categories"),
    path("/admin/categories/<uuid:category_id>", admin_service_category_detail, name="admin-category-detail"),
    path("/<slug:slug>", service_detail, name="service-detail"),
]

for pattern in urlpatterns:
    pattern.callback = log_service_request(pattern.callback)
