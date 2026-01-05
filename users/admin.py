# users/admin.py - ONLY register and configure admin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models.customer import CustomerProfile
from .models.address import Address
from .models.user import User
from .models.customer import CustomerProfile

# Register your models to admin
admin.site.register(User, UserAdmin)  # Or CustomUserAdmin
admin.site.register(CustomerProfile)
admin.site.register(Address)