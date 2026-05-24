"""
users/utils/token_utils.py

Token generation and validation utilities
"""

import secrets
import string
import uuid
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
import jwt
import hashlib
from typing import Optional, Tuple, Dict, Any


def generate_verification_token(user, token_length: int = 32) -> str:
    """
    Generate a secure random verification token

    Args:
        user: User object (for uniqueness)
        token_length: Length of token to generate (default: 32)

    Returns:
        str: Secure random token
    """
    try:
        # Use a combination of random characters for security
        alphabet = string.ascii_letters + string.digits + "-_"

        # Generate random token
        token = "".join(secrets.choice(alphabet) for _ in range(token_length))

        # Add timestamp and user ID hash for additional uniqueness
        timestamp = str(int(timezone.now().timestamp()))
        user_id_hash = hashlib.sha256(str(user.id).encode()).hexdigest()[:8]

        # Create final token with timestamp and user hash
        final_token = f"{token}_{timestamp}_{user_id_hash}"

        return final_token

    except Exception as e:
        # Fallback to simple random token if something goes wrong
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(token_length))


def generate_jwt_token(user, token_type: str = "access", expires_in: int = None) -> str:
    """
    Generate JWT token

    Args:
        user: User object
        token_type: Type of token ('access', 'refresh', 'verification')
        expires_in: Expiry time in seconds

    Returns:
        str: JWT token
    """
    try:
        # Set default expiry based on token type
        if expires_in is None:
            if token_type == "access":
                expires_in = getattr(
                    settings, "ACCESS_TOKEN_TTL", 15 * 60
                )  # 15 minutes
            elif token_type == "refresh":
                expires_in = getattr(
                    settings, "REFRESH_TOKEN_TTL", 7 * 24 * 60 * 60
                )  # 7 days
            elif token_type == "verification":
                expires_in = getattr(
                    settings, "VERIFICATION_TOKEN_TTL", 24 * 60 * 60
                )  # 24 hours
            else:
                expires_in = 3600  # 1 hour default

        # Create JWT payload
        payload = {
            "user_id": str(user.id),
            "email": user.email,
            "type": token_type,
            "exp": datetime.utcnow() + timedelta(seconds=expires_in),
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),  # JWT ID for tracking
            "role": user.role,
        }

        # Add additional claims based on token type
        if token_type == "verification":
            payload["purpose"] = "email_verification"

        # Generate JWT token
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        return token

    except Exception as e:
        raise Exception(f"Failed to generate JWT token: {str(e)}")


def validate_jwt_token(token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Validate JWT token

    Args:
        token: JWT token string

    Returns:
        Tuple[bool, Optional[Dict], Optional[str]]: (is_valid, payload, error_message)
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return True, payload

    except jwt.ExpiredSignatureError:
        return False, "Token has expired"
    except jwt.InvalidTokenError as e:
        return False, f"Invalid token: {str(e)}"
    except Exception as e:
        return False, f"Token validation failed: {str(e)}"


def generate_numeric_code(length: int = 6) -> str:
    """
    Generate a numeric verification code (for SMS/OTP)

    Args:
        length: Length of numeric code (default: 6)

    Returns:
        str: Numeric code
    """
    # Ensure minimum length of 4 for security
    if length < 4:
        length = 4

    # Generate secure numeric code
    digits = string.digits
    code = "".join(secrets.choice(digits) for _ in range(length))

    return code


def generate_api_key(length: int = 32) -> str:
    """
    Generate a secure API key

    Args:
        length: Length of API key (default: 32)

    Returns:
        str: API key
    """
    # Generate random bytes and encode as URL-safe base64
    random_bytes = secrets.token_bytes(length)

    # Convert to URL-safe base64
    import base64

    api_key = base64.urlsafe_b64encode(random_bytes).decode("ascii")

    # Trim to desired length
    return api_key[:length]


def generate_short_token(length: int = 8) -> str:
    """
    Generate a short token (for URLs, invitations, etc.)

    Args:
        length: Length of token (default: 8)

    Returns:
        str: Short token
    """
    # Use a reduced alphabet for shorter, more readable tokens
    alphabet = string.ascii_uppercase + string.digits

    # Remove ambiguous characters
    ambiguous = "0O1Il"
    for char in ambiguous:
        alphabet = alphabet.replace(char, "")

    # Generate token
    token = "".join(secrets.choice(alphabet) for _ in range(length))

    return token


def hash_token(token: str) -> str:
    """
    Hash a token for secure storage (not reversible)

    Args:
        token: Plain text token

    Returns:
        str: Hashed token
    """
    # Use SHA-256 for hashing
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, hashed_token: str) -> bool:
    """
    Verify a token against its hash

    Args:
        token: Plain text token to verify
        hashed_token: Previously hashed token

    Returns:
        bool: True if token matches hash
    """
    return hash_token(token) == hashed_token


def generate_secure_random_string(length: int = 16) -> str:
    """
    Generate a secure random string

    Args:
        length: Length of string (default: 16)

    Returns:
        str: Random string
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"

    # Ensure at least one of each type for strong passwords
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))

        # Check if meets basic criteria
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)
        ):
            return password


def create_token_pair(user) -> Dict[str, str]:
    """
    Create access and refresh token pair

    Args:
        user: User object

    Returns:
        Dict with access_token and refresh_token
    """
    access_token = generate_jwt_token(user, "access")
    refresh_token = generate_jwt_token(user, "refresh")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": getattr(settings, "ACCESS_TOKEN_TTL", 15 * 60),
    }


def extract_token_from_header(auth_header: str) -> Optional[str]:
    """
    Extract token from Authorization header

    Args:
        auth_header: Authorization header string

    Returns:
        str: Token or None if invalid
    """
    if not auth_header:
        return None

    parts = auth_header.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def is_token_expired(token: str) -> bool:
    """
    Check if JWT token is expired

    Args:
        token: JWT token string

    Returns:
        bool: True if expired
    """
    try:
        # Decode without verification to check expiry
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )

        # Check expiry
        exp_timestamp = payload.get("exp")
        if not exp_timestamp:
            return True

        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        return datetime.utcnow() > exp_datetime

    except Exception:
        return True


def get_token_payload(token: str) -> Optional[Dict]:
    """
    Get token payload without validation

    Args:
        token: JWT token

    Returns:
        Dict: Token payload or None
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False, "verify_signature": False},
        )
        return payload
    except Exception:
        return None
