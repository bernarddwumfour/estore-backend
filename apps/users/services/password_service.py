"""
users/services/password_service.py

Password reset service using unified VerificationToken model
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

from ..models.user import User
from ..models.verification_token import VerificationToken
from ..utils.token_utils import generate_verification_token
from estore.utils.email_util import send_templated_email
from urllib.parse import urlencode


logger = logging.getLogger(__name__)


class PasswordService:

    @staticmethod
    def request_reset(email, request):
        """
        Request password reset for email
        Returns: (success, message)
        """
        try:
            # Find active user by email
            user = User.objects.filter(email=email, is_active=True).first()
            user_email = user.email

            if not user:
                # Security: Don't reveal if email exists
                return (
                    True,
                    "If your email exists, you will receive a reset link shortly",
                )

            # Rate limiting: Check recent password reset attempts
            five_minutes_ago = timezone.now() - timedelta(minutes=5)
            recent_attempts = VerificationToken.objects.filter(
                user=user, token_type="password_reset", created_at__gte=five_minutes_ago
            ).count()

            if recent_attempts >= 3:
                return False, "Too many reset attempts. Please try again in 5 minutes."

            # Check for existing valid password reset token
            valid_token = VerificationToken.objects.filter(
                user=user,
                token_type="password_reset",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if valid_token:
                # Resend email with existing token
                reset_url = PasswordService._build_reset_url(valid_token.token, request)
                success = PasswordService._send_reset_email(user, reset_url)

                if success:
                    return True, "Password reset email sent successfully"
                else:
                    return False, "Failed to send reset email"

            # Create new password reset token
            token = generate_verification_token(user)
            expires_at = timezone.now() + timedelta(hours=1)  # 1 hour expiry

            # Save token to database
            verification_token = VerificationToken.objects.create(
                user=user,
                token=token,
                token_type="password_reset",
                expires_at=expires_at,
            )

            # Log request info
            if request:
                verification_token.ip_address = request.META.get("REMOTE_ADDR")
                verification_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
                verification_token.save()

            # Build reset URL
            print("Email ", user.email)
            reset_url = PasswordService._build_reset_url(token, user.email)

            # Send reset email
            success = PasswordService._send_reset_email(user, reset_url)

            if success:
                logger.info(f"Password reset email sent to {user.email}")
                return True, "Password reset email sent successfully"
            else:
                return False, "Failed to send reset email"

        except Exception as e:
            logger.error(f"Password reset request error for {email}: {str(e)}")
            return False, "Password reset request failed"

    @staticmethod
    def _build_reset_url(token, email):
        """Build the password reset URL for frontend"""
        base_url = settings.FRONTEND_BASE_URL.rstrip("/")

        query = urlencode({"token": token, "email": email})

        return f"{base_url}/reset-password/?{query}"

    @staticmethod
    def _send_reset_email(user, reset_url):
        """Send password reset email"""
        subject = f"Reset Your Password - {getattr(settings, 'SITE_NAME', 'API')}"

        return send_templated_email(
            recipient_email=user.email,
            subject=subject,
            template="password_reset.html",
            context={"reset_url": reset_url},
            recipient_name=user.username or user.email,
            async_send=False,
        )

    @staticmethod
    def validate_token(token):
        """
        Validate password reset token
        Returns: (valid, error_message, user)
        """
        try:
            reset_token = VerificationToken.objects.filter(
                token=token,
                token_type="password_reset",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if not reset_token:
                return False, "Invalid or expired reset token", None

            return True, "Token is valid", reset_token.user

        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False, "Token validation failed", None

    @staticmethod
    def reset_password(token, new_password, request):
        """
        Reset password using token
        Returns: (success, error_message)
        """
        try:
            # Validate token
            valid, error, user = PasswordService.validate_token(token)

            if not valid:
                return False, error

            # Validate password strength
            from ..utils.validators import UserValidators

            is_valid, error, _ = UserValidators.validate_password_strength(new_password)
            if not is_valid:
                return False, error

            # Set new password
            user.set_password(new_password)
            user.save()

            # Mark token as used
            reset_token = VerificationToken.objects.get(
                token=token, token_type="password_reset"
            )
            reset_token.mark_as_used()

            # Update request info
            if request:
                reset_token.ip_address = request.META.get("REMOTE_ADDR")
                reset_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
                reset_token.save()

            # Send password changed confirmation email
            PasswordService._send_password_changed_email(user, request)

            # Blacklist all user's tokens for security
            # from .token_service import TokenService
            # TokenService.blacklist_all_user_tokens(
            #     str(user.id),
            #     request=request,
            #     reason='password_reset'
            # )

            logger.info(f"Password reset successful for user: {user.email}")
            return True, "Password reset successful"

        except Exception as e:
            logger.error(f"Password reset error: {str(e)}")
            return False, "Password reset failed"

    @staticmethod
    def _send_password_changed_email(user, request=None):
        """Send password changed confirmation email"""
        subject = (
            f"Your Password Has Been Changed - {getattr(settings, 'SITE_NAME', 'API')}"
        )

        # Get IP address if available
        ip_address = request.META.get("REMOTE_ADDR") if request else "unknown"
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")

        try:
            return send_templated_email(
                recipient_email=user.email,
                subject=subject,
                template="password_changed.html",
                context={"timestamp": timestamp, "ip_address": ip_address},
                recipient_name=user.username or user.email,
            )
        except Exception as e:
            logger.error(f"Failed to send password changed email: {str(e)}")
            return False

    @staticmethod
    def cleanup_expired_tokens():
        """Clean up expired password reset tokens"""
        try:
            # Clean up all expired tokens (including password reset)
            expired_tokens = VerificationToken.objects.filter(
                expires_at__lt=timezone.now()
            )
            count = expired_tokens.count()
            expired_tokens.delete()
            logger.info(f"Cleaned up {count} expired tokens")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {str(e)}")
            return 0
