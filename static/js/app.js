// app.js - Main Application JavaScript

// Global variables
let currentUser = null;
let authToken = null;
let refreshToken = null;
let csrfToken = null;
let appConfig = null;

// =============================================================================
// SECURITY & INPUT SANITIZATION
// =============================================================================

function sanitizeInput(input) {
    if (typeof input !== 'string') return input;
    
    // Remove HTML tags and encode special characters
    const tempDiv = document.createElement('div');
    tempDiv.textContent = input;
    return tempDiv.innerHTML
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;')
        .replace(/\//g, '&#x2F;');
}

function validateUserInput(input, maxLength = 100) {
    if (!input || typeof input !== 'string') {
        return { valid: false, error: 'Input cannot be empty' };
    }
    
    const trimmed = input.trim();
    if (trimmed.length === 0) {
        return { valid: false, error: 'Input cannot be empty' };
    }
    
    if (trimmed.length > maxLength) {
        return { valid: false, error: `Input too long (max ${maxLength} characters)` };
    }
    
    // Check for potential XSS patterns
    const xssPatterns = [
        /<script/i,
        /javascript:/i,
        /on\w+\s*=/i,
        /<iframe/i,
        /<object/i,
        /<embed/i
    ];
    
    for (const pattern of xssPatterns) {
        if (pattern.test(trimmed)) {
            return { valid: false, error: 'Invalid characters detected' };
        }
    }
    
    return { valid: true, value: sanitizeInput(trimmed) };
}

function validateId(id) {
    if (!id || typeof id !== 'string') {
        return false;
    }
    
    // Check if it's a valid hex string of 32 characters
    return /^[a-f0-9]{32}$/i.test(id.trim());
}

// =============================================================================
// CSRF TOKEN MANAGEMENT
// =============================================================================

async function getCSRFToken() {
    // Get CSRF token from server (returns null if disabled)
    try {
        const response = await fetch('/api/csrf-token');
        if (response.ok) {
            const data = await response.json();
            csrfToken = data.csrf_token; // Will be null if CSRF disabled
            return csrfToken;
        }
    } catch (error) {
        console.error('Error getting CSRF token:', error);
    }
    return null;
}

async function loadAppConfig() {
    // Load application configuration for feature flags
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            appConfig = await response.json();
            updateUIBasedOnConfig();
        }
    } catch (error) {
        console.error('Error loading app config:', error);
        // Use defaults if config fails to load
        appConfig = {
            features: {
                user_registration: true,
                team_creation: true,
                team_joining: true,
                meeting_creation: true,
                meeting_joining: true,
                file_upload: true,
                secret_id_retrieval: true,
                account_deletion: true
            }
        };
        updateUIBasedOnConfig();
    }
}

function updateUIBasedOnConfig() {
    // Update UI elements based on configuration
    if (!appConfig) return;
    
    const features = appConfig.features || {};
    
    // Hide/show registration option
    if (!features.user_registration) {
        const registerBtn = document.getElementById('register-toggle');
        if (registerBtn) registerBtn.style.display = 'none';
    }
    
    // Hide/show team creation
    if (!features.team_creation) {
        const createTeamBtn = document.querySelector('[onclick="showCreateTeamModal()"]');
        if (createTeamBtn) createTeamBtn.style.display = 'none';
    }
    
    // Hide/show team joining
    if (!features.team_joining) {
        const joinTeamBtn = document.querySelector('[onclick="showJoinTeamModal()"]');
        if (joinTeamBtn) joinTeamBtn.style.display = 'none';
    }
    
    // Hide/show meeting creation
    if (!features.meeting_creation) {
        const createMeetingBtn = document.querySelector('[onclick="showCreateMeetingModal()"]');
        if (createMeetingBtn) createMeetingBtn.style.display = 'none';
    }
    
    // Hide/show meeting joining
    if (!features.meeting_joining) {
        const joinMeetingBtn = document.querySelector('[onclick="showJoinMeetingModal()"]');
        if (joinMeetingBtn) joinMeetingBtn.style.display = 'none';
    }
    
    // Hide/show secret ID button
    if (!features.secret_id_retrieval) {
        const secretIdBtn = document.querySelector('[onclick="showSecretIdModal()"]');
        if (secretIdBtn) secretIdBtn.style.display = 'none';
    }
    
    // Hide/show account deletion
    if (!features.account_deletion) {
        const deleteAccountBtn = document.querySelector('[onclick="confirmDeleteAccount()"]');
        if (deleteAccountBtn) deleteAccountBtn.style.display = 'none';
    }
}

