
import os
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import socket
import time

load_dotenv()

# Pydantic models for requests
class CreateAdminRequest(BaseModel):
    email: str
    full_name: str
    password: str

class GenerateHashRequest(BaseModel):
    password: str

class AdminService:
    def __init__(self):
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
            print(f"⚠️ Admin service initialization skipped (connection issue): {e}")
    
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
        """Initialize admin tables - PostgreSQL version"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create schema if not exists
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(f"SET search_path TO {self.schema}")
            
            # Create admins table - PostgreSQL syntax
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    full_name VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_by INT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_admin_created_by FOREIGN KEY (created_by) 
                        REFERENCES admins(id) ON DELETE SET NULL
                )
            ''')
            
            # Create admin_sessions table - PostgreSQL syntax
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    id SERIAL PRIMARY KEY,
                    admin_id INT NOT NULL,
                    session_token VARCHAR(500) NOT NULL,
                    device_info TEXT,
                    ip_address VARCHAR(100),
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_admin_sessions_admin FOREIGN KEY (admin_id) 
                        REFERENCES admins(id) ON DELETE CASCADE
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admins_email ON admins(email)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admins_active ON admins(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_sessions_admin_id ON admin_sessions(admin_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_sessions_token ON admin_sessions(session_token)')
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(" Admin tables initialized successfully (PostgreSQL)")
            
        except Exception as e:
            print(f"  Admin table initialization error: {e}")
            raise
    
    def create_default_admin(self):
        """Create default admin account from .env"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if default admin already exists
            cursor.execute("SELECT id FROM admins WHERE email = %s", (self.default_admin_email,))
            if cursor.fetchone():
                print(f" Default admin already exists: {self.default_admin_email}")
                cursor.close()
                conn.close()
                return
            
            # Hash default password
            password_hash = self.hash_password(self.default_admin_password)
            
            # Insert default admin
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
            print(f" Password: {self.default_admin_password}")
            print(" Please change the default password after first login!")
            
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
    
    def create_admin(self, admin_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new admin account"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if admin already exists
            cursor.execute("SELECT id FROM admins WHERE email = %s", (admin_data['email'],))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin already exists with this email"}
            
            # Hash password
            password_hash = self.hash_password(admin_data['password'])
            
            # Insert admin
            cursor.execute('''
                INSERT INTO admins (email, full_name, password_hash, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id, email, full_name, created_at
            ''', (
                admin_data['email'],
                admin_data['full_name'],
                password_hash
            ))
            
            admin = cursor.fetchone()
            
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
                    "created_at": admin['created_at']
                },
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
                SELECT * FROM admins 
                WHERE id = %s AND is_active = TRUE
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
    
    def get_all_admins(self) -> list:
        """Get all admins"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('''
                SELECT * FROM admins 
                ORDER BY created_at DESC
            ''')
            
            admins = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            for admin in admins:
                admin['role'] = 'admin'
            
            return admins
            
        except Exception as e:
            print(f"  Get all admins error: {e}")
            return []
    
    def toggle_admin_status(self, admin_id: int) -> Dict[str, Any]:
        """Toggle admin active status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if admin exists
            cursor.execute("SELECT id, is_active FROM admins WHERE id = %s", (admin_id,))
            admin = cursor.fetchone()
            
            if not admin:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin not found"}
            
            # Toggle status
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
    
    def update_admin_profile(self, admin_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update admin profile"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Build update query
            update_fields = []
            params = []
            
            if 'full_name' in update_data:
                update_fields.append("full_name = %s")
                params.append(update_data['full_name'])
            
            if 'email' in update_data:
                # Check if email already exists
                cursor.execute(
                    "SELECT id FROM admins WHERE email = %s AND id != %s",
                    (update_data['email'], admin_id)
                )
                if cursor.fetchone():
                    cursor.close()
                    conn.close()
                    return {"success": False, "error": "Email already in use"}
                
                update_fields.append("email = %s")
                params.append(update_data['email'])
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                query = f"UPDATE admins SET {', '.join(update_fields)} WHERE id = %s"
                params.append(admin_id)
                
                cursor.execute(query, params)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {"success": True, "message": "Profile updated successfully"}
            
        except Exception as e:
            print(f"  Update admin profile error: {e}")
            return {"success": False, "error": str(e)}
    
    def change_admin_password(self, admin_id: int, current_password: str, new_password: str) -> Dict[str, Any]:
        """Change admin password"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get current password hash
            cursor.execute("SELECT password_hash FROM admins WHERE id = %s", (admin_id,))
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                conn.close()
                return {"success": False, "error": "Admin not found"}
            
            # Verify current password
            if not self.verify_password(current_password, result['password_hash']):
                cursor.close()
                conn.close()
                return {"success": False, "error": "Current password is incorrect"}
            
            # Update password
            new_hash = self.hash_password(new_password)
            cursor.execute(
                "UPDATE admins SET password_hash = %s WHERE id = %s",
                (new_hash, admin_id)
            )
            
            # Invalidate all sessions
            cursor.execute("DELETE FROM admin_sessions WHERE admin_id = %s", (admin_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {"success": True, "message": "Password changed successfully"}
            
        except Exception as e:
            print(f"  Change admin password error: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_password_hash(self, password: str) -> Dict[str, Any]:
        """Generate password hash for display purposes"""
        try:
            password_hash = self.hash_password(password)
            return {
                "success": True,
                "password_hash": password_hash,
                "message": "Password hash generated successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_user_growth_data(self) -> Dict[str, Any]:
        """Get user growth data for charts"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get daily user registrations for the last 30 days
            cursor.execute('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count
                FROM users
                WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            ''')
            
            daily_growth = cursor.fetchall()
            
            # Get total users count
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            # Get active users (users with at least one website)
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count 
                FROM websites
            """)
            active_users = cursor.fetchone()['count']
            
            cursor.close()
            conn.close()
            
            return {
                "success": True,
                "daily_growth": daily_growth,
                "total_users": total_users,
                "active_users": active_users
            }
            
        except Exception as e:
            print(f"  Get user growth data error: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
admin_service = AdminService()