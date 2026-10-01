from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import os
import asyncio
import json
import uuid
import threading
import time
from urllib.parse import urlparse

# ========== ADD THIS IMPORT ==========
import psycopg2
from psycopg2.extras import RealDictCursor
# ====================================

from app.vectoredb.website_loader import WebsiteLoader
from app.vectoredb.embedding_handler import EmbeddingHandler
from app.chatbot_generator import ChatbotGenerator
from app.database.database import db_manager
from app.auth.auth import auth_service
from app.services.payment_service import payment_service
from .auth import get_current_user

router = APIRouter()

# Training status storage
training_status = {}

class TrainRequest(BaseModel):
    website_url: str
    website_name: Optional[str] = None
    contact_email: str
    generate_script: bool = True

def train_website_background(website_id: str, url: str, website_name: str, contact_email: str, should_generate_script: bool, user_id: int):
    """Background task for website training"""
    try:
        print(f" Background training started for {website_id} (User: {user_id})")
        start_time = datetime.now()
        
        training_status[website_id].update({
            "status": "starting",
            "progress": 5,
            "message": "Initializing training process...",
            "updated_at": datetime.now().isoformat()
        })
        
        time.sleep(0.5)
        
        training_status[website_id].update({
            "status": "starting",
            "progress": 8,
            "message": "Preparing to crawl website...",
            "updated_at": datetime.now().isoformat()
        })
        
        # Step 1: Extract website data
        website_loader = WebsiteLoader(max_pages=50, max_depth=3)
        
        training_status[website_id].update({
            "status": "extracting",
            "progress": 10,
            "message": "Starting website crawl...",
            "data_points": 0,
            "updated_at": datetime.now().isoformat()
        })
        
        try:
            website_data = website_loader.extract_website_data(url)
            
            if not website_data:
                raise Exception("No content could be extracted from the website")
            
            pages_extracted = len(website_data)
            
            for i, page in enumerate(website_data):
                if i % 2 == 0:
                    progress = min(40, 8 + ((i + 1) / pages_extracted) * 32)
                    training_status[website_id].update({
                        "status": "extracting",
                        "progress": progress,
                        "message": f"Crawling website: Found {i + 1} pages...",
                        "data_points": i + 1,
                        "updated_at": datetime.now().isoformat()
                    })
                    time.sleep(0.1)
            
            training_status[website_id].update({
                "status": "extracting",
                "progress": 40,
                "message": f"Extracted {pages_extracted} pages from website",
                "data_points": pages_extracted,
                "updated_at": datetime.now().isoformat()
            })
            
            print(f" Successfully extracted {pages_extracted} pages")
            
        except Exception as e:
            error_msg = f"Failed to extract website content: {str(e)}"
            print(f"  {error_msg}")
            
            training_status[website_id] = {
                "website_id": website_id,
                "website_name": website_name,
                "status": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            }
            return
        
        # Step 2: Processing data
        for i in range(1, 11):
            progress = 40 + (i * 2)
            training_status[website_id].update({
                "status": "processing",
                "progress": progress,
                "message": f"Processing extracted content: Step {i}/10...",
                "data_points": pages_extracted,
                "updated_at": datetime.now().isoformat()
            })
            time.sleep(0.3)
        
        # Create website directory
        website_dir = os.path.join("data", website_id)
        os.makedirs(website_dir, exist_ok=True)
        
        training_status[website_id].update({
            "status": "processing",
            "progress": 60,
            "message": "Saving extracted content...",
            "updated_at": datetime.now().isoformat()
        })
        
        data_file = os.path.join(website_dir, "website_data.json")
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(website_data, f, ensure_ascii=False, indent=2)
        
        # Step 3: Creating embeddings
        training_status[website_id].update({
            "status": "embedding",
            "progress": 62,
            "message": "Initializing OpenAI embedding model...",
            "updated_at": datetime.now().isoformat()
        })
        
        time.sleep(0.5)
        
        try:
            embedding_handler = EmbeddingHandler()
            
            for i in range(1, 11):
                progress = 62 + (i * 2.8)
                training_status[website_id].update({
                    "status": "embedding",
                    "progress": min(90, progress),
                    "message": f"Creating embeddings: Chunk {i}/10...",
                    "embedding_count": int((i / 10) * pages_extracted),
                    "updated_at": datetime.now().isoformat()
                })
                time.sleep(0.4)
            
            embedding_info = embedding_handler.create_embeddings(
                website_id, 
                website_data,
                user_id=user_id
            )
            
            training_status[website_id].update({
                "status": "embedding",
                "progress": 90,
                "message": f"Created {pages_extracted} embeddings and stored in Qdrant Cloud",
                "embedding_count": pages_extracted,
                "updated_at": datetime.now().isoformat()
            })
            
            print(f" Created embeddings: {pages_extracted} chunks")
            
        except Exception as e:
            error_msg = "Internal server Error"
            print(f"Failed to create embeddings in Qdrant: {str(e)}")
            
            training_status[website_id] = {
                "website_id": website_id,
                "website_name": website_name,
                "status": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            }
            return
        
        # Step 4: Generate script
        training_status[website_id].update({
            "status": "embedding",
            "progress": 92,
            "message": "Generating chatbot script...",
            "updated_at": datetime.now().isoformat()
        })
        
        time.sleep(0.5)
        
        script_data = {}
        if should_generate_script:
            try:
                training_status[website_id].update({
                    "status": "embedding",
                    "progress": 94,
                    "message": "Creating embed code...",
                    "updated_at": datetime.now().isoformat()
                })
                
                chatbot_generator = ChatbotGenerator(base_url=os.getenv("BACKEND_URL"))
                script_path = chatbot_generator.generate_script_file(website_id)
                
                training_status[website_id].update({
                    "status": "embedding",
                    "progress": 96,
                    "message": "Finalizing script...",
                    "updated_at": datetime.now().isoformat()
                })
                
                script_url = chatbot_generator.generate_script_url(website_id)
                embed_code = chatbot_generator.generate_embed_code(website_id)
                
                script_data = {
                    "script_url": script_url,
                    "embed_code": embed_code,
                    "script_path": script_path,
                    "script_generated": True
                }
                
                db_manager.update_website_script(website_id, embed_code)
                print(f" Generated chatbot script: {script_url}")
                
            except Exception as e:
                print(f" Script generation warning: {e}")
                script_data = {
                    "script_generated": False,
                    "script_error": str(e)
                }
        
        total_training_time = (datetime.now() - start_time).total_seconds()
        
        training_status[website_id].update({
            "status": "embedding",
            "progress": 98,
            "message": "Saving training data...",
            "updated_at": datetime.now().isoformat()
        })
        
        time.sleep(0.3)
        
        # Final status
        training_status[website_id].update({
            "status": "completed",
            "progress": 100,
            "message": "Training completed successfully!",
            "website_id": website_id,
            "website_name": website_name,
            "contact_email": contact_email,
            "website_url": url,
            "data_points": pages_extracted,
            "embedding_info": embedding_info,
            "completed_at": datetime.now().isoformat(),
            "training_time": total_training_time,
            "training_time_formatted": f"{total_training_time:.2f} seconds",
            **script_data
        })
        
        # Save to database
        db_manager.save_training_log(website_id, {
            'status': 'completed',
            'message': 'Training completed successfully',
            'data_points': pages_extracted,
            'embedding_count': pages_extracted,
            'training_time': total_training_time
        })
        
        db_manager.save_website({
            'website_id': website_id,
            'website_name': website_name,
            'website_url': url,
            'admin_email': contact_email,
            'contact_email': contact_email,
            'script_tag': script_data.get('embed_code', ''),
            'status': 'active',
            'user_id': user_id
        })
        
        print(f" Training completed for: {website_name} (ID: {website_id})")
        print(f"      Pages extracted: {pages_extracted}")
        print(f"     Training time: {total_training_time:.2f} seconds")
        
    except Exception as e:
        print(f"  Background training error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        training_status[website_id] = {
            "website_id": website_id,
            "website_name": website_name,
            "status": "error",
            "progress": 0,
            "message": f"Training failed: {str(e)}",
            "error": str(e),
            "completed_at": datetime.now().isoformat()
        }


