import os
import json
import urllib.parse
import asyncio
from typing import List, Dict, Any, Optional, Tuple, AsyncIterator
from datetime import datetime
from functools import partial

import redis
from langgraph.checkpoint.redis import RedisSaver
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple


class RedisCheckpointSaver(BaseCheckpointSaver):
    """Redis checkpointer for local Redis"""
    
    def __init__(self, redis_client):
        super().__init__()
        self.redis_client = redis_client
        self._saver = None
        self._init_saver()
    
    def _init_saver(self):
        """Initialize the underlying RedisSaver"""
        try:
            redis_url = os.getenv("REDIS_URL")
            
            if hasattr(RedisSaver, 'from_conn_string'):
                self._saver = RedisSaver.from_conn_string(redis_url)
            else:
                # Parse connection parameters from redis_client
                conn_kwargs = self.redis_client.connection_pool.connection_kwargs
                
                # Extract connection parameters
                host = conn_kwargs.get('host')
                port = conn_kwargs.get('port')
                db = conn_kwargs.get('db', 0)
                password = conn_kwargs.get('password')
                username = conn_kwargs.get('username')
                ssl = conn_kwargs.get('ssl', False)
                
                # If connection pool doesn't have these values, use environment variables
                if not host:
                    host = os.getenv("REDIS_HOST")
                    port = int(os.getenv("REDIS_PORT"))
                    db = int(os.getenv("REDIS_DB"))
                    password = os.getenv("REDIS_PASSWORD")
                    username = os.getenv("REDIS_USERNAME")
                    ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
                
                self._saver = RedisSaver(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    username=username,
                    ssl=ssl
                )
            print(f"✅ RedisSaver initialized successfully")
        except Exception as e:
            print(f"⚠️ RedisSaver initialization error: {e}")
            self._saver = None
    
    def get_next_version(self, current_version: Optional[int], channel: str) -> int:
        if self._saver and hasattr(self._saver, 'get_next_version'):
            return self._saver.get_next_version(current_version, channel)
        if current_version is None:
            return 1
        return current_version + 1
    
    def put(self, config: Dict, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: Dict[str, int]) -> None:
        if self._saver and hasattr(self._saver, 'put'):
            return self._saver.put(config, checkpoint, metadata, new_versions)
        return None
    
    async def aput(self, config: Dict, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: Dict[str, int]) -> None:
        if self._saver and hasattr(self._saver, 'aput'):
            return await self._saver.aput(config, checkpoint, metadata, new_versions)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            partial(self.put, config, checkpoint, metadata, new_versions)
        )
    
    def put_writes(self, config: Dict, writes: List[Tuple[str, Any]], task_id: str) -> None:
        if self._saver and hasattr(self._saver, 'put_writes'):
            return self._saver.put_writes(config, writes, task_id)
        return None
    
    async def aput_writes(self, config: Dict, writes: List[Tuple[str, Any]], task_id: str) -> None:
        if self._saver and hasattr(self._saver, 'aput_writes'):
            return await self._saver.aput_writes(config, writes, task_id)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            partial(self.put_writes, config, writes, task_id)
        )
    
    def get_tuple(self, config: Dict) -> Optional[CheckpointTuple]:
        if self._saver and hasattr(self._saver, 'get_tuple'):
            return self._saver.get_tuple(config)
        return None
    
    async def aget_tuple(self, config: Dict) -> Optional[CheckpointTuple]:
        if self._saver and hasattr(self._saver, 'aget_tuple'):
            return await self._saver.aget_tuple(config)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.get_tuple, config))
    
    def list(self, config: Dict, limit: Optional[int] = None, before: Optional[Dict] = None) -> List[CheckpointTuple]:
        if self._saver and hasattr(self._saver, 'list'):
            return self._saver.list(config, limit, before)
        return []
    
    async def alist(self, config: Dict, limit: Optional[int] = None, before: Optional[Dict] = None) -> AsyncIterator[CheckpointTuple]:
        if self._saver and hasattr(self._saver, 'alist'):
            async for item in self._saver.alist(config, limit, before):
                yield item
        else:
            items = self.list(config, limit, before)
            for item in items:
                yield item
    
    def delete(self, config: Dict) -> None:
        if self._saver and hasattr(self._saver, 'delete'):
            return self._saver.delete(config)
        return None
    
    async def adelete(self, config: Dict) -> None:
        if self._saver and hasattr(self._saver, 'adelete'):
            return await self._saver.adelete(config)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.delete, config))


