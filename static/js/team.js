// team.js - Team Chat JavaScript

// Global variables
let teamId = null;
let token = null;
let currentUser = null;
let ws = null;
let connectionStatus = 'disconnected';
let isAdmin = false;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initializeTeamChat();
});

function initializeTeamChat() {
    // Get team ID from URL or element
    const teamIdElement = document.getElementById('team-id');
    if (teamIdElement) {
        teamId = teamIdElement.textContent;
    } else {
        // Extract from URL if needed
        const pathParts = window.location.pathname.split('/');
        teamId = pathParts[pathParts.length - 1];
    }
    
    // Get auth token
    token = localStorage.getItem('authToken');
    const userStr = localStorage.getItem('currentUser');
    
    if (!token || !userStr) {
        showError('Please login first');
        setTimeout(() => window.close(), 2000);
        return;
    }
    
    try {
        currentUser = JSON.parse(userStr);
    } catch (error) {
        showError('Invalid session data');
        setTimeout(() => window.close(), 2000);
        return;
    }
    
    // Update team ID display and fetch team name
    if (teamIdElement) {
        teamIdElement.textContent = teamId;
        // Fetch and display team name
        fetchTeamName();
    }
    
    // Connect to WebSocket
    connectWebSocket();
    
    // Set up event listeners
    setupEventListeners();
    
    // Check admin status and setup UI
    checkAdminStatus();
    
    // Load chat history
    loadChatHistory();
    
    // Show connection status
    updateConnectionStatus('connecting');
}

