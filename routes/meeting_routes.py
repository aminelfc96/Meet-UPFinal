# routes/meeting_routes.py - Meeting Management Routes - FIXED VERSION

from fastapi import APIRouter, HTTPException, Depends
import aiosqlite
import logging
import asyncio

from database import DIContainer
from models import MeetingCreate, MeetingJoinRequest, AdminAction
from utils import generate_id
from enhanced_auth import get_current_user, check_meeting_creator
from config_manager import get_config

config = get_config()
di_container = DIContainer(config.get_database_path())

logger = logging.getLogger(__name__)
router = APIRouter()

# Import WebSocket functions for notifications
try:
    from websocket_handlers import broadcast_meeting_deleted, notify_user, broadcast_to_room
except ImportError:
    logger.warning("WebSocket handlers not available for meeting notifications")
    async def broadcast_meeting_deleted(meeting_id: str): pass
    async def notify_user(user_id: str, message_type: str, message: str, **kwargs): pass
    async def broadcast_to_room(room_id: str, message_type: str, message: str, **kwargs): pass

# =============================================================================
# MEETING MANAGEMENT
# =============================================================================

@router.post("/meetings/create")
async def create_meeting(meeting: MeetingCreate, current_user: dict = Depends(get_current_user)):
    """Create a new meeting"""
    meeting_id = generate_id()
    
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Create meeting
        await db.execute(
            "INSERT INTO meetings (meeting_id, name, creator_user_id) VALUES (?, ?, ?)",
            (meeting_id, meeting.name, current_user["user_id"])
        )
        
        # Add creator as approved participant
        await db.execute(
            "INSERT INTO meeting_participants (meeting_id, user_id, status) VALUES (?, ?, 'approved')",
            (meeting_id, current_user["user_id"])
        )
        
        await db.commit()
    
    logger.info(f"Meeting created: {meeting.name} by {current_user['name']}")
    return {"meeting_id": meeting_id, "name": meeting.name}

@router.post("/meetings/join")
async def join_meeting(request: MeetingJoinRequest, current_user: dict = Depends(get_current_user)):
    """Request to join a meeting"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if meeting exists
        async with db.execute("SELECT meeting_id, creator_user_id FROM meetings WHERE meeting_id = ?", (request.meeting_id,)) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data:
                raise HTTPException(status_code=404, detail="Meeting not found")
        
        meeting_creator_id = meeting_data[1]
        
        # Check if already a participant
        async with db.execute(
            "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
            (request.meeting_id, current_user["user_id"])
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                if existing[0] == "approved":
                    return {"message": "Already in meeting", "approved": True}
                elif existing[0] == "pending":
                    raise HTTPException(status_code=400, detail="Join request already pending")
                else:
                    raise HTTPException(status_code=400, detail="Join request was rejected")
        
        # Add join request with pending status
        await db.execute(
            "INSERT INTO meeting_participants (meeting_id, user_id, status) VALUES (?, ?, 'pending')",
            (request.meeting_id, current_user["user_id"])
        )
        await db.commit()
    
    # Notify meeting creator about new pending request
    try:
        await notify_user(meeting_creator_id, "pending_request", 
                         f"{current_user['name']} requested to join the meeting",
                         meeting_id=request.meeting_id,
                         requester=current_user)
    except Exception as e:
        logger.warning(f"Could not notify meeting creator: {e}")
    
    logger.info(f"Meeting join request: {current_user['name']} -> {request.meeting_id}")
    return {"message": "Join request sent. Waiting for host approval.", "approved": False}

@router.get("/meetings/{meeting_id}/status")
async def get_meeting_status(meeting_id: str, current_user: dict = Depends(get_current_user)):
    """Get user's status in meeting"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if meeting exists
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data:
                raise HTTPException(status_code=404, detail="Meeting not found")
        
        is_creator = meeting_data[0] == current_user["user_id"]
        
        if is_creator:
            return {"status": "approved", "is_creator": True}
        
        # Check user's participation status
        async with db.execute(
            "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
            (meeting_id, current_user["user_id"])
        ) as cursor:
            participant_data = await cursor.fetchone()
            
            if not participant_data:
                return {"status": "not_member", "is_creator": False}
            
            return {"status": participant_data[0], "is_creator": False}

