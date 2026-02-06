# database/__init__.py - Database package initialization
import aiosqlite
import sys
import os

# Add parent directory to path to import from root database.py
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from .models import (
    User, Team, TeamMember, Meeting,
    IUserRepository, ITeamRepository, ITeamMemberRepository, 
    IMeetingRepository, IMeetingParticipantRepository,
    UserRepository, TeamRepository, TeamMemberRepository,
    MeetingRepository, MeetingParticipantRepository,
    DatabaseManager, DIContainer
)

# Database configuration
DATABASE_PATH = "meeting_app.db"

# Import init_database from root database.py
from sql_loader import sql_loader

async def init_database():
    """Initialize SQLite database with all tables"""
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if database file exists
    db_exists = os.path.exists(DATABASE_PATH)
    logger.info(f"Database exists: {db_exists} at {DATABASE_PATH}")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if required tables exist
        required_tables = ['users', 'teams', 'team_members', 'meetings', 'meeting_participants', 'team_messages']
        
        for table in required_tables:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
                (table,)
            )
            table_exists = await cursor.fetchone()
            await cursor.close()
            
            if not table_exists:
                logger.info(f"Table '{table}' does not exist, creating database schema...")
                # Load schema statements from external SQL file
                schema_statements = sql_loader.get_schema('create_tables')
                
                # Execute each schema statement
                for statement in schema_statements:
                    if statement.strip():  # Skip empty statements
                        await db.execute(statement)
                
                await db.commit()
                logger.info("Database schema created successfully")
                break
        else:
            logger.info("All required tables exist")
        
        # Verify users table structure
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        await cursor.close()
        
        if columns:
            column_names = [col[1] for col in columns]
            logger.info(f"Users table columns: {column_names}")
        else:
            logger.warning("Users table has no columns or doesn't exist")

__all__ = [
    'User', 'Team', 'TeamMember', 'Meeting',
    'IUserRepository', 'ITeamRepository', 'ITeamMemberRepository',
    'IMeetingRepository', 'IMeetingParticipantRepository',
    'UserRepository', 'TeamRepository', 'TeamMemberRepository',
    'MeetingRepository', 'MeetingParticipantRepository',
    'DatabaseManager', 'DIContainer',
    'DATABASE_PATH', 'init_database'
]