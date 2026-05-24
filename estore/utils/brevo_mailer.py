# estore/utils/brevo_mailer.py

import logging
import requests
from django.conf import settings
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BrevoMailer:
    """Brevo (Sendinblue) email service integration"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'BREVO_API_KEY', '')
        self.api_url = 'https://api.brevo.com/v3'
        self.sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com')
        self.sender_name = getattr(settings, 'DEFAULT_FROM_NAME', 'E-Commerce Store')
        
    def send_email(
        self,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        recipient_name: str = None,
        reply_to: str = None,
        cc: list = None,
        bcc: list = None,
        attachments: list = None,
    ) -> bool:
        """Send email using Brevo API"""
        
        if not self.api_key:
            logger.error("Brevo API key not configured")
            return False
        
        headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        # Prepare recipient
        to = [{'email': recipient_email}]
        if recipient_name:
            to[0]['name'] = recipient_name
        
        # Prepare email payload
        payload = {
            'sender': {
                'email': self.sender_email,
                'name': self.sender_name,
            },
            'to': to,
            'subject': subject,
            'htmlContent': html_content,
        }
        
        if text_content:
            payload['textContent'] = text_content
        
        if reply_to:
            payload['replyTo'] = {'email': reply_to}
        
        if cc:
            payload['cc'] = [{'email': email} for email in cc]
        
        if bcc:
            payload['bcc'] = [{'email': email} for email in bcc]
        
        if attachments:
            payload['attachment'] = attachments
        
        try:
            response = requests.post(
                f'{self.api_url}/smtp/email',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 201:
                logger.info(f"Email sent to {recipient_email} via Brevo")
                return True
            else:
                logger.error(f"Brevo email failed: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Brevo API request error: {str(e)}")
            return False
    
    def send_template_email(
        self,
        recipient_email: str,
        template_id: int,
        params: Dict[str, Any],
        recipient_name: str = None,
    ) -> bool:
        """Send email using a Brevo template"""
        
        if not self.api_key:
            logger.error("Brevo API key not configured")
            return False
        
        headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        
        to = [{'email': recipient_email}]
        if recipient_name:
            to[0]['name'] = recipient_name
        
        payload = {
            'to': to,
            'templateId': template_id,
            'params': params,
        }
        
        try:
            response = requests.post(
                f'{self.api_url}/smtp/templates/{template_id}/send',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 201:
                logger.info(f"Template email sent to {recipient_email} via Brevo")
                return True
            else:
                logger.error(f"Brevo template email failed: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Brevo API request error: {str(e)}")
            return False


# Helper function for backward compatibility
def send_email(
    recipient_email: str,
    subject: str,
    message_text: str,
    html_message: str = None,
    recipient_name: str = None,
) -> bool:
    """Send email using Brevo"""
    mailer = BrevoMailer()
    return mailer.send_email(
        recipient_email=recipient_email,
        subject=subject,
        html_content=html_message or message_text,
        text_content=message_text,
        recipient_name=recipient_name,
    )