async function loadChatHistory() {
    if (!token || !teamId) return;
    
    try {
        const response = await fetch(`/api/teams/${teamId}/messages`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        
        if (response.ok) {
            const messages = await response.json();
            messages.forEach(message => {
                displayMessage({
                    ...message,
                    type: message.message_type === 'file' ? 'file' : 'message'
                });
            });
            
            // Load all image previews after messages are displayed
            setTimeout(() => {
                const imagePreviews = document.querySelectorAll('.image-preview[data-file-id]');
                imagePreviews.forEach(preview => loadImagePreview(preview));
            }, 100);
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

async function fetchTeamName() {
    try {
        const response = await fetch('/api/user/teams', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const teams = await response.json();
            const currentTeam = teams.find(team => team.team_id === teamId);
            
            if (currentTeam) {
                // Update the header to show team name and ID
                const teamIdElement = document.getElementById('team-id');
                if (teamIdElement) {
                    teamIdElement.innerHTML = `<span class="team-name">${escapeHtml(currentTeam.name)}</span> <span class="team-id-small">(${teamId})</span>`;
                }
                
                // Also update page title
                document.title = `Team Chat - ${currentTeam.name}`;
            }
        }
    } catch (error) {
        console.error('Error fetching team name:', error);
    }
}

async function checkAdminStatus() {
    if (!token || !teamId || !currentUser) return;
    
    try {
        const response = await fetch('/api/user/teams', {
            headers: {'Authorization': `Bearer ${token}`}
        });
        
        if (response.ok) {
            const teams = await response.json();
            const currentTeam = teams.find(team => team.team_id === teamId);
            
            if (currentTeam) {
                isAdmin = currentTeam.is_admin;
                
                // Hide members button if not admin
                const membersBtn = document.getElementById('members-btn');
                if (membersBtn && !isAdmin) {
                    membersBtn.style.display = 'none';
                }
            }
        }
    } catch (error) {
        console.error('Error checking admin status:', error);
    }
}

function connectWebSocket() {
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/team/${teamId}?token=${token}`;
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            updateConnectionStatus('connected');
            displaySystemMessage('Connected to team chat');
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        ws.onclose = function(event) {
            updateConnectionStatus('disconnected');
            displaySystemMessage('Disconnected from team chat');
            
            // Don't reconnect if force disconnected
            if (connectionStatus === 'force_disconnected') {
                return;
            }
            
            // Attempt to reconnect after 3 seconds
            setTimeout(() => {
                if (connectionStatus === 'disconnected') {
                    connectWebSocket();
                }
            }, 3000);
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus('disconnected');
            showError('Connection error occurred');
        };
        
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        updateConnectionStatus('disconnected');
        showError('Failed to connect to team chat');
    }
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'system':
            displaySystemMessage(data.message);
            break;
        case 'message':
            if (data.message_type === 'file') {
                displayFileMessage(data);
            } else {
                displayMessage(data);
            }
            break;
        case 'file':
            displayFileMessage(data);
            break;
        case 'team_deleted':
            // Team was deleted by admin
            showTeamDeletedUI();
            setTimeout(() => window.close(), 5000);
            break;
        case 'chat_cleared':
            handleChatCleared(data);
            break;
        case 'member_action':
            handleMemberAction(data);
            break;
        case 'team_request_approved':
            handleTeamRequestApproved(data);
            break;
        case 'team_request_rejected':
            handleTeamRequestRejected(data);
            break;
        case 'team_unbanned':
            handleTeamUnbanned(data);
            break;
        case 'force_disconnect':
            handleForceDisconnect(data);
            break;
        case 'user_kicked':
            displaySystemMessage(data.message);
            break;
        case 'team_join_request':
            handleNewJoinRequest(data);
            break;
        case 'pending_request_update':
            handlePendingRequestUpdate(data);
            break;
        default:
            // Default to regular message handling
            displayMessage(data);
    }
}

function showTeamDeletedUI() {
    // Hide normal chat UI and show deleted message
    const chatContainer = document.querySelector('.chat-container');
    const inputArea = document.querySelector('.input-area');
    
    if (chatContainer) chatContainer.style.display = 'none';
    if (inputArea) inputArea.style.display = 'none';
    
    // Create deleted UI
    const deletedDiv = document.createElement('div');
    deletedDiv.id = 'team-deleted-status';
    deletedDiv.className = 'team-deleted-status';
    deletedDiv.innerHTML = `
        <div class="deleted-content">
            <div class="deleted-icon">🗑️</div>
            <h2>Team Deleted</h2>
            <p>This team has been deleted by the admin and is no longer available.</p>
            <p class="team-id">Team ID: ${teamId}</p>
            <p class="auto-close">This window will close automatically in 5 seconds...</p>
        </div>
    `;
    
    // Add styles
    deletedDiv.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;
    
    const deletedContent = deletedDiv.querySelector('.deleted-content');
    deletedContent.style.cssText = `
        text-align: center;
        color: white;
        padding: 40px;
        border-radius: 12px;
        background: #333;
        border: 2px solid #ff69b4;
        max-width: 400px;
        width: 90%;
    `;
    
    const deletedIcon = deletedDiv.querySelector('.deleted-icon');
    deletedIcon.style.cssText = `
        font-size: 60px;
        margin-bottom: 20px;
        display: block;
        color: #dc3545;
    `;
    
    const h2 = deletedDiv.querySelector('h2');
    h2.style.cssText = `
        color: #ff69b4;
        margin-bottom: 15px;
        font-size: 2em;
    `;
    
    const teamIdEl = deletedDiv.querySelector('.team-id');
    teamIdEl.style.cssText = `
        font-family: monospace;
        background: rgba(255, 255, 255, 0.1);
        padding: 8px;
        border-radius: 4px;
        font-size: 14px;
        margin: 10px 0;
    `;
    
    const autoClose = deletedDiv.querySelector('.auto-close');
    autoClose.style.cssText = `
        font-style: italic;
        color: #ccc;
        font-size: 12px;
        margin-top: 20px;
    `;
    
    document.body.appendChild(deletedDiv);
}

function setupEventListeners() {
    // Message input
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        });
        
        messageInput.addEventListener('input', function() {
            // Auto-resize if needed
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 100) + 'px';
        });
    }
    
    // File input
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', function(event) {
            handleFileSelection(event.target.files[0]);
        });
    }
    
    // Window events
    window.addEventListener('beforeunload', function() {
        if (ws) {
            ws.close();
        }
    });
    
    window.addEventListener('focus', function() {
        if (connectionStatus === 'disconnected') {
            connectWebSocket();
        }
    });
}

function sendMessage() {
    const messageInput = document.getElementById('message-input');
    if (!messageInput || !ws || ws.readyState !== WebSocket.OPEN) {
        showError('Cannot send message - not connected');
        return;
    }
    
    const message = messageInput.value.trim();
    if (!message) {
        return;
    }
    
    if (message.length > 1000) {
        showError('Message too long (max 1000 characters)');
        return;
    }
    
    try {
        ws.send(JSON.stringify({
            type: 'message',
            message: message,
            message_type: 'text'
        }));
        
        messageInput.value = '';
        messageInput.style.height = 'auto';
    } catch (error) {
        console.error('Error sending message:', error);
        showError('Failed to send message');
    }
}

async function handleFileSelection(file) {
    if (!file) return;
    
    // Validate file size (300KB)
    if (file.size > 300 * 1024) {
        showError('File size must be less than 300KB');
        return;
    }
    
    // Validate file type
    const allowedTypes = ['.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'];
    const blockedTypes = ['.exe', '.zip', '.rar', '.7z', '.bat', '.cmd', '.com', '.scr', '.pif'];
    
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();
    
    if (blockedTypes.includes(fileExt)) {
        showError('This file type is not allowed for security reasons');
        return;
    }
    
    if (!allowedTypes.includes(fileExt)) {
        showError('This file type is not supported');
        return;
    }
    
    // Check if we have the required data
    if (!token || !teamId) {
        showError('Cannot upload file - session invalid');
        return;
    }
    
    // Show upload progress
    const uploadStatus = showUploadProgress(file.name);
    
    try {
        // Create FormData for file upload
        const formData = new FormData();
        formData.append('file', file);
        
        // Upload file to server
        const response = await fetch(`/api/teams/${teamId}/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(errorData.detail || 'Upload failed');
        }
        
        const uploadResult = await response.json();
        
        // Update upload status to success
        updateUploadProgress(uploadStatus, 'success', `${file.name} uploaded successfully`);
        
        // Send file message through WebSocket to notify other team members
        if (ws && ws.readyState === WebSocket.OPEN) {
            try {
                ws.send(JSON.stringify({
                    type: 'message',
                    message: `[FILE] ${file.name} (${formatFileSize(file.size)})`,
                    message_type: 'file',
                    file_name: file.name,
                    file_size: file.size,
                    file_id: uploadResult.file_id,
                    file_path: uploadResult.file_path
                }));
            } catch (wsError) {
                console.error('Error notifying team members:', wsError);
                // File is uploaded, so this is not a critical error
            }
        }
        
    } catch (error) {
        console.error('Error uploading file:', error);
        updateUploadProgress(uploadStatus, 'error', error.message || 'Failed to upload file');
    }
    
    // Clear file input
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.value = '';
    }
}

function showUploadProgress(fileName) {
    // Create upload progress element
    const progressDiv = document.createElement('div');
    progressDiv.className = 'upload-progress';
    progressDiv.innerHTML = `
        <div class="upload-content">
            <div class="upload-icon">📤</div>
            <div class="upload-info">
                <div class="upload-filename">${escapeHtml(fileName)}</div>
                <div class="upload-status">Uploading...</div>
            </div>
            <div class="upload-spinner"></div>
        </div>
    `;
    
    // Style the progress element
    progressDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        min-width: 280px;
        max-width: 400px;
    `;
    
    const uploadContent = progressDiv.querySelector('.upload-content');
    uploadContent.style.cssText = `
        display: flex;
        align-items: center;
        gap: 12px;
    `;
    
    const uploadIcon = progressDiv.querySelector('.upload-icon');
    uploadIcon.style.cssText = `
        font-size: 20px;
        flex-shrink: 0;
    `;
    
    const uploadInfo = progressDiv.querySelector('.upload-info');
    uploadInfo.style.cssText = `
        flex-grow: 1;
        min-width: 0;
    `;
    
    const uploadFilename = progressDiv.querySelector('.upload-filename');
    uploadFilename.style.cssText = `
        font-weight: 500;
        color: #333;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 4px;
    `;
    
    const uploadStatus = progressDiv.querySelector('.upload-status');
    uploadStatus.style.cssText = `
        font-size: 12px;
        color: #666;
    `;
    
    const uploadSpinner = progressDiv.querySelector('.upload-spinner');
    uploadSpinner.style.cssText = `
        width: 16px;
        height: 16px;
        border: 2px solid #e9ecef;
        border-top: 2px solid #007bff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        flex-shrink: 0;
    `;
    
    // Add spinner animation
    if (!document.getElementById('spinner-animation')) {
        const style = document.createElement('style');
        style.id = 'spinner-animation';
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
    
    document.body.appendChild(progressDiv);
    return progressDiv;
}

function updateUploadProgress(progressElement, status, message) {
    if (!progressElement) return;
    
    const uploadIcon = progressElement.querySelector('.upload-icon');
    const uploadStatus = progressElement.querySelector('.upload-status');
    const uploadSpinner = progressElement.querySelector('.upload-spinner');
    
    if (status === 'success') {
        uploadIcon.textContent = '✅';
        uploadStatus.textContent = message;
        uploadStatus.style.color = '#28a745';
        if (uploadSpinner) uploadSpinner.style.display = 'none';
        
        // Change border color to success
        progressElement.style.borderColor = '#28a745';
        
        // Remove after 3 seconds
        setTimeout(() => {
            if (progressElement.parentNode) {
                progressElement.remove();
            }
        }, 3000);
        
    } else if (status === 'error') {
        uploadIcon.textContent = '❌';
        uploadStatus.textContent = message;
        uploadStatus.style.color = '#dc3545';
        if (uploadSpinner) uploadSpinner.style.display = 'none';
        
        // Change border color to error
        progressElement.style.borderColor = '#dc3545';
        
        // Remove after 5 seconds
        setTimeout(() => {
            if (progressElement.parentNode) {
                progressElement.remove();
            }
        }, 5000);
    }
}

function displayMessage(data) {
    const messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    // Handle system messages differently
    if (data.type === 'system') {
        displaySystemMessage(data.message);
        return;
    }
    
    // Skip messages from unknown users (but allow system messages)
    if (!data.user || !data.user.name || (data.user.name === 'Unknown' && data.user.public_id !== 'SYS')) {
        console.warn('Skipping message from unknown user:', data);
        return;
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    // Add special class for own messages
    if (data.user && currentUser && data.user.user_id === currentUser.user_id) {
        messageDiv.classList.add('own-message');
    }
    
    const time = formatTime(data.timestamp);
    const userName = data.user ? data.user.name : 'Unknown';
    const publicId = data.user ? data.user.public_id : '';
    
    // Handle the message content - it should be plain text now
    let messageContent = data.message || '';
    
    messageDiv.innerHTML = `
        <div class="message-header">
            ${escapeHtml(userName)} ${publicId ? `(${escapeHtml(publicId)})` : ''}
            <span class="message-time">${time}</span>
        </div>
        <div class="message-content">${escapeHtml(messageContent)}</div>
    `;
    
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
}

function displayFileMessage(data) {
    const messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    if (data.user && currentUser && data.user.user_id === currentUser.user_id) {
        messageDiv.classList.add('own-message');
    }
    
    const time = formatTime(data.timestamp);
    const userName = data.user ? data.user.name : 'Unknown';
    const publicId = data.user ? data.user.public_id : '';
    
    // Skip messages from unknown users
    if (!data.user || !data.user.name || data.user.name === 'Unknown') {
        console.warn('Skipping file message from unknown user:', data);
        return;
    }
    
    // Determine if this is a downloadable file (has file_id or file_path)
    const isDownloadable = data.file_id || data.file_path;
    const fileName = data.file_name || 'Unknown file';
    const fileSize = data.file_size || 0;
    
    // Check if this is an image file
    const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'];
    const fileExt = fileName.split('.').pop().toLowerCase();
    const isImage = imageExtensions.includes(fileExt);
    
    let imagePreviewHtml = '';
    if (isImage && isDownloadable) {
        const fileId = data.file_id || data.file_path.split('/').pop();
        imagePreviewHtml = `
            <div class="image-preview" data-file-id="${fileId}" data-file-name="${escapeHtml(fileName)}">
                <div class="image-placeholder">Loading image...</div>
            </div>
        `;
    }
    
    messageDiv.innerHTML = `
        <div class="message-header">
            ${escapeHtml(userName)} ${publicId ? `(${escapeHtml(publicId)})` : ''}
            <span class="message-time">${time}</span>
        </div>
        <div class="file-message ${isDownloadable ? 'downloadable' : ''}">
            <div class="file-icon">${getFileIcon(fileName)}</div>
            <div class="file-info">
                <div class="file-name">${escapeHtml(fileName)}</div>
                <div class="file-size">${formatFileSize(fileSize)}</div>
                ${isDownloadable ? `<div class="file-actions">
                    <button class="download-btn" onclick="downloadFile('${data.file_id || data.file_path}', '${escapeHtml(fileName)}')">
                        📥 Download
                    </button>
                </div>` : ''}
            </div>
        </div>
        ${imagePreviewHtml}
    `;
    
    // Add styles for file message
    const fileMessage = messageDiv.querySelector('.file-message');
    if (fileMessage) {
        fileMessage.style.cssText = `
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-top: 8px;
            ${isDownloadable ? 'cursor: pointer; transition: background-color 0.2s;' : ''}
        `;
        
        if (isDownloadable) {
            fileMessage.addEventListener('mouseenter', () => {
                fileMessage.style.backgroundColor = '#e9ecef';
            });
            fileMessage.addEventListener('mouseleave', () => {
                fileMessage.style.backgroundColor = '#f8f9fa';
            });
        }
    }
    
    const fileIcon = messageDiv.querySelector('.file-icon');
    if (fileIcon) {
        fileIcon.style.cssText = `
            font-size: 24px;
            flex-shrink: 0;
        `;
    }
    
    const fileInfo = messageDiv.querySelector('.file-info');
    if (fileInfo) {
        fileInfo.style.cssText = `
            flex-grow: 1;
            min-width: 0;
        `;
    }
    
    const fileNameEl = messageDiv.querySelector('.file-name');
    if (fileNameEl) {
        fileNameEl.style.cssText = `
            font-weight: 500;
            color: #333;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 4px;
        `;
    }
    
    const fileSizeEl = messageDiv.querySelector('.file-size');
    if (fileSizeEl) {
        fileSizeEl.style.cssText = `
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
        `;
    }
    
    const downloadBtn = messageDiv.querySelector('.download-btn');
    if (downloadBtn) {
        downloadBtn.style.cssText = `
            background: #007bff;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            transition: background-color 0.2s;
        `;
        
        downloadBtn.addEventListener('mouseenter', () => {
            downloadBtn.style.backgroundColor = '#0056b3';
        });
        downloadBtn.addEventListener('mouseleave', () => {
            downloadBtn.style.backgroundColor = '#007bff';
        });
    }
    
    // Style preview button
    const previewBtn = messageDiv.querySelector('.preview-btn');
    if (previewBtn) {
        previewBtn.style.cssText = `
            background: #28a745;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-left: 8px;
        `;
        
        previewBtn.addEventListener('mouseenter', () => {
            previewBtn.style.backgroundColor = '#218838';
        });
        previewBtn.addEventListener('mouseleave', () => {
            previewBtn.style.backgroundColor = '#28a745';
        });
    }
    
    
    messagesDiv.appendChild(messageDiv);
    
    // Load image preview with authentication if it's an image
    const imagePreview = messageDiv.querySelector('.image-preview[data-file-id]');
    if (imagePreview) {
        loadImagePreview(imagePreview);
    }
    
    scrollToBottom();
}

async function loadImagePreview(imagePreviewElement) {
    const fileId = imagePreviewElement.dataset.fileId;
    const fileName = imagePreviewElement.dataset.fileName;
    
    if (!fileId || !token) return;
    
    try {
        // Get secure token for preview
        const tokenResponse = await fetch(`/api/files/${fileId}/token?access_type=preview`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!tokenResponse.ok) {
            throw new Error('Failed to get preview token');
        }
        
        const tokenData = await tokenResponse.json();
        
        // Use secure token to load preview
        const response = await fetch(`/api/files/${fileId}/preview?token=${tokenData.token}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load image preview');
        }
        
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        
        // Create and configure image element
        const img = document.createElement('img');
        img.src = blobUrl;
        img.alt = fileName;
        img.onclick = () => showFullImage(fileId, fileName);
        img.style.cssText = `
            width: 100%;
            height: auto;
            max-height: 200px;
            object-fit: cover;
            transition: transform 0.2s;
            cursor: pointer;
        `;
        
        img.addEventListener('mouseenter', () => {
            img.style.transform = 'scale(1.02)';
        });
        img.addEventListener('mouseleave', () => {
            img.style.transform = 'scale(1)';
        });
        
        // Replace placeholder with image
        imagePreviewElement.innerHTML = '';
        imagePreviewElement.appendChild(img);
        
        // Clean up blob URL after a delay
        setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
        
    } catch (error) {
        console.error('Error loading image preview:', error);
        imagePreviewElement.innerHTML = '<div class="image-error">Failed to load image</div>';
    }
}

