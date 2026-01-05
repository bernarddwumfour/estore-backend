from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager for User model with roles and permissions."""

    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email must be set")

        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    # ========== ADD THIS METHOD ==========
    def create_user(self, email, password=None, **extra_fields):
        """
        Default create_user method - creates a regular user (customer by default)
        This is REQUIRED by Django's authentication system
        """
        extra_fields.setdefault("role", self.model.ROLE_CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_customer(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.ROLE_CUSTOMER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_staff(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.ROLE_STAFF)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_admin(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", self.model.ROLE_ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not extra_fields["is_staff"]:
            raise ValueError("Admin must have is_staff=True")
        if not extra_fields["is_superuser"]:
            raise ValueError("Admin must have is_superuser=True")

        return self._create_user(email, password, **extra_fields)

    # Required by Django
    def create_superuser(self, email, password=None, **extra_fields):
        return self.create_admin(email, password, **extra_fields)
