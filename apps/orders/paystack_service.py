# apps/orders/services/paystack_service.py
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional, Tuple
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class PaystackService:
    """Paystack payment gateway integration"""
    
    BASE_URL = settings.PAYSTACK_BASE_URL
    SECRET_KEY = settings.PAYSTACK_SECRET_KEY
    PUBLIC_KEY = settings.PAYSTACK_PUBLIC_KEY
    
    @classmethod
    def initialize_transaction(cls, order) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Initialize a Paystack transaction
        
        Returns:
            Tuple of (response_data, error_message)
        """
        try:
            # Calculate amount in kobo (smallest currency unit)
            # Paystack uses kobo for NGN, or the smallest unit for other currencies
            amount = int(order.total * 100)  # Convert to cents/pesewas/kobo
            
            # Get customer email
            email = order.customer_email
            
            # Prepare metadata
            metadata = {
                'order_id': str(order.id),
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'custom_fields': [
                    {
                        'display_name': 'Order Number',
                        'variable_name': 'order_number',
                        'value': order.order_number
                    },
                    {
                        'display_name': 'Customer Name',
                        'variable_name': 'customer_name',
                        'value': order.customer_name
                    }
                ]
            }
            
            # Prepare request data
            payload = {
                'amount': amount,
                'email': email,
                'currency': "GHS",
                'reference': cls.generate_reference(order),
                'metadata': metadata,
                'callback_url': settings.PAYMENT_SUCCESS_URL,
                'cancel_url': settings.PAYMENT_CANCEL_URL,
            }
            
            # Add order items to metadata if needed
            items = []
            for item in order.items.all():
                items.append({
                    'name': item.product_title[:30],
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                })
            payload['metadata']['items'] = items
            
            # Make request to Paystack
            headers = {
                'Authorization': f'Bearer {cls.SECRET_KEY}',
                'Content-Type': 'application/json',
            }
            
            response = requests.post(
                f'{cls.BASE_URL}/transaction/initialize',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    # Cache the reference for verification
                    cache.set(
                        f'paystack_ref_{payload["reference"]}',
                        str(order.id),
                        timeout=3600  # 1 hour
                    )
                    # Persist the reference so the payment can be reconciled
                    # with Paystack later even if the redirect/webhook is missed
                    # (the cache is in-memory and expires).
                    order.payment_intent_id = payload['reference']
                    order.save(update_fields=['payment_intent_id', 'updated_at'])
                    return {
                        'authorization_url': data['data']['authorization_url'],
                        'access_code': data['data']['access_code'],
                        'reference': payload['reference'],
                    }, None
                else:
                    logger.error(f"Paystack initialization failed: {data.get('message')}")
                    return None, data.get('message', 'Payment initialization failed')
            else:
                logger.error(f"Paystack API error: {response.status_code} - {response.text}")
                return None, f"Payment service error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Paystack initialization error: {str(e)}")
            return None, str(e)
    
    @staticmethod
    def generate_reference(order) -> str:
        """Generate unique transaction reference"""
        import secrets
        import time
        
        timestamp = str(int(time.time() * 1000))
        random_str = secrets.token_hex(8)
        return f"ORD-{order.order_number}-{timestamp}-{random_str}"[:50]
    
    @classmethod
    def verify_transaction(cls, reference: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Verify a Paystack transaction
        
        Returns:
            Tuple of (transaction_data, error_message)
        """
        try:
            headers = {
                'Authorization': f'Bearer {cls.SECRET_KEY}',
                'Content-Type': 'application/json',
            }
            
            response = requests.get(
                f'{cls.BASE_URL}/transaction/verify/{reference}',
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    return data['data'], None
                else:
                    logger.error(f"Paystack verification failed: {data.get('message')}")
                    return None, data.get('message', 'Verification failed')
            else:
                logger.error(f"Paystack verification API error: {response.status_code}")
                return None, f"Verification error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Paystack verification error: {str(e)}")
            return None, str(e)
    
    @classmethod
    def handle_webhook(cls, payload: bytes, signature: str) -> Optional[Dict]:
        """
        Handle Paystack webhook events
        
        Args:
            payload: Raw request body
            signature: Paystack signature header
            
        Returns:
            Parsed event data or None if invalid
        """
        # Verify webhook signature
        expected_signature = hmac.new(
            settings.PAYSTACK_WEBHOOK_SECRET.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid webhook signature")
            return None
        
        try:
            event_data = json.loads(payload)
            return event_data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid webhook payload: {str(e)}")
            return None

    @classmethod
    def get_transaction_status(cls, reference: str) -> Optional[str]:
        """
        Get transaction status from Paystack
        
        Returns:
            Status string or None
        """
        transaction_data, error = cls.verify_transaction(reference)
        if error or not transaction_data:
            return None
        return transaction_data.get('status')
    
    @classmethod
    def refund_transaction(cls, reference: str, amount: int = None) -> Tuple[bool, Any]:
        """
        Refund a Paystack transaction

        Args:
            reference: Transaction reference
            amount: Amount to refund in kobo/pesewas (if None, full refund)

        Returns:
            Tuple of (success, data_or_error). On success the second element is
            the Paystack refund payload (dict); on failure it is an error string.
        """
        try:
            payload = {
                'transaction': reference,
            }
            if amount:
                payload['amount'] = amount

            headers = {
                'Authorization': f'Bearer {cls.SECRET_KEY}',
                'Content-Type': 'application/json',
            }

            response = requests.post(
                f'{cls.BASE_URL}/refund',
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('status'):
                    return True, data.get('data', {})
                else:
                    return False, data.get('message', 'Refund failed')
            else:
                logger.error(f"Paystack refund API error: {response.status_code} - {response.text}")
                return False, f"Refund API error: {response.status_code}"

        except Exception as e:
            logger.error(f"Paystack refund error: {str(e)}")
            return False, str(e)
        
        
    # apps/orders/services/paystack_service.py - Update process_successful_payment

    @classmethod
    def process_successful_payment(cls, reference: str, order_id: str = None) -> Tuple[bool, Optional[Dict]]:
        """
        Process a successful payment after verification
        """
        from apps.orders.models import Order, Transaction
        from apps.orders.order_service import OrderService
        from decimal import Decimal
        
        # Verify transaction
        transaction_data, error = cls.verify_transaction(reference)
        if error or not transaction_data:
            return False, {'error': error or 'Verification failed'}

        # Resolve the order id first (needed for both success and failure paths).
        actual_order_id = order_id

        if not actual_order_id:
            from django.core.cache import cache
            actual_order_id = cache.get(f'paystack_ref_{reference}')

        if not actual_order_id:
            # Try to find from metadata
            metadata = transaction_data.get('metadata', {})
            actual_order_id = metadata.get('order_id')

        # Check if transaction was successful
        gateway_status = transaction_data.get('status')
        if gateway_status != 'success':
            # For terminal failures, release the order's reserved stock and mark
            # it failed so it isn't stranded in 'pending'. Transient/unknown
            # statuses are left for retry without altering the order.
            if actual_order_id and gateway_status in ('failed', 'abandoned', 'reversed'):
                OrderService.mark_payment_failed(
                    actual_order_id, reason=f"Paystack status: {gateway_status}"
                )
            return False, {'error': f'Payment not successful: {gateway_status}'}

        if not actual_order_id:
            return False, {'error': 'Order not found'}

        try:
            order = Order.objects.get(id=actual_order_id)
        except Order.DoesNotExist:
            return False, {'error': 'Order not found'}
        
        # Check if transaction already exists
        existing_transaction = Transaction.objects.filter(transaction_id=reference).first()
        if existing_transaction:
            # Transaction already recorded
            return True, {'order': order, 'transaction': transaction_data, 'existing': True}

        # Verify the captured amount and currency match what the order expects
        # before recording the charge or marking the order paid. The amount was
        # set server-side at initialization; this guards against any tampered or
        # partial capture being accepted as full payment.
        expected_amount_minor = int((order.total * 100).to_integral_value())
        paid_amount_minor = int(transaction_data.get('amount', 0) or 0)
        paid_currency = (transaction_data.get('currency') or '').upper()
        expected_currency = (order.currency or '').upper()

        if paid_amount_minor != expected_amount_minor or (
            paid_currency and expected_currency and paid_currency != expected_currency
        ):
            logger.error(
                "Payment amount/currency mismatch for order %s: expected %s %s, "
                "got %s %s (ref=%s)",
                order.order_number, expected_amount_minor, expected_currency,
                paid_amount_minor, paid_currency, reference,
            )
            return False, {
                'error': 'Payment amount or currency does not match the order. '
                         'Please contact support.'
            }

        # CREATE TRANSACTION RECORD
        from django.utils import timezone
        
        # Get payment method details
        payment_method = 'paystack'
        card_last4 = transaction_data.get('authorization', {}).get('last4', '')
        card_brand = transaction_data.get('authorization', {}).get('card_type', '')
        
        transaction_record = Transaction.objects.create(
            order=order,
            transaction_type=Transaction.TRANSACTION_TYPE_CHARGE,
            transaction_id=reference,
            reference=reference,
            amount=Decimal(str(transaction_data.get('amount', 0))) / 100,  # Convert from kobo/pesewas
            currency=transaction_data.get('currency', order.currency),
            status=Transaction.TRANSACTION_STATUS_SUCCESS,
            payment_method=payment_method,
            card_last4=card_last4,
            card_brand=card_brand,
            metadata=transaction_data,
            receipt_url=transaction_data.get('receipt_url', ''),
            completed_at=timezone.now(),
            notes=f"Payment via Paystack. Reference: {reference}",
        )
        
        # Update order payment status only if not already paid
        if order.payment_status != Order.PAYMENT_PAID:
            order, error = OrderService.update_payment_status(
                order_id=str(order.id),
                payment_status='paid',
                payment_intent_id=reference,
                payment_receipt_url=transaction_data.get('receipt_url', ''),
            )

            if error:
                return False, error

            # Confirmation email — inside the not-already-paid guard so it fires
            # once even though webhook and verify endpoint both converge here.
            from apps.orders.order_emails import send_order_confirmation_email
            send_order_confirmation_email(order, transaction_record)

        return True, {
            'order': order,
            'transaction': transaction_data,
            'transaction_record': transaction_record
        }