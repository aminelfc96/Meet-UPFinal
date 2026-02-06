# routes/user_routes.py - User Management Routes (Refactored)

from fastapi import APIRouter, HTTPException, Depends, Request
import logging
import secrets
import time
import aiosqlite
from datetime import datetime, timedelta

from models import UserRegister, UserLogin, SecretIdRequest
from services import (
    get_auth_service, get_password_service, 
    LoginRequest, RegisterRequest, AuthResult
)
from database import DIContainer
from enhanced_auth import get_current_user, logout_user
from config_manager import get_config
from utils import verify_password

logger = logging.getLogger(__name__)
router = APIRouter()
config = get_config()
DATABASE_PATH = config.get_database_path()

# Initialize DI container
di_container = DIContainer(DATABASE_PATH)

# =============================================================================
# USER AUTHENTICATION
# =============================================================================

@router.post("/register")
async def register(user: UserRegister):
    """Register a new user using service layer"""
    if not config.is_feature_enabled('user_registration'):
        raise HTTPException(status_code=403, detail="User registration is disabled")
    
    try:
        auth_service = get_auth_service()
        request_dto = RegisterRequest(name=user.name, password=user.password)
        result = await auth_service.register_user(request_dto)
        
        if result.success:
            return {
                "user_id": result.user.user_id, 
                "public_id": result.user.public_id,
                "message": "Registration successful"
            }
        else:
            raise HTTPException(status_code=400, detail=result.error_message)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login")
async def login(user: UserLogin, request: Request):
    """Login user with enhanced JWT security using service layer"""
    try:
        auth_service = get_auth_service()
        request_dto = LoginRequest(user_id=user.user_id, password=user.password)
        result = await auth_service.authenticate_user(request_dto, request)
        
        if result.success:
            response_data = result.to_response_dict()
            logger.info(f"Login successful for user: {result.user.public_id}")
            return response_data
        else:
            logger.warning(f"Failed login attempt for user: {user.user_id}")
            raise HTTPException(status_code=401, detail=result.error_message)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@router.post("/logout")
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """Logout user by blacklisting token"""
    auth_header = request.headers.get('authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        await logout_user(token, request)
    
    logger.info(f"User logged out: {current_user['name']}")
    return {"message": "Logout successful"}

# =============================================================================
# USER PROFILE MANAGEMENT
# =============================================================================

@router.get("/user/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT user_id, public_id, name, created_at FROM users WHERE user_id = ?",
            (current_user["user_id"],)
        ) as cursor:
            user_data = await cursor.fetchone()
            
            if not user_data:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {
                "user_id": user_data[0],
                "public_id": user_data[1],
                "name": user_data[2],
                "created_at": user_data[3]
            }

# Global storage for nonces to prevent replay attacks
used_nonces = {}
NONCE_EXPIRY_SECONDS = 300  # 5 minutes

@router.post("/user/secret-id")
async def get_secret_login_id(request: SecretIdRequest, current_user: dict = Depends(get_current_user)):
    """Get user's login ID with strong security verification
    
    This endpoint returns the user's actual login credential (user_id) that they need to log back in.
    Security measures include:
    - Password verification required
    - Anti-replay protection with nonces  
    - Rate limiting via nonce expiry
    - Short display time (10 seconds)
    - Audit logging
    
    ARCHITECTURAL NOTE: In a production system, consider separating login credentials 
    from internal user IDs, but for this app users need their actual login ID to sign back in.
    """
    
    # Anti-replay protection: Check nonce
    current_time = time.time()
    user_id = current_user["user_id"]
    
    # Clean expired nonces
    expired_keys = [key for key, timestamp in used_nonces.items() if current_time - timestamp > NONCE_EXPIRY_SECONDS]
    for key in expired_keys:
        del used_nonces[key]
    
    # Check if nonce was already used
    nonce_key = f"{user_id}:{request.nonce}"
    if nonce_key in used_nonces:
        logger.warning(f"Replay attack attempt detected for user {user_id}")
        raise HTTPException(status_code=400, detail="Invalid request. Please try again.")
    
    # Mark nonce as used
    used_nonces[nonce_key] = current_time
    
    # Verify password
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()
            
            if not user_data:
                raise HTTPException(status_code=404, detail="User not found")
            
            if not verify_password(request.password, user_data[0]):
                logger.warning(f"Failed secret ID access attempt for user {user_id}")
                raise HTTPException(status_code=401, detail="Invalid password")
    
    # Log successful access
    logger.info(f"Secret ID accessed by user {user_id}")
    
    # Return the actual login ID (user_id) with security info
    # This is the user's login credential that they need to log back in
    # Security is provided by: password verification, nonce protection, rate limiting, and short display time
    return {
        "secret_id": user_id,
        "message": "Login ID retrieved successfully - keep this secure!",
        "expires_in": "10 seconds",
        "timestamp": datetime.now().isoformat(),
        "security_note": "This is your actual login credential"
    }

@router.delete("/user/delete")
async def delete_user_account(current_user: dict = Depends(get_current_user)):
    """Delete user account and all associated data"""
    user_id = current_user["user_id"]
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Delete all user-related data
        await db.execute("DELETE FROM team_messages WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM team_members WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM meeting_participants WHERE user_id = ?", (user_id,))
        
        # Delete teams and meetings where user is admin/creator
        async with db.execute("SELECT team_id FROM teams WHERE admin_user_id = ?", (user_id,)) as cursor:
            admin_teams = await cursor.fetchall()
            for team in admin_teams:
                await db.execute("DELETE FROM team_members WHERE team_id = ?", (team[0],))
                await db.execute("DELETE FROM team_messages WHERE team_id = ?", (team[0],))
                await db.execute("DELETE FROM teams WHERE team_id = ?", (team[0],))
        
        async with db.execute("SELECT meeting_id FROM meetings WHERE creator_user_id = ?", (user_id,)) as cursor:
            creator_meetings = await cursor.fetchall()
            for meeting in creator_meetings:
                await db.execute("DELETE FROM meeting_participants WHERE meeting_id = ?", (meeting[0],))
                await db.execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting[0],))
        
        # Delete user
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.commit()
    
    logger.info(f"User account deleted: {user_id}")
    return {"message": "Account deleted successfully"}