// meeting.js - Enhanced Meeting JavaScript with WebRTC - FIXED VERSION

// Global variables
let meetingId = null;
let token = null;
let currentUser = null;
let ws = null;
let localStream = null;
let isMicOn = false; // Start with mic OFF for privacy
let isCameraOn = false; // Start with camera OFF for privacy
let isScreenSharing = false;
let connectionStatus = 'disconnected';
let participantCount = 0;
let isMeetingCreator = false;
let pendingPanelCollapsed = false;
let joinStatus = 'unknown';
let joinCheckInterval = null;
let gdprAccepted = false;
let eventListenersSetup = false; // Prevent duplicate event listeners

// WebRTC variables
let peerConnections = new Map(); // userId -> RTCPeerConnection
let remoteStreams = new Map(); // userId -> MediaStream
let localVideoElement = null;
let currentVideoQuality = 'medium';
let currentBandwidthLimit = 'medium';

// Video quality settings
const videoConstraints = {
    low: { width: 640, height: 360, frameRate: 15 },
    medium: { width: 1280, height: 720, frameRate: 24 },
    high: { width: 1920, height: 1080, frameRate: 30 }
};

// Bandwidth limits (in kbps)
const bandwidthLimits = {
    low: 500,
    medium: 1000,
    high: 2000,
    unlimited: null
};

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initializeMeeting();
});

async function initializeMeeting() {
    // Get meeting ID from URL or element
    const meetingIdElement = document.getElementById('meeting-id');
    if (meetingIdElement) {
        meetingId = meetingIdElement.textContent;
    } else {
        const pathParts = window.location.pathname.split('/');
        meetingId = pathParts[pathParts.length - 1];
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
    
    // Update meeting ID display
    if (meetingIdElement) {
        meetingIdElement.textContent = meetingId;
    }
    
    // Check GDPR consent
    if (!checkGDPRConsent()) {
        showGDPRModal();
        return;
    }
    
    // Check join status first
    await checkJoinStatus();
}

function checkGDPRConsent() {
    gdprAccepted = localStorage.getItem('gdprAccepted') === 'true';
    return gdprAccepted;
}

function showGDPRModal() {
    const modal = document.getElementById('gdpr-modal');
    if (modal) {
        modal.classList.remove('hidden');
    }
}

function acceptGDPR() {
    localStorage.setItem('gdprAccepted', 'true');
    localStorage.setItem('gdprAcceptedDate', new Date().toISOString());
    gdprAccepted = true;
    
    const modal = document.getElementById('gdpr-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
    
    // Continue with meeting initialization
    checkJoinStatus();
}

function rejectGDPR() {
    showError('Privacy consent is required to use this meeting application');
    setTimeout(() => window.close(), 3000);
}

async function checkJoinStatus() {
    if (!token || !meetingId) return;
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}/status`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        
        if (response.ok) {
            const data = await response.json();
            joinStatus = data.status;
            isMeetingCreator = data.is_creator;
            
            if (joinStatus === 'approved' || isMeetingCreator) {
                await proceedToMeeting();
            } else if (joinStatus === 'pending') {
                showPendingUI();
                startJoinStatusPolling();
            } else if (joinStatus === 'rejected') {
                showRejectedUI();
            } else if (joinStatus === 'not_member') {
                showError('You need to request to join this meeting first');
                setTimeout(() => window.close(), 3000);
            } else {
                showError('You are not authorized to join this meeting');
                setTimeout(() => window.close(), 2000);
            }
        } else {
            showError('Meeting not found or access denied');
            setTimeout(() => window.close(), 2000);
        }
    } catch (error) {
        console.error('Error checking join status:', error);
        showError('Connection error. Please try again.');
        setTimeout(() => window.close(), 2000);
    }
}

function showPendingUI() {
    // Hide normal meeting UI
    const videoMeetingArea = document.querySelector('.video-meeting-area');
    const controls = document.querySelector('.controls');
    
    if (videoMeetingArea) videoMeetingArea.style.display = 'none';
    if (controls) controls.style.display = 'none';
    
    // Create or show pending UI
    let pendingDiv = document.getElementById('pending-status');
    if (!pendingDiv) {
        pendingDiv = document.createElement('div');
        pendingDiv.id = 'pending-status';
        pendingDiv.className = 'pending-status';
        pendingDiv.innerHTML = `
            <div class="pending-content">
                <div class="pending-icon">⏳</div>
                <h2>Waiting for Approval</h2>
                <p>Your request to join this meeting is pending approval from the host.</p>
                <p class="meeting-id">Meeting ID: ${meetingId}</p>
                <div class="pending-animation">
                    <div class="dot"></div>
                    <div class="dot"></div>
                    <div class="dot"></div>
                </div>
                <button onclick="window.close()" class="close-btn-pending">Close Window</button>
            </div>
        `;
        
        // Add styles
        pendingDiv.style.cssText = `
            position: fixed;
            top: 80px;
            left: 0;
            width: 100%;
            height: calc(100% - 80px);
            background: rgba(0, 0, 0, 0.9);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        `;
        
        const pendingContent = pendingDiv.querySelector('.pending-content');
        pendingContent.style.cssText = `
            text-align: center;
            color: white;
            padding: 40px;
            border-radius: 12px;
            background: #333;
            border: 2px solid #ff69b4;
            max-width: 400px;
            width: 90%;
        `;
        
        const pendingIcon = pendingDiv.querySelector('.pending-icon');
        pendingIcon.style.cssText = `
            font-size: 60px;
            margin-bottom: 20px;
            display: block;
            animation: pulse 2s infinite;
        `;
        
        const h2 = pendingDiv.querySelector('h2');
        h2.style.cssText = `
            color: #ff69b4;
            margin-bottom: 15px;
            font-size: 2em;
        `;
        
        const meetingIdEl = pendingDiv.querySelector('.meeting-id');
        meetingIdEl.style.cssText = `
            font-family: monospace;
            background: rgba(255, 255, 255, 0.1);
            padding: 8px;
            border-radius: 4px;
            font-size: 14px;
            margin: 10px 0;
        `;
        
        const pendingAnimation = pendingDiv.querySelector('.pending-animation');
        pendingAnimation.style.cssText = `
            display: flex;
            justify-content: center;
            gap: 5px;
            margin: 20px 0;
        `;
        
        const dots = pendingDiv.querySelectorAll('.dot');
        dots.forEach((dot, index) => {
            dot.style.cssText = `
                width: 8px;
                height: 8px;
                background: #ff69b4;
                border-radius: 50%;
                animation: bounce 1.4s infinite ease-in-out;
                animation-delay: ${index * 0.16}s;
            `;
        });
        
        const closeBtn = pendingDiv.querySelector('.close-btn-pending');
        closeBtn.style.cssText = `
            background: #dc3545;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 20px;
        `;
        
        document.body.appendChild(pendingDiv);
        
        // Add CSS animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }
            @keyframes bounce {
                0%, 80%, 100% { transform: scale(0); }
                40% { transform: scale(1); }
            }
        `;
        document.head.appendChild(style);
    }
}

function hidePendingUI() {
    const pendingDiv = document.getElementById('pending-status');
    if (pendingDiv) {
        pendingDiv.remove();
    }
    
    // Show normal meeting UI
    const videoMeetingArea = document.querySelector('.video-meeting-area');
    const controls = document.querySelector('.controls');
    
    if (videoMeetingArea) videoMeetingArea.style.display = 'flex';
    if (controls) controls.style.display = 'flex';
}

