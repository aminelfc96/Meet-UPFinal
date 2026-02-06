# utils/error_handler.py - Centralized Error Handling

import logging
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from config_manager import get_config

logger = logging.getLogger(__name__)
config = get_config()

class AppError(Exception):
    """Base application error"""
    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(AppError):
    """Validation error"""
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR", 400)

class AuthenticationError(AppError):
    """Authentication error"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR", 401)

class AuthorizationError(AppError):
    """Authorization error"""
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, "AUTHZ_ERROR", 403)

class NotFoundError(AppError):
    """Resource not found error"""
    def __init__(self, message: str = "Resource not found", resource: str = None):
        self.resource = resource
        super().__init__(message, "NOT_FOUND", 404)

class ConflictError(AppError):
    """Conflict error"""
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, "CONFLICT", 409)

class DatabaseError(AppError):
    """Database error"""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, "DB_ERROR", 500)

def create_error_response(
    error: Exception,
    request: Optional[Request] = None,
    include_details: bool = None
) -> JSONResponse:
    """Create standardized error response"""
    
    # Determine if we should include detailed error information
    if include_details is None:
        include_details = config.get('server.debug', False)
    
    # Base error response
    error_response = {
        "error": True,
        "timestamp": "2024-01-01T12:00:00Z"  # In production, use actual timestamp
    }
    
    if isinstance(error, AppError):
        # Application errors
        error_response.update({
            "code": error.code,
            "message": error.message,
            "status_code": error.status_code
        })
        
        # Add field information for validation errors
        if isinstance(error, ValidationError) and error.field:
            error_response["field"] = error.field
        
        # Add resource information for not found errors
        if isinstance(error, NotFoundError) and error.resource:
            error_response["resource"] = error.resource
        
        status_code = error.status_code
        
    elif isinstance(error, HTTPException):
        # FastAPI HTTP exceptions
        error_response.update({
            "code": f"HTTP_{error.status_code}",
            "message": error.detail,
            "status_code": error.status_code
        })
        status_code = error.status_code
        
    else:
        # Unexpected errors
        error_response.update({
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred" if not include_details else str(error),
            "status_code": 500
        })
        status_code = 500
        
        # Log unexpected errors
        logger.error(f"Unexpected error: {error}", exc_info=True)
    
    # Add detailed error information in debug mode
    if include_details and not isinstance(error, AppError):
        error_response["debug"] = {
            "type": type(error).__name__,
            "details": str(error)
        }
        
        if request:
            error_response["debug"]["request"] = {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers)
            }
    
    # Create API response format for client compatibility
    if status_code >= 400:
        api_response = {"detail": error_response["message"]}
        if include_details:
            api_response["error_info"] = error_response
    else:
        api_response = error_response
    
    return JSONResponse(
        status_code=status_code,
        content=api_response
    )

def handle_database_error(operation: str, error: Exception) -> DatabaseError:
    """Handle database errors consistently"""
    logger.error(f"Database error in {operation}: {error}")
    
    # Map specific database errors to user-friendly messages
    error_str = str(error).lower()
    
    if "unique constraint" in error_str:
        return ConflictError("Resource already exists")
    elif "foreign key" in error_str:
        return ValidationError("Invalid reference to related resource")
    elif "not null constraint" in error_str:
        return ValidationError("Required field is missing")
    elif "syntax error" in error_str:
        logger.critical(f"SQL syntax error in {operation}: {error}")
        return DatabaseError("Invalid database operation")
    else:
        return DatabaseError(f"Database operation failed: {operation}")

def safe_execute(operation_name: str):
    """Decorator for safe operation execution"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except AppError:
                # Re-raise application errors as-is
                raise
            except Exception as e:
                # Convert unexpected errors to application errors
                logger.error(f"Error in {operation_name}: {e}", exc_info=True)
                raise DatabaseError(f"Operation failed: {operation_name}")
        return wrapper
    return decorator