function getFileIcon(fileName) {
    if (!fileName) return '📄';
    
    const ext = fileName.split('.').pop().toLowerCase();
    const iconMap = {
        // Images
        'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️', 'bmp': '🖼️', 'webp': '🖼️',
        // Documents
        'pdf': '📕', 'doc': '📄', 'docx': '📄', 'txt': '📝',
        // Audio
        'mp3': '🎵', 'wav': '🎵', 'flac': '🎵', 'aac': '🎵',
        // Video
        'mp4': '🎬', 'avi': '🎬', 'mov': '🎬', 'wmv': '🎬', 'mkv': '🎬',
        // Archives
        'zip': '📦', 'rar': '📦', '7z': '📦', 'tar': '📦',
        // Default
        'default': '📄'
    };
    
    return iconMap[ext] || iconMap.default;
}

async function downloadFile(fileIdentifier, fileName) {
    if (!token) {
        showError('Cannot download file - not authenticated');
        return;
    }
    
    try {
        // Extract file ID from file_path if needed
        let fileId = fileIdentifier;
        if (fileIdentifier.startsWith('/api/files/')) {
            fileId = fileIdentifier.split('/').pop();
        }
        
        // Get secure token for download
        const tokenResponse = await fetch(`/api/files/${fileId}/token?access_type=download`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!tokenResponse.ok) {
            throw new Error('Failed to get download token');
        }
        
        const tokenData = await tokenResponse.json();
        
        // Create download link with secure token
        const downloadUrl = `/api/files/${fileId}?token=${tokenData.token}`;
        
        // Create temporary link element and trigger download
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = fileName || 'download';
        
        // Add authorization header by fetching and creating blob URL
        const response = await fetch(downloadUrl, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to download file');
        }
        
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        
        link.href = blobUrl;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // Clean up blob URL
        setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
        
    } catch (error) {
        console.error('Error downloading file:', error);
        showError(`Failed to download ${fileName}: ${error.message}`);
    }
}