function showRejectedUI() {
    // Hide normal meeting UI
    const videoMeetingArea = document.querySelector('.video-meeting-area');
    const controls = document.querySelector('.controls');
    
    if (videoMeetingArea) videoMeetingArea.style.display = 'none';
    if (controls) controls.style.display = 'none';
    
    // Create rejected UI
    const rejectedDiv = document.createElement('div');
    rejectedDiv.id = 'rejected-status';
    rejectedDiv.className = 'rejected-status';
    rejectedDiv.innerHTML = `
        <div class="rejected-content">
            <div class="rejected-icon">❌</div>
            <h2>Access Denied</h2>
            <p>Your request to join this meeting has been rejected by the host.</p>
            <p class="meeting-id">Meeting ID: ${meetingId}</p>
            <p class="auto-close">This window will close automatically in 5 seconds...</p>
        </div>
    `;
    
    // Add styles similar to pending UI but with rejected theme
    rejectedDiv.style.cssText = `
        position: fixed;
        top: 80px;
        left: 0;
        width: 100%;
        height: calc(100% - 80px);
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;
    
    const rejectedContent = rejectedDiv.querySelector('.rejected-content');
    rejectedContent.style.cssText = `
        text-align: center;
        color: white;
        padding: 40px;
        border-radius: 12px;
        background: #333;
        border: 2px solid #dc3545;
        max-width: 400px;
        width: 90%;
    `;
    
    const h2 = rejectedDiv.querySelector('h2');
    h2.style.color = '#dc3545';
    
    document.body.appendChild(rejectedDiv);
    
    setTimeout(() => window.close(), 5000);
}

function showMeetingEndedUI() {
    // Clear any polling
    if (joinCheckInterval) {
        clearInterval(joinCheckInterval);
    }
    
    // Hide normal meeting UI
    const videoMeetingArea = document.querySelector('.video-meeting-area');
    const controls = document.querySelector('.controls');
    const pendingPanel = document.querySelector('.pending-requests');
    
    if (videoMeetingArea) videoMeetingArea.style.display = 'none';
    if (controls) controls.style.display = 'none';
    if (pendingPanel) pendingPanel.style.display = 'none';
    
    // Remove pending UI if exists
    hidePendingUI();
    
    // Create meeting ended UI
    const endedDiv = document.createElement('div');
    endedDiv.id = 'meeting-ended-status';
    endedDiv.className = 'meeting-ended-status';
    endedDiv.innerHTML = `
        <div class="ended-content">
            <div class="ended-icon">🔚</div>
            <h2>Meeting Ended</h2>
            <p>This meeting has been terminated by the host.</p>
            <p class="meeting-id">Meeting ID: ${meetingId}</p>
            <p class="auto-close">This window will close automatically in 5 seconds...</p>
        </div>
    `;
    
    // Add styles
    endedDiv.style.cssText = `
        position: fixed;
        top: 80px;
        left: 0;
        width: 100%;
        height: calc(100% - 80px);
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    `;
    
    const endedContent = endedDiv.querySelector('.ended-content');
    endedContent.style.cssText = `
        text-align: center;
        color: white;
        padding: 40px;
        border-radius: 12px;
        background: #333;
        border: 2px solid #ffc107;
        max-width: 400px;
        width: 90%;
    `;
    
    const h2 = endedDiv.querySelector('h2');
    h2.style.color = '#ffc107';
    
    document.body.appendChild(endedDiv);
}

function startJoinStatusPolling() {
    // Clear any existing interval
    if (joinCheckInterval) {
        clearInterval(joinCheckInterval);
    }
    
    joinCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/meetings/${meetingId}/status`, {
                headers: {'Authorization': `Bearer ${token}`}
            });
            
            if (response.ok) {
                const data = await response.json();
                const newStatus = data.status;
                
                if (newStatus !== joinStatus) {
                    joinStatus = newStatus;
                    
                    if (joinStatus === 'approved') {
                        clearInterval(joinCheckInterval);
                        hidePendingUI();
                        await proceedToMeeting();
                    } else if (joinStatus === 'rejected') {
                        clearInterval(joinCheckInterval);
                        hidePendingUI();
                        showRejectedUI();
                    }
                }
            } else if (response.status === 404) {
                // Meeting was deleted
                clearInterval(joinCheckInterval);
                hidePendingUI();
                showMeetingEndedUI();
                setTimeout(() => window.close(), 5000);
            }
        } catch (error) {
            console.error('Error polling join status:', error);
            // Continue polling - might be temporary network issue
        }
    }, 2000); // Poll every 2 seconds
}

async function proceedToMeeting() {
    // Clear any polling
    if (joinCheckInterval) {
        clearInterval(joinCheckInterval);
    }
    
    // Hide pending UI if showing
    hidePendingUI();
    
    // Request permissions first
    const hasPermissions = await requestMediaPermissions();
    if (!hasPermissions) {
        showError('Media permissions are required for meetings. Please enable camera and microphone access.');
        return;
    }

    // Initialize media with error handling
    await initializeMedia();
    
    // Create local video tile
    createLocalVideoTile();
    
    // Check if user is meeting creator for admin features
    if (isMeetingCreator) {
        const pendingPanel = document.getElementById('pending-requests-panel');
        const deleteMeetingBtn = document.getElementById('delete-meeting-btn');
        
        if (pendingPanel) pendingPanel.classList.remove('hidden');
        if (deleteMeetingBtn) deleteMeetingBtn.classList.remove('hidden');
        
        loadPendingRequests();
        setInterval(loadPendingRequests, 5000);
    }
    
    // Connect to WebSocket
    connectWebSocket();
    
    // Set up event listeners (only once)
    if (!eventListenersSetup) {
        setupEventListeners();
        eventListenersSetup = true;
    }
    
    // Show connection status
    updateConnectionStatus('connecting');

    // Populate device lists
    await populateDeviceLists();
}

