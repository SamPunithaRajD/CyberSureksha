"""
DocuShield AI — Authentication & RBAC FastAPI Dependencies

Provides token extraction, current user lookup, and role restriction checkers.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from bson import ObjectId

from app.database import get_collection
from app.utils.auth_helper import decode_access_token

# Support standard OAuth2 scheme (FastAPI automatically finds it in Swagger docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    """
    Extract the JWT from the Authorization header and retrieve the corresponding user.
    If no token is provided in Authorization, we also fall back to checking a
    custom X-Auth-Token header or cookie (useful for quick frontend integrations).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        logger.warning("No authentication token found in request headers")
        raise credentials_exception
        
    payload = decode_access_token(token)
    if payload is None:
        logger.warning("Failed to decode token or token expired")
        raise credentials_exception
        
    email = payload.get("email")
    if email is None:
        raise credentials_exception
        
    users_col = get_collection("users")
    user = await users_col.find_one({"email": email})
    if user is None:
        logger.warning(f"Authenticated token maps to non-existent user: {email}")
        raise credentials_exception
        
    # Make ObjectId JSON serializable in user dictionary representation
    user["id"] = str(user["_id"])
    return user


class RoleChecker:
    """Enforce endpoint access control based on user roles."""

    def __init__(self, allowed_roles: list[str]) -> None:
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: dict = Depends(get_current_user)) -> dict:
        user_role = current_user.get("role")
        if user_role not in self.allowed_roles:
            logger.warning(
                f"User {current_user.get('email')} with role '{user_role}' "
                f"attempted to access restricted resource. Allowed roles: {self.allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user
