"""
Transaction Schemas - Serialization and validation for transactions
"""

from typing import Dict, Any, Tuple, Optional, List
from decimal import Decimal


def serialize_transaction(transaction, is_admin: bool = False) -> Dict:
    """Serialize transaction for API response"""
    data = {
        "id": str(transaction.id),
        "transaction_type": transaction.transaction_type,
        "transaction_type_display": transaction.get_transaction_type_display(),
        "transaction_id": transaction.transaction_id,
        "reference": transaction.reference,
        "amount": float(transaction.amount),
        "currency": transaction.currency,
        "status": transaction.status,
        "status_display": transaction.get_status_display(),
        "payment_method": transaction.payment_method,
        "created_at": transaction.created_at.isoformat(),
        "completed_at": transaction.completed_at.isoformat() if transaction.completed_at else None,
    }
    
    if is_admin:
        data.update({
            "card_last4": transaction.card_last4,
            "card_brand": transaction.card_brand,
            "metadata": transaction.metadata,
            "notes": transaction.notes,
            "receipt_url": transaction.receipt_url,
            "refund_reason": transaction.refund_reason,
            "parent_transaction_id": str(transaction.parent_transaction_id) if transaction.parent_transaction_id else None,
        })
    
    return data


def serialize_transaction_list(transactions: List, is_admin: bool = False) -> List[Dict]:
    """Serialize list of transactions for list view"""
    return [serialize_transaction(t, is_admin=is_admin) for t in transactions]


def validate_payment_initiation(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate payment initiation request"""
    errors = {}
    cleaned = {}
    
    # No additional validation needed for now
    # Can add payment method override in the future
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_refund_request(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate refund request"""
    errors = {}
    cleaned = {}
    
    amount = data.get('amount')
    if not amount:
        errors['amount'] = "Amount is required"
    else:
        try:
            cleaned['amount'] = Decimal(str(amount))
            if cleaned['amount'] <= 0:
                errors['amount'] = "Amount must be greater than 0"
        except:
            errors['amount'] = "Invalid amount"
    
    if 'refund_reason' in data:
        cleaned['refund_reason'] = data['refund_reason']
    
    if 'admin_note' in data:
        cleaned['admin_note'] = data['admin_note']
    
    if errors:
        return None, errors
    
    return cleaned, None