function isFeatureEnabled(feature) {
    // Check if a feature is enabled
    return appConfig?.features?.[feature] !== false;
}

async function makeSecureRequest(url, options = {}) {
    // Make authenticated request with optional CSRF protection
    // Only add CSRF token if it's enabled on the server
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method?.toUpperCase())) {
        if (!csrfToken) {
            await getCSRFToken();
        }
        
        // Add CSRF token to headers only if we have one
        if (csrfToken) {
            options.headers = {
                ...options.headers,
                'X-CSRF-Token': csrfToken
            };
        }
    }
    
    // Add auth token if available
    if (authToken) {
        options.headers = {
            ...options.headers,
            'Authorization': `Bearer ${authToken}`
        };
    }
    
    // Ensure Content-Type is set for JSON requests
    if (options.body && typeof options.body === 'string') {
        options.headers = {
            ...options.headers,
            'Content-Type': 'application/json'
        };
    }
    
    try {
        const response = await fetch(url, options);
        
        // Handle token expiration
        if (response.status === 401 && authToken) {
            const refreshed = await attemptTokenRefresh();
            if (refreshed) {
                // Retry request with new token
                options.headers['Authorization'] = `Bearer ${authToken}`;
                return await fetch(url, options);
            } else {
                // Refresh failed, logout user
                logout();
                throw new Error('Session expired');
            }
        }
        
        return response;
    } catch (error) {
        console.error('Secure request failed:', error);
        throw error;
    }
}

async function attemptTokenRefresh() {
    // Attempt to refresh access token
    if (!refreshToken) {
        return false;
    }
    
    try {
        const response = await fetch('/api/refresh-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_token: refreshToken
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('authToken', authToken);
            return true;
        }
    } catch (error) {
        console.error('Token refresh failed:', error);
    }
    
    return false;
}

// Utility functions
function showError(message) {
    const errorEl = document.getElementById('error-message');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.remove('hidden');
        setTimeout(() => errorEl.classList.add('hidden'), 5000);
    }
}

function showSuccess(message) {
    const successEl = document.getElementById('success-message');
    if (successEl) {
        successEl.textContent = message;
        successEl.classList.remove('hidden');
        setTimeout(() => successEl.classList.add('hidden'), 5000);
    }
}

function clearMessages() {
    const errorEl = document.getElementById('error-message');
    const successEl = document.getElementById('success-message');
    if (errorEl) errorEl.classList.add('hidden');
    if (successEl) successEl.classList.add('hidden');
}

// Authentication functions
function toggleAuth() {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    if (loginForm && registerForm) {
        loginForm.classList.toggle('hidden');
        registerForm.classList.toggle('hidden');
        clearMessages();
    }
}

