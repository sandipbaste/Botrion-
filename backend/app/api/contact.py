from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from psycopg2.extras import RealDictCursor
from app.database.database import db_manager
from app.services.email_service import email_service
from .auth import get_current_user

router = APIRouter()

class ContactFormRequest(BaseModel):
    website_id: str
    name: str
    email: str
    phone: Optional[str] = None
    message: str
    additional_data: Optional[Dict[str, Any]] = None

@router.post("")
async def submit_contact_form(request: ContactFormRequest):
    """Submit contact form and send email to admin"""
    try:
        form_data = {
            'name': request.name,
            'email': request.email,
            'phone': request.phone,
            'message': request.message,
            'additional_data': request.additional_data
        }
        
        form_id = db_manager.save_contact_form(request.website_id, form_data)
        
        website = db_manager.get_website(request.website_id)
        admin_email = website.get('admin_email') if website else None
        
        if admin_email:
            email_service.send_contact_form_notification(
                website_id=request.website_id,
                admin_email=admin_email,
                form_data=form_data
            )
        
        system_message_data = {
            'website_id': request.website_id,
            'conversation_id': f"contact_{form_id}",
            'role': 'system',
            'message': f"Contact form submitted by {request.name} ({request.email}): {request.message[:100]}...",
            'metadata': {
                'event': 'contact_form',
                'form_id': form_id,
                'admin_notified': admin_email is not None,
                'timestamp': datetime.now().isoformat()
            }
        }
        db_manager.save_chat_message(system_message_data)
        
        return {
            "success": True,
            "message": "Contact form submitted successfully",
            "form_id": form_id,
            "admin_notified": admin_email is not None,
            "website_id": request.website_id
        }
        
    except Exception as e:
        print(f"  Contact form error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Submission failed",
                "message": str(e)
            }
        )

@router.get("/forms/{website_id}")
async def get_contact_forms(
    website_id: str,
    limit: int = 100,
    user: dict = Depends(get_current_user)
):
    """Get contact forms for a website"""
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT * FROM contact_forms WHERE website_id = %s ORDER BY created_at DESC LIMIT %s",
            (website_id, limit)
        )
        forms = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "website_id": website_id,
            "forms": forms,
            "count": len(forms)
        }
    except Exception as e:
        print(f"Error getting contact forms: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/form/{form_id}/status")
async def update_contact_form_status(
    form_id: int,
    request: Dict[str, str],
    user: dict = Depends(get_current_user)
):
    """Update contact form status"""
    try:
        new_status = request.get('status')
        if new_status not in ['pending', 'processed', 'spam']:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE contact_forms SET status = %s WHERE id = %s",
            (new_status, form_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "message": f"Form status updated to {new_status}",
            "form_id": form_id,
            "status": new_status
        }
        
    except Exception as e:
        print(f"Error updating contact form status: {e}")
        raise HTTPException(status_code=500, detail=str(e))