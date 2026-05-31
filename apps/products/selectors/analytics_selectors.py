"""
Product Analytics Selectors - Comprehensive e-commerce analytics
"""

from django.db.models import Sum, Count, Avg, Q, F, Min, Max
from django.db.models.functions import TruncDay,  Coalesce
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from apps.products.models import (
    Product,
    ProductVariant,
    Category,
    Brand,
    ProductReview,
    Wishlist,
)
from apps.orders.models import OrderItem, Order


class ProductAnalyticsSelector:
    """Enhanced selector for product analytics"""

    @staticmethod
    def get_overview_stats(
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get overview statistics for products"""

        product_qs = Product.objects.all()
        if start_date:
            product_qs = product_qs.filter(created_at__gte=start_date)
        if end_date:
            product_qs = product_qs.filter(created_at__lte=end_date)

        total_products = product_qs.count()
        active_products = product_qs.filter(status=Product.STATUS_PUBLISHED).count()
        draft_products = product_qs.filter(status=Product.STATUS_DRAFT).count()
        archived_products = product_qs.filter(status=Product.STATUS_ARCHIVED).count()

        variant_qs = ProductVariant.objects.filter(is_active=True)
        total_variants = variant_qs.count()

        total_categories = Category.objects.filter(is_active=True).count()
        total_brands = Brand.objects.filter(is_active=True).count()

        stock_agg = variant_qs.aggregate(
            total_stock=Sum("stock"), total_value=Sum(F("price") * F("stock"))
        )

        out_of_stock_variants = variant_qs.filter(stock=0).count()
        low_stock_variants = variant_qs.filter(
            stock__lte=F("low_stock_threshold"), stock__gt=0
        ).count()

        total_reviews = ProductReview.objects.filter(is_approved=True).count()
        avg_rating = (
            ProductReview.objects.filter(is_approved=True).aggregate(avg=Avg("rating"))[
                "avg"
            ]
            or 0
        )

        total_wishlists = Wishlist.objects.count()
        products_with_reviews = (
            ProductReview.objects.filter(is_approved=True)
            .values("product")
            .distinct()
            .count()
        )

        thirty_days_ago = timezone.now() - timedelta(days=30)
        products_added_30d = Product.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()
        products_updated_30d = Product.objects.filter(
            updated_at__gte=thirty_days_ago
        ).count()
        variants_added_30d = ProductVariant.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()

        return {
            "summary": {
                "total_products": total_products,
                "total_variants": total_variants,
                "active_products": active_products,
                "draft_products": draft_products,
                "archived_products": archived_products,
                "total_categories": total_categories,
                "total_brands": total_brands,
            },
            "inventory_summary": {
                "total_stock": stock_agg["total_stock"] or 0,
                "out_of_stock_variants": out_of_stock_variants,
                "low_stock_variants": low_stock_variants,
                "total_inventory_value": float(stock_agg["total_value"] or 0),
            },
            "engagement": {
                "total_reviews": total_reviews,
                "average_rating": round(float(avg_rating), 1),
                "total_wishlists": total_wishlists,
                "products_with_reviews": products_with_reviews,
            },
            "recent_activity": {
                "products_added_30d": products_added_30d,
                "products_updated_30d": products_updated_30d,
                "variants_added_30d": variants_added_30d,
            },
        }

    @staticmethod
    def get_sales_performance(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category_id: Optional[str] = None,
        brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive sales performance metrics"""

        order_items = OrderItem.objects.filter(order__payment_status=Order.PAYMENT_PAID)

        if start_date:
            order_items = order_items.filter(order__created_at__gte=start_date)
        if end_date:
            order_items = order_items.filter(order__created_at__lte=end_date)

        if category_id:
            order_items = order_items.filter(variant__product__category_id=category_id)

        # Sales summary
        sales_summary = order_items.aggregate(
            total_revenue=Coalesce(Sum("total_price"), Decimal("0.00")),
            total_quantity=Coalesce(Sum("quantity"), 0),
            total_orders=Count("order", distinct=True),
            avg_order_value=Coalesce(Avg("order__total"), Decimal("0.00")),
            avg_unit_price=Coalesce(Avg("unit_price"), Decimal("0.00")),
        )

        # Items per order average
        items_per_order = (
            order_items.values("order")
            .annotate(items_count=Sum("quantity"))
            .aggregate(avg=Avg("items_count"))["avg"]
            or 0
        )

        # Top selling products
        top_products = (
            order_items.values("variant__product__id", "variant__product__title")
            .annotate(
                quantity_sold=Sum("quantity"),
                revenue=Sum("total_price"),
                orders=Count("order", distinct=True),
            )
            .order_by("-revenue")[:10]
        )

        # Products with zero sales
        products_with_sales_ids = set(
            order_items.values_list("variant__product__id", flat=True)
        )
        products_without_sales = (
            Product.objects.filter(status=Product.STATUS_PUBLISHED)
            .exclude(id__in=products_with_sales_ids)
            .count()
        )

        # Revenue trends
        revenue_trends = (
            order_items.annotate(day=TruncDay("order__created_at"))
            .values("day")
            .annotate(revenue=Sum("total_price"), orders=Count("order", distinct=True))
            .order_by("-day")[:30]
        )

        return {
            "sales_summary": {
                "total_revenue": float(sales_summary["total_revenue"]),
                "total_quantity_sold": sales_summary["total_quantity"],
                "total_orders": sales_summary["total_orders"],
                "average_order_value": float(sales_summary["avg_order_value"]),
                "average_unit_price": float(sales_summary["avg_unit_price"]),
                "items_per_order": round(items_per_order, 2),
            },
            "top_products": [
                {
                    "product_id": str(p["variant__product__id"]),
                    "title": p["variant__product__title"],
                    "quantity_sold": p["quantity_sold"],
                    "revenue": float(p["revenue"]),
                    "orders": p["orders"],
                }
                for p in top_products
            ],
            "products_without_sales": products_without_sales,
            "revenue_trends": [
                {
                    "date": t["day"].isoformat() if t["day"] else None,
                    "revenue": float(t["revenue"] or 0),
                    "orders": t["orders"],
                }
                for t in revenue_trends
            ],
        }

    @staticmethod
    def get_product_funnel_analytics(
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get product conversion funnel metrics"""

        total_products = Product.objects.filter(status=Product.STATUS_PUBLISHED).count()

        # Products with wishlist adds
        products_with_wishlists = (
            Wishlist.objects.values("variant__product").distinct().count()
        )

        # Products with purchases
        order_items = OrderItem.objects.filter(order__payment_status=Order.PAYMENT_PAID)
        if start_date:
            order_items = order_items.filter(order__created_at__gte=start_date)
        if end_date:
            order_items = order_items.filter(order__created_at__lte=end_date)

        products_with_purchases = (
            order_items.values("variant__product").distinct().count()
        )

        # Products with cart adds (simplified - same as purchases for now)
        products_with_carts = products_with_purchases

        # Calculate percentages
        wishlist_to_cart = (
            (products_with_carts / products_with_wishlists * 100)
            if products_with_wishlists > 0
            else 0
        )
        cart_to_purchase = (
            (products_with_purchases / products_with_carts * 100)
            if products_with_carts > 0
            else 0
        )

        return {
            "total_products": total_products,
            "products_with_views": 0,  # Placeholder for analytics service
            "products_with_wishlists": products_with_wishlists,
            "products_with_carts": products_with_carts,
            "products_with_purchases": products_with_purchases,
            "conversion_rates": {
                "view_to_wishlist": 0,
                "wishlist_to_cart": round(wishlist_to_cart, 2),
                "cart_to_purchase": round(cart_to_purchase, 2),
                "overall_conversion": (
                    round((products_with_purchases / total_products * 100), 2)
                    if total_products > 0
                    else 0
                ),
            },
        }

    @staticmethod
    def get_inventory_health_metrics() -> Dict[str, Any]:
        """Get detailed inventory health metrics"""

        variants = ProductVariant.objects.filter(is_active=True)

        ninety_days_ago = timezone.now() - timedelta(days=90)

        turnover_data = []
        for variant in variants[:50]:
            sales_90d = (
                OrderItem.objects.filter(
                    variant=variant,
                    order__payment_status=Order.PAYMENT_PAID,
                    order__created_at__gte=ninety_days_ago,
                ).aggregate(total=Sum("quantity"))["total"]
                or 0
            )

            average_inventory = (variant.stock + variant.stock) / 2
            turnover_rate = (
                sales_90d / average_inventory if average_inventory > 0 else 0
            )

            days_of_stock = (variant.stock / (sales_90d / 90)) if sales_90d > 0 else 999

            turnover_data.append(
                {
                    "variant_id": str(variant.id),
                    "sku": variant.sku,
                    "product_title": variant.product.title,
                    "current_stock": variant.stock,
                    "sales_last_90d": sales_90d,
                    "turnover_rate": round(turnover_rate, 2),
                    "days_of_stock": round(days_of_stock),
                    "reorder_point": variant.low_stock_threshold,
                }
            )

        turnover_data.sort(key=lambda x: x["days_of_stock"])

        slow_movers = [t for t in turnover_data if t["days_of_stock"] > 90]
        fast_movers = [t for t in turnover_data if t["days_of_stock"] < 15]

        avg_turnover = (
            sum(t["turnover_rate"] for t in turnover_data) / len(turnover_data)
            if turnover_data
            else 0
        )

        return {
            "summary": {
                "total_variants_analyzed": len(turnover_data),
                "average_turnover_rate": round(avg_turnover, 2),
                "slow_movers_count": len(slow_movers),
                "fast_movers_count": len(fast_movers),
            },
            "slow_movers": slow_movers[:10],
            "fast_movers": fast_movers[:10],
            "reorder_recommendations": [
                {
                    "variant_id": t["variant_id"],
                    "sku": t["sku"],
                    "product_title": t["product_title"],
                    "current_stock": t["current_stock"],
                    "days_until_out": t["days_of_stock"],
                    "reorder_quantity": t["reorder_point"] * 2,
                    "priority": (
                        "high"
                        if t["days_of_stock"] < 15
                        else "medium" if t["days_of_stock"] < 30 else "low"
                    ),
                }
                for t in turnover_data
                if t["days_of_stock"] < 30
            ][:10],
        }

    @staticmethod
    def get_pricing_analytics() -> Dict[str, Any]:
        """Get pricing analytics and optimization insights"""
        
        variants = ProductVariant.objects.filter(is_active=True)
        
        price_ranges = [
            {"range": "$0 - $25", "min": 0, "max": 25},
            {"range": "$25 - $50", "min": 25, "max": 50},
            {"range": "$50 - $100", "min": 50, "max": 100},
            {"range": "$100 - $200", "min": 100, "max": 200},
            {"range": "$200+", "min": 200, "max": None},
        ]
        
        ranges_data = []
        total_variants = variants.count()
        
        for price_range in price_ranges:
            if price_range["max"] is None:
                range_variants = variants.filter(price__gte=price_range["min"])
            else:
                range_variants = variants.filter(
                    price__gte=price_range["min"],
                    price__lt=price_range["max"]
                )
            
            variant_count = range_variants.count()
            product_count = range_variants.values('product').distinct().count()
            
            ranges_data.append({
                "range": price_range["range"],
                "variant_count": variant_count,
                "product_count": product_count,
                "percentage": round(variant_count / total_variants * 100, 2) if total_variants > 0 else 0,
            })
        
        price_stats = variants.aggregate(
            min_price=Min('price'),
            max_price=Max('price'),
            avg_price=Avg('price'),
        )
        
        # Fix: Calculate discount percentage manually from discount_amount
        discounted_variants = variants.filter(discount_amount__gt=0)
        total_discounted = discounted_variants.count()
        
        # Calculate average discount percentage manually
        avg_discount = 0
        if discounted_variants.exists():
            discount_sum = 0
            for v in discounted_variants:
                if v.price > 0:
                    discount_sum += (v.discount_amount / v.price) * 100
            avg_discount = discount_sum / total_discounted if total_discounted > 0 else 0
        
        price_elasticity = []
        price_points = [25, 50, 75, 100, 150, 200]
        for price in price_points:
            demand = max(0, 1000 - (price * 8))
            revenue = price * demand
            price_elasticity.append({
                "price": price,
                "estimated_demand": demand,
                "estimated_revenue": revenue,
            })
        
        optimal = max(price_elasticity, key=lambda x: x['estimated_revenue'])
        
        return {
            "distribution": ranges_data,
            "statistics": {
                "min_price": float(price_stats['min_price'] or 0),
                "max_price": float(price_stats['max_price'] or 0),
                "avg_price": float(price_stats['avg_price'] or 0),
                "median_price": float(price_stats['avg_price'] or 0),
                "total_variants": total_variants,
            },
            "discount_analysis": {
                "total_discounted_variants": total_discounted,
                "discounted_percentage": round(total_discounted / total_variants * 100, 2) if total_variants > 0 else 0,
                "average_discount_percentage": round(avg_discount, 2),
            },
            "price_elasticity": price_elasticity,
            "optimal_price_point": {
                "price": optimal['price'],
                "estimated_revenue": optimal['estimated_revenue'],
                "estimated_demand": optimal['estimated_demand'],
            },
        }
        
        
    @staticmethod
    def get_category_analytics(
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get detailed category analytics"""

        categories = Category.objects.filter(is_active=True, is_hidden=False)
        result = []

        for category in categories:
            descendant_ids = category.get_descendant_ids()
            products = Product.objects.filter(
                category_id__in=descendant_ids, status=Product.STATUS_PUBLISHED
            )

            variants = ProductVariant.objects.filter(
                product__in=products, is_active=True
            )

            order_items = OrderItem.objects.filter(
                variant__in=variants, order__payment_status=Order.PAYMENT_PAID
            )

            if start_date:
                order_items = order_items.filter(order__created_at__gte=start_date)
            if end_date:
                order_items = order_items.filter(order__created_at__lte=end_date)

            sales_data = order_items.aggregate(
                total_quantity=Sum("quantity"),
                total_revenue=Sum("total_price"),
                total_orders=Count("order", distinct=True),
            )

            top_products_in_category = (
                order_items.values("variant__product__id", "variant__product__title")
                .annotate(revenue=Sum("total_price"), quantity=Sum("quantity"))
                .order_by("-revenue")[:5]
            )

            revenue = float(sales_data["total_revenue"] or 0)

            result.append(
                {
                    "id": str(category.id),
                    "name": category.name,
                    "slug": category.slug,
                    "metrics": {
                        "total_products": products.count(),
                        "total_variants": variants.count(),
                        "total_quantity_sold": sales_data["total_quantity"] or 0,
                        "total_revenue": revenue,
                        "total_orders": sales_data["total_orders"] or 0,
                        "avg_product_price": float(
                            variants.aggregate(avg=Avg("price"))["avg"] or 0
                        ),
                    },
                    "top_products": [
                        {
                            "product_id": str(p["variant__product__id"]),
                            "title": p["variant__product__title"],
                            "revenue": float(p["revenue"] or 0),
                            "quantity": p["quantity"] or 0,
                        }
                        for p in top_products_in_category
                    ],
                }
            )

        return sorted(result, key=lambda x: x["metrics"]["total_revenue"], reverse=True)

    @staticmethod
    def get_top_products(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10,
        category_id: Optional[str] = None,
        brand_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get top selling products based on revenue"""

        order_items = OrderItem.objects.filter(order__payment_status=Order.PAYMENT_PAID)

        if start_date:
            order_items = order_items.filter(order__created_at__gte=start_date)
        if end_date:
            order_items = order_items.filter(order__created_at__lte=end_date)

        if category_id:
            order_items = order_items.filter(variant__product__category_id=category_id)

        product_stats = (
            order_items.values(
                "variant__product__id",
                "variant__product__title",
                "variant__product__slug",
                "variant__product__category__name",
                "variant__product__category__id",
            )
            .annotate(
                total_quantity_sold=Sum("quantity"),
                total_revenue=Sum("total_price"),
                total_orders=Count("order", distinct=True),
                average_price=Avg("unit_price"),
            )
            .order_by("-total_revenue")[:limit]
        )

        result = []
        total_revenue_all = sum(
            float(item["total_revenue"] or 0) for item in product_stats
        )

        for stat in product_stats:
            product_id = stat["variant__product__id"]

            variants = ProductVariant.objects.filter(
                product_id=product_id, is_active=True
            )
            current_stock = variants.aggregate(total=Sum("stock"))["total"] or 0

            rating_data = ProductReview.objects.filter(
                product_id=product_id, is_approved=True
            ).aggregate(avg_rating=Avg("rating"), total_reviews=Count("id"))

            revenue = float(stat["total_revenue"] or 0)
            quantity = stat["total_quantity_sold"] or 0

            result.append(
                {
                    "id": str(product_id),
                    "title": stat["variant__product__title"],
                    "slug": stat["variant__product__slug"],
                    "category": stat["variant__product__category__name"]
                    or "Uncategorized",
                    "category_id": (
                        str(stat["variant__product__category__id"])
                        if stat["variant__product__category__id"]
                        else None
                    ),
                    "brand": None,
                    "thumbnail": None,
                    "metrics": {
                        "total_quantity_sold": quantity,
                        "total_revenue": revenue,
                        "total_orders": stat["total_orders"] or 0,
                        "average_price": float(stat["average_price"] or 0),
                        "revenue_percentage": (
                            round((revenue / total_revenue_all * 100), 2)
                            if total_revenue_all > 0
                            else 0
                        ),
                    },
                    "inventory": {
                        "current_stock": current_stock,
                        "total_variants": variants.count(),
                        "stock_status": (
                            "out_of_stock"
                            if current_stock == 0
                            else "low_stock" if current_stock < 10 else "in_stock"
                        ),
                    },
                    "ratings": {
                        "average_rating": float(rating_data["avg_rating"] or 0),
                        "total_reviews": rating_data["total_reviews"] or 0,
                    },
                }
            )

        return result

    @staticmethod
    def get_variant_analytics(
        product_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get detailed analytics for product variants"""

        variants = ProductVariant.objects.filter(is_active=True)

        if product_id:
            variants = variants.filter(product_id=product_id)

        result = []

        for variant in variants:
            order_items = OrderItem.objects.filter(
                variant=variant, order__payment_status=Order.PAYMENT_PAID
            )

            if start_date:
                order_items = order_items.filter(order__created_at__gte=start_date)
            if end_date:
                order_items = order_items.filter(order__created_at__lte=end_date)

            sales_data = order_items.aggregate(
                quantity_sold=Sum("quantity"),
                revenue=Sum("total_price"),
                orders=Count("order", distinct=True),
            )

            quantity_sold = sales_data["quantity_sold"] or 0
            revenue = float(sales_data["revenue"] or 0)
            orders = sales_data["orders"] or 0

            wishlist_adds = Wishlist.objects.filter(variant=variant).count()

            initial_stock = variant.stock + quantity_sold
            stock_turnover_rate = (
                round(quantity_sold / initial_stock, 2) if initial_stock > 0 else 0
            )

            avg_daily_sales = quantity_sold / 30 if quantity_sold > 0 else 0
            days_until_out_of_stock = (
                int(variant.stock / avg_daily_sales) if avg_daily_sales > 0 else 0
            )

            price_float = float(variant.price)
            profit_margin = (
                round(((price_float - (price_float * 0.6)) / price_float * 100), 2)
                if price_float > 0
                else 0
            )

            category_products = ProductVariant.objects.filter(
                product__category=variant.product.category, is_active=True
            )
            rank = 0
            for idx, v in enumerate(category_products.order_by("-price"), 1):
                if v.id == variant.id:
                    rank = idx
                    
                
            discount_percentage = float((variant.discount_amount / variant.price * 100)) if variant.price > 0 and variant.discount_amount > 0 else 0


            result.append(
                {
                    "id": str(variant.id),
                    "sku": variant.sku,
                    "product_title": variant.product.title,
                    "product_id": str(variant.product.id),
                    "attributes": variant.attributes,
                    "metrics": {
                        "quantity_sold": quantity_sold,
                        "revenue": revenue,
                        "orders_count": orders,
                        "conversion_rate": 0,
                        "return_rate": 0,
                        "average_days_to_sell": (
                            round(days_until_out_of_stock / 2)
                            if days_until_out_of_stock > 0
                            else 0
                        ),
                    },
                    "pricing": {
                        "price": price_float,
                        "discounted_price": float(variant.discounted_price),
                        "discount_percentage": discount_percentage,
                        "competitor_price_avg": None,
                        "price_position": (
                            "below_average" if price_float < 50 else "above_average"
                        ),
                    },
                    "inventory": {
                        "current_stock": variant.stock,
                        "initial_stock": initial_stock,
                        "stock_turnover_rate": stock_turnover_rate,
                        "days_until_out_of_stock": days_until_out_of_stock,
                        "reorder_point": variant.low_stock_threshold,
                        "stock_status": (
                            "out_of_stock"
                            if variant.stock == 0
                            else (
                                "low_stock"
                                if variant.stock <= variant.low_stock_threshold
                                else "in_stock"
                            )
                        ),
                    },
                    "performance": {
                        "views": 0,
                        "wishlist_adds": wishlist_adds,
                        "cart_adds": 0,
                        "abandoned_carts": 0,
                        "sell_through_rate": (
                            round((quantity_sold / initial_stock * 100), 2)
                            if initial_stock > 0
                            else 0
                        ),
                        "profit_margin": profit_margin,
                        "rank_in_category": rank,
                    },
                }
            )

        return result

    @staticmethod
    def get_inventory_status() -> Dict[str, Any]:
        """Get comprehensive inventory status"""

        variants = ProductVariant.objects.filter(is_active=True)

        total_variants = variants.count()
        total_stock = variants.aggregate(total=Sum("stock"))["total"] or 0
        total_value = (
            variants.aggregate(total=Sum(F("price") * F("stock")))["total"] or 0
        )

        in_stock = variants.filter(stock__gt=0).count()
        low_stock = variants.filter(
            stock__lte=F("low_stock_threshold"), stock__gt=0
        ).count()
        out_of_stock = variants.filter(stock=0).count()

        low_stock_alerts = []
        for variant in variants.filter(
            stock__lte=F("low_stock_threshold"), stock__gt=0
        )[:20]:
            low_stock_alerts.append(
                {
                    "variant_id": str(variant.id),
                    "sku": variant.sku,
                    "product_title": variant.product.title,
                    "attributes": variant.attributes,
                    "current_stock": variant.stock,
                    "threshold": variant.low_stock_threshold,
                    "severity": (
                        "critical"
                        if variant.stock <= variant.low_stock_threshold / 2
                        else "warning"
                    ),
                }
            )

        out_of_stock_items = []
        for variant in variants.filter(stock=0)[:20]:
            out_of_stock_items.append(
                {
                    "variant_id": str(variant.id),
                    "sku": variant.sku,
                    "product_title": variant.product.title,
                    "attributes": variant.attributes,
                    "days_out_of_stock": 0,
                }
            )

        inventory_by_category = []
        for category in Category.objects.filter(is_active=True):
            category_variants = variants.filter(product__category=category)
            if category_variants.exists():
                inventory_by_category.append(
                    {
                        "category": category.name,
                        "total_stock": category_variants.aggregate(total=Sum("stock"))[
                            "total"
                        ]
                        or 0,
                        "total_value": float(
                            category_variants.aggregate(
                                total=Sum(F("price") * F("stock"))
                            )["total"]
                            or 0
                        ),
                        "variants_count": category_variants.count(),
                        "low_stock_count": category_variants.filter(
                            stock__lte=F("low_stock_threshold"), stock__gt=0
                        ).count(),
                        "out_of_stock_count": category_variants.filter(stock=0).count(),
                    }
                )

        inventory_by_brand = []
        brand_values = {}
        for variant in variants:
            brand = variant.attributes.get("brand")
            if brand:
                if brand not in brand_values:
                    brand_values[brand] = {
                        "brand": brand,
                        "total_stock": 0,
                        "total_value": 0,
                        "variants_count": 0,
                    }
                brand_values[brand]["total_stock"] += variant.stock
                brand_values[brand]["total_value"] += (
                    float(variant.price) * variant.stock
                )
                brand_values[brand]["variants_count"] += 1

        for brand_data in brand_values.values():
            inventory_by_brand.append(brand_data)

        return {
            "summary": {
                "total_variants": total_variants,
                "total_stock": total_stock,
                "total_inventory_value": float(total_value),
                "avg_stock_per_variant": (
                    round(total_stock / total_variants, 2) if total_variants > 0 else 0
                ),
            },
            "stock_status": {
                "in_stock": in_stock,
                "low_stock": low_stock,
                "out_of_stock": out_of_stock,
            },
            "low_stock_alerts": low_stock_alerts,
            "out_of_stock": out_of_stock_items,
            "inventory_by_category": inventory_by_category,
            "inventory_by_brand": inventory_by_brand,
        }

    @staticmethod
    def get_price_distribution() -> Dict[str, Any]:
        """Get price distribution across variants"""

        variants = ProductVariant.objects.filter(is_active=True)

        price_ranges = [
            {"range": "$0 - $25", "min": 0, "max": 25},
            {"range": "$25 - $50", "min": 25, "max": 50},
            {"range": "$50 - $100", "min": 50, "max": 100},
            {"range": "$100 - $200", "min": 100, "max": 200},
            {"range": "$200+", "min": 200, "max": None},
        ]

        ranges_data = []
        total_variants = variants.count()

        for price_range in price_ranges:
            if price_range["max"] is None:
                range_variants = variants.filter(price__gte=price_range["min"])
            else:
                range_variants = variants.filter(
                    price__gte=price_range["min"], price__lt=price_range["max"]
                )

            variant_count = range_variants.count()
            product_count = range_variants.values("product").distinct().count()
            total_value = (
                range_variants.aggregate(total=Sum(F("price") * F("stock")))["total"]
                or 0
            )

            ranges_data.append(
                {
                    "range": price_range["range"],
                    "min": price_range["min"],
                    "max": price_range["max"],
                    "variant_count": variant_count,
                    "product_count": product_count,
                    "percentage": (
                        round(variant_count / total_variants * 100, 2)
                        if total_variants > 0
                        else 0
                    ),
                    "total_value": float(total_value),
                }
            )

        price_stats = variants.aggregate(
            min_price=Min("price"),
            max_price=Max("price"),
            avg_price=Avg("price"),
        )

        return {
            "ranges": ranges_data,
            "statistics": {
                "min_price": float(price_stats["min_price"] or 0),
                "max_price": float(price_stats["max_price"] or 0),
                "avg_price": float(price_stats["avg_price"] or 0),
                "total_variants": total_variants,
                "total_products": Product.objects.filter(
                    status=Product.STATUS_PUBLISHED
                ).count(),
            },
        }

    @staticmethod
    def get_review_analytics() -> Dict[str, Any]:
        """Get review and rating analytics"""

        reviews = ProductReview.objects.filter(is_approved=True)

        total_reviews = reviews.count()
        avg_rating = reviews.aggregate(avg=Avg("rating"))["avg"] or 0
        verified_purchases = reviews.filter(is_verified_purchase=True).count()

        rating_distribution = {
            "5_stars": reviews.filter(rating=5).count(),
            "4_stars": reviews.filter(rating=4).count(),
            "3_stars": reviews.filter(rating=3).count(),
            "2_stars": reviews.filter(rating=2).count(),
            "1_star": reviews.filter(rating=1).count(),
        }

        products_with_reviews = reviews.values("product").distinct().count()
        products_without_reviews = (
            Product.objects.filter(status=Product.STATUS_PUBLISHED)
            .exclude(id__in=reviews.values_list("product", flat=True).distinct())
            .count()
        )

        recent_reviews = []
        for review in reviews.order_by("-created_at")[:10]:
            recent_reviews.append(
                {
                    "id": str(review.id),
                    "product_title": review.product.title,
                    "product_id": str(review.product.id),
                    "rating": review.rating,
                    "title": review.title,
                    "comment": review.comment[:100],
                    "user_email": review.user.email,
                    "is_verified_purchase": review.is_verified_purchase,
                    "created_at": review.created_at.isoformat(),
                }
            )

        top_rated = Product.objects.filter(
            total_reviews__gte=5, status=Product.STATUS_PUBLISHED
        ).order_by("-average_rating")[:10]

        top_rated_data = []
        for product in top_rated:
            top_rated_data.append(
                {
                    "product_id": str(product.id),
                    "title": product.title,
                    "average_rating": float(product.average_rating),
                    "total_reviews": product.total_reviews,
                    "category": product.category.name if product.category else None,
                }
            )

        lowest_rated = Product.objects.filter(
            total_reviews__gte=5, status=Product.STATUS_PUBLISHED
        ).order_by("average_rating")[:10]

        lowest_rated_data = []
        for product in lowest_rated:
            lowest_rated_data.append(
                {
                    "product_id": str(product.id),
                    "title": product.title,
                    "average_rating": float(product.average_rating),
                    "total_reviews": product.total_reviews,
                    "category": product.category.name if product.category else None,
                }
            )

        return {
            "summary": {
                "total_reviews": total_reviews,
                "average_rating": round(float(avg_rating), 1),
                "verified_purchases": verified_purchases,
                "verified_percentage": (
                    round(verified_purchases / total_reviews * 100, 1)
                    if total_reviews > 0
                    else 0
                ),
                "products_with_reviews": products_with_reviews,
                "products_without_reviews": products_without_reviews,
            },
            "rating_distribution": rating_distribution,
            "recent_reviews": recent_reviews,
            "top_rated_products": top_rated_data,
            "lowest_rated_products": lowest_rated_data,
        }

    @staticmethod
    def get_category_performance(
        start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get performance metrics by category (legacy)"""

        categories = Category.objects.filter(is_active=True)
        result = []

        for category in categories:
            descendant_ids = category.get_descendant_ids()
            products = Product.objects.filter(
                category_id__in=descendant_ids, status=Product.STATUS_PUBLISHED
            )

            variants = ProductVariant.objects.filter(
                product__in=products, is_active=True
            )

            order_items = OrderItem.objects.filter(
                variant__in=variants, order__payment_status=Order.PAYMENT_PAID
            )

            if start_date:
                order_items = order_items.filter(order__created_at__gte=start_date)
            if end_date:
                order_items = order_items.filter(order__created_at__lte=end_date)

            sales_data = order_items.aggregate(
                total_quantity=Sum("quantity"), total_revenue=Sum("total_price")
            )

            inventory_data = variants.aggregate(
                total_stock=Sum("stock"),
                out_of_stock=Count("id", filter=Q(stock=0)),
                low_stock=Count(
                    "id", filter=Q(stock__lte=F("low_stock_threshold"), stock__gt=0)
                ),
            )

            rating_data = ProductReview.objects.filter(
                product__in=products, is_approved=True
            ).aggregate(avg_rating=Avg("rating"), total_reviews=Count("id"))

            revenue = float(sales_data["total_revenue"] or 0)

            result.append(
                {
                    "id": str(category.id),
                    "name": category.name,
                    "slug": category.slug,
                    "metrics": {
                        "total_products": products.count(),
                        "total_variants": variants.count(),
                        "total_quantity_sold": sales_data["total_quantity"] or 0,
                        "total_revenue": revenue,
                        "revenue_percentage": 0,
                        "quantity_percentage": 0,
                        "avg_product_price": float(
                            variants.aggregate(avg=Avg("price"))["avg"] or 0
                        ),
                    },
                    "inventory": {
                        "total_stock": inventory_data["total_stock"] or 0,
                        "out_of_stock_products": inventory_data["out_of_stock"] or 0,
                        "low_stock_products": inventory_data["low_stock"] or 0,
                    },
                    "engagement": {
                        "average_rating": float(rating_data["avg_rating"] or 0),
                        "total_reviews": rating_data["total_reviews"] or 0,
                    },
                }
            )

        total_revenue = sum(c["metrics"]["total_revenue"] for c in result)

        for category in result:
            category["metrics"]["revenue_percentage"] = (
                round((category["metrics"]["total_revenue"] / total_revenue * 100), 2)
                if total_revenue > 0
                else 0
            )

        return sorted(result, key=lambda x: x["metrics"]["total_revenue"], reverse=True)
