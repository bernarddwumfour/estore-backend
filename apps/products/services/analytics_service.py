"""
Analytics Service - Business logic for product analytics
"""

import logging
from typing import Dict, Any, List, Optional
from django.db.models import Count, Sum, Avg, Q, F
from django.utils import timezone
from datetime import timedelta

from apps.products.models import Product, ProductVariant, Category, ProductReview
from common.analytics import BaseAnalyticsService, AggregatedMetrics
from common.chart_configs import ChartConfig, ColorPalette

logger = logging.getLogger(__name__)


class ProductAnalyticsService(BaseAnalyticsService):
    """Optimized product analytics service"""

    def __init__(self):
        super().__init__(app_name="products", cache_timeout=300)

    def get_card_data(self, request) -> List[Dict]:
        """Get card data using optimized single-query aggregations"""

        # Single query for all product counts
        product_aggregates = Product.objects.aggregate(
            total=Count("id"),
            published=Count("id", filter=Q(status=Product.STATUS_PUBLISHED)),
            draft=Count("id", filter=Q(status=Product.STATUS_DRAFT)),
            archived=Count("id", filter=Q(status=Product.STATUS_ARCHIVED)),
            featured=Count("id", filter=Q(is_featured=True)),
            bestseller=Count("id", filter=Q(is_bestseller=True)),
            new=Count(
                "id", filter=Q(created_at__gte=timezone.now() - timedelta(days=30))
            ),
            missing_variants=Count("id", filter=Q(variants__isnull=True)),
        )

        # Single query for variant metrics
        variant_aggregates = ProductVariant.objects.aggregate(
            total_variants=Count("id"),
            total_stock=Sum("stock"),
            low_stock=Count(
                "id", filter=Q(stock__lte=F("low_stock_threshold"), stock__gt=0)
            ),
            out_of_stock=Count("id", filter=Q(stock=0)),
            inventory_value=Sum(F("price") * F("stock")),
        )

        # Single query for category metrics
        category_aggregates = Category.objects.aggregate(
            active_categories=Count("id", filter=Q(is_active=True, is_hidden=False))
        )

        # Rating average
        rating_avg = (
            ProductReview.objects.filter(is_approved=True).aggregate(
                avg_rating=Avg("rating")
            )["avg_rating"]
            or 0
        )

        return [
            {
                "id": "total_products",
                "name": "Total Products",
                "value": product_aggregates["total"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "published_products",
                "name": "Published",
                "value": product_aggregates["published"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "draft_products",
                "name": "Draft",
                "value": product_aggregates["draft"] or 0,
                "unit": "",
                "critical": product_aggregates["draft"] > 10,
            },
            {
                "id": "archived_products",
                "name": "Archived",
                "value": product_aggregates["archived"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "total_variants",
                "name": "Total Variants",
                "value": variant_aggregates["total_variants"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "total_stock",
                "name": "Total Stock",
                "value": variant_aggregates["total_stock"] or 0,
                "unit": "units",
                "critical": (variant_aggregates["total_stock"] or 0) < 100,
            },
            {
                "id": "low_stock_variants",
                "name": "Low Stock",
                "value": variant_aggregates["low_stock"] or 0,
                "unit": "variants",
                "critical": (variant_aggregates["low_stock"] or 0) > 5,
            },
            {
                "id": "out_of_stock",
                "name": "Out of Stock",
                "value": variant_aggregates["out_of_stock"] or 0,
                "unit": "variants",
                "critical": (variant_aggregates["out_of_stock"] or 0) > 10,
            },
            {
                "id": "featured_products",
                "name": "Featured",
                "value": product_aggregates["featured"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "bestseller_products",
                "name": "Bestsellers",
                "value": product_aggregates["bestseller"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "new_products",
                "name": "New (30 days)",
                "value": product_aggregates["new"] or 0,
                "unit": "",
                "critical": False,
            },
            {
                "id": "inventory_value",
                "name": "Inventory Value",
                "value": round(variant_aggregates["inventory_value"] or 0, 2),
                "unit": "$",
                "critical": False,
            },
            {
                "id": "products_without_variants",
                "name": "Missing Variants",
                "value": product_aggregates["missing_variants"] or 0,
                "unit": "",
                "critical": (product_aggregates["missing_variants"] or 0) > 5,
            },
            {
                "id": "avg_rating",
                "name": "Average Rating",
                "value": round(rating_avg, 1),
                "unit": "★",
                "critical": rating_avg < 3.5,
            },
            {
                "id": "active_categories",
                "name": "Active Categories",
                "value": category_aggregates["active_categories"] or 0,
                "unit": "",
                "critical": False,
            },
        ]

    def get_chart_data(self, request, chart_type: str = None) -> Dict:
        """Get all chart data with optimized queries"""

        charts = {}

        # Only fetch requested chart type if specified
        if chart_type and chart_type != "all":
            method_name = f"_get_{chart_type}_chart"
            if hasattr(self, method_name):
                charts[chart_type] = getattr(self, method_name)()
        else:
            # Fetch all charts (use caching)
            charts = {
                "monthly_trend": self._get_monthly_trend_chart(),
                "categories": self._get_category_chart(),
                "status_distribution": self._get_status_chart(),
                "stock_distribution": self._get_stock_chart(),
                "weekly_activity": self._get_weekly_chart(),
                "top_products": self._get_top_products_chart(),
                "rating_distribution": self._get_rating_chart(),
                "product_flags": self._get_flags_chart(),
                "category_visibility": self._get_visibility_chart(),
            }

        return charts

    def _get_monthly_trend_chart(self) -> Dict:
        """Get monthly product creation trend using time series aggregation"""
        six_months_ago = timezone.now() - timedelta(days=180)

        time_series = AggregatedMetrics.get_time_series(
            queryset=Product.objects.filter(created_at__gte=six_months_ago),
            date_field="created_at",
            group_by="month",
            value_field="id",
            aggregation="count",
        )

        data = [
            {
                "month": item["period"].strftime("%b") if item["period"] else "Unknown",
                "products": item["value"],
                "full_date": item["period"].isoformat() if item["period"] else None,
            }
            for item in time_series
        ]

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.AREA,
                title="Product Creation Trend",
                description="Number of products created per month",
                data_key="products",
                color="hsl(var(--chart-1))",
            ),
        )

    def _get_category_chart(self) -> Dict:
        """Get products by category - optimized with single query"""
        categories = (
            Category.objects.filter(is_hidden=False)
            .annotate(
                product_count=Count(
                    "products", filter=Q(products__status=Product.STATUS_PUBLISHED)
                )
            )
            .filter(product_count__gt=0)
            .order_by("-product_count")[:10]
        )

        data = [
            {"category": cat.name, "products": cat.product_count} for cat in categories
        ]

        # Add colors
        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Products by Category",
                description="Top categories by product count",
                data_key="products",
            ),
        )

    def _get_status_chart(self) -> Dict:
        """Get product status distribution - from cached aggregates"""
        status_counts = Product.objects.aggregate(
            published=Count("id", filter=Q(status=Product.STATUS_PUBLISHED)),
            draft=Count("id", filter=Q(status=Product.STATUS_DRAFT)),
            archived=Count("id", filter=Q(status=Product.STATUS_ARCHIVED)),
        )

        data = [
            {"status": "Published", "count": status_counts["published"] or 0},
            {"status": "Draft", "count": status_counts["draft"] or 0},
            {"status": "Archived", "count": status_counts["archived"] or 0},
        ]

        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.PIE,
                title="Product Status",
                description="Distribution by publication status",
                data_key="count",
            ),
        )

    def _get_stock_chart(self) -> Dict:
        """Get stock distribution - optimized with conditional aggregation"""
        total_variants = ProductVariant.objects.count() or 1

        stock_stats = ProductVariant.objects.aggregate(
            in_stock=Count("id", filter=Q(stock__gt=10)),
            low_stock=Count("id", filter=Q(stock__lte=10, stock__gt=0)),
            out_of_stock=Count("id", filter=Q(stock=0)),
        )

        data = [
            {
                "status": "In Stock (>10)",
                "count": stock_stats["in_stock"] or 0,
                "percentage": round(
                    (stock_stats["in_stock"] or 0) / total_variants * 100, 1
                ),
            },
            {
                "status": "Low Stock (1-10)",
                "count": stock_stats["low_stock"] or 0,
                "percentage": round(
                    (stock_stats["low_stock"] or 0) / total_variants * 100, 1
                ),
            },
            {
                "status": "Out of Stock",
                "count": stock_stats["out_of_stock"] or 0,
                "percentage": round(
                    (stock_stats["out_of_stock"] or 0) / total_variants * 100, 1
                ),
            },
        ]

        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.DONUT,
                title="Stock Distribution",
                description="Variants by stock availability",
                data_key="count",
            ),
        )

    def _get_weekly_chart(self) -> Dict:
        """Get weekly activity - last 7 days"""
        seven_days_ago = timezone.now() - timedelta(days=7)

        daily_activity = (
            Product.objects.filter(created_at__gte=seven_days_ago)
            .extra({"day": "DATE(created_at)"})
            .values("day")
            .annotate(
                created=Count("id"),
                published=Count("id", filter=Q(status=Product.STATUS_PUBLISHED)),
            )
            .order_by("day")
        )

        # Create a dict for quick lookup
        activity_dict = {item["day"]: item for item in daily_activity}

        # Generate last 7 days
        data = []
        for i in range(7):
            day = (timezone.now() - timedelta(days=6 - i)).date()
            day_activity = activity_dict.get(day, {})
            data.append(
                {
                    "day": day.strftime("%a"),
                    "created": day_activity.get("created", 0),
                    "published": day_activity.get("published", 0),
                }
            )

        return ChartConfig.format_for_shadcn(
            data=data,
            config={
                "title": "Weekly Activity",
                "description": "Last 7 days product activity",
                "type": ChartConfig.BAR,
                "config": {
                    "created": {"label": "Created", "color": "hsl(var(--chart-1))"},
                    "published": {"label": "Published", "color": "hsl(var(--chart-2))"},
                },
            },
        )

    def _get_top_products_chart(self) -> Dict:
        """Get top products by inventory value - limited to 10"""
        top_products = (
            ProductVariant.objects.values("product__id", "product__title")
            .annotate(total_value=Sum(F("price") * F("stock")))
            .order_by("-total_value")[:10]
        )

        data = [
            {
                "product": item["product__title"][:30],
                "value": round(float(item["total_value"] or 0), 2),
            }
            for item in top_products
        ]

        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Top Products by Value",
                description="Highest inventory value products",
                data_key="value",
            ),
        )

    def _get_rating_chart(self) -> Dict:
        """Get rating distribution"""
        ratings = []
        for rating in range(1, 6):
            count = ProductReview.objects.filter(
                rating=rating, is_approved=True
            ).count()
            ratings.append({"rating": f"{rating} ★", "count": count})

        ratings = ColorPalette.add_colors_to_data(ratings, key="fill")

        return ChartConfig.format_for_shadcn(
            data=ratings,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Customer Ratings",
                description="Distribution of product reviews",
                data_key="count",
            ),
        )

    def _get_flags_chart(self) -> Dict:
        """Get products by flag status"""
        flag_counts = Product.objects.aggregate(
            featured=Count("id", filter=Q(is_featured=True)),
            bestseller=Count("id", filter=Q(is_bestseller=True)),
            new=Count("id", filter=Q(is_new=True)),
        )

        data = [
            {"flag": "Featured", "count": flag_counts["featured"] or 0},
            {"flag": "Bestseller", "count": flag_counts["bestseller"] or 0},
            {"flag": "New Arrival", "count": flag_counts["new"] or 0},
        ]

        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.BAR,
                title="Product Highlights",
                description="Products with special flags",
                data_key="count",
            ),
        )

    def _get_visibility_chart(self) -> Dict:
        """Get category visibility distribution"""
        visibility_counts = Category.objects.aggregate(
            visible=Count("id", filter=Q(is_hidden=False, is_active=True)),
            hidden=Count("id", filter=Q(is_hidden=True)),
        )

        data = [
            {"status": "Visible", "count": visibility_counts["visible"] or 0},
            {"status": "Hidden", "count": visibility_counts["hidden"] or 0},
        ]

        data = ColorPalette.add_colors_to_data(data, key="fill")

        return ChartConfig.format_for_shadcn(
            data=data,
            config=ChartConfig.create_config(
                chart_type=ChartConfig.PIE,
                title="Category Visibility",
                description="Hidden vs visible categories",
                data_key="count",
            ),
        )


# Singleton instance
product_analytics_service = ProductAnalyticsService()