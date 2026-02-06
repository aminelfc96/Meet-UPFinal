# Admin Configuration Guide

## 📋 Overview

This webapp uses a centralized configuration system that allows administrators to easily modify application behavior, security settings, and feature availability without code changes.

## 🔧 Configuration Files

### Main Configuration File: `config.json`

The primary configuration file located in the root directory. All settings are organized into logical sections.

### Environment Variables

Certain sensitive settings can be overridden using environment variables:
- `SECURITY_KEY`: JWT signing key (overrides config.json)
- `ALLOWED_ORIGINS`: Comma-separated list of allowed origins

## 📖 Configuration Sections

### 1. Server Settings

```json
{
  "server": {
    "host": "0.0.0.0",          // Server binding address
    "port": 8000,               // Server port
    "debug": false,             // Debug mode (development only)
    "reload": false             // Auto-reload on changes (development only)
  }
}
```

### 2. Security Configuration

```json
{
  "security": {
    "secret_key": "auto-generate",        // JWT signing key (auto-generated if not set)
    "allowed_origins": [                  // CORS allowed origins
      "http://localhost:8000",
      "https://localhost:8000"
    ],
    "csrf_protection": {
      "enabled": true,                    // Enable/disable CSRF protection
      "token_expiry_hours": 1            // CSRF token validity period
    },
    "jwt": {
      "access_token_expire_minutes": 60,  // Access token lifespan
      "refresh_token_expire_days": 7,     // Refresh token lifespan
      "algorithm": "HS256"                // JWT signing algorithm
    },
    "rate_limiting": {
      "enabled": true,                    // Enable/disable rate limiting
      "auth_requests_per_minute": 5,      // Login/register rate limit
      "api_requests_per_minute": 30,      // API endpoints rate limit
      "static_requests_per_minute": 60,   // Static files rate limit
      "max_strikes": 3,                   // Strikes before IP ban
      "ban_duration_minutes": 30          // IP ban duration
    },
    "anti_bot": {
      "enabled": true,                    // Enable/disable bot protection
      "strict_user_agent_check": true,    // Strict UA validation
      "block_automation_tools": true,     // Block curl, wget, etc.
      "require_browser_headers": true     // Require standard headers
    },
    "device_fingerprinting": {
      "enabled": true,                    // Enable device fingerprinting
      "strict_validation": true           // Strict fingerprint matching
    }
  }
}
```

### 3. Feature Flags

```json
{
  "features": {
    "user_registration": true,            // Allow new user registration
    "team_creation": true,                // Allow team creation
    "team_joining": true,                 // Allow joining teams
    "meeting_creation": true,             // Allow meeting creation
    "meeting_joining": true,              // Allow joining meetings
    "file_upload": true,                  // Enable file uploads
    "chat_functionality": true,           // Enable chat features
    "secret_id_retrieval": true,          // Allow secret ID access
    "account_deletion": true,             // Allow account deletion
    "admin_management": true              // Enable admin features
  }
}
```

### 4. Input Validation

```json
{
  "validation": {
    "password_min_length": 4,             // Minimum password length
    "password_max_length": 128,           // Maximum password length
    "username_min_length": 1,             // Minimum username length
    "username_max_length": 50,            // Maximum username length
    "team_name_max_length": 100,          // Maximum team name length
    "meeting_name_max_length": 100,       // Maximum meeting name length
    "message_max_length": 1000            // Maximum chat message length
  }
}
```

### 5. File Upload Settings

```json
{
  "file_upload": {
    "enabled": true,                      // Enable/disable file uploads
    "max_file_size_mb": 10,              // Maximum file size in MB
    "allowed_extensions": [               // Allowed file extensions
      ".jpg", ".jpeg", ".png", ".gif", 
      ".pdf", ".txt", ".doc", ".docx"
    ],
    "upload_directory": "uploads",        // Upload directory path
    "scan_files": true                    // Enable virus scanning (if available)
  }
}
```

### 6. Database Configuration

```json
{
  "database": {
    "path": "webapp.db",                  // SQLite database file path
    "backup_enabled": true,               // Enable automatic backups
    "backup_interval_hours": 24,          // Backup frequency
    "auto_vacuum": true                   // Enable auto-vacuum
  }
}
```

### 7. Logging Settings

```json
{
  "logging": {
    "level": "INFO",                      // Log level (DEBUG, INFO, WARNING, ERROR)
    "enable_file_logging": true,          // Write logs to files
    "log_directory": "logs",              // Log files directory
    "max_log_file_size_mb": 50,          // Maximum log file size
    "backup_count": 5,                    // Number of log file backups
    "log_security_events": true,          // Log security-related events
    "log_api_requests": false             // Log all API requests
  }
}
```

### 8. WebSocket Configuration

```json
{
  "websocket": {
    "enabled": true,                      // Enable WebSocket functionality
    "max_connections_per_room": 50,       // Max connections per chat room
    "connection_timeout_seconds": 300,    // Connection timeout
    "heartbeat_interval_seconds": 30      // Heartbeat interval
  }
}
```

### 9. Session Management

```json
{
  "session": {
    "auto_logout_inactive_minutes": 1440, // Auto-logout after inactivity
    "remember_device_days": 30,           // Device fingerprint validity
    "max_concurrent_sessions": 5          // Max sessions per user
  }
}
```

