# estore/utils/email_util.py
"""
Legacy wrappers kept for import stability — all logic lives in the base
EmailService (estore/utils/email_service.py). New code should use
`from estore.utils.email_service import email_service` directly.
"""

from estore.utils.email_service import email_service


def send_email(
    recipient_email: str,
    subject: str,
    message_text: str,
    html_message: str = None,
    recipient_name: str = None,
) -> bool:
    return email_service.send(
        recipient_email=recipient_email,
        subject=subject,
        message_text=message_text,
        html_message=html_message,
        recipient_name=recipient_name,
    )


def send_templated_email(
    recipient_email: str,
    subject: str,
    template: str,
    context: dict = None,
    recipient_name: str = None,
    async_send: bool = True,
) -> bool:
    return email_service.send_templated(
        recipient_email=recipient_email,
        subject=subject,
        template=template,
        context=context,
        recipient_name=recipient_name,
        async_send=async_send,
    )
