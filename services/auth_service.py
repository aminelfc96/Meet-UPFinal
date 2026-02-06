# services/auth_service.py - Authentication Service following SOLID principles

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

from database.models import User, IUserRepository
from utils import hash_password, verify_password, generate_id
from config_manager import get_config

logger = logging.getLogger(__name__)
config = get_config()

# =============================================================================
# DATA TRANSFER OBJECTS
# =============================================================================

@dataclass
class LoginRequest:
    """Login request DTO"""
    user_id: str
    password: str

@dataclass 
class RegisterRequest:
    """Registration request DTO"""
    name: str
    password: str

@dataclass
class AuthResult:
    """Authentication result DTO"""
    success: bool
    user: Optional[User] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response format"""
        if self.success and self.user:
            return {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": "bearer",
                "expires_in": config.get('security.jwt.access_token_expire_minutes', 60) * 60,
                "user": self.user.to_safe_dict()
            }
        else:
            return {
                "detail": self.error_message or "Authentication failed"
            }

# =============================================================================
# SERVICE INTERFACES
# =============================================================================

class IAuthService(ABC):
    """Authentication service interface"""
    
    @abstractmethod
    async def register_user(self, request: RegisterRequest) -> AuthResult:
        """Register a new user"""
        pass
    
    @abstractmethod
    async def authenticate_user(self, request: LoginRequest, client_request) -> AuthResult:
        """Authenticate user credentials"""
        pass
    
    @abstractmethod
    async def validate_token(self, token: str, client_request) -> Optional[User]:
        """Validate authentication token"""
        pass
    
    @abstractmethod
    async def logout_user(self, token: str, client_request) -> bool:
        """Logout user and invalidate token"""
        pass

class IPasswordService(ABC):
    """Password service interface"""
    
    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Hash a password securely"""
        pass
    
    @abstractmethod
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        pass
    
    @abstractmethod
    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password meets security requirements"""
        pass

# =============================================================================
# SERVICE IMPLEMENTATIONS
# =============================================================================

class PasswordService(IPasswordService):
    """Password service implementation"""
    
    def hash_password(self, password: str) -> str:
        """Hash password using secure algorithm"""
        return hash_password(password)
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return verify_password(password, hashed)
    
    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password meets security requirements"""
        min_length = config.get('validation.password_min_length', 4)
        max_length = config.get('validation.password_max_length', 128)
        
        if len(password) < min_length:
            return False, f"Password must be at least {min_length} characters long"
        
        if len(password) > max_length:
            return False, f"Password must be less than {max_length} characters long"
        
        # Additional strength checks can be added here
        # For now, we'll keep the basic length requirement
        
        return True, "Password is valid"

