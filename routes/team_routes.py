# routes/team_routes.py - Team Management Routes (Refactored)

from fastapi import APIRouter, HTTPException, Depends
import logging
import aiosqlite

from database import DIContainer, Team, TeamMember
from models import TeamCreate, TeamJoinRequest, AdminAction
from utils import generate_id, encrypt_data, decrypt_data
from enhanced_auth import get_current_user
from websocket_manager import manager
from config_manager import get_config

logger = logging.getLogger(__name__)
router = APIRouter()
config = get_config()

# Initialize DI container
di_container = DIContainer(config.get_database_path())

# =============================================================================
# TEAM MANAGEMENT
# =============================================================================

@router.get("/user/teams")
async def get_user_teams(current_user: dict = Depends(get_current_user)):
    """Get teams for current user using repository pattern"""
    try:
        team_repo = di_container.get_team_repository()
        teams = await team_repo.get_user_teams(current_user["user_id"])
        
        team_list = []
        for team in teams:
            team_data = team.to_dict()
            team_data["is_admin"] = team.admin_user_id == current_user["user_id"]
            team_list.append(team_data)
        
        return team_list
    except Exception as e:
        logger.error(f"Error getting user teams: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve teams")

@router.post("/teams/create")
async def create_team(team: TeamCreate, current_user: dict = Depends(get_current_user)):
    """Create a new team using repository pattern"""
    if not config.is_feature_enabled('team_creation'):
        raise HTTPException(status_code=403, detail="Team creation is disabled")
    
    try:
        team_id = generate_id()
        
        # Create team using repository
        team_repo = di_container.get_team_repository()
        team_member_repo = di_container.get_team_member_repository()
        
        # Create team
        new_team = Team(
            team_id=team_id,
            name=team.name,
            admin_user_id=current_user["user_id"]
        )
        
        team_created = await team_repo.create(new_team)
        if not team_created:
            raise HTTPException(status_code=500, detail="Failed to create team")
        
        # Add creator as approved member
        member_added = await team_member_repo.add_member(team_id, current_user["user_id"], "approved")
        if not member_added:
            # Cleanup: delete team if member addition failed
            await team_repo.delete(team_id)
            raise HTTPException(status_code=500, detail="Failed to add creator to team")
        
        logger.info(f"Team created: {team.name} by {current_user['name']}")
        return {"team_id": team_id, "name": team.name}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team: {e}")
        raise HTTPException(status_code=500, detail="Failed to create team")

