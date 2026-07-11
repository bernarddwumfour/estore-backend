# estore/utils/resend_mailer.py

import logging

import resend
from django.conf import settings

logger = logging.getLogger(__name__)


class ResendMailer:
    """Resend email service integration"""

    def __init__(self):
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        self.sender_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '')
        self.sender_name = getattr(settings, 'DEFAULT_FROM_NAME', 'E-Commerce Store')

    def send_email(
        self,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        reply_to: str = None,
        cc: list = None,
        bcc: list = None,
    ) -> bool:
        """Send email using the Resend API. Returns True on success."""

        if not self.api_key:
            logger.error("Resend API key not configured")
            return False

        if not self.sender_email:
            logger.error("SENDER_EMAIL not configured; Resend requires a verified sender")
            return False

        resend.api_key = self.api_key

        params = {
            'from': f'{self.sender_name} <{self.sender_email}>',
            'to': [recipient_email],
            'subject': subject,
            'html': html_content,
        }

        if text_content:
            params['text'] = text_content

        if reply_to:
            params['reply_to'] = reply_to

        if cc:
            params['cc'] = cc

        if bcc:
            params['bcc'] = bcc

        try:
            response = resend.Emails.send(params)
            logger.info(
                f"Email sent to {recipient_email} via Resend (id: {response.get('id', 'unknown')})"
            )
            return True
        except Exception as e:
            # Log server-side only; never propagate provider errors to callers
            logger.error(f"Resend send failed for {recipient_email}: {str(e)}")
            return False

    def send_batch(self, emails: list) -> tuple:
        """
        Send up to 100 emails in one Resend batch call.

        emails: [{"to", "subject", "html", "text"(optional)}, ...]
        Returns (ok, error_message). Never raises.
        """
        if not self.api_key:
            logger.error("Resend API key not configured")
            return False, "API key not configured"

        if not self.sender_email:
            logger.error("SENDER_EMAIL not configured; Resend requires a verified sender")
            return False, "Sender email not configured"

        resend.api_key = self.api_key
        sender = f"{self.sender_name} <{self.sender_email}>"

        params = []
        for email in emails:
            item = {
                "from": sender,
                "to": [email["to"]],
                "subject": email["subject"],
                "html": email["html"],
            }
            if email.get("text"):
                item["text"] = email["text"]
            params.append(item)

        try:
            resend.Batch.send(params)
            logger.info(f"Batch of {len(params)} emails sent via Resend")
            return True, None
        except Exception as e:
            logger.error(f"Resend batch send failed ({len(params)} emails): {str(e)}")
            return False, str(e)
