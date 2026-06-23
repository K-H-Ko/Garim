import json
import os

from sqlalchemy import text

from utils.database import SessionLocal

WORKER_SECRET = os.getenv("WORKER_SECRET", "")


def authenticate_worker(authorization: str | None) -> None:
    if not WORKER_SECRET:
        raise PermissionError("WORKER_SECRET이 설정되지 않았습니다.")
    if not authorization or not authorization.startswith("Bearer "):
        raise PermissionError("Worker 인증이 필요합니다.")
    if authorization[7:] != WORKER_SECRET:
        raise PermissionError("유효하지 않은 Worker 토큰입니다.")


def get_next_job(worker_type: str | None = None) -> dict | None:
    """대기 중인 job 1개 반환.

    worker_type:
      'local'       — analysis (로컬 OCR 워커 전담)
      'colab'       — stt_analysis (STT 전용 코랩 워커, 하위 호환 유지)
      'colab_mask'  — mask_preview / mask_final (마스킹 전용 코랩 워커)
      'colab_full'  — stt_analysis + mask_preview + mask_final (통합 코랩 워커)
      None/기타     — 모든 job_type (하위 호환)
    """
    db = SessionLocal()
    try:
        # worker_type 에 따라 job_type 필터 결정
        if worker_type == "local":
            # mask job은 코랩으로 위임 — local은 OCR analysis만 처리
            type_filter = "AND aj.job_type = 'analysis'"
        elif worker_type == "colab":
            # 하위 호환 — STT 전용 워커용
            type_filter = "AND aj.job_type = 'stt_analysis'"
        elif worker_type == "colab_mask":
            # 마스킹 미리보기/본처리는 Colab GPU 워커 전담
            type_filter = "AND aj.job_type IN ('mask_preview', 'mask_final')"
        elif worker_type == "colab_full":
            # STT + 마스킹 통합 코랩 워커 — 하나의 Colab에서 모두 처리
            type_filter = "AND aj.job_type IN ('stt_analysis', 'mask_preview', 'mask_final')"
        else:
            type_filter = ""          # 필터 없음 — 모든 job_type

        row = db.execute(
            text(f"""
                SELECT aj.job_id, aj.upload_id, aj.job_type, aj.queue_position,
                       u.stored_path, u.original_filename, u.media_type,
                       u.content_type, u.file_size
                FROM analysis_jobs aj
                JOIN uploads u ON u.upload_id = aj.upload_id
                WHERE aj.status = 'queued'
                  AND aj.cancel_requested = false
                  {type_filter}
                ORDER BY aj.queue_position ASC NULLS LAST, aj.created_at ASC
                LIMIT 1
            """)
        ).fetchone()

        if not row:
            return None

        m = row._mapping
        return {
            "job_id": str(m["job_id"]),
            "upload_id": str(m["upload_id"]),
            "job_type": m["job_type"],
            "queue_position": m["queue_position"],
            "file_path": m["stored_path"],
            "original_filename": m["original_filename"],
            "media_type": m["media_type"],
            "content_type": m["content_type"],
            "file_size": m["file_size"],
        }
    finally:
        db.close()


