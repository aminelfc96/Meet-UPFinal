/**
 * Application Utilities
 * 
 * Shared JavaScript utilities to eliminate code redundancy across the application.
 * Includes common patterns for initialization, authentication, WebSocket handling,
 * error messages, and other frequently used functionality.
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

const AppConfig = {
    // API endpoints
    API_BASE: '/api',
    WS_BASE: 'ws://localhost:8000/ws',
    
    // Message limits
    MAX_TEAM_MESSAGE_LENGTH: 1000,
    MAX_MEETING_MESSAGE_LENGTH: 500,
    
    // File limits
    MAX_FILE_SIZE: 300 * 1024, // 300KB
    ALLOWED_FILE_TYPES: ['.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'],
    
    // UI timeouts
    TOAST_DURATION: 5000,
    RECONNECT_DELAY: 2000,
    THROTTLE_DELAY: 1000,
    
    // WebSocket settings
    WS_PING_INTERVAL: 30000,
    WS_MAX_RECONNECT_ATTEMPTS: 5,
    
    // Video quality settings
    VIDEO_CONSTRAINTS: {
        low: { width: 640, height: 360, frameRate: 15 },
        medium: { width: 1280, height: 720, frameRate: 24 },
        high: { width: 1920, height: 1080, frameRate: 30 }
    }
};

// =============================================================================
// APP INITIALIZER
// =============================================================================

class AppInitializer {
    constructor() {
        this.authToken = null;
        this.currentUser = null;
        this.initialized = false;
    }
    
    async initialize() {
        if (this.initialized) return true;
        
        try {
            // Get authentication data
            this.authToken = localStorage.getItem('authToken');
            const userStr = localStorage.getItem('currentUser');
            
            if (!this.authToken || !userStr) {
                this.handleAuthFailure('Please login first');
                return false;
            }
            
            try {
                this.currentUser = JSON.parse(userStr);
            } catch (error) {
                this.handleAuthFailure('Invalid session data');
                return false;
            }
            
            // Validate token with server
            if (!await this.validateToken()) {
                this.handleAuthFailure('Session expired');
                return false;
            }
            
            this.initialized = true;
            return true;
            
        } catch (error) {
            console.error('Initialization error:', error);
            this.handleAuthFailure('Initialization failed');
            return false;
        }
    }
    
    async validateToken() {
        try {
            const response = await fetch(`${AppConfig.API_BASE}/auth/validate`, {
                headers: { 'Authorization': `Bearer ${this.authToken}` }
            });
            return response.ok;
        } catch (error) {
            console.error('Token validation error:', error);
            return false;
        }
    }
    
    handleAuthFailure(message) {
        MessageService.showError(message);
        setTimeout(() => {
            window.location.href = '/';
        }, 2000);
    }
    
    getAuthHeaders() {
        return {
            'Authorization': `Bearer ${this.authToken}`,
            'Content-Type': 'application/json'
        };
    }
    
    extractIdFromUrl() {
        const pathParts = window.location.pathname.split('/');
        return pathParts[pathParts.length - 1];
    }
    
    logout() {
        this.authToken = null;
        this.currentUser = null;
        localStorage.removeItem('authToken');
        localStorage.removeItem('currentUser');
        this.initialized = false;
        window.location.href = '/';
    }
}

// =============================================================================
// MESSAGE SERVICE (Error/Success/Toast handling)
// =============================================================================

class MessageService {
    static toastContainer = null;
    
    static init() {
        if (!this.toastContainer) {
            this.toastContainer = document.createElement('div');
            this.toastContainer.id = 'toast-container';
            this.toastContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-width: 400px;
            `;
            document.body.appendChild(this.toastContainer);
        }
    }
    
    static showMessage(message, type = 'info', duration = AppConfig.TOAST_DURATION) {
        this.init();
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            padding: 12px 16px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease-out;
            cursor: pointer;
            word-wrap: break-word;
        `;
        
        // Set background color based on type
        const colors = {
            error: '#dc3545',
            success: '#28a745',
            warning: '#ffc107',
            info: '#17a2b8'
        };
        toast.style.backgroundColor = colors[type] || colors.info;
        
        toast.textContent = message;
        
        // Close on click
        toast.addEventListener('click', () => {
            this.removeToast(toast);
        });
        
        this.toastContainer.appendChild(toast);
        
        // Auto remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.removeToast(toast);
            }, duration);
        }
    }
    
    static removeToast(toast) {
        if (toast && toast.parentNode) {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }
    }
    
    static showError(message, duration) {
        this.showMessage(message, 'error', duration);
    }
    
    static showSuccess(message, duration) {
        this.showMessage(message, 'success', duration);
    }
    
    static showWarning(message, duration) {
        this.showMessage(message, 'warning', duration);
    }
    
    static showInfo(message, duration) {
        this.showMessage(message, 'info', duration);
    }
    
    static clear() {
        if (this.toastContainer) {
            this.toastContainer.innerHTML = '';
        }
    }
}

// =============================================================================
// API SERVICE
// =============================================================================

class ApiService {
    constructor(appInitializer) {
        this.app = appInitializer;
    }
    
    async request(endpoint, options = {}) {
        const url = endpoint.startsWith('http') ? endpoint : `${AppConfig.API_BASE}${endpoint}`;
        
        const config = {
            headers: this.app.getAuthHeaders(),
            ...options
        };
        
        try {
            const response = await fetch(url, config);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || data.message || `HTTP ${response.status}`);
            }
            
            return data;
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
    
    async get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }
    
    async post(endpoint, body = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }
    
    async put(endpoint, body = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
    }
    
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

// =============================================================================
// WEBSOCKET SERVICE
// =============================================================================

class WebSocketService {
    constructor(url, options = {}) {
        this.url = url;
        this.options = {
            autoReconnect: true,
            maxReconnectAttempts: AppConfig.WS_MAX_RECONNECT_ATTEMPTS,
            reconnectDelay: AppConfig.RECONNECT_DELAY,
            pingInterval: AppConfig.WS_PING_INTERVAL,
            ...options
        };
        
        this.ws = null;
        this.reconnectAttempts = 0;
        this.pingTimer = null;
        this.isConnecting = false;
        
        // Event handlers
        this.onOpen = this.options.onOpen || (() => {});
        this.onMessage = this.options.onMessage || (() => {});
        this.onClose = this.options.onClose || (() => {});
        this.onError = this.options.onError || (() => {});
        this.onReconnect = this.options.onReconnect || (() => {});
    }
    
    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        
        this.isConnecting = true;
        
        try {
            this.ws = new WebSocket(this.url);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected:', this.url);
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.startPing();
                this.onOpen();
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type !== 'pong') { // Ignore pong responses
                        this.onMessage(data);
                    }
                } catch (error) {
                    console.error('Failed to parse WebSocket message:', error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected:', this.url);
                this.isConnecting = false;
                this.stopPing();
                this.onClose();
                
                if (this.options.autoReconnect) {
                    this.scheduleReconnect();
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.isConnecting = false;
                this.onError(error);
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.isConnecting = false;
            this.onError(error);
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.options.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        
        setTimeout(() => {
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.options.maxReconnectAttempts})`);
            this.onReconnect(this.reconnectAttempts);
            this.connect();
        }, delay);
    }
    
    startPing() {
        if (this.pingTimer) return;
        
        this.pingTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'ping' });
            }
        }, this.options.pingInterval);
    }
    
    stopPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            return true;
        }
        return false;
    }
    
    disconnect() {
        this.options.autoReconnect = false;
        this.stopPing();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
    
    getState() {
        if (!this.ws) return 'disconnected';
        
        switch (this.ws.readyState) {
            case WebSocket.CONNECTING: return 'connecting';
            case WebSocket.OPEN: return 'connected';
            case WebSocket.CLOSING: return 'closing';
            case WebSocket.CLOSED: return 'disconnected';
            default: return 'unknown';
        }
    }
}

// =============================================================================
// VALIDATION UTILITIES
// =============================================================================

class ValidationUtils {
    static validateId(id, fieldName = 'ID') {
        if (!id || typeof id !== 'string') {
            throw new Error(`${fieldName} is required`);
        }
        
        if (!/^[a-f0-9]+$/i.test(id)) {
            throw new Error(`${fieldName} must be a valid hex string`);
        }
        
        if (id.length < 8 || id.length > 64) {
            throw new Error(`${fieldName} must be between 8 and 64 characters`);
        }
        
        return id.toLowerCase();
    }
    
    static validateMessage(message, maxLength = 1000) {
        if (!message || typeof message !== 'string') {
            throw new Error('Message is required');
        }
        
        message = message.trim();
        if (!message) {
            throw new Error('Message cannot be empty');
        }
        
        if (message.length > maxLength) {
            throw new Error(`Message too long (max ${maxLength} characters)`);
        }
        
        return message;
    }
    
    static validateFile(file) {
        if (!file) {
            throw new Error('File is required');
        }
        
        if (file.size > AppConfig.MAX_FILE_SIZE) {
            throw new Error(`File too large (max ${AppConfig.MAX_FILE_SIZE / 1024 / 1024}MB)`);
        }
        
        const extension = '.' + file.name.split('.').pop().toLowerCase();
        if (!AppConfig.ALLOWED_FILE_TYPES.includes(extension)) {
            throw new Error(`File type ${extension} not allowed`);
        }
        
        return true;
    }
}

// =============================================================================
// FORMAT UTILITIES
// =============================================================================

class FormatUtils {
    static escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
    
    static formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit', 
            hour12: false 
        });
    }
    
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    static formatDate(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleDateString([], {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }
    
    static formatDateTime(timestamp) {
        return this.formatDate(timestamp) + ' ' + this.formatTime(timestamp);
    }
}

// =============================================================================
// THROTTLE UTILITY
// =============================================================================

class ThrottleUtils {
    static throttle(func, delay) {
        let timeoutId;
        let lastExecTime = 0;
        
        return function (...args) {
            const currentTime = Date.now();
            
            if (currentTime - lastExecTime > delay) {
                func.apply(this, args);
                lastExecTime = currentTime;
            } else {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => {
                    func.apply(this, args);
                    lastExecTime = Date.now();
                }, delay - (currentTime - lastExecTime));
            }
        };
    }
    
    static debounce(func, delay) {
        let timeoutId;
        
        return function (...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => func.apply(this, args), delay);
        };
    }
}

// =============================================================================
// GLOBAL INSTANCES
// =============================================================================

// Create global instances for easy access
const appInitializer = new AppInitializer();
const apiService = new ApiService(appInitializer);

// Add CSS for animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AppConfig,
        AppInitializer,
        MessageService,
        ApiService,
        WebSocketService,
        ValidationUtils,
        FormatUtils,
        ThrottleUtils,
        appInitializer,
        apiService
    };
}