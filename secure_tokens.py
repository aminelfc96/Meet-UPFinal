"""
Secure Token Management for One-Time File Access
Prevents replay attacks and unauthorized file access
"""

import time
import secrets
import hashlib
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from threading import Lock
import logging

logger = logging.getLogger(__name__)

@dataclass
class FileAccessToken:
    """Represents a secure file access token"""
    token: str
    file_id: str
    user_id: str
    team_id: str
    created_at: float
    expires_at: float
    used: bool = False
    access_type: str = "download"  # download, preview
    max_uses: int = 1
    use_count: int = 0

class SecureTokenManager:
    """Manages secure one-time file access tokens"""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.tokens: Dict[str, FileAccessToken] = {}
        self.lock = Lock()
        self.default_ttl = default_ttl
        self.cleanup_interval = 60  # Cleanup every minute
        self.last_cleanup = time.time()
    
    def generate_token(self, file_id: str, user_id: str, team_id: str, 
                      access_type: str = "download", ttl: Optional[int] = None,
                      max_uses: int = 1) -> str:
        """Generate a secure one-time access token"""
        with self.lock:
            # Generate cryptographically secure token
            token_bytes = secrets.token_bytes(32)
            timestamp = str(int(time.time() * 1000))
            combined = f"{file_id}:{user_id}:{team_id}:{timestamp}".encode()
            
            # Create hash to prevent tampering
            hash_obj = hashlib.sha256(token_bytes + combined)
            token = hash_obj.hexdigest()
            
            # Set expiration
            now = time.time()
            expires_at = now + (ttl or self.default_ttl)
            
            # Store token
            access_token = FileAccessToken(
                token=token,
                file_id=file_id,
                user_id=user_id,
                team_id=team_id,
                created_at=now,
                expires_at=expires_at,
                access_type=access_type,
                max_uses=max_uses
            )
            
            self.tokens[token] = access_token
            
            # Cleanup old tokens periodically
            if now - self.last_cleanup > self.cleanup_interval:
                self._cleanup_expired_tokens()
                self.last_cleanup = now
            
            logger.info(f"Generated {access_type} token for file {file_id} by user {user_id}")
            return token
    
    def validate_and_consume_token(self, token: str) -> Optional[FileAccessToken]:
        """Validate token and mark as used (one-time use)"""
        with self.lock:
            access_token = self.tokens.get(token)
            
            if not access_token:
                logger.warning(f"Token not found: {token[:8]}...")
                return None
            
            now = time.time()
            
            # Check if expired
            if now > access_token.expires_at:
                logger.warning(f"Expired token used: {token[:8]}...")
                del self.tokens[token]
                return None
            
            # Check if already used up
            if access_token.use_count >= access_token.max_uses:
                logger.warning(f"Token already used: {token[:8]}...")
                del self.tokens[token]
                return None
            
            # Mark as used
            access_token.use_count += 1
            
            # Remove if max uses reached
            if access_token.use_count >= access_token.max_uses:
                del self.tokens[token]
            
            logger.info(f"Token consumed for file {access_token.file_id} by user {access_token.user_id}")
            return access_token
    
    def get_token_info(self, token: str) -> Optional[FileAccessToken]:
        """Get token information without consuming it"""
        with self.lock:
            return self.tokens.get(token)
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a specific token"""
        with self.lock:
            if token in self.tokens:
                del self.tokens[token]
                logger.info(f"Token revoked: {token[:8]}...")
                return True
            return False
    
    def revoke_user_tokens(self, user_id: str) -> int:
        """Revoke all tokens for a specific user"""
        with self.lock:
            tokens_to_remove = []
            for token, access_token in self.tokens.items():
                if access_token.user_id == user_id:
                    tokens_to_remove.append(token)
            
            for token in tokens_to_remove:
                del self.tokens[token]
            
            logger.info(f"Revoked {len(tokens_to_remove)} tokens for user {user_id}")
            return len(tokens_to_remove)
    
    def revoke_file_tokens(self, file_id: str) -> int:
        """Revoke all tokens for a specific file"""
        with self.lock:
            tokens_to_remove = []
            for token, access_token in self.tokens.items():
                if access_token.file_id == file_id:
                    tokens_to_remove.append(token)
            
            for token in tokens_to_remove:
                del self.tokens[token]
            
            logger.info(f"Revoked {len(tokens_to_remove)} tokens for file {file_id}")
            return len(tokens_to_remove)
    
    def _cleanup_expired_tokens(self):
        """Remove expired tokens (internal use)"""
        now = time.time()
        expired_tokens = []
        
        for token, access_token in self.tokens.items():
            if now > access_token.expires_at:
                expired_tokens.append(token)
        
        for token in expired_tokens:
            del self.tokens[token]
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired tokens")
    
    def get_stats(self) -> Dict:
        """Get token manager statistics"""
        with self.lock:
            now = time.time()
            active_tokens = 0
            expired_tokens = 0
            
            for access_token in self.tokens.values():
                if now <= access_token.expires_at:
                    active_tokens += 1
                else:
                    expired_tokens += 1
            
            return {
                "total_tokens": len(self.tokens),
                "active_tokens": active_tokens,
                "expired_tokens": expired_tokens,
                "last_cleanup": self.last_cleanup
            }

# Global token manager instance
token_manager = SecureTokenManager()

def generate_secure_file_token(file_id: str, user_id: str, team_id: str, 
                             access_type: str = "download", ttl: Optional[int] = None) -> str:
    """Convenience function to generate secure file access token"""
    return token_manager.generate_token(file_id, user_id, team_id, access_type, ttl)

def validate_file_token(token: str) -> Optional[FileAccessToken]:
    """Convenience function to validate and consume file access token"""
    return token_manager.validate_and_consume_token(token)

def revoke_file_token(token: str) -> bool:
    """Convenience function to revoke a file access token"""
    return token_manager.revoke_token(token)