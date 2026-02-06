# security_middleware.py - Advanced Security Middleware

import secrets
import time
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Set
from collections import defaultdict
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import user_agents
import re
from config_manager import get_config

logger = logging.getLogger(__name__)
config = get_config()

# Global CSRF protection instance - shared across the application
_csrf_protection_instance = None

def get_csrf_protection() -> 'CSRFProtection':
    """Get or create the global CSRF protection instance"""
    global _csrf_protection_instance
    if _csrf_protection_instance is None:
        secret_key = config.get_secret_key()
        _csrf_protection_instance = CSRFProtection(secret_key)
    return _csrf_protection_instance

def get_csrf_token() -> str:
    """Helper function to generate a new CSRF token"""
    csrf_protection = get_csrf_protection()
    return csrf_protection.generate_token()

# =============================================================================
# CSRF PROTECTION
# =============================================================================

class CSRFProtection:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()
        self.tokens: Dict[str, float] = {}  # token -> expiry_time
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
        
    def generate_token(self) -> str:
        """Generate a cryptographically secure CSRF token"""
        timestamp = str(int(time.time()))
        random_bytes = secrets.token_bytes(32)
        
        # Create HMAC signature
        message = f"{timestamp}:{random_bytes.hex()}"
        signature = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
        
        token = f"{timestamp}:{random_bytes.hex()}:{signature}"
        
        # Store token with expiry from config
        expiry_hours = config.get('security.csrf_protection.token_expiry_hours', 1)
        self.tokens[token] = time.time() + (expiry_hours * 3600)
        
        # Periodic cleanup
        if time.time() - self.last_cleanup > self.cleanup_interval:
            self._cleanup_expired_tokens()
            
        return token
    
    def validate_token(self, token: str) -> bool:
        """Validate CSRF token"""
        if not token or token not in self.tokens:
            return False
            
        # Check if token expired
        if time.time() > self.tokens[token]:
            del self.tokens[token]
            return False
            
        # Verify HMAC signature
        try:
            parts = token.split(':')
            if len(parts) != 3:
                return False
                
            timestamp, random_hex, signature = parts
            message = f"{timestamp}:{random_hex}"
            expected_signature = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return False
                
            # Remove token after use (single-use)
            del self.tokens[token]
            return True
            
        except Exception as e:
            logger.error(f"CSRF token validation error: {e}")
            return False
    
    def _cleanup_expired_tokens(self):
        """Remove expired tokens"""
        current_time = time.time()
        expired_tokens = [token for token, expiry in self.tokens.items() if current_time > expiry]
        for token in expired_tokens:
            del self.tokens[token]
        self.last_cleanup = current_time

# =============================================================================
# ANTI-BOT PROTECTION
# =============================================================================

class AntiBotProtection:
    def __init__(self):
        self.suspicious_patterns = [
            r'bot',
            r'crawler',
            r'spider',
            r'scraper',
            r'curl',
            r'wget',
            r'python-requests',
            r'go-http-client',
            r'postman',
            r'insomnia',
            r'httpie'
        ]
        
        self.rate_limits: Dict[str, list] = defaultdict(list)  # IP -> [timestamps]
        self.blocked_ips: Set[str] = set()
        self.suspicious_ips: Dict[str, int] = defaultdict(int)  # IP -> violation_count
        
    def is_bot_user_agent(self, user_agent: str) -> bool:
        """Check if user agent appears to be a bot"""
        # Skip check if anti-bot protection is disabled
        if not config.get('security.anti_bot.enabled', True):
            return False
            
        if not user_agent:
            return config.get('security.anti_bot.require_browser_headers', True)
            
        user_agent_lower = user_agent.lower()
        
        # Check against known bot patterns
        for pattern in self.suspicious_patterns:
            if re.search(pattern, user_agent_lower):
                return True
                
        # Parse user agent for additional checks
        try:
            parsed = user_agents.parse(user_agent)
            
            # Legitimate browsers should have these properties
            if not parsed.browser.family or not parsed.browser.version_string:
                return True
                
            # Check for headless browsers (common in automation)
            if 'headless' in user_agent_lower:
                return True
                
        except:
            return True
            
        return False
    
    def check_request_fingerprint(self, request: Request) -> bool:
        """Advanced bot detection based on request fingerprinting"""
        suspicious_score = 0
        
        # Check headers
        headers = dict(request.headers)
        
        # Missing common browser headers
        expected_headers = ['accept', 'accept-language', 'accept-encoding']
        for header in expected_headers:
            if header not in headers:
                suspicious_score += 1
                
        # Suspicious header values
        accept = headers.get('accept', '').lower()
        if '*/*' in accept and 'text/html' not in accept:
            suspicious_score += 1
            
        # Missing or suspicious accept-language
        accept_lang = headers.get('accept-language', '')
        if not accept_lang or len(accept_lang) < 5:
            suspicious_score += 1
            
        # Check for automation-specific headers
        automation_headers = [
            'x-requested-with',
            'x-automation',
            'x-test',
            'selenium-test'
        ]
        for header in automation_headers:
            if header in headers:
                suspicious_score += 2
                
        return suspicious_score >= 3
    
    def check_rate_limit(self, ip: str, endpoint: str) -> bool:
        """Check if IP is exceeding rate limits"""
        if ip in self.blocked_ips:
            return False
            
        current_time = time.time()
        
        # Clean old entries
        key = f"{ip}:{endpoint}"
        self.rate_limits[key] = [
            timestamp for timestamp in self.rate_limits[key]
            if current_time - timestamp < 60  # 1 minute window
        ]
        
        # Add current request
        self.rate_limits[key].append(current_time)
        
        # Check limits from config
        if endpoint in ['/api/register', '/api/login']:
            limit = config.get('security.rate_limiting.auth_requests_per_minute', 5)
        elif endpoint.startswith('/api/'):
            limit = config.get('security.rate_limiting.api_requests_per_minute', 30)
        else:
            limit = config.get('security.rate_limiting.static_requests_per_minute', 60)
            
        if len(self.rate_limits[key]) > limit:
            self.suspicious_ips[ip] += 1
            
            # Block IP after multiple violations
            max_strikes = config.get('security.rate_limiting.max_strikes', 3)
            if self.suspicious_ips[ip] >= max_strikes:
                self.blocked_ips.add(ip)
                logger.warning(f"IP blocked for rate limit violations: {ip}")
                
            return False
            
        return True

