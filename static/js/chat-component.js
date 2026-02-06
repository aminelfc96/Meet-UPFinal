/**
 * Unified Chat Component
 * 
 * A reusable chat component that can be used for both meetings and teams.
 * Provides common functionality like message display, sending, WebSocket handling.
 */

class UnifiedChatComponent {
    constructor(config) {
        this.config = {
            // Required
            containerId: config.containerId,
            inputId: config.inputId,
            sendButtonId: config.sendButtonId,
            wsUrl: config.wsUrl,
            
            // Optional
            maxMessageLength: config.maxMessageLength || 500,
            enableHistory: config.enableHistory || false,
            enableFiles: config.enableFiles || false,
            enableThrottling: config.enableThrottling || true,
            historyEndpoint: config.historyEndpoint || null,
            messageType: config.messageType || 'message',
            
            // Callbacks
            onConnectionChange: config.onConnectionChange || (() => {}),
            onMessageReceived: config.onMessageReceived || (() => {}),
            onError: config.onError || (() => {}),
            
            // Throttling settings
            sendThrottle: config.sendThrottle || 1000,
            displayThrottle: config.displayThrottle || 500,
            
            ...config
        };
        
        // Internal state
        this.ws = null;
        this.connectionStatus = 'disconnected';
        this.lastSendTime = 0;
        this.lastDisplayTime = 0;
        this.messageQueue = [];
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        this.init();
    }
    
    init() {
        this.setupElements();
        this.setupEventListeners();
        if (this.config.enableHistory) {
            this.loadHistory();
        }
        this.connect();
    }
    
    setupElements() {
        this.container = document.getElementById(this.config.containerId);
        this.input = document.getElementById(this.config.inputId);
        this.sendButton = document.getElementById(this.config.sendButtonId);
        
        if (!this.container || !this.input) {
            throw new Error('Required chat elements not found');
        }
        
        // Add chat container class for styling
        this.container.classList.add('unified-chat-container');
    }
    
    setupEventListeners() {
        // Send message on Enter key
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Send button click
        if (this.sendButton) {
            this.sendButton.addEventListener('click', () => {
                this.sendMessage();
            });
        }
        
        // Auto-resize textarea if it's a textarea
        if (this.input.tagName.toLowerCase() === 'textarea') {
            this.input.addEventListener('input', () => {
                this.autoResizeTextarea();
            });
        }
    }
    
    autoResizeTextarea() {
        if (this.input.tagName.toLowerCase() === 'textarea') {
            this.input.style.height = 'auto';
            this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';
        }
    }
    