def accept_job(job_id: str) -> dict:
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                UPDATE analysis_jobs
                SET status = 'processing',
                    current_stage = 'queued',
                    message = '작업자가 분석 작업을 시작했습니다.',
                    started_at = now(),
                    updated_at = now()
                WHERE job_id = :job_id AND status = 'queued'
                RETURNING job_id, status
            """),
            {"job_id": job_id},
        ).fetchone()

        if not result:
            existing = db.execute(
                text("SELECT status FROM analysis_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).fetchone()
            if not existing:
                raise ValueError("분석 작업을 찾을 수 없습니다.")
            db.rollback()
            return {
                "job_id": job_id,
                "status": existing._mapping["status"],
                "message": "이미 처리 중이거나 완료된 작업입니다.",
            }

        db.execute(
            text("""
                INSERT INTO job_queue_history
                    (job_id, queue_name, priority, dequeued_position, status, message, dequeued_at)
                VALUES
                    (:job_id, 'default', 0, 0, 'dequeued', :message, now())
            """),
            {"job_id": job_id, "message": "작업자가 분석 작업을 가져갔습니다."},
        )

        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source)
                VALUES
                    (:job_id, 'queued', 100, 0, 'processing', :message, 'worker')
            """),
            {"job_id": job_id, "message": "작업자가 분석 작업을 시작했습니다."},
        )

        db.commit()
        return {"job_id": job_id, "status": "processing"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_upload_file_info(upload_id: str) -> dict:
    db = SessionLocal()
    try:
        # 1차적으로는 가장 최근에 마스킹된 완료 파일(processed_files)을 새로운 원본(입력)으로 간주합니다.
        # (대표님의 '개별 원본 이어달리기' 아키텍처에 따라, 마스킹이 한 번이라도 되었다면 그 결과물이 새로운 원본이 됨)
        import os
        pf = db.execute(
            text("""
                SELECT pf.stored_path, pf.content_type, pf.filename
                FROM processed_files pf
                JOIN analysis_jobs aj ON pf.job_id = aj.job_id
                WHERE aj.upload_id = :upload_id AND aj.job_type = 'mask_final'
                ORDER BY pf.created_at DESC LIMIT 1
            """),
            {"upload_id": upload_id}
        ).fetchone()

        if pf and os.path.exists(pf._mapping["stored_path"]):
            return {
                "stored_path": pf._mapping["stored_path"],
                "original_filename": pf._mapping["filename"],
                "content_type": pf._mapping["content_type"]
            }

        # 마스킹 이력이 없다면 (최초 1차 작업) 업로드 테이블의 순정 원본을 불러옵니다.
        row = db.execute(
            text("""
                SELECT stored_path, original_filename, content_type, status
                FROM uploads
                WHERE upload_id = :upload_id
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not row:
            raise ValueError("업로드를 찾을 수 없습니다.")

        m = row._mapping
        if m["status"] != "uploaded":
            raise ValueError(f"파일이 아직 준비되지 않았습니다. (status: {m['status']})")
        if not os.path.exists(m["stored_path"]):
            raise ValueError("원본 파일이 삭제되었으며 이전 결과물도 찾을 수 없습니다.")

        return {
            "stored_path": m["stored_path"],
            "original_filename": m["original_filename"],
            "content_type": m["content_type"],
        }
    finally:
        db.close()


def update_job_progress(
    job_id: str,
    worker_id: str | None,
    stage_name: str,
    stage_progress: int,
    total_progress: int,
    message: str | None = None,
) -> dict:
    db = SessionLocal()
    try:
        db.execute(
            text("""
                UPDATE analysis_jobs
                SET current_stage = :stage_name,
                    stage_progress = :stage_progress,
                    total_progress = :total_progress,
                    message = :message,
                    eta_seconds = CASE 
                        WHEN :total_progress > 0 AND :total_progress < 100 AND started_at IS NOT NULL 
                        THEN CAST(EXTRACT(EPOCH FROM (now() - started_at)) / :total_progress * (100 - :total_progress) AS INTEGER)
                        ELSE eta_seconds 
                    END,
                    updated_at = now()
                WHERE job_id = :job_id
            """),
            {
                "job_id": job_id,
                "stage_name": stage_name,
                "stage_progress": stage_progress,
                "total_progress": total_progress,
                "message": message,
            },
        )

        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source, eta_seconds)
                SELECT
                    :job_id, :stage_name, :stage_progress, :total_progress, 'processing', :message, 'worker', eta_seconds
                FROM analysis_jobs
                WHERE job_id = :job_id
            """),
            {
                "job_id": job_id,
                "stage_name": stage_name,
                "stage_progress": stage_progress,
                "total_progress": total_progress,
                "message": message,
            },
        )

        # 진행률 보고 응답에 '취소 요청 여부'를 함께 실어 보낸다(워커가 매 보고 시 즉시 감지).
        #  - cancel_requested=true (사용자 취소) 또는 job 행 자체가 삭제됨(업로드 삭제) → 둘 다 '취소'로 신호.
        cur = db.execute(
            text("SELECT cancel_requested, status FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        cancel_requested = (cur is None) or bool(cur._mapping["cancel_requested"])

        db.commit()
        return {
            "job_id": job_id,
            "stage_name": stage_name,
            "stage_progress": stage_progress,
            "total_progress": total_progress,
            "cancel_requested": cancel_requested,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def finalize_cancelled_job(job_id: str) -> dict:
    """워커가 처리 중단을 확정 → status='cancelled' 로 마무리.
    (job 행이 이미 삭제된 경우=업로드 삭제 경로는 0건 업데이트로 조용히 통과)."""
    db = SessionLocal()
    try:
        db.execute(
            text("""
                UPDATE analysis_jobs
                SET status = 'cancelled', updated_at = now()
                WHERE job_id = :job_id
                  AND status IN ('queued', 'processing', 'cancelling', 'retrying')
            """),
            {"job_id": job_id},
        )
        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source)
                SELECT :job_id, 'cancelled', 0, 0, 'cancelled', '작업이 취소되었습니다.', 'worker'
                WHERE EXISTS (SELECT 1 FROM analysis_jobs WHERE job_id = :job_id)
            """),
            {"job_id": job_id},
        )
        db.commit()
        return {"job_id": job_id, "status": "cancelled"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def complete_job(
    job_id: str,
    worker_id: str | None,
    detection_count: int = 0,
    duration_seconds: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    db = SessionLocal()
    try:
        db.execute(
            text("""
                UPDATE analysis_jobs
                SET status = 'completed',
                    completed_at = now(),
                    total_progress = 100,
                    stage_progress = 100,
                    eta_seconds = 0,
                    detection_count = :detection_count,
                    duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                    width  = COALESCE(:width,  width),
                    height = COALESCE(:height, height),
                    updated_at = now()
                WHERE job_id = :job_id
            """),
            {
                "job_id": job_id,
                "detection_count": detection_count,
                "duration_seconds": duration_seconds,
                "width": width,
                "height": height,
            },
        )

        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source, eta_seconds)
                VALUES
                    (:job_id, 'completed', 100, 100, 'completed', '분석이 완료되었습니다.', 'worker', 0)
            """),
            {"job_id": job_id},
        )

        job_info = db.execute(
            text("""
                SELECT j.job_type, j.upload_id, u.user_id, u.original_filename
                FROM analysis_jobs j
                JOIN uploads u ON u.upload_id = j.upload_id
                WHERE j.job_id = :job_id
            """),
            {"job_id": job_id}
        ).fetchone()

        if job_info:
            ji = job_info._mapping
            # uploads 테이블에도 메타데이터 반영 (없는 경우에만 채움)
            if duration_seconds is not None or width is not None or height is not None:
                db.execute(
                    text("""
                        UPDATE uploads
                        SET duration_seconds = COALESCE(:duration_seconds, duration_seconds),
                            width  = COALESCE(:width,  width),
                            height = COALESCE(:height, height),
                            updated_at = now()
                        WHERE upload_id = :upload_id
                    """),
                    {
                        "upload_id": ji["upload_id"],
                        "duration_seconds": duration_seconds,
                        "width": width,
                        "height": height,
                    },
                )
            job_type = ji["job_type"]
            upload_id = ji["upload_id"]
            user_id = str(ji["user_id"])
            filename = ji["original_filename"] or "파일"

            if job_type == "mask_final":
                # 분석 작업의 replacement_actions 완료 처리
                db.execute(
                    text("""
                        UPDATE replacement_actions
                        SET status = 'completed', updated_at = now()
                        WHERE job_id IN (
                            SELECT job_id FROM analysis_jobs
                            WHERE upload_id = :upload_id AND job_type IN ('analysis', 'stt_analysis')
                        )
                        AND is_user_selected = true AND status = 'pending'
                    """),
                    {"upload_id": upload_id}
                )

            # 사용자 알림 기록 (analysis/stt_analysis/mask_final 완료 시)
            notif_map = {
                "analysis":     ("analysis_complete", "개인정보 탐지 완료",   f"'{filename}' 파일의 개인정보 탐지가 완료되었습니다."),
                "stt_analysis": ("analysis_complete", "음성 분석 완료",        f"'{filename}' 파일의 음성 분석이 완료되었습니다."),
                "mask_final":   ("mask_complete",     "마스킹 처리 완료",      f"'{filename}' 파일의 마스킹 처리가 완료되었습니다. 결과를 확인하세요."),
            }
            if job_type in notif_map:
                ntype, title, message = notif_map[job_type]
                import uuid as _uuid
                job_uuid = _uuid.UUID(job_id)
                db.execute(
                    text("""
                        INSERT INTO notification_events
                            (user_id, channel, notification_type, title, message,
                             target_type, target_id, status)
                        VALUES
                            (:user_id, 'app', :ntype, :title, :message,
                             'job', :target_id, 'pending')
                    """),
                    {
                        "user_id": user_id,
                        "ntype": ntype,
                        "title": title,
                        "message": message,
                        "target_id": job_uuid,
                    },
                )

        db.commit()
        return {"job_id": job_id, "status": "completed"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fail_job(
    job_id: str,
    worker_id: str | None,
    error_code: str | None,
    error_message: str | None,
) -> dict:
    db = SessionLocal()
    try:
        db.execute(
            text("""
                UPDATE analysis_jobs
                SET status = 'failed',
                    error_code = :error_code,
                    error_message = :error_message,
                    updated_at = now()
                WHERE job_id = :job_id
            """),
            {
                "job_id": job_id,
                "error_code": error_code,
                "error_message": error_message,
            },
        )

        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source)
                VALUES
                    (:job_id, 'failed', 0, 0, 'failed', :error_message, 'worker')
            """),
            {"job_id": job_id, "error_message": error_message},
        )

        db.commit()
        return {"job_id": job_id, "status": "failed"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_job_status(job_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT job_id, status, cancel_requested, current_stage, total_progress
                FROM analysis_jobs
                WHERE job_id = :job_id
            """),
            {"job_id": job_id},
        ).fetchone()

        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")

        m = row._mapping
        return {
            "job_id": str(m["job_id"]),
            "status": m["status"],
            "cancel_requested": bool(m["cancel_requested"]),
            "current_stage": m["current_stage"],
            "total_progress": m["total_progress"],
        }
    finally:
        db.close()


