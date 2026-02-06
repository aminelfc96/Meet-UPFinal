from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from database import DATABASE_PATH
from utils import validate_user_id

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    try:
        # In a real app, you'd verify JWT here
        # For simplicity, we'll use the token as user_id
        user_id = credentials.credentials
        
        # Validate user ID format
        if not validate_user_id(user_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT user_id, public_id, name FROM users WHERE user_id = ?", 
                (user_id,)
            ) as cursor:
                user = await cursor.fetchone()
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found"
                    )
                return {
                    "user_id": user[0],
                    "public_id": user[1],
                    "name": user[2]
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )

async def get_user_by_id(user_id: str) -> dict:
    """Get user information by user ID"""
    if not validate_user_id(user_id):
        return None
    
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute(
                "SELECT user_id, public_id, name FROM users WHERE user_id = ?", 
                (user_id,)
            ) as cursor:
                user = await cursor.fetchone()
                if user:
                    return {
                        "user_id": user[0],
                        "public_id": user[1],
                        "name": user[2]
                    }
                return None
    except Exception as e:
        print(f"Error getting user by ID: {e}")
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
        print(f"Error checking team admin: {e}")
        return False

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
        print(f"Error checking meeting creator: {e}")
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
        print(f"Error checking team membership: {e}")
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
        print(f"Error checking meeting participation: {e}")
        return None
