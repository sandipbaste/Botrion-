import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

class DatabaseManager:
    def __init__(self):
        # PostgreSQL connection details
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT'))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.schema = os.getenv('DB_SCHEMA')
        self.connection = None
        
        print(f" DatabaseManager initialized with PostgreSQL (Schema: {self.schema})")

    def get_connection(self):
        """Get PostgreSQL database connection"""
        try:
            if self.connection is None or self.connection.closed:
                self.connection = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    options=f'-c search_path={self.schema}'
                )
                self.connection.autocommit = True
            return self.connection
        except Exception as e:
            print(f"  Database connection error: {e}")
            raise
    
    def get_cursor(self, dict_cursor=True):
        """Get database cursor"""
        conn = self.get_connection()
        if dict_cursor:
            return conn.cursor(cursor_factory=RealDictCursor)
        return conn.cursor()
    
    def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
        """Execute query and return results"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(query, params or ())
            
            result = None
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            
            cursor.close()
            return result
            
        except Exception as e:
            print(f"  Query execution error: {e}")
            raise

    # =========================
    # WEBSITE MANAGEMENT
    # =========================
    def save_website(self, website_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save website information to database - PostgreSQL"""
        try:
            query = """
                INSERT INTO websites 
                (website_id, website_name, website_url, script_tag, admin_email, 
                 contact_email, data_directory, status, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (website_id) 
                DO UPDATE SET
                    website_name = EXCLUDED.website_name,
                    website_url = EXCLUDED.website_url,
                    script_tag = EXCLUDED.script_tag,
                    admin_email = EXCLUDED.admin_email,
                    contact_email = EXCLUDED.contact_email,
                    data_directory = EXCLUDED.data_directory,
                    status = EXCLUDED.status,
                    user_id = EXCLUDED.user_id,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
            """
            
            values = (
                website_data['website_id'],
                website_data.get('website_name', ''),
                website_data.get('website_url', ''),
                website_data.get('script_tag', ''),
                website_data.get('admin_email', ''),
                website_data.get('contact_email', ''),
                website_data.get('data_directory', ''),
                website_data.get('status', 'active'),
                website_data.get('user_id', None)
            )
            
            result = self.execute_query(query, values, fetch_one=True)
            return result
            
        except Exception as e:
            print(f"  Error saving website: {e}")
            raise

    def save_website_with_user(self, website_data: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        """Save website information with user ID"""
        website_data['user_id'] = user_id
        return self.save_website(website_data)

    def get_website(self, website_id: str) -> Optional[Dict[str, Any]]:
        """Get website by ID"""
        try:
            query = "SELECT * FROM websites WHERE website_id = %s"
            return self.execute_query(query, (website_id,), fetch_one=True)
        except Exception as e:
            print(f"  Error getting website: {e}")
            return None

    def get_all_websites(self) -> List[Dict[str, Any]]:
        """Get all websites"""
        try:
            query = "SELECT * FROM websites ORDER BY created_at DESC"
            return self.execute_query(query, fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting websites: {e}")
            return []

    def update_website_script(self, website_id: str, script_tag: str) -> bool:
        """Update website script tag"""
        try:
            query = "UPDATE websites SET script_tag = %s WHERE website_id = %s"
            self.execute_query(query, (script_tag, website_id))
            return True
        except Exception as e:
            print(f"  Error updating website script: {e}")
            return False

    # =========================
    # TRAINING LOGS MANAGEMENT
    # =========================
    def save_training_log(self, website_id: str, log_data: Dict[str, Any]) -> int:
        """Save training log with training time"""
        try:
            query = """
                INSERT INTO training_logs 
                (website_id, status, message, data_points, embedding_count, training_time)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            training_time = float(log_data.get('training_time', 0.0))
            
            values = (
                website_id,
                log_data.get('status', 'started'),
                log_data.get('message', ''),
                log_data.get('data_points', 0),
                log_data.get('embedding_count', 0),
                training_time
            )
            
            result = self.execute_query(query, values, fetch_one=True)
            return result['id'] if result else 0
            
        except Exception as e:
            print(f"  Error saving training log: {e}")
            raise

    def update_training_time(self, website_id: str, training_time: float) -> bool:
        """Update training time for the latest training log"""
        try:
            query = """
                UPDATE training_logs 
                SET training_time = %s 
                WHERE id = (
                    SELECT id FROM training_logs 
                    WHERE website_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                )
            """
            self.execute_query(query, (training_time, website_id))
            return True
        except Exception as e:
            print(f"  Error updating training time: {e}")
            return False

    def get_training_logs(self, website_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get training logs for a website"""
        try:
            query = """
                SELECT * FROM training_logs 
                WHERE website_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """
            return self.execute_query(query, (website_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting training logs: {e}")
            return []

    # =========================
    # CONTACT FORM MANAGEMENT
    # =========================
    def save_contact_form(self, website_id: str, form_data: Dict[str, Any]) -> int:
        """Save contact form submission"""
        try:
            query = """
                INSERT INTO contact_forms 
                (website_id, name, email, phone, message, form_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            values = (
                website_id,
                form_data.get('name', ''),
                form_data.get('email', ''),
                form_data.get('phone', ''),
                form_data.get('message', ''),
                json.dumps(form_data)
            )
            
            result = self.execute_query(query, values, fetch_one=True)
            return result['id'] if result else 0
            
        except Exception as e:
            print(f"  Error saving contact form: {e}")
            raise

    def get_contact_forms(self, website_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get contact forms for a website"""
        try:
            query = """
                SELECT * FROM contact_forms 
                WHERE website_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """
            return self.execute_query(query, (website_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting contact forms: {e}")
            return []

    # =========================
    # CHAT HISTORY MANAGEMENT
    # =========================
    def save_chat_message(self, chat_data: Dict[str, Any]) -> int:
        """Save a single chat message"""
        try:
            query = """
                INSERT INTO chat_history 
                (website_id, conversation_id, session_id, user_id, user_name, user_email, 
                 user_phone, role, message, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            website_id = chat_data.get('website_id')
            conversation_id = chat_data.get('conversation_id', '')
            session_id = chat_data.get('session_id', '')
            user_id = chat_data.get('user_id', '')
            user_name = chat_data.get('user_name', '')
            user_email = chat_data.get('user_email', '')
            user_phone = chat_data.get('user_phone', '')
            role = chat_data.get('role', 'user')
            message = chat_data.get('message', '')
            metadata = json.dumps(chat_data.get('metadata', {}))
            
            values = (
                website_id,
                conversation_id,
                session_id,
                str(user_id) if user_id else '',
                user_name,
                user_email,
                user_phone,
                role,
                message,
                metadata
            )
            
            result = self.execute_query(query, values, fetch_one=True)
            return result['id'] if result else 0
            
        except Exception as e:
            print(f"  Error saving chat message: {e}")
            import traceback
            traceback.print_exc()
            raise

    def get_chat_history(self, website_id: str, conversation_id: str = None, 
                        limit: int = 50) -> List[Dict[str, Any]]:
        """Get chat history for a website or conversation"""
        try:
            if conversation_id:
                query = """
                    SELECT * FROM chat_history 
                    WHERE website_id = %s AND conversation_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                """
                return self.execute_query(query, (website_id, conversation_id, limit), fetch_all=True) or []
            else:
                query = """
                    SELECT * FROM chat_history 
                    WHERE website_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """
                return self.execute_query(query, (website_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting chat history: {e}")
            return []

    def get_conversations(self, website_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all conversations for a website"""
        try:
            query = """
                SELECT DISTINCT conversation_id, 
                       MAX(created_at) as last_activity,
                       COUNT(*) as message_count,
                       MAX(user_name) as user_name,
                       MAX(user_email) as user_email
                FROM chat_history 
                WHERE website_id = %s
                GROUP BY conversation_id
                ORDER BY last_activity DESC
                LIMIT %s
            """
            return self.execute_query(query, (website_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting conversations: {e}")
            return []

    def get_full_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get full conversation by conversation ID"""
        try:
            query = """
                SELECT * FROM chat_history 
                WHERE conversation_id = %s
                ORDER BY created_at ASC
            """
            return self.execute_query(query, (conversation_id,), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting conversation: {e}")
            return []

    def get_chat_history_by_session(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get chat history by session ID"""
        try:
            query = """
                SELECT * FROM chat_history 
                WHERE session_id = %s
                ORDER BY created_at ASC
                LIMIT %s
            """
            return self.execute_query(query, (session_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting chat history by session: {e}")
            return []

    def get_conversation_messages(self, conversation_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get chat messages by conversation ID"""
        try:
            query = """
                SELECT * FROM chat_history 
                WHERE conversation_id = %s
                ORDER BY created_at ASC
                LIMIT %s
            """
            return self.execute_query(query, (conversation_id, limit), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting conversation messages: {e}")
            return []

    # =========================
    # FILE MANAGEMENT
    # =========================
    def save_file_record(self, website_id: str, file_data: Dict[str, Any]) -> int:
        """Save file upload record"""
        try:
            query = """
                INSERT INTO website_files 
                (website_id, filename, file_path, file_type, file_size, 
                 upload_type, processed, chunk_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            values = (
                website_id,
                file_data.get('filename', ''),
                file_data.get('file_path', ''),
                file_data.get('file_type', ''),
                file_data.get('file_size', 0),
                file_data.get('upload_type', 'user_upload'),
                file_data.get('processed', False),
                file_data.get('chunk_count', 0)
            )
            
            result = self.execute_query(query, values, fetch_one=True)
            return result['id'] if result else 0
            
        except Exception as e:
            print(f"  Error saving file record: {e}")
            raise

    def get_website_files(self, website_id: str, file_type: str = None) -> List[Dict[str, Any]]:
        """Get files for a website"""
        try:
            if file_type:
                query = """
                    SELECT * FROM website_files 
                    WHERE website_id = %s AND file_type = %s
                    ORDER BY created_at DESC
                """
                return self.execute_query(query, (website_id, file_type), fetch_all=True) or []
            else:
                query = """
                    SELECT * FROM website_files 
                    WHERE website_id = %s
                    ORDER BY created_at DESC
                """
                return self.execute_query(query, (website_id,), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting website files: {e}")
            return []

    # =========================
    # USER MANAGEMENT
    # =========================
    def get_user_websites(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all websites for a specific user"""
        try:
            query = """
                SELECT * FROM websites 
                WHERE user_id = %s
                ORDER BY created_at DESC
            """
            return self.execute_query(query, (user_id,), fetch_all=True) or []
        except Exception as e:
            print(f"  Error getting user websites: {e}")
            return []

    def get_website_with_owner(self, website_id: str) -> Optional[Dict[str, Any]]:
        """Get website with owner info"""
        try:
            query = """
                SELECT w.*, u.email as owner_email, u.full_name as owner_name
                FROM websites w
                LEFT JOIN users u ON w.user_id = u.id
                WHERE w.website_id = %s
            """
            return self.execute_query(query, (website_id,), fetch_one=True)
        except Exception as e:
            print(f"  Error getting website with owner: {e}")
            return None

    # =========================
    # STATISTICS
    # =========================
    def get_website_stats(self, website_id: str) -> Dict[str, Any]:
        """Get website statistics"""
        try:
            stats = {}
            
            # Total contact forms
            query1 = "SELECT COUNT(*) as count FROM contact_forms WHERE website_id = %s"
            result = self.execute_query(query1, (website_id,), fetch_one=True)
            stats['contact_forms'] = result['count'] if result else 0
            
            # Total chat messages
            query2 = "SELECT COUNT(*) as count FROM chat_history WHERE website_id = %s"
            result = self.execute_query(query2, (website_id,), fetch_one=True)
            stats['chat_messages'] = result['count'] if result else 0
            
            # Total conversations
            query3 = """
                SELECT COUNT(DISTINCT conversation_id) as count FROM chat_history 
                WHERE website_id = %s
            """
            result = self.execute_query(query3, (website_id,), fetch_one=True)
            stats['conversations'] = result['count'] if result else 0
            
            # Total files
            query4 = "SELECT COUNT(*) as count FROM website_files WHERE website_id = %s"
            result = self.execute_query(query4, (website_id,), fetch_one=True)
            stats['files'] = result['count'] if result else 0
            
            # Latest training time
            query5 = """
                SELECT training_time, created_at 
                FROM training_logs 
                WHERE website_id = %s AND status = 'completed'
                ORDER BY created_at DESC 
                LIMIT 1
            """
            result = self.execute_query(query5, (website_id,), fetch_one=True)
            if result:
                stats['latest_training_time'] = result['training_time']
                stats['last_trained'] = result['created_at']
            
            return stats
            
        except Exception as e:
            print(f"  Error getting website stats: {e}")
            return {}

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics for a user"""
        try:
            stats = {}
            
            # Total websites
            query1 = "SELECT COUNT(*) as count FROM websites WHERE user_id = %s"
            result = self.execute_query(query1, (user_id,), fetch_one=True)
            stats['total_websites'] = result['count'] if result else 0
            
            # Active websites
            query2 = "SELECT COUNT(*) as count FROM websites WHERE user_id = %s AND status = 'active'"
            result = self.execute_query(query2, (user_id,), fetch_one=True)
            stats['active_websites'] = result['count'] if result else 0
            
            # Total contact forms
            query3 = """
                SELECT COUNT(*) as count FROM contact_forms cf
                JOIN websites w ON cf.website_id = w.website_id
                WHERE w.user_id = %s
            """
            result = self.execute_query(query3, (user_id,), fetch_one=True)
            stats['contact_forms'] = result['count'] if result else 0
            
            # Total chat messages
            query4 = """
                SELECT COUNT(*) as count FROM chat_history ch
                JOIN websites w ON ch.website_id = w.website_id
                WHERE w.user_id = %s
            """
            result = self.execute_query(query4, (user_id,), fetch_one=True)
            stats['chat_messages'] = result['count'] if result else 0
            
            # Total conversations
            query5 = """
                SELECT COUNT(DISTINCT conversation_id) as count FROM chat_history ch
                JOIN websites w ON ch.website_id = w.website_id
                WHERE w.user_id = %s
            """
            result = self.execute_query(query5, (user_id,), fetch_one=True)
            stats['conversations'] = result['count'] if result else 0
            
            # Total files
            query6 = """
                SELECT COUNT(*) as count FROM website_files wf
                JOIN websites w ON wf.website_id = w.website_id
                WHERE w.user_id = %s
            """
            result = self.execute_query(query6, (user_id,), fetch_one=True)
            stats['files'] = result['count'] if result else 0
            
            return stats
            
        except Exception as e:
            print(f"  Error getting user stats: {e}")
            return {}

    def get_admin_stats(self) -> Dict[str, Any]:
        """Get admin dashboard statistics"""
        try:
            stats = {}
            
            # Total users
            query1 = "SELECT COUNT(*) as count FROM users WHERE role = 'user'"
            result = self.execute_query(query1, fetch_one=True)
            stats['total_users'] = result['count'] if result else 0
            
            # Total admins
            query2 = "SELECT COUNT(*) as count FROM users WHERE role = 'admin'"
            result = self.execute_query(query2, fetch_one=True)
            stats['total_admins'] = result['count'] if result else 0
            
            # Total websites
            query3 = "SELECT COUNT(*) as count FROM websites"
            result = self.execute_query(query3, fetch_one=True)
            stats['total_websites'] = result['count'] if result else 0
            
            # Active websites
            query4 = "SELECT COUNT(*) as count FROM websites WHERE status = 'active'"
            result = self.execute_query(query4, fetch_one=True)
            stats['active_websites'] = result['count'] if result else 0
            
            # Today's activity
            query5 = "SELECT COUNT(*) as count FROM websites WHERE DATE(created_at) = CURRENT_DATE"
            result = self.execute_query(query5, fetch_one=True)
            stats['websites_today'] = result['count'] if result else 0
            
            query6 = "SELECT COUNT(*) as count FROM contact_forms WHERE DATE(created_at) = CURRENT_DATE"
            result = self.execute_query(query6, fetch_one=True)
            stats['forms_today'] = result['count'] if result else 0
            
            query7 = "SELECT COUNT(*) as count FROM chat_history WHERE DATE(created_at) = CURRENT_DATE"
            result = self.execute_query(query7, fetch_one=True)
            stats['messages_today'] = result['count'] if result else 0
            
            # Recent activity (last 7 days)
            query8 = """
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM websites 
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """
            stats['recent_websites'] = self.execute_query(query8, fetch_all=True) or []
            
            # Average training time
            query9 = """
                SELECT COALESCE(AVG(training_time), 0) as avg_training_time
                FROM training_logs 
                WHERE status = 'completed' AND training_time > 0
            """
            result = self.execute_query(query9, fetch_one=True)
            avg_time = result['avg_training_time'] if result else 0
            stats['avg_training_time'] = round(float(avg_time), 2) if avg_time else 0
            
            return stats
            
        except Exception as e:
            print(f"  Error getting admin stats: {e}")
            return {}

    def reconnect(self):
        """Reconnect to database"""
        try:
            if self.connection and not self.connection.closed:
                self.connection.close()
            
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                options=f'-c search_path={self.schema}'
            )
            self.connection.autocommit = True
            return True
        except Exception as e:
            print(f"  Database reconnection error: {e}")
            return False

    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None

# Singleton instance
db_manager = DatabaseManager()