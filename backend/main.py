import os
import json
import sys
import warnings
import threading
from datetime import datetime
from dotenv import load_dotenv
import uvicorn

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Add parent directory to path to allow absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Now use absolute imports
from app.vectoredb.website_loader import WebsiteLoader
from app.file_processor import FileProcessor
from app.vectoredb.embedding_handler import EmbeddingHandler
from app.chatbot_generator import ChatbotGenerator
from app.agents.agents import ChatAgent
from app.database.database import db_manager
from app.services.email_service import email_service
from app.pdf_generator import pdf_generator
from app.auth.auth import auth_service
from app.services.payment_service import payment_service
from app.auth.addAdmin import admin_service
from app.auth.admin_auth import admin_auth_service
from app.tokens.token_counter import token_counter
from app.vectoredb.vector_store import VectorStore

# Import API routes - try multiple paths
try:
    from app.api import api_router
except ImportError:
    try:
        from app.api.init import api_router
    except ImportError:
        from backend.app.api import api_router

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL").rstrip('/')
FRONTEND_URL = os.getenv("FRONTEND_URL").rstrip('/')

# Create FastAPI app
app = FastAPI(
    title="Chatbot Generator API",
    description="API for generating AI chatbots trained on website content with MySQL database and email notifications",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    servers=[
        {
            "url": BACKEND_URL,
            "description": "Current server"
        }
    ]
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "https://botrion-v2.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount static files
os.makedirs("generated_scripts", exist_ok=True)
app.mount("/scripts", StaticFiles(directory="generated_scripts"), name="scripts")

os.makedirs("data", exist_ok=True)
app.mount("/data", StaticFiles(directory="data"), name="data")

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Initialize admin tables
try:
    admin_service.initialize_admin_tables()
except Exception as e:
    print(f"⚠️ Admin tables initialization error: {e}")

# Include API routers
app.include_router(api_router)

# Global variables for WebSocket (if needed)
auto_reported_sessions = set()

# ======================
# ROOT ENDPOINT
# ======================

@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "success": True,
        "message": "🤖 Chatbot Generator API v3.0",
        "version": "3.0.0",
        "status": "running",
        "database": "PostgreSQL",
        "email": "Enabled",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "/api/docs": "API Documentation",
            "/api/redoc": "ReDoc Documentation",
            "/embed/{id}/script.js": "Chatbot Script",
            "/test/{id}": "Test Chatbot Page",
            "/api/auth": "Authentication endpoints",
            "/api/chat": "Chat endpoints",
            "/api/contact": "Contact form endpoints",
            "/api/payments": "Payment endpoints",
            "/api/training": "Training endpoints",
            "/api/uploads": "Upload endpoints",
            "/api/user": "User endpoints",
            "/api/websites": "Website management endpoints",
            "/api/admin": "Admin endpoints"
        }
    }

# ======================
# EMBED SCRIPT ROUTE - FIX 404
# ======================

@app.get("/embed/{website_id}/script.js")
async def get_chatbot_script(website_id: str):
    """Serve the chatbot JavaScript file for embedding"""
    try:
        print(f" Serving script for website: {website_id}")
        
        # Check if script exists
        script_filename = f"chatbot_{website_id}.js"
        script_path = os.path.join("generated_scripts", script_filename)
        
        if not os.path.exists(script_path):
            # Check if website exists
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
            
            # Try to generate script
            try:
                print(f" Script not found, generating for {website_id}")
                generator = ChatbotGenerator(base_url=BACKEND_URL)
                script_path = generator.generate_script_file(website_id)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "success": False,
                        "error": "Script generation failed",
                        "message": f"Failed to generate script: {str(e)}"
                    }
                )
        
        if not os.path.exists(script_path):
            raise HTTPException(
                status_code=404,
                detail={
                    "success": False,
                    "error": "Script not found",
                    "message": f"Script file not found for website {website_id}"
                }
            )
        
        # Read and return the file
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f" Script served: {script_path} ({len(content)} bytes)")
        
        return HTMLResponse(
            content=content,
            media_type="application/javascript",
            headers={
                "Content-Type": "application/javascript; charset=utf-8",
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
                "X-Website-ID": website_id,
                "X-Script-Size": str(len(content))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"  Script serve error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "Internal server error",
                "message": str(e)
            }
        )

