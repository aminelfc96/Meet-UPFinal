# database/models.py - Database Models and Abstractions

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import aiosqlite
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# =============================================================================
# DATA MODELS (Following Domain-Driven Design)
# =============================================================================

@dataclass
class User:
    """User domain model"""
    user_id: str
    public_id: str
    name: str
    password_hash: str
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'public_id': self.public_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def to_safe_dict(self) -> Dict[str, Any]:
        """Return user data without sensitive information"""
        return {
            'user_id': self.user_id,
            'public_id': self.public_id,
            'name': self.name
        }

@dataclass
class Team:
    """Team domain model"""
    team_id: str
    name: str
    admin_user_id: str
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'team_id': self.team_id,
            'name': self.name,
            'admin_user_id': self.admin_user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class TeamMember:
    """Team member domain model"""
    team_id: str
    user_id: str
    status: str  # 'pending', 'approved', 'rejected'
    requested_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'team_id': self.team_id,
            'user_id': self.user_id,
            'status': self.status,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None
        }

@dataclass
class Meeting:
    """Meeting domain model"""
    meeting_id: str
    name: str
    creator_user_id: str
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'meeting_id': self.meeting_id,
            'name': self.name,
            'creator_user_id': self.creator_user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# =============================================================================
# REPOSITORY INTERFACES (Following Repository Pattern)
# =============================================================================

class BaseRepository(ABC):
    """Base repository interface following SOLID principles"""
    
    @abstractmethod
    async def create(self, entity: Any) -> bool:
        """Create a new entity"""
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[Any]:
        """Get entity by ID"""
        pass
    
    @abstractmethod
    async def update(self, entity: Any) -> bool:
        """Update an entity"""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity"""
        pass

class IUserRepository(BaseRepository):
    """User repository interface"""
    
    @abstractmethod
    async def get_by_credentials(self, user_id: str, password_hash: str) -> Optional[User]:
        """Get user by credentials"""
        pass
    
    @abstractmethod
    async def exists(self, user_id: str) -> bool:
        """Check if user exists"""
        pass

class ITeamRepository(BaseRepository):
    """Team repository interface"""
    
    @abstractmethod
    async def get_user_teams(self, user_id: str) -> List[Team]:
        """Get all teams for a user"""
        pass
    
    @abstractmethod
    async def is_admin(self, team_id: str, user_id: str) -> bool:
        """Check if user is team admin"""
        pass

class ITeamMemberRepository(BaseRepository):
    """Team member repository interface"""
    
    @abstractmethod
    async def get_pending_requests(self, team_id: str) -> List[Dict[str, Any]]:
        """Get pending team requests"""
        pass
    
    @abstractmethod
    async def add_member(self, team_id: str, user_id: str, status: str = 'pending') -> bool:
        """Add member to team"""
        pass
    
    @abstractmethod
    async def update_status(self, team_id: str, user_id: str, status: str) -> bool:
        """Update member status"""
        pass
    
    @abstractmethod
    async def get_member_status(self, team_id: str, user_id: str) -> Optional[str]:
        """Get member status"""
        pass

class IMeetingRepository(BaseRepository):
    """Meeting repository interface"""
    
    @abstractmethod
    async def get_user_meetings(self, user_id: str) -> List[Meeting]:
        """Get all meetings for a user"""
        pass
    
    @abstractmethod
    async def is_creator(self, meeting_id: str, user_id: str) -> bool:
        """Check if user is meeting creator"""
        pass

class IMeetingParticipantRepository(BaseRepository):
    """Meeting participant repository interface"""
    
    @abstractmethod
    async def get_pending_requests(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get pending meeting requests"""
        pass
    
    @abstractmethod
    async def add_participant(self, meeting_id: str, user_id: str, status: str = 'pending') -> bool:
        """Add participant to meeting"""
        pass
    
    @abstractmethod
    async def update_status(self, meeting_id: str, user_id: str, status: str) -> bool:
        """Update participant status"""
        pass
    
    @abstractmethod
    async def get_status(self, meeting_id: str, user_id: str) -> Optional[str]:
        """Get participant status"""
        pass

# =============================================================================
# DATABASE CONNECTION MANAGER (Following ACID Principles)
# =============================================================================

