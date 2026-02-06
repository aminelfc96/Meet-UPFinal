# Enhanced utils.py - Utility Functions with Better Security and GDPR Compliance

import hashlib
import secrets
import mimetypes
import os
import re
import hmac
import base64
import logging
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from pathlib import Path
from typing import Union, Optional, Dict, List, Tuple
import bleach
import ipaddress

logger = logging.getLogger(__name__)

# =============================================================================
# ENCRYPTION AND SECURITY
# =============================================================================

# Generate or load encryption key (in production, use proper key management)
ENCRYPTION_KEY_FILE = "encryption.key"

def get_or_create_encryption_key() -> bytes:
    """Get existing encryption key or create new one"""
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, "wb") as f:
            f.write(key)
        os.chmod(ENCRYPTION_KEY_FILE, 0o600)  # Read-only for owner
        return key

ENCRYPTION_KEY = get_or_create_encryption_key()
fernet = Fernet(ENCRYPTION_KEY)

# Additional encryption for sensitive data
def generate_key_from_password(password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
    """Generate encryption key from password using PBKDF2"""
    if salt is None:
        salt = os.urandom(16)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt

# RSA key pair for additional security (optional)
def generate_rsa_keypair() -> Tuple[bytes, bytes]:
    """Generate RSA key pair for additional encryption"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem, public_pem

# =============================================================================
# PASSWORD SECURITY
# =============================================================================

def hash_password(password: str, salt: bytes = None) -> str:
    """Enhanced password hashing with salt"""
    if salt is None:
        salt = os.urandom(32)
    
    # Use PBKDF2 with SHA-256
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    
    # Combine salt and hash
    return base64.b64encode(salt + pwdhash).decode('ascii')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    try:
        # Decode the stored hash
        decoded = base64.b64decode(hashed.encode('ascii'))
        salt = decoded[:32]
        stored_hash = decoded[32:]
        
        # Hash the provided password with the same salt
        pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        
        # Use hmac.compare_digest for timing attack resistance
        return hmac.compare_digest(stored_hash, pwdhash)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def check_password_strength(password: str) -> Dict[str, any]:
    """Check password strength and provide feedback"""
    result = {
        "is_strong": True,
        "score": 0,
        "feedback": []
    }
    
    # Length check
    if len(password) < 8:
        result["is_strong"] = False
        result["feedback"].append("Password must be at least 8 characters long")
    else:
        result["score"] += 1
    
    # Character variety checks
    if not re.search(r"[a-z]", password):
        result["is_strong"] = False
        result["feedback"].append("Password must contain lowercase letters")
    else:
        result["score"] += 1
    
    if not re.search(r"[A-Z]", password):
        result["is_strong"] = False
        result["feedback"].append("Password must contain uppercase letters")
    else:
        result["score"] += 1
    
    if not re.search(r"\d", password):
        result["is_strong"] = False
        result["feedback"].append("Password must contain numbers")
    else:
        result["score"] += 1
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        result["feedback"].append("Consider adding special characters for stronger security")
    else:
        result["score"] += 1
    
    # Common password check (basic)
    common_passwords = ["password", "123456", "password123", "admin", "qwerty"]
    if password.lower() in common_passwords:
        result["is_strong"] = False
        result["feedback"].append("Password is too common")
    
    return result

# =============================================================================
# DATA ENCRYPTION
# =============================================================================

def encrypt_data(data: str, key: bytes = None) -> str:
    """Enhanced data encryption with optional custom key"""
    try:
        if not data:
            return ""
        
        encryption_key = key or ENCRYPTION_KEY
        f = Fernet(encryption_key) if key else fernet
        
        # Add timestamp and random padding for additional security
        timestamp = datetime.now().isoformat()
        padding = secrets.token_hex(8)
        enhanced_data = f"{timestamp}|{padding}|{data}"
        
        encrypted = f.encrypt(enhanced_data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return data  # Return original data if encryption fails

def decrypt_data(encrypted_data: str, key: bytes = None) -> str:
    """Enhanced data decryption with validation"""
    try:
        if not encrypted_data:
            return ""
        
        encryption_key = key or ENCRYPTION_KEY
        f = Fernet(encryption_key) if key else fernet
        
        # Handle both old and new encryption formats
        try:
            # Try new format first
            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = f.decrypt(decoded).decode()
            
            # Parse enhanced format
            if '|' in decrypted:
                parts = decrypted.split('|', 2)
                if len(parts) == 3:
                    timestamp_str, padding, original_data = parts
                    
                    # Validate timestamp (optional: check if not too old)
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        # Check if data is not older than 1 year (configurable)
                        if (datetime.now() - timestamp).days > 365:
                            logger.warning("Decrypting very old data")
                    except:
                        pass
                    
                    return original_data
            
            return decrypted
            
        except:
            # Fallback to old format
            return fernet.decrypt(encrypted_data.encode()).decode()
            
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return encrypted_data  # Return original if decryption fails

def encrypt_file(file_path: str, key: bytes = None) -> bool:
    """Encrypt a file in place"""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        encryption_key = key or ENCRYPTION_KEY
        f_cipher = Fernet(encryption_key) if key else fernet
        
        encrypted_data = f_cipher.encrypt(data)
        
        with open(file_path + '.enc', 'wb') as f:
            f.write(encrypted_data)
        
        # Remove original file
        os.remove(file_path)
        os.rename(file_path + '.enc', file_path)
        
        return True
    except Exception as e:
        logger.error(f"File encryption error: {e}")
        return False

# =============================================================================
# INPUT VALIDATION AND SANITIZATION
# =============================================================================

def sanitize_input(text: str, max_length: int = 1000, allow_html: bool = False) -> str:
    """Enhanced input sanitization"""
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    
    if not allow_html:
        # Remove HTML tags and potentially dangerous content
        text = bleach.clean(text, tags=[], attributes={}, strip=True)
    else:
        # Allow only safe HTML tags
        allowed_tags = ['b', 'i', 'u', 'em', 'strong', 'p', 'br']
        text = bleach.clean(text, tags=allowed_tags, attributes={}, strip=True)
    
    # Remove null bytes and other control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    # Additional XSS protection
    text = text.replace('<script', '&lt;script')
    text = text.replace('javascript:', '')
    text = text.replace('data:', '')
    
    return text

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_user_id(user_id: str) -> bool:
    """Enhanced user ID validation"""
    if not user_id:
        return False
    
    # Should be hex string of specific length
    try:
        int(user_id, 16)
        return len(user_id) == 32  # 16 bytes = 32 hex chars
    except ValueError:
        return False

def validate_team_id(team_id: str) -> bool:
    """Validate team ID format"""
    return validate_user_id(team_id)  # Same format

def validate_meeting_id(meeting_id: str) -> bool:
    """Validate meeting ID format"""
    return validate_user_id(meeting_id)

def validate_ip_address(ip: str) -> bool:
    """Validate IP address"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def validate_user_agent(user_agent: str) -> bool:
    """Validate user agent string"""
    if not user_agent or len(user_agent) > 500:
        return False
    
    # Basic check for suspicious patterns
    suspicious_patterns = ['<script', 'javascript:', 'data:', '\x00']
    return not any(pattern in user_agent.lower() for pattern in suspicious_patterns)

# =============================================================================
# FILE HANDLING SECURITY
# =============================================================================

# Enhanced file upload settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4', '.avi', '.webm'}
BLOCKED_EXTENSIONS = {'.exe', '.zip', '.rar', '.7z', '.bat', '.cmd', '.com', '.scr', '.pif', '.js', '.vbs', '.ps1'}

def is_safe_file(filename: str, file_content: bytes = None) -> Dict[str, any]:
    """Enhanced file safety check"""
    result = {
        "is_safe": True,
        "reasons": [],
        "mime_type": None,
        "detected_extension": None
    }
    
    if not filename:
        result["is_safe"] = False
        result["reasons"].append("No filename provided")
        return result
    
    # Sanitize filename
    filename = Path(filename).name
    ext = Path(filename).suffix.lower()
    
    # Check blocked extensions first
    if ext in BLOCKED_EXTENSIONS:
        result["is_safe"] = False
        result["reasons"].append(f"File extension {ext} is blocked for security reasons")
    
    # Check allowed extensions
    if ext not in ALLOWED_EXTENSIONS:
        result["is_safe"] = False
        result["reasons"].append(f"File extension {ext} is not allowed")
    
    # MIME type detection
    if file_content:
        import magic
        try:
            mime_type = magic.from_buffer(file_content, mime=True)
            result["mime_type"] = mime_type
            
            # Check if MIME type matches extension
            expected_mime = mimetypes.guess_type(filename)[0]
            if expected_mime and mime_type != expected_mime:
                result["reasons"].append("File content doesn't match extension")
        except:
            # Fallback if python-magic is not available
            mime_type = mimetypes.guess_type(filename)[0]
            result["mime_type"] = mime_type
    
    # Additional content checks
    if file_content:
        # Check for executable signatures
        executable_signatures = [
            b'MZ',  # Windows PE
            b'\x7fELF',  # Linux ELF
            b'\xca\xfe\xba\xbe',  # Mach-O
            b'PK',  # ZIP archives
        ]
        
        for sig in executable_signatures:
            if file_content.startswith(sig):
                result["is_safe"] = False
                result["reasons"].append("File appears to be executable or archive")
                break
        
        # Check for script content in supposedly safe files
        if ext in {'.txt', '.pdf', '.doc', '.docx'}:
            script_patterns = [b'<script', b'javascript:', b'data:', b'vbscript:']
            content_lower = file_content.lower()
            
            for pattern in script_patterns:
                if pattern in content_lower:
                    result["is_safe"] = False
                    result["reasons"].append("File contains potentially malicious script content")
                    break
    
    return result

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    if not filename:
        return "unknown_file"
    
    # Remove path components
    filename = Path(filename).name
    
    # Remove potentially dangerous characters
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        filename = name[:255-len(ext)] + ext
    
    # Ensure filename doesn't start with dot (hidden files)
    if filename.startswith('.'):
        filename = 'file_' + filename
    
    return filename

def get_safe_upload_path(filename: str, upload_dir: str = "uploads") -> str:
    """Generate safe upload path"""
    # Create upload directory if it doesn't exist
    os.makedirs(upload_dir, exist_ok=True)
    
    # Sanitize filename
    safe_filename = sanitize_filename(filename)
    
    # Add timestamp to prevent conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = Path(safe_filename).stem, Path(safe_filename).suffix
    unique_filename = f"{timestamp}_{secrets.token_hex(4)}_{name}{ext}"
    
    return os.path.join(upload_dir, unique_filename)

# =============================================================================
# ID GENERATION
# =============================================================================

def generate_id() -> str:
    """Generate cryptographically secure unique ID"""
    return secrets.token_hex(16)

def generate_short_id() -> str:
    """Generate short ID for public display"""
    return secrets.token_hex(4).upper()

def generate_session_token() -> str:
    """Generate secure session token"""
    return secrets.token_urlsafe(32)

def generate_api_key() -> str:
    """Generate API key"""
    return f"ma_{secrets.token_urlsafe(32)}"

# =============================================================================
# RATE LIMITING UTILITIES
# =============================================================================

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, identifier: str, limit: int, window: int = 60) -> bool:
        """Check if request is allowed under rate limit"""
        now = datetime.now()
        
        # Clean old entries
        if identifier in self.requests:
            self.requests[identifier] = [
                timestamp for timestamp in self.requests[identifier]
                if (now - timestamp).total_seconds() < window
            ]
        else:
            self.requests[identifier] = []
        
        # Check limit
        if len(self.requests[identifier]) >= limit:
            return False
        
        # Add current request
        self.requests[identifier].append(now)
        return True

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"

