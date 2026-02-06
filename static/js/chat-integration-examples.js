/**
 * Chat Integration Examples
 * 
 * This file shows how to integrate the UnifiedChatComponent into meetings and teams.
 * These examples can be used to replace the existing chat functionality.
 */

// =============================================================================
// MEETING CHAT INTEGRATION EXAMPLE
// =============================================================================

/**
 * Initialize chat for meetings
 * Replace the existing meeting chat implementation with this
 */
function initializeMeetingChat(meetingId) {
    // Create chat instance for meetings
    const meetingChat = new UnifiedChatComponent({
        // Required configuration
        containerId: 'chat-messages',           // ID of chat messages container
        inputId: 'chat-input',                  // ID of input element
        sendButtonId: 'send-button',            // ID of send button (optional)
        wsUrl: `ws://localhost:8000/ws/meeting/${meetingId}`,
        
        // Meeting-specific configuration
        maxMessageLength: 500,                  // Shorter messages for meetings
        enableHistory: false,                   // No persistent history for meetings
        enableFiles: false,                     // No file sharing in meetings
        enableThrottling: true,                 // Prevent spam
        messageType: 'chat',                    // WebSocket message type
        
        // Throttling settings
        sendThrottle: 1000,                     // 1 second between sends
        displayThrottle: 500,                   // 500ms display throttle
        
        // Event handlers
        onConnectionChange: (status) => {
            updateMeetingConnectionStatus(status);
        },
        
        onMessageReceived: (data) => {
            // Handle meeting-specific message types
            switch (data.type) {
                case 'user_joined':
                    addParticipantVideo(data.user);
                    break;
                case 'user_left':
                    removeParticipantVideo(data.user);
                    break;
                case 'media_state':
                    updateParticipantMediaState(data.user, data.mediaState);
                    break;
                case 'meeting_ended':
                    handleMeetingEnded();
                    break;
                // Add other meeting-specific handlers
            }
        },
        
        onError: (message) => {
            createToast(message, 'error');
        }
    });
    
    return meetingChat;
}

/**
 * Update connection status for meetings
 */
function updateMeetingConnectionStatus(status) {
    const statusElement = document.getElementById('connection-status');
    if (statusElement) {
        statusElement.className = `connection-status ${status}`;
        statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    }
}

// =============================================================================
// TEAM CHAT INTEGRATION EXAMPLE
// =============================================================================

/**
 * Initialize chat for teams
 * Replace the existing team chat implementation with this
 */
function initializeTeamChat(teamId) {
    // Create chat instance for teams
    const teamChat = new UnifiedChatComponent({
        // Required configuration
        containerId: 'messages-container',      // ID of chat messages container
        inputId: 'message-input',               // ID of input element (textarea)
        sendButtonId: 'send-message-btn',       // ID of send button
        wsUrl: `ws://localhost:8000/ws/team/${teamId}`,
        
        // Team-specific configuration
        maxMessageLength: 1000,                 // Longer messages for teams
        enableHistory: true,                    // Load message history
        enableFiles: true,                      // Support file sharing
        enableThrottling: false,                // No throttling for team chat
        messageType: 'message',                 // WebSocket message type
        
        // History endpoint
        historyEndpoint: `/api/teams/${teamId}/messages`,
        
        // Event handlers
        onConnectionChange: (status) => {
            updateTeamConnectionStatus(status);
        },
        
        onMessageReceived: (data) => {
            // Handle team-specific message types
            switch (data.type) {
                case 'team_deleted':
                    handleTeamDeleted(data);
                    break;
                case 'member_joined':
                    showSystemMessage(`${data.user_name} joined the team`);
                    break;
                case 'member_left':
                    showSystemMessage(`${data.user_name} left the team`);
                    break;
                // Add other team-specific handlers
            }
        },
        
        onError: (message) => {
            showError(message);
        }
    });
    
    return teamChat;
}

/**
 * Update connection status for teams
 */
function updateTeamConnectionStatus(status) {
    const statusElement = document.getElementById('team-status');
    if (statusElement) {
        statusElement.className = `team-status ${status}`;
        statusElement.textContent = `Chat: ${status}`;
    }
}

// =============================================================================
// MIGRATION HELPERS
// =============================================================================

/**
 * Migration helper: Replace existing meeting chat
 * Use this to gradually migrate from the old implementation
 */