async function showFullImage(fileId, fileName) {
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        z-index: 10000;
        display: flex;
        justify-content: center;
        align-items: center;
        cursor: pointer;
    `;
    
    // Create image container
    const imageContainer = document.createElement('div');
    imageContainer.style.cssText = `
        max-width: 90%;
        max-height: 90%;
        position: relative;
    `;
    
    // Create the image with proper authentication
    const img = document.createElement('img');
    
    // Load image with secure token
    const loadImageWithAuth = async () => {
        try {
            // Get secure token for preview
            const tokenResponse = await fetch(`/api/files/${fileId}/token?access_type=preview`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (!tokenResponse.ok) {
                throw new Error('Failed to get preview token');
            }
            
            const tokenData = await tokenResponse.json();
            
            // Use secure token to load preview
            const response = await fetch(`/api/files/${fileId}/preview?token=${tokenData.token}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to load image');
            }
            
            const blob = await response.blob();
            const blobUrl = URL.createObjectURL(blob);
            img.src = blobUrl;
            
            // Clean up blob URL when image is removed
            img.addEventListener('load', () => {
                setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
            });
        } catch (error) {
            console.error('Error loading image:', error);
            img.onerror();
        }
    };
    
    img.alt = fileName;
    loadImageWithAuth();
    img.style.cssText = `
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    `;
    
    // Create close button
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '✕';
    closeBtn.style.cssText = `
        position: absolute;
        top: -10px;
        right: -10px;
        background: #fff;
        border: none;
        border-radius: 50%;
        width: 30px;
        height: 30px;
        font-size: 16px;
        cursor: pointer;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        z-index: 10001;
    `;
    
    // Create download button
    const downloadBtn = document.createElement('button');
    downloadBtn.innerHTML = '📥 Download';
    downloadBtn.style.cssText = `
        position: absolute;
        bottom: -40px;
        left: 50%;
        transform: translateX(-50%);
        background: #007bff;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
    `;
    
    // Add event listeners with proper error handling
    closeBtn.onclick = (e) => {
        e.stopPropagation();
        closeImageViewer(overlay);
    };
    
    downloadBtn.onclick = (e) => {
        e.stopPropagation();
        downloadFile(fileId, fileName);
    };
    
    overlay.onclick = () => {
        closeImageViewer(overlay);
    };
    
    img.onclick = (e) => {
        e.stopPropagation();
    };
    
    // Handle image load error
    img.onerror = () => {
        imageContainer.innerHTML = `
            <div style="color: white; text-align: center; padding: 20px;">
                <p>Failed to load image</p>
                <button onclick="closeImageViewer(document.querySelector('[style*=\\'z-index: 10000\\']'))" 
                        style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                    Close
                </button>
            </div>
        `;
    };
    
    // Assemble the modal
    imageContainer.appendChild(img);
    imageContainer.appendChild(closeBtn);
    imageContainer.appendChild(downloadBtn);
    overlay.appendChild(imageContainer);
    document.body.appendChild(overlay);
}