class AuthService(IAuthService):
    """Authentication service implementation"""
    
    def __init__(self, user_repository: IUserRepository, password_service: IPasswordService):
        self.user_repo = user_repository
        self.password_service = password_service
        self._jwt_manager = None
    
    def get_jwt_manager(self):
        """Lazy load JWT manager to avoid circular imports"""
        if self._jwt_manager is None:
            from enhanced_auth import get_jwt_manager
            self._jwt_manager = get_jwt_manager()
        return self._jwt_manager
    
    async def register_user(self, request: RegisterRequest) -> AuthResult:
        """Register a new user"""
        try:
            # Validate password strength
            is_valid, message = self.password_service.validate_password_strength(request.password)
            if not is_valid:
                return AuthResult(success=False, error_message=message)
            
            # Generate unique IDs
            user_id = generate_id()
            public_id = generate_id()[:8]
            
            # Check if user already exists (collision detection)
            if await self.user_repo.exists(user_id):
                logger.warning(f"User ID collision detected: {user_id}")
                return AuthResult(success=False, error_message="Registration failed, please try again")
            
            # Hash password
            password_hash = self.password_service.hash_password(request.password)
            
            # Create user
            user = User(
                user_id=user_id,
                public_id=public_id,
                name=request.name,
                password_hash=password_hash,
                created_at=datetime.utcnow()
            )
            
            # Save to database
            success = await self.user_repo.create(user)
            if success:
                logger.info(f"User registered successfully: {request.name} ({public_id})")
                return AuthResult(
                    success=True,
                    user=user,
                    error_message=None
                )
            else:
                return AuthResult(success=False, error_message="Registration failed")
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return AuthResult(success=False, error_message="Registration failed")
    
    async def authenticate_user(self, request: LoginRequest, client_request) -> AuthResult:
        """Authenticate user credentials"""
        try:
            # Validate input format
            if not request.user_id or not request.password:
                return AuthResult(success=False, error_message="User ID and password are required")
            
            # Get user by user_id first
            user = await self.user_repo.get_by_id(request.user_id)
            if not user:
                logger.warning(f"Failed login attempt for user: {request.user_id}")
                return AuthResult(success=False, error_message="Invalid credentials")
            
            # Verify password against stored hash
            if not self.password_service.verify_password(request.password, user.password_hash):
                logger.warning(f"Failed login attempt for user: {request.user_id}")
                return AuthResult(success=False, error_message="Invalid credentials")
            
            # Generate JWT tokens
            user_data = user.to_safe_dict()
            jwt_manager = self.get_jwt_manager()
            access_token = jwt_manager.create_access_token(user_data, client_request)
            refresh_token = jwt_manager.create_refresh_token(user.user_id)
            
            logger.info(f"User authenticated successfully: {user.name} ({user.public_id})")
            return AuthResult(
                success=True,
                user=user,
                access_token=access_token,
                refresh_token=refresh_token
            )
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return AuthResult(success=False, error_message="Authentication failed")
    
    async def validate_token(self, token: str, client_request) -> Optional[User]:
        """Validate authentication token"""
        try:
            # Verify JWT token
            jwt_manager = self.get_jwt_manager()
            payload = jwt_manager.verify_token(token, client_request, "access")
            if not payload:
                return None
            
            # Get user from database to ensure they still exist
            user_id = payload.get("sub")
            if not user_id:
                return None
            
            user = await self.user_repo.get_by_id(user_id)
            if not user:
                # User was deleted, blacklist token
                jti = payload.get("jti")
                if jti:
                    jwt_manager = self.get_jwt_manager()
                    jwt_manager.blacklist_token(jti)
                return None
            
            return user
            
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
    
    async def logout_user(self, token: str, client_request) -> bool:
        """Logout user and invalidate token"""
        try:
            jwt_manager = self.get_jwt_manager()
            payload = jwt_manager.verify_token(token, client_request, "access")
            if payload:
                jti = payload.get("jti")
                if jti:
                    jwt_manager.blacklist_token(jti)
                    logger.info(f"User logged out: {payload.get('sub')}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False

# =============================================================================
# SERVICE FACTORY (Dependency Injection)
# =============================================================================

class ServiceFactory:
    """Factory for creating service instances"""
    
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository
        self._password_service = None
        self._auth_service = None
    
    def get_password_service(self) -> IPasswordService:
        """Get password service instance"""
        if self._password_service is None:
            self._password_service = PasswordService()
        return self._password_service
    
    def get_auth_service(self) -> IAuthService:
        """Get authentication service instance"""
        if self._auth_service is None:
            self._auth_service = AuthService(
                self.user_repository,
                self.get_password_service()
            )
        return self._auth_service

# =============================================================================
# GLOBAL SERVICE INSTANCES
# =============================================================================

_service_factory: Optional[ServiceFactory] = None

def init_services(user_repository: IUserRepository):
    """Initialize global service instances"""
    global _service_factory
    _service_factory = ServiceFactory(user_repository)

def get_auth_service() -> IAuthService:
    """Get authentication service instance"""
    if _service_factory is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _service_factory.get_auth_service()

def get_password_service() -> IPasswordService:
    """Get password service instance"""
    if _service_factory is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _service_factory.get_password_service()