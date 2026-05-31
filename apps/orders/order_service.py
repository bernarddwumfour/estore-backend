import logging
from typing import Dict, Optional, List, Tuple
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
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Create a new order - VERIFIES prices and EXPANDS bundles on server side"""
        try:
            from apps.orders.shipping_calculator import ShippingCalculator
            from apps.orders.payment_config import PaymentConfigService
            from apps.promotions.models import Promotion
            
            has_user = user is not None
            
            subtotal = Decimal('0.00')
            order_items_data = []
            variants_for_weight = []

            for item_data in items:
                if item_data.get('is_bundle'):
                    # Handle bundle/promotion - VERIFY bundle exists and is active
                    bundle_id = item_data.get('bundle_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        promotion = Promotion.objects.get(id=bundle_id)
                    except Promotion.DoesNotExist:
                        return None, {"items": f"Promotion bundle not found: {bundle_id}"}
                    
                    # Verify promotion is active
                    if promotion.status != Promotion.STATUS_ACTIVE:
                        return None, {"items": f"Promotion {promotion.name} is not active"}
                    
                    # Verify promotion hasn't expired
                    now = timezone.now()
                    if promotion.starts_at > now:
                        return None, {"items": f"Promotion {promotion.name} has not started yet"}
                    if promotion.ends_at and promotion.ends_at < now:
                        return None, {"items": f"Promotion {promotion.name} has expired"}
                    
                    # Verify client price matches server price
                    client_price = Decimal(str(item_data.get('price', 0)))
                    server_price = promotion.bundle_price
                    
                    if client_price != server_price:
                        logger.warning(f"Price mismatch for bundle {promotion.name}: client={client_price}, server={server_price}")
                        return None, {"items": f"Price mismatch for promotion bundle. Please refresh and try again."}
                    
                    # Expand bundle items
                    for bundle_item in promotion.items.all():
                        item_quantity = bundle_item.quantity * requested_quantity
                        
                        # Verify stock
                        if bundle_item.variant.stock < item_quantity:
                            return None, {"items": f"Insufficient stock for {bundle_item.variant.sku} in bundle {promotion.name}"}
                        
                        # Calculate price (free items have zero price)
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
                            'bundle_price': float(promotion.bundle_price),
                        })
                        
                        subtotal += unit_price * Decimal(str(item_quantity))
                        variants_for_weight.append({'variant': bundle_item.variant, 'quantity': item_quantity})
                        
                else:
                    # Handle regular variant
                    variant_id = item_data.get('variant_id')
                    requested_quantity = item_data.get('quantity', 1)
                    
                    try:
                        variant = ProductVariant.objects.select_related('product').get(
                            id=variant_id, is_active=True
                        )
                    except ProductVariant.DoesNotExist:
                        return None, {"items": f"Product variant not found: {variant_id}"}
                    
                    # Verify variant is active
                    if not variant.is_active:
                        return None, {"items": f"Variant {variant.sku} is no longer available"}
                    
                    # Verify product is published
                    if variant.product.status != Product.STATUS_PUBLISHED:
                        return None, {"items": f"Product {variant.product.title} is not available"}
                    
                    # Verify stock
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
            shipping_address = OrderService._create_or_get_address(shipping_address_data, user, 'shipping')
            
            if billing_address_data:
                billing_address = OrderService._create_or_get_address(billing_address_data, user, 'billing')
            else:
                billing_address = shipping_address

            # Calculate shipping cost based on weight and destination
            total_weight = ShippingCalculator.calculate_order_weight(variants_for_weight)
            shipping_calculation = ShippingCalculator.calculate_shipping_cost(
                country_code=shipping_address.country,
                total_weight_kg=total_weight,
                subtotal=subtotal,
            )
            
            shipping_cost = shipping_calculation['cost']
            shipping_method = shipping_calculation['method_name']
            
            logger.info(f"Shipping calculation: weight={total_weight}kg, cost=${shipping_cost}, method={shipping_method}")
            
            # Calculate tax (simple example - customize as needed)
            tax_rate = Decimal('0.00')
            tax_amount = Decimal('0.00')
            discount_amount = Decimal('0.00')
            
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
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
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

            logger.info(f"Order created: {order.order_number} with subtotal=${subtotal}, shipping=${shipping_cost}, total=${total}")
            return order, None

        except Exception as e:
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

    @staticmethod
    @transaction.atomic
    def update_order_status(
        order_id: str,
        status: str,
        admin_note: str = None,
        carrier: str = None,
        tracking_number: str = None,
        user: User = None
    ) -> Tuple[Optional[Order], Optional[Dict]]:
        """Update order status and create/update shipment when marked as shipped"""
        try:
            from apps.orders.models import Shipment, ShipmentTracking
            
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            # Validate status transition
            valid_statuses = dict(Order.STATUS_CHOICES).keys()
            if status not in valid_statuses:
                return None, {"status": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}

            # Update order status and timestamps
            old_status = order.status
            order.status = status
            
            if status == Order.STATUS_CONFIRMED and not order.confirmed_at:
                order.confirmed_at = timezone.now()
            elif status == Order.STATUS_SHIPPED and not order.shipped_at:
                order.shipped_at = timezone.now()
            elif status == Order.STATUS_DELIVERED and not order.delivered_at:
                order.delivered_at = timezone.now()
            elif status == Order.STATUS_CANCELLED and not order.cancelled_at:
                order.cancelled_at = timezone.now()
                
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

            # Handle Shipment creation/updates
            if status == Order.STATUS_SHIPPED:
                try:
                    # Try to get existing shipment
                    shipment = order.shipment
                    # Update existing shipment
                    if shipment.status != Shipment.STATUS_SHIPPED:
                        shipment.status = Shipment.STATUS_SHIPPED
                        if tracking_number:
                            shipment.tracking_number = tracking_number
                        if carrier:
                            shipment.carrier = carrier
                        shipment.save()
                        
                        ShipmentTracking.objects.create(
                            shipment=shipment,
                            status=Shipment.STATUS_SHIPPED,
                            description=f"Order status changed from {old_status} to {status}",
                            created_by=user,
                        )
                        logger.info(f"Shipment updated for order {order.order_number}")
                except Exception as e:
                    # Create new shipment
                    shipment = Shipment.objects.create(
                        order=order,
                        status=Shipment.STATUS_SHIPPED,
                        carrier=carrier or '',
                        tracking_number=tracking_number or '',
                        created_by=user,
                        notes=f"Shipment created when order status changed to {status}"
                    )
                    
                    ShipmentTracking.objects.create(
                        shipment=shipment,
                        status=Shipment.STATUS_SHIPPED,
                        description="Shipment created",
                        created_by=user,
                    )
                    logger.info(f"Shipment created for order {order.order_number}")
                    
            elif status == Order.STATUS_DELIVERED:
                try:
                    shipment = order.shipment
                    if shipment.status != Shipment.STATUS_DELIVERED:
                        shipment.status = Shipment.STATUS_DELIVERED
                        shipment.delivered_at = timezone.now()
                        shipment.save()
                        
                        ShipmentTracking.objects.create(
                            shipment=shipment,
                            status=Shipment.STATUS_DELIVERED,
                            description="Order marked as delivered",
                            created_by=user,
                        )
                        logger.info(f"Shipment marked as delivered for order {order.order_number}")
                except:
                    logger.warning(f"No shipment found for delivered order {order.order_number}")
                    
            elif status == Order.STATUS_CANCELLED:
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
                except:
                    pass

            logger.info(f"Order {order.order_number} status updated from {old_status} to {status}")
            return order, None

        except Exception as e:
            logger.error(f"Order status update error: {str(e)}")
            return None, {"general": f"Failed to update order status: {str(e)}"}

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
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            valid_statuses = dict(Order.PAYMENT_STATUS_CHOICES).keys()
            if payment_status not in valid_statuses:
                return None, {"payment_status": f"Invalid payment status. Must be one of: {', '.join(valid_statuses)}"}

            order.payment_status = payment_status

            if payment_intent_id:
                order.payment_intent_id = payment_intent_id
            if payment_receipt_url:
                order.payment_receipt_url = payment_receipt_url

            # Auto-update order status if payment is paid
            if payment_status == Order.PAYMENT_PAID and order.status == Order.STATUS_PENDING:
                order.status = Order.STATUS_CONFIRMED
                order.confirmed_at = timezone.now()
                order.paid_at = timezone.now()

            order.save()

            logger.info(f"Order {order.order_number} payment status updated to {payment_status}")
            return order, None

        except Exception as e:
            logger.error(f"Payment status update error: {str(e)}")
            return None, {"general": f"Failed to update payment status: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def cancel_order(order_id: str, user: User = None, reason: str = "") -> Tuple[Optional[Order], Optional[Dict]]:
        """Cancel an order"""
        try:
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

            logger.info(f"Order {order.order_number} cancelled")
            return order, None

        except Exception as e:
            logger.error(f"Order cancellation error: {str(e)}")
            return None, {"general": f"Failed to cancel order: {str(e)}"}
        
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