function closeImageViewer(overlay) {
    if (overlay && overlay.parentNode && overlay.parentNode.contains(overlay)) {
        try {
            overlay.parentNode.removeChild(overlay);
        } catch (error) {
            console.error('Error closing image viewer:', error);
        }
    } else if (overlay && document.body.contains(overlay)) {
        try {
            document.body.removeChild(overlay);
        } catch (error) {
            console.error('Error removing overlay from body:', error);
        }
    }
}

function displaySystemMessage(message) {
    const messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system-message';
    
    messageDiv.innerHTML = `
        <div class="message-content">${escapeHtml(message)}</div>
    `;
    
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
}

function updateConnectionStatus(status) {
    connectionStatus = status;
    
    // Remove existing status indicator
    const existingIndicator = document.querySelector('.connection-status');
    if (existingIndicator) {
        existingIndicator.remove();
    }
    
    // Add new status indicator
    const statusDiv = document.createElement('div');
    statusDiv.className = `connection-status ${status}`;
    
    switch (status) {
        case 'connected':
            statusDiv.textContent = '● Connected';
            break;
        case 'connecting':
            statusDiv.textContent = '● Connecting...';
            break;
        case 'disconnected':
            statusDiv.textContent = '● Disconnected';
            break;
    }
    
    document.body.appendChild(statusDiv);
    
    // Auto-remove after 3 seconds if connected
    if (status === 'connected') {
        setTimeout(() => {
            if (statusDiv.parentNode) {
                statusDiv.remove();
            }
        }, 3000);
    }
}