async function loadPendingRequests() {
    if (!isMeetingCreator || !token || !meetingId) return;
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}/pending`, {
            headers: {'Authorization': `Bearer ${token}`}
        });
        
        if (response.ok) {
            const requests = await response.json();
            const pendingList = document.getElementById('pending-requests-list');
            
            if (pendingList) {
                if (requests.length === 0) {
                    pendingList.innerHTML = '<p style="color: #ccc; text-align: center; padding: 10px;">No pending requests</p>';
                } else {
                    let requestsHtml = '';
                    requests.forEach(request => {
                        requestsHtml += `
                            <div class="pending-request">
                                <div class="request-info">
                                    <div class="request-name">${escapeHtml(request.name)}</div>
                                    <div class="request-id">${escapeHtml(request.public_id)} - ${new Date(request.requested_at).toLocaleTimeString()}</div>
                                </div>
                                <div class="request-actions">
                                    <button class="approve-btn" onclick="approveMeetingRequest('${request.user_id}', 'approve')">Approve</button>
                                    <button class="reject-btn" onclick="approveMeetingRequest('${request.user_id}', 'reject')">Reject</button>
                                </div>
                            </div>
                        `;
                    });
                    pendingList.innerHTML = requestsHtml;
                }
                
                // Update panel visibility
                const pendingPanel = document.getElementById('pending-requests-panel');
                if (pendingPanel) {
                    if (requests.length > 0) {
                        pendingPanel.classList.remove('hidden');
                    } else if (!pendingPanelCollapsed) {
                        // Only hide if manually collapsed
                        pendingPanel.classList.add('hidden');
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error loading pending requests:', error);
    }
}

async function approveMeetingRequest(userId, action) {
    if (!isMeetingCreator || !token || !meetingId) return;
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: action
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message);
            // Reload pending requests
            loadPendingRequests();
        } else {
            const data = await response.json();
            showError(data.detail || `Failed to ${action} request`);
        }
    } catch (error) {
        console.error('Error approving request:', error);
        showError('Network error. Please try again.');
    }
}

function togglePendingPanel() {
    const panel = document.getElementById('pending-requests-panel');
    const list = document.getElementById('pending-requests-list');
    const collapseBtn = document.querySelector('.collapse-btn');
    
    if (panel && list && collapseBtn) {
        if (pendingPanelCollapsed) {
            list.style.display = 'block';
            collapseBtn.textContent = '−';
            pendingPanelCollapsed = false;
        } else {
            list.style.display = 'none';
            collapseBtn.textContent = '+';
            pendingPanelCollapsed = true;
        }
    }
}

async function deleteMeeting() {
    if (!isMeetingCreator || !confirm('Are you sure you want to delete this meeting? This will end the meeting for all participants.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}`, {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${token}`}
        });
        
        if (response.ok) {
            showSuccess('Meeting deleted successfully');
            setTimeout(() => window.close(), 2000);
        } else {
            const data = await response.json();
            showError(data.detail || 'Failed to delete meeting');
        }
    } catch (error) {
        console.error('Error deleting meeting:', error);
        showError('Network error. Please try again.');
    }
}

async function requestMediaPermissions() {
    try {
        // Request both audio and video permissions
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: true, 
            video: true 
        });
        
        // Stop the tracks immediately - we just wanted to check permissions
        stream.getTracks().forEach(track => track.stop());
        return true;
    } catch (error) {
        console.error('Permission denied:', error);
        
        // Try audio only
        try {
            const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioStream.getTracks().forEach(track => track.stop());
            showWarning('Camera access denied. You can still participate with audio only.');
            return true;
        } catch (audioError) {
            console.error('Audio permission also denied:', audioError);
            return false;
        }
    }
}

let mediaInitialized = false; // Add this flag

async function initializeMedia() {
    if (mediaInitialized) {
        console.log('Media already initialized, skipping...');
        return;
    }
    
    try {
        // Start with audio only by default - use browser's default microphone
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                deviceId: 'default' // Use browser's default microphone
            },
            video: false
        });
        
        mediaInitialized = true;
        
        // Update button states
        updateMediaButtons();
        
        console.log('Media initialized successfully');
        
    } catch (error) {
        console.error('Error accessing media devices:', error);
        
        // Create empty stream as fallback
        localStream = new MediaStream();
        mediaInitialized = true; // Still set to prevent retry
        showWarning('Could not access microphone. Check permissions and try again.');
    }
}

function createLocalVideoTile() {
    const videoArea = document.getElementById('video-area');
    if (!videoArea) return;
    
    // Remove any existing local tile
    const existingTile = document.getElementById('local-user-tile');
    if (existingTile) {
        existingTile.remove();
    }
    
    const localTile = document.createElement('div');
    localTile.className = 'video-tile local-tile';
    localTile.id = 'local-user-tile';
    
    localTile.innerHTML = `
        <video id="local-video" autoplay muted playsinline></video>
        <div class="video-placeholder">
            <div class="placeholder-icon">📷</div>
            <div class="placeholder-text">Camera Off</div>
        </div>
        <div class="video-label">
            <span class="user-name">You</span>
            <div class="media-indicators">
                <span id="local-mic-indicator" class="indicator mic-off">🎤</span>
                <span id="local-cam-indicator" class="indicator cam-off">📷</span>
            </div>
        </div>
        <div class="video-overlay">
            <button class="overlay-btn" onclick="toggleCamera()" title="Toggle Camera">📷</button>
            <button class="overlay-btn" onclick="toggleMic()" title="Toggle Microphone">🎤</button>
        </div>
    `;
    
    videoArea.appendChild(localTile);
    
    // Get video element reference
    localVideoElement = document.getElementById('local-video');
    
    // Set initial states
    updateLocalVideoDisplay();
}

function updateLocalVideoDisplay() {
    const videoElement = document.getElementById('local-video');
    const placeholder = document.querySelector('#local-user-tile .video-placeholder');
    const micIndicator = document.getElementById('local-mic-indicator');
    const camIndicator = document.getElementById('local-cam-indicator');
    
    if (!videoElement || !placeholder) return;
    
    if (isCameraOn && localStream && localStream.getVideoTracks().length > 0) {
        videoElement.srcObject = localStream;
        videoElement.style.display = 'block';
        placeholder.style.display = 'none';
    } else {
        videoElement.style.display = 'none';
        placeholder.style.display = 'flex';
    }
    
    // Update indicators
    if (micIndicator) {
        micIndicator.className = `indicator ${isMicOn ? 'mic-on' : 'mic-off'}`;
        micIndicator.textContent = isMicOn ? '🎤' : '🔇';
    }
    
    if (camIndicator) {
        camIndicator.className = `indicator ${isCameraOn ? 'cam-on' : 'cam-off'}`;
        camIndicator.textContent = isCameraOn ? '📷' : '📷';
    }
}

function connectWebSocket() {
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/meeting/${meetingId}?token=${token}`;
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            updateConnectionStatus('connected');
            displayChatMessage({
                type: 'system',
                message: 'Connected to meeting',
                timestamp: new Date().toISOString(),
                user: { name: 'System', public_id: 'SYS' }
            });
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
            displayChatMessage({
                type: 'system',
                message: 'Disconnected from meeting',
                timestamp: new Date().toISOString(),
                user: { name: 'System', public_id: 'SYS' }
            });
            
            // Attempt to reconnect only if approved
            if (joinStatus === 'approved') {
                setTimeout(() => {
                    if (connectionStatus === 'disconnected') {
                        connectWebSocket();
                    }
                }, 3000);
            }
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus('disconnected');
            showError('Connection error occurred');
        };
        
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        updateConnectionStatus('disconnected');
        showError('Failed to connect to meeting');
    }
}

async function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'user_joined':
            if (data.user && data.user.user_id !== currentUser.user_id) {
                await addParticipantVideo(data.user);
                await createPeerConnection(data.user.user_id);
                displayChatMessage({
                    type: 'system',
                    message: `${data.user.name} joined the meeting`,
                    timestamp: new Date().toISOString(),
                    user: { name: 'System', public_id: 'SYS' }
                });
            }
            break;
            
        case 'user_left':
            if (data.user && data.user.user_id !== currentUser.user_id) {
                removeParticipantVideo(data.user);
                closePeerConnection(data.user.user_id);
                displayChatMessage({
                    type: 'system',
                    message: `${data.user.name} left the meeting`,
                    timestamp: new Date().toISOString(),
                    user: { name: 'System', public_id: 'SYS' }
                });
            }
            break;
            
        case 'webrtc_offer':
            await handleWebRTCOffer(data);
            break;
            
        case 'webrtc_answer':
            await handleWebRTCAnswer(data);
            break;
            
        case 'webrtc_ice_candidate':
            await handleICECandidate(data);
            break;
            
        case 'media_state':
            if (data.user && data.user.user_id !== currentUser.user_id) {
                updateParticipantMediaState(data.user, data.mediaState);
            }
            break;
            
        case 'chat':
        case 'message':
            displayChatMessage(data);
            break;
            
        case 'system':
        case 'system_notification':
            displayChatMessage({
                ...data,
                user: { name: 'System', public_id: 'SYS' }
            });
            break;
            
        case 'participant_update':
            updateParticipantCount(data.count);
            break;
            
        case 'pending_request':
            // Handle new pending request notifications for host
            if (isMeetingCreator) {
                showSuccess(data.message);
                loadPendingRequests();
            }
            break;
            
        case 'pending_requests_update':
            // Handle pending requests count updates
            if (isMeetingCreator) {
                loadPendingRequests();
            }
            break;
            
        case 'request_decision':
            // Handle approval/rejection decision for requester
            if (data.decision === 'approve') {
                showSuccess('Your request has been approved!');
                // Status polling will handle the transition
            } else if (data.decision === 'reject') {
                showError('Your request has been rejected');
                setTimeout(() => window.close(), 3000);
            }
            break;
            
        case 'meeting_removed':
        case 'meeting_kicked':
            showError(data.message);
            setTimeout(() => window.close(), 3000);
            break;
            
        case 'meeting_deleted':
        case 'meeting_ended':
            showMeetingEndedUI();
            setTimeout(() => window.close(), 5000);
            break;
            
        default:
            console.log('Unknown message type:', data.type);
    }
}

