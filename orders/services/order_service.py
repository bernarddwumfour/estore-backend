# services/order_service.py
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from decimal import Decimal
import random
from typing import List, Dict, Optional, Tuple
import uuid

from ..models import Order, OrderItem, ProductVariant, Address


class AddressService:
    """
    Service for handling address-related operations
    """

    @staticmethod
    def create_address_from_data(
        data: Dict, user=None, address_type: str = "shipping"
    ) -> Address:
        """
        Create address from data dictionary
        """
        required_fields = [
            "first_name",
            "last_name",
            "address_line1",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
            "email",
        ]

        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"Missing required field: {field}")

        # Create address
        address = Address.objects.create(
            user=user,
            address_type=address_type,
            first_name=data["first_name"],
            last_name=data["last_name"],
            company=data.get("company", ""),
            phone=data["phone"],
            email=data["email"],
            address_line1=data["address_line1"],
            address_line2=data.get("address_line2", ""),
            city=data["city"],
            state=data["state"],
            postal_code=data["postal_code"],
            country=data["country"],
            instructions=data.get("instructions", ""),
            is_default=data.get("is_default", False),
        )

        return address

    @staticmethod
    def update_address(address_id: str, data: Dict, user=None) -> Address:
        """
        Update existing address
        """
        try:
            address = Address.objects.get(id=address_id, user=user)
        except Address.DoesNotExist:
            raise ValidationError("Address not found")

        # Update fields
        updatable_fields = [
            "first_name",
            "last_name",
            "company",
            "phone",
            "email",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            "instructions",
            "is_default",
        ]

        for field in updatable_fields:
            if field in data:
                setattr(address, field, data[field])

        address.save()
        return address

    @staticmethod
    def delete_address(address_id: str, user=None) -> bool:
        """
        Delete address (soft delete)
        """
        try:
            address = Address.objects.get(id=address_id, user=user)
            address.is_active = False
            address.save()
            return True
        except Address.DoesNotExist:
            raise ValidationError("Address not found")

    @staticmethod
    def get_user_addresses(
        user, address_type: str = None, active_only: bool = True
    ) -> List[Address]:
        """
        Get addresses for user
        """
        queryset = Address.objects.filter(user=user)

        if active_only:
            queryset = queryset.filter(is_active=True)

        if address_type:
            queryset = queryset.filter(address_type=address_type)

        return queryset.order_by("-is_default", "-created_at")

    @staticmethod
    def get_or_create_guest_address(
        data: Dict, address_type: str = "shipping"
    ) -> Address:
        """
        Create address for guest order (no user association)
        """
        return AddressService.create_address_from_data(
            data, user=None, address_type=address_type
        )