function migrateMeetingChat(meetingId) {
    // Initialize new chat component
    const newChat = initializeMeetingChat(meetingId);
    
    // Disable old chat functions (if they exist)
    if (window.sendChatMessage) {
        window.sendChatMessage = () => {
            console.warn('Old sendChatMessage disabled - using unified chat');
        };
    }
    
    if (window.displayChatMessage) {
        window.displayChatMessage = () => {
            console.warn('Old displayChatMessage disabled - using unified chat');
        };
    }
    
    return newChat;
}

/**
 * Migration helper: Replace existing team chat
 * Use this to gradually migrate from the old implementation
 */
function migrateTeamChat(teamId) {
    // Initialize new chat component
    const newChat = initializeTeamChat(teamId);
    
    // Disable old chat functions (if they exist)
    if (window.sendMessage) {
        window.sendMessage = () => {
            console.warn('Old sendMessage disabled - using unified chat');
        };
    }
    
    if (window.displayMessage) {
        window.displayMessage = () => {
            console.warn('Old displayMessage disabled - using unified chat');
        };
    }
    
    return newChat;
}

// =============================================================================
// ADVANCED USAGE EXAMPLES
// =============================================================================

/**
 * Example: Chat with custom message handlers
 */
function createCustomChat(config) {
    return new UnifiedChatComponent({
        ...config,
        
        onMessageReceived: (data) => {
            // Custom message processing
            console.log('Received message:', data);
            
            // Apply content filters
            if (data.message && containsProfanity(data.message)) {
                data.message = '[Message filtered]';
            }
            
            // Add message reactions
            if (data.reactions) {
                addMessageReactions(data);
            }
            
            // Handle mentions
            if (data.mentions && data.mentions.includes(getCurrentUserId())) {
                playNotificationSound();
                highlightMessage(data);
            }
        }
    });
}

/**
 * Example: Multi-room chat manager
 */
class MultiRoomChatManager {
    constructor() {
        this.activeChats = new Map();
        this.currentRoom = null;
    }
    
    joinRoom(roomId, roomType, config) {
        if (this.activeChats.has(roomId)) {
            return this.activeChats.get(roomId);
        }
        
        const chatConfig = {
            ...config,
            wsUrl: `ws://localhost:8000/ws/${roomType}/${roomId}`,
            onConnectionChange: (status) => {
                this.updateRoomStatus(roomId, status);
            }
        };
        
        const chat = new UnifiedChatComponent(chatConfig);
        this.activeChats.set(roomId, chat);
        
        return chat;
    }
    
    leaveRoom(roomId) {
        const chat = this.activeChats.get(roomId);
        if (chat) {
            chat.disconnect();
            this.activeChats.delete(roomId);
        }
    }
    
    switchToRoom(roomId) {
        // Hide all chat containers
        this.activeChats.forEach((chat, id) => {
            const container = document.getElementById(chat.config.containerId);
            if (container) {
                container.style.display = id === roomId ? 'block' : 'none';
            }
        });
        
        this.currentRoom = roomId;
    }
    
    updateRoomStatus(roomId, status) {
        console.log(`Room ${roomId} status: ${status}`);
        // Update UI accordingly
    }
    
    cleanup() {
        this.activeChats.forEach(chat => chat.disconnect());
        this.activeChats.clear();
    }
}

// =============================================================================
// UTILITY FUNCTIONS FOR EXAMPLES
// =============================================================================

function containsProfanity(message) {
    // Simple profanity filter example
    const profanityList = ['spam', 'bad', 'inappropriate'];
    return profanityList.some(word => 
        message.toLowerCase().includes(word.toLowerCase())
    );
}

function addMessageReactions(data) {
    // Add message reactions UI
    console.log('Adding reactions:', data.reactions);
}

function playNotificationSound() {
    // Play notification sound for mentions
    const audio = new Audio('/static/sounds/notification.mp3');
    audio.play().catch(e => console.log('Could not play sound:', e));
}

function highlightMessage(data) {
    // Highlight mentioned messages
    console.log('Highlighting message for mention:', data);
}

function getCurrentUserId() {
    try {
        const user = JSON.parse(localStorage.getItem('currentUser'));
        return user?.user_id;
    } catch {
        return null;
    }
}

// Export for use in other files
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializeMeetingChat,
        initializeTeamChat,
        migrateMeetingChat,
        migrateTeamChat,
        MultiRoomChatManager
    };
}