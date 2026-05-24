# apps/orders/services/transaction_service.py
import logging
from typing import Dict,  Optional, Tuple
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, Transaction
from apps.orders.selectors import get_order_by_id, get_refundable_amount

logger = logging.getLogger(__name__)


class TransactionService:
    """Transaction business logic"""
    
    @staticmethod
    @transaction.atomic
    def record_charge(
        order_id: str,
        transaction_id: str,
        amount: Decimal,
        reference: str = "",
        payment_method: str = "",
        card_last4: str = "",
        card_brand: str = "",
        receipt_url: str = "",
        metadata: Dict = None,
    ) -> Tuple[Optional[Transaction], Optional[Dict]]:
        """Record a successful charge transaction"""
        try:
            order = get_order_by_id(order_id)
            if not order:
                return None, {"order": "Order not found"}
            
            transaction_obj = Transaction.objects.create(
                order=order,
                transaction_type=Transaction.TRANSACTION_TYPE_CHARGE,
                transaction_id=transaction_id,
                reference=reference,
                amount=amount,
                currency=order.currency,
                status=Transaction.TRANSACTION_STATUS_SUCCESS,
                payment_method=payment_method,
                card_last4=card_last4,
                card_brand=card_brand,
                metadata=metadata or {},
                receipt_url=receipt_url,
                completed_at=timezone.now(),
            )
            
            # Update order payment status
            if order.payment_status != Order.PAYMENT_PAID:
                order.payment_status = Order.PAYMENT_PAID
                order.paid_at = timezone.now()
                order.save()
            
            logger.info(f"Charge recorded for order {order.order_number}: {amount}")
            return transaction_obj, None
            
        except Exception as e:
            logger.error(f"Record charge error: {str(e)}")
            return None, {"general": str(e)}
    
    @staticmethod
    @transaction.atomic
    def record_refund(
        order_id: str,
        amount: Decimal,
        refund_reason: str = "",
        parent_transaction_id: str = None,
        notes: str = "",
    ) -> Tuple[Optional[Transaction], Optional[Dict]]:
        """Record a refund transaction"""
        try:
            order = get_order_by_id(order_id)
            if not order:
                return None, {"order": "Order not found"}
            
            # Check refundable amount
            refundable = get_refundable_amount(order_id)
            if amount > refundable:
                return None, {"amount": f"Cannot refund more than refundable amount (${refundable})"}
            
            # Find parent transaction if provided
            parent = None
            if parent_transaction_id:
                try:
                    parent = Transaction.objects.get(transaction_id=parent_transaction_id)
                except Transaction.DoesNotExist:
                    pass
            
            refund_transaction = Transaction.objects.create(
                order=order,
                transaction_type=Transaction.TRANSACTION_TYPE_REFUND,
                transaction_id=f"REF-{order.order_number}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                amount=amount,
                currency=order.currency,
                status=Transaction.TRANSACTION_STATUS_SUCCESS,
                parent_transaction=parent,
                refund_reason=refund_reason,
                notes=notes,
                completed_at=timezone.now(),
            )
            
            # Update order payment status
            new_refundable = refundable - amount
            if new_refundable == 0:
                order.payment_status = Order.PAYMENT_REFUNDED
                order.status = Order.STATUS_REFUNDED
            else:
                order.payment_status = Order.PAYMENT_PARTIALLY_REFUNDED
            order.save()
            
            logger.info(f"Refund of {amount} recorded for order {order.order_number}")
            return refund_transaction, None
            
        except Exception as e:
            logger.error(f"Record refund error: {str(e)}")
            return None, {"general": str(e)}