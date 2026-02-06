# enhanced_auth.py - Enhanced JWT Authentication with Security Features

import jwt
import secrets
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
import logging

from utils import validate_user_id
from config_manager import get_config
from error_handler import AuthenticationError, create_error_response

logger = logging.getLogger(__name__)
config = get_config()

# =============================================================================
# JWT CONFIGURATION
# =============================================================================

class JWTManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.algorithm = config.get('security.jwt.algorithm', 'HS256')
        self.access_token_expire_minutes = config.get('security.jwt.access_token_expire_minutes', 60)
        self.refresh_token_expire_days = config.get('security.jwt.refresh_token_expire_days', 7)
        
        # Token blacklist and fingerprints
        self.blacklisted_tokens = set()
        self.token_fingerprints: Dict[str, str] = {}
        
    def create_access_token(self, user_data: dict, request: Request) -> str:
        """Create JWT access token with enhanced security"""
        now = datetime.utcnow()
        expire = now + timedelta(minutes=self.access_token_expire_minutes)
        
        # Add small buffer for clock skew
        current_timestamp = time.time()
        issued_at = int(current_timestamp)
        expires_at = int(current_timestamp + (self.access_token_expire_minutes * 60))
        
        # Create unique token ID
        jti = secrets.token_hex(16)
        
        # Create device fingerprint
        fingerprint = self._create_device_fingerprint(request)
        self.token_fingerprints[jti] = fingerprint
        
        payload = {
            "sub": user_data["user_id"],  # Subject (user ID)
            "name": user_data["name"],
            "public_id": user_data["public_id"],
            "iat": issued_at,  # Issued at (using time.time() for consistency)
            "exp": expires_at,  # Expiration (using time.time() for consistency)
            "jti": jti,  # JWT ID
            "type": "access",
            "fingerprint": fingerprint[:8]  # Partial fingerprint in token
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        # Log token creation with timing info
        logger.info(f"Access token created for user {user_data['user_id']} (jti: {jti})")
        logger.info(f"Token issued at: {issued_at}, expires at: {expires_at}")
        logger.info(f"Current time: {current_timestamp}, expires in: {expires_at - current_timestamp} seconds")
        
        return token
    
    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token"""
        now = datetime.utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)
        
        jti = secrets.token_hex(16)
        
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": jti,
            "type": "refresh"
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str, request: Request, token_type: str = "access") -> Optional[dict]:
        """Verify JWT token with enhanced security checks"""
        try:
            # Decode token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check token type
            if payload.get("type") != token_type:
                logger.warning(f"Invalid token type: expected {token_type}, got {payload.get('type')}")
                return None
            
            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti in self.blacklisted_tokens:
                logger.warning(f"Blacklisted token used: {jti}")
                return None
            
            # Verify device fingerprint for access tokens (if enabled)
            if token_type == "access" and config.get('security.device_fingerprinting.enabled', True):
                stored_fingerprint = self.token_fingerprints.get(jti)
                current_fingerprint = self._create_device_fingerprint(request)
                
                if stored_fingerprint and stored_fingerprint != current_fingerprint:
                    logger.warning(f"Device fingerprint mismatch for token {jti}")
                    if config.get('security.device_fingerprinting.strict_validation', True):
                        self.blacklist_token(jti)
                        return None
            
            # Check expiration
            exp = payload.get("exp")
            current_time = time.time()
            if exp and exp < current_time:
                logger.info(f"Expired token: {jti}, exp: {exp}, current: {current_time}, diff: {current_time - exp}")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError as e:
            logger.info(f"Token expired (JWT library): {e}")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
    
    def blacklist_token(self, jti: str):
        """Add token to blacklist"""
        self.blacklisted_tokens.add(jti)
        if jti in self.token_fingerprints:
            del self.token_fingerprints[jti]
        logger.info(f"Token blacklisted: {jti}")
    
    def _create_device_fingerprint(self, request: Request) -> str:
        """Create device fingerprint from request headers"""
        headers = dict(request.headers)
        
        # Collect stable device characteristics
        fingerprint_data = [
            headers.get('user-agent', ''),
            headers.get('accept-language', ''),
            headers.get('accept-encoding', ''),
            request.client.host if request.client else ''
        ]
        
        # Create hash of fingerprint data
        fingerprint_str = '|'.join(fingerprint_data)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()
    
    def cleanup_expired_tokens(self):
        """Clean up expired token fingerprints"""
        # This would be called periodically to clean up old data
        # For production, consider using Redis with TTL
        pass

# =============================================================================
# ENHANCED SECURITY BEARER
# =============================================================================

class EnhancedHTTPBearer(HTTPBearer):
    def __init__(self, jwt_manager: JWTManager):
        super().__init__()
        self.jwt_manager = jwt_manager
    
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        # Get credentials
        credentials = await super().__call__(request)
        
        # Additional security checks
        self._check_request_security(request)
        
        return credentials
    
    def _check_request_security(self, request: Request):
        """Additional security checks for API requests"""
        headers = dict(request.headers)
        
        # Check for required headers
        if not headers.get('user-agent'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required headers"
            )
        
        # Check for suspicious patterns
        user_agent = headers.get('user-agent', '').lower()
        suspicious_patterns = ['bot', 'crawler', 'spider', 'curl', 'wget']
        
        if any(pattern in user_agent for pattern in suspicious_patterns):
            logger.warning(f"Suspicious user agent detected: {user_agent}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

# =============================================================================
# DEPENDENCY FUNCTIONS
# =============================================================================

# Initialize JWT manager (will be properly initialized in main.py)
jwt_manager = None

def init_jwt_manager(secret_key: str):
    """Initialize JWT manager with secret key"""
    global jwt_manager
    jwt_manager = JWTManager(secret_key)
    return jwt_manager

def get_jwt_manager() -> JWTManager:
    """Get JWT manager instance"""
    if jwt_manager is None:
        raise RuntimeError("JWT manager not initialized")
    return jwt_manager

# Enhanced security bearer
enhanced_security = None

def init_enhanced_security():
    """Initialize enhanced security"""
    global enhanced_security
    enhanced_security = EnhancedHTTPBearer(get_jwt_manager())
    return enhanced_security

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(lambda: enhanced_security)
) -> dict:
    """Get current user from enhanced JWT token"""
    if not enhanced_security:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system not initialized"
        )
    
    try:
        # Get credentials
        auth_credentials = await enhanced_security(request)
        token = auth_credentials.credentials
        
        # Verify token
        payload = jwt_manager.verify_token(token, request, "access")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user ID from payload
        user_id = payload.get("sub")
        if not user_id or not validate_user_id(user_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
        
        # Verify user still exists in database using repository pattern
        from database import DIContainer
        
        di_container = DIContainer(config.get_database_path())
        user_repo = di_container.get_user_repository()
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            # User was deleted, blacklist token
            jti = payload.get("jti")
            if jti:
                jwt_manager.blacklist_token(jti)
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        return user.to_safe_dict()
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(lambda: enhanced_security)
) -> Optional[dict]:
    """Get current user optionally (for endpoints that work with or without auth)"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None

# =============================================================================
# ADMIN ROLE CHECKING
# =============================================================================

async def check_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Check if current user has admin privileges"""
    # For now, all users are regular users
    # This can be extended with role-based access control
    return current_user

async def check_meeting_creator(
    meeting_id: str, 
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Check if current user is the creator of a meeting"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", 
            (meeting_id,)
        ) as cursor:
            meeting = await cursor.fetchone()
            if not meeting or meeting[0] != current_user["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only meeting creator can perform this action"
                )
    
    return current_user

async def check_team_admin(
    team_id: str, 
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Check if current user is admin of a team"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT admin_user_id FROM teams WHERE team_id = ?", 
            (team_id,)
        ) as cursor:
            team = await cursor.fetchone()
            if not team or team[0] != current_user["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only team admin can perform this action"
                )
    
    return current_user

# =============================================================================
# TOKEN MANAGEMENT
# =============================================================================

async def logout_user(token: str, request: Request):
    """Logout user by blacklisting token"""
    try:
        payload = jwt_manager.verify_token(token, request, "access")
        if payload:
            jti = payload.get("jti")
            if jti:
                jwt_manager.blacklist_token(jti)
                logger.info(f"User logged out: {payload.get('sub')}")
    except Exception as e:
        logger.error(f"Logout error: {e}")

async def refresh_access_token(refresh_token: str, request: Request) -> Optional[str]:
    """Refresh access token using refresh token"""
    try:
        payload = jwt_manager.verify_token(refresh_token, request, "refresh")
        if not payload:
            return None
        
        user_id = payload.get("sub")
        
        # Get user data using repository
        from database import DIContainer
        
        di_container = DIContainer(config.get_database_path())
        user_repo = di_container.get_user_repository()
        
        user = await user_repo.get_by_id(user_id)
        if not user:
            return None
        
        user_data = user.to_safe_dict()
        
        # Create new access token
        return jwt_manager.create_access_token(user_data, request)
                
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return None