async function register() {
    // Check if registration is enabled
    if (!isFeatureEnabled('user_registration')) {
        showError('Registration is currently disabled');
        return;
    }
    
    const name = document.getElementById('register-name').value;
    const password = document.getElementById('register-password').value;
    
    if (!name || !password) {
        showError('Please fill in all fields');
        return;
    }
    
    // Get password requirements from config or use defaults
    const minLength = appConfig?.validation?.password_min_length || 4;
    const maxLength = appConfig?.validation?.password_max_length || 128;
    
    if (password.length < minLength) {
        showError(`Password must be at least ${minLength} characters long`);
        return;
    }
    
    if (password.length > maxLength) {
        showError(`Password must be less than ${maxLength} characters long`);
        return;
    }
    
    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, password})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(`Registration successful! Your User ID is: ${data.user_id}`);
            // Clear form
            document.getElementById('register-name').value = '';
            document.getElementById('register-password').value = '';
            // Switch to login and prefill user ID
            setTimeout(() => {
                toggleAuth();
                document.getElementById('login-userid').value = data.user_id;
            }, 2000);
        } else {
            showError(data.detail || 'Registration failed');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function login() {
    const user_id = document.getElementById('login-userid').value;
    const password = document.getElementById('login-password').value;
    
    // Validate inputs
    const userIdValidation = validateUserInput(user_id, 32);
    const passwordValidation = validateUserInput(password, 128);
    
    if (!userIdValidation.valid) {
        showError('Invalid User ID: ' + userIdValidation.error);
        return;
    }
    
    if (!passwordValidation.valid) {
        showError('Invalid password: ' + passwordValidation.error);
        return;
    }
    
    if (!validateId(user_id.trim())) {
        showError('Invalid User ID format');
        return;
    }
    
    try {
        // Login doesn't require CSRF token initially
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: userIdValidation.value, 
                password: passwordValidation.value
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Store enhanced JWT tokens
            authToken = data.access_token;
            refreshToken = data.refresh_token;
            currentUser = data.user;
            
            // Validate tokens before storing
            if (!authToken || !currentUser) {
                showError('Invalid response from server');
                return;
            }
            
            localStorage.setItem('authToken', authToken);
            localStorage.setItem('refreshToken', refreshToken);
            localStorage.setItem('currentUser', JSON.stringify(currentUser));
            
            // Clear form
            document.getElementById('login-userid').value = '';
            document.getElementById('login-password').value = '';
            
            // Get CSRF token after successful login
            try {
                await getCSRFToken();
            } catch (error) {
                console.warn('Failed to get CSRF token:', error);
                // Continue anyway - CSRF will be retrieved when needed
            }
            
            showSuccess('Login successful!');
            
            // Small delay to ensure UI state is stable
            setTimeout(() => {
                showDashboard();
                // Connect to global notification WebSocket
                connectGlobalNotifications();
            }, 100);
        } else {
            showError(data.detail || 'Login failed');
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Network error. Please try again.');
    }
}

function showDashboard() {
    const authPage = document.getElementById('auth-page');
    const dashboard = document.getElementById('dashboard');
    
    if (authPage && dashboard) {
        authPage.classList.add('hidden');
        dashboard.classList.remove('hidden');
        
        // Update user info
        const userNameEl = document.getElementById('user-name');
        const publicIdEl = document.getElementById('public-id');
        
        if (userNameEl) userNameEl.textContent = currentUser.name;
        if (publicIdEl) publicIdEl.textContent = currentUser.public_id;
        
        // Lazy load teams after a short delay to improve perceived performance
        setTimeout(() => {
            if (authToken && currentUser) {
                loadUserTeams();
            }
        }, 200);
    }
}

async function loadUserTeams() {
    if (!authToken) return;
    
    try {
        // Use direct fetch instead of cache for now to avoid connection issues
        const response = await makeSecureRequest('/api/user/teams', {
            method: 'GET'
        });
        
        if (response.ok) {
            const teams = await response.json();
            const teamsList = document.getElementById('teams-list');
            
            if (teamsList) {
                if (teams.length === 0) {
                    teamsList.innerHTML = '<p>No teams joined yet</p>';
                } else {
                    let teamsHtml = '';
                    
                    // Process teams in parallel using RequestCache to prevent duplicate requests
                    const teamPromises = teams.map(async (team) => {
                        try {
                            const result = await window.requestCache.getPendingRequests(team.team_id, authToken);
                            return { ...team, isAdmin: result.isAdmin, requests: result.requests || [] };
                        } catch (error) {
                            return { ...team, isAdmin: false, requests: [] };
                        }
                    });
                    
                    const teamsWithPending = await Promise.all(teamPromises);
                    
                    for (const team of teamsWithPending) {
                        teamsHtml += `
                            <div class="team-item">
                                <div class="team-info">
                                    <div class="team-name">${escapeHtml(team.name)}</div>
                                    <div class="team-id-container">
                                        <span class="team-id">ID: ${escapeHtml(team.team_id)}</span>
                                        <button class="copy-btn" onclick="copyToClipboard('${escapeHtml(team.team_id)}', this)" title="Copy Team ID">📋</button>
                                    </div>
                                    ${team.requests.length > 0 ? `<div class="pending-requests">${team.requests.length} pending request(s)</div>` : ''}
                                </div>
                                <div class="team-actions">
                                    <button class="btn" onclick="openTeamChat('${escapeHtml(team.team_id)}', '${escapeHtml(team.name)}')">Open</button>
                                    ${team.requests.length > 0 ? `<button class="btn btn-secondary" onclick="showTeamRequests('${escapeHtml(team.team_id)}', '${escapeHtml(team.name)}')">Manage</button>` : ''}
                                    ${team.isAdmin ? `<button class="btn" style="background: #dc3545;" onclick="confirmDeleteTeam('${escapeHtml(team.team_id)}', '${escapeHtml(team.name)}')">Delete Team</button>` : `<button class="btn" style="background: #fd7e14;" onclick="confirmLeaveTeam('${escapeHtml(team.team_id)}', '${escapeHtml(team.name)}')">Leave Team</button>`}
                                </div>
                            </div>
                        `;
                    }
                    
                    teamsList.innerHTML = teamsHtml;
                }
            }
        }
    } catch (error) {
        console.error('Error loading teams:', error);
    }
}

async function confirmDeleteTeam(teamId, teamName) {
    if (confirm(`Are you sure you want to delete team "${teamName}"? This action cannot be undone and will remove the team for all members.`)) {
        await deleteTeam(teamId);
    }
}

async function deleteTeam(teamId) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}`, {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            // Cache invalidated - reload teams
            loadUserTeams(); // Refresh teams list
        } else {
            showError(data.detail || 'Failed to delete team');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function confirmLeaveTeam(teamId, teamName) {
    if (confirm(`Are you sure you want to leave team "${teamName}"? You'll need to be re-invited to rejoin.`)) {
        await leaveTeam(teamId);
    }
}

