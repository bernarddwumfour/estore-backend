"""
users/models/customer.py

Customer-specific data (separate from auth)
"""
import uuid
from datetime import date
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def validate_minimum_age(value):
    """Customer must be at least 13 years old. A function (not a
    MaxValueValidator built from date.today()) so the cutoff is evaluated at
    validation time — a baked-in date changes daily and makes makemigrations
    demand a new migration every day."""
    if not value:
        return
    today = date.today()
    try:
        cutoff = today.replace(year=today.year - 13)
    except ValueError:  # Feb 29 in a non-leap target year
        cutoff = today.replace(month=2, day=28, year=today.year - 13)
    if value > cutoff:
        raise ValidationError(_("Must be at least 13 years old."))


class CustomerProfile(models.Model):
    """
    Customer profile with essential e-commerce data
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='customer_profile'
    )
    
    # Essential personal data
    date_of_birth = models.DateField(
        _("date of birth"),
        null=True,
        blank=True,
        validators=[validate_minimum_age],
    )
    
    # Communication preferences (simple boolean flags)
    receive_marketing = models.BooleanField(
        _("receive marketing emails"),
        default=True
    )
    
    receive_newsletter = models.BooleanField(
        _("receive newsletter"),
        default=True
    )
    
    # Customer metadata
    last_order_date = models.DateTimeField(
        _("last order date"),
        null=True,
        blank=True
    )
    
    # Loyalty (simple implementation)
    loyalty_points = models.IntegerField(
        _("loyalty points"),
        default=0
    )
    
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        db_table = 'customer_profiles'
        verbose_name = _("customer profile")
    
    def __str__(self):
        return f"Customer: {self.user.email}"
    
    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class StaffProfile(models.Model):
       
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='staff_profile'
    )
    
    employee_id = models.CharField(
        _("employee ID"),
        max_length=50,
        unique=True
    )
    
    department = models.CharField(
        _("department"),
        max_length=100,
        blank=True
    )
    
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    
    class Meta:
        db_table = 'staff_profiles'
        verbose_name = _("staff profile")
    
    def __str__(self):
        return f"Staff: {self.user.email}"