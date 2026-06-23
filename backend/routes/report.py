# 프론트엔드에서 들어오는 신고/문의 API 요청을 처리하는 라우터
from fastapi import APIRouter, Depends, HTTPException, Cookie
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

from utils.database import get_db
from models.report import create_abuse_report_query
from schemas.report import ReportCreate
from services import auth
from sqlalchemy import text as _text
import os
import shutil

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Reports"])

class SuccessResponse(BaseModel):
    success: bool
    report_id: str

@router.post("/", response_model=SuccessResponse)
def submit_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
):
    # 전달받은 데이터를 DB에 삽입하고 결과 ID를 반환
    current_user = auth.authenticate_access_token(access_token)
    user_id = str(current_user["id"])
    
    try:
        # 1. 신고 접수
        report_id = create_abuse_report_query(
            conn=db,
            user_id=user_id,
            report_type=data.report_type,
            target_job_id=data.target_job_id,
            title=data.title,
            description=data.description
        )

        # 2. 오탐지 신고인 경우, 상세보기 파일과 result.json을 support 폴더로 복사
        if data.target_job_id:
            artifacts = db.execute(
                _text("SELECT artifact_type, stored_path FROM analysis_artifacts WHERE job_id = :job_id AND artifact_type IN ('pii_result', 'detail_image', 'detail_video')"),
                {"job_id": data.target_job_id}
            ).fetchall()
            
            detail_path = None
            result_path = None
            for row in artifacts:
                m = row._mapping
                atype = m["artifact_type"]
                apath = m["stored_path"]
                if atype == "pii_result":
                    result_path = apath
                elif atype in ("detail_image", "detail_video"):
                    detail_path = apath

            if detail_path or result_path:
                support_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output_file", "support")
                os.makedirs(support_dir, exist_ok=True)
                
                # 원본(상세보기) 파일 복사
                if detail_path and os.path.exists(detail_path):
                    ext = os.path.splitext(detail_path)[1]
                    dest_detail = os.path.join(support_dir, f"관리자문의_{data.target_job_id}_상세보기{ext}")
                    shutil.copy2(detail_path, dest_detail)
                    
                # result.json 복사
                if result_path and os.path.exists(result_path):
                    dest_result = os.path.join(support_dir, f"관리자문의_{data.target_job_id}_result.json")
                    shutil.copy2(result_path, dest_result)

        # 3. 모든 관리자에게 알림 전송 (notification_events)
        admins = db.execute(_text("SELECT user_id FROM users WHERE role = 'admin'")).fetchall()
        for admin in admins:
            admin_id = str(admin._mapping["user_id"])
            db.execute(
                _text("""
                    INSERT INTO notification_events 
                    (user_id, channel, notification_type, title, message, target_type, target_id, status, created_at)
                    VALUES 
                    (:user_id, 'app', 'admin_report', :title, :message, 'report', :target_id, 'pending', NOW())
                """),
                {
                    "user_id": admin_id,
                    "title": "새로운 문의/신고가 접수되었습니다.",
                    "message": f"[{data.report_type}] {data.title}",
                    "target_id": report_id
                }
            )

        db.commit()
        return {"success": True, "report_id": report_id}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to submit report: {e}")
        raise HTTPException(status_code=500, detail="신고 접수 중 오류가 발생했습니다.")

