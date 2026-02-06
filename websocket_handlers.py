# websocket_handlers.py - WebSocket & Real-time Communication - FIXED VERSION

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from datetime import datetime
import aiosqlite

from database import DATABASE_PATH
from utils import encrypt_data
from websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)
websocket_router = APIRouter()
manager = ConnectionManager()

# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@websocket_router.websocket("/ws/{room_type}/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_type: str, room_id: str, token: str):
    """WebSocket endpoint for real-time communication"""
    user_data = None
    try:
        # Verify token and get user data
        user_data = await authenticate_websocket_user(token)
        if not user_data:
            await websocket.close(code=1008)
            return
        
        # For meetings, verify the user is approved to join
        if room_type == "meeting":
            membership_status = await check_meeting_participation(user_data["user_id"], room_id)
            if membership_status != "approved":
                # Check if user is the creator
                is_creator = await check_meeting_creator(user_data["user_id"], room_id)
                if not is_creator:
                    await websocket.close(code=1008)
                    return
        
        # For teams, verify the user is approved member or team admin
        elif room_type == "team":
            membership_status = await check_team_membership(user_data["user_id"], room_id)
            if membership_status != "approved":
                # Check if user is the team admin
                is_admin = await check_team_admin(user_data["user_id"], room_id)
                if not is_admin:
                    await websocket.close(code=1008)
                    return
        
        # For user notifications, verify the user is connecting to their own channel
        elif room_type == "user":
            if room_id != user_data["user_id"]:
                logger.warning(f"User {user_data['user_id']} tried to connect to user channel {room_id}")
                await websocket.close(code=1008)
                return
        
        # Connect user to room
        await manager.connect(websocket, room_id, user_data["user_id"], user_data)
        
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"Connected to {room_type}: {room_id}",
            "user": {"name": "System", "public_id": "SYS"},
            "timestamp": datetime.now().isoformat()
        }))
        
        # Notify room about user joining
        await manager.broadcast_user_joined(room_id, user_data)
        
        # Main message loop
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Add user info and timestamp
            message_data["user"] = user_data
            message_data["timestamp"] = datetime.now().isoformat()
            message_data["fromUserId"] = user_data["user_id"]
            
            # Handle different message types
            await handle_websocket_message(room_id, room_type, message_data, user_data)
    
    except WebSocketDisconnect:
        if user_data:
            manager.disconnect(websocket, room_id, user_data["user_id"])
            await handle_user_disconnect(room_id, room_type, user_data)
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user_data:
            try:
                manager.disconnect(websocket, room_id, user_data["user_id"])
            except:
                pass

# =============================================================================
# MESSAGE HANDLERS
# =============================================================================

async def handle_websocket_message(room_id: str, room_type: str, message_data: dict, user_data: dict):
    """Handle different types of WebSocket messages"""
    message_type = message_data.get("type")
    
    if message_type in ["webrtc_offer", "webrtc_answer", "webrtc_ice_candidate"]:
        # Handle WebRTC signaling
        await handle_webrtc_signaling(room_id, message_data)
        
    elif message_type == "media_state":
        # Broadcast media state changes
        await manager.send_to_room(room_id, message_data)
        
    elif message_type in ["message", "chat"]:
        # Handle chat messages
        await handle_chat_message(room_id, room_type, message_data, user_data)
    
    else:
        # Default: broadcast to room
        await manager.send_to_room(room_id, message_data)

async def handle_webrtc_signaling(room_id: str, message_data: dict):
    """Handle WebRTC signaling messages"""
    target_user_id = message_data.get("targetUserId")
    
    if target_user_id:
        # Send to specific user
        await manager.send_to_user(target_user_id, message_data)
    else:
        # Broadcast to room (for offers to all participants)
        await manager.send_to_room(room_id, message_data)

async def handle_chat_message(room_id: str, room_type: str, message_data: dict, user_data: dict):
    """Handle chat messages"""
    original_message = message_data.get("message", "")
    
    # Broadcast to room first (real-time)
    await manager.send_to_room(room_id, message_data)
    
    # Store in database if team chat
    if room_type == "team":
        await store_team_message(room_id, user_data["user_id"], original_message, message_data.get("message_type", "text"))

async def handle_user_disconnect(room_id: str, room_type: str, user_data: dict):
    """Handle user disconnection"""
    if room_type == "meeting":
        await handle_meeting_disconnect(room_id, user_data)
    else:
        # Regular disconnect for teams
        await manager.broadcast_user_left(room_id, user_data)

