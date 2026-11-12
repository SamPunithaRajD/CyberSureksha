"""
Notifications Routes — Retrieve and manage system alerts/notifications for bank underwriters and analysts.
"""
from typing import Any
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId

from fastapi import APIRouter, Depends, HTTPException, status
from app.utils.auth_deps import get_current_user
from app.database import get_collection

router = APIRouter()


def _to_object_id(id_str: str, label: str = "ID") -> ObjectId:
    """Convert string to ObjectId, raising a 400 on failure."""
    try:
        return ObjectId(id_str)
    except (InvalidId, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label} format: {id_str}",
        )


def serialize_notification(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert raw MongoDB notification document to JSON-safe dict."""
    if not doc:
        return {}
    
    serialized = {
        "id": str(doc["_id"]),
        "username": doc.get("username"),
        "document_id": doc.get("document_id"),
        "document_name": doc.get("document_name"),
        "message": doc.get("message"),
        "type": doc.get("type"),
        "read": doc.get("read", False),
    }
    
    dt = doc.get("created_at")
    if isinstance(dt, datetime):
        serialized["created_at"] = dt.isoformat()
    else:
        serialized["created_at"] = dt
        
    return serialized


# ------------------------------------------------------------------ #
#  GET / — Retrieve user notifications
# ------------------------------------------------------------------ #
@router.get(
    "/",
    summary="Get notifications for the current user",
)
async def get_user_notifications(
    current_user: dict = Depends(get_current_user)
):
    """Retrieve notifications matching the authenticated user's username, sorted chronologically."""
    notifications_col = get_collection("notifications")
    
    # Query notifications for current user's username
    cursor = notifications_col.find(
        {"username": current_user["username"]}
    ).sort("created_at", -1)
    
    results = await cursor.to_list(length=100)
    return [serialize_notification(r) for r in results]


# ------------------------------------------------------------------ #
#  POST /{id}/read — Mark single notification as read
# ------------------------------------------------------------------ #
@router.post(
    "/{notif_id}/read",
    summary="Mark a notification as read",
)
async def mark_notification_read(
    notif_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark a specific notification as read after verification of ownership."""
    notifications_col = get_collection("notifications")
    oid = _to_object_id(notif_id, "notification ID")
    
    notif = await notifications_col.find_one({"_id": oid})
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
        
    if notif.get("username") != current_user["username"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to mark this notification as read.",
        )
        
    await notifications_col.update_one(
        {"_id": oid},
        {"$set": {"read": True}}
    )
    
    return {"status": "success", "message": "Notification marked as read"}


# ------------------------------------------------------------------ #
#  POST /read-all — Mark all notifications as read
# ------------------------------------------------------------------ #
@router.post(
    "/read-all",
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user)
):
    """Mark all unread notifications for the logged-in user as read."""
    notifications_col = get_collection("notifications")
    
    result = await notifications_col.update_many(
        {"username": current_user["username"], "read": False},
        {"$set": {"read": True}}
    )
    
    return {
        "status": "success",
        "message": f"Successfully marked {result.modified_count} notification(s) as read."
    }
