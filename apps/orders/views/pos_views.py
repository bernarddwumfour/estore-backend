"""
POS Views - Point of Sale order creation for admin/staff
"""

import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.db.models import Q

from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.common.logging import log_action, LogSeverity, get_user_info
from apps.orders.selectors.address_selectors import get_user_addresses, get_address_by_id
from apps.orders.schemas import serialize_order
from apps.orders.schemas.address_schemas import serialize_address, validate_address_create, validate_address_update
from apps.orders.order_service import OrderService, AddressService
from apps.products.models import ProductVariant
from apps.promotions.models import Promotion
from apps.users.models import User

logger = logging.getLogger(__name__)
APP_NAME = "orders"


# ==================== CUSTOMER ADDRESS MANAGEMENT ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pos_get_customer_addresses(request, customer_id):
    """Get all shipping addresses for a customer"""
    start_time = time.time()
    action = "pos_get_customer_addresses"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Getting addresses for customer: {customer_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"customer_id": customer_id}
    )
    
    try:
        # Verify customer exists
        try:
            customer = User.objects.get(id=customer_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.not_found("Customer not found")
        
        # Get addresses for customer (using existing selector)
        addresses = get_user_addresses(customer, address_type='shipping', only_active=True)
        
        addresses_data = [serialize_address(addr, is_admin=True) for addr in addresses]
        
        # Find default address
        default_address = None
        for addr in addresses:
            if addr.is_default:
                default_address = serialize_address(addr, is_admin=True)
                break
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Retrieved {len(addresses)} addresses for customer {customer.email}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "customer_id": customer_id,
                "addresses_count": len(addresses),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(
            data={
                "addresses": addresses_data,
                "default_address": default_address,
            },
            message="Customer addresses retrieved successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to get customer addresses: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"customer_id": customer_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def pos_create_customer_address(request, customer_id):
    """Create a new shipping address for a customer"""
    start_time = time.time()
    action = "pos_create_customer_address"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Creating address for customer: {customer_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"customer_id": customer_id}
    )
    
    try:
        # Verify customer exists
        try:
            customer = User.objects.get(id=customer_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.not_found("Customer not found")
        
        data = request.json_data
        
        # Validate address data
        cleaned, errors = validate_address_create(data)
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Address validation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        # Create address using existing service
        address, error = AddressService.create_address(
            user=customer,
            address_type='shipping',
            first_name=cleaned.get('first_name'),
            last_name=cleaned.get('last_name'),
            phone=cleaned.get('phone'),
            email=cleaned.get('email', customer.email),
            address_line1=cleaned.get('address_line1'),
            city=cleaned.get('city'),
            state=cleaned.get('state', ''),
            postal_code=cleaned.get('postal_code'),
            country=cleaned.get('country', 'GH'),
            company=cleaned.get('company', ''),
            address_line2=cleaned.get('address_line2', ''),
            instructions=cleaned.get('instructions', ''),
            is_default=cleaned.get('is_default', False),
        )
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Address creation failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        address_data = serialize_address(address, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Address created for customer {customer.email}",
            status_code=201,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "customer_id": customer_id,
                "address_id": str(address.id),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.created(
            data={"address": address_data},
            message="Address created successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to create address: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"customer_id": customer_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='PUT', block=True)
def pos_update_customer_address(request, customer_id, address_id):
    """Update a customer's shipping address"""
    start_time = time.time()
    action = "pos_update_customer_address"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Updating address {address_id} for customer: {customer_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"customer_id": customer_id, "address_id": address_id}
    )
    
    try:
        # Verify customer exists
        try:
            customer = User.objects.get(id=customer_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.not_found("Customer not found")
        
        # Verify address belongs to customer (using existing selector)
        address = get_address_by_id(address_id, customer)
        if not address:
            return APIResponse.not_found("Address not found")
        
        data = request.json_data
        
        # Validate update data
        cleaned, errors = validate_address_update(data)
        if errors:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description="Address update validation failed",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"errors": errors, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(errors)
        
        # Update address using existing service
        updated_address, error = AddressService.update_address(
            address_id=address_id,
            user=customer,
            **cleaned
        )
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Address update failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        address_data = serialize_address(updated_address, is_admin=True)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Address updated for customer {customer.email}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "customer_id": customer_id,
                "address_id": address_id,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(
            data={"address": address_data},
            message="Address updated successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to update address: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"customer_id": customer_id, "address_id": address_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='30/h', method='DELETE', block=True)
def pos_delete_customer_address(request, customer_id, address_id):
    """Delete a customer's shipping address (soft delete)"""
    start_time = time.time()
    action = "pos_delete_customer_address"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Deleting address {address_id} for customer: {customer_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"customer_id": customer_id, "address_id": address_id}
    )
    
    try:
        # Verify customer exists
        try:
            customer = User.objects.get(id=customer_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.not_found("Customer not found")
        
        # Verify address belongs to customer
        address = get_address_by_id(address_id, customer)
        if not address:
            return APIResponse.not_found("Address not found")
        
        # Soft delete address
        success, error = AddressService.delete_address(address_id, customer)
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Address deletion failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Address deleted for customer {customer.email}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "customer_id": customer_id,
                "address_id": address_id,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(message="Address deleted successfully")
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to delete address: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"customer_id": customer_id, "address_id": address_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def pos_calculate_shipping_for_address(request):
    """Calculate shipping cost for a given address (for POS)"""
    start_time = time.time()
    action = "pos_calculate_shipping_for_address"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Calculating shipping for address",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        address = data.get('address', {})
        items = data.get('items', [])
        
        if not items:
            return APIResponse.bad_request("Items are required")
        
        if not address:
            return APIResponse.bad_request("Address is required")
        
        from apps.orders.shipping_calculator import ShippingCalculator
        from decimal import Decimal
        
        total_weight = Decimal('0.00')
        subtotal = Decimal('0.00')
        
        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 1)
            
            try:
                variant = ProductVariant.objects.get(id=variant_id, is_active=True)
                
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * Decimal(str(quantity))
                else:
                    total_weight += Decimal('0.5') * Decimal(str(quantity))
                
                # Calculate subtotal from DB for accurate price verification
                subtotal += variant.discounted_price * Decimal(str(quantity))
                
            except ProductVariant.DoesNotExist:
                total_weight += Decimal('0.5') * Decimal(str(quantity))
        
        # Get country code from address
        country_code = address.get('country', 'GH')
        
        # Calculate shipping cost
        shipping_calculation = ShippingCalculator.calculate_shipping_cost(
            country_code=country_code,
            total_weight_kg=total_weight,
            subtotal=subtotal,
        )
        
        shipping_cost = shipping_calculation['cost']
        shipping_method = shipping_calculation['method_name']
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"Shipping calculated: ${shipping_cost} via {shipping_method}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "shipping_cost": float(shipping_cost),
                "shipping_method": shipping_method,
                "total_weight_kg": float(total_weight),
                "subtotal": float(subtotal),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.success(
            data={
                "shipping_cost": float(shipping_cost),
                "shipping_method": shipping_method,
                "total_weight_kg": float(total_weight),
                "subtotal": float(subtotal),
            },
            message="Shipping calculated successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Failed to calculate shipping: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()



@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def pos_create_order(request):
    """POS: Create an order - supports both in-store pickup and shipping with saved addresses"""
    start_time = time.time()
    action = "pos_create_order"
    user = request.user  # This is the staff/admin creating the order
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="POS order creation request",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        
        customer_id = data.get('customer_id')
        customer_email = data.get('customer_email')
        is_guest = data.get('is_guest', True)
        is_pickup = data.get('is_pickup', True)  # True = in-store pickup, False = shipping
        payment_method = data.get('payment_method', 'pos')

        # POS orders are settled in person: paid at the counter ('pos') or on
        # delivery. Online checkout (paystack) is not supported here because the
        # POS flow has no way to redirect the customer to the gateway, and would
        # otherwise create an uncollectible pending order.
        allowed_pos_methods = {'pos', 'cash_on_delivery', 'pod'}
        if payment_method not in allowed_pos_methods:
            return APIResponse.bad_request(
                "Unsupported POS payment method. Choose 'pos' (paid in-store) "
                "or 'cash_on_delivery'."
            )

        # Get or find customer
        if not is_guest and customer_id:
            try:
                order_user = User.objects.get(id=customer_id, is_active=True)
            except User.DoesNotExist:
                return APIResponse.not_found("Customer not found")
        elif not is_guest and customer_email:
            try:
                order_user = User.objects.get(email=customer_email, is_active=True)
            except User.DoesNotExist:
                return APIResponse.not_found(f"Customer with email {customer_email} not found")
        else:
            order_user = None
        
        # Process items
        items = []
        for item in data.get('items', []):
            if item.get('is_bundle'):
                try:
                    promotion = Promotion.objects.get(id=item['bundle_id'], status=Promotion.STATUS_ACTIVE)
                    
                    if not promotion.is_currently_active:
                        return APIResponse.bad_request(f"Promotion {promotion.name} is no longer active")
                    
                    if not promotion.has_stock:
                        return APIResponse.bad_request(f"Promotion {promotion.name} is out of stock")
                    
                    items.append({
                        'is_bundle': True,
                        'bundle_id': str(promotion.id),
                        'bundle_name': promotion.name,
                        'price': float(promotion.bundle_price),
                        'quantity': item.get('quantity', 1),
                        'bundle_items': [
                            {
                                'variant_id': str(bi.variant.id),
                                'quantity': bi.quantity,
                                'is_free': bi.is_free,
                                'original_price': float(bi.original_price),
                            }
                            for bi in promotion.items.all()
                        ],
                    })
                except Promotion.DoesNotExist:
                    return APIResponse.not_found(f"Promotion not found: {item['bundle_id']}")
            else:
                variant = ProductVariant.objects.select_related('product').get(
                    id=item['variant_id'], is_active=True
                )
                items.append({
                    'is_bundle': False,
                    'variant_id': str(variant.id),
                    'quantity': item.get('quantity', 1),
                    'price': float(variant.discounted_price),
                })
        
        if not items:
            return APIResponse.bad_request("No items to order")
        
        # Prepare guest info
        guest_info = None
        if not order_user:
            guest_info = {
                'email': customer_email or '',
                'first_name': data.get('customer_name', '').split()[0] if data.get('customer_name') else '',
                'last_name': ' '.join(data.get('customer_name', '').split()[1:]) if data.get('customer_name') else '',
                'phone': '',
            }
            
        
        # Handle shipping address based on delivery option
        if is_pickup:
            # In-store pickup - no shipping
            order, error = OrderService.create_pos_pickup_order(
                customer=order_user,
                items=items,
                payment_method=payment_method,
                guest_info=guest_info,
                customer_note=data.get('customer_note', ''),
                currency=data.get('currency', 'GHS'),
                created_by=user,
            )
        else:
            # With shipping - determine address source
            shipping_address_data = None
            saved_address_id = data.get('saved_address_id')
            
            # Check if using a saved address
            if saved_address_id and order_user:
                # Use existing selector to get saved address
                from apps.orders.selectors.address_selectors import get_address_by_id
                saved_address = get_address_by_id(saved_address_id, order_user)
                if saved_address:
                    shipping_address_data = {
                        'first_name': saved_address.first_name,
                        'last_name': saved_address.last_name,
                        'email': saved_address.email,
                        'phone': saved_address.phone,
                        'address_line1': saved_address.address_line1,
                        'address_line2': saved_address.address_line2 or '',
                        'city': saved_address.city,
                        'state': saved_address.state or '',
                        'postal_code': saved_address.postal_code,
                        'country': saved_address.country,
                        'instructions': saved_address.instructions or '',
                    }
            
            # If no saved address or address not found, use provided address
            if not shipping_address_data:
                shipping_address_data = {
                    'first_name': data.get('shipping_address', {}).get('first_name', ''),
                    'last_name': data.get('shipping_address', {}).get('last_name', ''),
                    'email': data.get('shipping_address', {}).get('email', customer_email or ''),
                    'phone': data.get('shipping_address', {}).get('phone', ''),
                    'address_line1': data.get('shipping_address', {}).get('address_line1', ''),
                    'address_line2': data.get('shipping_address', {}).get('address_line2', ''),
                    'city': data.get('shipping_address', {}).get('city', ''),
                    'state': data.get('shipping_address', {}).get('state', ''),
                    'postal_code': data.get('shipping_address', {}).get('postal_code', ''),
                    'country': data.get('shipping_address', {}).get('country', 'GH'),
                }
            
            # Optionally save the address as a saved address for future use
            save_address = data.get('save_address', False)
            if save_address and order_user and not saved_address_id:
                from apps.orders.schemas.address_schemas import validate_address_create
                from apps.orders.order_service import AddressService
                
                # Create a new saved address from the shipping address
                address_data = {
                    'first_name': shipping_address_data['first_name'],
                    'last_name': shipping_address_data['last_name'],
                    'phone': shipping_address_data['phone'],
                    'email': shipping_address_data['email'],
                    'address_line1': shipping_address_data['address_line1'],
                    'address_line2': shipping_address_data['address_line2'],
                    'city': shipping_address_data['city'],
                    'state': shipping_address_data['state'],
                    'postal_code': shipping_address_data['postal_code'],
                    'country': shipping_address_data['country'],
                    'instructions': shipping_address_data.get('instructions', ''),
                }
                
                cleaned, addr_errors = validate_address_create(address_data)
                if not addr_errors:
                    AddressService.create_address(
                        user=order_user,
                        address_type='shipping',
                        first_name=cleaned.get('first_name'),
                        last_name=cleaned.get('last_name'),
                        phone=cleaned.get('phone'),
                        email=cleaned.get('email', order_user.email),
                        address_line1=cleaned.get('address_line1'),
                        city=cleaned.get('city'),
                        state=cleaned.get('state', ''),
                        postal_code=cleaned.get('postal_code'),
                        country=cleaned.get('country', 'GH'),
                        company=cleaned.get('company', ''),
                        address_line2=cleaned.get('address_line2', ''),
                        instructions=cleaned.get('instructions', ''),
                        is_default=False,
                    )
                    log_action(
                        logger=logger,
                        severity=LogSeverity.INFO,
                        action=action,
                        description=f"Address saved for future use for customer {order_user.email}",
                        status_code=0,
                        user=user,
                        request=request,
                        app_name=APP_NAME,
                        extra={"customer_id": customer_id}
                    )
            
            order, error = OrderService.create_pos_shipping_order(
                customer=order_user,
                items=items,
                shipping_address_data=shipping_address_data,
                payment_method=payment_method,
                guest_info=guest_info,
                customer_note=data.get('customer_note', ''),
                currency=data.get('currency', 'GHS'),
                created_by=user,
            )
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"POS order creation failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"POS order created: {order.order_number}",
            status_code=201,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "items_count": len(items),
                "total": float(order.total),
                "customer": order.customer_email,
                "is_pickup": is_pickup,
                "payment_method": payment_method,
                "created_by": get_user_info(user),
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return APIResponse.created(
            data={
                "order": serialize_order(order, is_admin=True, detailed=True),
            },
            message="POS order created successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"POS order creation error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pos_search_customers(request):
    """Search customers for POS order creation"""
    start_time = time.time()
    action = "pos_search_customers"
    user = request.user
    
    try:
        search = request.GET.get('search', '').strip()
        limit = min(int(request.GET.get('limit', 20)), 50)
        
        if not search or len(search) < 2:
            return APIResponse.success(
                data={"customers": []},
                message="Enter at least 2 characters to search"
            )
        
        customers = User.objects.filter(
            is_active=True,
            # role__in=['customer', 'admin', 'staff']
        ).filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        ).values('id', 'email', 'first_name', 'last_name')[:limit]
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Customer search completed: {customers.count()} results",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"search_term": search, "results_count": customers.count(), "duration_ms": round(duration_ms, 2)}
        )
        
        return APIResponse.success(
            data={
                "customers": [
                    {
                        "id": str(c['id']),
                        "email": c['email'],
                        "name": f"{c['first_name']} {c['last_name']}".strip() or c['email'],
                        "first_name": c['first_name'],
                        "last_name": c['last_name'],
                    }
                    for c in customers
                ]
            },
            message="Customers retrieved"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Customer search error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pos_get_active_promotions(request):
    """Get active promotions for POS interface"""
    start_time = time.time()
    action = "pos_get_active_promotions"
    user = request.user
    
    try:
        from django.utils import timezone
        now = timezone.now()
        
        promotions = Promotion.objects.filter(
            status=Promotion.STATUS_ACTIVE,
            starts_at__lte=now,
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gte=now)
        ).values('id', 'name', 'slug', 'bundle_price', 'original_total', 'savings_amount', 'savings_percentage')
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Active promotions retrieved: {promotions.count()}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotions_count": promotions.count(), "duration_ms": round(duration_ms, 2)}
        )
        
        return APIResponse.success(
            data={
                "promotions": [
                    {
                        "id": str(p['id']),
                        "name": p['name'],
                        "slug": p['slug'],
                        "bundle_price": float(p['bundle_price']),
                        "original_total": float(p['original_total']),
                        "savings_amount": float(p['savings_amount']),
                        "savings_percentage": p['savings_percentage'],
                    }
                    for p in promotions
                ]
            },
            message="Active promotions retrieved"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Get promotions error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()