async def handle_meeting_disconnect(room_id: str, user_data: dict):
    """Handle meeting-specific disconnection logic"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if this was a meeting creator leaving
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (room_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            
            if meeting_data and meeting_data[0] == user_data["user_id"]:
                # Creator left - end meeting for everyone
                await manager.send_to_room(room_id, {
                    "type": "meeting_ended",
                    "message": "Meeting has ended because the host left",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Delete the meeting from database
                await db.execute("DELETE FROM meeting_participants WHERE meeting_id = ?", (room_id,))
                await db.execute("DELETE FROM meetings WHERE meeting_id = ?", (room_id,))
                await db.commit()
                
                logger.info(f"Meeting ended due to creator disconnect: {room_id}")
            else:
                # Regular participant left
                await manager.broadcast_user_left(room_id, user_data)

# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def authenticate_websocket_user(token: str) -> dict:
    """Authenticate WebSocket user by JWT token"""
    try:
        from enhanced_auth import get_jwt_manager
        from database import DIContainer
        from config_manager import get_config
        
        # Get JWT manager
        jwt_manager = get_jwt_manager()
        config = get_config()
        
        # Create a minimal request object for token verification
        class MockRequest:
            def __init__(self):
                self.headers = {'user-agent': 'WebSocket'}
                self.client = None
        
        mock_request = MockRequest()
        
        # Verify JWT token
        payload = jwt_manager.verify_token(token, mock_request, "access")
        if not payload:
            logger.warning("Invalid JWT token for WebSocket")
            return None
        
        # Get user ID from payload
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("No user ID in JWT token")
            return None
        
        # Get user from database
        di_container = DIContainer(config.get_database_path())
        user_repo = di_container.get_user_repository()
        user = await user_repo.get_by_id(user_id)
        
        if user:
            return user.to_safe_dict()
        
        logger.warning(f"User not found in database: {user_id}")
        return None
        
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        return None

async def check_meeting_participation(user_id: str, meeting_id: str) -> str:
    """Check user's participation status in meeting"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?", 
                (meeting_id, user_id)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        logger.error(f"Error checking meeting participation: {e}")
        return None

async def check_meeting_creator(user_id: str, meeting_id: str) -> bool:
    """Check if user is creator of meeting"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", 
                (meeting_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return result and result[0] == user_id
    except Exception as e:
        logger.error(f"Error checking meeting creator: {e}")
        return False

async def check_team_membership(user_id: str, team_id: str) -> str:
    """Check user's membership status in team"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?", 
                (team_id, user_id)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        logger.error(f"Error checking team membership: {e}")
        return None

