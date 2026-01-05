"""
users/utils/validators.py

Input validation and sanitization utilities
"""
import re
from typing import Dict, Optional, Tuple
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password as django_validate_password


class UserValidators:
    """Input validation for user operations"""
    
    @staticmethod
    def validate_email_format(email: str) -> Tuple[bool, Optional[str]]:
        """Validate email format"""
        try:
            validate_email(email)
            return True, None
        except ValidationError:
            return False, "Invalid email format"
    
    @staticmethod
    def validate_password_strength(password: str) -> Tuple[bool, Optional[str], Optional[list]]:
        """Validate password strength and return issues"""
        errors = []
        try:
            django_validate_password(password)
        except ValidationError as e:
            errors = list(e.messages)
            return False, "Password does not meet security requirements", errors
        
        # Additional custom validations
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        
        if errors:
            return False, "Password does not meet security requirements", errors
        
        return True, None, None
    
    @staticmethod
    def validate_phone_number(phone: str) -> Tuple[bool, Optional[str]]:
        """Validate phone number format (basic validation)"""
        # Remove all non-digit characters
        cleaned = re.sub(r'\D', '', phone)
        
        if len(cleaned) < 10:
            return False, "Phone number must be at least 10 digits"
        
        # E.164 format validation (optional)
        if not re.match(r'^\+?[1-9]\d{1,14}$', phone):
            return False, "Phone number format is invalid"
        
        return True, None
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = None) -> str:
        """Sanitize string input"""
        if not value:
            return value
        
        # Remove excessive whitespace
        value = ' '.join(value.split())
        
        # Truncate if max_length specified
        if max_length and len(value) > max_length:
            value = value[:max_length]
        
        return value.strip()
    
    @staticmethod
    def validate_registration_data(data: Dict) -> Tuple[bool, Optional[Dict]]:
        """Validate registration data"""
        errors = {}
        
        # Required fields
        required_fields = ['email', 'username', 'password']
        for field in required_fields:
            if not data.get(field):
                errors[field] = "This field is required"
        
        # Email validation
        if 'email' in data and data['email']:
            is_valid, email_error = UserValidators.validate_email_format(data['email'])
            if not is_valid:
                errors['email'] = email_error
        
        # Password validation
        if 'password' in data and data['password']:
            is_valid, pwd_error, pwd_errors = UserValidators.validate_password_strength(data['password'])
            if not is_valid:
                errors['password'] = pwd_errors or [pwd_error]
        
        # Username validation
        if 'username' in data and data['username']:
            username = data['username'].strip()
            if len(username) < 3:
                errors['username'] = "Username must be at least 3 characters long"
            if len(username) > 30:
                errors['username'] = "Username must be at most 30 characters long"
            if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
                errors['username'] = "Username can only contain letters, numbers, dots, dashes, and underscores"
        
        if errors:
            return False, errors
        
        return True, None