// WebRTC Functions
async function createPeerConnection(userId) {
    if (peerConnections.has(userId)) {
        console.log(`Peer connection already exists for user ${userId}`);
        return;
    }
    
    console.log(`Creating peer connection for user ${userId}`);
    
    const pc = new RTCPeerConnection({
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' },
            { urls: 'stun:stun3.l.google.com:19302' },
            { urls: 'stun:stun4.l.google.com:19302' }
        ],
        iceCandidatePoolSize: 10,
        iceTransportPolicy: 'all'
    });
    
    // Add local stream tracks
    if (localStream) {
        localStream.getTracks().forEach(track => {
            console.log(`Adding ${track.kind} track to peer connection`);
            pc.addTrack(track, localStream);
        });
    }
    
    // Handle remote stream
    pc.ontrack = (event) => {
        console.log(`🎥 Received ${event.track.kind} track from user ${userId}`, event);
        console.log(`Track details:`, {
            id: event.track.id,
            kind: event.track.kind,
            enabled: event.track.enabled,
            muted: event.track.muted,
            readyState: event.track.readyState
        });
        
        const [remoteStream] = event.streams;
        console.log(`Stream details:`, {
            id: remoteStream.id,
            audioTracks: remoteStream.getAudioTracks().length,
            videoTracks: remoteStream.getVideoTracks().length
        });
        
        remoteStreams.set(userId, remoteStream);
        updateParticipantVideo(userId, remoteStream);
        
        // Add track event listeners for debugging
        event.track.onmute = () => {
            console.log(`Track ${event.track.kind} muted for user ${userId}`);
            updateParticipantVideo(userId, remoteStream);
        };
        
        event.track.onunmute = () => {
            console.log(`Track ${event.track.kind} unmuted for user ${userId}`);
            updateParticipantVideo(userId, remoteStream);
        };
        
        event.track.onended = () => {
            console.log(`Track ${event.track.kind} ended for user ${userId}`);
            updateParticipantVideo(userId, remoteStream);
        };
    };
    
    // Handle ICE candidates
    pc.onicecandidate = (event) => {
        if (event.candidate && ws && ws.readyState === WebSocket.OPEN) {
            console.log(`Sending ICE candidate to user ${userId}`);
            ws.send(JSON.stringify({
                type: 'webrtc_ice_candidate',
                candidate: event.candidate,
                targetUserId: userId
            }));
        }
    };
    
    // Handle connection state changes
    pc.onconnectionstatechange = () => {
        console.log(`Peer connection state for ${userId}: ${pc.connectionState}`);
        
        switch (pc.connectionState) {
            case 'connected':
                console.log(`✓ Successfully connected to user ${userId}`);
                clearConnectionStatus(userId);
                break;
                
            case 'disconnected':
                console.warn(`⚠ Disconnected from user ${userId}`);
                break;
                
            case 'failed':
                console.error(`✗ Peer connection failed for user ${userId}`);
                debugWebRTCConnection(userId);
                handleConnectionFailure(userId, pc);
                break;
                
            case 'closed':
                console.log(`Connection closed for user ${userId}`);
                peerConnections.delete(userId);
                break;
        }
    };
    
    // Handle ICE connection state changes for more detailed debugging
    pc.oniceconnectionstatechange = () => {
        console.log(`ICE connection state for ${userId}: ${pc.iceConnectionState}`);
        
        if (pc.iceConnectionState === 'failed') {
            console.error(`ICE connection failed for user ${userId}`);
            // Try to restart ICE
            restartIceConnection(userId);
        }
    };
    
    // Store connection
    peerConnections.set(userId, pc);
    
    // Create and send offer
    try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            console.log(`Sending offer to user ${userId}`);
            ws.send(JSON.stringify({
                type: 'webrtc_offer',
                offer: offer,
                targetUserId: userId
            }));
        }
    } catch (error) {
        console.error(`Error creating offer for user ${userId}:`, error);
    }
}

async function handleWebRTCOffer(data) {
    const userId = data.fromUserId;
    console.log(`Received offer from user ${userId}`);
    
    let pc = peerConnections.get(userId);
    
    if (!pc) {
        console.log(`Creating new peer connection for offer from ${userId}`);
        pc = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' },
                { urls: 'stun:stun3.l.google.com:19302' },
                { urls: 'stun:stun4.l.google.com:19302' }
            ],
            iceCandidatePoolSize: 10,
            iceTransportPolicy: 'all'
        });
        
        // Add local stream tracks
        if (localStream) {
            localStream.getTracks().forEach(track => {
                console.log(`Adding ${track.kind} track to peer connection for ${userId}`);
                pc.addTrack(track, localStream);
            });
        }
        
        // Handle remote stream
        pc.ontrack = (event) => {
            console.log(`Received ${event.track.kind} track from user ${userId}`);
            const [remoteStream] = event.streams;
            remoteStreams.set(userId, remoteStream);
            updateParticipantVideo(userId, remoteStream);
        };
        
        // Handle ICE candidates
        pc.onicecandidate = (event) => {
            if (event.candidate && ws && ws.readyState === WebSocket.OPEN) {
                console.log(`Sending ICE candidate to user ${userId}`);
                ws.send(JSON.stringify({
                    type: 'webrtc_ice_candidate',
                    candidate: event.candidate,
                    targetUserId: userId
                }));
            }
        };
        
        // Handle connection state changes
        pc.onconnectionstatechange = () => {
            console.log(`Peer connection state for ${userId}: ${pc.connectionState}`);
            
            switch (pc.connectionState) {
                case 'connected':
                    console.log(`✓ Successfully connected to user ${userId}`);
                    clearConnectionStatus(userId);
                    break;
                    
                case 'disconnected':
                    console.warn(`⚠ Disconnected from user ${userId}`);
                    break;
                    
                case 'failed':
                    console.error(`✗ Peer connection failed for user ${userId}`);
                    debugWebRTCConnection(userId);
                    handleConnectionFailure(userId, pc);
                    break;
                    
                case 'closed':
                    console.log(`Connection closed for user ${userId}`);
                    peerConnections.delete(userId);
                    break;
            }
        };
        
        // Handle ICE connection state changes for more detailed debugging
        pc.oniceconnectionstatechange = () => {
            console.log(`ICE connection state for ${userId}: ${pc.iceConnectionState}`);
            
            if (pc.iceConnectionState === 'failed') {
                console.error(`ICE connection failed for user ${userId}`);
                // Try to restart ICE
                restartIceConnection(userId);
            }
        };
        
        peerConnections.set(userId, pc);
    }
    
    try {
        await pc.setRemoteDescription(data.offer);
        console.log(`Set remote description for ${userId}`);
        
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        console.log(`Created answer for ${userId}`);
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'webrtc_answer',
                answer: answer,
                targetUserId: userId
            }));
            console.log(`Sent answer to ${userId}`);
        }
    } catch (error) {
        console.error(`Error handling offer from ${userId}:`, error);
    }
}

async function handleWebRTCAnswer(data) {
    const userId = data.fromUserId;
    console.log(`Received answer from user ${userId}`);
    
    const pc = peerConnections.get(userId);
    if (pc) {
        try {
            // Check if we're in the correct state to set remote description
            if (pc.signalingState === 'have-local-offer') {
                await pc.setRemoteDescription(data.answer);
                console.log(`Set remote description (answer) for ${userId}`);
            } else {
                console.warn(`Cannot set remote description for ${userId}, signaling state is: ${pc.signalingState}`);
            }
        } catch (error) {
            console.error(`Error handling answer from ${userId}:`, error);
        }
    } else {
        console.error(`No peer connection found for user ${userId} when handling answer`);
    }
}

async function handleICECandidate(data) {
    const userId = data.fromUserId;
    console.log(`Received ICE candidate from user ${userId}`);
    
    const pc = peerConnections.get(userId);
    if (pc) {
        try {
            await pc.addIceCandidate(data.candidate);
            console.log(`Added ICE candidate for ${userId}`);
        } catch (error) {
            console.error(`Error adding ICE candidate for ${userId}:`, error);
        }
    } else {
        console.error(`No peer connection found for user ${userId} when handling ICE candidate`);
    }
}