# =============================================================================
# MEETING ADMINISTRATION
# =============================================================================

@router.get("/meetings/{meeting_id}/pending")
async def get_meeting_pending_requests(meeting_id: str, current_user: dict = Depends(get_current_user)):
    """Get pending join requests for a meeting (host only)"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if user is meeting creator
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data or meeting_data[0] != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="Only meeting host can view pending requests")
        
        # Get pending requests
        async with db.execute("""
            SELECT u.user_id, u.public_id, u.name, mp.joined_at
            FROM meeting_participants mp
            JOIN users u ON mp.user_id = u.user_id
            WHERE mp.meeting_id = ? AND mp.status = 'pending'
            ORDER BY mp.joined_at DESC
        """, (meeting_id,)) as cursor:
            requests = await cursor.fetchall()
            return [
                {
                    "user_id": req[0],
                    "public_id": req[1],
                    "name": req[2], 
                    "requested_at": req[3]
                } for req in requests
            ]

@router.post("/meetings/{meeting_id}/approve")
async def approve_meeting_request(meeting_id: str, action: AdminAction, current_user: dict = Depends(get_current_user)):
    """Approve or reject meeting join request (host only)"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if user is meeting creator
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data or meeting_data[0] != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="Only meeting host can approve requests")
        
        # Check if request exists
        async with db.execute(
            "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
            (meeting_id, action.target_user_id)
        ) as cursor:
            existing = await cursor.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Join request not found")
            if existing[0] != "pending":
                raise HTTPException(status_code=400, detail="Request is not pending")
        
        # Update status based on action
        if action.action == "approve":
            new_status = "approved"
            message = "User approved to join meeting"
            notification_message = "Your request to join the meeting has been approved"
        elif action.action == "reject":
            new_status = "rejected"
            message = "User request rejected"
            notification_message = "Your request to join the meeting has been rejected"
        elif action.action == "remove":
            # Remove from meeting entirely
            await db.execute(
                "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, action.target_user_id)
            )
            await db.commit()
            
            # Notify user they were removed
            try:
                await notify_user(action.target_user_id, "meeting_removed", 
                                "You have been removed from the meeting")
            except Exception as e:
                logger.warning(f"Could not notify removed user: {e}")
            
            logger.info(f"User removed from meeting: {action.target_user_id} from {meeting_id}")
            return {"message": "User removed from meeting"}
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        await db.execute(
            "UPDATE meeting_participants SET status = ? WHERE meeting_id = ? AND user_id = ?",
            (new_status, meeting_id, action.target_user_id)
        )
        await db.commit()
        
        # Notify user about decision
        try:
            await notify_user(action.target_user_id, "request_decision", notification_message,
                            meeting_id=meeting_id, decision=action.action)
        except Exception as e:
            logger.warning(f"Could not notify user about decision: {e}")
        
        logger.info(f"Meeting request {action.action}: {action.target_user_id} in {meeting_id}")
        return {"message": message}