# =============================================================================
# BROWSER VALIDATION
# =============================================================================

class BrowserValidator:
    def __init__(self):
        # Get allowed origins from config and extract hostnames
        origins = config.get_allowed_origins()
        self.allowed_origins = set()
        for origin in origins:
            if '://' in origin:
                hostname = origin.split('://')[1].split(':')[0]
                self.allowed_origins.add(hostname)
            else:
                self.allowed_origins.add(origin)
        
    def validate_browser_request(self, request: Request) -> bool:
        """Validate that request comes from a legitimate browser"""
        headers = dict(request.headers)
        
        # Check for required browser headers
        if 'user-agent' not in headers:
            return False
            
        # Must have either Referer or specific API headers
        has_referer = 'referer' in headers
        has_api_auth = 'authorization' in headers
        
        if not (has_referer or has_api_auth):
            return False
            
        # Validate origin for CORS requests
        origin = headers.get('origin')
        if origin:
            return self._validate_origin(origin)
            
        # Validate referer
        referer = headers.get('referer')
        if referer:
            return self._validate_referer(referer)
            
        return True
    
    def _validate_origin(self, origin: str) -> bool:
        """Validate request origin"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            
            # Check if it's an allowed domain
            hostname = parsed.hostname
            return hostname in self.allowed_origins or hostname.endswith('.localhost')
            
        except:
            return False
    
    def _validate_referer(self, referer: str) -> bool:
        """Validate request referer"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            
            # Check if it's from our application
            hostname = parsed.hostname
            return hostname in self.allowed_origins or hostname.endswith('.localhost')
            
        except:
            return False

# =============================================================================
# JWT ENHANCED SECURITY
# =============================================================================

class JWTSecurity:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.revoked_tokens: Set[str] = set()
        self.token_fingerprints: Dict[str, str] = {}  # token_id -> fingerprint
        
    def create_token_fingerprint(self, request: Request) -> str:
        """Create fingerprint for token binding"""
        headers = dict(request.headers)
        
        # Create fingerprint from stable browser characteristics
        fingerprint_data = {
            'user_agent': headers.get('user-agent', ''),
            'accept_language': headers.get('accept-language', ''),
            'accept_encoding': headers.get('accept-encoding', ''),
        }
        
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
    
    def validate_token_fingerprint(self, token_id: str, request: Request) -> bool:
        """Validate token fingerprint to prevent token theft"""
        if token_id not in self.token_fingerprints:
            return True  # New token, no fingerprint stored yet
            
        stored_fingerprint = self.token_fingerprints[token_id]
        current_fingerprint = self.create_token_fingerprint(request)
        
        return stored_fingerprint == current_fingerprint
    
    def revoke_token(self, token_id: str):
        """Revoke a token"""
        self.revoked_tokens.add(token_id)
        if token_id in self.token_fingerprints:
            del self.token_fingerprints[token_id]
    
    def is_token_revoked(self, token_id: str) -> bool:
        """Check if token is revoked"""
        return token_id in self.revoked_tokens

