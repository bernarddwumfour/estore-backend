# apps/users/managers.py

from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager for User model with roles and permissions."""

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")

        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
            user.is_guest = False
        else:
            user.set_unusable_password()
            user.is_guest = True
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Default create_user method - creates a regular user (customer by default)"""
        extra_fields.setdefault("role", self.model.ROLE_CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_guest", False)
        return self._create_user(email, password, **extra_fields)

    def create_customer(self, email, password=None, **extra_fields):
        """Create a customer user"""
        extra_fields.setdefault("role", self.model.ROLE_CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_guest", False)
        return self._create_user(email, password, **extra_fields)

    def create_guest(self, email, first_name='', last_name='', **extra_fields):
        """Create a guest user (no password, email not verified)"""
        email = self.normalize_email(email)
        extra_fields.setdefault("role", self.model.ROLE_CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("email_verified", False)
        extra_fields.setdefault("first_name", first_name)
        extra_fields.setdefault("last_name", last_name)
        extra_fields.setdefault("username", f"guest_{email.split('@')[0]}_{hash(email) % 10000}")
        extra_fields.setdefault("is_guest", True)
        
        return self._create_user(email, None, **extra_fields)

    def create_staff(self, email, password=None, **extra_fields):
        """Create a staff user"""
        extra_fields.setdefault("role", self.model.ROLE_STAFF)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_guest", False)
        return self._create_user(email, password, **extra_fields)

    def create_admin(self, email, password=None, **extra_fields):
        """Create an admin user"""
        extra_fields.setdefault("role", self.model.ROLE_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_guest", False)

        if not extra_fields["is_staff"]:
            raise ValueError("Admin must have is_staff=True")
        if not extra_fields["is_superuser"]:
            raise ValueError("Admin must have is_superuser=True")

        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create a superuser (admin)"""
        return self.create_admin(email, password, **extra_fields)