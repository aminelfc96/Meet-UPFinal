# models.py - Clean Pydantic Models without Email

from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re

# =============================================================================
# ENUMS
# =============================================================================

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"

class MembershipStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"

class MessageType(str, Enum):
    TEXT = "text"
    FILE = "file"
    IMAGE = "image"
    SYSTEM = "system"

# =============================================================================
# BASE MODELS
# =============================================================================

class BaseResponse(BaseModel):
    """Base response model"""
    success: bool = True
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

# =============================================================================
# USER MODELS
# =============================================================================

class UserRegister(BaseModel):
    """User registration model"""
    name: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)
    
    @validator('name')
    def validate_name(cls, v):
        v = v.strip()
        if not re.match(r'^[a-zA-Z0-9\s\-_.]+$', v):
            raise ValueError('Name contains invalid characters')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 4:
            raise ValueError('Password must be at least 4 characters long')
        return v

class UserLogin(BaseModel):
    """User login model"""
    user_id: str = Field(..., min_length=32, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    
    @validator('user_id')
    def validate_user_id(cls, v):
        try:
            int(v, 16)
        except ValueError:
            raise ValueError('Invalid user ID format')
        return v.lower()

class SecretIdRequest(BaseModel):
    """Request model for retrieving secret login ID"""
    password: str = Field(..., min_length=1, max_length=128)
    nonce: str = Field(..., min_length=16, max_length=64)  # Anti-replay protection
    
    @validator('password')
    def validate_password(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Password cannot be empty')
        return v
    
    @validator('nonce')
    def validate_nonce(cls, v):
        if not v.strip():
            raise ValueError('Nonce cannot be empty')
        return v

class UserProfile(BaseModel):
    """User profile model"""
    user_id: str
    public_id: str
    name: str
    role: UserRole = UserRole.USER
    created_at: datetime
    is_active: bool = True

# =============================================================================
# TEAM MODELS
# =============================================================================

class TeamCreate(BaseModel):
    """Team creation model"""
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    
    @validator('name')
    def validate_name(cls, v):
        v = v.strip()
        if not re.match(r'^[a-zA-Z0-9\s\-_.]+$', v):
            raise ValueError('Team name contains invalid characters')
        return v

class TeamJoinRequest(BaseModel):
    """Team join request model"""
    team_id: str = Field(..., min_length=32, max_length=32)
    message: Optional[str] = Field(None, max_length=200)
    
    @validator('team_id')
    def validate_team_id(cls, v):
        try:
            int(v, 16)
        except ValueError:
            raise ValueError('Invalid team ID format')
        return v.lower()

class TeamInfo(BaseModel):
    """Team information model"""
    team_id: str
    name: str
    description: Optional[str] = None
    admin_user_id: str
    member_count: int = 0
    created_at: datetime
    is_active: bool = True

# =============================================================================
# MEETING MODELS
# =============================================================================

class MeetingCreate(BaseModel):
    """Meeting creation model"""
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_temporary: bool = True
    max_participants: int = Field(50, ge=1, le=100)
    
    @validator('name')
    def validate_name(cls, v):
        v = v.strip()
        if not re.match(r'^[a-zA-Z0-9\s\-_.]+$', v):
            raise ValueError('Meeting name contains invalid characters')
        return v

class MeetingJoinRequest(BaseModel):
    """Meeting join request model"""
    meeting_id: str = Field(..., min_length=32, max_length=32)
    message: Optional[str] = Field(None, max_length=200)
    
    @validator('meeting_id')
    def validate_meeting_id(cls, v):
        try:
            int(v, 16)
        except ValueError:
            raise ValueError('Invalid meeting ID format')
        return v.lower()

class MeetingInfo(BaseModel):
    """Meeting information model"""
    meeting_id: str
    name: str
    description: Optional[str] = None
    creator_user_id: str
    is_temporary: bool = True
    participant_count: int = 0
    max_participants: int = 50
    created_at: datetime
    is_active: bool = True

# =============================================================================
# MESSAGE MODELS
# =============================================================================

class ChatMessage(BaseModel):
    """Chat message model"""
    message: str = Field(..., min_length=1, max_length=1000)
    message_type: MessageType = MessageType.TEXT
    
    @validator('message')
    def validate_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Message cannot be empty')
        return v

class MessageInfo(BaseModel):
    """Message information model"""
    message_id: str
    user_id: str
    user_name: str
    user_public_id: str
    message: str
    message_type: MessageType
    room_id: str
    room_type: str
    created_at: datetime

# =============================================================================
# ADMIN MODELS
# =============================================================================

class AdminAction(BaseModel):
    """Admin action model"""
    target_user_id: str = Field(..., min_length=32, max_length=32)
    action: str = Field(..., pattern=r'^(approve|reject|remove|block|kick|ban|promote|demote)$')
    reason: Optional[str] = Field(None, max_length=200)
    
    @validator('target_user_id')
    def validate_target_user_id(cls, v):
        try:
            int(v, 16)
        except ValueError:
            raise ValueError('Invalid user ID format')
        return v.lower()

# =============================================================================
# WEBSOCKET MODELS
# =============================================================================

class WebSocketMessage(BaseModel):
    """WebSocket message model"""
    type: str = Field(..., min_length=1, max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: Optional[str] = None
    room_id: Optional[str] = None

class WebRTCSignal(BaseModel):
    """WebRTC signaling model"""
    type: str = Field(..., pattern=r'^(offer|answer|ice_candidate)$')
    target_user_id: str = Field(..., min_length=32, max_length=32)
    payload: Dict[str, Any]
    
    @validator('target_user_id')
    def validate_target_user_id(cls, v):
        try:
            int(v, 16)
        except ValueError:
            raise ValueError('Invalid user ID format')
        return v.lower()

class MediaState(BaseModel):
    """Media state model"""
    audio: bool = False
    video: bool = False
    screen: bool = False
    quality: Optional[str] = Field(None, pattern=r'^(low|medium|high)$')

# =============================================================================
# SETTINGS MODELS
# =============================================================================

class UserSettings(BaseModel):
    """User settings model"""
    theme: str = Field("dark", pattern=r'^(light|dark|auto)$')
    language: str = Field("en", pattern=r'^[a-z]{2}$')
    notifications_enabled: bool = True
    sound_enabled: bool = True
    video_quality: str = Field("medium", pattern=r'^(low|medium|high)$')
    auto_join_audio: bool = False
    auto_join_video: bool = False