async function leaveTeam(teamId) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/leave`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            // Cache invalidated - reload teams
            loadUserTeams(); // Refresh teams list
        } else {
            showError(data.detail || 'Failed to leave team');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function copyToClipboard(text, buttonElement) {
    try {
        await navigator.clipboard.writeText(text);
        
        // Visual feedback
        const originalText = buttonElement.textContent;
        buttonElement.textContent = '✓';
        buttonElement.classList.add('copied');
        
        // Reset after 2 seconds
        setTimeout(() => {
            buttonElement.textContent = originalText;
            buttonElement.classList.remove('copied');
        }, 2000);
        
        // Show success message
        showSuccess('ID copied to clipboard!');
    } catch (error) {
        console.error('Failed to copy to clipboard:', error);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showSuccess('ID copied to clipboard!');
            
            // Visual feedback
            const originalText = buttonElement.textContent;
            buttonElement.textContent = '✓';
            buttonElement.classList.add('copied');
            
            setTimeout(() => {
                buttonElement.textContent = originalText;
                buttonElement.classList.remove('copied');
            }, 2000);
        } catch (fallbackError) {
            showError('Could not copy to clipboard');
        }
        document.body.removeChild(textArea);
    }
}

async function logout() {
    // Call logout endpoint to blacklist token
    if (authToken) {
        try {
            await makeSecureRequest('/api/logout', {
                method: 'POST'
            });
        } catch (error) {
            console.error('Logout API call failed:', error);
            // Continue with local logout even if API call fails
        }
    }
    
    // Clear all authentication data
    authToken = null;
    refreshToken = null;
    currentUser = null;
    csrfToken = null;
    
    localStorage.removeItem('authToken');
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('currentUser');
    
    // Disconnect global notifications
    disconnectGlobalNotifications();
    
    // Clear any cached requests
    // Cache cleared
    
    const authPage = document.getElementById('auth-page');
    const dashboard = document.getElementById('dashboard');
    
    if (authPage && dashboard) {
        authPage.classList.remove('hidden');
        dashboard.classList.add('hidden');
    }
    
    clearMessages();
    showSuccess('Logged out successfully');
}

function confirmDeleteAccount() {
    if (confirm('Are you sure you want to delete your account? This action cannot be undone and will delete all your teams and meetings.')) {
        deleteAccount();
    }
}

async function deleteAccount() {
    if (!authToken) return;
    
    try {
        const response = await fetch('/api/user/delete', {
            method: 'DELETE',
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        if (response.ok) {
            showSuccess('Account deleted successfully');
            setTimeout(logout, 2000);
        } else {
            const data = await response.json();
            showError(data.detail || 'Failed to delete account');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

// Modal functions
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('hidden');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
    }
    
    // Clear form inputs
    const inputs = modal.querySelectorAll('input[type="text"]');
    inputs.forEach(input => input.value = '');
}

function showCreateTeamModal() {
    showModal('create-team-modal');
}

function showJoinTeamModal() {
    showModal('join-team-modal');
}

function showCreateMeetingModal() {
    showModal('create-meeting-modal');
}

function showJoinMeetingModal() {
    showModal('join-meeting-modal');
}

// Team functions
async function createTeam() {
    const name = document.getElementById('team-name').value.trim();
    
    if (!name) {
        showError('Please enter a team name');
        return;
    }
    
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch('/api/teams/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({name})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(`Team created! Team ID: ${data.team_id}`);
            closeModal('create-team-modal');
            loadUserTeams();
        } else {
            showError(data.detail || 'Failed to create team');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function joinTeam() {
    const team_id = document.getElementById('join-team-id').value.trim();
    
    if (!team_id) {
        showError('Please enter a team ID');
        return;
    }
    
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch('/api/teams/join', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({team_id})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess('Join request sent! Waiting for admin approval.');
            closeModal('join-team-modal');
        } else {
            showError(data.detail || 'Failed to join team');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

// Meeting functions
async function createMeeting() {
    const name = document.getElementById('meeting-name').value.trim();
    
    if (!name) {
        showError('Please enter a meeting name');
        return;
    }
    
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch('/api/meetings/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({name})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(`Meeting created! Meeting ID: ${data.meeting_id}`);
            closeModal('create-meeting-modal');
            // Automatically open the meeting
            setTimeout(() => {
                openMeeting(data.meeting_id, name);
            }, 1000);
        } else {
            showError(data.detail || 'Failed to create meeting');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function joinMeeting() {
    const meeting_id = document.getElementById('join-meeting-id').value.trim();
    
    if (!meeting_id) {
        showError('Please enter a meeting ID');
        return;
    }
    
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch('/api/meetings/join', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({meeting_id})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            closeModal('join-meeting-modal');
            
            // Always open meeting window immediately
            // The meeting window will handle showing pending/approved/rejected status
            showSuccess('Opening meeting...');
            setTimeout(() => {
                openMeeting(meeting_id, 'Meeting');
            }, 500);
            
        } else {
            showError(data.detail || 'Failed to join meeting');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

// Team management functions
async function showTeamRequests(teamId, teamName) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    try {
        const response = await fetch(`/api/teams/${teamId}/pending`, {
            headers: {'Authorization': `Bearer ${authToken}`}
        });
        
        if (response.ok) {
            const requests = await response.json();
            
            if (requests.length === 0) {
                showSuccess('No pending requests');
                return;
            }
            
            let requestsHtml = `
                <h3>Pending Requests for ${escapeHtml(teamName)}</h3>
                <div style="max-height: 300px; overflow-y: auto;">
            `;
            
            requests.forEach(request => {
                requestsHtml += `
                    <div style="border: 1px solid #ddd; padding: 10px; margin: 10px 0; border-radius: 4px;">
                        <strong>${escapeHtml(request.name)}</strong> (${escapeHtml(request.public_id)})
                        <br><small>Requested: ${new Date(request.requested_at).toLocaleString()}</small>
                        <br>
                        <button onclick="approveTeamRequest('${teamId}', '${request.user_id}', 'approve')" style="background: #28a745; color: white; border: none; padding: 5px 10px; margin: 5px; border-radius: 3px; cursor: pointer;">Approve</button>
                        <button onclick="approveTeamRequest('${teamId}', '${request.user_id}', 'reject')" style="background: #dc3545; color: white; border: none; padding: 5px 10px; margin: 5px; border-radius: 3px; cursor: pointer;">Reject</button>
                    </div>
                `;
            });
            
            requestsHtml += '</div>';
            
            // Create and show modal
            showCustomModal('Team Requests', requestsHtml);
            
        } else {
            showError('Failed to load pending requests');
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

async function approveTeamRequest(teamId, userId, action) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    // Validate inputs
    if (!validateId(teamId) || !validateId(userId)) {
        showError('Invalid team or user ID');
        return;
    }
    
    const allowedActions = ['approve', 'reject', 'remove', 'kick', 'ban'];
    if (!allowedActions.includes(action)) {
        showError('Invalid action');
        return;
    }
    
    try {
        const response = await makeSecureRequest(`/api/teams/${teamId}/approve`, {
            method: 'POST',
            body: JSON.stringify({
                target_user_id: userId,
                action: action
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showSuccess(data.message);
            closeCustomModal();
            // Cache invalidated - reload teams
            loadUserTeams(); // Refresh teams list
        } else {
            showError(data.detail || `Failed to ${action} request`);
        }
    } catch (error) {
        showError('Network error. Please try again.');
    }
}

function showCustomModal(title, content) {
    // Remove existing custom modal
    const existingModal = document.getElementById('custom-modal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Create new modal
    const modal = document.createElement('div');
    modal.id = 'custom-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <button class="close-btn" onclick="closeCustomModal()">&times;</button>
            <h2>${title}</h2>
            <div>${content}</div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeCustomModal() {
    const modal = document.getElementById('custom-modal');
    if (modal) {
        modal.remove();
    }
}
function openTeamChat(teamId, teamName) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    // Open team chat in new window/tab
    const url = `/team/${encodeURIComponent(teamId)}`;
    window.open(url, '_blank', 'width=1200,height=800');
}

function openMeeting(meetingId, meetingName) {
    if (!authToken) {
        showError('Please login first');
        return;
    }
    
    // Open meeting in new window/tab
    const url = `/meeting/${encodeURIComponent(meetingId)}`;
    window.open(url, '_blank', 'width=1400,height=900');
}

// Utility function to escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// Keyboard event handlers
document.addEventListener('keydown', function(event) {
    // Handle Enter key for forms
    if (event.key === 'Enter') {
        const activeElement = document.activeElement;
        
        if (activeElement && activeElement.tagName === 'INPUT') {
            const form = activeElement.closest('form');
            if (form) {
                // Prevent default form submission
                event.preventDefault();
                
                // Find the submit button and click it
                if (form.id === 'login-form') {
                    login();
                } else if (form.id === 'register-form') {
                    register();
                }
            }
        }
    }
    
    // Handle Escape key for modals
    if (event.key === 'Escape') {
        const modals = document.querySelectorAll('.modal:not(.hidden)');
        modals.forEach(modal => {
            modal.classList.add('hidden');
        });
    }
});

// Check for existing session on load
window.addEventListener('load', async function() {
    const storedToken = localStorage.getItem('authToken');
    const storedRefreshToken = localStorage.getItem('refreshToken');
    const storedUser = localStorage.getItem('currentUser');
    
    if (storedToken && storedUser) {
        try {
            // Validate stored data
            const parsedUser = JSON.parse(storedUser);
            if (!parsedUser || !parsedUser.user_id) {
                throw new Error('Invalid stored user data');
            }
            
            authToken = storedToken;
            refreshToken = storedRefreshToken;
            currentUser = parsedUser;
            
            // Get CSRF token for the session
            try {
                await getCSRFToken();
            } catch (csrfError) {
                console.warn('Failed to get CSRF token during session restore:', csrfError);
            }
            
            showDashboard();
        } catch (error) {
            console.error('Session restoration error:', error);
            // Clear invalid session data
            authToken = null;
            refreshToken = null;
            currentUser = null;
            localStorage.removeItem('authToken');
            localStorage.removeItem('refreshToken');
            localStorage.removeItem('currentUser');
        }
    } else {
        // Get CSRF token for login form
        try {
            await getCSRFToken();
        } catch (csrfError) {
            console.warn('Failed to get CSRF token for login form:', csrfError);
        }
    }
    
    // Load application configuration
    await loadAppConfig();
});

// Handle page visibility change
document.addEventListener('visibilitychange', function() {
    if (!document.hidden && authToken) {
        // Refresh teams when page becomes visible
        loadUserTeams();
    }
});

// =============================================================================
// SECRET ID FUNCTIONALITY
// =============================================================================

let secretIdCountdown = null;

function showSecretIdModal() {
    document.getElementById('secret-id-modal').classList.remove('hidden');
    // Clear any previous results
    document.getElementById('secret-id-result').classList.add('hidden');
    document.getElementById('secret-password').value = '';
    document.getElementById('secret-password').focus();
}

function closeSecretIdModal() {
    document.getElementById('secret-id-modal').classList.add('hidden');
    // Clear sensitive data
    document.getElementById('secret-password').value = '';
    document.getElementById('secret-id-value').value = '';
    if (secretIdCountdown) {
        clearInterval(secretIdCountdown);
        secretIdCountdown = null;
    }
}

async function retrieveSecretId() {
    const password = document.getElementById('secret-password').value;
    if (!password.trim()) {
        showError('Please enter your password');
        return;
    }

    try {
        // Get a fresh CSRF token specifically for this request (CSRF tokens are single-use)
        csrfToken = null; // Clear any existing token
        await getCSRFToken();
        
        // Generate a cryptographically secure nonce for anti-replay protection
        const nonce = crypto.getRandomValues(new Uint8Array(16));
        const nonceHex = Array.from(nonce).map(b => b.toString(16).padStart(2, '0')).join('');

        const response = await makeSecureRequest('/api/user/secret-id', {
            method: 'POST',
            body: JSON.stringify({
                password: password,
                nonce: nonceHex
            })
        });

        const data = await response.json();

        if (response.ok) {
            // Hide form and show result
            document.getElementById('secret-id-form').style.display = 'none';
            document.getElementById('secret-id-result').classList.remove('hidden');
            document.getElementById('secret-id-value').value = data.secret_id;

            // Clear password immediately
            document.getElementById('secret-password').value = '';

            // Start countdown timer
            startSecretIdCountdown();
            
            showSuccess('Login ID retrieved successfully');
        } else {
            showError(data.detail || 'Failed to retrieve login ID');
        }
    } catch (error) {
        console.error('Error retrieving secret ID:', error);
        showError('Network error. Please try again.');
    }
}

function copySecretId() {
    const secretInput = document.getElementById('secret-id-value');
    secretInput.select();
    secretInput.setSelectionRange(0, 99999); // For mobile devices
    
    try {
        document.execCommand('copy');
        const copyBtn = document.querySelector('.copy-btn');
        const originalText = copyBtn.textContent;
        copyBtn.textContent = '✅ Copied!';
        copyBtn.style.background = '#28a745';
        
        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.style.background = '#007bff';
        }, 2000);
    } catch (err) {
        console.error('Failed to copy text: ', err);
        showError('Failed to copy to clipboard');
    }
}

function startSecretIdCountdown() {
    let timeLeft = 10;
    const countdownElement = document.getElementById('countdown');
    
    secretIdCountdown = setInterval(() => {
        countdownElement.textContent = timeLeft;
        timeLeft--;
        
        if (timeLeft < 0) {
            closeSecretIdModal();
        }
    }, 1000);
}

// Initialize app on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check for existing authentication
    checkExistingAuth();
    
    // Handle Enter key in secret password field
    const secretPasswordField = document.getElementById('secret-password');
    if (secretPasswordField) {
        secretPasswordField.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                retrieveSecretId();
            }
        });
    }
});

async function checkExistingAuth() {
    // Check localStorage for existing tokens
    const storedAuthToken = localStorage.getItem('authToken');
    const storedRefreshToken = localStorage.getItem('refreshToken');
    const storedUser = localStorage.getItem('currentUser');
    
    if (storedAuthToken && storedUser) {
        // Restore tokens and user data
        authToken = storedAuthToken;
        refreshToken = storedRefreshToken;
        currentUser = JSON.parse(storedUser);
        
        // Show dashboard - let natural API calls handle token validation
        showDashboard();
        // Connect to global notifications
        connectGlobalNotifications();
    } else {
        // No valid stored session, show auth page
        showAuthPage();
    }
}

function showAuthPage() {
    const authPage = document.getElementById('auth-page');
    const dashboard = document.getElementById('dashboard');
    
    if (authPage && dashboard) {
        authPage.classList.remove('hidden');
        dashboard.classList.add('hidden');
    }
}

// =============================================================================
// GLOBAL NOTIFICATION WEBSOCKET
// =============================================================================

let globalNotificationWs = null;

function connectGlobalNotifications() {
    if (!authToken || !currentUser) return;
    
    // Disconnect existing connection
    if (globalNotificationWs) {
        globalNotificationWs.close();
        globalNotificationWs = null;
    }
    
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/user/${currentUser.user_id}?token=${authToken}`;
        
        globalNotificationWs = new WebSocket(wsUrl);
        
        globalNotificationWs.onopen = function() {
            console.log('Global notifications connected');
        };
        
        globalNotificationWs.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleGlobalNotification(data);
            } catch (error) {
                console.error('Error parsing global notification:', error);
            }
        };
        
        globalNotificationWs.onclose = function() {
            console.log('Global notifications disconnected');
            // Reconnect after delay if still authenticated
            if (authToken && currentUser) {
                setTimeout(connectGlobalNotifications, 5000);
            }
        };
        
        globalNotificationWs.onerror = function(error) {
            console.error('Global notification WebSocket error:', error);
        };
        
    } catch (error) {
        console.error('Error creating global notification WebSocket:', error);
    }
}

