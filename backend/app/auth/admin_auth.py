
import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import socket

load_dotenv()

class AdminAuthService:
    def __init__(self):
        self.jwt_secret = os.getenv('JWT_SECRET')
        self.jwt_algorithm = os.getenv('JWT_ALGORITHM')
        self.jwt_expiry_hours = int(os.getenv('JWT_EXPIRY_HOURS', 24))
        
        # Database connection
        self.host = os.getenv('DB_HOST')
        self.port = int(os.getenv('DB_PORT'))
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.database = os.getenv('DB_NAME')
        self.schema = os.getenv('DB_SCHEMA')
        
        # Default admin credentials
        self.default_admin_email = os.getenv('DEFAULT_ADMIN_EMAIL')
        self.default_admin_password = os.getenv('DEFAULT_ADMIN_PASSWORD')
        
        try:
            self.initialize_admin_tables()
            self.create_default_admin()
        except Exception as e:
            print(f"⚠️ Admin initialization skipped (connection issue): {e}")
    
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
    
    def initialize_admin_tables(self):
        """Initialize admin tables"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(f"SET search_path TO {self.schema}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(" Admin tables verified successfully")
            
        except Exception as e:
            print(f"  Admin table initialization error: {e}")
            raise
    
    def create_default_admin(self):
        """Create default admin account from .env"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT id FROM admins WHERE email = %s", (self.default_admin_email,))
            if cursor.fetchone():
                print(f" Default admin already exists: {self.default_admin_email}")
                cursor.close()
                conn.close()
                return
            
            password_hash = self.hash_password(self.default_admin_password)
            
            cursor.execute('''
                INSERT INTO admins (email, full_name, password_hash, created_by, is_active)
                VALUES (%s, %s, %s, NULL, TRUE)
            ''', (
                self.default_admin_email,
                "System Administrator",
                password_hash
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f" Default admin created: {self.default_admin_email}")
            
        except Exception as e:
            print(f"  Default admin creation error: {e}")
    
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
    
    def create_access_token(self, admin_id: int, email: str) -> str:
        """Create JWT access token for admin"""
        payload = {
            'user_id': admin_id,
            'email': email,
            'user_type': 'admin',
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
    
    def login_admin(self, email: str, password: str) -> Dict[str, Any]:
        """Login admin"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT id, email, full_name, password_hash, is_active 
                FROM admins WHERE email = %s
            ''', (email,))
            admin = cursor.fetchone()
            
            if not admin:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin not found"}
            
            if not admin['is_active']:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin account is deactivated"}
            
            if not self.verify_password(password, admin['password_hash']):
                cursor.close()
                conn.close()
                return {"success": False, "error": "Invalid password"}
            
            token = self.create_access_token(admin['id'], admin['email'])
            
            cursor.execute('''
                INSERT INTO admin_sessions (admin_id, session_token, expires_at)
                VALUES (%s, %s, %s)
            ''', (
                admin['id'],
                token,
                datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "admin": {
                    "id": admin['id'],
                    "email": admin['email'],
                    "full_name": admin['full_name'],
                    "role": "admin"
                },
                "access_token": token,
                "message": "Admin login successful"
            }
            
        except Exception as e:
            print(f"  Admin login error: {e}")
            return {"success": False, "error": str(e)}
    
    def create_admin(self, admin_data: Dict[str, Any], created_by_admin_id: int) -> Dict[str, Any]:
        """Create a new admin account"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT id FROM admins WHERE email = %s", (admin_data['email'],))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin already exists with this email"}
            
            password_hash = self.hash_password(admin_data['password'])
            
            cursor.execute('''
                INSERT INTO admins (email, full_name, password_hash, created_by, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id
            ''', (
                admin_data['email'],
                admin_data['full_name'],
                password_hash,
                created_by_admin_id
            ))
            
            admin_id = cursor.fetchone()['id']
            
            cursor.execute('''
                SELECT a.*, creator.email as created_by_email, creator.full_name as created_by_name
                FROM admins a
                LEFT JOIN admins creator ON a.created_by = creator.id
                WHERE a.id = %s
            ''', (admin_id,))
            admin = cursor.fetchone()
            
            token = self.create_access_token(admin_id, admin['email'])
            
            cursor.execute('''
                INSERT INTO admin_sessions (admin_id, session_token, expires_at)
                VALUES (%s, %s, %s)
            ''', (
                admin_id,
                token,
                datetime.utcnow() + timedelta(hours=self.jwt_expiry_hours)
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "admin": {
                    "id": admin['id'],
                    "email": admin['email'],
                    "full_name": admin['full_name'],
                    "role": "admin",
                    "created_by": {
                        "id": created_by_admin_id,
                        "email": admin['created_by_email'],
                        "name": admin['created_by_name']
                    } if admin['created_by'] else None,
                    "created_at": admin['created_at']
                },
                "access_token": token,
                "message": "Admin created successfully"
            }
            
        except Exception as e:
            print(f"  Admin creation error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_admin_by_id(self, admin_id: int) -> Optional[Dict[str, Any]]:
        """Get admin by ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT a.*, creator.email as created_by_email, creator.full_name as created_by_name
                FROM admins a
                LEFT JOIN admins creator ON a.created_by = creator.id
                WHERE a.id = %s AND a.is_active = TRUE
            ''', (admin_id,))
            
            admin = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if admin:
                admin['role'] = 'admin'
            return admin
            
        except Exception as e:
            print(f"  Get admin error: {e}")
            return None
    
    def get_all_admins(self, current_admin_id: int = None) -> list:
        """Get all admins"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = '''
                SELECT a.*, creator.email as created_by_email, creator.full_name as created_by_name
                FROM admins a
                LEFT JOIN admins creator ON a.created_by = creator.id
                WHERE 1=1
            '''
            params = []
            
            if current_admin_id:
                query += " AND a.id != %s"
                params.append(current_admin_id)
            
            query += " ORDER BY a.created_at DESC"
            
            cursor.execute(query, params)
            admins = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            for admin in admins:
                admin['role'] = 'admin'
            
            return admins
            
        except Exception as e:
            print(f"  Get all admins error: {e}")
            return []
    
    def toggle_admin_status(self, admin_id: int, current_admin_id: int) -> Dict[str, Any]:
        """Toggle admin active status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("SELECT id, is_active FROM admins WHERE id = %s", (admin_id,))
            admin = cursor.fetchone()
            
            if not admin:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin not found"}
            
            if admin_id == current_admin_id:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Cannot deactivate your own account"}
            
            new_status = not admin['is_active']
            cursor.execute(
                "UPDATE admins SET is_active = %s WHERE id = %s",
                (new_status, admin_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "message": f"Admin {'activated' if new_status else 'deactivated'} successfully",
                "is_active": new_status
            }
            
        except Exception as e:
            print(f"  Toggle admin status error: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
admin_auth_service = AdminAuthService()