# estore/utils/email_service.py
"""
Single entry point for ALL outgoing email (auth, orders, campaigns).

Every sender in the codebase goes through `email_service` (or the legacy
wrappers in email_util.py, which delegate here). Invariants:
- console-log fallback when RESEND_API_KEY is unset (dev/test);
- never raises across the caller boundary; returns bool / counts;
- provider errors are logged server-side only.
"""

import logging
import threading
import time

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

# Registry of known email types: name -> {"template": ..., "default_subject": ...}
# Lets new email kinds be declared in one reviewable place.
EMAIL_TYPES = {}


def register_email_type(name: str, template: str, default_subject: str = None):
    EMAIL_TYPES[name] = {"template": template, "default_subject": default_subject}


class EmailService:
    """Base email service wrapping the Resend provider."""

    BATCH_SIZE = 100          # Resend batch API limit
    BATCH_PAUSE_SECONDS = 0.6  # stay under the ~2 req/s rate limit

    def _provider_configured(self) -> bool:
        return bool(getattr(settings, "RESEND_API_KEY", None))

    def send(
        self,
        recipient_email: str,
        subject: str,
        message_text: str,
        html_message: str = None,
        recipient_name: str = None,
    ) -> bool:
        """Send a single email. Falls back to console logging in dev."""
        if self._provider_configured():
            from .resend_mailer import ResendMailer

            return ResendMailer().send_email(
                recipient_email=recipient_email,
                subject=subject,
                html_content=html_message or message_text,
                text_content=message_text,
            )

        logger.info(f"Email would be sent to {recipient_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body: {message_text}")
        return True

    def send_templated(
        self,
        recipient_email: str,
        subject: str,
        template: str,
        context: dict = None,
        recipient_name: str = None,
        async_send: bool = True,
    ) -> bool:
        """
        Render templates/emails/<template> and send it.

        With async_send=True (default) the send happens on a daemon thread so a
        slow or failing provider never blocks or breaks the request; the return
        value only reflects that the send was dispatched. Pass async_send=False
        when the caller needs the actual send result (e.g. email verification).
        """
        site_name = getattr(settings, "SITE_NAME", "E-Commerce Store")
        support_email = ""
        try:
            from apps.common.models import GeneralConfig
            config = GeneralConfig.get_cached()
            site_name = config.store_name or site_name
            support_email = config.support_email
        except Exception:
            pass  # config must never block an email
        base_context = {
            "site_name": site_name,
            "support_email": support_email,
            "recipient_name": recipient_name,
        }
        if context:
            base_context.update(context)

        html_message = render_to_string(f"emails/{template}", base_context)
        message_text = strip_tags(html_message)

        if not async_send:
            return self.send(
                recipient_email=recipient_email,
                subject=subject,
                message_text=message_text,
                html_message=html_message,
                recipient_name=recipient_name,
            )

        def _send():
            try:
                self.send(
                    recipient_email=recipient_email,
                    subject=subject,
                    message_text=message_text,
                    html_message=html_message,
                    recipient_name=recipient_name,
                )
            except Exception as e:
                logger.error(
                    f"Background email send failed for {recipient_email}: {str(e)}"
                )

        threading.Thread(target=_send, daemon=True).start()
        return True

    def send_type(
        self,
        email_type: str,
        recipient_email: str,
        context: dict = None,
        subject: str = None,
        recipient_name: str = None,
        async_send: bool = True,
    ) -> bool:
        """Send a registered email type by name."""
        spec = EMAIL_TYPES.get(email_type)
        if not spec:
            logger.error(f"Unknown email type: {email_type}")
            return False
        return self.send_templated(
            recipient_email=recipient_email,
            subject=subject or spec.get("default_subject") or email_type,
            template=spec["template"],
            context=context,
            recipient_name=recipient_name,
            async_send=async_send,
        )

    def send_batch(self, messages: list) -> tuple:
        """
        Bulk send. messages: [{"to", "subject", "html", "text"(optional)}, ...].

        Chunks into Resend batch calls of up to BATCH_SIZE, pausing between
        chunks to respect the provider rate limit. Returns
        (sent_count, failed_count, error_sample) where error_sample is a list
        of {"email", "error"} dicts (capped by the caller as needed).

        Console fallback (no API key): logs each message and counts it as sent.
        """
        sent_count = 0
        failed_count = 0
        error_sample = []

        if not messages:
            return 0, 0, []

        if not self._provider_configured():
            for message in messages:
                logger.info(
                    f"[batch] Email would be sent to {message.get('to')} "
                    f"— {message.get('subject')}"
                )
            return len(messages), 0, []

        from .resend_mailer import ResendMailer

        mailer = ResendMailer()
        for start in range(0, len(messages), self.BATCH_SIZE):
            chunk = messages[start:start + self.BATCH_SIZE]
            ok, error = mailer.send_batch(chunk)
            if ok:
                sent_count += len(chunk)
            else:
                failed_count += len(chunk)
                for message in chunk[: max(0, 20 - len(error_sample))]:
                    error_sample.append(
                        {"email": message.get("to"), "error": error or "send failed"}
                    )
            if start + self.BATCH_SIZE < len(messages):
                time.sleep(self.BATCH_PAUSE_SECONDS)

        return sent_count, failed_count, error_sample


email_service = EmailService()