function closePeerConnection(userId) {
    const pc = peerConnections.get(userId);
    if (pc) {
        pc.close();
        peerConnections.delete(userId);
    }
    
    remoteStreams.delete(userId);
}

async function toggleMic() {
    if (!localStream) {
        showError('No audio stream available');
        return;
    }
    
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) {
        // Immediate UI feedback
        audioTrack.enabled = !audioTrack.enabled;
        isMicOn = audioTrack.enabled;
        
        // Update UI immediately for responsiveness
        updateMediaButtons();
        updateLocalVideoDisplay();
        
        // Notify other participants asynchronously to avoid blocking UI
        setTimeout(() => broadcastMediaState(), 0);
    } else {
        // Try to get new audio track
        try {
            const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const newAudioTrack = audioStream.getAudioTracks()[0];
            
            if (newAudioTrack) {
                localStream.addTrack(newAudioTrack);
                isMicOn = true;
                updateMediaButtons();
                updateLocalVideoDisplay();
                broadcastMediaState();
                
                // Add track to all peer connections
                peerConnections.forEach(async (pc) => {
                    try {
                        pc.addTrack(newAudioTrack, localStream);
                        // Create new offer to renegotiate with new track
                        const offer = await pc.createOffer();
                        await pc.setLocalDescription(offer);
                        
                        // Send new offer through WebSocket
                        const remoteUserId = Array.from(peerConnections.entries())
                            .find(([id, connection]) => connection === pc)?.[0];
                        if (remoteUserId && ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: 'webrtc_offer',
                                offer: offer,
                                targetUserId: remoteUserId
                            }));
                        }
                    } catch (error) {
                        console.error('Error adding audio track to peer connection:', error);
                    }
                });
            }
        } catch (error) {
            console.error('Error getting audio track:', error);
            showError('Could not access microphone');
        }
    }
}

async function toggleCamera() {
    if (isCameraOn) {
        // Turn camera OFF
        if (localStream) {
            const videoTracks = localStream.getVideoTracks();
            videoTracks.forEach(track => {
                track.stop();
                localStream.removeTrack(track);
            });
        }
        
        isCameraOn = false;
        
        // Update all peer connections to remove video
        for (const [remoteUserId, pc] of peerConnections.entries()) {
            const sender = pc.getSenders().find(s => 
                s.track && s.track.kind === 'video'
            );
            if (sender) {
                try {
                    await sender.replaceTrack(null);
                    // Only create offer if we're in a stable state
                    if (pc.signalingState === 'stable') {
                        const offer = await pc.createOffer();
                        await pc.setLocalDescription(offer);
                        
                        // Send new offer through WebSocket
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: 'webrtc_offer',
                                offer: offer,
                                targetUserId: remoteUserId
                            }));
                        }
                    }
                } catch (error) {
                    console.error('Error removing video track from peer connection:', error);
                }
            }
        }
        
    } else {
        // Turn camera ON
        try {
            const constraints = {
                video: {
                    ...videoConstraints[currentVideoQuality],
                    facingMode: 'user'
                }
            };
            
            const videoStream = await navigator.mediaDevices.getUserMedia(constraints);
            const videoTrack = videoStream.getVideoTracks()[0];
            
            if (videoTrack && localStream) {
                localStream.addTrack(videoTrack);
                
                // Add/replace track in all peer connections
                for (const [remoteUserId, pc] of peerConnections.entries()) {
                    try {
                        // First check if we already have a video sender (even with null track)
                        let sender = pc.getSenders().find(s => 
                            s.track?.kind === 'video' || 
                            (s.track === null && s.dtmf === null) // Empty video sender slot
                        );
                        
                        if (sender) {
                            console.log(`Replacing video track for ${remoteUserId}`);
                            await sender.replaceTrack(videoTrack);
                        } else {
                            console.log(`Adding new video track for ${remoteUserId}`);
                            const newSender = pc.addTrack(videoTrack, localStream);
                            console.log(`Added sender:`, newSender);
                        }
                        
                        // Wait a bit for track to be properly added, then create offer
                        await new Promise(resolve => setTimeout(resolve, 100));
                        
                        // Only create offer if we're in a stable state
                        if (pc.signalingState === 'stable') {
                            console.log(`Creating offer for ${remoteUserId} with video track`);
                            
                            // Include explicit offer options to ensure video is included
                            const offer = await pc.createOffer({
                                offerToReceiveAudio: true,
                                offerToReceiveVideo: true
                            });
                            
                            console.log(`Offer SDP for ${remoteUserId}:`, offer.sdp.includes('video'));
                            await pc.setLocalDescription(offer);
                            
                            // Send new offer through WebSocket
                            if (ws && ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({
                                    type: 'webrtc_offer',
                                    offer: offer,
                                    targetUserId: remoteUserId,
                                    mediaUpdate: true  // Flag to indicate this is a media update
                                }));
                                console.log(`Sent video offer to ${remoteUserId}`);
                            }
                        } else {
                            console.warn(`Cannot create offer for ${remoteUserId}, signaling state: ${pc.signalingState}`);
                        }
                    } catch (error) {
                        console.error('Error adding video track to peer connection:', error);
                    }
                }
            }
            
            isCameraOn = true;
            
        } catch (error) {
            console.error('Error starting camera:', error);
            showError('Could not start camera. Please check permissions.');
            isCameraOn = false;
        }
    }
    
    updateMediaButtons();
    updateLocalVideoDisplay();
    broadcastMediaState();
}

async function toggleScreen() {
    try {
        if (!isScreenSharing) {
            // Start screen sharing
            const screenStream = await navigator.mediaDevices.getDisplayMedia({
                video: {
                    ...videoConstraints[currentVideoQuality]
                },
                audio: true
            });
            
            const videoTrack = screenStream.getVideoTracks()[0];
            if (videoTrack && localStream) {
                // Replace video track
                const existingVideoTrack = localStream.getVideoTracks()[0];
                if (existingVideoTrack) {
                    localStream.removeTrack(existingVideoTrack);
                    existingVideoTrack.stop();
                }
                
                localStream.addTrack(videoTrack);
                
                // Update all peer connections
                for (const [remoteUserId, pc] of peerConnections.entries()) {
                    try {
                        const sender = pc.getSenders().find(s => 
                            s.track && s.track.kind === 'video'
                        );
                        if (sender) {
                            console.log('Replacing video track with screen share');
                            await sender.replaceTrack(videoTrack);
                        } else {
                            console.log('Adding screen share track to peer connection');
                            pc.addTrack(videoTrack, localStream);
                        }
                        
                        // Only create offer if we're in a stable state
                        if (pc.signalingState === 'stable') {
                            const offer = await pc.createOffer();
                            await pc.setLocalDescription(offer);
                            
                            // Send new offer through WebSocket
                            if (ws && ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({
                                    type: 'webrtc_offer',
                                    offer: offer,
                                    targetUserId: remoteUserId
                                }));
                            }
                        }
                    } catch (error) {
                        console.error('Error updating screen share in peer connection:', error);
                    }
                }
                
                if (localVideoElement) {
                    localVideoElement.srcObject = localStream;
                }
            }
            
            isScreenSharing = true;
            isCameraOn = true; // Screen sharing counts as camera on
            updateMediaButtons();
            updateLocalVideoDisplay();
            broadcastMediaState();
            
            // Handle screen share end
            videoTrack.onended = () => {
                console.log('Screen share ended by user');
                stopScreenShare();
            };
            
        } else {
            stopScreenShare();
        }
    } catch (error) {
        console.error('Error sharing screen:', error);
        showError('Failed to share screen. Please check permissions.');
    }
}