def save_stt_result(
    job_id: str,
    language: str,
    full_text: str,
    segment_count: int,
) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        user_id = row._mapping["user_id"]

        result = db.execute(
            text("""
                INSERT INTO analysis_artifacts
                    (job_id, user_id, artifact_type, stored_path, metadata)
                VALUES
                    (:job_id, :user_id, 'stt_transcript', '', :metadata)
                RETURNING artifact_id
            """),
            {
                "job_id": job_id,
                "user_id": user_id,
                "metadata": json.dumps({
                    "language": language,
                    "full_text": full_text,
                    "segment_count": segment_count,
                }),
            },
        ).fetchone()

        db.commit()
        return {
            "job_id": job_id,
            "artifact_id": str(result._mapping["artifact_id"]),
            "artifact_type": "stt_transcript",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_pii_result(job_id: str, pii_segments: list, detection_type: str = "voice_pii") -> dict:
    """
    PII 탐지 결과를 detections 테이블에 저장.

    detection_type:
      - 'voice_pii' : 음성 STT PII (audio_pii_groups 항목)
        필수 필드: label(=pii_type), confidence, start_time_sec, end_time_sec, detected_text
      - 'visual_pii': 시각 OCR PII (pii_groups 항목)
        필수 필드: pii_label, confidence, rep_frame, bbox([x1,y1,x2,y2]), detected_text
        선택 필드: polygons ([[x,y]*4] 리스트) → polygon_json TEXT로 저장 (SVG 오버레이용)
        무시 필드: keyframes, boxes, frames (result.json 파일에만 보관)
    """
    db = SessionLocal()
    try:
        detection_ids = []
        for seg in pii_segments:
            if detection_type == "visual_pii":
                # bbox [x1, y1, x2, y2] → bbox_x/y/w/h 변환
                bbox = seg.get("bbox") or []
                if len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    bbox_x, bbox_y = float(x1), float(y1)
                    bbox_w, bbox_h = float(x2 - x1), float(y2 - y1)
                else:
                    bbox_x = bbox_y = bbox_w = bbox_h = None

                import json as _json
                polys = seg.get("polygons")
                polygon_json = _json.dumps(polys) if polys else None

                result = db.execute(
                    text("""
                        INSERT INTO detections
                            (job_id, detection_type, label, confidence,
                             frame_no, start_time_sec, end_time_sec,
                             bbox_x, bbox_y, bbox_w, bbox_h, detected_text, pii_id, polygon_json)
                        VALUES
                            (:job_id, 'visual_pii', :label, :confidence,
                             :frame_no, :start_time_sec, :end_time_sec,
                             :bbox_x, :bbox_y, :bbox_w, :bbox_h, :detected_text, :pii_id, :polygon_json)
                        RETURNING detection_id
                    """),
                    {
                        "job_id": job_id,
                        "label": seg.get("pii_label"),           # pii_label → label 변환
                        "confidence": seg.get("confidence"),
                        "frame_no": seg.get("rep_frame"),         # rep_frame → frame_no 변환
                        "start_time_sec": seg.get("start_time_sec"),  # 미리보기 버튼 표시용
                        "end_time_sec": seg.get("end_time_sec"),
                        "bbox_x": bbox_x,
                        "bbox_y": bbox_y,
                        "bbox_w": bbox_w,
                        "bbox_h": bbox_h,
                        "detected_text": seg.get("detected_text"),
                        "pii_id": seg.get("pii_id"),
                        "polygon_json": polygon_json,
                    },
                ).fetchone()
            else:
                # 음성 PII (기존 로직 유지)
                result = db.execute(
                    text("""
                        INSERT INTO detections
                            (job_id, detection_type, label, confidence,
                             start_time_sec, end_time_sec, detected_text, pii_id)
                        VALUES
                            (:job_id, 'voice_pii', :label, :confidence,
                             :start_time_sec, :end_time_sec, :detected_text, :pii_id)
                        RETURNING detection_id
                    """),
                    {
                        "job_id": job_id,
                        "label": seg.get("label"),
                        "confidence": seg.get("confidence"),
                        "start_time_sec": seg.get("start_time_sec"),
                        "end_time_sec": seg.get("end_time_sec"),
                        "detected_text": seg.get("detected_text"),
                        "pii_id": seg.get("pii_id"),
                    },
                ).fetchone()

            detection_ids.append(str(result._mapping["detection_id"]))

        db.commit()
        return {
            "job_id": job_id,
            "saved_count": len(detection_ids),
            "detection_ids": detection_ids,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_processed_file(
    job_id: str,
    filename: str,
    stored_path: str,
    content_type: str,
    file_size: int,
    expires_days: int = 7,
) -> dict:
    """마스킹 완료 결과물을 processed_files 테이블에 등록."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id, job_type FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        user_id = row._mapping["user_id"]
        upload_id = str(row._mapping["upload_id"])
        job_type = row._mapping["job_type"]

        # 현재 활성 구독의 result_retention_days 조회 (없으면 free 플랜, 기본값 7)
        retention_row = db.execute(
            text("""
                SELECT COALESCE(
                    (SELECT p.result_retention_days
                     FROM subscriptions s
                     JOIN plans p ON p.plan_id = s.plan_id
                     WHERE s.user_id = :user_id
                       AND s.status = 'active'
                       AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
                     ORDER BY p.plan_rank DESC LIMIT 1),
                    (SELECT result_retention_days FROM plans WHERE plan_code = 'free' AND status = 'active' LIMIT 1),
                    :default_days
                ) AS days
            """),
            {"user_id": user_id, "default_days": expires_days}
        ).fetchone()
        calculated_expires_days = retention_row._mapping["days"] if retention_row else expires_days

        result = db.execute(
            text("""
                INSERT INTO processed_files
                    (job_id, user_id, filename, stored_path,
                     content_type, file_size, watermark_applied,
                     expires_at)
                VALUES
                    (:job_id, :user_id, :filename, :stored_path,
                     :content_type, :file_size, false,
                     now() + (:calculated_expires_days || ' days')::interval)
                RETURNING processed_file_id
            """),
            {
                "job_id": job_id,
                "user_id": user_id,
                "filename": filename,
                "stored_path": stored_path,
                "content_type": content_type,
                "file_size": file_size,
                "calculated_expires_days": calculated_expires_days,
            },
        ).fetchone()

        db.commit()

        # [상세보기 파일 이어달리기 복사 로직]
        # 대표님의 '개별 원본' 아키텍처: mask_final이 끝날 때마다 원본 상세보기 파일을 자신의 UID 이름으로 복사해 둠으로써
        # 삭제 시 (job_id_*) 패턴에 의해 개별적으로 깔끔하게 삭제되고, 히스토리에서 조회할 때 이 파일을 바로 틀어주도록 함.
        if job_type == "mask_final":
            import os
            import shutil
            
            # 1번 원본(부모 분석 작업)의 상세보기 파일 경로 찾기
            parent_job = db.execute(
                text("""
                    SELECT job_id FROM analysis_jobs 
                    WHERE upload_id = :upload_id AND job_type = 'analysis'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"upload_id": upload_id}
            ).fetchone()
            
            if parent_job:
                parent_job_id = str(parent_job._mapping["job_id"])
                
                # 이미지인지 영상인지 구분하기 위해 원본 업로드 타입 확인
                up_row = db.execute(
                    text("SELECT content_type FROM uploads WHERE upload_id = :upload_id"),
                    {"upload_id": upload_id}
                ).fetchone()
                
                up_content_type = up_row._mapping["content_type"] if up_row else ""
                artifact_type = "detail_video" if "video" in up_content_type else "detail_image"
                
                old_artifact = db.execute(
                    text("""
                        SELECT stored_path FROM analysis_artifacts
                        WHERE job_id = :p_job_id AND artifact_type = :a_type
                        ORDER BY created_at DESC LIMIT 1
                    """),
                    {"p_job_id": parent_job_id, "a_type": artifact_type}
                ).fetchone()
                
                if old_artifact:
                    old_path = old_artifact._mapping["stored_path"]
                    if old_path and os.path.exists(old_path):
                        # {job_id}를 접두어로 하는 새 파일명 생성
                        ext = os.path.splitext(old_path)[1]
                        dir_path = os.path.dirname(old_path)
                        new_path = os.path.join(dir_path, f"{job_id}_상세보기{ext}")
                        
                        try:
                            # DB에는 따로 등록하지 않고 물리적 복사만 수행합니다. (analysis.py 에서 fallback으로 job_id 기반으로 바로 찾도록)
                            shutil.copy2(old_path, new_path)
                        except Exception as e:
                            print(f"Failed to copy detail file: {e}")

            # 원본 업로드 파일 삭제 (12시간 자동 삭제 전이라도 마스킹 본처리가 끝나면 용량 확보를 위해 즉시 삭제)
            up_row = db.execute(
                text("SELECT stored_path FROM uploads WHERE upload_id = :upload_id"),
                {"upload_id": upload_id}
            ).fetchone()
            
            if up_row and up_row._mapping["stored_path"]:
                original_path = up_row._mapping["stored_path"]
                if os.path.exists(original_path):
                    try:
                        os.remove(original_path)
                    except Exception:
                        pass
        return {
            "job_id": job_id,
            "processed_file_id": str(result._mapping["processed_file_id"]),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_artifact(
    job_id: str,
    artifact_type: str,
    stored_path: str,
    content_type: str | None = None,
    file_size: int | None = None,
    metadata: dict | None = None,
) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        user_id = row._mapping["user_id"]

        result = db.execute(
            text("""
                INSERT INTO analysis_artifacts
                    (job_id, user_id, artifact_type, stored_path,
                     content_type, file_size, metadata)
                VALUES
                    (:job_id, :user_id, :artifact_type, :stored_path,
                     :content_type, :file_size, :metadata)
                RETURNING artifact_id
            """),
            {
                "job_id": job_id,
                "user_id": user_id,
                "artifact_type": artifact_type,
                "stored_path": stored_path,
                "content_type": content_type,
                "file_size": file_size,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        ).fetchone()

        db.commit()
        return {
            "job_id": job_id,
            "artifact_id": str(result._mapping["artifact_id"]),
            "artifact_type": artifact_type,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_mask_job_context(mask_job_id: str) -> dict:
    """Colab mask 워커가 처리 전 조회 — result_json 내용 + selected_pii_ids 반환.
    mask_job_id → parent analysis job → pii_result artifact 경로 → 파일 내용 읽기."""
    db = SessionLocal()
    try:
        # mask job의 upload_id 및 target_pii_id 조회
        # ※ target_pii_id 는 전용 컬럼에서 읽는다. (과거에는 message 컬럼을 공유했으나
        #    워커의 진행상태 보고가 message 를 덮어써서 값이 사라지는 버그가 있었음)
        mask_job = db.execute(
            text("SELECT upload_id, target_pii_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": mask_job_id},
        ).fetchone()
        if not mask_job:
            raise ValueError("mask job을 찾을 수 없습니다.")
        upload_id = str(mask_job._mapping["upload_id"])
        target_pii_id = mask_job._mapping["target_pii_id"] or None

        # 같은 upload_id의 완료된 analysis job 찾기
        analysis_job = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs
                WHERE upload_id = :upload_id AND job_type = 'analysis' AND status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
            """),
            {"upload_id": upload_id},
        ).fetchone()
        if not analysis_job:
            raise ValueError("완료된 분석 작업을 찾을 수 없습니다.")
        parent_job_id = str(analysis_job._mapping["job_id"])

        # analysis_artifacts에서 result json 경로 조회 (pii_result 타입)
        artifact = db.execute(
            text("""
                SELECT stored_path FROM analysis_artifacts
                WHERE job_id = :job_id AND artifact_type = 'pii_result'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"job_id": parent_job_id},
        ).fetchone()

        result_json_content = None
        if artifact:
            json_path = artifact._mapping["stored_path"]
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    result_json_content = json.load(f)

        if target_pii_id:
            selected_pii_ids = [target_pii_id]
        else:
            # is_user_selected=True인 pii_id 목록 조회
            rows = db.execute(
                text("""
                    SELECT DISTINCT d.pii_id
                    FROM detections d
                    JOIN replacement_actions ra
                      ON ra.detection_id = d.detection_id AND ra.job_id = d.job_id
                    WHERE d.job_id = :job_id
                      AND ra.is_user_selected = true
                      AND d.pii_id IS NOT NULL
                """),
                {"job_id": parent_job_id},
            ).fetchall()
            selected_pii_ids = [r._mapping["pii_id"] for r in rows]

        return {
            "mask_job_id": mask_job_id,
            "parent_job_id": parent_job_id,
            "upload_id": upload_id,
            "result_json": result_json_content,
            "selected_pii_ids": selected_pii_ids,
        }
    finally:
        db.close()


def save_uploaded_processed_file(
    job_id: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    expires_days: int = 7,
) -> dict:
    """Colab mask 워커가 multipart로 전송한 처리 완료 파일을 서버에 저장 후 processed_files 등록."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        user_id   = row._mapping["user_id"]
        upload_id = str(row._mapping["upload_id"])

        # 서버 저장 경로: 프로젝트 루트/output_file/ 하위
        output_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "output_file")
        )
        os.makedirs(output_dir, exist_ok=True)
        stored_path = os.path.join(output_dir, f"{upload_id}_{filename}")

        with open(stored_path, "wb") as f:
            f.write(file_bytes)
        file_size = len(file_bytes)

        # 현재 활성 구독의 result_retention_days 조회 (없으면 free 플랜, 기본값 7)
        retention_row = db.execute(
            text("""
                SELECT COALESCE(
                    (SELECT p.result_retention_days
                     FROM subscriptions s
                     JOIN plans p ON p.plan_id = s.plan_id
                     WHERE s.user_id = :user_id
                       AND s.status = 'active'
                       AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
                     ORDER BY p.plan_rank DESC LIMIT 1),
                    (SELECT result_retention_days FROM plans WHERE plan_code = 'free' AND status = 'active' LIMIT 1),
                    :default_days
                ) AS days
            """),
            {"user_id": user_id, "default_days": expires_days}
        ).fetchone()
        calculated_expires_days = retention_row._mapping["days"] if retention_row else expires_days

        result = db.execute(
            text("""
                INSERT INTO processed_files
                    (job_id, user_id, filename, stored_path,
                     content_type, file_size, watermark_applied,
                     expires_at)
                VALUES
                    (:job_id, :user_id, :filename, :stored_path,
                     :content_type, :file_size, false,
                     now() + (:calculated_expires_days || ' days')::interval)
                RETURNING processed_file_id
            """),
            {
                "job_id":       job_id,
                "user_id":      user_id,
                "filename":     filename,
                "stored_path":  stored_path,
                "content_type": content_type,
                "file_size":    file_size,
                "calculated_expires_days": calculated_expires_days,
            },
        ).fetchone()

        db.commit()
        return {
            "job_id":              job_id,
            "processed_file_id":   str(result._mapping["processed_file_id"]),
            "stored_path":         stored_path,
            "file_size":           file_size,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_stt_job_id(upload_id: str) -> str | None:
    """upload_id 로 연결된 stt_analysis job_id 반환 (없으면 None)."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs
                WHERE upload_id = :upload_id AND job_type = 'stt_analysis'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"upload_id": upload_id},
        ).fetchone()
        return str(row._mapping["job_id"]) if row else None
    finally:
        db.close()


