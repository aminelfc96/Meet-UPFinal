"""
File Upload and Management Routes

Handles file uploading, serving, and management for team chat file sharing.
Includes secure token-based access to prevent unauthorized downloads.
"""

import os
import aiofiles
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Response, Query
from fastapi.responses import FileResponse
import aiosqlite
import logging

from enhanced_auth import get_current_user
from database import DIContainer
from config_manager import get_config

config = get_config()
di_container = DIContainer(config.get_database_path())
from common_utils import AppConfig, ValidationError, Validators
from secure_tokens import generate_secure_file_token, validate_file_token, revoke_file_token

logger = logging.getLogger(__name__)

router = APIRouter()

# Ensure uploads directory exists
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/teams/{team_id}/upload")
async def upload_file(
    team_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a file to team chat"""
    
    # Validate team ID
    try:
        team_id = Validators.validate_team_id(team_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if user is a team member
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, current_user["user_id"])
        ) as cursor:
            membership = await cursor.fetchone()
            if not membership or membership[0] != "approved":
                raise HTTPException(status_code=403, detail="Not a team member")
    
    # Validate file
    try:
        Validators.validate_file_upload(file.filename, file.size or 0)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix.lower()
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = UPLOAD_DIR / unique_filename
    
    try:
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Store file info in database
        async with aiosqlite.connect(config.get_database_path()) as db:
            await db.execute(
                """INSERT INTO team_messages 
                   (team_id, user_id, message, message_type, file_path) 
                   VALUES (?, ?, ?, ?, ?)""",
                (team_id, current_user["user_id"], 
                 f"[FILE] {file.filename}", "file", str(file_path))
            )
            await db.commit()
        
        return {
            "message": "File uploaded successfully",
            "file_id": unique_filename,
            "file_name": file.filename,
            "file_size": file.size,
            "file_path": f"/api/files/{unique_filename}"
        }
        
    except Exception as e:
        # Cleanup file if database operation fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail="File upload failed")

@router.get("/files/{file_id}/token")
async def get_file_token(file_id: str, access_type: str = "download", current_user: dict = Depends(get_current_user)):
    """Generate a secure token for file access"""
    
    # Validate file ID format
    if not file_id or len(file_id) < 10:
        raise HTTPException(status_code=400, detail="Invalid file ID")
    
    # Validate access type
    if access_type not in ["download", "preview"]:
        raise HTTPException(status_code=400, detail="Invalid access type")
    
    file_path = UPLOAD_DIR / file_id
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get file info from database to check permissions
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            """SELECT tm.team_id, tm.message, tmbr.status 
               FROM team_messages tm
               JOIN team_members tmbr ON tm.team_id = tmbr.team_id
               WHERE tm.file_path = ? AND tmbr.user_id = ?""",
            (str(file_path), current_user["user_id"])
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=403, detail="Access denied")
    
    team_id = result[0]
    
    # Generate secure token (valid for 5 minutes, single use)
    token = generate_secure_file_token(
        file_id=file_id,
        user_id=current_user["user_id"],
        team_id=team_id,
        access_type=access_type,
        ttl=300  # 5 minutes
    )
    
    logger.info(f"Generated {access_type} token for file {file_id} by user {current_user['user_id']}")
    
    return {
        "token": token,
        "expires_in": 300,
        "access_type": access_type,
        "file_id": file_id
    }

@router.get("/files/{file_id}")
async def download_file(file_id: str, token: str = Query(...), current_user: dict = Depends(get_current_user)):
    """Download a file using a secure token"""
    
    # Validate token
    access_token = validate_file_token(token)
    if not access_token:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    
    # Verify token matches file and user
    if (access_token.file_id != file_id or 
        access_token.user_id != current_user["user_id"] or
        access_token.access_type != "download"):
        raise HTTPException(status_code=403, detail="Token mismatch")
    
    file_path = UPLOAD_DIR / file_id
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get file info from database
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            """SELECT tm.team_id, tm.message, tmbr.status 
               FROM team_messages tm
               JOIN team_members tmbr ON tm.team_id = tmbr.team_id
               WHERE tm.file_path = ? AND tmbr.user_id = ?""",
            (str(file_path), current_user["user_id"])
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=403, detail="Access denied")
    
    # Extract original filename from message
    original_filename = result[1].replace("[FILE] ", "")
    
    logger.info(f"Secure download: {file_id} by user {current_user['user_id']}")
    
    return FileResponse(
        path=file_path,
        filename=original_filename,
        media_type='application/octet-stream'
    )

@router.get("/files/{file_id}/info")
async def get_file_info(file_id: str, current_user: dict = Depends(get_current_user)):
    """Get file information"""
    
    file_path = UPLOAD_DIR / file_id
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get file info from database
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            """SELECT tm.team_id, tm.message, tm.created_at, u.name, tmbr.status
               FROM team_messages tm
               JOIN users u ON tm.user_id = u.user_id
               JOIN team_members tmbr ON tm.team_id = tmbr.team_id
               WHERE tm.file_path = ? AND tmbr.user_id = ? AND tmbr.status = 'approved'""",
            (str(file_path), current_user["user_id"])
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=403, detail="Access denied")
    
    original_filename = result[1].replace("[FILE] ", "")
    file_size = file_path.stat().st_size
    
    # Determine if file is an image
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    is_image = Path(original_filename).suffix.lower() in image_extensions
    
    return {
        "file_id": file_id,
        "file_name": original_filename,
        "file_size": file_size,
        "uploaded_by": result[3],
        "uploaded_at": result[2],
        "is_image": is_image,
        "download_url": f"/api/files/{file_id}"
    }

@router.get("/files/{file_id}/preview")
async def preview_file(file_id: str, token: str = Query(...), current_user: dict = Depends(get_current_user)):
    """Preview a file using a secure token (for images)"""
    
    # Validate token
    access_token = validate_file_token(token)
    if not access_token:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    
    # Verify token matches file and user
    if (access_token.file_id != file_id or 
        access_token.user_id != current_user["user_id"] or
        access_token.access_type != "preview"):
        raise HTTPException(status_code=403, detail="Token mismatch")
    
    file_path = UPLOAD_DIR / file_id
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check permissions
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            """SELECT tm.team_id, tm.message, tmbr.status 
               FROM team_messages tm
               JOIN team_members tmbr ON tm.team_id = tmbr.team_id
               WHERE tm.file_path = ? AND tmbr.user_id = ?""",
            (str(file_path), current_user["user_id"])
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=403, detail="Access denied")
    
    # Determine content type
    original_filename = result[1].replace("[FILE] ", "")
    file_ext = Path(original_filename).suffix.lower()
    
    content_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp'
    }
    
    content_type = content_types.get(file_ext, 'application/octet-stream')
    
    logger.info(f"Secure preview: {file_id} by user {current_user['user_id']}")
    
    return FileResponse(
        path=file_path,
        media_type=content_type
    )

@router.delete("/files/{file_id}")
async def delete_file(file_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a file (only by uploader or team admin)"""
    
    file_path = UPLOAD_DIR / file_id
    
    # Get file info and check permissions
    async with aiosqlite.connect(config.get_database_path()) as db:
        async with db.execute(
            """SELECT tm.team_id, tm.user_id, t.admin_user_id
               FROM team_messages tm
               JOIN teams t ON tm.team_id = t.team_id
               WHERE tm.file_path = ?""",
            (str(file_path),)
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="File not found")
        
        team_id, uploader_id, admin_id = result
        
        # Check if user can delete (uploader or team admin)
        if current_user["user_id"] not in [uploader_id, admin_id]:
            raise HTTPException(status_code=403, detail="Cannot delete this file")
        
        # Delete from database
        await db.execute(
            "DELETE FROM team_messages WHERE file_path = ?",
            (str(file_path),)
        )
        await db.commit()
    
    # Delete physical file
    if file_path.exists():
        file_path.unlink()
    
    return {"message": "File deleted successfully"}