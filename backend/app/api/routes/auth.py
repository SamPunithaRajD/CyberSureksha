"""
DocuShield AI — Authentication API Routes

Endpoints for user login, current user details, and user management.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from pydantic import BaseModel, EmailStr, Field

from app.database import get_collection
from app.utils.auth_deps import get_current_user, RoleChecker
from app.utils.auth_helper import create_access_token, verify_password, hash_password

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    username: str
    role: str
    branch: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CreateUserRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str
    branch: str = "Canara Bank"


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate a user and return a JWT access token",
)
async def login(credentials: UserLoginRequest):
    """Log in using email and password, returning a JWT token."""
    users_col = get_collection("users")
    
    user = await users_col.find_one({"email": credentials.email})
    if not user:
        logger.warning(f"Login failed: User {credentials.email} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
        
    if not verify_password(credentials.password, user.get("password_hash", "")):
        logger.warning(f"Login failed: Incorrect password for user {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
        
    # Generate token
    token_data = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"]
    }
    
    access_token = create_access_token(token_data, expires_delta=timedelta(hours=24))
    
    # Audit log entry for login
    try:
        audit_col = get_collection("audit_logs")
        from datetime import datetime, timezone
        await audit_col.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "user_id": str(user["_id"]),
            "username": user.get("username", "Unknown"),
            "role": user.get("role", "Unknown"),
            "action": "user_login",
            "details": {"email": credentials.email}
        })
    except Exception as e:
        logger.error(f"Failed to write login audit log: {e}")
        
    logger.info(f"User {credentials.email} logged in successfully")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "username": user["username"],
            "role": user["role"],
            "branch": user.get("branch", "Canara Bank")
        }
    }


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current logged in user details",
)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Retrieve details of the authenticated user from the JWT session."""
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "role": current_user["role"],
        "branch": current_user.get("branch", "Canara Bank")
    }


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (Admin only)",
)
async def create_user(
    request: CreateUserRequest,
    current_user: dict = Depends(RoleChecker(["System Admin"]))
):
    """Create a new user with a specified role and branch. Restricted to System Admin."""
    users_col = get_collection("users")
    
    existing = await users_col.find_one({"email": request.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered.",
        )
        
    hashed_pass = hash_password(request.password)
    user_dict = {
        "email": request.email,
        "username": request.username,
        "password_hash": hashed_pass,
        "role": request.role,
        "branch": request.branch
    }
    
    result = await users_col.insert_one(user_dict)
    
    # Audit log
    try:
        audit_col = get_collection("audit_logs")
        from datetime import datetime, timezone
        await audit_col.insert_one({
            "timestamp": datetime.now(timezone.utc),
            "user_id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "action": "user_creation",
            "details": {"created_email": request.email, "role": request.role}
        })
    except Exception as e:
        logger.error(f"Failed to log user creation: {e}")
        
    return {
        "id": str(result.inserted_id),
        "email": request.email,
        "username": request.username,
        "role": request.role,
        "branch": request.branch
    }
