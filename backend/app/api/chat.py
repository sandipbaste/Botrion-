from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
import json
import uuid
import asyncio
import httpx

from app.database.database import db_manager
from app.services.email_service import email_service
from app.services.payment_service import payment_service
from app.agents.agents import ChatAgent
from .auth import get_current_user

router = APIRouter()

class ChatRequest(BaseModel):
    website_id: str
    question: str
    conversation_id: Optional[str] = None
    user_info: Optional[Dict[str, str]] = None
    session_id: Optional[str] = None

class SendChatReportRequest(BaseModel):
    website_id: str
    conversation_id: str

class EndSessionRequest(BaseModel):
    session_id: str

# Session storage
session_storage_dir = "user_sessions"
os.makedirs(session_storage_dir, exist_ok=True)
auto_reported_sessions = set()

def save_session_data(session_id: str, session_data: Dict[str, Any]):
    """Save session data to file"""
    session_file = os.path.join(session_storage_dir, f"{session_id}.json")
    try:
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  Error saving session data: {e}")

def load_session_data(session_id: str) -> Optional[Dict[str, Any]]:
    """Load session data from file"""
    session_file = os.path.join(session_storage_dir, f"{session_id}.json")
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  Error loading session data: {e}")
    return None

def delete_session_data(session_id: str):
    """Delete session data file"""
    session_file = os.path.join(session_storage_dir, f"{session_id}.json")
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
        except Exception as e:
            print(f"  Error deleting session data: {e}")

@router.post("")
async def chat_with_website(request: ChatRequest):
    """Chat with website chatbot - Qdrant Cloud only"""
    try:
        print(f" Chat request for website: {request.website_id}, "
              f"question: {request.question[:50]}...")
        
        website = db_manager.get_website(request.website_id)
        
        if not website:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Website not found",
                    "message": f"Website with ID {request.website_id} not found."
                }
            )
        
        # Subscription check
        user_id = website.get('user_id')
        
        if user_id:
            subscription_check = payment_service.check_subscription_active(user_id)
            
            if not subscription_check['success'] or not subscription_check['is_active']:
                expiry_message = f"⚠️ **Your subscription has expired.**\n\nPlease recharge to continue using the AI assistant."
                
                if request.conversation_id:
                    try:
                        expiry_data = {
                            'website_id': request.website_id,
                            'conversation_id': request.conversation_id,
                            'session_id': request.session_id,
                            'user_name': request.user_info.get('full_name', '') if request.user_info else '',
                            'user_email': request.user_info.get('email', '') if request.user_info else '',
                            'role': 'assistant',
                            'message': expiry_message,
                            'metadata': {
                                'subscription_expired': True,
                                'timestamp': datetime.now().isoformat(),
                                'user_id': user_id
                            }
                        }
                        db_manager.save_chat_message(expiry_data)
                    except Exception as e:
                        print(f"  Failed to save expiry message: {e}")
                
                return {
                    "success": True,
                    "website_id": request.website_id,
                    "conversation_id": request.conversation_id or f"conv_{int(datetime.now().timestamp())}",
                    "question": request.question,
                    "response": expiry_message,
                    "timestamp": datetime.now().isoformat(),
                    "subscription_expired": True
                }
        
        # Check embeddings in Qdrant
        try:
            from app.vectoredb.embedding_handler import EmbeddingHandler
            embedding_handler = EmbeddingHandler()
            has_embeddings = embedding_handler.check_embeddings_exist(request.website_id)
            
            if not has_embeddings:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "success": False,
                        "error": "Embeddings not found",
                        "message": "No embeddings found in Qdrant Cloud. Please train the website first."
                    }
                )
            
            print(f" Verified embeddings in Qdrant Cloud for website: {request.website_id}")
            
        except Exception as e:
            print(f"  Error checking Qdrant: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "success": False,
                    "error": "Qdrant connection failed",
                    "message": f" {str(e)}"
                }
            )
        
        # Process chat
        session_data = None
        if request.session_id:
            session_data = load_session_data(request.session_id)
            if session_data:
                session_data["last_active"] = datetime.now().isoformat()
                session_data["messages"].append({
                    'role': 'user',
                    'message': request.question,
                    'timestamp': datetime.now().isoformat()
                })
                save_session_data(request.session_id, session_data)
        
        try:
            chat_agent = ChatAgent()
            # Use asyncio timeout to prevent hanging
            response = await asyncio.wait_for(
                chat_agent.chat(
                    question=request.question,
                    website_id=request.website_id,
                    conversation_id=request.conversation_id,
                    user_info=request.user_info,
                    session_id=request.session_id,
                    user_id=user_id
                ),
                timeout=10.0  # 10 second timeout
            )
        except asyncio.TimeoutError:
            response = "I'm processing your request. Please wait a moment."
            
            try:
                from app.vectoredb.embedding_handler import EmbeddingHandler
                handler = EmbeddingHandler()
                search_results = handler.search_similar_content(
                    website_id=request.website_id,
                    query=request.question,
                    top_k=3
                )
                
                if search_results:
                    context = "\n\n".join([f"Content: {r['text'][:500]}..." for r in search_results])
                    response = f"Based on your website content: {context[:200]}..."
                else:
                    response = "I'm your AI assistant. How can I help you today?"
                    
            except Exception as search_error:
                print(f" Direct search error: {search_error}")
                response = "I'm your AI assistant. How can I help you today?"
            
            # Save to database for fallback
            if request.conversation_id:
                user_message_data = {
                    'website_id': request.website_id,
                    'conversation_id': request.conversation_id,
                    'session_id': request.session_id,
                    'user_id': str(user_id) if user_id else '',
                    'user_name': request.user_info.get('full_name', '') if request.user_info else '',
                    'user_email': request.user_info.get('email', '') if request.user_info else '',
                    'role': 'user',
                    'message': request.question,
                    'metadata': {
                        'timestamp': datetime.now().isoformat()
                    }
                }
                db_manager.save_chat_message(user_message_data)
                
                bot_message_data = {
                    'website_id': request.website_id,
                    'conversation_id': request.conversation_id,
                    'session_id': request.session_id,
                    'user_name': request.user_info.get('full_name', '') if request.user_info else '',
                    'user_email': request.user_info.get('email', '') if request.user_info else '',
                    'role': 'assistant',
                    'message': response,
                    'metadata': {
                        'timestamp': datetime.now().isoformat(),
                        'response_length': len(response)
                    }
                }
                db_manager.save_chat_message(bot_message_data)
        
        if session_data:
            session_data["messages"].append({
                'role': 'assistant',
                'message': response,
                'timestamp': datetime.now().isoformat()
            })
            save_session_data(request.session_id, session_data)
        
        print(f" Chat response generated ({len(response)} chars)")
        
        return {
            "success": True,
            "website_id": request.website_id,
            "conversation_id": request.conversation_id or f"conv_{int(datetime.now().timestamp())}",
            "question": request.question,
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "response_length": len(response)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Chat error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Chat failed",
                "message": str(e)
            }
        )