    connect() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            return;
        }
        
        this.updateConnectionStatus('connecting');
        
        try {
            this.ws = new WebSocket(this.config.wsUrl);
            
            this.ws.onopen = () => {
                console.log('Chat WebSocket connected');
                this.updateConnectionStatus('connected');
                this.reconnectAttempts = 0;
                this.processMessageQueue();
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.ws.onclose = () => {
                console.log('Chat WebSocket disconnected');
                this.updateConnectionStatus('disconnected');
                this.scheduleReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('Chat WebSocket error:', error);
                this.config.onError('Connection error');
            };
            
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.updateConnectionStatus('disconnected');
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            
            setTimeout(() => {
                console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, delay);
        } else {
            this.config.onError('Failed to reconnect to chat');
        }
    }
    
    updateConnectionStatus(status) {
        this.connectionStatus = status;
        this.config.onConnectionChange(status);
        
        // Update input state based on connection
        if (this.input) {
            this.input.disabled = status !== 'connected';
            this.input.placeholder = status === 'connected' 
                ? 'Type a message...' 
                : status === 'connecting' 
                    ? 'Connecting...' 
                    : 'Disconnected';
        }
    }
    
    sendMessage() {
        if (!this.input.value.trim()) return;
        
        const message = this.input.value.trim();
        
        // Validate message length
        if (message.length > this.config.maxMessageLength) {
            this.config.onError(`Message too long (max ${this.config.maxMessageLength} characters)`);
            return;
        }
        
        // Check send throttling
        if (this.config.enableThrottling) {
            const now = Date.now();
            if (now - this.lastSendTime < this.config.sendThrottle) {
                this.config.onError('Please wait before sending another message');
                return;
            }
            this.lastSendTime = now;
        }
        
        const messageData = {
            type: this.config.messageType,
            message: message,
            timestamp: new Date().toISOString()
        };
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(messageData));
            this.input.value = '';
            this.autoResizeTextarea();
        } else {
            // Queue message for when connection is restored
            this.messageQueue.push(messageData);
            this.config.onError('Message queued - not connected');
        }
    }
    
    processMessageQueue() {
        while (this.messageQueue.length > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
            const message = this.messageQueue.shift();
            this.ws.send(JSON.stringify(message));
        }
    }
    
    handleMessage(data) {
        // Apply display throttling if enabled
        if (this.config.enableThrottling) {
            const now = Date.now();
            if (now - this.lastDisplayTime < this.config.displayThrottle) {
                setTimeout(() => this.handleMessage(data), this.config.displayThrottle);
                return;
            }
            this.lastDisplayTime = now;
        }
        
        // Call external message handler first
        this.config.onMessageReceived(data);
        
        // Handle common message types
        switch (data.type) {
            case 'message':
            case 'chat':
                this.displayMessage(data);
                break;
            case 'file':
                if (this.config.enableFiles) {
                    this.displayFileMessage(data);
                }
                break;
            case 'system':
            case 'system_notification':
                this.displaySystemMessage(data.message || data.content);
                break;
        }
    }
    
    displayMessage(data) {
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message';
        
        // Add own message class if it's from current user
        if (data.user_id === this.getCurrentUserId()) {
            messageElement.classList.add('own-message');
        }
        
        const time = this.formatTime(data.timestamp);
        const userName = this.escapeHtml(data.user_name || data.name || 'Unknown');
        const messageText = this.escapeHtml(data.message);
        
        messageElement.innerHTML = `
            <div class="message-header">
                <span class="user-name">${userName}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">${messageText}</div>
        `;
        
        this.container.appendChild(messageElement);
        this.scrollToBottom();
    }
    
    displayFileMessage(data) {
        if (!this.config.enableFiles) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message file-message';
        
        if (data.user_id === this.getCurrentUserId()) {
            messageElement.classList.add('own-message');
        }
        
        const time = this.formatTime(data.timestamp);
        const userName = this.escapeHtml(data.user_name || data.name || 'Unknown');
        const fileName = this.escapeHtml(data.file_name || 'Unknown file');
        const fileSize = this.formatFileSize(data.file_size || 0);
        const fileUrl = data.file_url || '#';
        
        messageElement.innerHTML = `
            <div class="message-header">
                <span class="user-name">${userName}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">
                <div class="file-message-content">
                    <div class="file-info">
                        <span class="file-icon">📁</span>
                        <div class="file-details">
                            <a href="${fileUrl}" target="_blank" class="file-name">${fileName}</a>
                            <span class="file-size">${fileSize}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.container.appendChild(messageElement);
        this.scrollToBottom();
    }
    
    displaySystemMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message system-message';
        
        const time = this.formatTime(new Date().toISOString());
        
        messageElement.innerHTML = `
            <div class="message-content">
                <span class="system-icon">🔔</span>
                <span class="system-text">${this.escapeHtml(message)}</span>
                <span class="message-time">${time}</span>
            </div>
        `;
        
        this.container.appendChild(messageElement);
        this.scrollToBottom();
    }
    
    async loadHistory() {
        if (!this.config.historyEndpoint) return;
        
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(this.config.historyEndpoint, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.ok) {
                const messages = await response.json();
                messages.forEach(message => this.displayMessage(message));
            }
        } catch (error) {
            console.error('Error loading chat history:', error);
        }
    }
    
    scrollToBottom() {
        this.container.scrollTop = this.container.scrollHeight;
    }
    
    // Utility functions
    formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit', 
            hour12: false 
        });
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    }
    
    getCurrentUserId() {
        try {
            const currentUser = JSON.parse(localStorage.getItem('currentUser'));
            return currentUser?.user_id;
        } catch {
            return null;
        }
    }
    
    // Public methods
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.updateConnectionStatus('disconnected');
    }
    
    clear() {
        this.container.innerHTML = '';
    }
    
    sendSystemMessage(message) {
        this.displaySystemMessage(message);
    }
    
    setEnabled(enabled) {
        if (this.input) {
            this.input.disabled = !enabled;
        }
        if (this.sendButton) {
            this.sendButton.disabled = !enabled;
        }
    }
}