import sys
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    print("=" * 60)
    print("Testing Supabase PostgreSQL Connection")
    print("=" * 60)
    
    # Use user@project format for pooler
    host = os.getenv('DB_HOST')
    port = int(os.getenv('DB_PORT'))
    user = os.getenv('DB_USER')  # user@project
    password = os.getenv('DB_PASSWORD')
    database = os.getenv('DB_NAME')
    
    print(f"\n📋 Connection Details:")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Database: {database}")
    print(f"   User: {user}")
    
    print("\n🔌 Attempting to connect (Method 1: Pooler with user@project)...")
    
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=60,
            sslmode='require'
        )
        
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        
        print("✅ Connection successful!")
        print(f"   PostgreSQL version: {version[0][:50]}...")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        
        print("\n🔌 Attempting to connect (Method 2: Session Pooler)...")
        
        try:
            # Try with session pooler (direct host, port 5432)
            conn = psycopg2.connect(
                host="db.jkezidrdlxwakrhkaxpk.supabase.co",
                port=5432,
                user="postgres",
                password=password,
                database=database,
                connect_timeout=60,
                sslmode='require'
            )
            
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()
            
            print("✅ Connection successful with Session Pooler!")
            print(f"   PostgreSQL version: {version[0][:50]}...")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e2:
            print(f"❌ Session Pooler failed: {e2}")
        
        print("\n💡 Solutions:")
        print("   1. Go to Supabase Dashboard → Settings → Database")
        print("   2. Select 'Session pooler' from Connection Method")
        print("   3. OR Enable 'IPv4 add-on' for $10/month")
        print("   4. OR Ask network admin to enable IPv6")
        return False

if __name__ == "__main__":
    test_connection()