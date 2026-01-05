"""
users/services/auth_service.py
Updated for lean User model
"""

import logging
from typing import Dict, Any, Optional, Tuple
from django.db import transaction
from django.contrib.auth import authenticate
from django.conf import settings
from django.utils import timezone

from users.utils.token_utils import generate_jwt_token
from ..models.user import User
from ..utils.validators import UserValidators
from .verification_service import VerificationService


logger = logging.getLogger(__name__)


class AuthService:
    """Authentication business logic service"""

    @staticmethod
    @transaction.atomic
    def register_user(
        data: Dict[str, Any], request=None
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Register a new user
        Returns: (user_data, errors)
        """
        # Validate required fields
        required_fields = ["email", "password", "first_name", "last_name", "role"]
        errors = {}
        for field in required_fields:
            if not data.get(field):
                errors[field] = "This field is required"

        if errors:
            return None, errors

        # Validate email format
        is_valid_email, email_error = UserValidators.validate_email_format(
            data["email"]
        )
        if not is_valid_email:
            return None, {"email": email_error}

        # Validate password strength
        is_valid_password, pwd_error, _ = UserValidators.validate_password_strength(
            data["password"]
        )
        if not is_valid_password:
            return None, {"password": pwd_error}

        # Validate role
        valid_roles = [User.ROLE_CUSTOMER, User.ROLE_STAFF, User.ROLE_ADMIN]
        if data["role"] not in valid_roles:
            return None, {
                "role": f'Invalid role. Must be one of: {", ".join(valid_roles)}'
            }

        email = data["email"].lower().strip()

        # Check for existing user
        if User.objects.filter(email=email).exists():
            return None, {"email": "A user with this email already exists"}

        try:
            # Create user with required fields
            user = User.objects.create_user(
                email=email,
                password=data["password"],
                first_name=data["first_name"].strip(),
                last_name=data["last_name"].strip(),
                role=data["role"],
            )

            # Set optional phone if provided
            if "phone" in data and data["phone"]:
                user.phone = data["phone"].strip()

            user.save()

            # After creating user successfully:
            if user and not getattr(settings, "DISABLE_EMAIL_VERIFICATION", False):
                # Send verification email
                VerificationService.send_verification_email(user, request)
                print("Email Sent")

            # Generate tokens
            access_token = generate_jwt_token(user, "access")
            refresh_token, _ = generate_jwt_token(user, "refresh")

            # Prepare response data
            user_data = {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "phone": user.phone,
                    "role": user.role,
                    "email_verified": user.email_verified,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                },
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer",
                },
            }

            logger.info(
                f"User registered: {user.email} (ID: {user.id}, Role: {user.role})"
            )

            return user_data, None

        except Exception as e:
            logger.error(f"Registration failed for {email}: {str(e)}")
            return None, {"general": "Registration failed. Please try again."}

    @staticmethod
    @transaction.atomic
    def register_customer(
        data: Dict[str, Any], request=None
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Self-registration for customers only
        Role is automatically set to CUSTOMER
        """
        # Validate required fields (no role in input)
        required_fields = ["email", "password", "first_name", "last_name"]
        errors = {}
        for field in required_fields:
            if not data.get(field):
                errors[field] = "This field is required"

        if errors:
            return None, errors

        # Validate email format
        is_valid_email, email_error = UserValidators.validate_email_format(
            data["email"]
        )
        if not is_valid_email:
            return None, {"email": email_error}

        # Validate password strength
        is_valid_password, pwd_error, _ = UserValidators.validate_password_strength(
            data["password"]
        )
        if not is_valid_password:
            return None, {"password": pwd_error}

        email = data["email"].lower().strip()

        # Check for existing user
        if User.objects.filter(email=email).exists():
            return None, {"email": "A user with this email already exists"}

        try:
            # Create user - role is FORCED to CUSTOMER
            user = User.objects.create_customer(
                email=email,
                password=data["password"],
                first_name=data["first_name"].strip(),
                last_name=data["last_name"].strip(),
                role=User.ROLE_CUSTOMER,  # Always customer for self-registration
            )

            # Set optional phone if provided
            if "phone" in data and data["phone"]:
                user.phone = data["phone"].strip()

            user.save()

            # After creating user successfully:
            if user and not getattr(settings, "DISABLE_EMAIL_VERIFICATION", False):
                # Send verification email
                VerificationService.send_verification_email(user, request)
                print("Email Sent")

            # Generate tokens
            access_token = generate_jwt_token(user, "access")
            refresh_token, _ = generate_jwt_token(user, "refresh")

            # Prepare response data
            user_data = {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "phone": user.phone,
                    "role": user.role,  # Will always be 'customer'
                    # 'email_verified': user.email_verified,
                    "is_active": user.is_active,
                    "created_at": user.created_at.isoformat(),
                },
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "Bearer",
                },
            }

            logger.info(f"Customer registered: {user.email} (ID: {user.id})")

            return user_data, None

        except Exception as e:
            logger.error(f"Customer registration failed for {email}: {str(e)}")
            return None, {"general": "Registration failed. Please try again."}

    @staticmethod
    def authenticate_user(
        email: str, password: str, request=None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Authenticate user and generate tokens
        Returns: (auth_data, error_message)
        """
        try:
            # Authenticate
            user = authenticate(
                request, username=email.lower().strip(), password=password
            )

            if not user:
                return None, "Invalid email or password"

            if not user.is_active:
                return None, "Account is deactivated"

            # Generate tokens
            access_token = generate_jwt_token(user, "access")
            print("HERE")
            refresh_token = generate_jwt_token(user, "refresh")

            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            # Log login
            ip_address = None
            if request:
                x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
                ip_address = (
                    x_forwarded_for.split(",")[0]
                    if x_forwarded_for
                    else request.META.get("REMOTE_ADDR")
                )

            logger.info(f"User logged in: {user.email} from IP: {ip_address}")

            # Prepare response
            auth_data = {
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "phone": user.phone,
                    "role": user.role,
                    "email_verified": user.email_verified,
                    "is_active": user.is_active,
                },
                "tokens": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                },
            }

            return auth_data, None

        except Exception as e:
            logger.error(f"Authentication error for {email}: {str(e)}")
            return None, "Authentication failed"
