from fastapi import APIRouter, Depends, HTTPException
import os
import json
import uuid
from datetime import datetime

from .auth import router as auth_router
from .chat import router as chat_router
from .contact import router as contact_router
from .payments import router as payments_router
from .training import router as training_router
from .uploads import router as uploads_router
from .users import router as users_router
from .websites import router as websites_router
from .admin import router as admin_router
from .auth import get_current_user
from .users import UserRegistration

api_router = APIRouter()

# Main API routes
api_router.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
api_router.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
api_router.include_router(contact_router, prefix="/api/contact", tags=["Contact"])
api_router.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
api_router.include_router(training_router, prefix="/api/training", tags=["Training"])
api_router.include_router(uploads_router, prefix="/api/uploads", tags=["Uploads"])
api_router.include_router(users_router, prefix="/api/user", tags=["Users"])
api_router.include_router(websites_router, prefix="/api/websites", tags=["Websites"])
api_router.include_router(admin_router, prefix="/api/admin", tags=["Admin"])

# =============================================
# FRONTEND COMPATIBILITY ROUTES
# =============================================

# /api/train -> /api/training/train
api_router.include_router(training_router, prefix="/api", tags=["Training"])

# /api/training-status/{id} -> /api/training/status/{id}
@api_router.get("/api/training-status/{website_id}")
async def training_status_compat(website_id: str):
    from .training import get_training_status
    return await get_training_status(website_id)

# /api/website-uploads/{id} -> /api/uploads/{id}
@api_router.get("/api/website-uploads/{website_id}")
async def website_uploads_compat(website_id: str):
    from .uploads import get_website_uploads
    return await get_website_uploads(website_id)

# /api/website/{id} DELETE -> /api/websites/{id} DELETE
@api_router.delete("/api/website/{website_id}")
async def delete_website_compat(website_id: str, user: dict = Depends(get_current_user)):
    from .websites import delete_website
    return await delete_website(website_id, user)

# /api/delete-file/{id} -> /api/uploads/{id} DELETE
@api_router.delete("/api/delete-file/{website_id}")
async def delete_file_compat(website_id: str, request: dict):
    from .uploads import delete_uploaded_file
    return await delete_uploaded_file(website_id, request, user=Depends(get_current_user))

# /api/reindex/{id} -> /api/uploads/reindex/{id}
@api_router.post("/api/reindex/{website_id}")
async def reindex_compat(website_id: str):
    from .uploads import reindex_with_uploads
    await reindex_with_uploads(website_id)
    return {"success": True, "message": "Reindexing started"}

# /api/generate-script/{id} -> /api/websites/generate-script/{id}
@api_router.get("/api/generate-script/{website_id}")
async def generate_script_compat(website_id: str, user: dict = Depends(get_current_user)):
    from .websites import generate_script
    return await generate_script(website_id, user)

# /api/website/stats/{id} -> /api/websites/stats/{id}
@api_router.get("/api/website/stats/{website_id}")
async def website_stats_compat(website_id: str):
    from .websites import get_website_statistics
    return await get_website_statistics(website_id)

# /api/upload/{id} -> /api/uploads/{id}
@api_router.post("/api/upload/{website_id}")
async def upload_compat(website_id: str, files: list, background_tasks=None, user: dict = Depends(get_current_user)):
    from .uploads import upload_files
    return await upload_files(website_id, files, background_tasks, user)

# =============================================
# REGISTER COMPATIBILITY ROUTE - FIX 404
# =============================================

@api_router.post("/api/register")
async def register_user_compat(request: dict):
    """Register user before starting chat - Compatibility endpoint"""
    try:
        from app.database.database import db_manager
        from app.services.email_service import email_service
        
        full_name = request.get('full_name', '')
        email = request.get('email', '')
        mobile = request.get('mobile', '')
        website_id = request.get('website_id', '')
        
        if not full_name or not email or not mobile:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Missing fields",
                    "message": "Full name, email and mobile are required"
                }
            )
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        conversation_id = f"conv_{int(datetime.now().timestamp())}"
        
        # Store user info
        user_info = {
            "session_id": session_id,
            "full_name": full_name,
            "email": email,
            "mobile": mobile,
            "website_id": website_id,
            "registered_at": datetime.now().isoformat(),
            "conversation_id": conversation_id
        }
        
        # Save session data to file
        session_data = {
            "user_info": user_info,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat()
        }
        
        # Save session file
        session_storage_dir = "user_sessions"
        os.makedirs(session_storage_dir, exist_ok=True)
        session_file = os.path.join(session_storage_dir, f"{session_id}.json")
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        # Save to database
        system_message_data = {
            'website_id': website_id,
            'conversation_id': conversation_id,
            'session_id': session_id,
            'user_id': '',
            'user_name': full_name,
            'user_email': email,
            'role': 'system',
            'message': f"User {full_name} registered with email {email}",
            'metadata': {
                'event': 'user_registration',
                'timestamp': datetime.now().isoformat()
            }
        }
        db_manager.save_chat_message(system_message_data)
        
        # Send notification to admin
        website = db_manager.get_website(website_id)
        admin_email = website.get('admin_email') if website else None
        
        if admin_email:
            email_service.send_registration_notification(
                website_id=website_id,
                admin_email=admin_email,
                user_data=user_info
            )
        
        return {
            "success": True,
            "message": "User registered successfully",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "user_info": {
                "full_name": full_name,
                "email": email,
                "mobile": mobile
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Registration error: {str(e)}")
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