async function stopScreenShare() {
    if (!isScreenSharing) return;
    
    try {
        // Remove screen track
        if (localStream) {
            const videoTracks = localStream.getVideoTracks();
            videoTracks.forEach(track => {
                track.stop();
                localStream.removeTrack(track);
            });
        }
        
        isScreenSharing = false;
        isCameraOn = false;
        updateMediaButtons();
        updateLocalVideoDisplay();
        broadcastMediaState();
        
        // Update all peer connections to remove video
        for (const [remoteUserId, pc] of peerConnections.entries()) {
            const sender = pc.getSenders().find(s => 
                s.track && s.track.kind === 'video'
            );
            if (sender) {
                try {
                    await sender.replaceTrack(null);
                    // Only create offer if we're in a stable state
                    if (pc.signalingState === 'stable') {
                        const offer = await pc.createOffer();
                        await pc.setLocalDescription(offer);
                        
                        // Send new offer through WebSocket
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({
                                type: 'webrtc_offer',
                                offer: offer,
                                targetUserId: remoteUserId
                            }));
                        }
                    }
                } catch (error) {
                    console.error('Error stopping screen share in peer connection:', error);
                }
            }
        }
        
    } catch (error) {
        console.error('Error stopping screen share:', error);
    }
}

async function handleConnectionFailure(userId, failedPc) {
    console.log(`Handling connection failure for user ${userId}`);
    
    try {
        // Clean up the failed connection
        if (peerConnections.has(userId)) {
            const pc = peerConnections.get(userId);
            if (pc === failedPc) {
                pc.close();
                peerConnections.delete(userId);
            }
        }
        
        // Remove the user's video display
        const videoElement = document.getElementById(`participant-${userId}`);
        if (videoElement) {
            videoElement.style.opacity = '0.5';
            const statusText = videoElement.querySelector('.connection-status') || 
                             document.createElement('div');
            statusText.className = 'connection-status';
            statusText.textContent = 'Reconnecting...';
            statusText.style.cssText = `
                position: absolute;
                bottom: 5px;
                left: 5px;
                background: rgba(255, 165, 0, 0.8);
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
            `;
            if (!videoElement.querySelector('.connection-status')) {
                videoElement.appendChild(statusText);
            }
        }
        
        // Wait a bit before attempting to reconnect
        setTimeout(async () => {
            console.log(`Attempting to reconnect to user ${userId}`);
            
            // Only reconnect if user is still in the meeting
            const participantExists = document.getElementById(`participant-${userId}`);
            if (participantExists && ws && ws.readyState === WebSocket.OPEN) {
                await createPeerConnection(userId);
            }
        }, 2000);
        
    } catch (error) {
        console.error(`Error handling connection failure for ${userId}:`, error);
    }
}

async function restartIceConnection(userId) {
    console.log(`Restarting ICE connection for user ${userId}`);
    
    const pc = peerConnections.get(userId);
    if (!pc) return;
    
    try {
        // Create a new offer to restart ICE
        if (pc.signalingState === 'stable') {
            const offer = await pc.createOffer({ iceRestart: true });
            await pc.setLocalDescription(offer);
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'webrtc_offer',
                    offer: offer,
                    targetUserId: userId,
                    iceRestart: true
                }));
                console.log(`Sent ICE restart offer to user ${userId}`);
            }
        }
    } catch (error) {
        console.error(`Error restarting ICE for user ${userId}:`, error);
        // If ICE restart fails, fall back to full reconnection
        handleConnectionFailure(userId, pc);
    }
}

function clearConnectionStatus(userId) {
    const videoElement = document.getElementById(`participant-${userId}`);
    if (videoElement) {
        videoElement.style.opacity = '1';
        const statusElement = videoElement.querySelector('.connection-status');
        if (statusElement) {
            statusElement.remove();
        }
    }
}

async function logConnectionStats(userId) {
    const pc = peerConnections.get(userId);
    if (!pc) return;
    
    try {
        const stats = await pc.getStats();
        let candidatePairs = [];
        let localCandidates = [];
        let remoteCandidates = [];
        
        stats.forEach(report => {
            if (report.type === 'candidate-pair') {
                candidatePairs.push(report);
            } else if (report.type === 'local-candidate') {
                localCandidates.push(report);
            } else if (report.type === 'remote-candidate') {
                remoteCandidates.push(report);
            }
        });
        
        console.log(`Connection stats for ${userId}:`, {
            connectionState: pc.connectionState,
            iceConnectionState: pc.iceConnectionState,
            iceGatheringState: pc.iceGatheringState,
            signalingState: pc.signalingState,
            candidatePairs: candidatePairs.length,
            localCandidates: localCandidates.length,
            remoteCandidates: remoteCandidates.length,
            selectedPair: candidatePairs.find(pair => pair.selected || pair.nominated)
        });
        
    } catch (error) {
        console.error(`Error getting stats for ${userId}:`, error);
    }
}

// Global debugging functions (accessible from console)
window.debugWebRTC = function(userId) {
    if (!userId) {
        console.log('Available peer connections:', Array.from(peerConnections.keys()));
        console.log('Usage: debugWebRTC("user_id") or debugWebRTC() to see all connections');
        peerConnections.forEach((pc, id) => {
            debugWebRTCConnection(id);
        });
        return;
    }
    debugWebRTCConnection(userId);
};

window.debugLocalStream = function() {
    console.log('🎥 Local stream debug:');
    console.log('- Has local stream:', !!localStream);
    if (localStream) {
        console.log('- Stream ID:', localStream.id);
        console.log('- Audio tracks:', localStream.getAudioTracks().length);
        console.log('- Video tracks:', localStream.getVideoTracks().length);
        
        localStream.getAudioTracks().forEach((track, i) => {
            console.log(`  Audio track ${i}:`, {
                id: track.id,
                kind: track.kind,
                enabled: track.enabled,
                readyState: track.readyState,
                muted: track.muted
            });
        });
        
        localStream.getVideoTracks().forEach((track, i) => {
            console.log(`  Video track ${i}:`, {
                id: track.id,
                kind: track.kind,
                enabled: track.enabled,
                readyState: track.readyState,
                muted: track.muted,
                settings: track.getSettings()
            });
        });
    }
    
    console.log('- Camera state:', isCameraOn);
    console.log('- Mic state:', isMicOn);
    console.log('- Screen sharing:', isScreenSharing);
    
    const localVideo = document.getElementById('local-video');
    if (localVideo) {
        console.log('- Local video element:', {
            srcObject: !!localVideo.srcObject,
            videoWidth: localVideo.videoWidth,
            videoHeight: localVideo.videoHeight,
            readyState: localVideo.readyState,
            paused: localVideo.paused
        });
    }
};

window.debugAllConnections = function() {
    console.log('🔍 Complete WebRTC debug:');
    debugLocalStream();
    console.log('');
    debugWebRTC();
};

async function copyMeetingId() {
    const button = document.querySelector('.meeting-copy-btn');
    try {
        await navigator.clipboard.writeText(meetingId);
        
        // Visual feedback
        const originalText = button.textContent;
        button.textContent = '✓';
        button.classList.add('copied');
        
        // Reset after 2 seconds
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 2000);
        
        // Show success message
        createToast('Meeting ID copied to clipboard!', 'success');
    } catch (error) {
        console.error('Failed to copy to clipboard:', error);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = meetingId;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            createToast('Meeting ID copied to clipboard!', 'success');
            
            // Visual feedback
            const originalText = button.textContent;
            button.textContent = '✓';
            button.classList.add('copied');
            
            setTimeout(() => {
                button.textContent = originalText;
                button.classList.remove('copied');
            }, 2000);
        } catch (fallbackError) {
            createToast('Could not copy to clipboard', 'error');
        }
        document.body.removeChild(textArea);
    }
}