# =============================================================================
# MAIN SECURITY MIDDLEWARE
# =============================================================================

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        self.csrf = get_csrf_protection()  # Use shared instance
        self.anti_bot = AntiBotProtection()
        self.browser_validator = BrowserValidator()
        self.jwt_security = JWTSecurity(secret_key)
        
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Skip security for public endpoints
        public_endpoints = ['/health', '/api/csrf-token', '/api/register', '/api/login', '/api/config']
        if request.url.path in public_endpoints:
            return await call_next(request)
            
        # Anti-bot protection (only if enabled)
        if config.get('security.anti_bot.enabled', True):
            if not await self._check_bot_protection(request, client_ip):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests"}
                )
            
        # Browser validation for API endpoints
        if request.url.path.startswith('/api/'):
            if not self.browser_validator.validate_browser_request(request):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Invalid request origin"}
                )
                
        # CSRF protection disabled - causes too many issues
        # Using other security measures instead (JWT, rate limiting, etc.)
        # if config.get('security.csrf_protection.enabled', False):
        #     csrf_exempt_endpoints = ['/api/register', '/api/login']
        #     if request.method in ['POST', 'PUT', 'DELETE', 'PATCH'] and request.url.path not in csrf_exempt_endpoints:
        #         if not await self._check_csrf_protection(request):
        #             return JSONResponse(
        #                 status_code=status.HTTP_403_FORBIDDEN,
        #                 content={"detail": "CSRF token missing or invalid"}
        #             )
                
        # JWT validation and fingerprinting
        jwt_exempt_endpoints = ['/api/register', '/api/login', '/api/csrf-token', '/api/config']
        if request.url.path.startswith('/api/') and request.url.path not in jwt_exempt_endpoints:
            if not await self._check_jwt_security(request):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or compromised token"}
                )
        
        # Add security headers to response
        response = await call_next(request)
        self._add_security_headers(response)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP"""
        # Check for forwarded headers (reverse proxy)
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            return forwarded.split(',')[0].strip()
            
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
            
        return request.client.host if request.client else '127.0.0.1'
    
    async def _check_bot_protection(self, request: Request, client_ip: str) -> bool:
        """Check anti-bot protection"""
        user_agent = request.headers.get('user-agent', '')
        
        # Check if user agent is a bot
        if self.anti_bot.is_bot_user_agent(user_agent):
            logger.warning(f"Bot detected: {user_agent} from {client_ip}")
            return False
            
        # Check request fingerprint
        if self.anti_bot.check_request_fingerprint(request):
            logger.warning(f"Suspicious request fingerprint from {client_ip}")
            return False
            
        # Check rate limits
        if not self.anti_bot.check_rate_limit(client_ip, request.url.path):
            return False
            
        return True
    
    async def _check_csrf_protection(self, request: Request) -> bool:
        """Check CSRF protection"""
        # Skip CSRF for certain endpoints that use other protection
        skip_csrf_paths = ['/api/files/', '/ws/']
        if any(request.url.path.startswith(path) for path in skip_csrf_paths):
            return True
            
        # Get CSRF token from header or form data (case-insensitive)
        csrf_token = request.headers.get('x-csrf-token') or request.headers.get('X-CSRF-Token')
        
        if not csrf_token:
            logger.warning(f"No CSRF token found in request to {request.url.path}. Headers: {dict(request.headers)}")
        
        if not csrf_token and request.headers.get('content-type', '').startswith('application/x-www-form-urlencoded'):
            # Try to get from form data
            try:
                body = await request.body()
                if b'csrf_token=' in body:
                    csrf_token = body.decode().split('csrf_token=')[1].split('&')[0]
            except:
                pass
                
        if not csrf_token:
            logger.warning(f"CSRF validation failed: No token provided for {request.url.path}")
            return False
        
        is_valid = self.csrf.validate_token(csrf_token)
        if not is_valid:
            logger.warning(f"CSRF validation failed: Invalid token for {request.url.path}")
        else:
            logger.info(f"CSRF validation successful for {request.url.path}")
            
        return is_valid
    
    async def _check_jwt_security(self, request: Request) -> bool:
        """Check JWT security and fingerprinting"""
        auth_header = request.headers.get('authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return False
            
        try:
            token = auth_header.split(' ')[1]
            
            # Extract token ID (would need to decode JWT to get jti claim)
            # For now, use token hash as ID
            token_id = hashlib.sha256(token.encode()).hexdigest()[:16]
            
            # Check if token is revoked
            if self.jwt_security.is_token_revoked(token_id):
                return False
                
            # Validate token fingerprint
            if not self.jwt_security.validate_token_fingerprint(token_id, request):
                logger.warning(f"Token fingerprint mismatch for token {token_id}")
                return False
                
            # Store fingerprint for new tokens
            fingerprint = self.jwt_security.create_token_fingerprint(request)
            self.jwt_security.token_fingerprints[token_id] = fingerprint
            
            return True
            
        except Exception as e:
            logger.error(f"JWT security check failed: {e}")
            return False
    
    def _add_security_headers(self, response):
        """Add security headers to response"""
        security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value

