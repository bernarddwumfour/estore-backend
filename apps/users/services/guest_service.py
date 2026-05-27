# apps/users/services/guest_service.py

import logging
from typing import Dict, Optional, Tuple
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from apps.users.models import User

logger = logging.getLogger(__name__)


class GuestCheckoutService:
    """Service for guest checkout operations"""
    
    
    @staticmethod
    @transaction.atomic
    def create_guest_checkout(
        data: Dict[str, any],
        order_data: Dict = None,
    ) -> Tuple[Optional[User], Optional[str]]:  # Changed return type to User, not Dict
        """
        Create or retrieve guest user for checkout
        
        Args:
            data: Dictionary containing guest user data (email, first_name, last_name, phone)
            order_data: Optional order data to include in response
        
        Returns:
            Tuple of (guest_user, error_message) - guest_user is a User object
        """
        from apps.users.models.user import User
        
        try:
            # Validate required fields
            required_fields = ['email', 'first_name', 'last_name']
            for field in required_fields:
                if not data.get(field):
                    return None, f"{field} is required"
            
            email = data['email'].lower().strip()
            first_name = data['first_name'].strip()
            last_name = data['last_name'].strip()
            
            # Validate email format
            try:
                validate_email(email)
            except ValidationError:
                return None, "Invalid email format"
            
            # Check if user exists with this email
            user = User.objects.filter(email=email).first()
            
            if user:
                # If user exists and has a password, they should log in
                if user.has_usable_password():
                    return None, "User already exists. Please log in to continue."
                
                # If user exists as guest, update their information
                if first_name:
                    user.first_name = first_name
                if last_name:
                    user.last_name = last_name
                if data.get('phone'):
                    user.phone = data['phone'].strip()
                user.save()
                
                logger.info(f"Existing guest user updated: {user.email}")
            else:
                # Create new guest user
                user = User.objects.create_guest(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                )
                
                # Set phone if provided
                if data.get('phone'):
                    user.phone = data['phone'].strip()
                    user.save()
                
                logger.info(f"New guest user created: {user.email}")
            
            # Return the User object directly
            return user, None
            
        except Exception as e:
            logger.error(f"Guest checkout error: {str(e)}")
            return None, "Failed to process guest checkout"
    
   
    
    @staticmethod
    def get_guest_user_by_email(email: str) -> Optional[Dict]:
        """
        Get guest user by email
        
        Args:
            email: User email address
        
        Returns:
            Serialized guest user data or None
        """
        from apps.users.models.user import User
        
        try:
            email = email.lower().strip()
            user = User.objects.filter(email=email).first()
            
            if user and not user.has_usable_password():
                return {
                    "id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_guest": True,
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Get guest user error: {str(e)}")
            return None
    
    @staticmethod
    def convert_guest_to_registered(email: str, password: str, **extra_fields) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Convert a guest user to a registered user with password
        
        Args:
            email: Guest user email
            password: New password for the user
            extra_fields: Additional user fields (first_name, last_name, phone, etc.)
        
        Returns:
            Tuple of (user_data, error_message)
        """
        from apps.users.models.user import User
        from apps.users.utils.validators import UserValidators
        
        try:
            email = email.lower().strip()
            user = User.objects.filter(email=email).first()
            
            if not user:
                return None, "User not found"
            
            if user.has_usable_password():
                return None, "User already has a password. Please log in."
            
            # Validate password strength
            is_valid, error, _ = UserValidators.validate_password_strength(password)
            if not is_valid:
                return None, error
            
            # Set password and update user info
            user.set_password(password)
            
            # Update user fields
            if extra_fields.get('first_name'):
                user.first_name = extra_fields['first_name']
            if extra_fields.get('last_name'):
                user.last_name = extra_fields['last_name']
            if extra_fields.get('phone'):
                user.phone = extra_fields['phone']
            
            # Generate username if not set
            if not user.username:
                user.username = email
            
            user.save()
            
            logger.info(f"Guest user converted to registered user: {user.email}")
            
            # Prepare user data
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "role": user.role,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
            }
            
            return user_data, None
            
        except Exception as e:
            logger.error(f"Convert guest to registered error: {str(e)}")
            return None, "Failed to convert guest user"