// Enhanced debugging for WebRTC issues
function debugWebRTCConnection(userId) {
    const pc = peerConnections.get(userId);
    if (!pc) {
        console.error(`No peer connection found for user ${userId}`);
        return;
    }
    
    console.log(`🔍 Debug info for ${userId}:`);
    console.log(`- Connection State: ${pc.connectionState}`);
    console.log(`- ICE Connection State: ${pc.iceConnectionState}`);
    console.log(`- ICE Gathering State: ${pc.iceGatheringState}`);
    console.log(`- Signaling State: ${pc.signalingState}`);
    
    // Log detailed stats
    logConnectionStats(userId);
    
    // Check if we have media tracks
    const senders = pc.getSenders();
    const receivers = pc.getReceivers();
    console.log(`- Senders: ${senders.length} (${senders.map(s => s.track?.kind || 'null').join(', ')})`);
    console.log(`- Receivers: ${receivers.length} (${receivers.map(r => r.track?.kind || 'null').join(', ')})`);
}

function updateMediaButtons() {
    const micBtn = document.getElementById('mic-btn');
    const cameraBtn = document.getElementById('camera-btn');
    const screenBtn = document.getElementById('screen-btn');
    
    if (micBtn) {
        micBtn.innerHTML = isMicOn ? 'MIC ON' : 'MIC OFF';
        micBtn.className = `control-btn mic-btn ${isMicOn ? '' : 'off'}`;
    }
    
    if (cameraBtn) {
        if (isScreenSharing) {
            cameraBtn.innerHTML = 'SCREEN ON';
            cameraBtn.className = 'control-btn camera-btn screen-active';
        } else {
            cameraBtn.innerHTML = isCameraOn ? 'CAM ON' : 'CAM OFF';
            cameraBtn.className = `control-btn camera-btn ${isCameraOn ? '' : 'off'}`;
        }
    }
    
    if (screenBtn) {
        screenBtn.innerHTML = isScreenSharing ? 'STOP SHARE' : 'SHARE SCREEN';
        screenBtn.className = `control-btn screen-btn ${isScreenSharing ? 'sharing' : ''}`;
    }
}

function broadcastMediaState() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        try {
            ws.send(JSON.stringify({
                type: 'media_state',
                mediaState: {
                    audio: isMicOn,
                    video: isCameraOn,
                    screen: isScreenSharing
                }
            }));
        } catch (error) {
            console.error('Error broadcasting media state:', error);
        }
    }
}

async function addParticipantVideo(user) {
    const videoArea = document.getElementById('video-area');
    if (!videoArea) return;
    
    // Check if participant already exists
    const existingTile = document.getElementById(`participant-${user.user_id}`);
    if (existingTile) return;
    
    const videoTile = document.createElement('div');
    videoTile.className = 'video-tile remote-tile';
    videoTile.id = `participant-${user.user_id}`;
    
    let participantControls = '';
    if (isMeetingCreator && user.user_id !== currentUser.user_id) {
        participantControls = `
            <div class="participant-controls">
                <button class="control-button kick-btn" onclick="kickParticipant('${user.user_id}', 'kick')" title="Kick">Kick</button>
                <button class="control-button block-btn" onclick="kickParticipant('${user.user_id}', 'block')" title="Block">Block</button>
            </div>
        `;
    }
    
    videoTile.innerHTML = `
        <video id="video-${user.user_id}" autoplay playsinline></video>
        <div class="video-placeholder">
            <div class="placeholder-icon">👤</div>
            <div class="placeholder-text">${escapeHtml(user.name)}</div>
        </div>
        <div class="video-label">
            <span class="user-name">${escapeHtml(user.name)} (${escapeHtml(user.public_id)})</span>
            <div class="media-indicators">
                <span id="mic-${user.user_id}" class="indicator mic-off">🔇</span>
                <span id="cam-${user.user_id}" class="indicator cam-off">📷</span>
            </div>
        </div>
        ${participantControls}
    `;
    
    videoArea.appendChild(videoTile);
    updateParticipantCount(participantCount + 1);
}

function updateParticipantVideo(userId, stream) {
    const videoElement = document.getElementById(`video-${userId}`);
    const placeholder = document.querySelector(`#participant-${userId} .video-placeholder`);
    
    console.log(`🔄 Updating video for user ${userId}`, {
        hasVideoElement: !!videoElement,
        hasStream: !!stream,
        streamId: stream?.id,
        videoTracks: stream?.getVideoTracks().length || 0,
        audioTracks: stream?.getAudioTracks().length || 0
    });
    
    if (videoElement && stream) {
        videoElement.srcObject = stream;
        
        const videoTrack = stream.getVideoTracks()[0];
        console.log(`Video track details for ${userId}:`, {
            hasVideoTrack: !!videoTrack,
            enabled: videoTrack?.enabled,
            readyState: videoTrack?.readyState,
            muted: videoTrack?.muted,
            kind: videoTrack?.kind,
            id: videoTrack?.id
        });
        
        if (videoTrack && videoTrack.enabled && videoTrack.readyState === 'live') {
            console.log(`✅ Showing video for user ${userId}`);
            videoElement.style.display = 'block';
            if (placeholder) placeholder.style.display = 'none';
            
            // Ensure video plays and add additional debugging
            videoElement.play().then(() => {
                console.log(`▶️ Video playing successfully for user ${userId}`);
                console.log(`Video element state:`, {
                    readyState: videoElement.readyState,
                    videoWidth: videoElement.videoWidth,
                    videoHeight: videoElement.videoHeight,
                    paused: videoElement.paused,
                    muted: videoElement.muted
                });
            }).catch(e => {
                console.error(`❌ Error playing video for user ${userId}:`, e);
            });
        } else {
            console.log(`⚫ Hiding video for user ${userId} (no active video track)`, {
                trackReason: !videoTrack ? 'no track' : 
                           !videoTrack.enabled ? 'track disabled' :
                           videoTrack.readyState !== 'live' ? `track state: ${videoTrack.readyState}` : 'unknown'
            });
            videoElement.style.display = 'none';
            if (placeholder) placeholder.style.display = 'flex';
        }
    } else {
        console.warn(`⚠️ Video element or stream not found for user ${userId}`, {
            hasVideoElement: !!videoElement,
            hasStream: !!stream,
            participantExists: !!document.getElementById(`participant-${userId}`)
        });
    }
}

function updateParticipantMediaState(user, mediaState) {
    console.log(`Updating media state for user ${user.user_id}:`, mediaState);
    
    const micIndicator = document.getElementById(`mic-${user.user_id}`);
    const camIndicator = document.getElementById(`cam-${user.user_id}`);
    const videoElement = document.getElementById(`video-${user.user_id}`);
    const placeholder = document.querySelector(`#participant-${user.user_id} .video-placeholder`);
    
    if (micIndicator) {
        micIndicator.className = `indicator ${mediaState.audio ? 'mic-on' : 'mic-off'}`;
        micIndicator.textContent = mediaState.audio ? '🎤' : '🔇';
    }
    
    if (camIndicator) {
        const icon = mediaState.screen ? '🖥️' : '📷';
        camIndicator.className = `indicator ${mediaState.video ? 'cam-on' : 'cam-off'}`;
        camIndicator.textContent = icon;
    }
    
    // Update video display based on camera state
    if (videoElement && placeholder) {
        if (mediaState.video) {
            // Check if we have a stream for this user
            const stream = remoteStreams.get(user.user_id);
            if (stream) {
                const videoTrack = stream.getVideoTracks()[0];
                if (videoTrack && videoTrack.readyState === 'live') {
                    console.log(`Showing video for user ${user.user_id} due to media state update`);
                    videoElement.style.display = 'block';
                    placeholder.style.display = 'none';
                    
                    // Ensure video plays
                    videoElement.play().catch(e => {
                        console.error(`Error playing video for user ${user.user_id}:`, e);
                    });
                }
            }
        } else {
            console.log(`Hiding video for user ${user.user_id} due to media state update`);
            videoElement.style.display = 'none';
            placeholder.style.display = 'flex';
        }
    }
}

