"""
Admin Order Views - Admin-only order management endpoints
"""

import logging
import csv
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.orders.selectors import get_order_by_id, get_admin_orders_filtered, get_order_statistics
from apps.orders.schemas import (
    serialize_order,
    serialize_order_list,
    validate_order_status_update,
    validate_payment_status_update,
    serialize_pagination_metadata,
)
from apps.orders.order_service import OrderService
from apps.orders.models import Order, OrderItem

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_list(request):
    """Admin: List all orders with filtering, sorting, and pagination"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        search = request.GET.get("search", "").strip()
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        payment_method = request.GET.get("payment_method")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        min_total = request.GET.get("min_total")
        max_total = request.GET.get("max_total")
        
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        min_total_float = float(min_total) if min_total else None
        max_total_float = float(max_total) if max_total else None
        
        orders, total, pagination_meta = get_admin_orders_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            status=status if status else None,
            payment_status=payment_status if payment_status else None,
            payment_method=payment_method if payment_method else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
            min_total=min_total_float,
            max_total=max_total_float,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        return APIResponse.success(
            data={
                "orders": serialize_order_list(orders, is_admin=True),
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Orders retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Admin order list error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_detail(request, order_id):
    """Admin: Get order details with shipping cost and bundle grouping"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")

        # serialize_order already handles bundle grouping
        order_data = serialize_order(order, is_admin=True, detailed=True)
        
        # Ensure shipping cost is explicitly included (already in serialize_order but double-check)
        order_data["shipping_cost"] = float(order.shipping_cost)
        order_data["shipping_method"] = order.shipping_method
        
        return APIResponse.success(
            data=order_data,
            message="Order retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin order detail error: {str(e)}", exc_info=True)
        return APIResponse.server_error()
    

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_by_number(request, order_number):
    """Admin: Get order by order number"""
    try:
        order = get_order_by_id(order_number, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")

        return APIResponse.success(
            data=serialize_order(order, is_admin=True, detailed=True),
            message="Order retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin order by number error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_order_status(request, order_id):
    """Admin: Update order status (auto-creates shipment when status='shipped')"""
    try:
        data = request.json_data

        cleaned, errors = validate_order_status_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        tracking_number = cleaned.get('tracking_number')
        carrier = cleaned.get('carrier')
        
        order, error = OrderService.update_order_status(
            order_id=order_id,
            status=cleaned["status"],
            admin_note=cleaned.get("admin_note"),
            carrier=carrier,
            tracking_number=tracking_number,
            user=request.user,
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"order": serialize_order(order, is_admin=True)},
            message=f"Order status updated to {cleaned['status']}",
        )

    except Exception as e:
        logger.error(f"Update order status error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_payment_status(request, order_id):
    """Admin: Update payment status"""
    try:
        data = request.json_data

        cleaned, errors = validate_payment_status_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        order, error = OrderService.update_payment_status(
            order_id=order_id,
            payment_status=cleaned["payment_status"],
            payment_intent_id=cleaned.get("payment_intent_id"),
            payment_receipt_url=cleaned.get("payment_receipt_url"),
            user=request.user,
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"order": serialize_order(order, is_admin=True)},
            message=f"Payment status updated to {cleaned['payment_status']}",
        )

    except Exception as e:
        logger.error(f"Update payment status error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_stats(request):
    """Admin: Get order statistics"""
    try:
        stats = get_order_statistics()

        return APIResponse.success(
            data=stats, message="Order statistics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Order stats error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_analytics(request):
    """Admin: Get detailed order analytics"""
    try:
        from django.db.models import Sum
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        analytics = {
            "summary": {
                "total_orders": Order.objects.count(),
                "total_revenue": float(
                    Order.objects.aggregate(total=Sum("total"))["total"] or 0
                ),
                "average_order_value": 0,
                "total_items_sold": OrderItem.objects.aggregate(total=Sum("quantity"))["total"] or 0,
            },
            "today": {
                "orders": Order.objects.filter(created_at__date=today).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date=today).aggregate(
                        total=Sum("total")
                    )["total"] or 0
                ),
            },
            "this_week": {
                "orders": Order.objects.filter(created_at__date__gte=week_ago).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date__gte=week_ago).aggregate(
                        total=Sum("total")
                    )["total"] or 0
                ),
            },
            "this_month": {
                "orders": Order.objects.filter(created_at__date__gte=month_ago).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date__gte=month_ago).aggregate(
                        total=Sum("total")
                    )["total"] or 0
                ),
            },
            "by_status": {
                status: Order.objects.filter(status=status).count()
                for status, _ in Order.STATUS_CHOICES
            },
            "by_payment_method": {
                "paystack": Order.objects.filter(payment_method="paystack").count(),
                "pod": Order.objects.filter(payment_method="pod").count(),
            },
        }

        if analytics["summary"]["total_orders"] > 0:
            analytics["summary"]["average_order_value"] = round(
                analytics["summary"]["total_revenue"] / analytics["summary"]["total_orders"], 2
            )

        return APIResponse.success(
            data=analytics, message="Order analytics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Order analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_export_orders(request):
    """Admin: Export orders to CSV"""
    try:
        status = request.GET.get("status")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        queryset = Order.objects.all().order_by("-created_at")

        if status:
            queryset = queryset.filter(status=status)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="orders_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Order Number",
                "Customer Name",
                "Customer Email",
                "Status",
                "Payment Status",
                "Payment Method",
                "Subtotal",
                "Shipping",
                "Tax",
                "Discount",
                "Total",
                "Item Count",
                "Created At",
            ]
        )

        for order in queryset:
            writer.writerow(
                [
                    order.order_number,
                    order.customer_name,
                    order.customer_email,
                    order.get_status_display(),
                    order.get_payment_status_display(),
                    order.get_payment_method_display(),
                    float(order.subtotal),
                    float(order.shipping_cost),
                    float(order.tax_amount),
                    float(order.discount_amount),
                    float(order.total),
                    order.item_count,
                    order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

    except Exception as e:
        logger.error(f"Export orders error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_bulk_order_action(request):
    """Admin: Perform bulk actions on orders"""
    try:
        data = request.json_data
        action = data.get("action")
        order_ids = data.get("order_ids", [])

        if not order_ids:
            return APIResponse.bad_request("No order IDs provided")

        if not action:
            return APIResponse.bad_request("No action specified")

        results = {"success": [], "failed": [], "total": len(order_ids)}

        if action == "cancel":
            for order_id in order_ids:
                try:
                    order, error = OrderService.cancel_order(
                        order_id=order_id,
                        user=request.user,
                        reason="Bulk cancellation by admin",
                    )
                    if error:
                        results["failed"].append({"id": order_id, "reason": str(error)})
                    else:
                        results["success"].append(
                            {"id": order_id, "order_number": order.order_number}
                        )
                except Exception as e:
                    results["failed"].append({"id": order_id, "reason": str(e)})

        elif action in ["confirm", "process", "ship", "deliver"]:
            status_map = {
                "confirm": "confirmed",
                "process": "processing",
                "ship": "shipped",
                "deliver": "delivered",
            }
            new_status = status_map.get(action)

            for order_id in order_ids:
                try:
                    order, error = OrderService.update_order_status(
                        order_id=order_id,
                        status=new_status,
                        admin_note=f"Bulk {action} action by admin",
                        user=request.user,
                    )
                    if error:
                        results["failed"].append({"id": order_id, "reason": str(error)})
                    else:
                        results["success"].append(
                            {"id": order_id, "order_number": order.order_number}
                        )
                except Exception as e:
                    results["failed"].append({"id": order_id, "reason": str(e)})

        else:
            return APIResponse.bad_request(f"Unknown action: {action}")

        return APIResponse.success(
            data=results,
            message=f"Processed {len(results['success'])} out of {results['total']} orders",
        )

    except Exception as e:
        logger.error(f"Bulk order action error: {str(e)}")
        return APIResponse.server_error()