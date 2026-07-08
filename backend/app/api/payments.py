from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from app.services.payment_service import payment_service
from .auth import get_current_user

router = APIRouter()

class CreateOrderRequest(BaseModel):
    plan_id: int

class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str

@router.get("/plans")
async def get_subscription_plans():
    """Get all available subscription plans"""
    try:
        result = payment_service.get_subscription_plans()
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
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

@router.post("/create-order")
async def create_payment_order(
    request: CreateOrderRequest,
    user: dict = Depends(get_current_user)
):
    """Create a payment order for subscription"""
    try:
        result = payment_service.create_payment_order(user['id'], request.plan_id)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Create payment order error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    user: dict = Depends(get_current_user)
):
    """Verify payment and activate subscription"""
    try:
        payment_data = {
            'razorpay_payment_id': request.razorpay_payment_id,
            'razorpay_order_id': request.razorpay_order_id,
            'razorpay_signature': request.razorpay_signature
        }
        
        result = payment_service.verify_payment(payment_data)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Verify payment error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/user-subscription")
async def get_user_subscription(user: dict = Depends(get_current_user)):
    """Get user's active subscription"""
    try:
        result = payment_service.get_user_subscription(user['id'])
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Get user subscription error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/check-access")
async def check_user_access(
    action: str = "train",
    user: dict = Depends(get_current_user)
):
    """Check if user can perform an action based on subscription"""
    try:
        result = payment_service.check_user_access(user['id'], action)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Check user access error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/history")
async def get_payment_history(
    limit: int = 10,
    user: dict = Depends(get_current_user)
):
    """Get user's payment history"""
    try:
        result = payment_service.get_payment_history(user['id'], limit)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Get payment history error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.post("/cancel-subscription/{subscription_id}")
async def cancel_subscription(
    subscription_id: int,
    user: dict = Depends(get_current_user)
):
    """Cancel user subscription"""
    try:
        result = payment_service.cancel_subscription(user['id'], subscription_id)
        
        if not result['success']:
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        return result
        
    except Exception as e:
        print(f"  Cancel subscription error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )