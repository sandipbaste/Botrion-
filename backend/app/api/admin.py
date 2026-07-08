from fastapi import APIRouter, Depends, HTTPException, Security
from typing import Dict, Any, Optional
from datetime import datetime
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

from app.database.database import db_manager
from app.auth.auth import auth_service
from app.auth.admin_auth import admin_auth_service
from app.auth.addAdmin import CreateAdminRequest, GenerateHashRequest, admin_service
from app.services.payment_service import payment_service
from app.tokens.token_counter import token_counter
from .auth import get_current_admin

router = APIRouter()

@router.get("/users")
async def get_all_users(admin: dict = Depends(get_current_admin)):
    """Get all regular users with subscription info (admin only)"""
    try:
        conn = auth_service.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT u.id, u.email, u.full_name, u.mobile, u.is_active, u.created_at,
                   u.subscription_plan, u.subscription_end_date,
                   (SELECT COUNT(*) FROM websites WHERE user_id = u.id) as website_count
            FROM users u
            ORDER BY u.created_at DESC
        ''')
        
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        
        for user in users:
            user['role'] = 'user'
        
        return {
            "success": True,
            "users": users,
            "count": len(users)
        }
        
    except Exception as e:
        print(f"  Get all users error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admins")
async def get_all_admins(admin: dict = Depends(get_current_admin)):
    """Get all admins"""
    try:
        admins = admin_auth_service.get_all_admins(admin['id'])
        
        return {
            "success": True,
            "admins": admins,
            "count": len(admins)
        }
    except Exception as e:
        print(f"  Get all admins error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/websites")
async def get_all_websites_admin(admin: dict = Depends(get_current_admin)):
    """Get all websites with owner info (admin only)"""
    try:
        conn = auth_service.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT w.*, 
                   u.email as owner_email, 
                   u.full_name as owner_name,
                   u.id as owner_id
            FROM websites w
            LEFT JOIN users u ON w.user_id = u.id
            ORDER BY w.created_at DESC
        ''')
        
        websites = cursor.fetchall()
        cursor.close()
        conn.close()
        
        for website in websites:
            stats = db_manager.get_website_stats(website['website_id'])
            website['contact_forms_count'] = stats.get('contact_forms', 0)
            website['chat_messages_count'] = stats.get('chat_messages', 0)
            website['files_count'] = stats.get('files', 0)
        
        return {
            "success": True,
            "websites": websites,
            "count": len(websites)
        }
    except Exception as e:
        print(f"Error getting all websites admin: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_admin_statistics(admin: dict = Depends(get_current_admin)):
    """Get admin dashboard statistics"""
    try:
        conn = auth_service.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        stats = {}
        
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = TRUE")
        stats['total_users'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM admins WHERE is_active = TRUE")
        stats['total_admins'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM websites")
        stats['total_websites'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM websites WHERE status = 'active'")
        stats['active_websites'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM websites WHERE DATE(created_at) = CURRENT_DATE")
        stats['websites_today'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM contact_forms WHERE DATE(created_at) = CURRENT_DATE")
        stats['forms_today'] = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM chat_history WHERE DATE(created_at) = CURRENT_DATE")
        stats['messages_today'] = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except Exception as e:
        print(f"  Get admin stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-admin")
async def create_admin_user(
    request: CreateAdminRequest,
    admin: dict = Depends(get_current_admin)
):
    """Create a new admin user (admin only)"""
    result = admin_auth_service.create_admin(
        {
            "email": request.email,
            "full_name": request.full_name,
            "password": request.password
        },
        admin['id']
    )
    
    if not result['success']:
        raise HTTPException(
            status_code=400 if result.get('error') == 'Admin already exists with this email' else 500,
            detail=result
        )
    
    return result

@router.post("/generate-hash")
async def generate_password_hash(
    request: GenerateHashRequest,
    admin: dict = Depends(get_current_admin)
):
    """Generate password hash for display purposes (admin only)"""
    result = admin_service.generate_password_hash(request.password)
    
    if not result['success']:
        raise HTTPException(status_code=500, detail=result)
    
    return result

@router.put("/users/{user_id}/toggle")
async def toggle_user_status(
    user_id: int,
    request: Dict[str, Any],
    admin: dict = Depends(get_current_admin)
):
    """Toggle user active status (admin only)"""
    result = auth_service.toggle_user_status(user_id, admin['id'])
    
    if not result['success']:
        raise HTTPException(
            status_code=404 if result.get('error') == 'User not found' else 400,
            detail=result
        )
    
    return result

@router.put("/admins/{admin_id}/toggle")
async def toggle_admin_status(
    admin_id: int,
    admin: dict = Depends(get_current_admin)
):
    """Toggle admin active status"""
    result = admin_auth_service.toggle_admin_status(admin_id, admin['id'])
    
    if not result['success']:
        raise HTTPException(
            status_code=404 if result.get('error') == 'Admin not found' else 400,
            detail=result
        )
    
    return result

@router.get("/user-growth")
async def get_user_growth_data(admin: dict = Depends(get_current_admin)):
    """Get user growth data for charts (admin only)"""
    result = admin_service.get_user_growth_data()
    
    if not result['success']:
        raise HTTPException(status_code=500, detail=result)
    
    return result

@router.get("/subscription-plans")
async def get_all_subscription_plans(admin: dict = Depends(get_current_admin)):
    """Get all subscription plans with admin details (admin only)"""
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('SELECT * FROM subscription_plans ORDER BY price ASC')
        plans = cursor.fetchall()
        
        for plan in plans:
            if plan.get('features'):
                try:
                    if isinstance(plan['features'], str):
                        plan['features'] = json.loads(plan['features'])
                except:
                    plan['features'] = []
            else:
                plan['features'] = []
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "plans": plans,
            "count": len(plans)
        }
        
    except Exception as e:
        print(f"  Get subscription plans error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/subscription-stats")
async def get_subscription_statistics(admin: dict = Depends(get_current_admin)):
    """Get subscription statistics (admin only)"""
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT COUNT(*) as count 
            FROM user_subscriptions 
            WHERE payment_status = 'completed' 
            AND subscription_status = 'active'
            AND (end_date IS NULL OR end_date > CURRENT_TIMESTAMP)
        ''')
        active_subscriptions = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT SUM(amount_paid) as total_revenue 
            FROM user_subscriptions 
            WHERE payment_status = 'completed'
        ''')
        total_revenue = cursor.fetchone()['total_revenue'] or 0
        
        cursor.execute('''
            SELECT sp.plan_name, COUNT(us.id) as subscription_count
            FROM subscription_plans sp
            LEFT JOIN user_subscriptions us ON sp.id = us.plan_id 
                AND us.payment_status = 'completed'
            WHERE sp.is_active = TRUE
            GROUP BY sp.id, sp.plan_name
            ORDER BY sp.price ASC
        ''')
        plan_distribution = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "statistics": {
                "active_subscriptions": active_subscriptions,
                "total_revenue": float(total_revenue),
                "plan_distribution": plan_distribution
            }
        }
        
    except Exception as e:
        print(f"  Get subscription stats error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/token-summary")
async def get_token_summary(
    days: int = 30,
    admin: dict = Depends(get_current_admin)
):
    """Get overall token usage summary (admin only)"""
    try:
        summary = token_counter.get_token_summary(days)
        
        return {
            "success": True,
            "summary": summary
        }
        
    except Exception as e:
        print(f"  Get token summary error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/token/users")
async def get_all_users_token_usage(
    days: int = 30,
    admin: dict = Depends(get_current_admin)
):
    """Get token usage for all users (admin only)"""
    try:
        users = token_counter.get_all_users_token_usage(days)
        
        return {
            "success": True,
            "users": users,
            "count": len(users)
        }
        
    except Exception as e:
        print(f"  Get all users token usage error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )