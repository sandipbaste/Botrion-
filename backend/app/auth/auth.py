
import os
import json
import jwt
import bcrypt
import secrets
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import socket
import time

load_dotenv()

class AuthService:
    def __init__(self):
        self.jwt_secret = os.getenv('JWT_SECRET')
        self.jwt_algorithm = os.getenv('JWT_ALGORITHM')
        self.jwt_expiry_hours = int(os.getenv('JWT_EXPIRY_HOURS', 24))
        self.otp_expiry_minutes = int(os.getenv('OTP_EXPIRY_MINUTES', 10))
        
        # Database connection
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT', 5432))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.schema = os.getenv('DB_SCHEMA', 'Botrion')
        
        try:
            self.initialize_user_tables()
        except Exception as e:
            print(f"⚠️ User table initialization skipped (connection issue): {e}")
            print("   Server will start but database features may not work until connection is restored")
    
    def get_connection(self):
        """Get database connection"""
        try:
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
            
            return conn
        except Exception as e:
            print(f"  Database connection error: {e}")
            raise


    def initialize_user_tables(self):
        """Initialize user tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Check if tables exist, if not they will be created by the schema.sql
            # We'll just ensure the schema exists
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(f"SET search_path TO {self.schema}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(" User tables verified successfully")
            
        except Exception as e:
            print(f"  User table initialization error: {e}")
            raise
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except:
            return False
    
    def create_access_token(self, user_id: int, email: str, user_type: str = 'user') -> str:
        """Create JWT access token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'user_type': user_type,
            'exp': datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours),
            'iat': datetime.utcnow()
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token
    
    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            print("  Token expired")
            return None
        except jwt.InvalidTokenError:
            print("  Invalid token")
            return None
    
    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP"""
        digits = "0123456789"
        otp = ''.join(random.choice(digits) for _ in range(length))
        return otp
    
    def initiate_password_reset(self, email: str) -> Dict[str, Any]:
        """Initiate password reset process for users"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            print(f" Looking for user with email: {email}")
            
            cursor.execute(
                "SELECT id, email, full_name FROM users WHERE email = %s AND is_active = TRUE",
                (email,)
            )
            user = cursor.fetchone()
            
            if not user:
                cursor.close()
                conn.close()
                print(f"  User not found: {email}")
                return {"success": False, "error": "User not found"}
            
            user_id = user['id']
            print(f" Found user: {user['full_name']} (ID: {user_id})")
            
            otp = self.generate_otp()
            print(f" Generated OTP: {otp}")
            
            reset_token = secrets.token_urlsafe(32)
            print(f" Generated reset token: {reset_token[:20]}...")
            
            expires_at = datetime.utcnow() + timedelta(minutes=self.otp_expiry_minutes)
            print(f" OTP expires at: {expires_at}")
            
            # Invalidate any existing reset tokens for this user
            cursor.execute(
                "UPDATE password_resets SET used = TRUE WHERE user_id = %s AND used = FALSE",
                (user_id,)
            )
            print(f"  Invalidated previous reset tokens for user {user_id}")
            
            cursor.execute('''
                INSERT INTO password_resets (user_id, reset_token, otp, expires_at, verified, used)
                VALUES (%s, %s, %s, %s, FALSE, FALSE)
                RETURNING id
            ''', (user_id, reset_token, otp, expires_at))
            
            reset_id = cursor.fetchone()['id']
            print(f" Saved reset request with ID: {reset_id}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": "Password reset initiated",
                "reset_token": reset_token,
                "otp": otp,
                "expires_at": expires_at.isoformat(),
                "user": {
                    "id": user_id,
                    "email": user['email'],
                    "full_name": user['full_name']
                }
            }
            
        except Exception as e:
            print(f"  Password reset initiation error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def verify_otp(self, reset_token: str, otp: str) -> Dict[str, Any]:
        """Verify OTP for password reset"""
        try:
            print(f"\n Verifying OTP...")
            print(f"  Reset Token: {reset_token[:20]}...")
            print(f"  OTP to verify: {otp}")
            
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            print(f" Searching for reset token in database...")
            cursor.execute('''
                SELECT pr.*, u.email, u.full_name
                FROM password_resets pr
                JOIN users u ON pr.user_id = u.id
                WHERE pr.reset_token = %s 
                AND pr.used = FALSE 
                AND pr.verified = FALSE
                AND pr.expires_at > CURRENT_TIMESTAMP
            ''', (reset_token,))
            
            reset_request = cursor.fetchone()
            
            if not reset_request:
                print(f"  Reset token not found or invalid")
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid or expired reset token"}
            
            print(f" Found reset request:")
            print(f"   ID: {reset_request['id']}")
            print(f"   User: {reset_request['full_name']}")
            print(f"   Stored OTP: {reset_request['otp']}")
            print(f"   Input OTP: {otp}")
            print(f"   Expires at: {reset_request['expires_at']}")
            
            if reset_request['otp'] != otp:
                print(f"  OTP mismatch!")
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid OTP"}
            
            print(f" OTP matched!")
            
            cursor.execute('''
                UPDATE password_resets 
                SET verified = TRUE 
                WHERE id = %s
            ''', (reset_request['id'],))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f" OTP verified successfully!")
            
            return {
                "success": True,
                "message": "OTP verified successfully",
                "reset_token": reset_token,
                "user": {
                    "id": reset_request['user_id'],
                    "email": reset_request['email'],
                    "full_name": reset_request['full_name']
                }
            }
            
        except Exception as e:
            print(f"  OTP verification error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    def reset_password(self, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Reset password using verified reset token"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT pr.*, u.id as user_id, u.email
                FROM password_resets pr
                JOIN users u ON pr.user_id = u.id
                WHERE pr.reset_token = %s 
                AND pr.used = FALSE 
                AND pr.verified = TRUE
                AND pr.expires_at > CURRENT_TIMESTAMP
                AND u.is_active = TRUE
            ''', (reset_token,))
            
            reset_request = cursor.fetchone()
            
            if not reset_request:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid or expired reset token"}
            
            user_id = reset_request['user_id']
            
            new_password_hash = self.hash_password(new_password)
            
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (new_password_hash, user_id)
            )
            
            cursor.execute(
                "UPDATE password_resets SET used = TRUE WHERE id = %s",
                (reset_request['id'],)
            )
            
            cursor.execute(
                "DELETE FROM user_sessions WHERE user_id = %s",
                (user_id,)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": "Password reset successfully",
                "user": {
                    "id": user_id,
                    "email": reset_request['email']
                }
            }
            
        except Exception as e:
            print(f"  Password reset error: {e}")
            return {"success": False, "error": str(e)}
    
    def register_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new regular user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(
                "SELECT id FROM users WHERE email = %s",
                (user_data['email'],)
            )
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return {"success": False, "error": "User already exists with this email"}
            
            password_hash = self.hash_password(user_data['password'])
            
            cursor.execute('''
                INSERT INTO users (email, full_name, mobile, password_hash)
                VALUES (%s, %s, %s, %s)
                RETURNING id, email, full_name, mobile
            ''', (
                user_data['email'],
                user_data['full_name'],
                user_data.get('mobile', ''),
                password_hash
            ))
            
            user = cursor.fetchone()
            user_id = user['id']
            
            token = self.create_access_token(user_id, user['email'], 'user')
            
            cursor.execute('''
                INSERT INTO user_sessions (user_id, session_token, expires_at)
                VALUES (%s, %s, %s)
            ''', (
                user_id,
                token,
                datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "user": {
                    "id": user['id'],
                    "email": user['email'],
                    "full_name": user['full_name'],
                    "mobile": user['mobile'],
                    "role": "user"
                },
                "access_token": token,
                "message": "User registered successfully"
            }
            
        except Exception as e:
            print(f"  User registration error: {e}")
            return {"success": False, "error": str(e)}
    
    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Login regular user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT id, email, full_name, mobile, password_hash, is_active 
                FROM users WHERE email = %s
            ''', (email,))
            user = cursor.fetchone()
            
            if not user:
                cursor.close()
                conn.close()
                return {"success": False, "error": "User not found"}
            
            if not user['is_active']:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Account is deactivated"}
            
            if not self.verify_password(password, user['password_hash']):
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid password"}
            
            token = self.create_access_token(user['id'], user['email'], 'user')
            
            cursor.execute('''
                INSERT INTO user_sessions (user_id, session_token, expires_at)
                VALUES (%s, %s, %s)
            ''', (
                user['id'],
                token,
                datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "user": {
                    "id": user['id'],
                    "email": user['email'],
                    "full_name": user['full_name'],
                    "mobile": user['mobile'],
                    "role": "user"
                },
                "access_token": token,
                "message": "Login successful"
            }
            
        except Exception as e:
            print(f"  Login error: {e}")
            return {"success": False, "error": str(e)}
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify token and get user info"""
        try:
            payload = self.verify_access_token(token)
            if not payload:
                return {"success": False, "error": "Invalid or expired token"}
            
            user_type = payload.get('user_type', 'user')
            user_id = payload['user_id']
            
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            if user_type == 'user':
                cursor.execute('''
                    SELECT s.*, u.email, u.full_name, u.is_active
                    FROM user_sessions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.session_token = %s AND s.expires_at > CURRENT_TIMESTAMP AND u.is_active = TRUE
                    AND u.id = %s
                ''', (token, user_id))
            elif user_type == 'admin':
                cursor.execute('''
                    SELECT s.*, a.email, a.full_name, a.is_active
                    FROM admin_sessions s
                    JOIN admins a ON s.admin_id = a.id
                    WHERE s.session_token = %s AND s.expires_at > CURRENT_TIMESTAMP AND a.is_active = TRUE
                    AND a.id = %s
                ''', (token, user_id))
            else:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid user type"}
            
            session = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if not session:
                return {"success": False, "error": "Session expired or invalid"}
            
            return {
                "success": True,
                "user": {
                    "id": payload['user_id'],
                    "email": payload['email'],
                    "role": payload.get('user_type', 'user'),
                    "exp": payload['exp']
                }
            }
            
        except Exception as e:
            print(f"  Token verification error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT id, email, full_name, mobile, website_ids, created_at,
                    subscription_plan, subscription_end_date, is_active
                FROM users WHERE id = %s
            ''', (user_id,))
            
            user = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if user:
                user['role'] = 'user'
                if user.get('website_ids'):
                    try:
                        user['website_ids'] = json.loads(user['website_ids'])
                    except:
                        user['website_ids'] = []
                else:
                    user['website_ids'] = []
            return user
            
        except Exception as e:
            print(f"  Get user error: {e}")
            return None
    
    def add_website_to_user(self, user_id: int, website_id: str) -> Dict[str, Any]:
        """Add a website ID to user's website_ids list"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT website_ids FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                conn.close()
                return {"success": False, "error": "User not found"}
            
            current_website_ids = []
            if result[0]:
                try:
                    current_website_ids = json.loads(result[0])
                except:
                    current_website_ids = []
            
            if website_id not in current_website_ids:
                current_website_ids.append(website_id)
                
                cursor.execute(
                    "UPDATE users SET website_ids = %s WHERE id = %s",
                    (json.dumps(current_website_ids), user_id)
                )
                conn.commit()
                updated = True
            else:
                updated = False
            
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "updated": updated,
                "message": f"Website ID {'added' if updated else 'already exists'}",
                "website_ids": current_website_ids
            }
            
        except Exception as e:
            print(f"  Add website to user error: {e}")
            return {"success": False, "error": str(e)}
    
    def remove_website_from_user(self, user_id: int, website_id: str):
        """Remove website ID from user's website_ids array"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT website_ids FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                website_ids = result[0]
                if isinstance(website_ids, str):
                    try:
                        website_ids = json.loads(website_ids)
                    except:
                        website_ids = website_ids.split(',') if website_ids else []
                
                if website_id in website_ids:
                    website_ids.remove(website_id)
                
                cursor.execute(
                    "UPDATE users SET website_ids = %s WHERE id = %s",
                    (json.dumps(website_ids), user_id)
                )
                conn.commit()
                print(f" Removed website {website_id} from user {user_id}")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"  Error removing website from user: {e}")
            return False
    
    def get_user_websites_detailed(self, user_id: int) -> list:
        """Get detailed website information for a user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT website_ids FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result or not result['website_ids']:
                cursor.close()
                conn.close()
                return []
            
            try:
                website_ids = json.loads(result['website_ids'])
            except:
                website_ids = []
            
            if not website_ids:
                cursor.close()
                conn.close()
                return []
            
            websites = []
            for website_id in website_ids:
                cursor.execute('''
                    SELECT w.*, 
                        (SELECT COUNT(*) FROM contact_forms WHERE website_id = w.website_id) as contact_forms_count,
                        (SELECT COUNT(*) FROM chat_history WHERE website_id = w.website_id) as chat_messages_count,
                        (SELECT COUNT(*) FROM website_files WHERE website_id = w.website_id) as files_count
                    FROM websites w
                    WHERE w.website_id = %s
                ''', (website_id,))
                
                website = cursor.fetchone()
                if website:
                    websites.append(website)
            
            cursor.close()
            conn.close()
            
            return websites
            
        except Exception as e:
            print(f"  Get user websites detailed error: {e}")
            return []
    
    def toggle_user_status(self, user_id: int, current_user_id: int) -> Dict[str, Any]:
        """Toggle user active status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT id, is_active FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                cursor.close()
                conn.close()
                return {"success": False, "error": "User not found"}
            
            if user_id == current_user_id:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Cannot deactivate your own account"}
            
            new_status = not user['is_active']
            cursor.execute(
                "UPDATE users SET is_active = %s WHERE id = %s",
                (new_status, user_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": f"User {'activated' if new_status else 'deactivated'} successfully",
                "is_active": new_status
            }
            
        except Exception as e:
            print(f"  Toggle user status error: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
auth_service = AuthService()