@router.post("/teams/join")
async def join_team(request: TeamJoinRequest, current_user: dict = Depends(get_current_user)):
    """Request to join a team using repository pattern"""
    try:
        team_repo = di_container.get_team_repository()
        team_member_repo = di_container.get_team_member_repository()
        
        # Check if team exists
        team = await team_repo.get_by_id(request.team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Check if already a member
        existing_status = await team_member_repo.get_member_status(request.team_id, current_user["user_id"])
        if existing_status:
            if existing_status == "approved":
                raise HTTPException(status_code=400, detail="Already a team member")
            elif existing_status == "pending":
                raise HTTPException(status_code=400, detail="Join request already pending")
            elif existing_status == "banned":
                # Make it appear as if team doesn't exist for banned users
                raise HTTPException(status_code=404, detail="Team not found")
            else:
                raise HTTPException(status_code=400, detail="Join request was rejected")
        
        # Add join request with pending status
        member_added = await team_member_repo.add_member(request.team_id, current_user["user_id"], "pending")
        if not member_added:
            raise HTTPException(status_code=500, detail="Failed to submit join request")
        
        # Notify team admin about new join request
        try:
            from websocket_handlers import notify_user, broadcast_to_room
            # Notify the admin specifically
            await notify_user(team.admin_user_id, "team_join_request", 
                            f"{current_user['name']} requested to join the team",
                            team_id=request.team_id, requester=current_user)
            
            # Also broadcast to team room for any admins currently online
            await broadcast_to_room(request.team_id, "pending_request_update", 
                                  f"New join request from {current_user['name']}")
        except ImportError:
            logger.warning("WebSocket handlers not available for join request notification")
        
        logger.info(f"Team join request: {current_user['name']} -> {request.team_id}")
        return {"message": "Join request sent. Waiting for admin approval."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing team join request: {e}")
        raise HTTPException(status_code=500, detail="Failed to process join request")

# =============================================================================
# TEAM ADMINISTRATION
# =============================================================================

@router.get("/teams/{team_id}/pending")
async def get_team_pending_requests(team_id: str, current_user: dict = Depends(get_current_user)):
    """Get pending join requests for a team (admin only)"""
    try:
        team_repo = di_container.get_team_repository()
        team_member_repo = di_container.get_team_member_repository()
        
        # Check if user is team admin
        is_admin = await team_repo.is_admin(team_id, current_user["user_id"])
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only team admin can view pending requests")
        
        # Get pending requests
        requests = await team_member_repo.get_pending_requests(team_id)
        return [
            {
                "user_id": req["user_id"],
                "public_id": req["public_id"], 
                "name": req["name"],
                "requested_at": req["requested_at"]
            } for req in requests
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pending requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pending requests")

@router.get("/teams/{team_id}/members")
async def get_team_members(team_id: str, current_user: dict = Depends(get_current_user)):
    """Get team members list (admin only)"""
    try:
        team_repo = di_container.get_team_repository()
        
        # Check if user is team admin
        is_admin = await team_repo.is_admin(team_id, current_user["user_id"])
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only team admin can view team members")
        
        # Get team members - using raw SQL temporarily for complex join
        # TODO: Add method to get team members with user info to repository
        async with aiosqlite.connect(config.get_database_path()) as db:
            async with db.execute("""
                SELECT u.user_id, u.public_id, u.name, tm.status, tm.requested_at
                FROM team_members tm
                JOIN users u ON tm.user_id = u.user_id
                WHERE tm.team_id = ? AND tm.status IN ('approved', 'banned')
                ORDER BY tm.requested_at ASC
            """, (team_id,)) as cursor:
                members = await cursor.fetchall()
                
                # Get online users from WebSocket manager
                online_users = manager.get_online_users(team_id)
                
                return [
                    {
                        "user_id": member[0],
                        "public_id": member[1], 
                        "name": member[2],
                        "status": member[3],
                        "joined_at": member[4],
                        "is_admin": member[0] == current_user["user_id"],
                        "is_online": member[0] in online_users
                    } for member in members
                ]
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team members: {e}")
        raise HTTPException(status_code=500, detail="Failed to get team members")

@router.post("/teams/{team_id}/approve")
async def approve_team_request(team_id: str, action: AdminAction, current_user: dict = Depends(get_current_user)):
    """Approve or reject team join request (admin only)"""
    try:
        team_repo = di_container.get_team_repository()
        team_member_repo = di_container.get_team_member_repository()
        
        # Check if user is team admin
        is_admin = await team_repo.is_admin(team_id, current_user["user_id"])
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only team admin can approve requests")
        
        # Handle kick, ban, and unban actions first (don't require pending status)
        if action.action in ["kick", "ban", "unban"]:
            # Check if user exists in team
            user_status = await team_member_repo.get_member_status(team_id, action.target_user_id)
            if not user_status:
                raise HTTPException(status_code=404, detail="User is not in this team")
            
            if action.action == "kick":
                # Kick user from team (immediate removal)
                removed = await team_member_repo.delete(team_id, action.target_user_id)
                if not removed:
                    raise HTTPException(status_code=500, detail="Failed to kick user")
                
                # Force disconnect user and broadcast action
                try:
                    from websocket_handlers import broadcast_member_action, force_disconnect_user
                    await broadcast_member_action(team_id, "kick", action.target_user_id, current_user["name"])
                    await force_disconnect_user(action.target_user_id, "Kicked from team")
                except ImportError:
                    logger.warning("WebSocket handlers not available")
                
                logger.info(f"User kicked from team: {action.target_user_id} from {team_id}")
                return {"message": "User kicked from team"}
                
            elif action.action == "ban":
                # Ban user from team (mark as banned)
                banned = await team_member_repo.update_status(team_id, action.target_user_id, "banned")
                if not banned:
                    raise HTTPException(status_code=500, detail="Failed to ban user")
                
                # Force disconnect user and broadcast action
                try:
                    from websocket_handlers import broadcast_member_action, force_disconnect_user
                    await broadcast_member_action(team_id, "ban", action.target_user_id, current_user["name"])
                    await force_disconnect_user(action.target_user_id, "Banned from team")
                except ImportError:
                    logger.warning("WebSocket handlers not available")
                
                logger.info(f"User banned from team: {action.target_user_id} from {team_id}")
                return {"message": "User banned from team"}
                
            elif action.action == "unban":
                # Check if user is actually banned
                if user_status != "banned":
                    raise HTTPException(status_code=400, detail="User is not banned from this team")
                
                # Unban user (remove from team entirely so they can rejoin)
                unbanned = await team_member_repo.delete(team_id, action.target_user_id)
                if not unbanned:
                    raise HTTPException(status_code=500, detail="Failed to unban user")
                
                # Notify user about unban
                try:
                    from websocket_handlers import notify_user
                    await notify_user(action.target_user_id, "team_unbanned", 
                                    f"You have been unbanned from the team and can request to join again.",
                                    team_id=team_id)
                except ImportError:
                    logger.warning("WebSocket handlers not available")
                
                logger.info(f"User unbanned from team: {action.target_user_id} from {team_id}")
                return {"message": "User unbanned from team"}
        
        # Handle approve/reject/remove actions (require specific status checks)
        existing_status = await team_member_repo.get_member_status(team_id, action.target_user_id)
        if not existing_status:
            raise HTTPException(status_code=404, detail="Join request not found")
        
        # Update status based on action
        if action.action == "approve":
            if existing_status != "pending":
                raise HTTPException(status_code=400, detail="Request is not pending")
            updated = await team_member_repo.update_status(team_id, action.target_user_id, "approved")
            
            # Notify user about approval and broadcast to team
            try:
                from websocket_handlers import notify_user, broadcast_to_room
                await notify_user(action.target_user_id, "team_request_approved", 
                                f"Your request to join the team has been approved!",
                                team_id=team_id, approved=True)
                
                # Also broadcast to team to refresh pending lists
                await broadcast_to_room(team_id, "pending_request_update", 
                                      f"Join request approved for new member")
            except ImportError:
                logger.warning("WebSocket handlers not available for approval notification")
            
            message = "User approved to join team"
        elif action.action == "reject":
            if existing_status != "pending":
                raise HTTPException(status_code=400, detail="Request is not pending")
            updated = await team_member_repo.update_status(team_id, action.target_user_id, "rejected")
            
            # Notify user about rejection and broadcast to team
            try:
                from websocket_handlers import notify_user, broadcast_to_room
                await notify_user(action.target_user_id, "team_request_rejected", 
                                f"Your request to join the team has been rejected.",
                                team_id=team_id, approved=False)
                
                # Also broadcast to team to refresh pending lists
                await broadcast_to_room(team_id, "pending_request_update", 
                                      f"Join request rejected")
            except ImportError:
                logger.warning("WebSocket handlers not available for rejection notification")
            
            message = "User request rejected"
        elif action.action == "remove":
            # Remove from team entirely
            updated = await team_member_repo.delete(team_id, action.target_user_id)
            if updated:
                logger.info(f"User removed from team: {action.target_user_id} from {team_id}")
                return {"message": "User removed from team"}
            else:
                raise HTTPException(status_code=500, detail="Failed to remove user")
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        if not updated:
            raise HTTPException(status_code=500, detail=f"Failed to {action.action} user")
        
        logger.info(f"Team request {action.action}: {action.target_user_id} in {team_id}")
        return {"message": message}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing team action: {e}")
        raise HTTPException(status_code=500, detail="Failed to process team action")

@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, current_user: dict = Depends(get_current_user)):
    """Delete team (admin only)"""
    try:
        team_repo = di_container.get_team_repository()
        
        # Check if user is team admin and get team info
        team = await team_repo.get_by_id(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        if team.admin_user_id != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="Only team admin can delete team")
        
        team_name = team.name
        
        # Delete team using repository (which handles cascading deletes)
        deleted = await team_repo.delete(team_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete team")
        
        logger.info(f"Team deleted: {team_name} by {current_user['name']}")
        return {"message": "Team deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting team: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete team")

@router.post("/teams/{team_id}/leave")
async def leave_team(team_id: str, current_user: dict = Depends(get_current_user)):
    """Leave team - regular members leave, admin leaving deletes team"""
    try:
        team_repo = di_container.get_team_repository()
        team_member_repo = di_container.get_team_member_repository()
        
        # Check if team exists and get team info
        team = await team_repo.get_by_id(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        is_admin = team.admin_user_id == current_user["user_id"]
        
        if is_admin:
            # Admin leaving - delete entire team
            deleted = await team_repo.delete(team_id)
            if not deleted:
                raise HTTPException(status_code=500, detail="Failed to delete team")
            
            # Broadcast team deletion to all members
            try:
                from websocket_handlers import broadcast_team_deleted
                await broadcast_team_deleted(team_id, team.name)
            except ImportError:
                logger.warning("WebSocket handlers not available")
            
            return {"message": "Team deleted successfully (admin left)"}
        else:
            # Regular member leaving - check if they are actually a member
            membership_status = await team_member_repo.get_member_status(team_id, current_user["user_id"])
            if not membership_status:
                raise HTTPException(status_code=403, detail="Not a team member")
            
            # Remove member from team
            removed = await team_member_repo.delete(team_id, current_user["user_id"])
            if not removed:
                raise HTTPException(status_code=500, detail="Failed to leave team")
            
            return {"message": "Left team successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error leaving team: {e}")
        raise HTTPException(status_code=500, detail="Failed to leave team")

# =============================================================================
# TEAM CHAT
# =============================================================================

@router.get("/teams/{team_id}/messages")
async def get_team_messages(team_id: str, current_user: dict = Depends(get_current_user)):
    """Get chat history for a team"""
    try:
        team_member_repo = di_container.get_team_member_repository()
        
        # Check if user is a member of the team
        membership_status = await team_member_repo.get_member_status(team_id, current_user["user_id"])
        if not membership_status or membership_status != "approved":
            raise HTTPException(status_code=403, detail="Not a team member")
        
        # Get recent messages using raw SQL for complex join (TODO: create message repository)
        async with aiosqlite.connect(config.get_database_path()) as db:
            # Get recent messages (last 50)
            async with db.execute("""
                SELECT tm.message, tm.message_type, tm.created_at, u.user_id, u.public_id, u.name
                FROM team_messages tm
                JOIN users u ON tm.user_id = u.user_id
                WHERE tm.team_id = ?
                ORDER BY tm.created_at DESC
                LIMIT 50
            """, (team_id,)) as cursor:
                messages = await cursor.fetchall()
                
                # Decrypt messages and format for return
                decrypted_messages = []
                for msg in reversed(messages):  # Reverse to show oldest first
                    try:
                        decrypted_message = decrypt_data(msg[0])
                    except:
                        decrypted_message = msg[0]  # Fallback if decryption fails
                    
                    decrypted_messages.append({
                        "message": decrypted_message,
                        "message_type": msg[1],
                        "timestamp": msg[2],
                        "user": {
                            "user_id": msg[3],
                            "public_id": msg[4],
                            "name": msg[5]
                        }
                    })
                
                return decrypted_messages
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to get team messages")

@router.delete("/teams/{team_id}/messages")
async def clear_team_chat(team_id: str, current_user: dict = Depends(get_current_user)):
    """Clear all team chat messages (admin only)"""
    try:
        team_repo = di_container.get_team_repository()
        
        # Check if user is team admin
        is_admin = await team_repo.is_admin(team_id, current_user["user_id"])
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only team admin can clear chat")
        
        # Delete all team messages and files - using raw SQL for file operations
        async with aiosqlite.connect(config.get_database_path()) as db:
            # Delete all team messages and files
            async with db.execute(
                "SELECT file_path FROM team_messages WHERE team_id = ? AND file_path IS NOT NULL",
                (team_id,)
            ) as cursor:
                file_paths = await cursor.fetchall()
            
            # Delete physical files
            import os
            from pathlib import Path
            for file_path_row in file_paths:
                if file_path_row and file_path_row[0]:
                    file_path = Path(file_path_row[0])
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            logger.info(f"Deleted file: {file_path}")
                        except Exception as e:
                            logger.error(f"Error deleting file {file_path}: {e}")
            
            # Delete all messages from database
            await db.execute("DELETE FROM team_messages WHERE team_id = ?", (team_id,))
            await db.commit()
        
        # Broadcast chat cleared message to all team members
        from websocket_handlers import broadcast_team_chat_cleared
        await broadcast_team_chat_cleared(team_id, current_user["name"])
        
        logger.info(f"Team chat cleared by admin {current_user['name']} for team {team_id}")
        return {"message": "Team chat cleared successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing team chat: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear team chat")