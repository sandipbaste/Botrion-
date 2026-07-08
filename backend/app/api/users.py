from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from app.database.database import db_manager
from app.auth.auth import auth_service
from app.services.payment_service import payment_service
from .auth import get_current_user
from .chat import save_session_data

router = APIRouter()

class UserRegistration(BaseModel):
    full_name: str
    email: str
    mobile: str
    website_id: str

@router.post("/register")
async def register_user(request: UserRegistration):
    """Register user before starting chat"""
    try:
        session_id = str(uuid.uuid4())
        conversation_id = f"conv_{int(datetime.now().timestamp())}"
        
        user_info = {
            "session_id": session_id,
            "full_name": request.full_name,
            "email": request.email,
            "mobile": request.mobile,
            "website_id": request.website_id,
            "registered_at": datetime.now().isoformat(),
            "conversation_id": conversation_id
        }
        
        session_data = {
            "user_info": user_info,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat()
        }
        
        save_session_data(session_id, session_data)
        
        system_message_data = {
            'website_id': request.website_id,
            'conversation_id': conversation_id,
            'session_id': session_id,
            'user_id': '',
            'user_name': request.full_name,
            'user_email': request.email,
            'role': 'system',
            'message': f"User {request.full_name} registered with email {request.email}",
            'metadata': {
                'event': 'user_registration',
                'timestamp': datetime.now().isoformat()
            }
        }
        db_manager.save_chat_message(system_message_data)
        
        website = db_manager.get_website(request.website_id)
        admin_email = website.get('admin_email') if website else None
        
        if admin_email:
            from app.services.email_service import email_service
            email_service.send_registration_notification(
                website_id=request.website_id,
                admin_email=admin_email,
                user_data=user_info
            )
        
        return {
            "success": True,
            "message": "User registered successfully",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_info": {
                "full_name": request.full_name,
                "email": request.email,
                "mobile": request.mobile
            }
        }
        
    except Exception as e:
        print(f"  User registration error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Registration failed",
                "message": str(e)
            }
        )

@router.get("/subscription-status")
async def get_subscription_status(user: dict = Depends(get_current_user)):
    """Get user's subscription status with expiry info"""
    try:
        result = payment_service.check_subscription_active(user['id'])
        
        if not result['success']:
            return {
                "success": False,
                "has_subscription": False,
                "is_active": False,
                "message": "Unable to verify subscription"
            }
        
        has_subscription = result['has_subscription']
        is_active = result['is_active']
        minutes_remaining = result.get('minutes_remaining', 0)
        subscription = result.get('subscription')
        
        notification = None
        if has_subscription and is_active:
            if minutes_remaining <= 55 and minutes_remaining > 0:
                notification = {
                    "show": True,
                    "type": "warning",
                    "message": f"⚠️ Your subscription will expire in {minutes_remaining} minutes.",
                    "action": "recharge",
                    "minutes_remaining": minutes_remaining
                }
            elif minutes_remaining <= 0:
                notification = {
                    "show": True,
                    "type": "danger",
                    "message": "❌ Your subscription has expired.",
                    "action": "recharge",
                    "minutes_remaining": 0
                }
            else:
                notification = {
                    "show": False,
                    "type": "success",
                    "message": f"✅ Subscription active. {minutes_remaining} minutes remaining.",
                    "minutes_remaining": minutes_remaining
                }
        elif not has_subscription:
            notification = {
                "show": True,
                "type": "info",
                "message": "You don't have an active subscription.",
                "action": "subscribe",
                "minutes_remaining": 0
            }
        else:
            notification = {
                "show": False,
                "type": "success",
                "message": "Subscription active",
                "minutes_remaining": minutes_remaining
            }
        
        return {
            "success": True,
            "has_subscription": has_subscription,
            "is_active": is_active,
            "minutes_remaining": minutes_remaining,
            "subscription": subscription,
            "notification": notification
        }
        
    except Exception as e:
        print(f"  Get subscription status error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/notification")
async def get_user_notification(user: dict = Depends(get_current_user)):
    """Get user notification for navbar"""
    try:
        result = payment_service.check_subscription_active(user['id'])
        
        if not result['success']:
            return {
                "success": True,
                "show_notification": False,
                "notification": None
            }
        
        has_subscription = result['has_subscription']
        is_active = result['is_active']
        minutes_remaining = result.get('minutes_remaining', 0)
        subscription = result.get('subscription')
        
        show_notification = False
        notification = None
        
        if has_subscription and is_active and minutes_remaining <= 55 and minutes_remaining > 0:
            show_notification = True
            notification = {
                "type": "warning",
                "message": f"⚠️ Subscription expires in {minutes_remaining} minutes!",
                "details": f"Your {subscription.get('plan_name', '')} plan will expire soon.",
                "action": "recharge",
                "action_text": "Recharge Now",
                "minutes_remaining": minutes_remaining
            }
        elif has_subscription and not is_active and minutes_remaining <= 0:
            show_notification = True
            notification = {
                "type": "danger",
                "message": "❌ Subscription Expired!",
                "details": "Your subscription has expired. Please recharge to continue.",
                "action": "recharge",
                "action_text": "Recharge Now",
                "minutes_remaining": 0
            }
        elif not has_subscription:
            show_notification = True
            notification = {
                "type": "info",
                "message": "No Active Subscription",
                "details": "Subscribe to a plan to start creating AI chatbots.",
                "action": "subscribe",
                "action_text": "Subscribe Now",
                "minutes_remaining": 0
            }
        
        return {
            "success": True,
            "show_notification": show_notification,
            "notification": notification,
            "minutes_remaining": minutes_remaining
        }
        
    except Exception as e:
        print(f"  Get notification error: {e}")
        return {
            "success": False,
            "show_notification": False,
            "notification": None
        }

@router.get("/{website_id}/{session_id}")
async def get_user_info(website_id: str, session_id: str):
    """Get user session information"""
    try:
        from .chat import load_session_data, save_session_data
        
        session_data = load_session_data(session_id)
        
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Session not found",
                    "message": "User session not found or expired"
                }
            )
        
        session_data["last_active"] = datetime.now().isoformat()
        save_session_data(session_id, session_data)
        
        return {
            "success": True,
            "user_info": session_data.get("user_info", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Get user info error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/websites")
async def get_user_websites(user: dict = Depends(get_current_user)):
    """Get all websites for current user"""
    try:
        websites = auth_service.get_user_websites_detailed(user['id'])
        
        return {
            "success": True,
            "websites": websites,
            "count": len(websites)
        }
    except Exception as e:
        print(f"  Get user websites error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/website-ids")
async def get_user_website_ids(user: dict = Depends(get_current_user)):
    """Get user's website IDs list"""
    try:
        user_data = auth_service.get_user_by_id(user['id'])
        if not user_data:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "error": "User not found"}
            )
        
        return {
            "success": True,
            "website_ids": user_data.get('website_ids', []),
            "count": len(user_data.get('website_ids', []))
        }
    except Exception as e:
        print(f"  Get user website IDs error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/stats")
async def get_user_statistics(user: dict = Depends(get_current_user)):
    """Get user statistics"""
    try:
        stats = db_manager.get_user_stats(user['id'])
        
        return {
            "success": True,
            "user_id": user['id'],
            "statistics": stats
        }
    except Exception as e:
        print(f"  Get user stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))