@router.get("/history/{website_id}")
async def get_chat_history(website_id: str, conversation_id: Optional[str] = None, limit: int = 50):
    """Get chat history for website or conversation"""
    try:
        if conversation_id:
            history = db_manager.get_chat_history(website_id, conversation_id, limit)
        else:
            history = db_manager.get_chat_history(website_id, limit=limit)
        
        return {
            "success": True,
            "website_id": website_id,
            "conversation_id": conversation_id,
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        print(f"  Get chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-report")
async def send_chat_report(request: SendChatReportRequest):
    """Send chat history report to admin"""
    try:
        chat_history = db_manager.get_full_conversation(request.conversation_id)
        
        if not chat_history:
            raise HTTPException(
                status_code=404,
                detail="No chat history found for this conversation"
            )
        
        website = db_manager.get_website(request.website_id)
        if not website:
            raise HTTPException(
                status_code=404,
                detail="Website not found"
            )
        
        user_info = {}
        for message in chat_history:
            if message.get('user_name'):
                user_info = {
                    'full_name': message.get('user_name', 'Unknown'),
                    'email': message.get('user_email', 'Unknown'),
                    'mobile': message.get('user_phone', 'Unknown')
                }
                break
        
        admin_email = website.get('admin_email')
        
        if admin_email:
            email_service.send_chat_session_report(
                website_id=request.website_id,
                admin_email=admin_email,
                conversation_id=request.conversation_id,
                chat_history=chat_history,
                user_info=user_info
            )
        
        system_message_data = {
            'website_id': request.website_id,
            'conversation_id': request.conversation_id,
            'role': 'system',
            'message': f"Chat history report sent to {admin_email}",
            'metadata': {
                'event': 'chat_report',
                'admin_email': admin_email,
                'message_count': len(chat_history),
                'timestamp': datetime.now().isoformat()
            }
        }
        db_manager.save_chat_message(system_message_data)
        
        return {
            "success": True,
            "admin_notified": admin_email is not None,
            "admin_email": admin_email,
            "conversation_id": request.conversation_id,
            "message_count": len(chat_history),
            "website_id": request.website_id
        }
        
    except Exception as e:
        print(f"  Send chat report error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/end-session")
async def end_chat_session(request: EndSessionRequest):
    """End chat session and send report to admin"""
    try:
        session_id = request.session_id
        
        session_data = load_session_data(session_id)
        
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Session not found",
                    "message": "Chat session not found"
                }
            )
        
        user_info = session_data.get("user_info", {})
        website_id = user_info.get("website_id")
        conversation_id = user_info.get("conversation_id")
        chat_history = db_manager.get_chat_history(
            website_id=website_id,
            conversation_id=conversation_id,
            limit=100
        )
        
        if not website_id or not conversation_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid session data",
                    "message": "Missing website ID or conversation ID"
                }
            )
        
        website = db_manager.get_website(website_id)
        admin_email = website.get('admin_email') if website else None
        
        if admin_email and chat_history:
            email_service.send_chat_session_report(
                website_id=website_id,
                admin_email=admin_email,
                conversation_id=conversation_id,
                chat_history=chat_history,
                user_info=user_info
            )
        
        delete_session_data(session_id)
        
        return {
            "success": True,
            "message": "Chat session ended and report sent to admin",
            "session_id": session_id,
            "messages_count": len(chat_history) if chat_history else 0,
            "admin_notified": admin_email is not None,
            "admin_email": admin_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  End chat session error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

@router.post("/auto-report")
async def auto_report_chat_session(session_id: str = Form(...)):
    """Auto-report chat session when browser closes/refreshes"""
    try:
        print(f" Auto-report triggered for session: {session_id}")
        
        if session_id in auto_reported_sessions:
            print(f" Session {session_id} already auto-reported, skipping duplicate")
            return {
                "success": True,
                "message": "Session already reported",
                "already_reported": True
            }
        
        session_data = load_session_data(session_id)
        
        if not session_data:
            chat_history = db_manager.get_chat_history_by_session(session_id, limit=100)
            
            if not chat_history:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "Session not found",
                        "message": f"No chat history found for session: {session_id}"
                    }
                )
            
            website_id = chat_history[0].get('website_id') if chat_history else None
            conversation_id = chat_history[0].get('conversation_id') if chat_history else None
            
            if not website_id or not conversation_id:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "Invalid session data",
                        "message": "Missing website ID or conversation ID"
                    }
                )
            
            user_info = {}
            for message in chat_history:
                if message.get('user_name'):
                    user_info = {
                        'full_name': message.get('user_name', 'Unknown'),
                        'email': message.get('user_email', 'Unknown'),
                        'mobile': message.get('user_phone', 'Unknown')
                    }
                    break
        else:
            user_info = session_data.get("user_info", {})
            website_id = user_info.get("website_id")
            conversation_id = user_info.get("conversation_id")
            chat_history = db_manager.get_chat_history(
                website_id=website_id,
                conversation_id=conversation_id,
                limit=100
            )
        
        if not website_id or not conversation_id:
            delete_session_data(session_id)
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Invalid session data",
                    "message": "Missing website ID or conversation ID"
                }
            )
        
        if not chat_history or len(chat_history) < 2:
            delete_session_data(session_id)
            return {
                "success": True,
                "message": "No significant chat history to report",
                "session_id": session_id,
                "messages_count": len(chat_history) if chat_history else 0
            }
        
        website = db_manager.get_website(website_id)
        admin_email = website.get('admin_email') if website else None
        
        print(f" Website admin_email: {admin_email}")
        print(f" Session user email: {user_info.get('email')}")
        
        if admin_email and chat_history:
            email_service.send_chat_session_report(
                website_id=website_id,
                admin_email=admin_email,
                conversation_id=conversation_id,
                chat_history=chat_history,
                user_info=user_info,
                is_auto_report=True
            )
            
            print(f" Auto-sent chat report for session: {session_id} to {admin_email}")
            
            auto_reported_sessions.add(session_id)
            
            system_message_data = {
                'website_id': website_id,
                'conversation_id': conversation_id,
                'user_id': '',
                'user_name': user_info.get('full_name', ''),
                'user_email': user_info.get('email', ''),
                'role': 'system',
                'message': f'Chat session auto-reported (browser closed/refreshed) to {admin_email}',
                'metadata': {
                    'event': 'auto_report',
                    'session_id': session_id,
                    'admin_email': admin_email,
                    'message_count': len(chat_history),
                    'timestamp': datetime.now().isoformat(),
                    'reported_once': True
                }
            }
            db_manager.save_chat_message(system_message_data)
        else:
            print(f" No admin email found for website {website_id}")
        
        delete_session_data(session_id)
        
        return {
            "success": True,
            "message": "Chat session auto-reported successfully",
            "session_id": session_id,
            "messages_count": len(chat_history) if chat_history else 0,
            "admin_notified": admin_email is not None,
            "admin_email": admin_email,
            "already_reported": False
        }
        
    except Exception as e:
        print(f"  Auto-report error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
    
    async def send_message(self, message: str, session_id: str):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(message)

manager = ConnectionManager()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id)
        
        if session_id in auto_reported_sessions:
            print(f" Session {session_id} already reported, skipping WebSocket auto-report")
            return
        
        try:
            await asyncio.sleep(1)
            
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.post(
                        f"{os.getenv('BACKEND_URL')}/api/chat/auto-report",
                        data={"session_id": session_id}
                    )
                    if response.status_code == 200:
                        response_data = response.json()
                        if response_data.get('already_reported'):
                            print(f" WebSocket auto-report skipped (already reported) for session: {session_id}")
                        else:
                            print(f" WebSocket auto-report successful for session: {session_id}")
                    else:
                        print(f" WebSocket auto-report failed: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f" WebSocket auto-report HTTP error: {e}")
            
            print(f" Auto-report triggered for session: {session_id}")
        except Exception as e:
            print(f" Error in WebSocket auto-report: {e}")