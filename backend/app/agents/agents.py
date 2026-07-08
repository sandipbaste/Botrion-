import os
import json
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage

# Import database and email services
from app.database.database import db_manager
from app.services.email_service import email_service
from app.tokens.token_counter import token_counter
from app.vectoredb.embedding_handler import EmbeddingHandler
from app.services.payment_service import payment_service

# Import modular components
from app.core.llm import LLMManager
from app.graph.state import ChatState
from app.graph.graph import ChatGraph
from app.memory.redis import RedisMemory, RedisCheckpointSaver

FRONTEND_URL = os.getenv("FRONTEND_URL").rstrip('/')

class ChatAgent:
    def __init__(self):
        # Initialize LLM
        self.llm_manager = LLMManager()
        
        # Initialize embedding handler
        self.embedding_handler = EmbeddingHandler()
        
        # Initialize Redis
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL not found in environment variables")
        
        # Initialize Redis client
        self.redis_client = RedisMemory.init_redis_client(redis_url)
        
        # Initialize Redis memory
        self.redis_memory = RedisMemory(self.redis_client)
        
        # Initialize Redis checkpointer
        self.checkpointer = RedisCheckpointSaver(self.redis_client)
        
        # Initialize chat graph with redis_memory for summary support
        self.chat_graph = ChatGraph(
            embedding_handler=self.embedding_handler,
            llm=self.llm_manager,
            checkpointer=self.checkpointer,
            redis_memory=self.redis_memory
        )
        
        # Keep graph reference for backward compatibility
        self.graph = self.chat_graph.graph
        
        print("Production Redis initialized successfully with summary agent")
    
    def check_subscription_for_user(self, user_id: Optional[int]) -> Dict[str, Any]:
        """Check if user has active subscription for AI functionality"""
        if not user_id:
            return {
                "has_access": True,
                "is_expired": False,
                "message": None
            }
        
        # user_id is already int here
        subscription_result = payment_service.check_subscription_active(user_id)
        
        if not subscription_result['success']:
            return {
                "has_access": False,
                "is_expired": True,
                "message": f"❌ Your subscription has expired. Please recharge to continue using the AI assistant.\n\n[Click here to recharge]({FRONTEND_URL}/pricing)"
            }
        
        if not subscription_result['has_subscription']:
            return {
                "has_access": False,
                "is_expired": True,
                "message": f"❌ Your subscription has expired. Please recharge to continue using the AI assistant.\n\n[Click here to recharge]({FRONTEND_URL}/pricing)"
            }
        
        if not subscription_result['is_active'] or subscription_result.get('minutes_remaining', 0) <= 0:
            return {
                "has_access": False,
                "is_expired": True,
                "message": f"❌ Your subscription has expired. Please recharge to continue using the AI assistant.\n\n[Click here to recharge]({FRONTEND_URL}/pricing)"
            }
        
        return {
            "has_access": True,
            "is_expired": False,
            "message": None,
            "minutes_remaining": subscription_result.get('minutes_remaining', 0)
        }
    
    
    async def chat(
        self,
        question: str,
        website_id: str,
        conversation_id: str = None,
        user_info: Dict[str, str] = None,
        session_id: str = None,
        user_id: str = None
    ) -> str:
        """Main chat method with subscription check"""
        print(f"\n Chat request for website: {website_id}, question: {question[:50]}...")
        
        # Convert user_id to int for subscription check
        user_id_int = int(user_id) if user_id else None
        
        # Check subscription status
        subscription_check = self.check_subscription_for_user(user_id_int)
        
        # If subscription expired, return expiry message
        if not subscription_check['has_access']:
            expiry_message = subscription_check['message']
            print(f" Subscription expired for user {user_id}")
            
            if conversation_id:
                try:
                    system_message_data = {
                        'website_id': website_id,
                        'conversation_id': conversation_id,
                        'session_id': session_id,
                        'user_id': str(user_id) if user_id else '',
                        'user_name': user_info.get('full_name', '') if user_info else '',
                        'user_email': user_info.get('email', '') if user_info else '',
                        'role': 'assistant',
                        'message': expiry_message,
                        'metadata': {
                            'timestamp': datetime.now().isoformat(),
                            'subscription_expired': True,
                            'user_id': str(user_id) if user_id else None
                        }
                    }
                    db_manager.save_chat_message(system_message_data)
                except Exception as e:
                    print(f"  Failed to save expiry message: {e}")
            
            return expiry_message
        
        print(f" Subscription active for user {user_id}")
        
        # Generate conversation ID if not provided
        if not conversation_id:
            conversation_id = f"conv_{int(datetime.now().timestamp())}"
            print(f" Generated new conversation_id: {conversation_id}")
        
        config = {
            "configurable": {"thread_id": conversation_id},
            "metadata": {"thread_id": conversation_id},
            "run_name": "chat_turn",
        }
        
        try:
            # Load ALL messages from Redis (no time limit, get all)
            redis_messages = self.redis_memory.get_messages(
                website_id, 
                conversation_id, 
                user_id=str(user_id) if user_id else None,  # Ensure user_id is string
                limit=100, 
                hours=720  # 30 days
            )
            
            print(f" Loaded {len(redis_messages)} messages from Redis for conversation: {conversation_id}")
            
            # Convert Redis messages to LangChain message objects
            all_messages = []
            for msg in redis_messages:
                content = msg.get('content', msg.get('message', ''))
                if msg.get('role') == 'user':
                    all_messages.append(HumanMessage(content=content))
                elif msg.get('role') == 'assistant':
                    all_messages.append(AIMessage(content=content))
            
            if all_messages:
                print(" Last 5 messages in conversation:")
                for i, msg in enumerate(all_messages[-5:], 1):
                    print(f"   {i}. {type(msg).__name__}: {msg.content[:100]}...")
            
            # Get existing summary if any
            summary_key = f"chat:summary:{conversation_id}"
            existing_summary = self.redis_client.get(summary_key) or ""
            
            total_messages = len(all_messages)
            print(f" Total messages in conversation: {total_messages}")
            
            # Save user message to Redis FIRST
            user_message_data = {
                'website_id': website_id,
                'conversation_id': conversation_id,
                'session_id': session_id,
                'user_id': str(user_id) if user_id else '',
                'user_name': user_info.get('full_name', '') if user_info else '',
                'user_email': user_info.get('email', '') if user_info else '',
                'role': 'user',
                'content': question,
                'message': question,
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'user_info': user_info if user_info else {},
                    'user_id': str(user_id) if user_id else None,
                    'message_index': total_messages + 1,
                    'subscription_active': True,
                    'minutes_remaining': subscription_check.get('minutes_remaining', 0)
                }
            }
            
            user_message_id = self.redis_memory.save_message(website_id, conversation_id, user_message_data)
            print(f" Saved user message to Redis (ID: {user_message_id})")
            
            # Add the new question to messages
            all_messages.append(HumanMessage(content=question))
            
            # Create initial state with ALL messages
            initial_state = ChatState(
                messages=all_messages,  # This contains all conversation history
                website_id=website_id,
                conversation_id=conversation_id,
                user_id=str(user_id) if user_id else None,
                user_info=user_info,
                session_id=session_id
            )
            if existing_summary:
                initial_state.summary = existing_summary

            print(f" Invoking graph with {len(all_messages)} messages...")
            
            # Invoke the graph
            result = await self.chat_graph.graph.ainvoke(
                initial_state,
                config=config,
            )
            
            response_text = result.get("response", "Sorry, I couldn't generate a response.")
            
            print(f" Chat response generated ({len(response_text)} chars)")
            
            # ========== ADD TOKEN TRACKING HERE ==========
            # Track tokens for this chat interaction
            try:
                from app.tokens.token_counter import token_counter
                token_data = token_counter.track_chat_tokens(
                    website_id=website_id,
                    user_id=int(user_id) if user_id else None,
                    input_text=question,
                    output_text=response_text,
                    model="gpt-4o-mini",
                    metadata={
                        'conversation_id': conversation_id,
                        'session_id': session_id,
                        'response_length': len(response_text),
                        'user_info': user_info
                    }
                )
                print(f" Token tracking: {token_data}")
            except Exception as token_error:
                print(f" Token tracking error: {token_error}")
            # ========== END TOKEN TRACKING ==========
            
            # Save bot response to Redis
            bot_message_data = {
                'website_id': website_id,
                'conversation_id': conversation_id,
                'session_id': session_id,
                'user_id': str(user_id) if user_id else '',
                'user_name': user_info.get('full_name', '') if user_info else '',
                'user_email': user_info.get('email', '') if user_info else '',
                'role': 'assistant',
                'content': response_text,
                'message': response_text,
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'response_length': len(response_text),
                    'user_message_id': user_message_id,
                    'user_id': str(user_id) if user_id else None,
                    'subscription_active': True,
                    'minutes_remaining': subscription_check.get('minutes_remaining', 0)
                }
            }
            bot_message_id = self.redis_memory.save_message(website_id, conversation_id, bot_message_data)
            print(f" Saved bot response to Redis (ID: {bot_message_id})")
            
            # Save to PostgreSQL for backup
            try:
                pg_user_data = {
                    'website_id': website_id,
                    'conversation_id': conversation_id,
                    'session_id': session_id,
                    'user_id': str(user_id) if user_id else '',
                    'user_name': user_info.get('full_name', '') if user_info else '',
                    'user_email': user_info.get('email', '') if user_info else '',
                    'role': 'user',
                    'message': question,
                    'metadata': {'source': 'postgres_backup', 'user_id': str(user_id) if user_id else None}
                }
                db_manager.save_chat_message(pg_user_data)
                
                pg_bot_data = {
                    'website_id': website_id,
                    'conversation_id': conversation_id,
                    'session_id': session_id,
                    'user_id': str(user_id) if user_id else '',
                    'user_name': user_info.get('full_name', '') if user_info else '',
                    'user_email': user_info.get('email', '') if user_info else '',
                    'role': 'assistant',
                    'message': response_text,
                    'metadata': {'source': 'postgres_backup', 'user_id': str(user_id) if user_id else None}
                }
                db_manager.save_chat_message(pg_bot_data)
                print(f" Also saved to PostgreSQL as backup")
            except Exception as pg_error:
                print(f" Failed to save to PostgreSQL: {pg_error}")
            
            return response_text
            
        except Exception as e:
            print(f"\n    ERROR in chat method: {str(e)}")
            print(f" Error type: {type(e).__name__}")
            import traceback
            print(f" Traceback:")
            print(traceback.format_exc())
            
            # Save error to Redis
            if session_id or conversation_id:
                try:
                    error_message_data = {
                        'website_id': website_id,
                        'conversation_id': conversation_id,
                        'session_id': session_id,
                        'user_id': str(user_id) if user_id else '',
                        'role': 'system',
                        'content': f"Error: {str(e)}",
                        'message': f"Error: {str(e)}",
                        'metadata': {
                            'error': True,
                            'timestamp': datetime.now().isoformat(),
                            'question': question,
                            'error_type': type(e).__name__,
                            'user_id': str(user_id) if user_id else None
                        }
                    }
                    self.redis_memory.save_message(website_id, conversation_id, error_message_data)
                except Exception as redis_error:
                    print(f"  Failed to save error to Redis: {redis_error}")
            
            return "I'm sorry, I encountered an error while processing your request. Please try again."
    
    async def get_conversation_history(self, website_id: str, conversation_id: str, user_id: str = None) -> List[Dict[str, str]]:
        """Get conversation history"""
        try:
            redis_messages = self.redis_memory.get_messages(website_id, conversation_id, user_id=user_id)
            if redis_messages:
                formatted = []
                for msg in redis_messages:
                    formatted.append({
                        "role": msg.get('role', 'user'),
                        "content": msg.get('content', msg.get('message', '')),
                        "timestamp": msg.get('metadata', {}).get('timestamp', msg.get('timestamp')),
                        "user_id": msg.get('user_id')
                    })
                return formatted
            return await self._get_history_from_database(conversation_id, user_id=user_id)
        except Exception as e:
            print(f"Error getting conversation history: {e}")
            return await self._get_history_from_database(conversation_id)
        
    def get_chat_history(self, website_id: str = None, conversation_id: str = None, 
                    user_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chat history for a website or conversation or user"""
        try:
            params = []
            conditions = []
            
            if website_id:
                conditions.append("website_id = %s")
                params.append(website_id)
            
            if conversation_id:
                conditions.append("conversation_id = %s")
                params.append(conversation_id)
            
            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT * FROM chat_history 
                WHERE {where_clause}
                ORDER BY created_at ASC
                LIMIT %s
            """
            params.append(limit)
            
            return self.execute_query(query, tuple(params), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting chat history: {e}")
            return []
    
    async def clear_conversation(self, conversation_id: str) -> bool:
        """Clear conversation history"""
        try:
            redis_success = self.redis_memory.clear_conversation(conversation_id)
            
            if self.checkpointer:
                try:
                    config = {"configurable": {"thread_id": conversation_id}}
                    await self.checkpointer.adelete(config)
                    print(f" Cleared conversation {conversation_id} from Redis checkpoint")
                except Exception as cp_error:
                    print(f" Error clearing checkpoint: {cp_error}")
            
            try:
                conn = db_manager.get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM chat_history WHERE conversation_id = %s", (conversation_id,))
                conn.commit()
                cursor.close()
                print(f" Cleared conversation {conversation_id} from PostgreSQL")
            except Exception as db_error:
                print(f" Error clearing from PostgreSQL: {db_error}")
            
            return redis_success
        except Exception as e:
            print(f"Error clearing conversation: {e}")
            return False
    
    async def send_chat_report(self, website_id: str, conversation_id: str, user_id: str = None):
        """Send chat history report to admin"""
        try:
            redis_messages = self.redis_memory.get_messages(website_id, conversation_id, user_id=user_id)
            
            if redis_messages:
                formatted_history = []
                for msg in redis_messages:
                    formatted_history.append({
                        'role': msg.get('role', 'user'),
                        'message': msg.get('content', msg.get('message', '')),
                        'created_at': msg.get('metadata', {}).get('timestamp', datetime.now().isoformat()),
                        'user_id': msg.get('user_id')
                    })
                
                success = email_service.send_chat_history_email(
                    website_id,
                    conversation_id,
                    formatted_history
                )
                
                if success:
                    print(f" Chat report sent for conversation {conversation_id}")
                    return success
            
            chat_history = db_manager.get_full_conversation(conversation_id)
            
            if not chat_history:
                print(f"No chat history found for conversation {conversation_id}")
                return False
            
            formatted_history = []
            for chat in chat_history:
                formatted_history.append({
                    'role': chat['role'],
                    'message': chat['message'],
                    'created_at': chat['created_at'].strftime('%Y-%m-%d %H:%M:%S') if chat['created_at'] else '',
                    'user_id': chat.get('user_id')
                })
            
            success = email_service.send_chat_history_email(
                website_id,
                conversation_id,
                formatted_history
            )
            
            if success:
                print(f" Chat report sent for conversation {conversation_id}")
            else:
                print(f"  Failed to send chat report for conversation {conversation_id}")
            
            return success
            
        except Exception as e:
            print(f"  Error sending chat report: {e}")
            return False

# Singleton instance
chat_agent = ChatAgent()