class RedisMemory:
    """Redis operations for chat history management"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
    
    @staticmethod
    def init_redis_client(redis_url: str = None):
        """Initialize Redis client for local connection"""
        if not redis_url:
            redis_url = os.getenv("REDIS_URL")
        
        # Also support individual environment variables as fallback
        if not redis_url:
            host = os.getenv("REDIS_HOST")
            port = os.getenv("REDIS_PORT")
            password = os.getenv("REDIS_PASSWORD")
            username = os.getenv("REDIS_USERNAME", "sandipbaste")
            db = os.getenv("REDIS_DB", "0")
            ssl = os.getenv("REDIS_SSL", "true").lower() == "true"
            
            # Build Redis URL
            if username and password:
                redis_url = f"redis://{username}:{password}@{host}:{port}/{db}"
            elif password:
                redis_url = f"redis://:{password}@{host}:{port}/{db}"
            else:
                redis_url = f"redis://{host}:{port}/{db}"
            
            if ssl:
                redis_url = redis_url.replace("redis://", "rediss://")
        
        # Mask password in logs for security
        display_url = redis_url
        if '@' in display_url:
            parts = display_url.split('@')
            if ':' in parts[0]:
                if parts[0].startswith('redis://:'):
                    display_url = f"redis://:***@{parts[1]}"
                elif '://' in parts[0]:
                    protocol = parts[0].split('://')[0]
                    display_url = f"{protocol}://:***@{parts[1]}"
        
        print(f"🔧 Connecting to Redis at: {display_url}")
        
        try:
            redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=30,
                socket_connect_timeout=30
            )
            redis_client.ping()
            print("✅ Redis connected successfully")
            return redis_client
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            raise
    
    def _get_redis_key(self, website_id: str, conversation_id: str, message_id: str = None) -> str:
        if message_id:
            return f"chat:history:{website_id}:{conversation_id}:{message_id}"
        return f"chat:history:{conversation_id}"
    
    def save_message(self, website_id: str, conversation_id: str, message_data: Dict[str, Any]) -> str:
        """Save a single message to Redis using SET with EX (more compatible)"""
        try:
            message_id = f"msg_{int(datetime.now().timestamp() * 1000)}_{hash(str(message_data)) % 10000}"
            key = self._get_redis_key(website_id, conversation_id, message_id)
            
            if 'timestamp' not in message_data:
                message_data['timestamp'] = datetime.now().isoformat()
            
            if 'metadata' not in message_data:
                message_data['metadata'] = {}
            
            timestamp_epoch = datetime.now().timestamp()
            message_data['metadata']['timestamp_epoch'] = timestamp_epoch
            message_data['metadata']['message_id'] = message_id
            message_data['metadata']['saved_at'] = datetime.now().isoformat()
            message_data['timestamp_epoch'] = timestamp_epoch
            
            # Use SET with EX instead of SETEX (more compatible with restricted permissions)
            self.redis_client.set(
                key,
                json.dumps(message_data, ensure_ascii=False),
                ex=2592000  # 30 days expiry
            )
            
            sorted_set_key = f"chat:messages:{conversation_id}"
            self.redis_client.zadd(
                sorted_set_key,
                {message_id: timestamp_epoch}
            )
            self.redis_client.expire(sorted_set_key, 2592000)
            
            print(f"💾 Saved message {message_id} to Redis with timestamp {timestamp_epoch}")
            return message_id
            
        except Exception as e:
            print(f"❌ Error saving message to Redis: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_conversation_summary(self, conversation_id: str) -> str:
        """Get conversation summary from Redis"""
        try:
            key = f"chat:summary:{conversation_id}"
            summary = self.redis_client.get(key)
            return summary if summary else ""
        except Exception as e:
            print(f"⚠️ Error getting summary: {e}")
            return ""
    
    def save_conversation_summary(self, conversation_id: str, summary: str) -> bool:
        """Save conversation summary to Redis using SET with EX"""
        try:
            key = f"chat:summary:{conversation_id}"
            self.redis_client.set(key, summary, ex=2592000)
            return True
        except Exception as e:
            print(f"⚠️ Error saving summary: {e}")
            return False
    
    def get_message_count(self, conversation_id: str) -> int:
        """Get total message count for a conversation"""
        try:
            sorted_set_key = f"chat:messages:{conversation_id}"
            return self.redis_client.zcard(sorted_set_key)
        except Exception as e:
            print(f"⚠️ Error getting message count: {e}")
            return 0
    
    def get_recent_messages(
        self,
        website_id: str,
        conversation_id: str,
        user_id: str = None,
        limit: int = 30
    ) -> List[Dict]:
        """Get only recent messages (bypasses summary)"""
        try:
            sorted_set_key = f"chat:messages:{conversation_id}"
            message_ids = self.redis_client.zrevrange(
                sorted_set_key,
                0,
                limit - 1
            )
            
            pipe = self.redis_client.pipeline(transaction=False)
            for msg_id in message_ids:
                key = self._get_redis_key(website_id, conversation_id, msg_id)
                pipe.get(key)
            
            results = pipe.execute()
            messages = []
            
            for msg_json in results:
                if msg_json:
                    try:
                        msg_data = json.loads(msg_json)
                        if user_id:
                            msg_user_id = msg_data.get('user_id') or msg_data.get('metadata', {}).get('user_id')
                            if msg_user_id and msg_user_id != user_id:
                                continue
                        messages.append(msg_data)
                    except json.JSONDecodeError:
                        continue
            
            messages.sort(key=lambda x: x.get("metadata", {}).get("timestamp_epoch", 0))
            return messages
            
        except Exception as e:
            print(f"⚠️ Error getting recent messages: {e}")
            return []
    
    def get_messages(self, website_id: str, conversation_id: str, user_id: str = None, limit: int = 100, hours: int = 720):
        """Get messages from Redis"""
        try:
            sorted_set_key = f"chat:messages:{conversation_id}"
            
            all_message_ids = self.redis_client.zrange(
                sorted_set_key,
                0,
                -1
            )
            
            print(f"📊 Found {len(all_message_ids)} total messages in Redis for conversation {conversation_id}")
            
            if not all_message_ids:
                return []
            
            pipe = self.redis_client.pipeline(transaction=False)
            for msg_id in all_message_ids:
                key = self._get_redis_key(website_id, conversation_id, msg_id)
                pipe.get(key)
            
            results = pipe.execute()
            messages = []
            
            current_time = datetime.now().timestamp()
            cutoff_time = current_time - (hours * 3600)
            
            for msg_json in results:
                if msg_json:
                    try:
                        msg_data = json.loads(msg_json)
                        
                        msg_time = None
                        if 'metadata' in msg_data and 'timestamp_epoch' in msg_data['metadata']:
                            msg_time = msg_data['metadata']['timestamp_epoch']
                        elif 'timestamp_epoch' in msg_data:
                            msg_time = msg_data['timestamp_epoch']
                        elif 'timestamp' in msg_data:
                            try:
                                if isinstance(msg_data['timestamp'], str):
                                    msg_time = datetime.fromisoformat(msg_data['timestamp'].replace('Z', '+00:00')).timestamp()
                                else:
                                    msg_time = msg_data['timestamp']
                            except:
                                msg_time = current_time
                        
                        if msg_time is None:
                            msg_time = current_time
                        
                        if msg_time < cutoff_time:
                            continue
                        
                        if user_id:
                            msg_user_id = msg_data.get('user_id') or msg_data.get('metadata', {}).get('user_id')
                            if msg_user_id and str(msg_user_id) != str(user_id):
                                continue
                        
                        messages.append(msg_data)
                        
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Error decoding message: {e}")
                        continue
                    except Exception as e:
                        print(f"⚠️ Error processing message: {e}")
                        continue
            
            messages.sort(key=lambda x: x.get("metadata", {}).get("timestamp_epoch", 0))
            
            if limit and len(messages) > limit:
                messages = messages[-limit:]
            
            user_filter_msg = f" for user {user_id}" if user_id else ""
            print(f"✅ Retrieved {len(messages)} messages from last {hours} hours{user_filter_msg}")
            
            if messages:
                print(f"📝 First message: {messages[0].get('role')} - {messages[0].get('content', '')[:50]}...")
                print(f"📝 Last message: {messages[-1].get('role')} - {messages[-1].get('content', '')[:50]}...")
            
            return messages
            
        except Exception as e:
            print(f"❌ Error getting messages from Redis: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear all messages for a conversation from Redis"""
        try:
            pipe = self.redis_client.pipeline(transaction=False)
            for key in self.redis_client.scan_iter(f"chat:history:*:{conversation_id}:*"):
                pipe.delete(key)
            pipe.delete(f"chat:messages:{conversation_id}")
            pipe.execute()
            print(f"🗑️ Cleared conversation {conversation_id} from Redis")
            return True
        except Exception as e:
            print(f"❌ Error clearing conversation from Redis: {e}")
            return False