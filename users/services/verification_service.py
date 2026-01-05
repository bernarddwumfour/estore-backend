"""
users/services/verification_service.py
"""

import logging
import secrets
import string
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings

from ..models.user import User
from ..models.verification_token import VerificationToken
from estore.utils.email_util import send_email
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class VerificationService:

    @staticmethod
    def generate_token(length=32):
        """Generate a secure random token"""
        alphabet = string.ascii_letters + string.digits + "-_"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def create_verification_token(user, request=None):
        """Create and save verification token"""
        try:
            # Generate unique token
            token = VerificationService.generate_token()

            # Ensure token is unique
            while VerificationToken.objects.filter(token=token).exists():
                token = VerificationService.generate_token()

            # Calculate expiry
            expires_at = timezone.now() + timedelta(
                hours=getattr(settings, "EMAIL_VERIFICATION_EXPIRY_HOURS", 24)
            )

            # Create token record
            verification_token = VerificationToken.objects.create(
                user=user,
                token=token,
                token_type="email_verification",
                expires_at=expires_at,
            )

            # Log request info
            if request:
                verification_token.ip_address = request.META.get("REMOTE_ADDR")
                verification_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
                verification_token.save()

            return verification_token

        except Exception as e:
            logger.error(
                f"Failed to create verification token for {user.email}: {str(e)}"
            )
            return None

    @staticmethod
    def send_verification_email(user, request=None):
        """
        Send email verification link to user
        """
        try:
            if user.email_verified:
                return True, "Email is already verified"

            # Create verification token
            verification_token = VerificationService.create_verification_token(
                user, request
            )
            if not verification_token:
                return False, "Failed to create verification token"

            # Build verification URL
            verification_url = VerificationService._build_verification_url(
                verification_token.token, user.email
            )

            # Send email
            success = VerificationService._send_verification_email(
                user, verification_url
            )

            if success:
                logger.info(f"Verification email sent to {user.email}")
                return True, "Verification email sent successfully"
            else:
                return False, "Failed to send verification email"

        except Exception as e:
            logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
            return False, "Failed to send verification email"

    @staticmethod
    def _build_verification_url(token, email):
        """
        Build frontend email verification URL
        """
        base_url = settings.FRONTEND_BASE_URL.rstrip("/")

        query = urlencode({"token": token, "email": email})

        return f"{base_url}/verify-email?{query}"

    @staticmethod
    def _send_verification_email(user, verification_url):
        """Send the actual verification email"""
        subject = f"Verify Your Email - {getattr(settings, 'SITE_NAME', 'API')}"

        # Plain text email
        message_text = f"""Hello {user.username or user.email},

Please verify your email address by clicking this link:
{verification_url}

This link will expire in {getattr(settings, 'EMAIL_VERIFICATION_EXPIRY_HOURS', 24)} hours.

If you didn't create an account, please ignore this email.

Best regards,
{getattr(settings, 'SITE_NAME', 'API')} Team"""

        # HTML email
        html_message = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <div style="max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Verify Your Email</h2>
        <p>Hello <strong>{user.username or user.email}</strong>,</p>
        <p>Please verify your email address by clicking the button below:</p>
        <p>
            <a href="{verification_url}" 
               style="background: #4CAF50; color: white; padding: 12px 24px; 
                      text-decoration: none; border-radius: 5px; display: inline-block;">
                Verify Email Address
            </a>
        </p>
        <p>Or copy this link to your browser:<br>
        <code style="background: #f5f5f5; padding: 8px; border-radius: 3px; 
                     word-break: break-all; display: block; margin: 10px 0;">
            {verification_url}
        </code></p>
        <p><strong>Note:</strong> This link expires in {getattr(settings, 'EMAIL_VERIFICATION_EXPIRY_HOURS', 24)} hours.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p>Best regards,<br>
        <strong>{getattr(settings, 'SITE_NAME', 'API')} Team</strong></p>
    </div>
</body>
</html>"""

        return send_email(
            recipient_email=user.email,
            subject=subject,
            message_text=message_text,
            html_message=html_message,
        )

    @staticmethod
    def verify_email_token(token):
        """
        Verify email token using database model
        """
        try:
            # Find valid token
            verification_token = VerificationToken.objects.filter(
                token=token,
                token_type="email_verification",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if not verification_token:
                return False, None, "Invalid or expired verification token"

            # Update user
            user = verification_token.user
            user.mark_email_verified()

            # Mark token as used
            verification_token.mark_as_used()

            logger.info(f"Email verified for user: {user.email}")
            return True, user, "Email verified successfully"

        except Exception as e:
            logger.error(f"Email verification error: {str(e)}")
            return False, None, "Email verification failed"

    @staticmethod
    def validate_token(token):
        """Check if token is valid without using it"""
        try:
            verification_token = VerificationToken.objects.filter(
                token=token,
                token_type="email_verification",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if verification_token:
                return True, verification_token.user, "Token is valid"
            else:
                return False, None, "Invalid or expired token"

        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False, None, "Token validation failed"

    @staticmethod
    def resend_verification_email(email, request):
        """
        Resend verification email with rate limiting
        """
        try:
            user = User.objects.filter(email=email).first()

            if not user:
                # Security: don't reveal if email exists
                return (
                    True,
                    "If your email exists and is not verified, you will receive a verification email shortly",
                )

            if user.email_verified:
                return True, "Email is already verified"

            # Rate limiting: Check recent attempts
            five_minutes_ago = timezone.now() - timedelta(minutes=5)
            recent_attempts = VerificationToken.objects.filter(
                user=user,
                token_type="email_verification",
                created_at__gte=five_minutes_ago,
            ).count()

            if recent_attempts >= 3:
                return (
                    False,
                    "Too many verification attempts. Please try again in 5 minutes.",
                )

            # Check for existing valid token
            valid_token = VerificationToken.objects.filter(
                user=user,
                token_type="email_verification",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if valid_token:
                # Resend with existing token
                verification_url = VerificationService._build_verification_url(
                    valid_token.token, user.email
                )
                success = VerificationService._send_verification_email(
                    user, verification_url
                )

                if success:
                    return True, "Verification email resent successfully"
                else:
                    return False, "Failed to resend verification email"

            # Create new token and send
            return VerificationService.send_verification_email(user, request)

        except Exception as e:
            logger.error(f"Resend verification error for {email}: {str(e)}")
            return False, "Failed to resend verification email"

    @staticmethod
    def cleanup_expired_tokens():
        """Clean up expired verification tokens"""
        try:
            expired_tokens = VerificationToken.objects.filter(
                expires_at__lt=timezone.now()
            )
            count = expired_tokens.count()
            expired_tokens.delete()
            logger.info(f"Cleaned up {count} expired verification tokens")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {str(e)}")
            return 0

    @staticmethod
    def get_verification_status(user_id):
        """Get verification statistics for a user"""
        try:
            user = User.objects.get(id=user_id)

            tokens = VerificationToken.objects.filter(
                user=user, token_type="email_verification"
            )

            return {
                "email_verified": user.email_verified,
                "email_verified_at": user.email_verified_at,
                "total_tokens": tokens.count(),
                "used_tokens": tokens.filter(is_used=True).count(),
                "active_tokens": tokens.filter(
                    is_used=False, expires_at__gt=timezone.now()
                ).count(),
                "last_token_created": (
                    tokens.order_by("-created_at").first().created_at
                    if tokens.exists()
                    else None
                ),
            }
        except User.DoesNotExist:
            return None
