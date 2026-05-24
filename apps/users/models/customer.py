"""
users/models/customer.py

Customer-specific data (separate from auth)
"""
import uuid
from datetime import date
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator


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
        validators=[
            MaxValueValidator(
                date.today().replace(year=date.today().year - 13),
                message=_("Must be at least 13 years old.")
            )
        ]
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