function scrollToBottom() {
    const messagesDiv = document.getElementById('messages');
    if (messagesDiv) {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

function formatTime(timestamp) {
    if (!timestamp) return '';
    
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false 
        });
    } catch (error) {
        return '';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    if (typeof text !== 'string') return '';
    
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    
    return text.replace(/[&<>"']/g, function(m) { 
        return map[m]; 
    });
}

function showError(message) {
    // Create a temporary error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-toast';
    errorDiv.textContent = message;
    errorDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #f8d7da;
        color: #721c24;
        padding: 12px 20px;
        border: 1px solid #f5c6cb;
        border-radius: 4px;
        z-index: 10000;
        font-weight: 500;
        max-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    
    document.body.appendChild(errorDiv);
    
    // Remove after 5 seconds
    setTimeout(() => {
        if (errorDiv.parentNode) {
            errorDiv.remove();
        }
    }, 5000);
}

function showSuccess(message) {
    // Create a temporary success message
    const successDiv = document.createElement('div');
    successDiv.className = 'success-toast';
    successDiv.textContent = message;
    successDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #d4edda;
        color: #155724;
        padding: 12px 20px;
        border: 1px solid #c3e6cb;
        border-radius: 4px;
        z-index: 10000;
        font-weight: 500;
        max-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    
    document.body.appendChild(successDiv);
    
    // Remove after 3 seconds
    setTimeout(() => {
        if (successDiv.parentNode) {
            successDiv.remove();
        }
    }, 3000);
}

// =============================================================================
// TEAM MEMBERS PANEL
// =============================================================================

let membersPanelVisible = false;

function toggleMembersPanel() {
    const panel = document.getElementById('members-panel');
    if (!panel) return;
    
    membersPanelVisible = !membersPanelVisible;
    
    if (membersPanelVisible) {
        panel.classList.remove('hidden');
        loadTeamMembers();
    } else {
        panel.classList.add('hidden');
    }
}

async function loadTeamMembers() {
    const membersList = document.getElementById('members-list');
    const adminActions = document.getElementById('admin-actions');
    
    if (!membersList) return;
    
    try {
        membersList.innerHTML = '<div class="loading">Loading members...</div>';
        
        const response = await fetch(`/api/teams/${teamId}/members`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const members = await response.json();
            displayTeamMembers(members);
            
            // Check if current user is admin
            isAdmin = members.some(m => m.is_admin && m.user_id === currentUser.user_id);
            
            if (isAdmin && adminActions) {
                adminActions.classList.remove('hidden');
                // Also load pending requests for admins
                loadPendingRequests();
            }
        } else if (response.status === 403) {
            membersList.innerHTML = '<div class="loading">Only team admins can view members</div>';
        } else {
            membersList.innerHTML = '<div class="loading">Failed to load members</div>';
        }
    } catch (error) {
        console.error('Error loading team members:', error);
        membersList.innerHTML = '<div class="loading">Error loading members</div>';
    }
}

