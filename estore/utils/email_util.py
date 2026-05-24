# estore/utils/email_util.py

import logging
from .brevo_mailer import  send_email as brevo_send_email

logger = logging.getLogger(__name__)


def send_email(
    recipient_email: str,
    subject: str,
    message_text: str,
    html_message: str = None,
    recipient_name: str = None,
) -> bool:
    """
    Send email using Brevo (Sendinblue)
    Falls back to console if API key not configured
    """
    from django.conf import settings
    
    # Try to send via Brevo
    if getattr(settings, 'BREVO_API_KEY', None):
        return brevo_send_email(
            recipient_email=recipient_email,
            subject=subject,
            message_text=message_text,
            html_message=html_message,
            recipient_name=recipient_name,
        )
    
    # Fallback to console output for development
    logger.info(f"Email would be sent to {recipient_email}")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body: {message_text}")
    return True