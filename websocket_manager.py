# Enhanced websocket_manager.py - WebSocket Connection Manager with WebRTC Support

from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import logging
from typing import Dict, Set, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class UserConnection:
    """Represents a user connection with metadata"""
    websocket: WebSocket
    user_id: str
    user_info: dict
    room_id: str
    connected_at: datetime
    last_ping: datetime
    is_active: bool = True

@dataclass
class RoomInfo:
    """Room information and statistics"""
    room_id: str
    room_type: str  # 'team' or 'meeting'
    created_at: datetime
    participant_count: int
    max_participants: int = 50  # Configurable limit
    is_active: bool = True

class ConnectionManager:
    def __init__(self):
        # Core connection tracking
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.user_connections: Dict[str, UserConnection] = {}
        self.room_participants: Dict[str, Dict[str, dict]] = defaultdict(dict)
        
        # Online user tracking by room
        self.online_users: Dict[str, Set[str]] = defaultdict(set)  # room_id -> set of user_ids
        
        # WebRTC signaling support
        self.webrtc_sessions: Dict[str, Set[str]] = defaultdict(set)  # room_id -> set of user_ids
        self.peer_connections: Dict[str, Dict[str, str]] = defaultdict(dict)  # room_id -> {user1: user2}
        
        # Room management
        self.room_info: Dict[str, RoomInfo] = {}
        
        # Connection quality tracking
        self.connection_stats: Dict[str, dict] = defaultdict(lambda: {
            'messages_sent': 0,
            'messages_received': 0,
            'last_activity': datetime.now(),
            'ping_times': [],
            'errors': 0
        })
        
        # Rate limiting per user
        self.user_message_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.MAX_MESSAGES_PER_MINUTE = 60
        
        logger.info("Enhanced ConnectionManager initialized")
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: str, user_info: dict = None):
        """Connect user to a room with enhanced tracking"""
        try:
            await websocket.accept()
            
            # Create user connection record
            connection = UserConnection(
                websocket=websocket,
                user_id=user_id,
                user_info=user_info or {},
                room_id=room_id,
                connected_at=datetime.now(),
                last_ping=datetime.now()
            )
            
            # Check room participant limit
            if len(self.room_participants[room_id]) >= 50:  # Max 50 participants
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Room is full. Maximum 50 participants allowed.",
                    "timestamp": datetime.now().isoformat()
                }))
                await websocket.close(code=1013)  # Try again later
                return False
            
            # Add to connections
            self.active_connections[room_id].add(websocket)
            self.user_connections[user_id] = connection
            
            # Add to room participants
            if user_info:
                self.room_participants[room_id][user_id] = user_info
            
            # Track online user
            self.online_users[room_id].add(user_id)
            
            # Update room info
            if room_id not in self.room_info:
                self.room_info[room_id] = RoomInfo(
                    room_id=room_id,
                    room_type="meeting",  # Default, can be updated
                    created_at=datetime.now(),
                    participant_count=0
                )
            
            self.room_info[room_id].participant_count = len(self.room_participants[room_id])
            
            # Add to WebRTC tracking
            self.webrtc_sessions[room_id].add(user_id)
            
            # Initialize connection stats
            self.connection_stats[user_id]['last_activity'] = datetime.now()
            
            # Notify room about participant update
            await self.broadcast_participant_update(room_id)
            
            # Notify room about online users update
            await self.broadcast_online_users_update(room_id)
            
            logger.info(f"User {user_id} connected to room {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting user {user_id} to room {room_id}: {e}")
            return False
    
    def disconnect(self, websocket: WebSocket, room_id: str, user_id: str):
        """Disconnect user from room with cleanup"""
        try:
            # Remove from active connections
            if room_id in self.active_connections:
                self.active_connections[room_id].discard(websocket)
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]
            
            # Remove user connection
            if user_id in self.user_connections:
                connection = self.user_connections[user_id]
                connection.is_active = False
                del self.user_connections[user_id]
            
            # Remove from room participants
            user_info = None
            if room_id in self.room_participants:
                user_info = self.room_participants[room_id].pop(user_id, None)
                if not self.room_participants[room_id]:
                    del self.room_participants[room_id]
            
            # Remove from online users
            if room_id in self.online_users:
                self.online_users[room_id].discard(user_id)
                if not self.online_users[room_id]:
                    del self.online_users[room_id]
            
            # Update room info
            if room_id in self.room_info:
                self.room_info[room_id].participant_count = len(self.room_participants.get(room_id, {}))
                if self.room_info[room_id].participant_count == 0:
                    self.room_info[room_id].is_active = False
            
            # Clean up WebRTC tracking
            if room_id in self.webrtc_sessions:
                self.webrtc_sessions[room_id].discard(user_id)
                if not self.webrtc_sessions[room_id]:
                    del self.webrtc_sessions[room_id]
            
            # Clean up peer connections
            if room_id in self.peer_connections:
                # Remove any peer connections involving this user
                to_remove = []
                for peer_pair, connection_id in self.peer_connections[room_id].items():
                    if user_id in peer_pair.split('-'):
                        to_remove.append(peer_pair)
                
                for peer_pair in to_remove:
                    del self.peer_connections[room_id][peer_pair]
            
            # Notify room about participant leaving if user_info exists
            if user_info:
                asyncio.create_task(self.broadcast_user_left(room_id, user_info))
            
            # Notify room about participant count update
            asyncio.create_task(self.broadcast_participant_update(room_id))
            
            # Notify room about online users update
            asyncio.create_task(self.broadcast_online_users_update(room_id))
            
            logger.info(f"User {user_id} disconnected from room {room_id}")
            
        except Exception as e:
            logger.error(f"Error disconnecting user {user_id} from room {room_id}: {e}")
    
    async def send_to_room(self, room_id: str, message: dict, exclude_user: Optional[str] = None):
        """Send message to all connections in a room with error handling"""
        if room_id not in self.active_connections:
            return 0
        
        # Add server timestamp and room info
        message.update({
            "server_timestamp": datetime.now().isoformat(),
            "room_id": room_id
        })
        
        message_str = json.dumps(message)
        sent_count = 0
        disconnected = []
        
        for connection in self.active_connections[room_id].copy():
            try:
                # Skip if excluding specific user
                user_connection = None
                for user_id, conn in self.user_connections.items():
                    if conn.websocket == connection:
                        user_connection = conn
                        break
                
                if exclude_user and user_connection and user_connection.user_id == exclude_user:
                    continue
                
                await connection.send_text(message_str)
                sent_count += 1
                
                # Update stats
                if user_connection:
                    self.connection_stats[user_connection.user_id]['messages_sent'] += 1
                    self.connection_stats[user_connection.user_id]['last_activity'] = datetime.now()
                
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                logger.error(f"Error sending message to connection in room {room_id}: {e}")
                disconnected.append(connection)
                
                # Update error stats
                if user_connection:
                    self.connection_stats[user_connection.user_id]['errors'] += 1
        
        # Clean up disconnected connections
        for conn in disconnected:
            self.active_connections[room_id].discard(conn)
        
        return sent_count
    
    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send message to specific user with delivery confirmation"""
        if user_id not in self.user_connections:
            # Check if this is just a stale reference (reduce log noise)
            if message.get('type') in ['webrtc_offer', 'webrtc_answer', 'webrtc_ice_candidate']:
                logger.debug(f"User {user_id} not found for WebRTC message (likely disconnected)")
            else:
                logger.warning(f"User {user_id} not found for direct message")
            return False
        
        connection = self.user_connections[user_id]
        if not connection.is_active:
            logger.warning(f"User {user_id} connection is inactive")
            return False
        
        try:
            # Add server timestamp and direct message flag
            message.update({
                "server_timestamp": datetime.now().isoformat(),
                "direct_message": True,
                "target_user": user_id
            })
            
            await connection.websocket.send_text(json.dumps(message))
            
            # Update stats
            self.connection_stats[user_id]['messages_sent'] += 1
            self.connection_stats[user_id]['last_activity'] = datetime.now()
            
            return True
            
        except (WebSocketDisconnect, Exception) as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            # Mark connection as inactive
            connection.is_active = False
            self.connection_stats[user_id]['errors'] += 1
            return False
    
    async def broadcast_participant_update(self, room_id: str):
        """Broadcast participant count and list update to room"""
        if room_id not in self.room_participants:
            return
        
        participants_list = list(self.room_participants[room_id].values())
        participant_count = len(participants_list)
        
        await self.send_to_room(room_id, {
            "type": "participant_update",
            "count": participant_count,
            "participants": participants_list,
            "room_stats": {
                "active_connections": len(self.active_connections.get(room_id, [])),
                "webrtc_sessions": len(self.webrtc_sessions.get(room_id, set()))
            }
        })
    
    async def broadcast_user_joined(self, room_id: str, user_info: dict):
        """Broadcast that a user joined the room"""
        # First, send existing participants to the new user
        await self.send_existing_participants_to_user(room_id, user_info.get("user_id"))
        
        # Then broadcast the new user to existing participants
        await self.send_to_room(room_id, {
            "type": "user_joined",
            "user": user_info,
            "timestamp": datetime.now().isoformat(),
            "room_participant_count": len(self.room_participants.get(room_id, {}))
        }, exclude_user=user_info.get("user_id"))
    
    async def send_existing_participants_to_user(self, room_id: str, user_id: str):
        """Send existing participants in the room to a newly joined user"""
        if user_id not in self.user_connections:
            return
        
        room_participants = self.room_participants.get(room_id, {})
        for participant_id, participant_info in room_participants.items():
            if participant_id != user_id:  # Don't send the user to themselves
                try:
                    await self.send_to_user(user_id, {
                        "type": "user_joined",
                        "user": participant_info,
                        "timestamp": datetime.now().isoformat(),
                        "is_existing_participant": True
                    })
                except Exception as e:
                    logger.error(f"Error sending existing participant {participant_id} to {user_id}: {e}")
    
    async def broadcast_user_left(self, room_id: str, user_info: dict):
        """Broadcast that a user left the room"""
        await self.send_to_room(room_id, {
            "type": "user_left",
            "user": user_info,
            "timestamp": datetime.now().isoformat(),
            "room_participant_count": len(self.room_participants.get(room_id, {}))
        })
    
    async def broadcast_media_state(self, room_id: str, user_info: dict, media_state: dict):
        """Broadcast user's media state change with WebRTC support"""
        await self.send_to_room(room_id, {
            "type": "media_state",
            "user": user_info,
            "mediaState": media_state,
            "timestamp": datetime.now().isoformat(),
            "webrtc_info": {
                "supports_video": media_state.get("video", False),
                "supports_audio": media_state.get("audio", False),
                "screen_sharing": media_state.get("screen", False)
            }
        }, exclude_user=user_info.get("user_id"))
    
    # WebRTC-specific methods
    async def handle_webrtc_offer(self, room_id: str, from_user_id: str, to_user_id: str, offer: dict):
        """Handle WebRTC offer signaling"""
        if to_user_id in self.user_connections:
            message = {
                "type": "webrtc_offer",
                "offer": offer,
                "fromUserId": from_user_id,
                "timestamp": datetime.now().isoformat()
            }
            
            success = await self.send_to_user(to_user_id, message)
            
            if success:
                # Track peer connection attempt
                peer_pair = f"{from_user_id}-{to_user_id}"
                self.peer_connections[room_id][peer_pair] = "negotiating"
                
            return success
        return False
    
    async def handle_webrtc_answer(self, room_id: str, from_user_id: str, to_user_id: str, answer: dict):
        """Handle WebRTC answer signaling"""
        if to_user_id in self.user_connections:
            message = {
                "type": "webrtc_answer",
                "answer": answer,
                "fromUserId": from_user_id,
                "timestamp": datetime.now().isoformat()
            }
            
            success = await self.send_to_user(to_user_id, message)
            
            if success:
                # Update peer connection status
                peer_pair = f"{to_user_id}-{from_user_id}"
                self.peer_connections[room_id][peer_pair] = "connected"
                
            return success
        return False
    
    async def handle_ice_candidate(self, room_id: str, from_user_id: str, to_user_id: str, candidate: dict):
        """Handle ICE candidate signaling"""
        if to_user_id in self.user_connections:
            message = {
                "type": "webrtc_ice_candidate",
                "candidate": candidate,
                "fromUserId": from_user_id,
                "timestamp": datetime.now().isoformat()
            }
            
            return await self.send_to_user(to_user_id, message)
        return False
    
    def get_room_participants(self, room_id: str) -> List[dict]:
        """Get list of participants in room"""
        return list(self.room_participants.get(room_id, {}).values())
    
    def get_participant_count(self, room_id: str) -> int:
        """Get number of participants in room"""
        return len(self.room_participants.get(room_id, {}))
    
    def is_user_in_room(self, user_id: str, room_id: str) -> bool:
        """Check if user is in specific room"""
        return user_id in self.room_participants.get(room_id, {})
    
    def get_user_rooms(self, user_id: str) -> List[str]:
        """Get all rooms a user is connected to"""
        rooms = []
        for room_id, participants in self.room_participants.items():
            if user_id in participants:
                rooms.append(room_id)
        return rooms
    
    def get_connection_stats(self, user_id: str) -> dict:
        """Get connection statistics for a user"""
        return self.connection_stats.get(user_id, {})
    
    def get_room_stats(self, room_id: str) -> dict:
        """Get room statistics"""
        return {
            "participant_count": len(self.room_participants.get(room_id, {})),
            "active_connections": len(self.active_connections.get(room_id, [])),
            "webrtc_sessions": len(self.webrtc_sessions.get(room_id, set())),
            "peer_connections": len(self.peer_connections.get(room_id, {})),
            "room_info": asdict(self.room_info.get(room_id)) if room_id in self.room_info else None
        }
    
    async def force_disconnect_user(self, user_id: str, reason: str = "Admin action"):
        """Force disconnect a specific user from all rooms"""
        try:
            if user_id in self.user_connections:
                connection = self.user_connections[user_id]
                
                # Send disconnect message to user before closing
                disconnect_message = {
                    "type": "force_disconnect",
                    "reason": reason,
                    "message": f"You have been disconnected: {reason}",
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    await connection.websocket.send_text(json.dumps(disconnect_message))
                    await asyncio.sleep(0.1)  # Give time for message to be sent
                except:
                    pass  # Connection might already be closed
                
                # Close the WebSocket connection
                try:
                    await connection.websocket.close(code=1008, reason=reason)
                except:
                    pass  # Connection might already be closed
                
                # Clean up from all rooms
                user_rooms = self.get_user_rooms(user_id)
                for room_id in user_rooms:
                    self.disconnect(connection.websocket, room_id, user_id)
                
                logger.info(f"Force disconnected user {user_id}: {reason}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error force disconnecting user {user_id}: {e}")
            return False
    
    def get_total_connections(self) -> int:
        """Get total number of active connections"""
        return len(self.user_connections)
    
    def get_active_rooms(self) -> List[str]:
        """Get list of active rooms"""
        return [room_id for room_id, info in self.room_info.items() if info.is_active]
    
    async def check_rate_limit(self, user_id: str) -> bool:
        """Check if user is within rate limits"""
        now = datetime.now()
        
        # Clean old messages (older than 1 minute)
        self.user_message_counts[user_id] = [
            timestamp for timestamp in self.user_message_counts[user_id]
            if (now - timestamp).total_seconds() < 60
        ]
        
        # Check limit
        if len(self.user_message_counts[user_id]) >= self.MAX_MESSAGES_PER_MINUTE:
            return False
        
        # Add current message
        self.user_message_counts[user_id].append(now)
        return True
    
    async def ping_user(self, user_id: str) -> bool:
        """Ping a specific user to check connection"""
        if user_id not in self.user_connections:
            return False
        
        connection = self.user_connections[user_id]
        
        try:
            ping_message = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            
            await connection.websocket.send_text(json.dumps(ping_message))
            connection.last_ping = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Error pinging user {user_id}: {e}")
            connection.is_active = False
            return False
    
    async def cleanup_disconnected(self):
        """Enhanced cleanup of disconnected connections"""
        try:
            current_time = datetime.now()
            disconnected_users = []
            
            # Check for inactive connections
            for user_id, connection in list(self.user_connections.items()):
                # Check if connection is stale (no activity for 5 minutes)
                if (current_time - connection.last_ping).total_seconds() > 300:
                    try:
                        # Try to ping the connection
                        if not await self.ping_user(user_id):
                            disconnected_users.append(user_id)
                    except:
                        disconnected_users.append(user_id)
            
            # Clean up disconnected users
            for user_id in disconnected_users:
                connection = self.user_connections.get(user_id)
                if connection:
                    self.disconnect(connection.websocket, connection.room_id, user_id)
            
            # Clean up empty rooms
            empty_rooms = []
            for room_id, connections in list(self.active_connections.items()):
                if not connections:
                    empty_rooms.append(room_id)
            
            for room_id in empty_rooms:
                del self.active_connections[room_id]
                if room_id in self.room_participants:
                    del self.room_participants[room_id]
                if room_id in self.webrtc_sessions:
                    del self.webrtc_sessions[room_id]
                if room_id in self.peer_connections:
                    del self.peer_connections[room_id]
                if room_id in self.room_info:
                    self.room_info[room_id].is_active = False
            
            # Clean up old connection stats
            old_users = []
            for user_id, stats in self.connection_stats.items():
                if (current_time - stats['last_activity']).total_seconds() > 3600:  # 1 hour
                    old_users.append(user_id)
            
            for user_id in old_users:
                del self.connection_stats[user_id]
                if user_id in self.user_message_counts:
                    del self.user_message_counts[user_id]
            
            if disconnected_users or empty_rooms or old_users:
                logger.info(f"Cleanup completed: {len(disconnected_users)} users, {len(empty_rooms)} rooms, {len(old_users)} old stats removed")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_online_users(self, room_id: str) -> Set[str]:
        """Get set of online user IDs for a room"""
        return self.online_users.get(room_id, set())
    
    def is_user_online(self, room_id: str, user_id: str) -> bool:
        """Check if a specific user is online in a room"""
        return user_id in self.online_users.get(room_id, set())
    
    async def broadcast_online_users_update(self, room_id: str):
        """Broadcast updated online users list to room participants"""
        try:
            online_user_ids = list(self.get_online_users(room_id))
            message = {
                "type": "online_users_update",
                "online_users": online_user_ids,
                "timestamp": datetime.now().isoformat()
            }
            await self.send_to_room(room_id, message)
            
        except Exception as e:
            logger.error(f"Error broadcasting online users update for room {room_id}: {e}")

async def periodic_cleanup():
    """Periodic cleanup function"""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        await manager.cleanup_disconnected()

# Global connection manager instance
manager = ConnectionManager()