// Settings and Device Management
async function populateDeviceLists() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        
        const audioInputSelect = document.getElementById('audio-input');
        const videoInputSelect = document.getElementById('video-input');
        
        if (audioInputSelect && videoInputSelect) {
            // Clear existing options
            audioInputSelect.innerHTML = '';
            videoInputSelect.innerHTML = '';
            
            devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label || `${device.kind} ${device.deviceId.substr(0, 8)}`;
                
                if (device.kind === 'audioinput') {
                    audioInputSelect.appendChild(option);
                } else if (device.kind === 'videoinput') {
                    videoInputSelect.appendChild(option);
                }
            });
        }
    } catch (error) {
        console.error('Error enumerating devices:', error);
    }
}

function showSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.remove('hidden');
    }
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

async function changeVideoQuality() {
    const select = document.getElementById('video-quality');
    if (select) {
        currentVideoQuality = select.value;
        
        // Apply bandwidth limit if active
        if (currentBandwidthLimit !== 'unlimited') {
            await applyBandwidthLimit();
        }
        
        // Restart camera if active
        if (isCameraOn) {
            await toggleCamera(); // Turn off
            await toggleCamera(); // Turn on with new quality
        }
    }
}

async function changeBandwidthLimit() {
    const select = document.getElementById('bandwidth-limit');
    if (select) {
        currentBandwidthLimit = select.value;
        await applyBandwidthLimit();
    }
}

async function applyBandwidthLimit() {
    const limit = bandwidthLimits[currentBandwidthLimit];
    if (!limit) return;
    
    // Apply bandwidth limit to all peer connections
    peerConnections.forEach(async (pc) => {
        const senders = pc.getSenders();
        for (const sender of senders) {
            if (sender.track && sender.track.kind === 'video') {
                const params = sender.getParameters();
                if (!params.encodings) params.encodings = [{}];
                
                params.encodings[0].maxBitrate = limit * 1000; // Convert to bps
                
                try {
                    await sender.setParameters(params);
                } catch (error) {
                    console.error('Error setting bandwidth limit:', error);
                }
            }
        }
    });
}

// Utility Functions
function updateConnectionStatus(status) {
    connectionStatus = status;
    const statusElement = document.getElementById('connection-status');
    
    if (statusElement) {
        statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        statusElement.className = `connection-status ${status}`;
    }
}

let lastMessageTime = 0;
const MESSAGE_THROTTLE = 500; // 500ms throttle

function displayChatMessage(data) {
    const chatDiv = document.getElementById('chat-messages');
    if (!chatDiv) return;
    
    // Throttle messages to prevent duplicates
    const now = Date.now();
    if (now - lastMessageTime < MESSAGE_THROTTLE) {
        return;
    }
    lastMessageTime = now;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    const time = formatTime(data.timestamp);
    const userName = data.user ? data.user.name : 'Unknown';
    const isSystem = data.type === 'system' || data.type === 'system_notification';
    
    if (isSystem) {
        messageDiv.classList.add('system-message');
        messageDiv.innerHTML = `
            <div class="message-content">
                <span class="system-icon">ℹ️</span>
                ${escapeHtml(data.message)}
            </div>
            <div class="message-time">${time}</div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="user-name">${escapeHtml(userName)}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">${escapeHtml(data.message)}</div>
        `;
    }
    
    chatDiv.appendChild(messageDiv);
    scrollChatToBottom();
}

let lastMessageSent = 0;
const SEND_THROTTLE = 1000; // 1 second throttle

function sendChatMessage() {
    const chatInput = document.getElementById('chat-input');
    if (!chatInput || !ws || ws.readyState !== WebSocket.OPEN) {
        showError('Cannot send message - not connected');
        return;
    }
    
    // Throttle message sending
    const now = Date.now();
    if (now - lastMessageSent < SEND_THROTTLE) {
        showError('Please wait before sending another message');
        return;
    }
    
    const message = chatInput.value.trim();
    if (!message) return;
    
    if (message.length > 500) {
        showError('Message too long (max 500 characters)');
        return;
    }
    
    try {
        ws.send(JSON.stringify({
            type: 'chat',
            message: message
        }));
        
        lastMessageSent = now;
        chatInput.value = '';
    } catch (error) {
        console.error('Error sending chat message:', error);
        showError('Failed to send message');
    }
}

function scrollChatToBottom() {
    const chatDiv = document.getElementById('chat-messages');
    if (chatDiv) {
        chatDiv.scrollTop = chatDiv.scrollHeight;
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
    createToast(message, 'error');
}

function showWarning(message) {
    createToast(message, 'warning');
}

function showSuccess(message) {
    createToast(message, 'success');
}

function createToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    const styles = {
        error: { bg: '#f8d7da', color: '#721c24', border: '#f5c6cb' },
        warning: { bg: '#fff3cd', color: '#856404', border: '#ffeaa7' },
        success: { bg: '#d4edda', color: '#155724', border: '#c3e6cb' }
    };
    
    const style = styles[type] || styles.error;
    
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${style.bg};
        color: ${style.color};
        padding: 12px 20px;
        border: 1px solid ${style.border};
        border-radius: 4px;
        z-index: 10000;
        font-weight: 500;
        max-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease-out;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        if (toast.parentNode) {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
}

// Event Listeners
function setupEventListeners() {
    // Chat input
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendChatMessage();
            }
        });
    }
    
    // Window events
    window.addEventListener('beforeunload', function() {
        // Clean up resources
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
        
        peerConnections.forEach(pc => pc.close());
        
        if (ws) {
            ws.close();
        }
        
        if (joinCheckInterval) {
            clearInterval(joinCheckInterval);
        }
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        if (event.target.tagName === 'INPUT') return;
        
        // Space bar to toggle mic
        if (event.code === 'Space') {
            event.preventDefault();
            toggleMic();
        }
        
        // Ctrl+D to toggle camera
        if (event.ctrlKey && event.code === 'KeyD') {
            event.preventDefault();
            toggleCamera();
        }
        
        // Ctrl+Shift+S to toggle screen share
        if (event.ctrlKey && event.shiftKey && event.code === 'KeyS') {
            event.preventDefault();
            toggleScreen();
        }
        
        // Escape to leave meeting
        if (event.code === 'Escape') {
            leaveMeeting();
        }
    });
}

function updateParticipantCount(count) {
    participantCount = count;
    const countElement = document.getElementById('participant-count');
    if (countElement) {
        countElement.textContent = `${count} participant${count !== 1 ? 's' : ''}`;
    }
}

function removeParticipantVideo(user) {
    const videoTile = document.getElementById(`participant-${user.user_id}`);
    if (videoTile) {
        videoTile.remove();
        updateParticipantCount(Math.max(0, participantCount - 1));
    }
}

async function kickParticipant(userId, action) {
    if (!isMeetingCreator || !confirm(`Are you sure you want to ${action} this participant?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/meetings/${meetingId}/kick`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                target_user_id: userId,
                action: action
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message);
        } else {
            const data = await response.json();
            showError(data.detail || `Failed to ${action} participant`);
        }
    } catch (error) {
        console.error('Error kicking participant:', error);
        showError('Network error. Please try again.');
    }
}

function leaveMeeting() {
    if (confirm('Are you sure you want to leave the meeting?')) {
        // Clean up resources
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
        
        peerConnections.forEach(pc => pc.close());
        
        if (ws) {
            ws.close();
        }
        
        if (joinCheckInterval) {
            clearInterval(joinCheckInterval);
        }
        
        window.close();
    }
}

// Export functions for global access
window.toggleMic = toggleMic;
window.toggleCamera = toggleCamera;
window.toggleScreen = toggleScreen;
window.sendChatMessage = sendChatMessage;
window.leaveMeeting = leaveMeeting;
window.deleteMeeting = deleteMeeting;
window.showSettings = showSettings;
window.closeSettings = closeSettings;
window.changeVideoQuality = changeVideoQuality;
window.changeBandwidthLimit = changeBandwidthLimit;
window.acceptGDPR = acceptGDPR;
window.rejectGDPR = rejectGDPR;
window.kickParticipant = kickParticipant;
window.togglePendingPanel = togglePendingPanel;
window.approveMeetingRequest = approveMeetingRequest;