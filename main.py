# main.py - App Setup and Configuration Only

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
import asyncio
import os
import secrets
import logging

# Import route modules
from routes import user_routes, team_routes, meeting_routes, file_routes
from websocket_handlers import websocket_router
from database import init_database, DIContainer
from security_middleware import SecurityMiddleware, get_csrf_token
from enhanced_auth import init_jwt_manager, init_enhanced_security
from services import init_services
from config_manager import get_config

# Initialize configuration
config = get_config()

# Configure logging based on config
log_level = getattr(logging, config.get('logging.level', 'INFO').upper())
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# LIFESPAN EVENTS (Modern FastAPI pattern)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifespan events"""
    # Startup
    await init_database()
    
    # Create necessary directories
    directories = ["static/css", "static/js", "static/html", "uploads", "logs"]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize enhanced authentication with config
    security_key = config.get_secret_key()
    init_jwt_manager(security_key)
    init_enhanced_security()
    
    # Initialize services with dependency injection
    di_container = DIContainer(config.get_database_path())
    user_repository = di_container.get_user_repository()
    init_services(user_repository)
    
    # Start background tasks
    from websocket_handlers import start_background_tasks
    asyncio.create_task(start_background_tasks())
    
    logger.info("Meeting App started successfully with enhanced security")
    
    yield  # Application runs here
    
    # Shutdown (if needed)
    logger.info("Meeting App shutting down")

# =============================================================================
# APP CONFIGURATION
# =============================================================================

def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="Meeting App", 
        description="Modular meeting application",
        version="2.0.0",
        lifespan=lifespan  # Use modern lifespan pattern
    )

    # Get security key from config
    security_key = config.get_secret_key()
    
    # Add security middleware FIRST (only if enabled)
    if config.get('security.csrf_protection.enabled', True):
        app.add_middleware(SecurityMiddleware, secret_key=security_key)

    # CORS middleware with config-based origins
    allowed_origins = config.get_allowed_origins()
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Include route modules
    app.include_router(user_routes.router, prefix="/api", tags=["users"])
    app.include_router(team_routes.router, prefix="/api", tags=["teams"])
    app.include_router(meeting_routes.router, prefix="/api", tags=["meetings"])
    app.include_router(file_routes.router, prefix="/api", tags=["files"])
    app.include_router(websocket_router, tags=["websocket"])

    # Store security middleware reference (if needed)
    app.state.security_middleware = None
    
    return app

app = create_app()

# =============================================================================
# STATIC ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def get_landing_page():
    """Serve the main landing page"""
    with open("static/html/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/team/{team_id}", response_class=HTMLResponse)
async def get_team_page(team_id: str):
    """Serve team chat page"""
    with open("static/html/team.html", "r", encoding="utf-8") as f:
        content = f.read()
        return content.replace("{team_id}", team_id)

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker"""
    if not config.is_feature_enabled('health_endpoint'):
        raise HTTPException(status_code=404, detail="Health endpoint disabled")
    return {"status": "healthy", "message": "Service is running"}

@app.get("/api/csrf-token")
async def get_csrf_token_endpoint(request: Request):
    """Get CSRF token for forms"""
    # Check if CSRF protection is enabled
    if not config.get('security.csrf_protection.enabled', True):
        return {"csrf_token": None, "message": "CSRF protection disabled"}
    
    # Generate CSRF token using the shared instance
    from security_middleware import get_csrf_token
    token = get_csrf_token()
    expiry_hours = config.get('security.csrf_protection.token_expiry_hours', 1)
    
    return {
        "csrf_token": token,
        "expires_in": expiry_hours * 3600
    }

@app.get("/meeting/{meeting_id}", response_class=HTMLResponse)
async def get_meeting_page(meeting_id: str):
    """Serve meeting page"""
    with open("static/html/meeting.html", "r", encoding="utf-8") as f:
        content = f.read()
        return content.replace("{meeting_id}", meeting_id)

@app.get("/api/config")
async def get_app_config():
    """Get application configuration for frontend"""
    return {
        "features": {
            "user_registration": config.is_feature_enabled('user_registration'),
            "team_creation": config.is_feature_enabled('team_creation'),
            "team_joining": config.is_feature_enabled('team_joining'),
            "meeting_creation": config.is_feature_enabled('meeting_creation'),
            "meeting_joining": config.is_feature_enabled('meeting_joining'),
            "file_upload": config.is_feature_enabled('file_upload'),
            "secret_id_retrieval": config.is_feature_enabled('secret_id_retrieval'),
            "account_deletion": config.is_feature_enabled('account_deletion')
        },
        "validation": {
            "password_min_length": config.get('validation.password_min_length', 4),
            "password_max_length": config.get('validation.password_max_length', 128),
            "username_max_length": config.get('validation.username_max_length', 50),
            "message_max_length": config.get('validation.message_max_length', 1000)
        },
        "file_upload": {
            "max_size_mb": config.get('file_upload.max_file_size_mb', 10),
            "allowed_extensions": config.get('file_upload.allowed_extensions', [])
        }
    }

@app.post("/api/refresh-token")
async def refresh_token_endpoint(request: Request):
    """Refresh access token using refresh token"""
    try:
        data = await request.json()
        refresh_token = data.get("refresh_token")
        
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Refresh token required")
        
        from enhanced_auth import refresh_access_token
        new_access_token = await refresh_access_token(refresh_token, request)
        
        if new_access_token:
            return {"access_token": new_access_token, "token_type": "bearer"}
        else:
            raise HTTPException(status_code=403, detail="Invalid or expired refresh token")
            
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=403, detail="Token refresh failed")


# =============================================================================
# DEVELOPMENT SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    host = config.get('server.host', '192.168.0.189')
    port = config.get('server.port', 8000)
    reload = config.get('server.reload', False)
    
    # Set log level based on debug mode
    log_level = "debug" if config.get('server.debug', False) else "info"
    
    uvicorn.run(app, host=host, port=port, reload=reload, log_level=log_level)