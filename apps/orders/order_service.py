import logging
from typing import Any, Dict, Optional, List, Tuple
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderItem
from apps.products.models import ProductVariant, Product
from apps.users.models import Address, User
from apps.orders.selectors import get_order_by_id, get_address_by_id

logger = logging.getLogger(__name__)


class OrderService:
    """Order business logic - with price verification and bundle expansion"""

    @staticmethod
    def _prepare_order_items(
        items: List[Dict],
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Decimal], Optional[List[Dict[str, Any]]], Optional[Dict]]:
        """Validate checkout items against current catalog data."""
        from apps.promotions.models import Promotion

        subtotal = Decimal("0.00")
        order_items_data: List[Dict[str, Any]] = []
        variants_for_weight: List[Dict[str, Any]] = []

        for item_data in items:
            if item_data.get("is_bundle"):
                bundle_id = item_data.get("bundle_id")
                requested_quantity = item_data.get("quantity", 1)

                try:
                    promotion = Promotion.objects.get(id=bundle_id)
                except Promotion.DoesNotExist:
                    return None, None, None, {"items": f"Promotion bundle not found: {bundle_id}"}

                if promotion.status != Promotion.STATUS_ACTIVE:
                    return None, None, None, {"items": f"Promotion {promotion.name} is not active"}

                now = timezone.now()
                if promotion.starts_at > now:
                    return None, None, None, {"items": f"Promotion {promotion.name} has not started yet"}
                if promotion.ends_at and promotion.ends_at < now:
                    return None, None, None, {"items": f"Promotion {promotion.name} has expired"}

                client_price = Decimal(str(item_data.get("price", 0)))
                server_price = promotion.bundle_price
                if client_price != server_price:
                    logger.warning(
                        "Price mismatch for bundle %s: client=%s, server=%s",
                        promotion.name,
                        client_price,
                        server_price,
                    )
                    return None, None, None, {
                        "items": "Price mismatch for promotion bundle. Please refresh and try again."
                    }

                for bundle_item in promotion.items.select_related("variant", "variant__product"):
                    item_quantity = bundle_item.quantity * requested_quantity

                    if bundle_item.variant.stock < item_quantity:
                        return None, None, None, {
                            "items": (
                                f"Insufficient stock for {bundle_item.variant.sku} "
                                f"in bundle {promotion.name}"
                            )
                        }

                    unit_price = Decimal("0.00") if bundle_item.is_free else bundle_item.original_price
                    order_items_data.append(
                        {
                            "variant": bundle_item.variant,
                            "quantity": item_quantity,
                            "unit_price": unit_price,
                            "product_title": bundle_item.variant.product.title,
                            "product_slug": bundle_item.variant.product.slug,
                            "variant_attributes": bundle_item.variant.attributes,
                            "sku": bundle_item.variant.sku,
                            "is_bundle_item": True,
                            "bundle_id": str(promotion.id),
                            "bundle_name": promotion.name,
                            "bundle_price": float(promotion.bundle_price),
                        }
                    )
                    subtotal += unit_price * Decimal(str(item_quantity))
                    variants_for_weight.append({"variant": bundle_item.variant, "quantity": item_quantity})
                continue

            variant_id = item_data.get("variant_id")
            requested_quantity = item_data.get("quantity", 1)

            try:
                variant = ProductVariant.objects.select_related("product").get(
                    id=variant_id,
                    is_active=True,
                )
            except ProductVariant.DoesNotExist:
                return None, None, None, {"items": f"Product variant not found: {variant_id}"}

            if not variant.is_active:
                return None, None, None, {"items": f"Variant {variant.sku} is no longer available"}

            if variant.product.status != Product.STATUS_PUBLISHED:
                return None, None, None, {"items": f"Product {variant.product.title} is not available"}

            if variant.stock < requested_quantity:
                return None, None, None, {
                    "items": f"Insufficient stock for {variant.sku}. Available: {variant.stock}"
                }

            unit_price = variant.discounted_price
            order_items_data.append(
                {
                    "variant": variant,
                    "quantity": requested_quantity,
                    "unit_price": unit_price,
                    "product_title": variant.product.title,
                    "product_slug": variant.product.slug,
                    "variant_attributes": variant.attributes,
                    "sku": variant.sku,
                    "is_bundle_item": False,
                }
            )
            subtotal += unit_price * Decimal(str(requested_quantity))
            variants_for_weight.append({"variant": variant, "quantity": requested_quantity})

        return order_items_data, subtotal, variants_for_weight, None

    @staticmethod
    def preview_discount_code(
        items: List[Dict],
        discount_code: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict]]:
        """Preview the server-side effect of a discount code for a cart."""
        from apps.promotions.services import DiscountCodeService

        order_items_data, subtotal, _, error = OrderService._prepare_order_items(items)
        if error:
            return None, error

        discount_obj, discount_details, discount_error = DiscountCodeService.validate_discount_code(
            discount_code,
            subtotal,
            items=order_items_data,
        )
        if discount_error:
            return None, discount_error

        return {
            "entered_code": discount_details["entered_code"],
            "code": discount_obj.code,
            "name": discount_obj.name,
            "subtotal": float(subtotal),
            "discount_amount": float(discount_details["discount_amount"]),
            "subtotal_after_discount": float(discount_details["subtotal_after_discount"]),
            "is_affiliate_code": discount_details["is_affiliate_code"],
            "resolved_from_referral_code": discount_details["resolved_from_referral_code"],
        }, None

    @staticmethod
    @transaction.atomic
    def create_order(
        user: Optional[User],
        items: List[Dict],
        shipping_address_data: Dict,
        payment_method: str,
        guest_info: Dict = None,
        billing_address_data: Dict = None,
        customer_note: str = "",
        currency: str = "GHS",
        discount_code: str = "",
        shipping_method_id: str = "",
        popular_address_id: str = "",
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Create a new order - VERIFIES prices and EXPANDS bundles on server side"""
        try:
            from apps.common.models import GeneralConfig
            from apps.orders.shipping_calculator import ShippingCalculator
            from apps.orders.payment_config import PaymentConfigService
            from apps.promotions.services import DiscountCodeService

            general_config = GeneralConfig.get_cached()

            if payment_method == 'paystack' and not general_config.paystack_enabled:
                return None, {"payment_method": "Payment method 'paystack' is currently disabled"}
            if payment_method == 'pod' and not general_config.pod_enabled:
                return None, {"payment_method": "Payment method 'pod' is currently disabled"}

            currency = (currency or general_config.currency or 'GHS')[:3]

            order_items_data, subtotal, variants_for_weight, error = OrderService._prepare_order_items(items)
            if error:
                return None, error

            if general_config.min_order_value > 0 and subtotal < general_config.min_order_value:
                return None, {
                    "items": (
                        f"Minimum order value is {general_config.currency} "
                        f"{general_config.min_order_value}"
                    )
                }

            # Create shipping address
            shipping_address = OrderService._create_or_get_address(shipping_address_data, user, 'shipping')
            
            if billing_address_data:
                billing_address = OrderService._create_or_get_address(billing_address_data, user, 'billing')
            else:
                billing_address = shipping_address

            # Resolve the customer's shipping selection server-side (the
            # quoted amount is never trusted from the client)
            from apps.orders.shipping_quote_service import ShippingQuoteService

            total_weight = ShippingCalculator.calculate_order_weight(variants_for_weight)
            resolution, ship_error = ShippingQuoteService.resolve_selected_option(
                shipping_method_id=shipping_method_id,
                popular_address_id=popular_address_id,
                destination={
                    "country": shipping_address.country,
                    "state": shipping_address.state,
                    "city": shipping_address.city,
                    "postal_code": shipping_address.postal_code,
                    "address": shipping_address.address_line1,
                },
                items=items,
                subtotal=subtotal,
                total_weight=total_weight,
                currency=currency,
            )
            if ship_error:
                return None, ship_error

            shipping_cost = resolution['cost']
            shipping_method = resolution['method_name']
            is_pickup = resolution['is_pickup']

            logger.info(f"Shipping resolution: weight={total_weight}kg, cost={shipping_cost}, method={shipping_method}")
            
            # Tax from store config (percent of subtotal; 0 = tax off).
            # tax_inclusive means prices already contain tax — add nothing.
            tax_rate = general_config.tax_rate or Decimal('0.00')
            tax_amount = (
                (subtotal * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
                if tax_rate > 0 and not general_config.tax_inclusive
                else Decimal('0.00')
            )
            discount_amount = Decimal('0.00')

            discount_obj = None
            discount_details = None
            if discount_code:
                discount_obj, discount_details, discount_error = DiscountCodeService.validate_discount_code(
                    discount_code,
                    subtotal,
                    items=order_items_data,
                )
                if discount_error:
                    return None, discount_error
                discount_amount = discount_details["discount_amount"]
            
            total = subtotal + shipping_cost + tax_amount - discount_amount

            # Create order
            order = Order.objects.create(
                user=user,
                guest_email=guest_info.get('email', '') if guest_info else shipping_address.email,
                guest_first_name=guest_info.get('first_name', '') if guest_info else shipping_address.first_name,
                guest_last_name=guest_info.get('last_name', '') if guest_info else shipping_address.last_name,
                guest_phone=guest_info.get('phone', '') if guest_info else shipping_address.phone,
                shipping_address=shipping_address,
                billing_address=billing_address,
                payment_method=payment_method,
                shipping_method=shipping_method,
                shipping_cost=shipping_cost,
                is_pickup=is_pickup,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                discount_code=discount_obj,
                discount_code_text=discount_obj.code if discount_obj else "",
                entered_discount_code_text=(
                    discount_details["entered_code"] if discount_details else ""
                ),
                affiliate=discount_obj.affiliate if discount_obj else None,
                affiliate_commission_amount=(
                    discount_details["commission_amount"] if discount_details else Decimal("0.00")
                ),
                subtotal=subtotal,
                total=total,
                customer_note=customer_note,
                currency=currency,
            )

            # Create order items and reduce stock
            for item_data in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    variant=item_data['variant'],
                    product_title=item_data['product_title'],
                    product_slug=item_data['product_slug'],
                    variant_attributes=item_data['variant_attributes'],
                    sku=item_data['sku'],
                    unit_price=item_data['unit_price'],
                    quantity=item_data['quantity'],
                    is_bundle_item=item_data.get('is_bundle_item', False),
                    bundle_id=item_data.get('bundle_id', ''),
                    bundle_name=item_data.get('bundle_name', ''),
                )
                item_data['variant'].reduce_stock(item_data['quantity'])

            # Handle payment method specific logic
            if payment_method == 'cash_on_delivery' or payment_method == 'pod':
                is_eligible, reason = PaymentConfigService.check_pod_eligibility(order)
                if not is_eligible:
                    order.delete()
                    return None, {"payment_method": reason}
                
                order.payment_status = Order.PAYMENT_PENDING
                order.status = Order.STATUS_CONFIRMED
                order.confirmed_at = timezone.now()
                order.payment_type = Order.PAYMENT_TYPE_POD
                order.pod_eligible = True
                order.save()
                
            elif payment_method == 'paystack':
                order.payment_status = Order.PAYMENT_PENDING
                order.status = Order.STATUS_PENDING
                order.payment_type = Order.PAYMENT_TYPE_ONLINE
                order.save()
            
            else:
                order.delete()
                return None, {"payment_method": f"Unsupported payment method: {payment_method}"}

            DiscountCodeService.register_order_discount(order, discount_obj, discount_details)
            DiscountCodeService.sync_order_commission(order, reason="Order created")

            logger.info(f"Order created: {order.order_number} with subtotal=${subtotal}, shipping=${shipping_cost}, total=${total}")
            return order, None

        except ValueError as e:
            # Raised by reduce_stock when concurrent demand exhausts stock.
            # Roll back so no partial order/stock change is committed.
            transaction.set_rollback(True)
            logger.warning(f"Order creation stock conflict: {str(e)}")
            return None, {"items": str(e)}
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Order creation error: {str(e)}")
            return None, {"general": f"Failed to create order: {str(e)}"}

        

    @staticmethod
    def get_order_payment_options(order_id: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Get available payment options for an order"""
        from apps.orders.selectors import get_order_by_id
        from apps.orders.payment_config import PaymentConfigService
        
        try:
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}
            
            payment_options = PaymentConfigService.get_available_payment_methods(order)
            
            return payment_options, None
            
        except Exception as e:
            logger.error(f"Get payment options error: {str(e)}")
            return None, {"general": str(e)}
  
  
    @staticmethod
    def _create_or_get_address(address_data: Dict, user: Optional[User], address_type: str = 'shipping') -> Address:
        """Create an address for a user"""
        from apps.users.models.address import Address
        
        # For both authenticated and guest users, create a new address
        # Don't try to get existing addresses as shipping addresses can be different per order
        address = Address.objects.create(
            user=user,  # user is either authenticated user or guest user (User object)
            address_type=address_type,
            first_name=address_data.get('first_name', ''),
            last_name=address_data.get('last_name', ''),
            email=address_data.get('email', ''),
            phone=address_data.get('phone', ''),
            address_line1=address_data.get('address_line1', ''),
            address_line2=address_data.get('address_line2', ''),
            city=address_data.get('city', ''),
            state=address_data.get('state', ''),
            postal_code=address_data.get('postal_code', ''),
            country=address_data.get('country', 'Ghana'),
            is_default=False,  # Don't set as default for guest orders
        )
        
        return address

    # Statuses an admin may set through the order-status endpoint. shipped and
    # delivered belong to the shipments domain (create a shipment / mark its
    # shipment delivered); pending/refunded are never set directly.
    ADMIN_SETTABLE_STATUSES = (
        Order.STATUS_CONFIRMED,
        Order.STATUS_PROCESSING,
        Order.STATUS_READY_FOR_SHIPPING,
        Order.STATUS_COMPLETED,
        Order.STATUS_CANCELLED,
    )

    STATUS_TIMESTAMP_FIELDS = {
        Order.STATUS_CONFIRMED: "confirmed_at",
        Order.STATUS_PROCESSING: "processing_at",
        Order.STATUS_READY_FOR_SHIPPING: "ready_for_shipping_at",
        Order.STATUS_SHIPPED: "shipped_at",
        Order.STATUS_DELIVERED: "delivered_at",
        Order.STATUS_COMPLETED: "completed_at",
        Order.STATUS_CANCELLED: "cancelled_at",
    }

    @staticmethod
    @transaction.atomic
    def update_order_status(
        order_id: str,
        status: str,
        admin_note: str = None,
        skip_behavior: str = None,
        user: User = None
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Update order status along the fulfilment pipeline.

        Enforces the forward-only rails (Order.SHIPPING_PIPELINE /
        Order.PICKUP_PIPELINE). Jumping more than one step ahead requires an
        explicit skip_behavior:
        - "skip": jump, leaving the skipped steps' timestamps null;
        - "complete": jump and backfill the skipped steps' timestamps.
        Without it, a jump returns a conflict payload under "__conflict__" that
        the view maps to HTTP 409 so the UI can prompt the admin.
        """
        try:
            from apps.orders.models import Shipment, ShipmentTracking
            from apps.promotions.services import DiscountCodeService

            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            valid_statuses = dict(Order.STATUS_CHOICES).keys()
            if status not in valid_statuses:
                return None, {"status": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

            if status in (Order.STATUS_SHIPPED, Order.STATUS_DELIVERED):
                return None, {
                    "status": (
                        "shipped/delivered are managed through shipments — "
                        "create a shipment or update its status instead"
                    )
                }
            if status not in OrderService.ADMIN_SETTABLE_STATUSES:
                return None, {"status": f"Status '{status}' cannot be set directly"}

            old_status = order.status

            # Idempotent no-op (useful for bulk actions).
            if status == old_status:
                return order, None

            if status == Order.STATUS_CANCELLED:
                if old_status in (Order.STATUS_DELIVERED, Order.STATUS_COMPLETED):
                    return None, {
                        "status": "Delivered/completed orders cannot be cancelled — use the refund flow"
                    }
                if old_status == Order.STATUS_REFUNDED:
                    return None, {"status": "Refunded orders cannot be cancelled"}
            else:
                if old_status in (Order.STATUS_CANCELLED, Order.STATUS_REFUNDED):
                    return None, {"status": f"Cannot change status of a {old_status} order"}

                rail = Order.PICKUP_PIPELINE if order.is_pickup else Order.SHIPPING_PIPELINE
                if status not in rail:
                    return None, {"status": f"Pickup orders cannot be set to '{status}'"}
                if old_status not in rail:
                    return None, {"status": f"Cannot move a {old_status} order to '{status}'"}

                current_index = rail.index(old_status)
                target_index = rail.index(status)
                if target_index < current_index:
                    return None, {
                        "status": f"Cannot move order backwards from {old_status} to {status}"
                    }

                if status == Order.STATUS_COMPLETED:
                    if order.is_pickup:
                        if order.payment_status != Order.PAYMENT_PAID:
                            return None, {
                                "status": "Pickup orders must be paid before they can be completed"
                            }
                    elif old_status != Order.STATUS_DELIVERED:
                        return None, {
                            "status": "Only delivered orders can be completed — mark the shipment delivered first"
                        }

                skipped_statuses = rail[current_index + 1:target_index]
                if skipped_statuses:
                    if skip_behavior not in ("skip", "complete"):
                        return None, {
                            "__conflict__": {
                                "code": "steps_skipped",
                                "current_status": old_status,
                                "requested_status": status,
                                "skipped_statuses": list(skipped_statuses),
                                "allowed_skip_behaviors": ["skip", "complete"],
                            }
                        }
                    if skip_behavior == "complete":
                        for skipped in skipped_statuses:
                            field = OrderService.STATUS_TIMESTAMP_FIELDS.get(skipped)
                            if field and not getattr(order, field):
                                setattr(order, field, timezone.now())

            order.status = status

            timestamp_field = OrderService.STATUS_TIMESTAMP_FIELDS.get(status)
            if timestamp_field and not getattr(order, timestamp_field):
                setattr(order, timestamp_field, timezone.now())

            if status == Order.STATUS_CANCELLED:
                # Restore stock when cancelling
                for item in order.items.all():
                    if item.variant:
                        item.variant.increase_stock(item.quantity)

            if admin_note:
                timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                if order.admin_note:
                    order.admin_note += f"\n{timestamp}: {admin_note}"
                else:
                    order.admin_note = f"{timestamp}: {admin_note}"

            order.save()

            if status == Order.STATUS_READY_FOR_SHIPPING and not order.is_pickup:
                if not hasattr(order, "shipment"):
                    shipment = Shipment.objects.create(
                        order=order,
                        status=Shipment.STATUS_PENDING,
                        notes="Created when order was marked ready for shipping",
                        created_by=user,
                    )
                    ShipmentTracking.objects.create(
                        shipment=shipment,
                        status=Shipment.STATUS_PENDING,
                        description="Shipment created — awaiting dispatch",
                        created_by=user,
                    )
                    logger.info(f"Pending shipment created for order {order.order_number}")

            if status == Order.STATUS_CANCELLED:
                try:
                    shipment = order.shipment
                    if shipment.status != Shipment.STATUS_CANCELLED:
                        shipment.status = Shipment.STATUS_CANCELLED
                        shipment.save()

                        ShipmentTracking.objects.create(
                            shipment=shipment,
                            status=Shipment.STATUS_CANCELLED,
                            description="Order cancelled",
                            created_by=user,
                        )
                        logger.info(f"Shipment cancelled for order {order.order_number}")
                except Shipment.DoesNotExist:
                    pass

            DiscountCodeService.sync_order_commission(
                order,
                reason=f"Order status changed to {status}",
            )

            logger.info(f"Order {order.order_number} status updated from {old_status} to {status}")
            return order, None

        except Exception as e:
            transaction.set_rollback(True)
            logger.exception("Order status update error")
            return None, {"general": "Failed to update order status"}

    @staticmethod
    def _on_payment_captured(order: Order, was_failed: bool) -> None:
        """Apply the side effects of a successful payment capture (in memory —
        the caller saves the order and syncs the commission afterwards).

        - If the payment had previously been marked failed, the reserved stock
          was restored then; re-reserve it now. If some items can no longer be
          covered, keep the order paid (the money is captured) but flag the
          oversell in the admin note and logs.
        - Pickup orders auto-complete once paid (POS flow); shipped orders just
          advance pending -> confirmed as before.
        """
        now = timezone.now()

        if was_failed:
            oversold = []
            for item in order.items.select_related("variant").all():
                if not item.variant:
                    continue
                try:
                    item.variant.reduce_stock(item.quantity)
                except ValueError:
                    oversold.append(f"{item.sku} x{item.quantity}")
            if oversold:
                timestamp = now.strftime("%Y-%m-%d %H:%M")
                note = f"{timestamp}: OVERSOLD on re-payment: {', '.join(oversold)}"
                order.admin_note = f"{order.admin_note}\n{note}" if order.admin_note else note
                logger.error(
                    f"Order {order.order_number} oversold on re-payment: {', '.join(oversold)}"
                )

        if not order.paid_at:
            order.paid_at = now

        if order.is_pickup and order.status in (
            Order.STATUS_PENDING,
            Order.STATUS_CONFIRMED,
            Order.STATUS_PROCESSING,
        ):
            order.status = Order.STATUS_COMPLETED
            order.completed_at = now
            if not order.confirmed_at:
                order.confirmed_at = now
        elif order.status == Order.STATUS_PENDING:
            order.status = Order.STATUS_CONFIRMED
            order.confirmed_at = now

    @staticmethod
    @transaction.atomic
    def update_payment_status(
        order_id: str,
        payment_status: str,
        payment_intent_id: str = None,
        payment_receipt_url: str = None,
        user: User = None
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Update payment status"""
        try:
            from apps.promotions.services import DiscountCodeService

            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            valid_statuses = dict(Order.PAYMENT_STATUS_CHOICES).keys()
            if payment_status not in valid_statuses:
                return None, {"payment_status": f"Invalid payment status. Must be one of: {', '.join(valid_statuses)}"}

            was_failed = order.payment_status == Order.PAYMENT_FAILED
            was_paid = order.payment_status == Order.PAYMENT_PAID
            order.payment_status = payment_status

            if payment_intent_id:
                order.payment_intent_id = payment_intent_id
            if payment_receipt_url:
                order.payment_receipt_url = payment_receipt_url

            if payment_status == Order.PAYMENT_PAID and not was_paid:
                OrderService._on_payment_captured(order, was_failed)

            order.save()
            DiscountCodeService.sync_order_commission(
                order,
                reason=f"Payment status changed to {payment_status}",
            )

            logger.info(f"Order {order.order_number} payment status updated to {payment_status}")
            return order, None

        except Exception:
            transaction.set_rollback(True)
            logger.exception("Payment status update error")
            return None, {"general": "Failed to update payment status"}

    @staticmethod
    @transaction.atomic
    def mark_payment_failed(order_id: str, reason: str = "") -> Tuple[Optional[Order], Optional[Dict]]:
        """Mark an order's payment as failed and return its reserved stock.

        Called when a Paystack payment is reported failed/abandoned. Stock is
        reduced at order creation, so a pending online order that never gets paid
        is holding inventory; this releases it. The operation is idempotent:
        - if the order is already paid, it is left untouched (no stock change);
        - if it is already failed, it is a no-op (stock is not restored twice).
        """
        try:
            from apps.promotions.services import DiscountCodeService

            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            # Never override a successful payment.
            if order.payment_status == Order.PAYMENT_PAID:
                return None, {"payment": "Order is already paid"}

            # Idempotent: already failed -> nothing to do, don't restore again.
            if order.payment_status == Order.PAYMENT_FAILED:
                return order, None

            # Restore reserved stock, unless it was already released by a
            # cancellation (cancelled orders restore stock on their own path).
            if order.status != Order.STATUS_CANCELLED:
                for item in order.items.select_related("variant").all():
                    if item.variant:
                        item.variant.increase_stock(item.quantity)

            order.payment_status = Order.PAYMENT_FAILED
            if reason:
                timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                note = f"{timestamp}: Payment failed: {reason}"
                order.admin_note = f"{order.admin_note}\n{note}" if order.admin_note else note
            order.save()
            DiscountCodeService.sync_order_commission(
                order,
                reason=reason or "Payment failed",
            )

            logger.info(f"Order {order.order_number} marked payment failed; stock restored. Reason: {reason}")
            return order, None

        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Mark payment failed error: {str(e)}")
            return None, {"general": f"Failed to mark payment failed: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def cancel_order(order_id: str, user: User = None, reason: str = "") -> Tuple[Optional[Order], Optional[Dict]]:
        """Cancel an order"""
        try:
            from apps.promotions.services import DiscountCodeService

            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            # Check permissions
            if user and not user.is_staff:
                if order.user != user:
                    return None, {"permission": "You don't have permission to cancel this order"}

            # Check if order can be cancelled
            if not order.can_cancel:
                return None, {"status": f"Order cannot be cancelled in its current state: {order.get_status_display()}"}

            # Update order
            order.status = Order.STATUS_CANCELLED
            order.cancelled_at = timezone.now()
            
            if reason:
                timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                if order.admin_note:
                    order.admin_note += f"\n{timestamp}: Cancelled by {'user' if user and not user.is_staff else 'admin'}: {reason}"
                else:
                    order.admin_note = f"{timestamp}: Cancelled by {'user' if user and not user.is_staff else 'admin'}: {reason}"

            order.save()

            # Restore stock
            for item in order.items.all():
                if item.variant:
                    item.variant.increase_stock(item.quantity)

            DiscountCodeService.sync_order_commission(
                order,
                reason=reason or "Order cancelled",
            )

            logger.info(f"Order {order.order_number} cancelled")
            return order, None

        except Exception as e:
            logger.error(f"Order cancellation error: {str(e)}")
            return None, {"general": f"Failed to cancel order: {str(e)}"}

    @staticmethod
    def cancel_stale_unpaid_orders() -> Tuple[int, int]:
        """Cancel pending online-payment orders left unpaid past the
        configured window, restoring their reserved stock.

        POD orders are excluded (unpaid until delivery by design).
        Returns (cancelled_count, failed_count); (0, 0) when disabled.
        """
        from apps.common.models import GeneralConfig

        hours = GeneralConfig.get_cached().auto_cancel_unpaid_hours
        if not hours:
            return 0, 0

        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        stale_ids = list(
            Order.objects.filter(
                status=Order.STATUS_PENDING,
                payment_status=Order.PAYMENT_PENDING,
                created_at__lt=cutoff,
            )
            .exclude(payment_method='pod')
            .values_list('id', flat=True)
        )

        cancelled = failed = 0
        for order_id in stale_ids:
            _, error = OrderService.cancel_order(
                str(order_id),
                user=None,
                reason=f"Auto-cancelled: unpaid for over {hours}h",
            )
            if error:
                failed += 1
                logger.error(f"Auto-cancel failed for order {order_id}: {error}")
            else:
                cancelled += 1

        if cancelled or failed:
            logger.info(f"Auto-cancel unpaid orders: {cancelled} cancelled, {failed} failed")
        return cancelled, failed

    # Add to apps/orders/services/order_service.py

    @staticmethod
    def initiate_payment(order_id: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Initiate payment for an order"""
        from apps.orders.selectors import get_order_by_id
        from apps.orders.paystack_service import PaystackService
        
        try:
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}
            
            # Check if order can be paid
            if order.payment_status == Order.PAYMENT_PAID:
                return None, {"payment": "Order is already paid"}
            
            if order.status == Order.STATUS_CANCELLED:
                return None, {"payment": "Cancelled orders cannot be paid"}
            
            # Initialize Paystack transaction
            payment_data, error = PaystackService.initialize_transaction(order)
            
            if error:
                return None, {"payment": error}
            
            # Store payment reference
            order.payment_intent_id = payment_data['reference']
            order.save()
            
            return payment_data, None
            
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return None, {"general": str(e)}


    # apps/orders/services/order_service.py - Update verify_payment

    @staticmethod
    def verify_payment(reference: str, order_id: str = None) -> Tuple[bool, Optional[Dict]]:
        """Verify payment after callback"""
        from apps.orders.paystack_service import PaystackService
        
        try:
            success, result = PaystackService.process_successful_payment(reference, order_id)
            
            if success:
                # result should contain both order and transaction
                return True, result
            else:
                return False, result
                
        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
            return False, {"error": str(e)}
        
    @staticmethod
    @transaction.atomic
    def create_pos_pickup_order(
        customer: Optional[User],
        items: List[Dict],
        payment_method: str,
        guest_info: Dict = None,
        customer_note: str = "",
        currency: str = "GHS",
        created_by: User = None,
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Create a POS order for in-store pickup (NO SHIPPING)"""
        try:
            from apps.common.models import GeneralConfig
            from apps.promotions.models import Promotion
            from apps.orders.store_address import get_or_create_store_address

            currency = (currency or GeneralConfig.get_cached().currency or 'GHS')[:3]
            subtotal = Decimal('0.00')
            order_items_data = []

            # Process items (same as before)
            for item_data in items:
                if item_data.get('is_bundle'):
                    bundle_id = item_data.get('bundle_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        promotion = Promotion.objects.get(id=bundle_id)
                    except Promotion.DoesNotExist:
                        return None, {"items": f"Promotion bundle not found: {bundle_id}"}
                    
                    if promotion.status != Promotion.STATUS_ACTIVE:
                        return None, {"items": f"Promotion {promotion.name} is not active"}
                    
                    now = timezone.now()
                    if promotion.starts_at > now:
                        return None, {"items": f"Promotion {promotion.name} has not started yet"}
                    if promotion.ends_at and promotion.ends_at < now:
                        return None, {"items": f"Promotion {promotion.name} has expired"}
                    
                    for bundle_item in promotion.items.all():
                        item_quantity = bundle_item.quantity * requested_quantity
                        
                        if bundle_item.variant.stock < item_quantity:
                            return None, {"items": f"Insufficient stock for {bundle_item.variant.sku} in bundle {promotion.name}"}
                        
                        unit_price = Decimal('0.00') if bundle_item.is_free else bundle_item.original_price
                        
                        order_items_data.append({
                            'variant': bundle_item.variant,
                            'quantity': item_quantity,
                            'unit_price': unit_price,
                            'product_title': bundle_item.variant.product.title,
                            'product_slug': bundle_item.variant.product.slug,
                            'variant_attributes': bundle_item.variant.attributes,
                            'sku': bundle_item.variant.sku,
                            'is_bundle_item': True,
                            'bundle_id': str(promotion.id),
                            'bundle_name': promotion.name,
                        })
                        
                        subtotal += unit_price * Decimal(str(item_quantity))
                        
                else:
                    variant_id = item_data.get('variant_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        variant = ProductVariant.objects.select_related('product').get(
                            id=variant_id, is_active=True
                        )
                    except ProductVariant.DoesNotExist:
                        return None, {"items": f"Product variant not found: {variant_id}"}
                    
                    if not variant.is_active:
                        return None, {"items": f"Variant {variant.sku} is no longer available"}
                    
                    if variant.product.status != Product.STATUS_PUBLISHED:
                        return None, {"items": f"Product {variant.product.title} is not available"}
                    
                    if variant.stock < requested_quantity:
                        return None, {"items": f"Insufficient stock for {variant.sku}. Available: {variant.stock}"}
                    
                    unit_price = variant.discounted_price
                    
                    order_items_data.append({
                        'variant': variant,
                        'quantity': requested_quantity,
                        'unit_price': unit_price,
                        'product_title': variant.product.title,
                        'product_slug': variant.product.slug,
                        'variant_attributes': variant.attributes,
                        'sku': variant.sku,
                        'is_bundle_item': False,
                    })
                    
                    subtotal += unit_price * Decimal(str(requested_quantity))

            # NO SHIPPING for pickup
            shipping_cost = Decimal('0.00')
            shipping_method = "In-Store Pickup"
            tax_amount = Decimal('0.00')
            discount_amount = Decimal('0.00')
            total = subtotal + shipping_cost + tax_amount - discount_amount

            # GET OR CREATE store pickup address (from settings)
            store_address = get_or_create_store_address(created_by)

            # Create order
            order = Order.objects.create(
                user=customer,
                guest_email=guest_info.get('email', '') if guest_info else store_address.email,
                guest_first_name=guest_info.get('first_name', '') if guest_info else store_address.first_name,
                guest_last_name=guest_info.get('last_name', '') if guest_info else store_address.last_name,
                guest_phone=guest_info.get('phone', '') if guest_info else store_address.phone,
                shipping_address=store_address,
                billing_address=store_address,
                payment_method=payment_method,
                shipping_method=shipping_method,
                shipping_cost=shipping_cost,
                is_pickup=True,
                tax_rate=Decimal('0.00'),
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                subtotal=subtotal,
                total=total,
                customer_note=customer_note,
                currency=currency,
                created_by=created_by,
            )

            # Create order items and reduce stock
            for item_data in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    variant=item_data['variant'],
                    product_title=item_data['product_title'],
                    product_slug=item_data['product_slug'],
                    variant_attributes=item_data['variant_attributes'],
                    sku=item_data['sku'],
                    unit_price=item_data['unit_price'],
                    quantity=item_data['quantity'],
                    is_bundle_item=item_data.get('is_bundle_item', False),
                    bundle_id=item_data.get('bundle_id', ''),
                    bundle_name=item_data.get('bundle_name', ''),
                )
                item_data['variant'].reduce_stock(item_data['quantity'])

            # Handle payment status based on method
            if payment_method == 'pos':
                # Paid in store and handed over: the order is done.
                now = timezone.now()
                order.payment_status = Order.PAYMENT_PAID
                order.status = Order.STATUS_COMPLETED
                order.confirmed_at = now
                order.completed_at = now
                order.paid_at = now
                order.payment_type = 'pos'
            elif payment_method == 'cash_on_delivery' or payment_method == 'pod':
                # Pay on collection: stays confirmed and auto-completes when
                # the payment is recorded (_on_payment_captured).
                order.payment_status = Order.PAYMENT_PENDING
                order.status = Order.STATUS_CONFIRMED
                order.confirmed_at = timezone.now()
                order.payment_type = Order.PAYMENT_TYPE_POD
                order.pod_eligible = True
            else:
                # POS orders are settled in person; online checkout is not
                # supported here (no gateway redirect path). Reject rather than
                # create an uncollectible pending order.
                transaction.set_rollback(True)
                return None, {"payment_method": f"Unsupported POS payment method: {payment_method}"}

            order.save()

            logger.info(f"POS pickup order created by {created_by.email if created_by else 'unknown'}: {order.order_number} with total=${total}")
            return order, None

        except ValueError as e:
            transaction.set_rollback(True)
            logger.warning(f"POS pickup order stock conflict: {str(e)}")
            return None, {"items": str(e)}
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"POS pickup order creation error: {str(e)}", exc_info=True)
            return None, {"general": f"Failed to create POS order: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def create_pos_shipping_order(
        customer: Optional[User],
        items: List[Dict],
        shipping_address_data: Dict,
        payment_method: str,
        guest_info: Dict = None,
        customer_note: str = "",
        currency: str = "GHS",
        created_by: User = None,  # Staff/admin creating the order
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Create a POS order with shipping (customer wants items shipped)"""
        try:
            from apps.common.models import GeneralConfig
            from apps.orders.shipping_calculator import ShippingCalculator
            from apps.promotions.models import Promotion

            currency = (currency or GeneralConfig.get_cached().currency or 'GHS')[:3]
            subtotal = Decimal('0.00')
            order_items_data = []
            variants_for_weight = []

            for item_data in items:
                if item_data.get('is_bundle'):
                    bundle_id = item_data.get('bundle_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        promotion = Promotion.objects.get(id=bundle_id)
                    except Promotion.DoesNotExist:
                        return None, {"items": f"Promotion bundle not found: {bundle_id}"}
                    
                    if promotion.status != Promotion.STATUS_ACTIVE:
                        return None, {"items": f"Promotion {promotion.name} is not active"}
                    
                    now = timezone.now()
                    if promotion.starts_at > now:
                        return None, {"items": f"Promotion {promotion.name} has not started yet"}
                    if promotion.ends_at and promotion.ends_at < now:
                        return None, {"items": f"Promotion {promotion.name} has expired"}
                    
                    for bundle_item in promotion.items.all():
                        item_quantity = bundle_item.quantity * requested_quantity
                        
                        if bundle_item.variant.stock < item_quantity:
                            return None, {"items": f"Insufficient stock for {bundle_item.variant.sku} in bundle {promotion.name}"}
                        
                        unit_price = Decimal('0.00') if bundle_item.is_free else bundle_item.original_price
                        
                        order_items_data.append({
                            'variant': bundle_item.variant,
                            'quantity': item_quantity,
                            'unit_price': unit_price,
                            'product_title': bundle_item.variant.product.title,
                            'product_slug': bundle_item.variant.product.slug,
                            'variant_attributes': bundle_item.variant.attributes,
                            'sku': bundle_item.variant.sku,
                            'is_bundle_item': True,
                            'bundle_id': str(promotion.id),
                            'bundle_name': promotion.name,
                        })
                        
                        subtotal += unit_price * Decimal(str(item_quantity))
                        variants_for_weight.append({'variant': bundle_item.variant, 'quantity': item_quantity})
                        
                else:
                    variant_id = item_data.get('variant_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        variant = ProductVariant.objects.select_related('product').get(
                            id=variant_id, is_active=True
                        )
                    except ProductVariant.DoesNotExist:
                        return None, {"items": f"Product variant not found: {variant_id}"}
                    
                    if not variant.is_active:
                        return None, {"items": f"Variant {variant.sku} is no longer available"}
                    
                    if variant.product.status != Product.STATUS_PUBLISHED:
                        return None, {"items": f"Product {variant.product.title} is not available"}
                    
                    if variant.stock < requested_quantity:
                        return None, {"items": f"Insufficient stock for {variant.sku}. Available: {variant.stock}"}
                    
                    unit_price = variant.discounted_price
                    
                    order_items_data.append({
                        'variant': variant,
                        'quantity': requested_quantity,
                        'unit_price': unit_price,
                        'product_title': variant.product.title,
                        'product_slug': variant.product.slug,
                        'variant_attributes': variant.attributes,
                        'sku': variant.sku,
                        'is_bundle_item': False,
                    })
                    
                    subtotal += unit_price * Decimal(str(requested_quantity))
                    variants_for_weight.append({'variant': variant, 'quantity': requested_quantity})

            # Create shipping address
            shipping_address = OrderService._create_or_get_address(shipping_address_data, customer, 'shipping')
            
            # Calculate shipping cost
            total_weight = ShippingCalculator.calculate_order_weight(variants_for_weight)
            shipping_calculation = ShippingCalculator.calculate_shipping_cost(
                country_code=shipping_address.country,
                total_weight_kg=total_weight,
                subtotal=subtotal,
            )
            
            shipping_cost = shipping_calculation['cost']
            shipping_method = shipping_calculation['method_name']
            
            tax_amount = Decimal('0.00')
            discount_amount = Decimal('0.00')
            total = subtotal + shipping_cost + tax_amount - discount_amount

            # Create order
            order = Order.objects.create(
                user=customer,
                guest_email=guest_info.get('email', '') if guest_info else shipping_address.email,
                guest_first_name=guest_info.get('first_name', '') if guest_info else shipping_address.first_name,
                guest_last_name=guest_info.get('last_name', '') if guest_info else shipping_address.last_name,
                guest_phone=guest_info.get('phone', '') if guest_info else shipping_address.phone,
                shipping_address=shipping_address,
                billing_address=shipping_address,
                payment_method=payment_method,
                shipping_method=shipping_method,
                shipping_cost=shipping_cost,
                tax_rate=Decimal('0.00'),
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                subtotal=subtotal,
                total=total,
                customer_note=customer_note,
                currency=currency,
                created_by=created_by,  # Track who created this order
            )

            # Create order items and reduce stock
            for item_data in order_items_data:
                OrderItem.objects.create(
                    order=order,
                    variant=item_data['variant'],
                    product_title=item_data['product_title'],
                    product_slug=item_data['product_slug'],
                    variant_attributes=item_data['variant_attributes'],
                    sku=item_data['sku'],
                    unit_price=item_data['unit_price'],
                    quantity=item_data['quantity'],
                    is_bundle_item=item_data.get('is_bundle_item', False),
                    bundle_id=item_data.get('bundle_id', ''),
                    bundle_name=item_data.get('bundle_name', ''),
                )
                item_data['variant'].reduce_stock(item_data['quantity'])

            # Handle payment status based on method
            if payment_method == 'pos':
                order.payment_status = Order.PAYMENT_PAID
                order.status = Order.STATUS_CONFIRMED
                order.confirmed_at = timezone.now()
                order.paid_at = timezone.now()
                order.payment_type = 'pos'
            elif payment_method == 'cash_on_delivery' or payment_method == 'pod':
                order.payment_status = Order.PAYMENT_PENDING
                order.status = Order.STATUS_CONFIRMED
                order.confirmed_at = timezone.now()
                order.payment_type = Order.PAYMENT_TYPE_POD
                order.pod_eligible = True
            else:
                # POS orders are settled in person; online checkout is not
                # supported here (no gateway redirect path). Reject rather than
                # create an uncollectible pending order.
                transaction.set_rollback(True)
                return None, {"payment_method": f"Unsupported POS payment method: {payment_method}"}

            order.save()

            logger.info(f"POS shipping order created by {created_by.email if created_by else 'unknown'}: {order.order_number} with subtotal=${subtotal}, shipping=${shipping_cost}, total=${total}")
            return order, None

        except ValueError as e:
            transaction.set_rollback(True)
            logger.warning(f"POS shipping order stock conflict: {str(e)}")
            return None, {"items": str(e)}
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"POS shipping order creation error: {str(e)}", exc_info=True)
            return None, {"general": f"Failed to create POS order: {str(e)}"}


class AddressService:
    """Address business logic"""

    @staticmethod
    def get_user_addresses(user: User, address_type: str = None, active_only: bool = True) -> List[Address]:
        """Get addresses for user"""
        from apps.orders.selectors import get_user_addresses
        return get_user_addresses(user, address_type, active_only)

    @staticmethod
    @transaction.atomic
    def create_address(
        user: User,
        address_type: str,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        address_line1: str,
        city: str,
        state: str,
        postal_code: str,
        country: str,
        company: str = "",
        address_line2: str = "",
        instructions: str = "",
        is_default: bool = False,
    ) -> Tuple[Optional[Address], Optional[Dict]]:
        """Create a new address for user"""
        try:
            # If this is default, remove default from other addresses of same type
            if is_default:
                Address.objects.filter(
                    user=user, 
                    address_type=address_type, 
                    is_default=True
                ).update(is_default=False)

            address = Address.objects.create(
                user=user,
                address_type=address_type,
                first_name=first_name,
                last_name=last_name,
                company=company,
                phone=phone,
                email=email,
                address_line1=address_line1,
                address_line2=address_line2,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                instructions=instructions,
                is_default=is_default,
            )

            logger.info(f"Address created for user {user.email}")
            return address, None

        except Exception as e:
            logger.error(f"Address creation error: {str(e)}")
            return None, {"general": f"Failed to create address: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def update_address(
        address_id: str,
        user: User,
        **kwargs
    ) -> Tuple[Optional[Address], Optional[Dict]]:
        """Update an existing address"""
        try:
            address = get_address_by_id(address_id, user)
            if not address:
                return None, {"address": "Address not found"}

            # Handle default flag
            if kwargs.get('is_default'):
                Address.objects.filter(
                    user=user,
                    address_type=address.address_type,
                    is_default=True
                ).exclude(id=address.id).update(is_default=False)

            # Update fields
            updatable_fields = [
                'first_name', 'last_name', 'company', 'phone', 'email',
                'address_line1', 'address_line2', 'city', 'state',
                'postal_code', 'country', 'instructions', 'is_default'
            ]

            for field in updatable_fields:
                if field in kwargs:
                    setattr(address, field, kwargs[field])

            address.save()

            logger.info(f"Address {address_id} updated for user {user.email}")
            return address, None

        except Exception as e:
            logger.error(f"Address update error: {str(e)}")
            return None, {"general": f"Failed to update address: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def delete_address(address_id: str, user: User) -> Tuple[bool, Optional[Dict]]:
        """Soft delete an address"""
        try:
            address = get_address_by_id(address_id, user)
            if not address:
                return False, {"address": "Address not found"}

            address.is_active = False
            address.save()

            logger.info(f"Address {address_id} deleted for user {user.email}")
            return True, None

        except Exception as e:
            logger.error(f"Address deletion error: {str(e)}")
            return False, {"general": f"Failed to delete address: {str(e)}"}
