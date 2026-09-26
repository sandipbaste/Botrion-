import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import threading

load_dotenv()

class TokenCounter:
    def __init__(self):
        # Database connection - PostgreSQL
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT'))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.schema = os.getenv('DB_SCHEMA', 'public')
        
        # ✅ FIX: Initialize connection_pool as None
        self.connection_pool = None
        
        # Token estimation rates
        self.INPUT_TOKEN_RATE = 0.00000015
        self.OUTPUT_TOKEN_RATE = 0.00000060
        self.EMBEDDING_TOKEN_RATE = 0.00000002
        
        print(" Token tables assumed to exist (schema already created)")
        self._start_cleanup_thread()
    
    def get_connection(self, retry_count=3):
        """Get database connection with retry logic"""
        last_error = None
        
        for attempt in range(retry_count):
            try:
                print(f"  TokenCounter DB connection attempt {attempt + 1}/{retry_count}...")
                
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    connect_timeout=60,
                    sslmode='require'
                )
                conn.autocommit = True
                
                # Set schema after connection
                cursor = conn.cursor()
                cursor.execute(f"SET search_path TO {self.schema}")
                cursor.close()
                
                print("  ✅ TokenCounter DB connected successfully")
                return conn
                
            except Exception as e:
                last_error = e
                print(f"  TokenCounter DB connection attempt {attempt + 1} failed: {e}")
                if attempt < retry_count - 1:
                    wait_time = min(2 ** attempt, 10)
                    print(f"  Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                continue
        
        raise last_error or Exception("Failed to connect to database after retries")
    
    def release_connection(self, conn):
        """Release connection back to pool"""
        if conn:
            try:
                # ✅ FIX: Check if connection_pool exists
                if hasattr(self, 'connection_pool') and self.connection_pool:
                    self.connection_pool.putconn(conn)
                else:
                    conn.close()
            except Exception as e:
                print(f"  Error releasing connection: {e}")
    
    def execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic for connection issues"""
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Execute the provided function
                result = func(cursor, *args, **kwargs)
                
                if not conn.autocommit:
                    conn.commit()
                
                cursor.close()
                self.release_connection(conn)
                return result
                
            except Exception as e:
                last_error = e
                print(f"  Execute attempt {attempt + 1} failed: {e}")
                if conn:
                    try:
                        conn.rollback()
                    except:
                        pass
                    self.release_connection(conn)
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
        
        raise last_error or Exception("Execution failed after retries")
    
    def _start_cleanup_thread(self):
        """Start background thread for cleaning old token data"""
        def cleanup_old_tokens():
            while True:
                try:
                    time.sleep(86400)  # Run once per day
                    self.archive_old_tokens(days=90)
                except Exception as e:
                    print(f"  Token cleanup error: {e}")
        
        thread = threading.Thread(target=cleanup_old_tokens, daemon=True)
        thread.start()
    
    def count_tokens(self, text: str, model: str = "gpt-4o-mini") -> int:
        """Count tokens using model-specific tokenizer"""
        if not text:
            return 0
        
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model("gpt-4o-mini")
            return len(encoding.encode(text))
        except ImportError:
            import re
            words = len(re.findall(r'\b\w+\b', text))
            punctuation = len(re.findall(r'[^\w\s]', text))
            return int(words * 1.3 + punctuation)
    
    def track_chat_tokens(
        self,
        website_id: str,
        user_id: Optional[int],
        input_text: str,
        output_text: str,
        model: str = "gpt-4o-mini",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Track tokens used in a chat interaction"""
        try:
            input_tokens = self.count_tokens(input_text, model)
            output_tokens = self.count_tokens(output_text, model)
            
            input_cost = input_tokens * self.INPUT_TOKEN_RATE
            output_cost = output_tokens * self.OUTPUT_TOKEN_RATE
            
            conn = None
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                
                # Save input tokens
                cursor.execute('''
                    INSERT INTO token_usage 
                    (website_id, user_id, token_type, tokens, cost, model, operation_type, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    website_id,
                    user_id,
                    'input',
                    input_tokens,
                    input_cost,
                    model,
                    'chat',
                    json.dumps({**(metadata or {}), 'text_preview': input_text[:100]})
                ))
                
                # Save output tokens
                cursor.execute('''
                    INSERT INTO token_usage 
                    (website_id, user_id, token_type, tokens, cost, model, operation_type, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    website_id,
                    user_id,
                    'output',
                    output_tokens,
                    output_cost,
                    model,
                    'chat',
                    json.dumps({**(metadata or {}), 'text_preview': output_text[:100]})
                ))
                
                # Update aggregates
                self._update_aggregates_fast(cursor, website_id, user_id, input_tokens, output_tokens, 0, 1)
                
                conn.commit()
                
                print(f" Token tracking: {input_tokens}+{output_tokens}={input_tokens+output_tokens} tokens")
                
            except Exception as e:
                print(f"  Token tracking error: {e}")
            finally:
                if conn:
                    try:
                        self.release_connection(conn)
                    except:
                        pass
            
            return {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'input_cost': input_cost,
                'output_cost': output_cost,
                'total_cost': input_cost + output_cost
            }
            
        except Exception as e:
            print(f"  Track chat tokens error: {e}")
            return {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'error': str(e)
            }

    def _update_aggregates_fast(self, cursor, website_id, user_id, input_tokens, output_tokens, embedding_tokens, chat_count):
        """Fast aggregate update using existing cursor"""
        try:
            today = datetime.now().date()
            year_month = today.strftime('%Y-%m')
            
            total_tokens = input_tokens + output_tokens + embedding_tokens
            input_cost = input_tokens * self.INPUT_TOKEN_RATE
            output_cost = output_tokens * self.OUTPUT_TOKEN_RATE
            embedding_cost = embedding_tokens * self.EMBEDDING_TOKEN_RATE
            total_cost = input_cost + output_cost + embedding_cost
            
            # Update daily aggregate
            cursor.execute('''
                INSERT INTO token_aggregates_daily 
                (website_id, user_id, date, input_tokens, output_tokens, embedding_tokens, 
                total_tokens, input_cost, output_cost, embedding_cost, total_cost,
                chat_count, training_count, search_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0)
                ON CONFLICT (website_id, date) 
                DO UPDATE SET
                input_tokens = token_aggregates_daily.input_tokens + EXCLUDED.input_tokens,
                output_tokens = token_aggregates_daily.output_tokens + EXCLUDED.output_tokens,
                embedding_tokens = token_aggregates_daily.embedding_tokens + EXCLUDED.embedding_tokens,
                total_tokens = token_aggregates_daily.total_tokens + EXCLUDED.total_tokens,
                input_cost = token_aggregates_daily.input_cost + EXCLUDED.input_cost,
                output_cost = token_aggregates_daily.output_cost + EXCLUDED.output_cost,
                embedding_cost = token_aggregates_daily.embedding_cost + EXCLUDED.embedding_cost,
                total_cost = token_aggregates_daily.total_cost + EXCLUDED.total_cost,
                chat_count = token_aggregates_daily.chat_count + EXCLUDED.chat_count
            ''', (
                website_id,
                user_id,
                today,
                input_tokens,
                output_tokens,
                embedding_tokens,
                total_tokens,
                input_cost,
                output_cost,
                embedding_cost,
                total_cost,
                chat_count
            ))
            
            # Update monthly aggregate
            cursor.execute('''
                INSERT INTO token_aggregates_monthly 
                (website_id, user_id, year_month, input_tokens, output_tokens, embedding_tokens,
                total_tokens, input_cost, output_cost, embedding_cost, total_cost,
                chat_count, training_count, search_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0)
                ON CONFLICT (website_id, year_month) 
                DO UPDATE SET
                input_tokens = token_aggregates_monthly.input_tokens + EXCLUDED.input_tokens,
                output_tokens = token_aggregates_monthly.output_tokens + EXCLUDED.output_tokens,
                embedding_tokens = token_aggregates_monthly.embedding_tokens + EXCLUDED.embedding_tokens,
                total_tokens = token_aggregates_monthly.total_tokens + EXCLUDED.total_tokens,
                input_cost = token_aggregates_monthly.input_cost + EXCLUDED.input_cost,
                output_cost = token_aggregates_monthly.output_cost + EXCLUDED.output_cost,
                embedding_cost = token_aggregates_monthly.embedding_cost + EXCLUDED.embedding_cost,
                total_cost = token_aggregates_monthly.total_cost + EXCLUDED.total_cost,
                chat_count = token_aggregates_monthly.chat_count + EXCLUDED.chat_count
            ''', (
                website_id,
                user_id,
                year_month,
                input_tokens,
                output_tokens,
                embedding_tokens,
                total_tokens,
                input_cost,
                output_cost,
                embedding_cost,
                total_cost,
                chat_count
            ))
            
            # Update user aggregate if user_id provided
            if user_id:
                cursor.execute('''
                    INSERT INTO token_aggregates_user 
                    (user_id, input_tokens, output_tokens, embedding_tokens, total_tokens,
                    input_cost, output_cost, embedding_cost, total_cost,
                    chat_count, website_count, last_updated)
                    SELECT 
                        %s as user_id,
                        COALESCE(SUM(input_tokens), 0) as input_tokens,
                        COALESCE(SUM(output_tokens), 0) as output_tokens,
                        COALESCE(SUM(embedding_tokens), 0) as embedding_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(SUM(input_cost), 0) as input_cost,
                        COALESCE(SUM(output_cost), 0) as output_cost,
                        COALESCE(SUM(embedding_cost), 0) as embedding_cost,
                        COALESCE(SUM(total_cost), 0) as total_cost,
                        COALESCE(SUM(chat_count), 0) as chat_count,
                        COUNT(DISTINCT website_id) as website_count,
                        CURRENT_TIMESTAMP
                    FROM token_aggregates_monthly
                    WHERE user_id = %s
                    ON CONFLICT (user_id) DO UPDATE SET
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    embedding_tokens = EXCLUDED.embedding_tokens,
                    total_tokens = EXCLUDED.total_tokens,
                    input_cost = EXCLUDED.input_cost,
                    output_cost = EXCLUDED.output_cost,
                    embedding_cost = EXCLUDED.embedding_cost,
                    total_cost = EXCLUDED.total_cost,
                    chat_count = EXCLUDED.chat_count,
                    website_count = EXCLUDED.website_count,
                    last_updated = CURRENT_TIMESTAMP
                ''', (user_id, user_id))
                
        except Exception as e:
            print(f"  Fast aggregate update error: {e}")
    
    def track_embedding_tokens(
        self,
        website_id: str,
        user_id: Optional[int],
        texts: List[str],
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
        operation_type: str = "embedding",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Track tokens used in embedding generation"""
        try:
            total_tokens = sum(self.count_tokens(text) for text in texts)
            cost = total_tokens * self.EMBEDDING_TOKEN_RATE
            
            print(f"   Saving {total_tokens} embedding tokens for website {website_id}")
            
            self._save_token_usage(
                website_id=website_id,
                user_id=user_id,
                token_type='embedding',
                tokens=total_tokens,
                cost=cost,
                model=model,
                operation_type=operation_type,
                metadata={**(metadata or {}), 'text_count': len(texts)}
            )
            
            # Update aggregates
            update_kwargs = {
                'website_id': website_id,
                'user_id': user_id,
                'input_tokens': 0,
                'output_tokens': 0,
                'embedding_tokens': total_tokens
            }
            
            if operation_type == 'training':
                update_kwargs['training_count'] = 1
            elif operation_type == 'search':
                update_kwargs['search_count'] = 1
            
            self._update_aggregates(**update_kwargs)
            
            return {
                'embedding_tokens': total_tokens,
                'embedding_cost': cost,
                'texts_processed': len(texts)
            }
            
        except Exception as e:
            print(f"  Track embedding tokens error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'embedding_tokens': 0,
                'error': str(e)
            }
    
    def track_training_tokens(
        self,
        website_id: str,
        user_id: Optional[int],
        website_data: List[Dict[str, Any]],
        model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ) -> Dict[str, Any]:
        """Track tokens used in website training"""
        try:
            texts = []
            for item in website_data:
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, str) and len(value) > 50:
                            texts.append(value)
                elif isinstance(item, str):
                    texts.append(item)
            
            result = self.track_embedding_tokens(
                website_id=website_id,
                user_id=user_id,
                texts=texts,
                model=model,
                operation_type='training',
                metadata={'data_points': len(website_data)}
            )
            
            return result
            
        except Exception as e:
            print(f"  Track training tokens error: {e}")
            return {'embedding_tokens': 0}
    
    def _save_token_usage(
        self,
        website_id: str,
        user_id: Optional[int],
        token_type: str,
        tokens: int,
        cost: float,
        model: str,
        operation_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Save token usage to database"""
        if tokens == 0:
            return
        
        def _save(cursor):
            query = '''
                INSERT INTO token_usage 
                (website_id, user_id, token_type, tokens, cost, model, operation_type, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            '''
            cursor.execute(query, (
                website_id,
                user_id,
                token_type,
                tokens,
                cost,
                model,
                operation_type,
                json.dumps(metadata) if metadata else None
            ))
            print(f" Saved token usage: {tokens} {token_type} tokens for website {website_id}")
        
        try:
            self.execute_with_retry(_save)
        except Exception as e:
            print(f"  Save token usage error (after retries): {e}")
    
    def _update_aggregates(
        self,
        website_id: str,
        user_id: Optional[int],
        input_tokens: int,
        output_tokens: int,
        embedding_tokens: int,
        chat_count: int = 0,
        training_count: int = 0,
        search_count: int = 0
    ):
        """Update daily, monthly, and user aggregates"""
        try:
            today = datetime.now().date()
            year_month = today.strftime('%Y-%m')
            
            total_tokens = input_tokens + output_tokens + embedding_tokens
            input_cost = input_tokens * self.INPUT_TOKEN_RATE
            output_cost = output_tokens * self.OUTPUT_TOKEN_RATE
            embedding_cost = embedding_tokens * self.EMBEDDING_TOKEN_RATE
            total_cost = input_cost + output_cost + embedding_cost
            
            print(f"   Updating aggregates for website {website_id}, user {user_id}:")
            print(f"   Input: {input_tokens} tokens (${input_cost:.8f})")
            print(f"   Output: {output_tokens} tokens (${output_cost:.8f})")
            print(f"   Embedding: {embedding_tokens} tokens (${embedding_cost:.8f})")
            
            def _update_daily(cursor):
                cursor.execute('''
                    INSERT INTO token_aggregates_daily 
                    (website_id, user_id, date, input_tokens, output_tokens, embedding_tokens, 
                    total_tokens, input_cost, output_cost, embedding_cost, total_cost,
                    chat_count, training_count, search_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (website_id, date) 
                    DO UPDATE SET
                    input_tokens = token_aggregates_daily.input_tokens + EXCLUDED.input_tokens,
                    output_tokens = token_aggregates_daily.output_tokens + EXCLUDED.output_tokens,
                    embedding_tokens = token_aggregates_daily.embedding_tokens + EXCLUDED.embedding_tokens,
                    total_tokens = token_aggregates_daily.total_tokens + EXCLUDED.total_tokens,
                    input_cost = token_aggregates_daily.input_cost + EXCLUDED.input_cost,
                    output_cost = token_aggregates_daily.output_cost + EXCLUDED.output_cost,
                    embedding_cost = token_aggregates_daily.embedding_cost + EXCLUDED.embedding_cost,
                    total_cost = token_aggregates_daily.total_cost + EXCLUDED.total_cost,
                    chat_count = token_aggregates_daily.chat_count + EXCLUDED.chat_count,
                    training_count = token_aggregates_daily.training_count + EXCLUDED.training_count,
                    search_count = token_aggregates_daily.search_count + EXCLUDED.search_count,
                    updated_at = CURRENT_TIMESTAMP
                ''', (
                    website_id,
                    user_id,
                    today,
                    input_tokens,
                    output_tokens,
                    embedding_tokens,
                    total_tokens,
                    input_cost,
                    output_cost,
                    embedding_cost,
                    total_cost,
                    chat_count,
                    training_count,
                    search_count
                ))
            
            def _update_monthly(cursor):
                cursor.execute('''
                    INSERT INTO token_aggregates_monthly 
                    (website_id, user_id, year_month, input_tokens, output_tokens, embedding_tokens,
                    total_tokens, input_cost, output_cost, embedding_cost, total_cost,
                    chat_count, training_count, search_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (website_id, year_month) 
                    DO UPDATE SET
                    input_tokens = token_aggregates_monthly.input_tokens + EXCLUDED.input_tokens,
                    output_tokens = token_aggregates_monthly.output_tokens + EXCLUDED.output_tokens,
                    embedding_tokens = token_aggregates_monthly.embedding_tokens + EXCLUDED.embedding_tokens,
                    total_tokens = token_aggregates_monthly.total_tokens + EXCLUDED.total_tokens,
                    input_cost = token_aggregates_monthly.input_cost + EXCLUDED.input_cost,
                    output_cost = token_aggregates_monthly.output_cost + EXCLUDED.output_cost,
                    embedding_cost = token_aggregates_monthly.embedding_cost + EXCLUDED.embedding_cost,
                    total_cost = token_aggregates_monthly.total_cost + EXCLUDED.total_cost,
                    chat_count = token_aggregates_monthly.chat_count + EXCLUDED.chat_count,
                    training_count = token_aggregates_monthly.training_count + EXCLUDED.training_count,
                    search_count = token_aggregates_monthly.search_count + EXCLUDED.search_count,
                    updated_at = CURRENT_TIMESTAMP
                ''', (
                    website_id,
                    user_id,
                    year_month,
                    input_tokens,
                    output_tokens,
                    embedding_tokens,
                    total_tokens,
                    input_cost,
                    output_cost,
                    embedding_cost,
                    total_cost,
                    chat_count,
                    training_count,
                    search_count
                ))
            
            def _update_user(cursor):
                if user_id:
                    cursor.execute('''
                        INSERT INTO token_aggregates_user 
                        (user_id, input_tokens, output_tokens, embedding_tokens, total_tokens,
                        input_cost, output_cost, embedding_cost, total_cost,
                        chat_count, website_count, last_updated)
                        SELECT 
                            %s as user_id,
                            COALESCE(SUM(input_tokens), 0) as input_tokens,
                            COALESCE(SUM(output_tokens), 0) as output_tokens,
                            COALESCE(SUM(embedding_tokens), 0) as embedding_tokens,
                            COALESCE(SUM(total_tokens), 0) as total_tokens,
                            COALESCE(SUM(input_cost), 0) as input_cost,
                            COALESCE(SUM(output_cost), 0) as output_cost,
                            COALESCE(SUM(embedding_cost), 0) as embedding_cost,
                            COALESCE(SUM(total_cost), 0) as total_cost,
                            COALESCE(SUM(chat_count), 0) as chat_count,
                            COUNT(DISTINCT website_id) as website_count,
                            CURRENT_TIMESTAMP
                        FROM token_aggregates_monthly
                        WHERE user_id = %s
                        ON CONFLICT (user_id) DO UPDATE SET
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        embedding_tokens = EXCLUDED.embedding_tokens,
                        total_tokens = EXCLUDED.total_tokens,
                        input_cost = EXCLUDED.input_cost,
                        output_cost = EXCLUDED.output_cost,
                        embedding_cost = EXCLUDED.embedding_cost,
                        total_cost = EXCLUDED.total_cost,
                        chat_count = EXCLUDED.chat_count,
                        website_count = EXCLUDED.website_count,
                        last_updated = CURRENT_TIMESTAMP
                    ''', (user_id, user_id))
                    print(f" Updated user aggregates for user {user_id}")
            
            # Execute all updates with retry
            self.execute_with_retry(_update_daily)
            self.execute_with_retry(_update_monthly)
            if user_id:
                self.execute_with_retry(_update_user)
            
        except Exception as e:
            print(f"  Update aggregates error: {e}")
            import traceback
            traceback.print_exc()
    
    def get_user_websites_token_details(self, user_id: int) -> Dict[str, Any]:
        """Get all websites for a user with their token details"""
        try:
            def _get(cursor):
                cursor.execute('''
                    SELECT 
                        tam.website_id,
                        w.website_name,
                        w.website_url,
                        COALESCE(SUM(tam.input_tokens), 0) as total_input_tokens,
                        COALESCE(SUM(tam.output_tokens), 0) as total_output_tokens,
                        COALESCE(SUM(tam.embedding_tokens), 0) as total_embedding_tokens,
                        COALESCE(SUM(tam.total_tokens), 0) as total_tokens,
                        COALESCE(SUM(tam.input_cost), 0) as total_input_cost,
                        COALESCE(SUM(tam.output_cost), 0) as total_output_cost,
                        COALESCE(SUM(tam.embedding_cost), 0) as total_embedding_cost,
                        COALESCE(SUM(tam.total_cost), 0) as total_cost,
                        COALESCE(SUM(tam.chat_count), 0) as total_chats,
                        COUNT(DISTINCT tam.year_month) as months_active
                    FROM token_aggregates_monthly tam
                    LEFT JOIN websites w ON tam.website_id = w.website_id
                    WHERE tam.user_id = %s
                    GROUP BY tam.website_id, w.website_name, w.website_url
                    ORDER BY total_tokens DESC
                ''', (user_id,))
                return cursor.fetchall()
            
            websites = self.execute_with_retry(_get)
            
            overall_totals = {
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_embedding_tokens': 0,
                'total_tokens': 0,
                'total_input_cost': 0.0,
                'total_output_cost': 0.0,
                'total_embedding_cost': 0.0,
                'total_cost': 0.0,
                'total_chats': 0,
                'website_count': len(websites)
            }
            
            formatted_websites = []
            for website in websites:
                website_data = {
                    'website_id': website['website_id'],
                    'website_name': website['website_name'] or website['website_id'],
                    'website_url': website['website_url'] or '',
                    'input_tokens': int(website['total_input_tokens'] or 0),
                    'output_tokens': int(website['total_output_tokens'] or 0),
                    'embedding_tokens': int(website['total_embedding_tokens'] or 0),
                    'total_tokens': int(website['total_tokens'] or 0),
                    'input_cost': float(website['total_input_cost'] or 0),
                    'output_cost': float(website['total_output_cost'] or 0),
                    'embedding_cost': float(website['total_embedding_cost'] or 0),
                    'total_cost': float(website['total_cost'] or 0),
                    'chats': int(website['total_chats'] or 0),
                    'months_active': int(website['months_active'] or 0)
                }
                
                overall_totals['total_input_tokens'] += website_data['input_tokens']
                overall_totals['total_output_tokens'] += website_data['output_tokens']
                overall_totals['total_embedding_tokens'] += website_data['embedding_tokens']
                overall_totals['total_tokens'] += website_data['total_tokens']
                overall_totals['total_input_cost'] += website_data['input_cost']
                overall_totals['total_output_cost'] += website_data['output_cost']
                overall_totals['total_embedding_cost'] += website_data['embedding_cost']
                overall_totals['total_cost'] += website_data['total_cost']
                overall_totals['total_chats'] += website_data['chats']
                
                formatted_websites.append(website_data)
            
            return {
                'success': True,
                'user_id': user_id,
                'websites': formatted_websites,
                'overall_totals': overall_totals
            }
            
        except Exception as e:
            print(f"  Get user websites token details error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def archive_old_tokens(self, days: int = 90):
        """Archive token usage older than specified days"""
        try:
            archive_date = datetime.now() - timedelta(days=days)
            
            def _archive(cursor):
                cursor.execute('''
                    INSERT INTO token_usage_archive 
                    (website_id, user_id, token_type, tokens, cost, model, operation_type, metadata, created_at)
                    SELECT website_id, user_id, token_type, tokens, cost, model, operation_type, metadata, created_at
                    FROM token_usage
                    WHERE created_at < %s
                ''', (archive_date,))
                archived_count = cursor.rowcount
                
                cursor.execute('''
                    DELETE FROM token_usage
                    WHERE created_at < %s
                ''', (archive_date,))
                
                return archived_count
            
            archived_count = self.execute_with_retry(_archive)
            print(f" Archived {archived_count} old token records")
            return archived_count
            
        except Exception as e:
            print(f"  Archive old tokens error: {e}")
            return 0
    
    def recalculate_aggregates(self, website_id: Optional[str] = None):
        """Recalculate aggregates from raw token usage"""
        # Keep existing implementation...
        pass

# Singleton instance
token_counter = TokenCounter()