@router.get("/")
def get_reports(
    category: str = "all",
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    offset = (page - 1) * size
    
    try:
        where_clause = ""
        params = {"limit": size, "offset": offset}
        
        if category and category != "all":
            where_clause = "WHERE report_type = :category"
            params["category"] = category
            
        count_query = f"SELECT COUNT(*) as total FROM abuse_reports {where_clause}"
        total = db.execute(_text(count_query), params).scalar()
        
        query = f"""
            SELECT report_id, reporter_user_id, report_type, target_job_id, title, status, created_at
            FROM abuse_reports
            {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        rows = db.execute(_text(query), params).fetchall()
        
        items = []
        for r in rows:
            m = r._mapping
            items.append({
                "id": str(m["report_id"]),
                "userId": str(m["reporter_user_id"]) if m["reporter_user_id"] else None,
                "type": m["report_type"],
                "targetJobId": m["target_job_id"],
                "title": m["title"],
                "status": m["status"],
                "createdAt": m["created_at"].isoformat() if m["created_at"] else None
            })
            
        return {
            "success": True,
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "totalPages": (total + size - 1) // size
        }
    except Exception as e:
        logger.error(f"Failed to fetch reports: {e}")
        raise HTTPException(status_code=500, detail="문의 내역 조회 중 오류가 발생했습니다.")

@router.get("/{report_id}")
def get_report_detail(
    report_id: str,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    try:
        row = db.execute(
            _text("""
                SELECT report_id, reporter_user_id, report_type, target_job_id, title, description, status, created_at
                FROM abuse_reports
                WHERE report_id = :report_id
            """),
            {"report_id": report_id}
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="해당 문의를 찾을 수 없습니다.")
            
        m = row._mapping
        
        # 파일 확인 (support 폴더)
        support_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output_file", "support")
        detail_files = []
        if m["target_job_id"] and os.path.exists(support_dir):
            import glob
            # 확장자 무관하게 검색
            pattern = os.path.join(support_dir, f"관리자문의_{m['target_job_id']}_*")
            matches = glob.glob(pattern)
            for file_path in matches:
                detail_files.append({
                    "filename": os.path.basename(file_path),
                    "url": f"/reports/{report_id}/files/{os.path.basename(file_path)}"
                })
                
        return {
            "success": True,
            "report": {
                "id": str(m["report_id"]),
                "userId": str(m["reporter_user_id"]) if m["reporter_user_id"] else None,
                "type": m["report_type"],
                "targetJobId": m["target_job_id"],
                "title": m["title"],
                "description": m["description"],
                "status": m["status"],
                "createdAt": m["created_at"].isoformat() if m["created_at"] else None,
                "files": detail_files
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch report detail: {e}")
        raise HTTPException(status_code=500, detail="문의 상세 조회 중 오류가 발생했습니다.")

from fastapi.responses import FileResponse
@router.get("/{report_id}/files/{filename}")
def download_support_file(
    report_id: str,
    filename: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    support_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output_file", "support")
    file_path = os.path.join(support_dir, filename)
    
    # Path traversal 방지
    if not os.path.normpath(file_path).startswith(os.path.normpath(support_dir)):
        raise HTTPException(status_code=400, detail="잘못된 파일 경로입니다.")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        
    import mimetypes
    media_type, _ = mimetypes.guess_type(file_path)
    if not media_type:
        media_type = "application/octet-stream"
        
    return FileResponse(file_path, media_type=media_type, filename=filename)

@router.put("/{report_id}/status")
def update_report_status(
    report_id: str,
    body: dict,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    status_val = body.get("status")
    if not status_val:
        raise HTTPException(status_code=400, detail="status 값이 필요합니다.")
        
    try:
        db.execute(
            _text("UPDATE abuse_reports SET status = :status WHERE report_id = :report_id"),
            {"status": status_val, "report_id": report_id}
        )
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update status: {e}")
        raise HTTPException(status_code=500, detail="상태 업데이트 중 오류가 발생했습니다.")


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
    try:
        # 삭제 전 존재하는지 확인
        row = db.execute(
            _text("SELECT report_id FROM abuse_reports WHERE report_id = :report_id"),
            {"report_id": report_id}
        ).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="문의 내역을 찾을 수 없습니다.")
            
        db.execute(
            _text("DELETE FROM abuse_reports WHERE report_id = :report_id"),
            {"report_id": report_id}
        )
        db.commit()
        return {"success": True, "message": "성공적으로 삭제되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete report: {e}")
        raise HTTPException(status_code=500, detail="삭제 중 오류가 발생했습니다.")
