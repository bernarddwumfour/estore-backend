# common/analytics.py
"""
Reusable, scalable analytics framework for all apps
Uses caching, optimized queries, and materialized views
"""
from django.core.cache import cache
from django.db import  connection
from typing import Dict, List
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class AnalyticsQueryOptimizer:
    """Optimize analytics queries with caching and batch processing"""
    
    @staticmethod
    def cached(timeout=300, key_prefix='analytics'):
        """Cache decorator for analytics functions"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key
                cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
                
                # Try to get from cache
                cached_data = cache.get(cache_key)
                if cached_data is not None:
                    return cached_data
                
                # Execute function
                result = func(*args, **kwargs)
                
                # Store in cache
                cache.set(cache_key, result, timeout)
                return result
            return wrapper
        return decorator
    
    @staticmethod
    def batch_queryset(queryset, batch_size=1000):
        """Process large querysets in batches to avoid memory issues"""
        total = queryset.count()
        for offset in range(0, total, batch_size):
            yield list(queryset[offset:offset + batch_size])


class MaterializedViewManager:
    """Manage materialized views for heavy analytics queries"""
    
    @staticmethod
    def refresh_view(view_name: str, concurrently: bool = True):
        """Refresh a materialized view"""
        concurrently_sql = "CONCURRENTLY" if concurrently else ""
        with connection.cursor() as cursor:
            cursor.execute(f"REFRESH MATERIALIZED VIEW {concurrently_sql} {view_name};")
    
    @staticmethod
    def create_product_stats_view():
        """Create materialized view for product statistics"""
        sql = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS product_stats_mv AS
        SELECT 
            p.id,
            p.status,
            p.is_featured,
            p.is_bestseller,
            p.is_new,
            p.created_at::date as created_date,
            p.category_id,
            COUNT(DISTINCT pv.id) as variant_count,
            COALESCE(SUM(pv.stock), 0) as total_stock,
            COALESCE(SUM(pv.price * pv.stock), 0) as inventory_value,
            COALESCE(AVG(pr.rating), 0) as avg_rating,
            COUNT(DISTINCT pr.id) as review_count
        FROM products_product p
        LEFT JOIN products_productvariant pv ON p.id = pv.product_id
        LEFT JOIN products_productreview pr ON p.id = pr.product_id AND pr.is_approved = true
        GROUP BY p.id, p.status, p.is_featured, p.is_bestseller, p.is_new, p.created_at, p.category_id;
        """
        with connection.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_product_stats_mv_id ON product_stats_mv (id);")


class BaseAnalyticsService:
    """Base analytics service that all app analytics inherit from"""
    
    def __init__(self, app_name: str, cache_timeout: int = 300):
        self.app_name = app_name
        self.cache_timeout = cache_timeout
        self.optimizer = AnalyticsQueryOptimizer()
    
    def get_card_data(self, request) -> List[Dict]:
        """Override in child classes"""
        raise NotImplementedError
    
    def get_chart_data(self, request, chart_type: str = None) -> Dict:
        """Override in child classes"""
        raise NotImplementedError
    
    @AnalyticsQueryOptimizer.cached(timeout=300)
    def get_dashboard_data(self, request) -> Dict:
        """Get complete dashboard data (cards + charts)"""
        return {
            "cards": self.get_card_data(request),
            "charts": self.get_chart_data(request)
        }


class AggregatedMetrics:
    """Efficient aggregation using Django's aggregation API"""
    
    @staticmethod
    def get_counts(queryset, **filters):
        """Get multiple counts in a single query"""
        from django.db.models import Count, Q
        
        aggregations = {}
        for name, filter_kwargs in filters.items():
            aggregations[name] = Count('id', filter=Q(**filter_kwargs))
        
        return queryset.aggregate(**aggregations)
    
    @staticmethod
    def get_time_series(queryset, date_field: str, group_by: str = 'month', 
                        value_field: str = 'id', aggregation: str = 'count'):
        """
        Get time series data efficiently
        
        group_by: 'day', 'week', 'month', 'year'
        aggregation: 'count', 'sum', 'avg'
        """
        from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear
        from django.db.models import Count, Sum, Avg
        
        trunc_map = {
            'day': TruncDay,
            'week': TruncWeek,
            'month': TruncMonth,
            'year': TruncYear
        }
        
        agg_map = {
            'count': Count(value_field),
            'sum': Sum(value_field),
            'avg': Avg(value_field)
        }
        
        trunc_func = trunc_map.get(group_by, TruncMonth)
        agg_func = agg_map.get(aggregation, Count(value_field))
        
        return queryset.annotate(
            period=trunc_func(date_field)
        ).values('period').annotate(
            value=agg_func
        ).order_by('period')