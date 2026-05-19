# from celery import shared_task


# @shared_task
def precompute_analytics():
    """Precompute analytics data for all apps"""
    from apps.products.services.product_service import product_analytics_service
    # from apps.users.analytics import user_analytics_service
    # from apps.orders.analytics import order_analytics_service
    
    # Precompute product analytics
    product_analytics_service.get_dashboard_data(None)
    
    # Precompute user analytics
    # user_analytics_service.get_dashboard_data(None)
    
    # Precompute order analytics
    # order_analytics_service.get_dashboard_data(None)
    
    return "Analytics precomputed successfully"


# Schedule every 5 minutes in celery beat
CELERY_BEAT_SCHEDULE = {
    'precompute-analytics': {
        'task': 'common.tasks.precompute_analytics',
        'schedule': 300.0,  # Every 5 minutes
    },
}