class DatabaseManager:
    """Database connection manager ensuring ACID properties"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection_pool: List[aiosqlite.Connection] = []
        self._pool_size = 5
    
    @asynccontextmanager
    async def get_connection(self):
        """Get database connection with proper transaction management"""
        connection = None
        try:
            connection = await aiosqlite.connect(self.db_path)
            # Enable foreign key constraints for referential integrity
            await connection.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency
            await connection.execute("PRAGMA journal_mode = WAL")
            # Set transaction to IMMEDIATE for ACID compliance
            await connection.execute("BEGIN IMMEDIATE")
            yield connection
            await connection.commit()
        except Exception as e:
            if connection:
                await connection.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            if connection:
                await connection.close()
    
    async def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SELECT query with parameterized inputs"""
        async with self.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = await cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
    
    async def execute_command(self, query: str, params: tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE command"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            return cursor.rowcount

# =============================================================================
# CONCRETE REPOSITORY IMPLEMENTATIONS
# =============================================================================

class UserRepository(IUserRepository):
    """User repository implementation with SQL injection protection"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def create(self, user: User) -> bool:
        """Create a new user"""
        query = """
            INSERT INTO users (user_id, public_id, name, password_hash, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            rows_affected = await self.db.execute_command(
                query, 
                (user.user_id, user.public_id, user.name, user.password_hash)
            )
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return False
    
    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID with parameterized query"""
        query = """
            SELECT user_id, public_id, name, password_hash, created_at 
            FROM users 
            WHERE user_id = ?
        """
        try:
            results = await self.db.execute_query(query, (user_id,))
            if results:
                row = results[0]
                return User(
                    user_id=row['user_id'],
                    public_id=row['public_id'],
                    name=row['name'],
                    password_hash=row['password_hash'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get user by ID: {e}")
            return None
    
    async def get_by_credentials(self, user_id: str, password_hash: str) -> Optional[User]:
        """Get user by credentials"""
        query = """
            SELECT user_id, public_id, name, password_hash, created_at 
            FROM users 
            WHERE user_id = ? AND password_hash = ?
        """
        try:
            results = await self.db.execute_query(query, (user_id, password_hash))
            if results:
                row = results[0]
                return User(
                    user_id=row['user_id'],
                    public_id=row['public_id'],
                    name=row['name'],
                    password_hash=row['password_hash'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
            return None
        except Exception as e:
            logger.error(f"Failed to authenticate user: {e}")
            return None
    
    async def exists(self, user_id: str) -> bool:
        """Check if user exists"""
        query = "SELECT 1 FROM users WHERE user_id = ? LIMIT 1"
        try:
            results = await self.db.execute_query(query, (user_id,))
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to check user existence: {e}")
            return False
    
    async def update(self, user: User) -> bool:
        """Update user information"""
        query = """
            UPDATE users 
            SET public_id = ?, name = ?, password_hash = ?
            WHERE user_id = ?
        """
        try:
            rows_affected = await self.db.execute_command(
                query,
                (user.public_id, user.name, user.password_hash, user.user_id)
            )
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return False
    
    async def delete(self, user_id: str) -> bool:
        """Delete user and cascade related data"""
        queries = [
            "DELETE FROM team_messages WHERE user_id = ?",
            "DELETE FROM team_members WHERE user_id = ?", 
            "DELETE FROM meeting_participants WHERE user_id = ?",
            "DELETE FROM teams WHERE admin_user_id = ?",
            "DELETE FROM meetings WHERE creator_user_id = ?",
            "DELETE FROM users WHERE user_id = ?"
        ]
        
        try:
            async with self.db.get_connection() as conn:
                for query in queries:
                    await conn.execute(query, (user_id,))
            return True
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

class TeamRepository(ITeamRepository):
    """Team repository implementation"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def create(self, team: Team) -> bool:
        """Create a new team"""
        query = """
            INSERT INTO teams (team_id, name, admin_user_id, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            rows_affected = await self.db.execute_command(
                query,
                (team.team_id, team.name, team.admin_user_id)
            )
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to create team: {e}")
            return False
    
    async def get_by_id(self, team_id: str) -> Optional[Team]:
        """Get team by ID"""
        query = """
            SELECT team_id, name, admin_user_id, created_at
            FROM teams
            WHERE team_id = ?
        """
        try:
            results = await self.db.execute_query(query, (team_id,))
            if results:
                row = results[0]
                return Team(
                    team_id=row['team_id'],
                    name=row['name'],
                    admin_user_id=row['admin_user_id'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get team: {e}")
            return None
    
    async def get_user_teams(self, user_id: str) -> List[Team]:
        """Get all teams for a user"""
        query = """
            SELECT DISTINCT t.team_id, t.name, t.admin_user_id, t.created_at
            FROM teams t
            LEFT JOIN team_members tm ON t.team_id = tm.team_id
            WHERE t.admin_user_id = ? OR (tm.user_id = ? AND tm.status = 'approved')
            ORDER BY t.created_at DESC
        """
        try:
            results = await self.db.execute_query(query, (user_id, user_id))
            teams = []
            for row in results:
                teams.append(Team(
                    team_id=row['team_id'],
                    name=row['name'],
                    admin_user_id=row['admin_user_id'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                ))
            return teams
        except Exception as e:
            logger.error(f"Failed to get user teams: {e}")
            return []
    
    async def is_admin(self, team_id: str, user_id: str) -> bool:
        """Check if user is team admin"""
        query = "SELECT 1 FROM teams WHERE team_id = ? AND admin_user_id = ?"
        try:
            results = await self.db.execute_query(query, (team_id, user_id))
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to check admin status: {e}")
            return False
    
    async def update(self, team: Team) -> bool:
        """Update team information"""
        query = "UPDATE teams SET name = ? WHERE team_id = ?"
        try:
            rows_affected = await self.db.execute_command(query, (team.name, team.team_id))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update team: {e}")
            return False
    
    async def delete(self, team_id: str) -> bool:
        """Delete team and related data"""
        queries = [
            "DELETE FROM team_messages WHERE team_id = ?",
            "DELETE FROM team_members WHERE team_id = ?",
            "DELETE FROM teams WHERE team_id = ?"
        ]
        
        try:
            async with self.db.get_connection() as conn:
                for query in queries:
                    await conn.execute(query, (team_id,))
            return True
        except Exception as e:
            logger.error(f"Failed to delete team: {e}")
            return False

class TeamMemberRepository(ITeamMemberRepository):
    """Team member repository implementation"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def create(self, member: TeamMember) -> bool:
        """Add a team member"""
        return await self.add_member(member.team_id, member.user_id, member.status)
    
    async def get_by_id(self, id: str) -> Optional[TeamMember]:
        """Not applicable for team members"""
        raise NotImplementedError("Team members don't have single ID")
    
    async def get_pending_requests(self, team_id: str) -> List[Dict[str, Any]]:
        """Get pending team requests with user information"""
        query = """
            SELECT tm.team_id, tm.user_id, tm.status, tm.requested_at,
                   u.name, u.public_id
            FROM team_members tm
            JOIN users u ON tm.user_id = u.user_id
            WHERE tm.team_id = ? AND tm.status = 'pending'
            ORDER BY tm.requested_at ASC
        """
        try:
            results = await self.db.execute_query(query, (team_id,))
            return results
        except Exception as e:
            logger.error(f"Failed to get pending requests: {e}")
            return []
    
    async def add_member(self, team_id: str, user_id: str, status: str = 'pending') -> bool:
        """Add member to team"""
        query = """
            INSERT OR REPLACE INTO team_members (team_id, user_id, status, requested_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            rows_affected = await self.db.execute_command(query, (team_id, user_id, status))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to add team member: {e}")
            return False
    
    async def update_status(self, team_id: str, user_id: str, status: str) -> bool:
        """Update member status"""
        query = """
            UPDATE team_members 
            SET status = ?, approved_at = CASE WHEN ? = 'approved' THEN CURRENT_TIMESTAMP ELSE approved_at END
            WHERE team_id = ? AND user_id = ?
        """
        try:
            rows_affected = await self.db.execute_command(query, (status, status, team_id, user_id))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update member status: {e}")
            return False
    
    async def get_member_status(self, team_id: str, user_id: str) -> Optional[str]:
        """Get member status"""
        query = "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?"
        try:
            results = await self.db.execute_query(query, (team_id, user_id))
            return results[0]['status'] if results else None
        except Exception as e:
            logger.error(f"Failed to get member status: {e}")
            return None
    
    async def update(self, member: TeamMember) -> bool:
        """Update team member"""
        return await self.update_status(member.team_id, member.user_id, member.status)
    
    async def delete(self, team_id: str, user_id: str = None) -> bool:
        """Remove member from team"""
        if user_id:
            query = "DELETE FROM team_members WHERE team_id = ? AND user_id = ?"
            params = (team_id, user_id)
        else:
            query = "DELETE FROM team_members WHERE team_id = ?"
            params = (team_id,)
        
        try:
            rows_affected = await self.db.execute_command(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to remove team member: {e}")
            return False

class MeetingRepository(IMeetingRepository):
    """Meeting repository implementation"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def create(self, meeting: Meeting) -> bool:
        """Create a new meeting"""
        query = """
            INSERT INTO meetings (meeting_id, name, creator_user_id, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            rows_affected = await self.db.execute_command(
                query,
                (meeting.meeting_id, meeting.name, meeting.creator_user_id)
            )
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to create meeting: {e}")
            return False
    
    async def get_by_id(self, meeting_id: str) -> Optional[Meeting]:
        """Get meeting by ID"""
        query = """
            SELECT meeting_id, name, creator_user_id, created_at
            FROM meetings
            WHERE meeting_id = ?
        """
        try:
            results = await self.db.execute_query(query, (meeting_id,))
            if results:
                row = results[0]
                return Meeting(
                    meeting_id=row['meeting_id'],
                    name=row['name'],
                    creator_user_id=row['creator_user_id'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get meeting: {e}")
            return None
    
    async def get_user_meetings(self, user_id: str) -> List[Meeting]:
        """Get all meetings for a user"""
        query = """
            SELECT DISTINCT m.meeting_id, m.name, m.creator_user_id, m.created_at
            FROM meetings m
            LEFT JOIN meeting_participants mp ON m.meeting_id = mp.meeting_id
            WHERE m.creator_user_id = ? OR (mp.user_id = ? AND mp.status = 'approved')
            ORDER BY m.created_at DESC
        """
        try:
            results = await self.db.execute_query(query, (user_id, user_id))
            meetings = []
            for row in results:
                meetings.append(Meeting(
                    meeting_id=row['meeting_id'],
                    name=row['name'],
                    creator_user_id=row['creator_user_id'],
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                ))
            return meetings
        except Exception as e:
            logger.error(f"Failed to get user meetings: {e}")
            return []
    
    async def is_creator(self, meeting_id: str, user_id: str) -> bool:
        """Check if user is meeting creator"""
        query = "SELECT 1 FROM meetings WHERE meeting_id = ? AND creator_user_id = ?"
        try:
            results = await self.db.execute_query(query, (meeting_id, user_id))
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to check creator status: {e}")
            return False
    
    async def update(self, meeting: Meeting) -> bool:
        """Update meeting information"""
        query = "UPDATE meetings SET name = ? WHERE meeting_id = ?"
        try:
            rows_affected = await self.db.execute_command(query, (meeting.name, meeting.meeting_id))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update meeting: {e}")
            return False
    
    async def delete(self, meeting_id: str) -> bool:
        """Delete meeting and related data"""
        queries = [
            "DELETE FROM meeting_participants WHERE meeting_id = ?",
            "DELETE FROM meetings WHERE meeting_id = ?"
        ]
        
        try:
            async with self.db.get_connection() as conn:
                for query in queries:
                    await conn.execute(query, (meeting_id,))
            return True
        except Exception as e:
            logger.error(f"Failed to delete meeting: {e}")
            return False

class MeetingParticipantRepository(IMeetingParticipantRepository):
    """Meeting participant repository implementation"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def create(self, participant) -> bool:
        """Add a meeting participant"""
        return await self.add_participant(participant.meeting_id, participant.user_id, participant.status)
    
    async def get_by_id(self, id: str) -> Optional[Any]:
        """Not applicable for meeting participants"""
        raise NotImplementedError("Meeting participants don't have single ID")
    
    async def get_pending_requests(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get pending meeting requests with user information"""
        query = """
            SELECT mp.meeting_id, mp.user_id, mp.status, mp.joined_at,
                   u.name, u.public_id
            FROM meeting_participants mp
            JOIN users u ON mp.user_id = u.user_id
            WHERE mp.meeting_id = ? AND mp.status = 'pending'
            ORDER BY mp.joined_at ASC
        """
        try:
            results = await self.db.execute_query(query, (meeting_id,))
            return results
        except Exception as e:
            logger.error(f"Failed to get pending meeting requests: {e}")
            return []
    
    async def add_participant(self, meeting_id: str, user_id: str, status: str = 'pending') -> bool:
        """Add participant to meeting"""
        query = """
            INSERT OR REPLACE INTO meeting_participants (meeting_id, user_id, status, joined_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """
        try:
            rows_affected = await self.db.execute_command(query, (meeting_id, user_id, status))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to add meeting participant: {e}")
            return False
    
    async def update_status(self, meeting_id: str, user_id: str, status: str) -> bool:
        """Update participant status"""
        query = """
            UPDATE meeting_participants 
            SET status = ?
            WHERE meeting_id = ? AND user_id = ?
        """
        try:
            rows_affected = await self.db.execute_command(query, (status, meeting_id, user_id))
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update participant status: {e}")
            return False
    
    async def get_status(self, meeting_id: str, user_id: str) -> Optional[str]:
        """Get participant status"""
        query = "SELECT status FROM meeting_participants WHERE meeting_id = ? AND user_id = ?"
        try:
            results = await self.db.execute_query(query, (meeting_id, user_id))
            return results[0]['status'] if results else None
        except Exception as e:
            logger.error(f"Failed to get participant status: {e}")
            return None
    
    async def update(self, participant) -> bool:
        """Update meeting participant"""
        return await self.update_status(participant.meeting_id, participant.user_id, participant.status)
    
    async def delete(self, meeting_id: str, user_id: str = None) -> bool:
        """Remove participant from meeting"""
        if user_id:
            query = "DELETE FROM meeting_participants WHERE meeting_id = ? AND user_id = ?"
            params = (meeting_id, user_id)
        else:
            query = "DELETE FROM meeting_participants WHERE meeting_id = ?"
            params = (meeting_id,)
        
        try:
            rows_affected = await self.db.execute_command(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to remove meeting participant: {e}")
            return False

# =============================================================================
# DEPENDENCY INJECTION CONTAINER (Following SOLID/DI Principles)
# =============================================================================

class DIContainer:
    """Dependency injection container"""
    
    def __init__(self, db_path: str):
        self._db_manager = DatabaseManager(db_path)
        self._repositories = {}
    
    def get_user_repository(self) -> IUserRepository:
        """Get user repository instance"""
        if 'user' not in self._repositories:
            self._repositories['user'] = UserRepository(self._db_manager)
        return self._repositories['user']
    
    def get_team_repository(self) -> ITeamRepository:
        """Get team repository instance"""
        if 'team' not in self._repositories:
            self._repositories['team'] = TeamRepository(self._db_manager)
        return self._repositories['team']
    
    def get_team_member_repository(self) -> ITeamMemberRepository:
        """Get team member repository instance"""
        if 'team_member' not in self._repositories:
            self._repositories['team_member'] = TeamMemberRepository(self._db_manager)
        return self._repositories['team_member']
    
    def get_meeting_repository(self) -> IMeetingRepository:
        """Get meeting repository instance"""
        if 'meeting' not in self._repositories:
            self._repositories['meeting'] = MeetingRepository(self._db_manager)
        return self._repositories['meeting']
    
    def get_meeting_participant_repository(self) -> IMeetingParticipantRepository:
        """Get meeting participant repository instance"""
        if 'meeting_participant' not in self._repositories:
            self._repositories['meeting_participant'] = MeetingParticipantRepository(self._db_manager)
        return self._repositories['meeting_participant']
    
    def get_db_manager(self) -> DatabaseManager:
        """Get database manager instance"""
        return self._db_manager