function displayTeamMembers(members) {
    const membersList = document.getElementById('members-list');
    if (!membersList) return;
    
    if (members.length === 0) {
        membersList.innerHTML = '<div class="loading">No members found</div>';
        return;
    }
    
    membersList.innerHTML = members.map(member => `
        <div class="member-item">
            <div class="member-info">
                <div class="member-status ${member.is_online ? 'online' : ''} ${member.status === 'banned' ? 'banned' : ''}"></div>
                <div class="member-name">${escapeHtml(member.name)}</div>
                ${member.is_admin ? '<span class="member-badge admin">Admin</span>' : ''}
                ${member.status === 'banned' ? '<span class="member-badge banned">Banned</span>' : ''}
            </div>
            ${isAdmin && !member.is_admin ? `
                <div class="member-actions">
                    ${member.status !== 'banned' ? `
                        <button class="member-action-btn kick" onclick="kickMember('${member.user_id}', '${escapeHtml(member.name)}')">Kick</button>
                        <button class="member-action-btn ban" onclick="banMember('${member.user_id}', '${escapeHtml(member.name)}')">Ban</button>
                    ` : `
                        <button class="member-action-btn unban" onclick="unbanMember('${member.user_id}', '${escapeHtml(member.name)}')">Unban</button>
                    `}
                </div>
            ` : ''}
        </div>
    `).join('');
}

async function loadPendingRequests() {
    if (!isAdmin || !token) return;
    
    const pendingSection = document.getElementById('pending-requests-section');
    const pendingList = document.getElementById('pending-list');
    
    if (!pendingSection || !pendingList) return;
    
    try {
        const response = await fetch(`/api/teams/${teamId}/pending`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const requests = await response.json();
            
            if (requests.length > 0) {
                pendingSection.classList.remove('hidden');
                displayPendingRequests(requests);
            } else {
                pendingSection.classList.add('hidden');
            }
        } else {
            pendingSection.classList.add('hidden');
        }
    } catch (error) {
        console.error('Error loading pending requests:', error);
        pendingSection.classList.add('hidden');
    }
}

function displayPendingRequests(requests) {
    const pendingList = document.getElementById('pending-list');
    if (!pendingList) return;
    
    if (requests.length === 0) {
        pendingList.innerHTML = '<div class="loading">No pending requests</div>';
        return;
    }
    
    pendingList.innerHTML = requests.map(request => `
        <div class="pending-item">
            <div class="pending-info">
                <div class="pending-name">${escapeHtml(request.name)} (${escapeHtml(request.public_id)})</div>
                <div class="pending-time">Requested ${formatTimeAgo(request.requested_at)}</div>
            </div>
            <div class="pending-actions">
                <button class="pending-action-btn approve" onclick="approveMember('${request.user_id}', '${escapeHtml(request.name)}')">✓ Approve</button>
                <button class="pending-action-btn reject" onclick="rejectMember('${request.user_id}', '${escapeHtml(request.name)}')">✗ Reject</button>
            </div>
        </div>
    `).join('');
}

function formatTimeAgo(timestamp) {
    try {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        return date.toLocaleDateString();
    } catch (error) {
        return 'recently';
    }
}

async function approveMember(userId, userName) {
    if (!confirm(`Approve ${userName} to join the team?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: 'approve'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadPendingRequests(); // Refresh pending list
            loadTeamMembers(); // Refresh member list
        } else {
            showError(data.detail || 'Failed to approve member');
        }
    } catch (error) {
        console.error('Error approving member:', error);
        showError('Network error. Please try again.');
    }
}

async function rejectMember(userId, userName) {
    if (!confirm(`Reject ${userName}'s request to join the team?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: 'reject'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadPendingRequests(); // Refresh pending list
        } else {
            showError(data.detail || 'Failed to reject member');
        }
    } catch (error) {
        console.error('Error rejecting member:', error);
        showError('Network error. Please try again.');
    }
}

async function kickMember(userId, userName) {
    if (!confirm(`Are you sure you want to kick ${userName} from the team?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: 'kick'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadTeamMembers(); // Refresh the list
        } else {
            showError(data.detail || 'Failed to kick member');
        }
    } catch (error) {
        console.error('Error kicking member:', error);
        showError('Network error. Please try again.');
    }
}

async function banMember(userId, userName) {
    if (!confirm(`Are you sure you want to ban ${userName} from the team? They will not be able to rejoin.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: 'ban'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadTeamMembers(); // Refresh the list
        } else {
            showError(data.detail || 'Failed to ban member');
        }
    } catch (error) {
        console.error('Error banning member:', error);
        showError('Network error. Please try again.');
    }
}

async function unbanMember(userId, userName) {
    if (!confirm(`Are you sure you want to unban ${userName}? They will be able to request to join the team again.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: 'unban'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            loadTeamMembers(); // Refresh the list
        } else {
            showError(data.detail || 'Failed to unban member');
        }
    } catch (error) {
        console.error('Error unbanning member:', error);
        showError('Network error. Please try again.');
    }
}

async function clearTeamChat() {
    if (!confirm('Are you sure you want to clear the entire team chat? This action cannot be undone and will delete all messages and files.')) {
        return;
    }
    
    if (!confirm('This will permanently delete ALL chat history and uploaded files. Are you absolutely sure?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/messages`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            // Clear local messages display
            const messagesDiv = document.getElementById('messages');
            if (messagesDiv) {
                messagesDiv.innerHTML = '';
            }
        } else {
            showError(data.detail || 'Failed to clear chat');
        }
    } catch (error) {
        console.error('Error clearing chat:', error);
        showError('Network error. Please try again.');
    }
}