@router.post("/meetings/{meeting_id}/kick")
async def kick_participant(meeting_id: str, action: AdminAction, current_user: dict = Depends(get_current_user)):
    """Kick or block participant from meeting (host only)"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if user is meeting creator
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data or meeting_data[0] != current_user["user_id"]:
                raise HTTPException(status_code=403, detail="Only meeting host can kick participants")
        
        # Check if user is actually in the meeting
        async with db.execute(
            "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
            (meeting_id, action.target_user_id)
        ) as cursor:
            participant_data = await cursor.fetchone()
            if not participant_data:
                raise HTTPException(status_code=404, detail="User is not in this meeting")
        
        if action.action == "kick":
            # Remove from meeting
            await db.execute(
                "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, action.target_user_id)
            )
            message = "User kicked from meeting"
            notification_message = "You have been kicked from the meeting"
        elif action.action == "block":
            # Block from meeting (set status to blocked)
            await db.execute(
                "UPDATE meeting_participants SET status = 'blocked' WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, action.target_user_id)
            )
            message = "User blocked from meeting"
            notification_message = "You have been blocked from the meeting"
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'kick' or 'block'")
        
        await db.commit()
        
        # Notify user they were kicked/blocked
        try:
            await notify_user(action.target_user_id, "meeting_kicked", notification_message)
        except Exception as e:
            logger.warning(f"Could not notify kicked user: {e}")
        
        # Broadcast to meeting room
        try:
            await broadcast_to_room(meeting_id, "participant_removed", 
                                  f"A participant was {action.action}ed from the meeting")
        except Exception as e:
            logger.warning(f"Could not broadcast kick event: {e}")
        
        logger.info(f"User {action.action}ed from meeting: {action.target_user_id} from {meeting_id}")
        return {"message": message}

@router.post("/meetings/{meeting_id}/leave")
async def leave_meeting(meeting_id: str, current_user: dict = Depends(get_current_user)):
    """Leave meeting - if creator, end meeting for everyone"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if user is meeting creator
        async with db.execute(
            "SELECT creator_user_id FROM meetings WHERE meeting_id = ?", (meeting_id,)
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data:
                raise HTTPException(status_code=404, detail="Meeting not found")
        
        is_creator = meeting_data[0] == current_user["user_id"]
        
        if is_creator:
            # Creator is leaving - end meeting for everyone
            # First notify all participants
            try:
                await broadcast_meeting_deleted(meeting_id)
            except Exception as e:
                logger.warning(f"Could not broadcast meeting end: {e}")
            
            await db.execute("DELETE FROM meeting_participants WHERE meeting_id = ?", (meeting_id,))
            await db.execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,))
            await db.commit()
            
            logger.info(f"Meeting ended by creator: {meeting_id}")
            return {"message": "Meeting ended for all participants"}
        else:
            # Regular participant leaving
            await db.execute(
                "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?",
                (meeting_id, current_user["user_id"])
            )
            await db.commit()
            
            # Notify other participants
            try:
                await broadcast_to_room(meeting_id, "participant_left", 
                                      f"{current_user['name']} left the meeting")
            except Exception as e:
                logger.warning(f"Could not broadcast participant leave: {e}")
            
            logger.info(f"User left meeting: {current_user['name']} from {meeting_id}")
            return {"message": "Left meeting successfully"}

@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, current_user: dict = Depends(get_current_user)):
    """Delete meeting (creator only)"""
    async with aiosqlite.connect(config.get_database_path()) as db:
        # Check if user is meeting creator
        async with db.execute(
            "SELECT name FROM meetings WHERE meeting_id = ? AND creator_user_id = ?", 
            (meeting_id, current_user["user_id"])
        ) as cursor:
            meeting_data = await cursor.fetchone()
            if not meeting_data:
                raise HTTPException(status_code=403, detail="Only meeting creator can delete meeting")
        
        meeting_name = meeting_data[0]
        
        # Notify all participants before deletion
        try:
            await broadcast_meeting_deleted(meeting_id)
        except Exception as e:
            logger.warning(f"Could not broadcast meeting deletion: {e}")
        
        # Give a moment for the notification to be sent
        await asyncio.sleep(0.5)
        
        # Delete everything related to the meeting
        await db.execute("DELETE FROM meeting_participants WHERE meeting_id = ?", (meeting_id,))
        await db.execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,))
        
        await db.commit()
    
    logger.info(f"Meeting deleted: {meeting_name} by {current_user['name']}")
    return {"message": "Meeting deleted successfully"}