### 10. UI Configuration

```json
{
  "ui": {
    "show_public_ids": true,              // Display public IDs in UI
    "enable_dark_mode": true,             // Enable dark mode option
    "show_user_count": true,              // Show user counts in teams
    "enable_notifications": true,         // Enable browser notifications
    "auto_refresh_interval_seconds": 30   // Auto-refresh frequency
  }
}
```

## 🛠️ Administration Tasks

### Disabling Features

To disable a feature, set its flag to `false`:

```json
{
  "features": {
    "user_registration": false,   // Disables new registrations
    "file_upload": false         // Disables file upload functionality
  }
}
```

### Adjusting Security Levels

#### High Security Environment
```json
{
  "security": {
    "rate_limiting": {
      "auth_requests_per_minute": 3,
      "max_strikes": 2
    },
    "anti_bot": {
      "strict_user_agent_check": true,
      "require_browser_headers": true
    },
    "device_fingerprinting": {
      "strict_validation": true
    }
  },
  "validation": {
    "password_min_length": 8
  }
}
```

#### Development Environment
```json
{
  "server": {
    "debug": true,
    "reload": true
  },
  "security": {
    "anti_bot": {
      "enabled": false
    },
    "rate_limiting": {
      "enabled": false
    }
  },
  "logging": {
    "level": "DEBUG",
    "log_api_requests": true
  }
}
```

### Maintenance Mode

To put the app in maintenance mode, disable most features:

```json
{
  "features": {
    "user_registration": false,
    "team_creation": false,
    "meeting_creation": false,
    "file_upload": false
  }
}
```

## 🔄 Configuration Management

### Reloading Configuration

The application automatically loads configuration on startup. To apply changes:

1. **Method 1**: Restart the application
2. **Method 2**: Use the config reload endpoint (if implemented)
3. **Method 3**: Send SIGHUP signal (Unix systems)

### Backup and Restore

#### Creating a Backup
```bash
cp config.json config.json.backup.$(date +%Y%m%d_%H%M%S)
```

#### Restoring from Backup
```bash
cp config.json.backup.20240101_120000 config.json
```

### Validation

The application validates configuration on startup and will:
- Log warnings for invalid values
- Use default values for missing settings
- Fail to start if critical validation errors occur

## 🚨 Security Considerations

### Critical Settings

1. **Never disable security features in production**:
   - `csrf_protection.enabled: true`
   - `anti_bot.enabled: true`
   - `rate_limiting.enabled: true`

2. **Use strong secret keys**:
   - Let the system auto-generate the secret key
   - Or provide a cryptographically secure key via environment variable

3. **Restrict origins**:
   - Only include trusted domains in `allowed_origins`
   - Never use wildcard origins (`*`) in production

### Access Control

1. **Protect the config file**:
   ```bash
   chmod 600 config.json
   chown webapp:webapp config.json
   ```

2. **Environment variables for secrets**:
   ```bash
   export SECURITY_KEY="your-secure-random-key-here"
   ```

### Monitoring

Enable security logging to monitor configuration changes:

```json
{
  "logging": {
    "log_security_events": true,
    "level": "INFO"
  }
}
```

## 📊 Performance Tuning

### High Traffic Settings

```json
{
  "security": {
    "rate_limiting": {
      "api_requests_per_minute": 100,
      "static_requests_per_minute": 200
    }
  },
  "websocket": {
    "max_connections_per_room": 100
  },
  "performance": {
    "enable_caching": true,
    "enable_compression": true
  }
}
```

### Resource Constrained Settings

```json
{
  "file_upload": {
    "max_file_size_mb": 5
  },
  "websocket": {
    "max_connections_per_room": 25,
    "connection_timeout_seconds": 120
  },
  "logging": {
    "max_log_file_size_mb": 25,
    "backup_count": 3
  }
}
```

## 🔍 Troubleshooting

### Common Issues

1. **Application won't start**:
   - Check config.json syntax (valid JSON)
   - Verify file permissions
   - Check logs for validation errors

2. **Features not working**:
   - Verify feature flags are enabled
   - Check browser console for errors
   - Ensure configuration was reloaded

3. **Security blocking legitimate users**:
   - Review rate limiting settings
   - Check anti-bot configuration
   - Verify allowed origins

### Debug Configuration

```json
{
  "logging": {
    "level": "DEBUG",
    "log_api_requests": true,
    "log_security_events": true
  }
}
```

## 📝 Change Log Template

When modifying configuration, document changes:

```
Date: 2024-01-01
Admin: John Doe
Changes:
- Increased password minimum length from 4 to 8
- Disabled user registration temporarily
- Enabled debug logging for troubleshooting
Reason: Security audit recommendations
```

## 🆘 Emergency Procedures

### Disable All Non-Essential Features
```json
{
  "features": {
    "user_registration": false,
    "team_creation": false,
    "meeting_creation": false,
    "file_upload": false
  }
}
```

### Maximum Security Mode
```json
{
  "security": {
    "rate_limiting": {
      "auth_requests_per_minute": 1,
      "api_requests_per_minute": 10,
      "max_strikes": 1
    },
    "anti_bot": {
      "enabled": true,
      "strict_user_agent_check": true
    }
  }
}
```

This configuration system provides complete control over the webapp's behavior while maintaining security and usability standards.