def generate_csrf_token() -> str:
    """Generate CSRF token"""
    return secrets.token_urlsafe(32)

def verify_csrf_token(token: str, stored_token: str) -> bool:
    """Verify CSRF token"""
    return hmac.compare_digest(token, stored_token)

def get_client_ip(request) -> str:
    """Get client IP address from request"""
    # Check for forwarded IP (behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the list
        return forwarded_for.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct connection
    return request.client.host

def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """Mask sensitive data for logging"""
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ""
    
    return data[:visible_chars] + mask_char * (len(data) - visible_chars)

def generate_audit_log_entry(
    user_id: str,
    action: str,
    resource: str,
    ip_address: str,
    user_agent: str,
    success: bool = True,
    details: Dict = None
) -> Dict:
    """Generate audit log entry"""
    return {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "ip_address": mask_sensitive_data(ip_address, visible_chars=8),
        "user_agent": mask_sensitive_data(user_agent, visible_chars=20),
        "success": success,
        "details": details or {},
        "session_id": generate_session_token()[:8]  # Short session identifier
    }

# =============================================================================
# GDPR UTILITIES
# =============================================================================

def anonymize_user_data(data: Dict) -> Dict:
    """Anonymize user data for GDPR compliance"""
    anonymized = data.copy()
    
    # Fields to anonymize
    sensitive_fields = ['name', 'email', 'ip_address', 'user_agent']
    
    for field in sensitive_fields:
        if field in anonymized:
            if field == 'email':
                # Keep domain for analytics
                email = anonymized[field]
                if '@' in email:
                    domain = email.split('@')[1]
                    anonymized[field] = f"anonymized@{domain}"
                else:
                    anonymized[field] = "anonymized"
            else:
                anonymized[field] = "anonymized"
    
    # Add anonymization timestamp
    anonymized['anonymized_at'] = datetime.now().isoformat()
    
    return anonymized

def calculate_data_retention_date(created_at: datetime, retention_days: int = 30) -> datetime:
    """Calculate when data should be deleted"""
    return created_at + timedelta(days=retention_days)

def is_data_expired(created_at: datetime, retention_days: int = 30) -> bool:
    """Check if data has expired and should be deleted"""
    expiry_date = calculate_data_retention_date(created_at, retention_days)
    return datetime.now() > expiry_date

# Global rate limiter instance
rate_limiter = RateLimiter()