async def check_team_admin(user_id: str, team_id: str) -> bool:
    """Check if user is admin of team"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT admin_user_id FROM teams WHERE team_id = ?", 
                (team_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return result and result[0] == user_id
    except Exception as e:
        logger.error(f"Error checking team admin: {e}")
        return False

async def store_team_message(team_id: str, user_id: str, message: str, message_type: str = "text"):
    """Store team message in database"""
    try:
        encrypted_message = encrypt_data(message)
    except:
        encrypted_message = message  # Fallback if encryption fails
        
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO team_messages (team_id, user_id, message, message_type) VALUES (?, ?, ?, ?)",
                (team_id, user_id, encrypted_message, message_type)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Error storing team message: {e}")

# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def start_background_tasks():
    """Start background tasks for WebSocket management"""
    asyncio.create_task(periodic_cleanup())
    asyncio.create_task(connection_health_check())
    asyncio.create_task(pending_request_monitor())

async def periodic_cleanup():
    """Periodic cleanup of disconnected connections"""
    while True:
        try:
            await manager.cleanup_disconnected()
            logger.debug("WebSocket cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        await asyncio.sleep(300)  # Run every 5 minutes

async def connection_health_check():
    """Periodic health check for connections"""
    while True:
        try:
            # Get connection statistics
            total_connections = manager.get_total_connections()
            active_rooms = len(manager.get_active_rooms())
            
            if total_connections > 0:
                logger.info(f"Health check: {total_connections} connections, {active_rooms} active rooms")
        except Exception as e:
            logger.error(f"Health check error: {e}")
        
        await asyncio.sleep(600)  # Run every 10 minutes

async def pending_request_monitor():
    """Monitor for pending requests and notify meeting creators"""
    while True:
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                # Check for new pending meeting requests
                async with db.execute("""
                    SELECT m.meeting_id, m.creator_user_id, COUNT(mp.user_id) as pending_count
                    FROM meetings m
                    JOIN meeting_participants mp ON m.meeting_id = mp.meeting_id
                    WHERE mp.status = 'pending'
                    GROUP BY m.meeting_id, m.creator_user_id
                """) as cursor:
                    pending_meetings = await cursor.fetchall()
                    
                    for meeting_id, creator_id, pending_count in pending_meetings:
                        # Notify creator about pending requests
                        await notify_user(creator_id, "pending_requests_update", 
                                        f"You have {pending_count} pending join request(s)",
                                        meeting_id=meeting_id, count=pending_count)
                
        except Exception as e:
            logger.error(f"Pending request monitor error: {e}")
        
        await asyncio.sleep(30)  # Check every 30 seconds

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def broadcast_to_room(room_id: str, message_type: str, message: str, **kwargs):
    """Utility function to broadcast messages to a room"""
    message_data = {
        "type": message_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }
    await manager.send_to_room(room_id, message_data)

async def notify_user(user_id: str, message_type: str, message: str, **kwargs):
    """Utility function to notify a specific user"""
    message_data = {
        "type": message_type,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }
    
    # Send to user's personal notification channel (user/{user_id})
    await manager.send_to_room(user_id, message_data)
    
    # Also send using the old method for backward compatibility
    return await manager.send_to_user(user_id, message_data)

async def broadcast_meeting_deleted(meeting_id: str):
    """Broadcast meeting deletion to all participants"""
    await broadcast_to_room(meeting_id, "meeting_deleted", 
                          "This meeting has been deleted by the host")

async def broadcast_team_deleted(team_id: str):
    """Broadcast team deletion to all members"""
    await broadcast_to_room(team_id, "team_deleted", 
                          "This team has been deleted by the admin")

# =============================================================================
# ROOM MANAGEMENT
# =============================================================================

async def get_room_participants(room_id: str) -> list:
    """Get list of participants in a room"""
    return manager.get_room_participants(room_id)

async def get_room_stats(room_id: str) -> dict:
    """Get room statistics"""
    return manager.get_room_stats(room_id)

async def force_disconnect_user(user_id: str, reason: str = "Admin action"):
    """Force disconnect a user from all rooms"""
    user_rooms = manager.get_user_rooms(user_id)
    
    # Broadcast to all rooms the user was in
    for room_id in user_rooms:
        await broadcast_to_room(room_id, "user_kicked", f"User was disconnected: {reason}")
    
    # Actually force disconnect the user
    await manager.force_disconnect_user(user_id, reason)
    logger.info(f"Force disconnect completed for user {user_id}: {reason}")

async def broadcast_team_chat_cleared(team_id: str, admin_name: str):
    """Broadcast chat cleared notification to all team members"""
    try:
        message = {
            "type": "chat_cleared",
            "message": f"Chat history has been cleared by {admin_name}",
            "admin_name": admin_name,
            "timestamp": datetime.now().isoformat()
        }
        
        await manager.send_to_room(team_id, message)
        logger.info(f"Chat cleared notification sent to team {team_id}")
        
    except Exception as e:
        logger.error(f"Error broadcasting chat cleared for team {team_id}: {e}")

async def broadcast_member_action(team_id: str, action: str, target_user_id: str, admin_name: str):
    """Broadcast member management actions (kick/ban) to team"""
    try:
        # Get target user name
        target_user_name = "Unknown User"
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT name FROM users WHERE user_id = ?", (target_user_id,)
                ) as cursor:
                    user_data = await cursor.fetchone()
                    if user_data:
                        target_user_name = user_data[0]
        except Exception as e:
            logger.warning(f"Could not get target user name: {e}")
        
        message = {
            "type": "member_action",
            "action": action,
            "target_user": target_user_name,
            "target_user_id": target_user_id,
            "admin_name": admin_name,
            "message": f"{target_user_name} was {action}ed by {admin_name}",
            "timestamp": datetime.now().isoformat()
        }
        
        await manager.send_to_room(team_id, message)
        logger.info(f"Member {action} notification sent to team {team_id}")
        
    except Exception as e:
        logger.error(f"Error broadcasting member {action} for team {team_id}: {e}")

# Export the manager for use in other modules
__all__ = ["websocket_router", "manager", "broadcast_to_room", "notify_user", "get_room_participants", "get_room_stats", "broadcast_meeting_deleted", "broadcast_team_deleted", "broadcast_team_chat_cleared", "broadcast_member_action"]