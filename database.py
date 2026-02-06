# database.py - Database Configuration and Setup
import aiosqlite
from sql_loader import sql_loader

# Use the same DATABASE_PATH as defined in database/__init__.py
DATABASE_PATH = "meeting_app.db"

async def init_database():
    """Initialize SQLite database with all tables"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Load schema statements from external SQL file
        schema_statements = sql_loader.get_schema('create_tables')
        
        # Execute each schema statement
        for statement in schema_statements:
            await db.execute(statement)
        
        await db.commit()