class OrderService:
    """
    Service class for handling order-related business logic
    """

    @staticmethod
    def generate_order_number() -> str:
        """Generate unique order number"""
        date_str = timezone.now().strftime("%Y%m%d")
        random_str = str(random.randint(1000, 9999))
        return f"ORD{date_str}{random_str}"

    @classmethod
    @classmethod
    def validate_order_data(cls, data: Dict) -> Tuple[bool, List[str], Dict]:
        """
        Validate and normalize order data
        """
        errors = []
        normalized = data.copy()

        # Validate user/guest consistency
        has_guest_data = any(
            data.get(field)
            for field in [
                "guest_email",
                "guest_first_name",
                "guest_last_name",
                "guest_phone",
            ]
        )

        # If user is authenticated, they shouldn't provide guest data
        # (This check will be done in the view with actual user object)
        # We'll add a note that view should handle this

        # Validate required fields
        required_fields = ["items", "shipping_address", "payment_method"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Validate items
        if "items" in data:
            if not isinstance(data["items"], list):
                errors.append("Items must be a list")
            elif len(data["items"]) == 0:
                errors.append("Order must contain at least one item")
            else:
                # Validate each item
                for i, item in enumerate(data["items"]):
                    if "variant_id" not in item:
                        errors.append(f"Item {i}: Missing variant_id")
                    if "quantity" not in item or item["quantity"] < 1:
                        errors.append(f"Item {i}: Invalid quantity")

                    # Don't allow users to set their own prices
                    if "unit_price" in item:
                        errors.append(f"Item {i}: Custom prices not allowed")

        # Validate shipping address for users.Address model
        if "shipping_address" in data:
            shipping = data["shipping_address"]
            required_shipping = [
                "first_name",
                "last_name",
                "phone",
                "email",
                "address_line1",
                "city",
                "state",
                "postal_code",
                "country",
            ]
            for field in required_shipping:
                if field not in shipping or not shipping[field]:
                    errors.append(f"Shipping address: Missing {field}")

        # Validate billing address if provided
        if "billing_address" in data and data.get("use_separate_billing", False):
            billing = data["billing_address"]
            required_billing = [
                "first_name",
                "last_name",
                "phone",
                "email",
                "address_line1",
                "city",
                "state",
                "postal_code",
                "country",
            ]
            for field in required_billing:
                if field not in billing or not billing[field]:
                    errors.append(f"Billing address: Missing {field}")

        # Normalize numeric fields
        numeric_fields = ["shipping_cost", "tax_rate", "discount_amount"]
        for field in numeric_fields:
            if field in normalized:
                try:
                    normalized[field] = Decimal(str(normalized[field]))
                except:
                    errors.append(f"Invalid value for {field}")

        # Add use_separate_billing flag if not present
        if "use_separate_billing" not in normalized:
            normalized["use_separate_billing"] = "billing_address" in normalized

        return len(errors) == 0, errors, normalized

    @classmethod
    @transaction.atomic
    def create_order_from_data(
        cls, data: Dict, user=None
    ) -> Tuple[Order, List[OrderItem]]:
        """
        Create order with separate address models
        """
        # Validate data
        is_valid, errors, normalized_data = cls.validate_order_data(data)
        if not is_valid:
            raise ValidationError(f"Invalid order data: {', '.join(errors)}")

        # VALIDATE USER/GUEST CONSISTENCY
        if user and user.is_authenticated:
            # Authenticated user - should not provide guest data
            guest_fields = [
                "guest_email",
                "guest_first_name",
                "guest_last_name",
                "guest_phone",
            ]
            provided_guest_fields = [f for f in guest_fields if normalized_data.get(f)]

            if provided_guest_fields:
                raise ValidationError(
                    f"Authenticated users should not provide guest fields: {', '.join(provided_guest_fields)}"
                )

        else:
            # Guest user - REQUIRE ALL guest fields
            required_guest_fields = [
                "guest_email",
                "guest_first_name",
                "guest_last_name",
                "guest_phone",
            ]
            missing_fields = []

            for field in required_guest_fields:
                if not normalized_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                raise ValidationError(
                    f"Guest checkout requires all guest fields. Missing: {', '.join(missing_fields)}"
                )
        # Extract data
        shipping_address_data = normalized_data["shipping_address"]
        items = normalized_data["items"]
        use_separate_billing = normalized_data.get("use_separate_billing", False)

        # Create or get addresses
        shipping_address = cls._create_or_get_address(
            shipping_address_data, user, "shipping"
        )

        if use_separate_billing and "billing_address" in normalized_data:
            billing_address = cls._create_or_get_address(
                normalized_data["billing_address"], user, "billing"
            )
        else:
            # Use shipping address for billing
            billing_address = shipping_address

        # Calculate subtotal and validate items
        subtotal = Decimal("0.00")
        order_items_data = []

        for item_data in items:
            try:
                variant = ProductVariant.objects.select_related("product").get(
                    id=item_data["variant_id"],
                    is_active=True,
                    product__status="published",
                )
            except ProductVariant.DoesNotExist:
                raise ValidationError(
                    f"Product variant not found: {item_data['variant_id']}"
                )

            # Check stock
            quantity = item_data.get("quantity", 1)
            if variant.stock < quantity:
                raise ValidationError(
                    f"Insufficient stock for {variant.sku}. "
                    f"Available: {variant.stock}, Requested: {quantity}"
                )

            # Get unit price - FIXED: Ensure it's always Decimal
            unit_price_raw = item_data.get("unit_price")
            if unit_price_raw is None:
                # Get variant discounted price
                discounted = variant.discounted_price

                # Force to Decimal
                if isinstance(discounted, (int, float)):
                    unit_price = Decimal(str(discounted))
                elif isinstance(discounted, Decimal):
                    unit_price = discounted
                else:
                    # Last resort: convert to string then Decimal
                    unit_price = Decimal(str(discounted))
            else:
                # Convert provided price to Decimal
                unit_price = Decimal(str(unit_price_raw))

            # Verify it's Decimal
            if not isinstance(unit_price, Decimal):
                unit_price = Decimal(str(unit_price))

            order_items_data.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "product_title": variant.product.title,
                    "product_slug": variant.product.slug,
                    "variant_attributes": variant.attributes,
                    "sku": variant.sku,
                }
            )

            # Ensure multiplication is between Decimals
            subtotal += unit_price * Decimal(str(quantity))

        # Helper function to ensure Decimal
        def ensure_decimal(value, default="0.00"):
            if value is None:
                return Decimal(default)
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))

        # Calculate amounts - all as Decimals
        shipping_cost = ensure_decimal(normalized_data.get("shipping_cost"))
        tax_rate = ensure_decimal(normalized_data.get("tax_rate"))
        discount_amount = ensure_decimal(normalized_data.get("discount_amount"))

        # Calculate tax amount (all Decimals)
        tax_amount = (subtotal * tax_rate) / Decimal("100.00")

        # Create order
        order = Order.objects.create(
            user=user,
            guest_email=normalized_data.get("guest_email", ""),
            guest_first_name=normalized_data.get("guest_first_name", ""),
            guest_last_name=normalized_data.get("guest_last_name", ""),
            guest_phone=normalized_data.get("guest_phone", ""),
            # Address relationships
            shipping_address=shipping_address,
            billing_address=billing_address,
            # Order details
            payment_method=normalized_data["payment_method"],
            shipping_method=normalized_data.get("shipping_method", ""),
            shipping_cost=shipping_cost,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            discount_amount=discount_amount,
            subtotal=subtotal,
            customer_note=normalized_data.get("customer_note", ""),
            currency=normalized_data.get("currency", "USD"),
        )

        print("Here")

        # Create order items and reduce stock
        order_items = []
        for item_data in order_items_data:
            order_item = OrderItem.objects.create(
                order=order,
                variant=item_data["variant"],
                product_title=item_data["product_title"],
                product_slug=item_data["product_slug"],
                variant_attributes=item_data["variant_attributes"],
                sku=item_data["sku"],
                unit_price=item_data["unit_price"],
                quantity=item_data["quantity"],
            )
            order_items.append(order_item)

            # Reduce stock
            item_data["variant"].reduce_stock(item_data["quantity"])

        return order, order_items

    @staticmethod
    def _create_or_get_address(address_data: Dict, user, address_type: str) -> Address:
        """
        Create or reuse address with CORRECT field names
        """
        from users.models import Address

        # For authenticated users, check if similar address exists
        if user and user.is_authenticated:
            existing = Address.objects.filter(
                user=user,
                address_type=address_type,
                first_name=address_data["first_name"],
                last_name=address_data["last_name"],
                address_line1=address_data["address_line1"],
                city=address_data["city"],
                country=address_data["country"],
                postal_code=address_data["postal_code"],
            ).first()

            if existing:
                return existing

        # Create new address with CORRECT field names
        return Address.objects.create(
            user=user,
            address_type=address_type,
            first_name=address_data["first_name"],
            last_name=address_data["last_name"],
            company=address_data.get("company", ""),
            phone=address_data["phone"],
            email=address_data["email"],
            address_line1=address_data["address_line1"],
            address_line2=address_data.get("address_line2", ""),
            city=address_data["city"],
            state=address_data["state"],
            postal_code=address_data["postal_code"],
            country=address_data["country"],
            instructions=address_data.get("instructions", ""),
            is_default=address_data.get("is_default", False),
        )

    @staticmethod
    def cancel_order(order_id: str, user=None, reason: str = "") -> Order:
        """
        Cancel an order
        Returns: Cancelled order
        """
        try:
            order = Order.objects.prefetch_related("items__variant").get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            # Try by order number
            try:
                order = Order.objects.prefetch_related("items__variant").get(
                    order_number=order_id
                )
            except Order.DoesNotExist:
                raise ValidationError("Order not found")

        # Check permissions
        if user and not user.is_staff:
            if order.user != user:
                raise PermissionDenied("You don't have permission to cancel this order")

        # Check if order can be cancelled
        if not order.can_cancel:
            raise ValidationError("Order cannot be cancelled in its current state")

        with transaction.atomic():
            # Restore stock
            for item in order.items.all():
                if item.variant:
                    item.variant.increase_stock(item.quantity)

            # Update order
            order.status = Order.STATUS_CANCELLED
            if reason:
                order.admin_note = (
                    f"Cancelled by {'user' if user else 'system'}: {reason}"
                )
            order.cancelled_at = timezone.now()
            order.save()

        return order

    @staticmethod
    def update_order_status(
        order_id: str,
        status: str,
        admin_note: str = "",
        carrier: str = "",
    ) -> Order:
        """
        Update order status (admin only)
        """
        try:
            order = Order.objects.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            # Try by order number
            try:
                order = Order.objects.get(order_number=order_id)
            except Order.DoesNotExist:
                raise ValidationError("Order not found")

        # Validate status
        valid_statuses = dict(Order.STATUS_CHOICES).keys()
        if status not in valid_statuses:
            raise ValidationError(f"Invalid status: {status}")

        # Update order
        order.status = status

        if carrier:
            order.carrier = carrier

        if admin_note:
            timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
            if order.admin_note:
                order.admin_note += f"\n{timestamp}: {admin_note}"
            else:
                order.admin_note = f"{timestamp}: {admin_note}"

        order.save()
        return order

    @staticmethod
    def update_payment_status(
        order_id: str,
        payment_status: str,
        payment_intent_id: str = "",
        payment_receipt_url: str = "",
    ) -> Order:
        """
        Update payment status
        """
        try:
            order = Order.objects.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            # Try by order number
            try:
                order = Order.objects.get(order_number=order_id)
            except Order.DoesNotExist:
                raise ValidationError("Order not found")

        # Validate payment status
        valid_statuses = dict(Order.PAYMENT_STATUS_CHOICES).keys()
        if payment_status not in valid_statuses:
            raise ValidationError(f"Invalid payment status: {payment_status}")

        # Update order
        order.payment_status = payment_status

        if payment_intent_id:
            order.payment_intent_id = payment_intent_id

        if payment_receipt_url:
            order.payment_receipt_url = payment_receipt_url

        # Auto-update order status if payment is paid
        if (
            payment_status == Order.PAYMENT_PAID
            and order.status == Order.STATUS_PENDING
        ):
            order.status = Order.STATUS_CONFIRMED
            order.confirmed_at = timezone.now()

        order.save()
        return order

    @staticmethod
    def get_order(order_id: str, user=None, guest_email: str = "") -> Order:
        """
        Get order with permission check
        Accepts UUID or order number
        """
        try:
            # Try by UUID
            try:
                order = Order.objects.prefetch_related("items").get(id=order_id)
            except (ValueError, Order.DoesNotExist):
                # Try by order number
                order = Order.objects.prefetch_related("items").get(
                    order_number=order_id
                )
        except Order.DoesNotExist:
            raise ValidationError("Order not found")

        # Check permissions
        if user and user.is_authenticated:
            if order.user and order.user != user:
                raise PermissionDenied("You don't have permission to view this order")
        elif order.guest_email:
            if not guest_email or guest_email != order.guest_email:
                raise PermissionDenied("Email verification required for guest orders")
        else:
            raise PermissionDenied("Authentication required")

        return order

    @staticmethod
    def get_user_orders(user, filters: Dict = None) -> Tuple[List[Order], int]:
        """
        Get paginated orders for user
        Returns: (orders, total_count)
        """
        filters = filters or {}

        queryset = Order.objects.filter(user=user).prefetch_related("items")

        # Apply filters
        if status := filters.get("status"):
            queryset = queryset.filter(status=status)

        if payment_status := filters.get("payment_status"):
            queryset = queryset.filter(payment_status=payment_status)

        if date_from := filters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to := filters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=date_to)

        # Get total count
        total_count = queryset.count()

        # Apply pagination
        page = int(filters.get("page", 1))
        per_page = int(filters.get("per_page", 10))
        offset = (page - 1) * per_page

        orders = list(queryset.order_by("-created_at")[offset : offset + per_page])

        return orders, total_count

    @staticmethod
    def get_admin_orders(filters: Dict = None) -> Tuple[List[Order], int]:
        """
        Get paginated orders for admin
        Returns: (orders, total_count)
        """
        filters = filters or {}

        queryset = Order.objects.all()

        # Apply filters
        if status := filters.get("status"):
            queryset = queryset.filter(status=status)

        if payment_status := filters.get("payment_status"):
            queryset = queryset.filter(payment_status=payment_status)

        if date_from := filters.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to := filters.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=date_to)

        if search := filters.get("search"):
            queryset = queryset.filter(
                models.Q(order_number__icontains=search)
                | models.Q(guest_email__icontains=search)
                | models.Q(shipping_first_name__icontains=search)
                | models.Q(shipping_last_name__icontains=search)
                | models.Q(user__email__icontains=search)
            )

        # Get total count
        total_count = queryset.count()

        # Apply pagination
        page = int(filters.get("page", 1))
        per_page = int(filters.get("per_page", 20))
        offset = (page - 1) * per_page

        orders = list(queryset.order_by("-created_at")[offset : offset + per_page])

        return orders, total_count

    @staticmethod
    def get_order_statistics() -> Dict:
        """
        Get order statistics
        """
        today = timezone.now().date()
        month_start = today.replace(day=1)

        # Today's stats
        today_orders = Order.objects.filter(created_at__date=today)
        today_revenue = today_orders.aggregate(total=models.Sum("total"))[
            "total"
        ] or Decimal("0.00")

        # This month stats
        month_orders = Order.objects.filter(created_at__date__gte=month_start)
        month_revenue = month_orders.aggregate(total=models.Sum("total"))[
            "total"
        ] or Decimal("0.00")

        # Total stats
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(total=models.Sum("total"))[
            "total"
        ] or Decimal("0.00")

        # Status distribution
        status_distribution = {
            status_name: Order.objects.filter(status=status_code).count()
            for status_code, status_name in Order.STATUS_CHOICES
        }

        # Payment status distribution
        payment_status_distribution = {
            status_name: Order.objects.filter(payment_status=status_code).count()
            for status_code, status_name in Order.PAYMENT_STATUS_CHOICES
        }

        return {
            "today": {"orders": today_orders.count(), "revenue": float(today_revenue)},
            "this_month": {
                "orders": month_orders.count(),
                "revenue": float(month_revenue),
            },
            "total": {"orders": total_orders, "revenue": float(total_revenue)},
            "status_distribution": status_distribution,
            "payment_status_distribution": payment_status_distribution,
        }

    @staticmethod
    def format_order(order: Order) -> Dict:
        """Format order for API response with addresses"""
        return {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "status_display": order.get_status_display(),
            "payment_status": order.payment_status,
            "payment_status_display": order.get_payment_status_display(),
            "payment_method": order.payment_method,
            "payment_method_display": order.get_payment_method_display(),
            "payment_intent_id": order.payment_intent_id,
            "payment_receipt_url": order.payment_receipt_url,
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "guest_phone": order.guest_phone,
            "subtotal": float(order.subtotal),
            "shipping_cost": float(order.shipping_cost),
            "tax_amount": float(order.tax_amount),
            "tax_rate": float(order.tax_rate),
            "discount_amount": float(order.discount_amount),
            "total": float(order.total),
            "currency": order.currency,
            "item_count": order.item_count,
            "shipping_method": order.shipping_method,
            "carrier": order.carrier,
            # Addresses
            "shipping_address": (
                order.shipping_address.to_dict() if order.shipping_address else None
            ),
            "billing_address": (
                order.billing_address.to_dict() if order.billing_address else None
            ),
            "use_separate_billing": order.shipping_address != order.billing_address,
            "items": OrderResponseService._format_order_items(order.items.all()),
            "customer_note": order.customer_note,
            "admin_note": order.admin_note,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "confirmed_at": (
                order.confirmed_at.isoformat() if order.confirmed_at else None
            ),
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
            "delivered_at": (
                order.delivered_at.isoformat() if order.delivered_at else None
            ),
            "cancelled_at": (
                order.cancelled_at.isoformat() if order.cancelled_at else None
            ),
        }

    @staticmethod
    def format_order_summary(order: Order) -> Dict:
        """Format order summary for list responses"""
        # Get and format order items
        items_data = []
        for item in order.items.all():
            # Access variant attributes if needed
            variant_attrs = item.variant_attributes or {}

            items_data.append(
                {
                    "id": str(item.id),
                    "variant_id": str(item.variant.id) if item.variant else None,
                    "product_title": item.product_title,
                    "product_slug": item.product_slug,
                    "sku": item.sku,
                    "variant_attributes": variant_attrs,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "discount_amount": float(item.discount_amount),
                    "total_price": float(item.total_price),
                    "discounted_unit_price": float(item.discounted_unit_price),
                    # If you need product image from variant
                    "image": (
                        item.variant.images.first().image.url
                        if (
                            item.variant
                            and hasattr(item.variant, "images")
                            and item.variant.images.exists()
                        )
                        else ""
                    ),
                }
            )

        return {
            "id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "status_display": order.get_status_display(),
            "payment_status": order.payment_status,
            "payment_status_display": order.get_payment_status_display(),
            "payment_method": order.payment_method,
            "payment_method_display": order.get_payment_method_display(),
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "guest_info": (
                {
                    "email": order.guest_email,
                    "first_name": order.guest_first_name,
                    "last_name": order.guest_last_name,
                    "phone": order.guest_phone,
                }
                if order.guest_email
                else None
            ),
            "subtotal": float(order.subtotal),
            "shipping_cost": float(order.shipping_cost),
            "tax_amount": float(order.tax_amount),
            "tax_rate": float(order.tax_rate),
            "discount_amount": float(order.discount_amount),
            "total": float(order.total),
            "currency": order.currency,
            "item_count": order.item_count,
            "items": items_data,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "shipping_method": order.shipping_method,
            "carrier": order.carrier,
            "customer_note": order.customer_note,
            "shipping_address": (
                {
                    "id": (
                        str(order.shipping_address.id)
                        if order.shipping_address
                        else None
                    ),
                    "city": (
                        order.shipping_address.city if order.shipping_address else ""
                    ),
                    "country": (
                        order.shipping_address.country if order.shipping_address else ""
                    ),
                    "address_line1": (
                        order.shipping_address.address_line1
                        if order.shipping_address
                        else ""
                    ),
                    "address_line2": (
                        order.shipping_address.address_line2
                        if order.shipping_address
                        else ""
                    ),
                    "postal_code": (
                        order.shipping_address.postal_code
                        if order.shipping_address
                        else ""
                    ),
                    "phone": (
                        order.shipping_address.phone if order.shipping_address else ""
                    ),
                }
                if order.shipping_address
                else None
            ),
            # "billing_address": (
            #     {
            #         "id": (
            #             str(order.billing_address.id) if order.billing_address else None
            #         ),
            #         "city": order.billing_address.city if order.billing_address else "",
            #         "country": (
            #             order.billing_address.country if order.billing_address else ""
            #         ),
            #         "address_line1": (
            #             order.billing_address.address_line1
            #             if order.billing_address
            #             else ""
            #         ),
            #         "address_line2": (
            #             order.billing_address.address_line2
            #             if order.shipping_address
            #             else ""
            #         ),
            #         "postal_code": (
            #             order.billing_address.postal_code
            #             if order.billing_address
            #             else ""
            #         ),
            #         "phone": (
            #             order.billing_address.phone if order.billing_address else ""
            #         ),
            #     }
            #     if order.billing_address
            #     else None
            # ),
            "timestamps": {
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                "confirmed_at": (
                    order.confirmed_at.isoformat() if order.confirmed_at else None
                ),
                "shipped_at": (
                    order.shipped_at.isoformat() if order.shipped_at else None
                ),
                "delivered_at": (
                    order.delivered_at.isoformat() if order.delivered_at else None
                ),
                "cancelled_at": (
                    order.cancelled_at.isoformat() if order.cancelled_at else None
                ),
            },
        }


class OrderResponseService:
    """
    Updated response service with address support
    """

    @staticmethod
    def _format_order_items(items) -> List[Dict]:
        """Format order items for response"""
        return [
            {
                "id": str(item.id),
                "product_title": item.product_title,
                "product_slug": item.product_slug,
                "sku": item.sku,
                "variant_attributes": item.variant_attributes,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "discount_amount": float(item.discount_amount),
                "total_price": float(item.total_price),
                "discounted_unit_price": float(item.discounted_unit_price),
                "image": (
                    item.variant.images.first().image.url
                    if (
                        item.variant
                        and hasattr(item.variant, "images")
                        and item.variant.images.exists()
                    )
                    else ""
                ),
            }
            for item in items
        ]
