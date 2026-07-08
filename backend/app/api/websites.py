from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime
import os
import json
import uuid
import shutil

from app.database.database import db_manager
from app.auth.auth import auth_service
from app.vectoredb.embedding_handler import EmbeddingHandler
from app.chatbot_generator import ChatbotGenerator
from app.services.payment_service import payment_service
from .auth import get_current_user, get_current_admin

router = APIRouter()

@router.get("")
async def list_websites():
    """List all trained websites"""
    try:
        websites = db_manager.get_all_websites()
        
        for website in websites:
            website_id = website['website_id']
            website_dir = os.path.join("data", website_id)
            
            if os.path.exists(website_dir):
                info_file = os.path.join(website_dir, "training_info.json")
                if os.path.exists(info_file):
                    try:
                        with open(info_file, 'r') as f:
                            file_info = json.load(f)
                            website.update(file_info)
                    except:
                        pass
                
                embedding_dir = os.path.join(website_dir, "embeddings")
                if os.path.exists(embedding_dir):
                    website['has_embeddings'] = True
                
                script_file = os.path.join("generated_scripts", f"chatbot_{website_id}.js")
                if os.path.exists(script_file):
                    website['has_script'] = True
                    website['script_size'] = os.path.getsize(script_file)
                
                upload_dir = os.path.join(website_dir, "uploads")
                if os.path.exists(upload_dir):
                    uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
                    if os.path.exists(uploads_meta):
                        try:
                            with open(uploads_meta, 'r') as f:
                                uploads = json.load(f)
                                website['uploads_metadata'] = uploads
                                website['upload_count'] = len(uploads)
                        except:
                            website['upload_count'] = 0
                    else:
                        website['upload_count'] = 0
            
            stats = db_manager.get_website_stats(website_id)
            website['stats'] = stats
        
        return {
            "success": True,
            "websites": websites,
            "count": len(websites),
            "trained_count": len([w for w in websites if w.get("status") == "active" or w.get("status") == "completed"]),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"  List websites error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/{website_id}")