function handleGlobalNotification(data) {
    // Only handle notification types relevant to global notifications
    // Filter out room-specific messages like participant_update, online_users_update, system
    const globalNotificationTypes = [
        'team_join_request',
        'team_request_approved', 
        'team_request_rejected',
        'pending_request_update',
        'team_unbanned',
        'team_deleted'
    ];
    
    if (!globalNotificationTypes.includes(data.type)) {
        // Ignore room-specific messages
        return;
    }
    
    switch (data.type) {
        case 'team_join_request':
            showNotification(`New team join request from ${data.requester?.name}`, 'info');
            // Refresh teams list to show updated pending counts
            loadUserTeams();
            break;
        case 'team_request_approved':
            showNotification('Your team join request was approved!', 'success');
            loadUserTeams();
            break;
        case 'team_request_rejected':
            showNotification('Your team join request was rejected', 'warning');
            loadUserTeams();
            break;
        case 'team_unbanned':
            showNotification('You have been unbanned from a team', 'success');
            loadUserTeams();
            break;
        case 'pending_request_update':
            // Refresh teams to show updated pending requests
            loadUserTeams();
            break;
        case 'team_deleted':
            showNotification('A team you were part of has been deleted', 'warning');
            loadUserTeams();
            break;
        default:
            console.log('Unhandled global notification type:', data.type);
    }
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        margin: 5px 0;
        border-radius: 5px;
        color: white;
        font-weight: bold;
        z-index: 10000;
        max-width: 300px;
        word-wrap: break-word;
        animation: slideIn 0.3s ease-out;
    `;
    
    // Set background color based on type
    switch (type) {
        case 'success':
            notification.style.backgroundColor = '#28a745';
            break;
        case 'warning':
            notification.style.backgroundColor = '#ffc107';
            notification.style.color = '#212529';
            break;
        case 'error':
            notification.style.backgroundColor = '#dc3545';
            break;
        default:
            notification.style.backgroundColor = '#007bff';
    }
    
    notification.textContent = message;
    
    // Add close button
    const closeBtn = document.createElement('span');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cssText = `
        float: right;
        margin-left: 15px;
        cursor: pointer;
        font-size: 20px;
        line-height: 1;
    `;
    closeBtn.onclick = () => notification.remove();
    notification.appendChild(closeBtn);
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Add CSS for notification animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
`;
document.head.appendChild(style);

// Disconnect global notifications on logout
function disconnectGlobalNotifications() {
    if (globalNotificationWs) {
        globalNotificationWs.close();
        globalNotificationWs = null;
    }
}