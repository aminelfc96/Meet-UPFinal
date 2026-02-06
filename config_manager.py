# config_manager.py - Configuration Management System

import json
import os
import secrets
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigManager:
    """Centralized configuration management for the webapp"""
    
    def __init__(self, config_file: str = None):
        # Auto-detect environment and config file
        self.environment = os.getenv('ENVIRONMENT', 'development')
        
        if config_file is None:
            if self.environment == 'production':
                config_file = "config_production.json"
            elif self.environment == 'staging':
                config_file = "config_staging.json"
            else:
                config_file = "config.json"
        
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self._load_config()
        self._apply_environment_overrides()
        self._validate_config()
        self._setup_auto_generated_values()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_file}")
            else:
                logger.warning(f"Config file {self.config_file} not found, using defaults")
                self._config = self._get_default_config()
                self._save_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._config = self._get_default_config()
    
    def _save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def _apply_environment_overrides(self):
        """Apply environment variable overrides"""
        # Override allowed origins if ALLOWED_ORIGINS is set
        allowed_origins = os.getenv('ALLOWED_ORIGINS')
        if allowed_origins:
            origins = [origin.strip() for origin in allowed_origins.split(',')]
            self._config.setdefault('security', {})['allowed_origins'] = origins
            logger.info(f"CORS origins overridden from environment: {origins}")
        
        # Override secret key if SECRET_KEY is set
        secret_key = os.getenv('SECRET_KEY')
        if secret_key:
            self._config.setdefault('security', {})['secret_key'] = secret_key
            logger.info("Secret key overridden from environment")
        
        # Override domain if DOMAIN is set
        domain = os.getenv('DOMAIN')
        if domain:
            # Auto-generate HTTPS origins for the domain
            origins = [
                f"https://{domain}",
                f"https://www.{domain}"
            ]
            # Add IP if provided
            ip_address = os.getenv('SERVER_IP')
            if ip_address:
                origins.append(f"https://{ip_address}")
            
            self._config.setdefault('security', {})['allowed_origins'] = origins
            logger.info(f"Auto-configured CORS for domain: {domain}")
        
        # Override database path for production
        if self.environment == 'production':
            self._config.setdefault('database', {})['path'] = '/app/data/meeting_app.db'
            self._config.setdefault('file_upload', {})['upload_directory'] = '/app/uploads'
            self._config.setdefault('logging', {})['log_directory'] = '/app/logs'
    
    def _validate_config(self):
        """Validate configuration values"""
        errors = []
        
        # Validate required sections
        required_sections = ['server', 'security', 'features', 'validation']
        for section in required_sections:
            if section not in self._config:
                errors.append(f"Missing required section: {section}")
        
        # Validate password length
        min_pass = self.get('validation.password_min_length', 4)
        max_pass = self.get('validation.password_max_length', 128)
        if min_pass > max_pass:
            errors.append("password_min_length cannot be greater than password_max_length")
        
        # Validate token expiry
        access_expire = self.get('security.jwt.access_token_expire_minutes', 60)
        if access_expire < 1:
            errors.append("access_token_expire_minutes must be at least 1")
        
        # Validate rate limiting
        if self.get('security.rate_limiting.enabled', True):
            auth_rate = self.get('security.rate_limiting.auth_requests_per_minute', 5)
            if auth_rate < 1:
                errors.append("auth_requests_per_minute must be at least 1")
        
        # Validate file upload size
        max_size = self.get('file_upload.max_file_size_mb', 10)
        if max_size < 1 or max_size > 100:
            errors.append("max_file_size_mb must be between 1 and 100")
        
        if errors:
            logger.error("Configuration validation errors:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        logger.info("Configuration validation passed")
    
    def _setup_auto_generated_values(self):
        """Setup auto-generated values like secret keys"""
        # Generate secret key if needed
        if self.get('security.secret_key') == 'auto-generate':
            secret_key = secrets.token_hex(32)
            self.set('security.secret_key', secret_key)
            self._save_config()
            logger.info("Auto-generated secret key")
        
        # Create directories
        directories = [
            self.get('file_upload.upload_directory', 'uploads'),
            self.get('logging.log_directory', 'logs'),
            'static/css',
            'static/js',
            'static/html'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'security.jwt.access_token_expire_minutes')"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation"""
        keys = key.split('.')
        config = self._config
        
        # Navigate to the parent of the target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get(f'features.{feature}', True)
    
    def get_allowed_origins(self) -> list:
        """Get allowed origins for CORS"""
        origins = self.get('security.allowed_origins', [])
        
        # Add environment-specific origins
        env_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
        for origin in env_origins:
            origin = origin.strip()
            if origin and origin not in origins:
                origins.append(origin)
        
        return origins
    
    def get_secret_key(self) -> str:
        """Get secret key, prioritizing environment variable"""
        env_key = os.getenv('SECURITY_KEY')
        if env_key:
            return env_key
        
        config_key = self.get('security.secret_key')
        if not config_key or config_key == 'auto-generate':
            # Generate and save new key
            new_key = secrets.token_hex(32)
            self.set('security.secret_key', new_key)
            self._save_config()
            return new_key
        
        return config_key
    
    def get_database_path(self) -> str:
        """Get database path"""
        return self.get('database.path', 'webapp.db')
    
    def reload_config(self):
        """Reload configuration from file"""
        logger.info("Reloading configuration")
        self._load_config()
        self._validate_config()
    
    def export_config(self, file_path: str):
        """Export current configuration to a file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Configuration exported to {file_path}")
        except Exception as e:
            logger.error(f"Error exporting config: {e}")
            raise
    
    def import_config(self, file_path: str):
        """Import configuration from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                new_config = json.load(f)
            
            # Backup current config
            backup_path = f"{self.config_file}.backup"
            self.export_config(backup_path)
            
            # Load new config
            self._config = new_config
            self._validate_config()
            self._save_config()
            
            logger.info(f"Configuration imported from {file_path}")
        except Exception as e:
            logger.error(f"Error importing config: {e}")
            raise
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "debug": False,
                "reload": False
            },
            "security": {
                "secret_key": "auto-generate",
                "allowed_origins": [
                    "http://localhost:8000",
                    "https://localhost:8000", 
                    "http://127.0.0.1:8000",
                    "https://127.0.0.1:8000"
                ],
                "csrf_protection": {
                    "enabled": True,
                    "token_expiry_hours": 1
                },
                "jwt": {
                    "access_token_expire_minutes": 60,
                    "refresh_token_expire_days": 7,
                    "algorithm": "HS256"
                },
                "rate_limiting": {
                    "enabled": True,
                    "auth_requests_per_minute": 5,
                    "api_requests_per_minute": 30,
                    "static_requests_per_minute": 60,
                    "max_strikes": 3,
                    "ban_duration_minutes": 30
                },
                "anti_bot": {
                    "enabled": True,
                    "strict_user_agent_check": True,
                    "block_automation_tools": True,
                    "require_browser_headers": True
                }
            },
            "features": {
                "user_registration": True,
                "team_creation": True,
                "team_joining": True,
                "meeting_creation": True,
                "meeting_joining": True,
                "file_upload": True,
                "chat_functionality": True,
                "secret_id_retrieval": True,
                "account_deletion": True
            },
            "validation": {
                "password_min_length": 4,
                "password_max_length": 128,
                "username_min_length": 1,
                "username_max_length": 50
            },
            "file_upload": {
                "enabled": True,
                "max_file_size_mb": 10,
                "allowed_extensions": [".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt"],
                "upload_directory": "uploads"
            }
        }

# Global configuration instance
config = ConfigManager()

def get_config() -> ConfigManager:
    """Get the global configuration instance"""
    return config

def is_feature_enabled(feature: str) -> bool:
    """Quick check if a feature is enabled"""
    return config.is_feature_enabled(feature)

def get_setting(key: str, default: Any = None) -> Any:
    """Quick access to configuration settings"""
    return config.get(key, default)