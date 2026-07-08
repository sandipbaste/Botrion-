from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
import os
import uuid
from datetime import datetime

from app.auth.auth import auth_service
from app.auth.admin_auth import admin_auth_service
from app.database.database import db_manager
from app.services.email_service import email_service

router = APIRouter()
security = HTTPBearer()

# Pydantic models
from pydantic import BaseModel

class SignUpModel(BaseModel):
    full_name: str
    email: str
    mobile: Optional[str] = None
    password: str
    confirm_password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UpdateProfile(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None

class ChangePassword(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyOTPRequest(BaseModel):
    reset_token: str
    otp: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str
    confirm_password: str

# Dependencies
def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Get current user from JWT token (checks both users and admins)"""
    token = credentials.credentials
    result = auth_service.verify_token(token)
    if not result['success']:
        raise HTTPException(
            status_code=401,
            detail=result['error']
        )
    
    user_data = result['user']
    user_type = user_data.get('role', 'user')
    user_id = user_data['id']
    
    if user_type == 'admin':
        admin = admin_auth_service.get_admin_by_id(user_id)
        if not admin:
            raise HTTPException(status_code=401, detail="Admin not found")
        return admin
    else:
        user = auth_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

def get_current_admin(user: dict = Depends(get_current_user)):
    """Ensure user is admin"""
    if user.get('role') != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return user

@router.post("/register")
async def register_user(request: SignUpModel):
    """Register a new user"""
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "Passwords do not match"
            }
        )
    
    if len(request.password) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "Password must be at least 6 characters long"
            }
        )
    
    result = auth_service.register_user({
        "full_name": request.full_name,
        "email": request.email,
        "mobile": request.mobile or "",
        "password": request.password
    })
    
    if not result['success']:
        raise HTTPException(
            status_code=400,
            detail=result
        )
    
    # Add a free trial subscription for new users
    try:
        user_id = result['user']['id']
        
        # Create a free trial subscription in the database
        conn = auth_service.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if there's a free plan, or create a trial entry
        cursor.execute("SELECT id FROM subscription_plans WHERE price = 0 LIMIT 1")
        free_plan = cursor.fetchone()
        
        if free_plan:
            plan_id = free_plan['id']
        else:
            # Create a free trial plan if it doesn't exist
            cursor.execute('''
                INSERT INTO subscription_plans 
                (plan_name, plan_description, price, currency, duration_days, 
                 max_websites, max_chat_messages, max_uploads, features, is_active)
                VALUES ('Free Trial', '1 free website trial', 0, 'INR', 30, 1, 100, 5, 
                       '["1 free website", "100 chat messages", "5 file uploads", "Basic support"]'::jsonb, TRUE)
                RETURNING id
            ''')
            plan_id = cursor.fetchone()['id']
        
        # Set trial end date (30 days from now)
        trial_end_date = datetime.now() + timedelta(days=30)
        
        # Insert trial subscription
        cursor.execute('''
            INSERT INTO user_subscriptions 
            (user_id, plan_id, payment_id, amount_paid, currency, 
             payment_status, subscription_status, end_date, sent_reminders)
            VALUES (%s, %s, %s, 0, 'INR', 'completed', 'active', %s, '')
        ''', (user_id, plan_id, f"trial_{user_id}_{int(datetime.now().timestamp())}", trial_end_date))
        
        # Update user with subscription plan
        cursor.execute('''
            UPDATE users 
            SET subscription_plan = 'Free Trial',
                subscription_end_date = %s
            WHERE id = %s
        ''', (trial_end_date, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f" Added free trial for new user: {request.email}")
        result['trial'] = {
            'active': True,
            'end_date': trial_end_date.isoformat(),
            'max_websites': 1,
            'message': 'You have 1 free website trial for 30 days'
        }
        
    except Exception as e:
        print(f"  Error adding free trial: {e}")
        # Continue even if trial creation fails
    
    return result

@router.post("/login")
async def login_user(request: UserLogin):
    """Login user or admin (checks both tables)"""
    admin_result = admin_auth_service.login_admin(request.email, request.password)
    
    if admin_result['success']:
        return admin_result
    
    user_result = auth_service.login_user(request.email, request.password)
    
    if not user_result['success']:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "error": "Invalid credentials",
                "message": "Please check your email and password"
            }
        )
    
    return user_result

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Initiate password reset process"""
    try:
        result = auth_service.initiate_password_reset(request.email)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        otp = result.get('otp')
        
        websites = db_manager.get_all_websites()
        website_id = websites[0]['website_id'] if websites else 'default'
        
        email_service.send_password_reset_otp(
            website_id=website_id,
            user_email=request.email,
            user_name=result['user']['full_name'],
            otp=otp
        )
        
        response_data = {
            "success": True,
            "message": "Password reset initiated. Check your email for OTP.",
            "reset_token": result['reset_token'],
            "expires_in": "10 minutes"
        }
        
        if os.getenv('ENVIRONMENT') == 'development':
            response_data['otp'] = otp
        
        return response_data
        
    except Exception as e:
        print(f"  Forgot password error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.post("/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    """Verify OTP for password reset"""
    try:
        result = auth_service.verify_otp(request.reset_token, request.otp)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return {
            "success": True,
            "message": "OTP verified successfully",
            "reset_token": request.reset_token
        }
        
    except Exception as e:
        print(f"  OTP verification error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Invalid OTP",
                "message": str(e)
            }
        )

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password with new password"""
    try:
        if request.new_password != request.confirm_password:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Passwords do not match"
                }
            )
        
        if len(request.new_password) < 6:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "New password must be at least 6 characters long"
                }
            )
        
        result = auth_service.reset_password(
            request.reset_token,
            request.new_password
        )
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return {
            "success": True,
            "message": "Password reset successfully",
            "user": {
                "email": result['user']['email']
            }
        }
        
    except Exception as e:
        print(f"  Reset password error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/me")
async def get_current_user_profile(user: dict = Depends(get_current_user)):
    """Get current user profile"""
    user_data = auth_service.get_user_by_id(user['id'])
    if not user_data:
        raise HTTPException(
            status_code=404,
            detail={"success": False, "error": "User not found"}
        )
    
    return {
        "success": True,
        "user": user_data
    }

@router.put("/profile")
async def update_user_profile(
    request: UpdateProfile,
    user: dict = Depends(get_current_user)
):
    """Update user profile"""
    result = auth_service.update_user_profile(user['id'], request.dict(exclude_unset=True))
    
    if not result['success']:
        raise HTTPException(
            status_code=400,
            detail=result
        )
    
    return result

@router.put("/change-password")
async def change_password(
    request: ChangePassword,
    user: dict = Depends(get_current_user)
):
    """Change user password"""
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "New passwords do not match"
            }
        )
    
    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "New password must be at least 6 characters long"
            }
        )
    
    result = auth_service.change_password(
        user['id'],
        request.current_password,
        request.new_password
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=400,
            detail=result
        )
    
    return result

@router.post("/logout")
async def logout_user(user: dict = Depends(get_current_user)):
    """Logout user"""
    return {
        "success": True,
        "message": "Logout successful - please remove token from client"
    }