@router.websocket("/ws/training/{website_id}")
async def training_websocket(websocket: WebSocket, website_id: str):
    await websocket.accept()
    try:
        while True:
            if website_id in training_status:
                status = training_status[website_id]
                await websocket.send_json({
                    "progress": status.get("progress", 0),
                    "status": status.get("status", "starting"),
                    "message": status.get("message", ""),
                    "data_points": status.get("data_points", 0)
                })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for {website_id}")



# ============ MAIN TRAINING ENDPOINT ============
@router.post("/train")
async def train_chatbot(
    request: TrainRequest,
    user: dict = Depends(get_current_user)
):
    """Train chatbot on website URL with contact email"""
    try:
        print(f" Training request for user {user['id']} ({user.get('email')})")
        
        # ========== CHECK SUBSCRIPTION ==========
        subscription_result = payment_service.check_subscription_active(user['id'])
        
        print(f" Subscription result: {subscription_result}")
        
        # Check if user has active subscription
        has_active_subscription = subscription_result.get('is_active', False)
        has_subscription = subscription_result.get('has_subscription', False)
        
        # Check website count - FIX: Use db_manager instead of direct connection
        websites = db_manager.get_user_websites(user['id'])
        website_count = len(websites)
        
        print(f" User has {website_count} websites, Active subscription: {has_active_subscription}")
        
        # If user has active subscription, check website limit
        if has_active_subscription:
            subscription = subscription_result.get('subscription', {})
            max_websites = subscription.get('max_websites', 1)
            
            if website_count >= max_websites:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "success": False,
                        "error": "Chatbot limit reached",
                        "message": f"You have reached the maximum limit of {max_websites} chatbots for your plan. Please upgrade your plan to add more chatbots.",
                        "max_allowed": max_websites,
                        "current_count": website_count,
                        "requires_upgrade": True
                    }
                )
            
            print(f" Active subscription, website count {website_count}/{max_websites}")
        
        elif has_subscription and not has_active_subscription:
            # Subscription exists but expired
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Subscription expired",
                    "message": "Your subscription has expired. Please recharge to continue.",
                    "requires_recharge": True,
                    "has_subscription": True,
                    "is_active": False,
                    "minutes_remaining": subscription_result.get('minutes_remaining', 0)
                }
            )
        
        else:
            # No subscription - allow first website for free (trial)
            if website_count >= 1:
                # User already has a website, needs subscription
                raise HTTPException(
                    status_code=403,
                    detail={
                        "success": False,
                        "error": "Subscription required",
                        "message": "You need an active subscription to create more chatbots. Please subscribe to a plan.",
                        "requires_subscription": True,
                        "has_subscription": False,
                        "current_count": website_count,
                        "free_limit": 1
                    }
                )
            else:
                # First website - allow for free (trial)
                print(f" User {user['id']} is creating their first website (free trial)")
                # Continue with training (no subscription check)
        
        # ========== VALIDATE URL ==========
        if not request.website_url.startswith(('http://', 'https://')):
            request.website_url = 'https://' + request.website_url
        
        # ========== GENERATE WEBSITE ID ==========
        website_id = str(uuid.uuid4())[:8]
        
        if request.website_name:
            website_name = request.website_name
        else:
            parsed = urlparse(request.website_url)
            website_name = parsed.netloc or request.website_url
            
        website_name = "".join(c for c in website_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        if not request.contact_email or '@' not in request.contact_email:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Invalid contact email",
                    "message": "Please provide a valid contact email address"
                }
            )
        
        # ========== SET INITIAL STATUS ==========
        training_status[website_id] = {
            "website_id": website_id,
            "website_name": website_name,
            "website_url": request.website_url,
            "contact_email": request.contact_email,
            "user_id": user['id'],
            "status": "starting",
            "progress": 0,
            "message": "Initializing training process...",
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "is_trial": not has_active_subscription and website_count == 0
        }
        
        # ========== CREATE DIRECTORIES ==========
        website_dir = os.path.join("data", website_id)
        os.makedirs(website_dir, exist_ok=True)
        
        upload_dir = os.path.join(website_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # ========== SAVE TO DATABASE ==========
        website_data = {
            'website_id': website_id,
            'website_name': website_name,
            'website_url': request.website_url,
            'admin_email': request.contact_email,
            'contact_email': request.contact_email,
            'data_directory': website_dir,
            'status': 'training',
            'user_id': user['id']
        }
        
        db_manager.save_website_with_user(website_data, user['id'])
        db_manager.save_training_log(website_id, {
            'status': 'started',
            'message': 'Training started',
            'data_points': 0,
            'user_id': user['id']
        })
        
        auth_service.add_website_to_user(user['id'], website_id)
        
        # ========== START TRAINING IN BACKGROUND ==========
        thread = threading.Thread(
            target=train_website_background,
            args=(website_id, request.website_url, website_name, request.contact_email, request.generate_script, user['id']),
            daemon=True
        )
        thread.start()
        
        # ========== RETURN RESPONSE ==========
        return {
            "success": True,
            "message": "Training started successfully!",
            "website_id": website_id,
            "website_name": website_name,
            "website_url": request.website_url,
            "contact_email": request.contact_email,
            "status_url": f"/api/training/status/{website_id}",
            "upload_url": f"/api/uploads/{website_id}",
            "estimated_time": "2-3 minutes",
            "polling_interval": 2000,
            "is_trial": not has_active_subscription and website_count == 0,
            "trial_message": "This is your free trial website. Subscribe to create more chatbots." if not has_active_subscription and website_count == 0 else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Training initialization error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Training failed to start",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )
        

# @router.get("/training-status/{website_id}")
# async def training_status_compat(website_id: str):
#     """Compatibility endpoint for /api/training-status/{website_id}"""
#     return await get_training_status(website_id)      
      
      
# ============ TRAINING STATUS ENDPOINTS ============
# For /api/training/status/{website_id}
# @router.get("/status/{website_id}")
# async def get_training_status(website_id: str):
#     """Get training status for a website"""
#     try:
#         if website_id not in training_status:
#             website_dir = os.path.join("data", website_id)
#             if os.path.exists(website_dir):
#                 info_file = os.path.join(website_dir, "training_info.json")
#                 if os.path.exists(info_file):
#                     with open(info_file, 'r', encoding='utf-8') as f:
#                         status_info = json.load(f)
                    
#                     if 'progress' not in status_info:
#                         if status_info.get('status') == 'completed':
#                             status_info['progress'] = 100
#                         elif status_info.get('status') == 'error':
#                             status_info['progress'] = 0
#                         else:
#                             status_info['progress'] = 50
                    
#                     return {
#                         "success": True,
#                         **status_info
#                     }
            
#             return {
#                 "success": False,
#                 "error": "Training not found",
#                 "message": f"No training found for website ID: {website_id}",
#                 "timestamp": datetime.now().isoformat()
#             }
        
#         status = training_status[website_id].copy()
        
#         if status.get('progress') is None:
#             if status.get('status') == 'completed':
#                 status['progress'] = 100
#             elif status.get('status') == 'error':
#                 status['progress'] = 0
#             else:
#                 status['progress'] = 50
        
#         return {
#             "success": True,
#             **status
#         }
        
#     except Exception as e:
#         print(f"  Training status error: {str(e)}")
#         return {
#             "success": False,
#             "error": "Internal server error",
#             "message": str(e),
#             "timestamp": datetime.now().isoformat()
#         }


# ============ COMPATIBILITY ROUTES FOR FRONTEND ============
# Frontend calls /api/training-status/{website_id}
# So we need to add this route
# @router.get("/training-status/{website_id}")
# async def get_training_status_compat(website_id: str):
#     """Compatibility endpoint for /api/training-status/{website_id}"""
#     return await get_training_status(website_id)   



def _status_from_db(website_id: str, user_id: int):
    """Status is kept in memory only. If it is gone (restart/crash), use the DB row."""
    try:
        for site in db_manager.get_user_websites(user_id) or []:
            if site.get("website_id") != website_id:
                continue
            db_status = str(site.get("status") or "").lower()
            if db_status in ("active", "completed", "trained"):
                return {"success": True, "website_id": website_id,
                        "website_name": site.get("website_name"),
                        "status": "completed", "progress": 100,
                        "message": "Training completed successfully!"}
            return {"success": True, "website_id": website_id,
                    "website_name": site.get("website_name"),
                    "status": "error", "progress": 0,
                    "message": "Training did not finish (server restarted or failed). Please delete this chatbot and train again."}
    except Exception as e:
        print(f"Status DB fallback error: {e}")
    return None


def _build_status(website_id: str, user_id: int):
    status = training_status.get(website_id)
    if status is not None:
        if status.get("user_id") not in (None, user_id):
            return {"success": False, "error": "Training not found",
                    "message": f"No training found for website ID: {website_id}"}
        status = status.copy()
        if status.get("progress") is None:
            status["progress"] = 100 if status.get("status") == "completed" else (0 if status.get("status") == "error" else 50)
        return {"success": True, **status}

    from_db = _status_from_db(website_id, user_id)
    if from_db:
        return from_db
    return {"success": False, "error": "Training not found",
            "message": f"No training found for website ID: {website_id}",
            "timestamp": datetime.now().isoformat()}


@router.get("/status/{website_id}")
async def get_training_status(website_id: str, user: dict = Depends(get_current_user)):
    return _build_status(website_id, user["id"])


@router.get("/wait/{website_id}")
async def wait_for_training(website_id: str, timeout: int = 25, user: dict = Depends(get_current_user)):
    """Long-poll: hold the request until training finishes/fails, or timeout."""
    deadline = time.time() + max(1, min(timeout, 55))
    while time.time() < deadline:
        status = training_status.get(website_id)
        if status is None or status.get("status") in ("completed", "error"):
            break
        await asyncio.sleep(1)
    return _build_status(website_id, user["id"])


@router.get("/training-status/{website_id}")
async def training_status_compat(website_id: str, user: dict = Depends(get_current_user)):
    return _build_status(website_id, user["id"])   
        
        