def get_audio_pii_segments(stt_job_id: str) -> dict:
    """stt_analysis job 의 상태 + voice_pii 탐지 결과 반환.
    로컬 워커가 merger 실행 전에 호출한다."""
    db = SessionLocal()
    try:
        job_row = db.execute(
            text("SELECT status, total_progress FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": stt_job_id},
        ).fetchone()
        if not job_row:
            return {"status": "not_found", "pii_segments": []}

        m = job_row._mapping
        if m["status"] != "completed":
            return {"status": m["status"], "pii_segments": []}

        rows = db.execute(
            text("""
                SELECT label, confidence, start_time_sec, end_time_sec, detected_text, pii_id
                FROM detections
                WHERE job_id = :job_id AND detection_type = 'voice_pii'
                ORDER BY start_time_sec
            """),
            {"job_id": stt_job_id},
        ).fetchall()

        segments = [
            {
                "label":           r._mapping["label"],
                "confidence":      float(r._mapping["confidence"]) if r._mapping["confidence"] else 0.0,
                "start_time_sec":  float(r._mapping["start_time_sec"]) if r._mapping["start_time_sec"] else 0.0,
                "end_time_sec":    float(r._mapping["end_time_sec"]) if r._mapping["end_time_sec"] else 0.0,
                "detected_text":   r._mapping["detected_text"] or "",
                "pii_id":          r._mapping["pii_id"] or "",
            }
            for r in rows
        ]
        return {"status": "completed", "pii_segments": segments}
    finally:
        db.close()


