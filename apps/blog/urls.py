"""blog/urls.py — URL configuration for the blog app."""

from django.urls import path

from .views import blog_category_views, blog_post_views

app_name = "blog"

urlpatterns = [
    # --- Public endpoints ---
    path("/posts", blog_post_views.list_posts_view, name="list-posts"),
    path("/posts/<slug:slug>", blog_post_views.post_detail, name="post-detail"),
    path("/categories", blog_category_views.list_categories_view, name="list-categories"),

    # --- Admin post endpoints ---
    # Specific paths MUST come before the <slug:id> catch-all (RULES.md §10).
    path("/admin/posts", blog_post_views.admin_list_posts, name="admin-list-posts"),
    path("/admin/posts/create", blog_post_views.admin_create_post, name="admin-create-post"),
    path("/admin/posts/bulk-action", blog_post_views.admin_bulk_action_posts, name="admin-bulk-action-posts"),
    path("/admin/posts/<slug:id>", blog_post_views.admin_post_detail, name="admin-post-detail"),
    path("/admin/posts/<slug:id>/update", blog_post_views.admin_update_post, name="admin-update-post"),
    path("/admin/posts/<slug:id>/publish", blog_post_views.admin_publish_post, name="admin-publish-post"),
    path("/admin/posts/<slug:id>/archive", blog_post_views.admin_archive_post, name="admin-archive-post"),
    path("/admin/posts/<slug:id>/delete", blog_post_views.admin_delete_post, name="admin-delete-post"),

    # --- Admin category endpoints ---
    path("/admin/categories", blog_category_views.admin_list_categories, name="admin-list-categories"),
    path("/admin/categories/create", blog_category_views.admin_create_category, name="admin-create-category"),
    path("/admin/categories/<slug:id>/update", blog_category_views.admin_update_category, name="admin-update-category"),
    path("/admin/categories/<slug:id>/delete", blog_category_views.admin_delete_category, name="admin-delete-category"),
]
