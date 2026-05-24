# apps/users/services/staff_service.py

import logging
from typing import Dict, Any, Optional, Tuple, List
from django.db import transaction
from apps.users.models.user import User
from apps.users.schemas import validate_staff_create

logger = logging.getLogger(__name__)


class StaffService:
    """Service for staff user management"""
    
    @staticmethod
    @transaction.atomic
    def create_staff_user(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Create a new staff or admin user"""
        
        cleaned, errors = validate_staff_create(data)
        if errors:
            return None, errors
        
        if User.objects.filter(email=cleaned["email"]).exists():
            return None, {"email": "User with this email already exists"}
        
        try:
            user = User.objects.create_user(
                email=cleaned["email"],
                password=cleaned["password"],
                first_name=cleaned["first_name"],
                last_name=cleaned["last_name"],
                role=cleaned["role"],
                email_verified=True,  # Staff users are pre-verified
            )
            
            if cleaned.get("phone"):
                user.phone = cleaned["phone"]
                user.save()
            
            logger.info(f"Staff user created: {user.email} (Role: {user.role})")
            
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "role": user.role,
                "is_active": user.is_active,
            }
            
            return user_data, None
            
        except Exception as e:
            logger.error(f"Failed to create staff user: {str(e)}")
            return None, {"general": "Failed to create staff user"}
    
    @staticmethod
    @transaction.atomic
    def bulk_action(action: str, user_ids: List[str], request_user=None) -> Dict:
        """Perform bulk action on staff users"""
        
        results = {"success": [], "failed": [], "total": len(user_ids), "success_count": 0, "failed_count": 0}
        
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id, role__in=['admin', 'staff'])
                
                if action == "activate":
                    user.is_active = True
                    user.save()
                    results["success"].append({"id": str(user.id), "name": user.email})
                    
                elif action == "deactivate":
                    user.is_active = False
                    user.save()
                    results["success"].append({"id": str(user.id), "name": user.email})
                    
                elif action == "delete":
                    if request_user and str(user.id) == str(request_user.id):
                        results["failed"].append({"id": user_id, "name": user.email, "reason": "Cannot delete your own account"})
                        continue
                    user.delete()
                    results["success"].append({"id": str(user.id), "name": user.email})
                    
            except User.DoesNotExist:
                results["failed"].append({"id": user_id, "name": "Unknown", "reason": "User not found"})
            except Exception as e:
                results["failed"].append({"id": user_id, "name": "Unknown", "reason": str(e)})
        
        results["success_count"] = len(results["success"])
        results["failed_count"] = len(results["failed"])
        
        return results