def get_selected_detections_for_mask(mask_job_id: str) -> dict:
    """mask job의 upload_id로 부모 analysis job에서 is_user_selected=True인 detection bbox 반환.
    local_worker가 실제 이미지 마스킹 시 호출."""
    db = SessionLocal()
    try:
        # mask job 정보 조회
        mask_job = db.execute(
            text("SELECT upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": mask_job_id},
        ).fetchone()
        if not mask_job:
            raise ValueError("mask job을 찾을 수 없습니다.")

        upload_id = str(mask_job._mapping["upload_id"])

        # 같은 upload_id를 가진 완료된 analysis job 찾기
        analysis_job = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs
                WHERE upload_id = :upload_id AND job_type = 'analysis' AND status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if not analysis_job:
            return {"detections": [], "file_path": ""}

        parent_job_id = str(analysis_job._mapping["job_id"])

        # 원본 파일 경로
        upload_row = db.execute(
            text("SELECT stored_path FROM uploads WHERE upload_id = :upload_id"),
            {"upload_id": upload_id},
        ).fetchone()
        file_path = upload_row._mapping["stored_path"] if upload_row else ""

        # is_user_selected=True인 detection bbox 조회
        rows = db.execute(
            text("""
                SELECT d.detection_id, d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h,
                       d.polygon_json, d.detected_text, d.label
                FROM detections d
                JOIN replacement_actions ra
                  ON ra.detection_id = d.detection_id AND ra.job_id = d.job_id
                WHERE d.job_id = :job_id
                  AND ra.is_user_selected = true
            """),
            {"job_id": parent_job_id},
        ).fetchall()

        detections = []
        for r in rows:
            m = r._mapping
            detections.append({
                "detection_id":  str(m["detection_id"]),
                "bbox_x":        float(m["bbox_x"]) if m["bbox_x"] is not None else None,
                "bbox_y":        float(m["bbox_y"]) if m["bbox_y"] is not None else None,
                "bbox_w":        float(m["bbox_w"]) if m["bbox_w"] is not None else None,
                "bbox_h":        float(m["bbox_h"]) if m["bbox_h"] is not None else None,
                "polygon_json":  m["polygon_json"],
                "label":         m["label"],
                "detected_text": m["detected_text"],
            })

        return {"detections": detections, "file_path": file_path}
    finally:
        db.close()


def record_heartbeat(
    job_id: str,
    worker_id: str | None,
    worker_type: str,
    ngrok_url: str | None,
    current_stage: str | None,
    progress_percent: int,
    message: str | None,
) -> dict:
    if worker_type and worker_type.startswith("colab"):
        worker_type = "colab"

    db = SessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO job_worker_heartbeats
                    (job_id, worker_id, worker_type, ngrok_url,
                     current_stage, progress_percent, message)
                VALUES
                    (:job_id, :worker_id, :worker_type, :ngrok_url,
                     :current_stage, :progress_percent, :message)
            """),
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "worker_type": worker_type,
                "ngrok_url": ngrok_url,
                "current_stage": current_stage,
                "progress_percent": progress_percent,
                "message": message,
            },
        )
        db.commit()
        return {"job_id": job_id, "recorded": True}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
