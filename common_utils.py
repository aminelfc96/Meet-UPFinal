"""
Common Utilities for WebApp

This module provides shared utilities and services to eliminate code redundancy
across the application. It includes database services, authentication helpers,
validation utilities, and other common patterns.
"""

import aiosqlite
import hashlib
import re
from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import logging

from database import DATABASE_PATH

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

class AppConfig:
    """Centralized application configuration"""
    
    # Database
    DATABASE_PATH = DATABASE_PATH
    
    # File limits
    MAX_FILE_SIZE = 300 * 1024  # 300KB
    ALLOWED_FILE_TYPES = {'.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    # Message limits
    MAX_TEAM_MESSAGE_LENGTH = 1000
    MAX_MEETING_MESSAGE_LENGTH = 500
    
    # Rate limiting
    MESSAGE_RATE_LIMIT = 5  # messages per minute
    JOIN_RATE_LIMIT = 10    # join requests per hour
    
    # WebSocket
    WS_PING_INTERVAL = 30
    WS_RECONNECT_MAX_ATTEMPTS = 5
    
    # Video quality settings
    VIDEO_CONSTRAINTS = {
        'low': {'width': 640, 'height': 360, 'frameRate': 15},
        'medium': {'width': 1280, 'height': 720, 'frameRate': 24},
        'high': {'width': 1920, 'height': 1080, 'frameRate': 30}
    }
    
    # Bandwidth limits (kbps)
    BANDWIDTH_LIMITS = {
        'low': 500,
        'medium': 1000,
        'high': 2000,
        'unlimited': None
    }

# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

class ValidationError(Exception):
    """Custom validation error"""
    pass

class Validators:
    """Common validation functions"""
    
    @staticmethod
    def validate_id(value: str, field_name: str = "ID") -> str:
        """Validate hex ID format used throughout the app"""
        if not value or not isinstance(value, str):
            raise ValidationError(f"{field_name} is required")
        
        if not re.match(r'^[a-f0-9]+$', value.lower()):
            raise ValidationError(f"{field_name} must be a valid hex string")
        
        if len(value) < 8 or len(value) > 64:
            raise ValidationError(f"{field_name} must be between 8 and 64 characters")
        
        return value.lower()
    
    @staticmethod
    def validate_user_id(value: str) -> str:
        """Validate user ID"""
        return Validators.validate_id(value, "User ID")
    
    @staticmethod
    def validate_team_id(value: str) -> str:
        """Validate team ID"""
        return Validators.validate_id(value, "Team ID")
    
    @staticmethod
    def validate_meeting_id(value: str) -> str:
        """Validate meeting ID"""
        return Validators.validate_id(value, "Meeting ID")
    
    @staticmethod
    def validate_message(message: str, max_length: int = None) -> str:
        """Validate message content"""
        if not message or not isinstance(message, str):
            raise ValidationError("Message is required")
        
        message = message.strip()
        if not message:
            raise ValidationError("Message cannot be empty")
        
        if max_length and len(message) > max_length:
            raise ValidationError(f"Message too long (max {max_length} characters)")
        
        return message
    
    @staticmethod
    def validate_file_upload(filename: str, file_size: int) -> None:
        """Validate file upload"""
        if not filename:
            raise ValidationError("Filename is required")
        
        file_ext = Path(filename).suffix.lower()
        if file_ext not in AppConfig.ALLOWED_FILE_TYPES:
            raise ValidationError(f"File type {file_ext} not allowed")
        
        if file_size > AppConfig.MAX_FILE_SIZE:
            raise ValidationError(f"File too large (max {AppConfig.MAX_FILE_SIZE // 1024 // 1024}MB)")

# =============================================================================
# DATABASE SERVICE
# =============================================================================

class DatabaseService:
    """Centralized database operations to eliminate redundancy"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or AppConfig.DATABASE_PATH
    
    async def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a query and return results as list of dicts"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def execute_query_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Execute a query and return first result as dict"""
        results = await self.execute_query(query, params)
        return results[0] if results else None
    
    async def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an update/insert/delete query and return rows affected"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount
    
    # User operations
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by ID (common operation across the app)"""
        query = "SELECT user_id, public_id, name FROM users WHERE user_id = ?"
        return await self.execute_query_one(query, (user_id,))
    
    async def get_user_with_password(self, user_id: str) -> Optional[Dict]:
        """Get user with password hash for authentication"""
        query = "SELECT user_id, public_id, name, password_hash FROM users WHERE user_id = ?"
        return await self.execute_query_one(query, (user_id,))
    
    # Team operations
    async def check_team_membership(self, user_id: str, team_id: str) -> Optional[str]:
        """Check team membership status"""
        query = "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?"
        result = await self.execute_query_one(query, (team_id, user_id))
        return result['status'] if result else None
    
    async def check_team_admin(self, user_id: str, team_id: str) -> bool:
        """Check if user is team admin"""
        query = "SELECT admin_user_id FROM teams WHERE team_id = ?"
        result = await self.execute_query_one(query, (team_id,))
        return result and result['admin_user_id'] == user_id
    
    async def get_team_info(self, team_id: str) -> Optional[Dict]:
        """Get team information"""
        query = "SELECT team_id, name, admin_user_id, created_at FROM teams WHERE team_id = ?"
        return await self.execute_query_one(query, (team_id,))
    
    # Meeting operations
    async def check_meeting_participation(self, user_id: str, meeting_id: str) -> Optional[str]:
        """Check meeting participation status"""
        query = "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?"
        result = await self.execute_query_one(query, (meeting_id, user_id))
        return result['status'] if result else None
    
    async def check_meeting_creator(self, user_id: str, meeting_id: str) -> bool:
        """Check if user is meeting creator"""
        query = "SELECT creator_user_id FROM meetings WHERE meeting_id = ?"
        result = await self.execute_query_one(query, (meeting_id,))
        return result and result['creator_user_id'] == user_id
    
    async def get_meeting_info(self, meeting_id: str) -> Optional[Dict]:
        """Get meeting information"""
        query = "SELECT meeting_id, name, creator_user_id, created_at FROM meetings WHERE meeting_id = ?"
        return await self.execute_query_one(query, (meeting_id,))

# =============================================================================
# AUTHENTICATION SERVICE
# =============================================================================

class AuthService:
    """Centralized authentication and authorization logic"""
    
    def __init__(self, db_service: DatabaseService = None):
        self.db = db_service or DatabaseService()
    
    async def authenticate_user(self, user_id: str, password: str) -> Optional[Dict]:
        """Authenticate user with password"""
        user = await self.db.get_user_with_password(user_id)
        if not user:
            return None
        
        # Check password hash
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user['password_hash'] != password_hash:
            return None
        
        # Return user without password
        return {
            'user_id': user['user_id'],
            'public_id': user['public_id'],
            'name': user['name']
        }
    
    async def check_team_permission(self, user_id: str, team_id: str, 
                                  required_status: str = 'approved') -> bool:
        """Check if user has permission for team operation"""
        status = await self.db.check_team_membership(user_id, team_id)
        return status == required_status
    
    async def check_team_admin_permission(self, user_id: str, team_id: str) -> bool:
        """Check if user is team admin"""
        return await self.db.check_team_admin(user_id, team_id)
    
    async def check_meeting_permission(self, user_id: str, meeting_id: str,
                                     required_status: str = 'approved') -> bool:
        """Check if user has permission for meeting operation"""
        status = await self.db.check_meeting_participation(user_id, meeting_id)
        return status == required_status
    
    async def check_meeting_creator_permission(self, user_id: str, meeting_id: str) -> bool:
        """Check if user is meeting creator"""
        return await self.db.check_meeting_creator(user_id, meeting_id)

# =============================================================================
# ADMIN ACTION SERVICE
# =============================================================================

class AdminActionService:
    """Centralized admin action patterns (approve/reject/remove)"""
    
    def __init__(self, db_service: DatabaseService = None):
        self.db = db_service or DatabaseService()
    
    async def handle_team_member_action(self, team_id: str, user_id: str, 
                                      action: str, admin_user_id: str) -> Dict:
        """Handle team member approve/reject/remove actions"""
        # Verify admin permission
        auth_service = AuthService(self.db)
        if not await auth_service.check_team_admin_permission(admin_user_id, team_id):
            raise PermissionError("Only team admin can perform this action")
        
        if action == 'approve':
            await self.db.execute_update(
                "UPDATE team_members SET status = 'approved' WHERE team_id = ? AND user_id = ?",
                (team_id, user_id)
            )
            return {"message": "Member approved successfully"}
        
        elif action == 'reject':
            await self.db.execute_update(
                "UPDATE team_members SET status = 'rejected' WHERE team_id = ? AND user_id = ?",
                (team_id, user_id)
            )
            return {"message": "Member rejected successfully"}
        
        elif action == 'remove':
            await self.db.execute_update(
                "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, user_id)
            )
            return {"message": "Member removed successfully"}
        
        else:
            raise ValueError(f"Invalid action: {action}")
    
    async def handle_meeting_participant_action(self, meeting_id: str, user_id: str,
                                              action: str, creator_user_id: str) -> Dict:
        """Handle meeting participant approve/reject/remove actions"""
        # Verify creator permission
        auth_service = AuthService(self.db)
        if not await auth_service.check_meeting_creator_permission(creator_user_id, meeting_id):
            raise PermissionError("Only meeting creator can perform this action")
        
        if action == 'approve':
            await self.db.execute_update(
                "UPDATE meeting_participants SET status = 'approved' WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, user_id)
            )
            return {"message": "Participant approved successfully"}
        
        elif action == 'reject':
            await self.db.execute_update(
                "UPDATE meeting_participants SET status = 'rejected' WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, user_id)
            )
            return {"message": "Participant rejected successfully"}
        
        elif action == 'remove':
            await self.db.execute_update(
                "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, user_id)
            )
            return {"message": "Participant removed successfully"}
        
        elif action == 'block':
            await self.db.execute_update(
                "UPDATE meeting_participants SET status = 'blocked' WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, user_id)
            )
            return {"message": "Participant blocked successfully"}
        
        else:
            raise ValueError(f"Invalid action: {action}")

# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

# Create global instances for easy access
db_service = DatabaseService()
auth_service = AuthService(db_service)
admin_service = AdminActionService(db_service)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_file_size(bytes_size: int) -> str:
    """Format file size in human readable format"""
    if bytes_size == 0:
        return "0 Bytes"
    
    k = 1024
    sizes = ["Bytes", "KB", "MB", "GB", "TB"]
    i = 0
    
    while bytes_size >= k and i < len(sizes) - 1:
        bytes_size /= k
        i += 1
    
    return f"{bytes_size:.2f} {sizes[i]}"

def generate_id() -> str:
    """Generate a unique hex ID"""
    import uuid
    return uuid.uuid4().hex

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    import re
    # Remove path separators and dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_len = 255 - len(ext) - 1
        filename = f"{name[:max_name_len]}.{ext}" if ext else name[:255]
    
    return filename

def get_client_ip(request) -> str:
    """Get client IP address from request"""
    # Check for forwarded IP first (for proxy/load balancer scenarios)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    return request.client.host if hasattr(request, 'client') else 'unknown'