"""만료된 processed_files를 주기적으로 삭제하고 deletion_events에 이력을 기록하는 스케줄러."""
import logging
import os
import threading
import time

from sqlalchemy import text

from utils.database import SessionLocal

logger = logging.getLogger(__name__)

# 실행 간격 (초) — 1시간마다 만료 파일 점검
_INTERVAL_SEC = 3600


def cleanup_expired_files() -> dict:
    """expires_at이 지난 processed_files를 삭제하고 deletion_events에 기록.

    Returns: {"deleted": 성공 수, "failed": 실패 수}
    """
    db = SessionLocal()
    deleted_count = 0
    failed_count = 0
    try:
        expired_rows = db.execute(
            text("""
                SELECT pf.processed_file_id, pf.stored_path, pf.expires_at, pf.user_id,
                       p.plan_code
                FROM processed_files pf
                LEFT JOIN analysis_jobs j ON j.job_id = pf.job_id
                LEFT JOIN subscriptions s ON s.user_id = pf.user_id AND s.status = 'active'
                LEFT JOIN plans p ON p.plan_id = s.plan_id
                WHERE pf.expires_at <= now()
                  AND pf.deleted_at IS NULL
                ORDER BY pf.expires_at ASC
                LIMIT 200
            """)
        ).fetchall()

        if not expired_rows:
            return {"deleted": 0, "failed": 0}

        logger.info("만료 파일 %d건 삭제 시작", len(expired_rows))

        for row in expired_rows:
            m = row._mapping
            file_id = str(m["processed_file_id"])
            stored_path = m["stored_path"]
            plan_code = m.get("plan_code") or "unknown"
            error_msg = None
            result = "success"

            # 실제 파일 삭제
            try:
                if stored_path and os.path.exists(stored_path):
                    os.remove(stored_path)
            except Exception as e:
                error_msg = f"파일 삭제 실패: {e}"
                result = "failed"
                failed_count += 1
                logger.warning("파일 삭제 실패 — id=%s path=%s err=%s", file_id, stored_path, e)

            try:
                # DB 소프트 삭제 표시
                db.execute(
                    text("UPDATE processed_files SET deleted_at = now() WHERE processed_file_id = :id"),
                    {"id": file_id},
                )
                # 삭제 이력 기록
                db.execute(
                    text("""
                        INSERT INTO deletion_events
                            (target_type, target_id, target_path,
                             delete_reason, retention_policy_code,
                             scheduled_delete_at, deleted_at, result,
                             error_message, actor_type)
                        VALUES
                            ('processed_file', :target_id, :target_path,
                             'expired', :policy_code,
                             :scheduled_at, now(), :result,
                             :error_msg, 'system')
                    """),
                    {
                        "target_id": file_id,
                        "target_path": stored_path,
                        "policy_code": plan_code,
                        "scheduled_at": m["expires_at"],
                        "result": result,
                        "error_msg": error_msg,
                    },
                )
                db.commit()
                if result == "success":
                    deleted_count += 1
                    logger.info("만료 파일 삭제 완료 — id=%s", file_id)
            except Exception as e:
                db.rollback()
                failed_count += 1
                logger.error("deletion_events 기록 실패 — id=%s err=%s", file_id, e)

    except Exception as e:
        logger.error("cleanup_expired_files 실행 오류: %s", e)
    finally:
        db.close()

    logger.info("만료 파일 정리 완료 — deleted=%d failed=%d", deleted_count, failed_count)
    return {"deleted": deleted_count, "failed": failed_count}


def cleanup_expired_uploads() -> dict:
    """플랜별 auto_delete_original_hours가 지난 uploads(원본 파일)를 자동 삭제."""
    db = SessionLocal()
    deleted_count = 0
    failed_count = 0
    try:
        # 진행 중인 작업이 없는 업로드 중에서, 업데이트(완료) 후 플랜 기준 시간이 지난 업로드 탐색
        expired_rows = db.execute(
            text("""
                SELECT u.upload_id, u.stored_path
                FROM uploads u
                JOIN subscriptions s ON s.user_id = u.user_id AND s.status = 'active'
                JOIN plans p ON p.plan_id = s.plan_id
                WHERE u.updated_at + (p.auto_delete_original_hours || ' hours')::interval <= now()
                  AND u.deleted_at IS NULL
                  AND u.status IN ('uploaded', 'failed', 'cancelled', 'expired')
                  AND NOT EXISTS (
                      SELECT 1 FROM analysis_jobs j 
                      WHERE j.upload_id = u.upload_id 
                        AND j.status IN ('queued', 'processing', 'cancelling', 'retrying')
                  )
                ORDER BY u.updated_at ASC
                LIMIT 50
            """)
        ).fetchall()

        if not expired_rows:
            return {"deleted": 0, "failed": 0}

        logger.info("만료 원본(Upload) %d건 자동 삭제 시작", len(expired_rows))

        for row in expired_rows:
            upload_id = str(row[0])
            stored_path = row[1]
            try:
                # 1) 물리 파일 삭제
                if stored_path and os.path.exists(stored_path):
                    os.remove(stored_path)
                
                # 2) DB에서 upload 레코드 삭제 (analysis_jobs.upload_id는 ON DELETE SET NULL로 유지됨)
                db.execute(
                    text("DELETE FROM uploads WHERE upload_id = :upload_id"),
                    {"upload_id": upload_id}
                )
                db.commit()
                
                deleted_count += 1
                logger.info("만료 원본(Upload) 자동 삭제 완료 — upload_id=%s", upload_id)
            except Exception as e:
                db.rollback()
                failed_count += 1
                logger.error("만료 원본(Upload) 자동 삭제 실패 — upload_id=%s err=%s", upload_id, e)

    except Exception as e:
        logger.error("cleanup_expired_uploads 실행 오류: %s", e)
    finally:
        db.close()

    if deleted_count > 0 or failed_count > 0:
        logger.info("만료 원본 정리 완료 — deleted=%d failed=%d", deleted_count, failed_count)
    return {"deleted": deleted_count, "failed": failed_count}


def _cleanup_loop():
    """백그라운드 스레드: 서버 시작 후 1분 대기 → 이후 매 INTERVAL_SEC마다 실행."""
    time.sleep(60)  # 서버 초기화 대기
    while True:
        try:
            cleanup_expired_files()
            cleanup_expired_uploads()
        except Exception as e:
            logger.error("cleanup 루프 예외: %s", e)
        time.sleep(_INTERVAL_SEC)


def start_cleanup_scheduler():
    """데몬 스레드로 만료 파일 정리 스케줄러를 시작."""
    t = threading.Thread(target=_cleanup_loop, daemon=True, name="file-cleanup")
    t.start()
    logger.info("✅ 파일 만료 삭제 스케줄러 시작 (interval=%ds)", _INTERVAL_SEC)
