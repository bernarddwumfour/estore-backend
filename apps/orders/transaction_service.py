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
            from apps.promotions.services import DiscountCodeService

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
                from apps.orders.order_service import OrderService

                was_failed = order.payment_status == Order.PAYMENT_FAILED
                order.payment_status = Order.PAYMENT_PAID
                OrderService._on_payment_captured(order, was_failed)
                order.save()
                DiscountCodeService.sync_order_commission(
                    order,
                    reason="Charge recorded",
                )
            
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
        """Record a refund transaction.

        For orders paid online via Paystack, this issues a real refund through
        the gateway first and only records the refund row if the gateway
        accepts it. Manual refunds (POS / pay-on-delivery / cash) that have no
        gateway charge are recorded directly.
        """
        try:
            from apps.promotions.services import DiscountCodeService

            order = get_order_by_id(order_id)
            if not order:
                return None, {"order": "Order not found"}

            if amount <= 0:
                return None, {"amount": "Refund amount must be greater than 0"}

            # Check refundable amount
            refundable = get_refundable_amount(order_id)
            if amount > refundable:
                return None, {"amount": f"Cannot refund more than refundable amount (${refundable})"}

            # Locate the originating successful charge for gateway refund + linkage.
            charge = Transaction.objects.filter(
                order=order,
                transaction_type=Transaction.TRANSACTION_TYPE_CHARGE,
                status=Transaction.TRANSACTION_STATUS_SUCCESS,
            ).order_by('-created_at').first()

            # Resolve the parent transaction (explicit id wins, else the charge).
            parent = None
            if parent_transaction_id:
                parent = Transaction.objects.filter(transaction_id=parent_transaction_id).first()
            if parent is None:
                parent = charge

            gateway_metadata = {}
            # If the order was paid online via Paystack, issue the refund at the
            # gateway BEFORE recording it locally. Bail out if the gateway rejects.
            if charge and charge.payment_method == 'paystack' and charge.transaction_id:
                from apps.orders.paystack_service import PaystackService

                amount_minor = int((amount * 100).to_integral_value())
                success, gw_result = PaystackService.refund_transaction(
                    charge.transaction_id, amount_minor
                )
                if not success:
                    logger.error(
                        f"Gateway refund failed for order {order.order_number}: {gw_result}"
                    )
                    return None, {"gateway": f"Payment gateway refund failed: {gw_result}"}
                gateway_metadata = gw_result if isinstance(gw_result, dict) else {"result": gw_result}

            refund_transaction = Transaction.objects.create(
                order=order,
                transaction_type=Transaction.TRANSACTION_TYPE_REFUND,
                transaction_id=f"REF-{order.order_number}-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                reference=charge.transaction_id if charge else "",
                amount=amount,
                currency=order.currency,
                status=Transaction.TRANSACTION_STATUS_SUCCESS,
                payment_method=charge.payment_method if charge else "",
                parent_transaction=parent,
                refund_reason=refund_reason,
                notes=notes,
                metadata=gateway_metadata,
                completed_at=timezone.now(),
            )

            # Update order payment status based on the remaining refundable amount.
            new_refundable = refundable - amount
            if new_refundable <= 0:
                order.payment_status = Order.PAYMENT_REFUNDED
                order.status = Order.STATUS_REFUNDED
            else:
                order.payment_status = Order.PAYMENT_PARTIALLY_REFUNDED
            order.save()
            DiscountCodeService.sync_order_commission(
                order,
                reason="Refund recorded",
            )

            logger.info(f"Refund of {amount} recorded for order {order.order_number}")
            return refund_transaction, None

        except Exception as e:
            logger.error(f"Record refund error: {str(e)}")
            return None, {"general": str(e)}