# ======================
# TEST PAGE ROUTE
# ======================

@app.get("/test/{website_id}")
async def test_chatbot_page(website_id: str):
    """Test page with embedded chatbot"""
    try:
        # Get website info
        website = db_manager.get_website(website_id)
        if not website:
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head><title>Error</title></head>
                <body>
                    <h1> Website Not Found</h1>
                    <p>Website with ID <code>{website_id}</code> not found.</p>
                    <a href="/">Back to Home</a>
                </body>
                </html>
                """,
                status_code=404
            )
        
        website_name = website.get('website_name', website_id)
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Chatbot - {website_name}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                    min-height: 100vh;
                }}
                .header {{
                    text-align: center;
                    padding: 40px;
                    background: white;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                }}
                .header h1 {{ color: #2d3748; margin-bottom: 10px; }}
                .info {{
                    background: white;
                    border-radius: 15px;
                    padding: 20px;
                    margin: 20px 0;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.05);
                }}
                .badge {{
                    display: inline-block;
                    background: #48bb78;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 14px;
                }}
                .instructions {{
                    background: #f0f9ff;
                    border-radius: 10px;
                    padding: 20px;
                    margin: 20px 0;
                    border: 1px solid #bfdbfe;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #6b7280;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1> Test Chatbot</h1>
                <p>Testing the chatbot for <strong>{website_name}</strong></p>
                <span class="badge">Website ID: {website_id}</span>
            </div>
            
            <div class="info">
                <h3> Instructions:</h3>
                <ol>
                    <li>The chatbot should appear in the bottom-right corner</li>
                    <li>Click the chat icon to open the widget</li>
                    <li><strong>Complete registration</strong> (required before chatting)</li>
                    <li>Ask questions about the website</li>
                </ol>
            </div>
            
            <div class="instructions">
                <p><strong>Need help?</strong> Try asking:</p>
                <ul>
                    <li>"What services do you offer?"</li>
                    <li>"Tell me about your company"</li>
                    <li>"How can I contact support?"</li>
                </ul>
            </div>
            
            <div class="footer">
                <p>The chatbot widget should appear in the bottom-right corner of this page.</p>
                <p>If not visible, check browser console for errors (F12 → Console)</p>
            </div>
            
            <!-- Embedded Chatbot Script -->
            <script src="/embed/{website_id}/script.js" defer></script>
            
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    console.log(' Test page loaded for website: {website_id}');
                    
                    // Check if chatbot loads
                    setTimeout(function() {{
                        if (document.getElementById('chatbot-widget')) {{
                            console.log(' Chatbot widget detected!');
                        }} else {{
                            console.log(' Chatbot widget not found. Check script loading.');
                        }}
                    }}, 3000);
                }});
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"  Test page error: {e}")
        return HTMLResponse(
            content=f"<h1>Error: {str(e)}</h1>",
            status_code=500
        )

# ======================
# EXCEPTION HANDLERS
# ======================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict) else {
            "success": False,
            "error": "HTTP Error",
            "message": str(exc.detail),
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    print(f"  Unhandled error: {exc}")
    import traceback
    traceback.print_exc()
    
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal Server Error",
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    print("=" * 70)
    print(" CHATBOT GENERATOR API v3.0")
    print("=" * 70)
    print(f" Local URL: {BACKEND_URL}")
    print(f" API Docs: {BACKEND_URL}/api/docs")
    print(f" Home Page: {BACKEND_URL}/")
    print(f" Database: PostgreSQL")
    print(f" Email: Enabled")
    print(f" Auto-Reports: Enabled (browser close/reload)")
    print(f" Data: {os.path.abspath('data')}")
    print(f" Scripts: {os.path.abspath('generated_scripts')}")
    print("=" * 70)
    print(" Starting server...")
    print("=" * 70)
    
    # Create necessary directories
    os.makedirs("data", exist_ok=True)
    os.makedirs("generated_scripts", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("user_sessions", exist_ok=True)
    
    # Check database connection
    try:
        websites = db_manager.get_all_websites()
        print(f"   Found {len(websites)} websites in database")
    except Exception as e:
        print(f" Database check error: {e}")
    
    uvicorn.run(
        app,
        host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        port=int(os.getenv("BACKEND_PORT", 8080)),
        reload=True,
        log_level="info"
    )