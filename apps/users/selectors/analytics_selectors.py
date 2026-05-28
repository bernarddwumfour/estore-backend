"""
User Analytics Selectors - Database read operations for user analytics
No business logic - just queries
"""

from django.db.models import Sum, Count, Avg, Q, F, Min, Max, OuterRef, Subquery, DecimalField, IntegerField, FloatField
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, Coalesce
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from apps.users.models.user import User
from apps.users.models.address import Address
from apps.users.models.affiliate import Affiliate
from apps.users.models.customer import CustomerProfile
from apps.orders.models import Order, OrderItem


class UserAnalyticsSelector:
    """Selector for user analytics data"""
    
    @staticmethod
    def get_user_overview_stats(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get user overview statistics"""
        
        user_qs = User.objects.all()
        
        if start_date:
            user_qs = user_qs.filter(created_at__gte=start_date)
        if end_date:
            user_qs = user_qs.filter(created_at__lte=end_date)
        
        # User counts
        total_users = user_qs.count()
        active_users = user_qs.filter(is_active=True).count()
        inactive_users = user_qs.filter(is_active=False).count()
        verified_emails = user_qs.filter(email_verified=True).count()
        unverified_emails = user_qs.filter(email_verified=False).count()
        
        # Role distribution
        customers = user_qs.filter(role=User.ROLE_CUSTOMER).count()
        staff = user_qs.filter(role=User.ROLE_STAFF).count()
        admins = user_qs.filter(role=User.ROLE_ADMIN).count()
        guests = user_qs.filter(is_guest=True).count()
        registered = user_qs.filter(is_guest=False).count()
        
        # New users by period
        thirty_days_ago = timezone.now() - timedelta(days=30)
        seven_days_ago = timezone.now() - timedelta(days=7)
        
        new_users_30d = user_qs.filter(created_at__gte=thirty_days_ago).count()
        new_users_7d = user_qs.filter(created_at__gte=seven_days_ago).count()
        
        # Active today
        today = timezone.now().date()
        active_today = user_qs.filter(last_login__date=today).count()
        
        return {
            "summary": {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": inactive_users,
                "verified_emails": verified_emails,
                "unverified_emails": unverified_emails,
                "verified_percentage": round(verified_emails / total_users * 100, 2) if total_users > 0 else 0,
            },
            "role_distribution": {
                "customers": customers,
                "staff": staff,
                "admins": admins,
                "guests": guests,
                "registered": registered,
                "customer_percentage": round(customers / total_users * 100, 2) if total_users > 0 else 0,
                "staff_percentage": round(staff / total_users * 100, 2) if total_users > 0 else 0,
                "guest_percentage": round(guests / total_users * 100, 2) if total_users > 0 else 0,
            },
            "growth": {
                "new_users_30d": new_users_30d,
                "new_users_7d": new_users_7d,
                "active_today": active_today,
            }
        }
    
    @staticmethod
    def get_user_growth_trends(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = 'day'
    ) -> List[Dict[str, Any]]:
        """Get user growth trends over time"""
        
        queryset = User.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        trunc_func = {
            'day': TruncDay,
            'week': TruncWeek,
            'month': TruncMonth,
        }.get(interval, TruncDay)
        
        trends = queryset.annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            new_users=Count('id'),
            active_users=Count('id', filter=Q(is_active=True)),
            verified_users=Count('id', filter=Q(email_verified=True)),
        ).order_by('period')
        
        return [
            {
                "period": item['period'].isoformat() if item['period'] else None,
                "new_users": item['new_users'],
                "active_users": item['active_users'],
                "verified_users": item['verified_users'],
            }
            for item in trends
        ]
    
    @staticmethod
    def get_user_engagement_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get user engagement metrics"""
        
        # Get orders data for customer engagement
        orders_queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID)
        
        if start_date:
            orders_queryset = orders_queryset.filter(created_at__gte=start_date)
        if end_date:
            orders_queryset = orders_queryset.filter(created_at__lte=end_date)
        
        # Customer purchase statistics
        customers_with_orders = orders_queryset.filter(user__isnull=False).values('user').distinct().count()
        total_customers = User.objects.filter(role=User.ROLE_CUSTOMER, is_guest=False).count()
        
        # Active customers (placed at least one order)
        active_customers = customers_with_orders
        
        # Inactive customers (registered but no orders)
        inactive_customers = total_customers - active_customers
        
        # Repeat customers (more than one order)
        repeat_customers = orders_queryset.filter(user__isnull=False).values('user').annotate(
            order_count=Count('id')
        ).filter(order_count__gt=1).count()
        
        # Customer lifetime value - fix: use proper aggregation
        customer_totals = orders_queryset.filter(user__isnull=False).values('user').annotate(
            total_spent=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )
        
        total_spent_sum = 0
        customer_count = 0
        for ct in customer_totals:
            total_spent_sum += float(ct['total_spent'])
            customer_count += 1
        
        avg_clv = total_spent_sum / customer_count if customer_count > 0 else 0
        
        # Average orders per customer
        customer_order_counts = orders_queryset.filter(user__isnull=False).values('user').annotate(
            order_count=Count('id')
        )
        
        total_orders_count = 0
        for coc in customer_order_counts:
            total_orders_count += coc['order_count']
        
        avg_orders_per_customer = total_orders_count / customer_count if customer_count > 0 else 0
        
        # Guest conversion to registered - fix: cannot use has_usable_password in queryset
        # Get all guest users and manually check password status
        guest_users = User.objects.filter(is_guest=True)
        total_guests = guest_users.count()
        
        # Count converted guests manually
        converted_guests = 0
        for user in guest_users:
            if user.has_usable_password():
                converted_guests += 1
        
        return {
            "customer_engagement": {
                "total_customers": total_customers,
                "active_customers": active_customers,
                "inactive_customers": inactive_customers,
                "active_percentage": round(active_customers / total_customers * 100, 2) if total_customers > 0 else 0,
                "repeat_customers": repeat_customers,
                "repeat_purchase_rate": round(repeat_customers / active_customers * 100, 2) if active_customers > 0 else 0,
            },
            "customer_lifetime_value": {
                "average_clv": round(avg_clv, 2),
                "average_orders_per_customer": round(avg_orders_per_customer, 2),
            },
            "guest_conversion": {
                "total_guests": total_guests,
                "converted_guests": converted_guests,
                "conversion_rate": round(converted_guests / total_guests * 100, 2) if total_guests > 0 else 0,
            }
        }
        
    @staticmethod
    def get_user_geographic_distribution() -> Dict[str, Any]:
        """Get user distribution by country and city from addresses"""
        
        # Get distinct users with addresses
        address_qs = Address.objects.filter(is_active=True).select_related('user')
        
        # Country distribution
        country_distribution = address_qs.values('country').annotate(
            user_count=Count('user', distinct=True)
        ).order_by('-user_count')
        
        # City distribution (top 10)
        city_distribution = address_qs.values('city', 'country').annotate(
            user_count=Count('user', distinct=True)
        ).order_by('-user_count')[:10]
        
        total_users = sum(c['user_count'] for c in country_distribution)
        
        return {
            "by_country": [
                {
                    "country": item['country'] or "Unknown",
                    "user_count": item['user_count'],
                    "percentage": round(item['user_count'] / total_users * 100, 2) if total_users > 0 else 0
                }
                for item in country_distribution
            ],
            "by_city": [
                {
                    "city": item['city'] or "Unknown",
                    "country": item['country'] or "Unknown",
                    "user_count": item['user_count'],
                }
                for item in city_distribution
            ]
        }
    
    @staticmethod
    def get_user_activity_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get user activity analytics (logins, registrations)"""
        
        queryset = User.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Login activity (using last_login field)
        users_with_login = queryset.filter(last_login__isnull=False)
        avg_last_login_days = 0
        if users_with_login.exists():
            now = timezone.now()
            login_days = []
            for user in users_with_login:
                if user.last_login:
                    delta = now - user.last_login
                    login_days.append(delta.days)
            avg_last_login_days = round(sum(login_days) / len(login_days), 2) if login_days else 0
        
        # Recently active (last 7 days)
        seven_days_ago = timezone.now() - timedelta(days=7)
        recently_active = queryset.filter(last_login__gte=seven_days_ago).count()
        
        # Never logged in
        never_logged_in = queryset.filter(last_login__isnull=True).count()
        
        # Registration by hour
        hourly_registration = []
        for hour in range(24):
            count = queryset.filter(created_at__hour=hour).count()
            if count > 0:
                hourly_registration.append({
                    "hour": hour,
                    "display_hour": f"{hour}:00",
                    "registrations": count
                })
        
        # Registration by day of week
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        daily_registration = []
        for idx, day in enumerate(days):
            count = queryset.filter(created_at__week_day=idx + 2).count()
            daily_registration.append({
                "day": day,
                "registrations": count,
                "day_index": idx,
            })
        
        return {
            "login_activity": {
                "average_days_since_last_login": avg_last_login_days,
                "recently_active_7d": recently_active,
                "never_logged_in": never_logged_in,
                "login_percentage": round(users_with_login.count() / queryset.count() * 100, 2) if queryset.count() > 0 else 0,
            },
            "registration_timing": {
                "by_hour": hourly_registration,
                "by_day_of_week": daily_registration,
            }
        }
    
    @staticmethod
    def get_affiliate_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get affiliate performance analytics"""
        
        affiliate_qs = Affiliate.objects.filter(is_active=True)
        
        if start_date:
            affiliate_qs = affiliate_qs.filter(joined_at__gte=start_date)
        if end_date:
            affiliate_qs = affiliate_qs.filter(joined_at__lte=end_date)
        
        # Total affiliates
        total_affiliates = affiliate_qs.count()
        approved_affiliates = affiliate_qs.filter(is_approved=True).count()
        pending_affiliates = affiliate_qs.filter(is_approved=False).count()
        
        # Level distribution
        level_distribution = {}
        for level_code, level_name in Affiliate.LEVEL_CHOICES:
            count = affiliate_qs.filter(level=level_code).count()
            if count > 0:
                level_distribution[level_code] = {
                    "count": count,
                    "name": level_name,
                    "percentage": round(count / total_affiliates * 100, 2) if total_affiliates > 0 else 0
                }
        
        # Earnings summary - fix: use proper aggregation without Avg on aggregate
        total_earnings = affiliate_qs.aggregate(total=Coalesce(Sum('total_earnings'), Decimal('0.00'), output_field=DecimalField()))['total'] or 0
        total_pending = affiliate_qs.aggregate(total=Coalesce(Sum('pending_earnings'), Decimal('0.00'), output_field=DecimalField()))['total'] or 0
        total_paid = affiliate_qs.aggregate(total=Coalesce(Sum('paid_earnings'), Decimal('0.00'), output_field=DecimalField()))['total'] or 0
        total_referrals = affiliate_qs.aggregate(total=Coalesce(Sum('total_referrals'), 0, output_field=IntegerField()))['total'] or 0
        
        avg_earnings = float(total_earnings) / total_affiliates if total_affiliates > 0 else 0
        
        # Top affiliates
        top_affiliates = affiliate_qs.select_related('user').order_by('-total_earnings')[:10]
        top_affiliates_data = []
        for aff in top_affiliates:
            top_affiliates_data.append({
                "affiliate_id": str(aff.id),
                "user_id": str(aff.user.id),
                "email": aff.user.email,
                "name": aff.user.full_name,
                "level": aff.level,
                "total_earnings": float(aff.total_earnings),
                "total_referrals": aff.total_referrals,
                "commission_rate": float(aff.commission_rate),
            })
        
        return {
            "summary": {
                "total_affiliates": total_affiliates,
                "approved_affiliates": approved_affiliates,
                "pending_affiliates": pending_affiliates,
                "approval_rate": round(approved_affiliates / total_affiliates * 100, 2) if total_affiliates > 0 else 0,
            },
            "level_distribution": level_distribution,
            "earnings_summary": {
                "total_earnings": float(total_earnings),
                "total_pending": float(total_pending),
                "total_paid": float(total_paid),
                "total_referrals": total_referrals,
                "average_earnings_per_affiliate": round(avg_earnings, 2),
            },
            "top_affiliates": top_affiliates_data,
        }
    
    @staticmethod
    def get_affiliate_growth_trends(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = 'month'
    ) -> List[Dict[str, Any]]:
        """Get affiliate growth trends"""
        
        queryset = Affiliate.objects.all()
        
        if start_date:
            queryset = queryset.filter(joined_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(joined_at__lte=end_date)
        
        trunc_func = {
            'day': TruncDay,
            'week': TruncWeek,
            'month': TruncMonth,
        }.get(interval, TruncMonth)
        
        trends = queryset.annotate(
            period=trunc_func('joined_at')
        ).values('period').annotate(
            new_affiliates=Count('id'),
            total_earnings=Coalesce(Sum('total_earnings'), Decimal('0.00'), output_field=DecimalField()),
            total_referrals=Coalesce(Sum('total_referrals'), 0, output_field=IntegerField()),
        ).order_by('period')
        
        return [
            {
                "period": item['period'].isoformat() if item['period'] else None,
                "new_affiliates": item['new_affiliates'],
                "total_earnings": float(item['total_earnings']),
                "total_referrals": item['total_referrals'],
            }
            for item in trends
        ]
    
    @staticmethod
    def get_customer_demographics() -> Dict[str, Any]:
        """Get customer demographic analytics"""
        
        # Age distribution from customer profiles
        customer_profiles = CustomerProfile.objects.select_related('user')
        
        age_groups = {
            "18-24": 0,
            "25-34": 0,
            "35-44": 0,
            "45-54": 0,
            "55+": 0,
            "Unknown": 0,
        }
        
        for profile in customer_profiles:
            age = profile.age
            if age:
                if 18 <= age <= 24:
                    age_groups["18-24"] += 1
                elif 25 <= age <= 34:
                    age_groups["25-34"] += 1
                elif 35 <= age <= 44:
                    age_groups["35-44"] += 1
                elif 45 <= age <= 54:
                    age_groups["45-54"] += 1
                elif age >= 55:
                    age_groups["55+"] += 1
            else:
                age_groups["Unknown"] += 1
        
        total_profiles = customer_profiles.count()
        
        # Marketing preferences
        marketing_count = customer_profiles.filter(receive_marketing=True).count()
        newsletter_count = customer_profiles.filter(receive_newsletter=True).count()
        
        # Loyalty points distribution
        total_points = customer_profiles.aggregate(total=Coalesce(Sum('loyalty_points'), 0, output_field=IntegerField()))['total'] or 0
        avg_points = total_points / total_profiles if total_profiles > 0 else 0
        max_points = customer_profiles.aggregate(max=Coalesce(Max('loyalty_points'), 0, output_field=IntegerField()))['max'] or 0
        customers_with_points = customer_profiles.filter(loyalty_points__gt=0).count()
        
        return {
            "age_distribution": [
                {"group": group, "count": count, "percentage": round(count / total_profiles * 100, 2) if total_profiles > 0 else 0}
                for group, count in age_groups.items()
            ],
            "marketing_preferences": {
                "receive_marketing": marketing_count,
                "receive_newsletter": newsletter_count,
                "marketing_percentage": round(marketing_count / total_profiles * 100, 2) if total_profiles > 0 else 0,
                "newsletter_percentage": round(newsletter_count / total_profiles * 100, 2) if total_profiles > 0 else 0,
            },
            "loyalty_program": {
                "total_points": total_points,
                "average_points": round(avg_points, 2),
                "max_points": max_points,
                "customers_with_points": customers_with_points,
            }
        }
    
    @staticmethod
    def get_top_customers_by_spending(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top customers by total spending"""
        
        queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID, user__isnull=False)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Get top customers by total spent
        customer_totals = queryset.values(
            'user__id', 'user__email', 'user__first_name', 'user__last_name'
        ).annotate(
            total_spent=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField()),
            order_count=Count('id'),
            avg_order_value=Coalesce(Avg('total'), Decimal('0.00'), output_field=DecimalField()),
            first_order=Min('created_at'),
            last_order=Max('created_at')
        ).order_by('-total_spent')[:limit]
        
        result = []
        for customer in customer_totals:
            result.append({
                "user_id": str(customer['user__id']),
                "email": customer['user__email'],
                "name": f"{customer['user__first_name'] or ''} {customer['user__last_name'] or ''}".strip() or customer['user__email'],
                "total_spent": float(customer['total_spent']),
                "order_count": customer['order_count'],
                "average_order_value": float(customer['avg_order_value']),
                "first_order": customer['first_order'].isoformat() if customer['first_order'] else None,
                "last_order": customer['last_order'].isoformat() if customer['last_order'] else None,
            })
        
        return result