// Handle WebSocket events for member updates
function handleMemberUpdate(data) {
    if (membersPanelVisible) {
        loadTeamMembers(); // Refresh member list
    }
}

function handleOnlineUsersUpdate(onlineUsers) {
    if (membersPanelVisible) {
        // Update online status indicators
        const memberItems = document.querySelectorAll('.member-item');
        memberItems.forEach(item => {
            const memberName = item.querySelector('.member-name').textContent;
            const statusIndicator = item.querySelector('.member-status');
            
            // This is a simplified approach - ideally we'd match by user ID
            // In a real implementation, we'd store user IDs in data attributes
            const isOnline = onlineUsers.some(userId => 
                document.querySelector(`[data-user-id="${userId}"]`)
            );
            
            if (statusIndicator) {
                statusIndicator.classList.toggle('online', isOnline);
            }
        });
    }
}

function handleChatCleared(data) {
    // Clear messages display first
    const messagesDiv = document.getElementById('messages');
    if (messagesDiv) {
        messagesDiv.innerHTML = '';
    }
    
    // Then show the system message
    displaySystemMessage(`Chat history cleared by ${data.admin_name}`);
}

function handleMemberAction(data) {
    displaySystemMessage(data.message);
    
    if (membersPanelVisible) {
        loadTeamMembers(); // Refresh member list
    }
}

function handleTeamRequestApproved(data) {
    showNotification('✅ Team Request Approved', data.message, 'success');
    
    // Refresh the page to show the team chat
    setTimeout(() => {
        window.location.reload();
    }, 2000);
}

function handleTeamRequestRejected(data) {
    showNotification('❌ Team Request Rejected', data.message, 'error');
    
    // Close the window/tab after showing the message
    setTimeout(() => {
        window.close();
    }, 3000);
}

function handleTeamUnbanned(data) {
    showNotification('🔓 Unbanned from Team', data.message, 'info');
}

function handleForceDisconnect(data) {
    // Show disconnect message
    showNotification('⚠️ Disconnected', data.message, 'warning');
    
    // Disable chat interface
    const chatInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const fileButton = document.getElementById('file-button');
    
    if (chatInput) {
        chatInput.disabled = true;
        chatInput.placeholder = 'You have been disconnected from this team';
    }
    if (sendButton) sendButton.disabled = true;
    if (fileButton) fileButton.disabled = true;
    
    // Close WebSocket if still open
    if (ws) {
        ws.close();
        ws = null;
    }
    
    // Prevent reconnection
    connectionStatus = 'force_disconnected';
    
    // Close the window after a delay
    setTimeout(() => {
        window.close();
    }, 5000);
}

function handleNewJoinRequest(data) {
    // Show notification to admin
    if (isAdmin) {
        showNotification('🙋 New Join Request', data.message, 'info');
        
        // Auto-refresh pending requests if panel is open
        if (membersPanelVisible) {
            loadPendingRequests();
        }
        
        // Update pending requests badge/indicator
        updatePendingRequestsBadge();
    }
}

function handlePendingRequestUpdate(data) {
    // Show system message
    displaySystemMessage(data.message);
    
    // Refresh pending requests if admin and panel is open  
    if (isAdmin && membersPanelVisible) {
        loadPendingRequests();
    }
    
    // Update badge
    updatePendingRequestsBadge();
}

function updatePendingRequestsBadge() {
    // Update any badge indicators for pending requests
    if (isAdmin) {
        // You can add a badge/counter here if you have one in the UI
        // For now, just ensure the requests panel shows current data
        setTimeout(() => {
            if (membersPanelVisible) {
                loadPendingRequests();
            }
        }, 500); // Small delay to ensure database is updated
    }
}

function showNotification(title, message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-header">
            <strong>${title}</strong>
            <button class="close-btn" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
        <div class="notification-message">${message}</div>
    `;
    
    // Add styles if not already added
    if (!document.getElementById('notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            .notification {
                position: fixed;
                top: 20px;
                right: 20px;
                max-width: 400px;
                padding: 15px;
                border-radius: 5px;
                background: #333;
                color: white;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                z-index: 10000;
                animation: slideIn 0.3s ease-out;
            }
            .notification-success { border-left: 4px solid #4CAF50; }
            .notification-error { border-left: 4px solid #f44336; }
            .notification-warning { border-left: 4px solid #ff9800; }
            .notification-info { border-left: 4px solid #2196F3; }
            .notification-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }
            .close-btn {
                background: none;
                border: none;
                color: white;
                font-size: 18px;
                cursor: pointer;
                padding: 0;
                width: 20px;
                height: 20px;
            }
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Export functions for global access
window.sendMessage = sendMessage;
window.handleFileSelection = handleFileSelection;
window.downloadFile = downloadFile;
window.toggleMembersPanel = toggleMembersPanel;
window.kickMember = kickMember;
window.banMember = banMember;
window.unbanMember = unbanMember;
window.approveMember = approveMember;
window.rejectMember = rejectMember;
window.clearTeamChat = clearTeamChat;