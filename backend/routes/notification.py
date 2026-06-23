from fastapi import APIRouter, Cookie, HTTPException
from sqlalchemy import text as _text
import logging

from utils.database import SessionLocal
from services import auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Notifications"])

@router.get("/")
def get_notifications(
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    user_id = str(current_user["id"])
    
    db = SessionLocal()
    try:
        rows = db.execute(
            _text("""
                SELECT notification_event_id as id, notification_type as type, 
                       title, message as msg, target_type, target_id, created_at, status
                FROM notification_events
                WHERE user_id = :user_id AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 50
            """),
            {"user_id": user_id}
        ).fetchall()
        
        notifications = []
        for r in rows:
            m = r._mapping
            notifications.append({
                "id": str(m["id"]),
                "type": m["type"],
                "title": m["title"],
                "msg": m["msg"],
                "target_type": m["target_type"],
                "target_id": m["target_id"] if m["target_id"] else None,
                "status": m["status"],
                "createdAt": m["created_at"].isoformat() if m["created_at"] else None
            })
            
        return {"success": True, "notifications": notifications}
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        raise HTTPException(status_code=500, detail="알림 조회 중 오류가 발생했습니다.")
    finally:
        db.close()

@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    user_id = str(current_user["id"])
    
    db = SessionLocal()
    try:
        db.execute(
            _text("""
                UPDATE notification_events 
                SET status = 'sent', sent_at = NOW() 
                WHERE notification_event_id = :notif_id AND user_id = :user_id
            """),
            {"notif_id": notification_id, "user_id": user_id}
        )
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark notification read: {e}")
        raise HTTPException(status_code=500, detail="알림 읽음 처리 중 오류가 발생했습니다.")
    finally:
        db.close()

@router.post("/read-all")
def mark_all_read(
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    user_id = str(current_user["id"])
    
    db = SessionLocal()
    try:
        db.execute(
            _text("""
                UPDATE notification_events 
                SET status = 'sent', sent_at = NOW() 
                WHERE user_id = :user_id AND status = 'pending'
            """),
            {"user_id": user_id}
        )
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to mark all notifications read: {e}")
        raise HTTPException(status_code=500, detail="알림 일괄 읽음 처리 중 오류가 발생했습니다.")
    finally:
        db.close()