async def get_website_info(website_id: str):
    """Get detailed info about a website"""
    try:
        website = db_manager.get_website(website_id)
        
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {website_id} not found."
                }
            )
        
        website_dir = os.path.join("data", website_id)
        if os.path.exists(website_dir):
            info_file = os.path.join(website_dir, "training_info.json")
            if os.path.exists(info_file):
                with open(info_file, 'r') as f:
                    file_info = json.load(f)
                    website.update(file_info)
            
            embedding_dir = os.path.join(website_dir, "embeddings")
            if os.path.exists(embedding_dir):
                website['has_embeddings'] = True
            
            script_file = os.path.join("generated_scripts", f"chatbot_{website_id}.js")
            if os.path.exists(script_file):
                website['has_script'] = True
                website['script_url'] = f"{os.getenv('BACKEND_URL')}/embed/{website_id}/script.js"
                website['embed_code'] = f'<script src="{os.getenv("BACKEND_URL")}/embed/{website_id}/script.js" defer></script>'
            
            upload_dir = os.path.join(website_dir, "uploads")
            if os.path.exists(upload_dir):
                website['has_uploads'] = True
                uploads_meta = os.path.join(upload_dir, "uploads_metadata.json")
                if os.path.exists(uploads_meta):
                    try:
                        with open(uploads_meta, 'r') as f:
                            uploads = json.load(f)
                            website['uploads_metadata'] = uploads
                            website['upload_count'] = len(uploads)
                    except:
                        website['upload_count'] = 0
                else:
                    website['upload_count'] = 0
        
        website['stats'] = db_manager.get_website_stats(website_id)
        website['recent_conversations'] = db_manager.get_conversations(website_id, limit=5)
        website['training_logs'] = db_manager.get_training_logs(website_id, limit=5)
        
        return {
            "success": True,
            **website
        }
        
    except Exception as e:
        print(f"  Get website info error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.get("/stats/{website_id}")
async def get_website_statistics(website_id: str):
    """Get website statistics"""
    try:
        stats = db_manager.get_website_stats(website_id)
        conversations = db_manager.get_conversations(website_id, limit=5)
        training_logs = db_manager.get_training_logs(website_id, limit=3)
        
        return {
            "success": True,
            "website_id": website_id,
            "statistics": stats,
            "recent_conversations": conversations,
            "recent_training_logs": training_logs
        }
    except Exception as e:
        print(f"  Get stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================
# GENERATE SCRIPT FUNCTION - ADD THIS
# =============================================
@router.get("/generate-script/{website_id}")
async def generate_script(website_id: str, user: dict = Depends(get_current_user)):
    """Generate chatbot script for embedding - Qdrant Cloud only"""
    try:
        print(f" Generating script for website: {website_id}")
        
        # Check if website exists in database
        website = db_manager.get_website(website_id)
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {website_id} not found in database."
                }
            )
        
        # Check if user owns this website
        if website.get('user_id') != user['id'] and user.get('role') != 'admin':
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to generate script for this website."
                }
            )
        
        # Check subscription status
        subscription_check = payment_service.check_subscription_active(user['id'])
        
        if not subscription_check['is_active'] and user.get('role') != 'admin':
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Subscription expired",
                    "message": "Your subscription has expired. Please recharge to generate scripts.",
                    "requires_recharge": True
                }
            )
        
        # Check for embeddings in Qdrant Cloud
        try:
            embedding_handler = EmbeddingHandler()
            
            # Use the dedicated method to check embeddings
            has_embeddings = embedding_handler.check_embeddings_exist(website_id)
            
            if not has_embeddings:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": "Embeddings not found",
                        "message": f"No embeddings found in Qdrant Cloud for website '{website.get('website_name', website_id)}'. Please train the website first.",
                        "website_id": website_id,
                        "website_name": website.get('website_name', website_id),
                        "storage": "Qdrant Cloud",
                        "resolution": "Use /api/train endpoint to train the website"
                    }
                )
            
            print(f" Verified embeddings in Qdrant Cloud for website: {website_id}")
            
        except Exception as e:
            print(f"  Error checking Qdrant: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": "Qdrant connection failed",
                    "message": "Something went wrong",
                    "website_id": website_id
                }
            )
        
        # Generate script
        try:
            generator = ChatbotGenerator(base_url=os.getenv("BACKEND_URL"))
            script_path = generator.generate_script_file(website_id)
            script_url = generator.generate_script_url(website_id)
            embed_code = generator.generate_embed_code(website_id)
            
            # Update database with script tag
            db_manager.update_website_script(website_id, embed_code)
            
            # Read script content to verify
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            print(f" Script generated successfully: {script_path}")
            
            return {
                "success": True,
                "message": "Script generated successfully",
                "website_id": website_id,
                "website_name": website.get('website_name', website_id),
                "script_url": script_url,
                "embed_code": embed_code,
                "script_path": script_path,
                "script_size": len(script_content),
                "storage": "Qdrant Cloud",
                "has_embeddings": True,
                "subscription_active": subscription_check.get('is_active', False),
                "minutes_remaining": subscription_check.get('minutes_remaining', 0),
                "instructions": {
                    "step1": "Copy the embed code below",
                    "step2": "Paste it into your website's <head> section",
                    "step3": "The chatbot will appear in the bottom-right corner",
                    "step4": "Click the chat icon to start chatting"
                }
            }
            
        except Exception as e:
            print(f"  Script generation error: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": "Script generation failed",
                    "message": str(e),
                    "website_id": website_id
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Generate script error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.delete("/{website_id}")
async def delete_website(website_id: str, user: dict = Depends(get_current_user)):
    """Delete a trained website and all associated data including Qdrant embeddings"""
    try:
        website = db_manager.get_website(website_id)
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {website_id} not found."
                }
            )
        
        if user.get('role') != 'admin' and website.get('user_id') != user['id']:
            raise HTTPException(
                status_code=403,
                detail={
                    "success": False,
                    "error": "Permission denied",
                    "message": "You don't have permission to delete this website."
                }
            )
        
        # Delete from Qdrant
        try:
            embedding_handler = EmbeddingHandler()
            qdrant_deleted = embedding_handler.delete_website_embeddings(website_id)
            if qdrant_deleted:
                print(f" Successfully deleted Qdrant embeddings for website: {website_id}")
        except Exception as e:
            print(f"  Error deleting Qdrant embeddings: {e}")
        
        # Delete from database
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM websites WHERE website_id = %s", (website_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_error:
            print(f"  Error deleting from database: {db_error}")
        
        # Delete local files
        website_dir = os.path.join("data", website_id)
        if os.path.exists(website_dir):
            try:
                shutil.rmtree(website_dir)
                print(f" Deleted website directory: {website_dir}")
            except Exception as dir_error:
                print(f"  Error deleting website directory: {dir_error}")
        
        script_file = os.path.join("generated_scripts", f"chatbot_{website_id}.js")
        if os.path.exists(script_file):
            try:
                os.remove(script_file)
                print(f" Deleted script file: {script_file}")
            except Exception as script_error:
                print(f"  Error deleting script file: {script_error}")
        
        if user.get('role') != 'admin':
            auth_service.remove_website_from_user(user['id'], website_id)
        
        return {
            "success": True,
            "message": f"Website {website_id} and all associated data deleted successfully",
            "website_id": website_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Delete website error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Deletion failed",
                "message": str(e)
            }
        )