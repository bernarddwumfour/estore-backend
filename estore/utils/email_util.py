"""
estore/utils/email_util.py

Simple SMTP email utility for API
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def send_email(
    recipient_email: str, subject: str, message_text: str, html_message: str = None
) -> bool:
    """
    Simple function to send an email message using SMTP.

    Args:
        recipient_email: Email address of the recipient
        subject: Email subject
        message_text: Plain text email content
        html_message: HTML email content (optional)

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get SMTP configuration
        SMTP_SERVER = getattr(
            settings, "SMTP_SERVER", os.getenv("SMTP_SERVER", "smtp.gmail.com")
        )
        SMTP_PORT = getattr(settings, "SMTP_PORT", int(os.getenv("SMTP_PORT", "587")))
        SMTP_USERNAME = getattr(
            settings, "SMTP_USERNAME", os.getenv("SMTP_USERNAME", "")
        )
        SMTP_PASSWORD = getattr(
            settings, "SMTP_PASSWORD", os.getenv("SMTP_PASSWORD", "")
        )
        SENDER_EMAIL = getattr(
            settings, "DEFAULT_FROM_EMAIL", os.getenv("SENDER_EMAIL", SMTP_USERNAME)
        )
        SENDER_NAME = getattr(
            settings, "SITE_NAME", os.getenv("SENDER_NAME", "ShopHub")
        )

        # Create email message
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject

        # Attach plain text version
        msg.attach(MIMEText(message_text, "plain"))

        # Attach HTML version if provided
        if html_message:
            msg.attach(MIMEText(html_message, "html"))

        # Send email via SMTP
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
        return False
