from uuid import uuid4

from sqlalchemy import text

from utils.database import SessionLocal

def create_analysis_job(upload_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        upload = db.execute(
            text("SELECT user_id, status FROM uploads WHERE upload_id = :upload_id"),
            {"upload_id": upload_id},
        ).fetchone()

        if not upload:
            raise ValueError("업로드를 찾을 수 없습니다.")

        um = upload._mapping
        if str(um["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")
        if um["status"] != "uploaded":
            raise ValueError(f"분석 요청할 수 없는 업로드 상태입니다: {um['status']}")

        existing = db.execute(
            text("""
                SELECT job_id, status FROM analysis_jobs
                WHERE upload_id = :upload_id
                  AND status NOT IN ('failed', 'cancelled')
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"upload_id": upload_id},
        ).fetchone()

        if existing:
            em = existing._mapping
            return {
                "job_id": str(em["job_id"]),
                "upload_id": upload_id,
                "status": em["status"],
                "already_exists": True,
                "message": "이미 처리 중인 분석 작업이 있습니다.",
            }

        queue_count = db.execute(
            text("SELECT COUNT(*) FROM analysis_jobs WHERE status = 'queued'")
        ).scalar() or 0

        job_id = str(uuid4())
        message = "분석 작업이 대기열에 등록되었습니다."
        db.execute(
            text("""
                INSERT INTO analysis_jobs (
                    job_id, upload_id, user_id, status, job_type,
                    current_stage, queue_position, total_progress, stage_progress, message
                ) VALUES (
                    :job_id, :upload_id, :user_id, 'queued', 'analysis',
                    :current_stage, :queue_position, :total_progress, :stage_progress, :message
                )
            """),
            {
                "job_id": job_id,
                "upload_id": upload_id,
                "user_id": user_id,
                "current_stage": "queued",
                "queue_position": queue_count + 1,
                "total_progress": 0,
                "stage_progress": 0,
                "message": message,
            },
        )
        db.execute(
            text("""
                INSERT INTO job_queue_history
                    (job_id, queue_name, priority, entered_position, status, message)
                VALUES
                    (:job_id, :queue_name, :priority, :entered_position, :status, :message)
            """),
            {
                "job_id": job_id,
                "queue_name": "default",
                "priority": 0,
                "entered_position": queue_count + 1,
                "status": "entered",
                "message": message,
            },
        )

        # 크레딧 차감 없음 — 분석은 무료, 크레딧은 상세보기 진입 시 차감

        # ── 영상 파일이면 코랩용 stt_analysis job 도 함께 생성 ──
        #    로컬 워커: analysis job (프레임 OCR)
        #    코랩 워커: stt_analysis job (음성 STT)
        stt_job_id = None
        media_type = db.execute(
            text("SELECT media_type FROM uploads WHERE upload_id = :upload_id"),
            {"upload_id": upload_id},
        ).scalar()
        if media_type and "video" in (media_type or ""):
            from uuid import uuid4 as _uuid4
            stt_job_id = str(_uuid4())
            db.execute(
                text("""
                    INSERT INTO analysis_jobs (
                        job_id, upload_id, user_id, status, job_type,
                        current_stage, queue_position, total_progress, stage_progress, message
                    ) VALUES (
                        :job_id, :upload_id, :user_id, 'queued', 'stt_analysis',
                        'queued', :queue_position, 0, 0, :message
                    )
                """),
                {
                    "job_id": stt_job_id,
                    "upload_id": upload_id,
                    "user_id": user_id,
                    "queue_position": queue_count + 2,
                    "message": "STT 분석 작업이 대기열에 등록되었습니다.",
                },
            )

        db.commit()

        # 워커에 즉시 처리 신호 전달
        try:
            from core.worker_event import WORKER_EVENT
            WORKER_EVENT.set()
        except Exception:
            pass

        return {
            "job_id": job_id,
            "stt_job_id": stt_job_id,       # 영상이면 코랩용 STT job_id, 이미지면 None
            "upload_id": upload_id,
            "status": "queued",
            "queue_position": queue_count + 1,
            "message": "분석 작업이 대기열에 등록되었습니다.",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cancel_analysis_job(job_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT user_id, status
                FROM analysis_jobs
                WHERE job_id = :job_id
            """),
            {"job_id": job_id},
        ).fetchone()

        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")
        if m["status"] in ("completed", "failed", "cancelled"):
            return {"job_id": job_id, "status": m["status"], "cancel_requested": False}

        message = "작업 취소가 요청되었습니다."
        updated = db.execute(
            text("""
                UPDATE analysis_jobs
                SET cancel_requested = true,
                    status = 'cancelling',
                    message = :message,
                    updated_at = now()
                WHERE job_id = :job_id
                RETURNING job_id, status
            """),
            {"job_id": job_id, "message": message},
        ).fetchone()

        db.execute(
            text("""
                INSERT INTO job_stage_logs
                    (job_id, stage_name, stage_progress, total_progress, status, message, source)
                VALUES
                    (:job_id, 'cancel_requested', 0, 0, 'cancelling', :message, 'backend')
            """),
            {"job_id": job_id, "message": message},
        )

        db.commit()
        return {
            "job_id": str(updated._mapping["job_id"]) if updated else job_id,
            "status": updated._mapping["status"] if updated else "cancelling",
            "cancel_requested": True,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_analysis_job(job_id: str, user_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("""
                SELECT j.job_id, j.upload_id, j.user_id, j.status, j.job_type,
                       j.total_progress, j.current_stage, j.stage_progress,
                       j.queue_position, j.eta_seconds, j.message,
                       j.cancel_requested, j.started_at, j.completed_at,
                       j.error_message, j.error_code, j.created_at,
                       u.original_filename as filename, u.media_type, u.file_size, u.thumbnail_path
                FROM analysis_jobs j
                JOIN uploads u ON j.upload_id = u.upload_id
                WHERE j.job_id = :job_id
            """),
            {"job_id": job_id},
        ).fetchone()

        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")

        m = row._mapping
        if str(m["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        logs = db.execute(
            text("""
                SELECT stage_name, stage_progress, total_progress, status, message,
                       eta_seconds, queue_position, source, created_at
                FROM job_stage_logs
                WHERE job_id = :job_id
                ORDER BY created_at DESC
                LIMIT 10
            """),
            {"job_id": job_id},
        ).fetchall()

        # 동적 큐 순번 계산
        if m["status"] == "queued":
            dynamic_pos = db.execute(
                text("""
                    SELECT COUNT(*) + 1
                    FROM analysis_jobs
                    WHERE status = 'queued' 
                      AND created_at < :created_at
                """),
                {"created_at": m["created_at"]}
            ).scalar()
            current_queue_position = dynamic_pos
        else:
            current_queue_position = None  # 처리 중이거나 완료된 작업은 대기 순번 없음

        result = {
            "job_id": str(m["job_id"]),
            "upload_id": str(m["upload_id"]),
            "status": m["status"],
            "job_type": m["job_type"],
            "total_progress": m["total_progress"],
            "current_stage": m["current_stage"],
            "stage_progress": m["stage_progress"],
            "queue_position": current_queue_position,
            "eta_seconds": m["eta_seconds"],
            "message": m["message"],
            "cancel_requested": m["cancel_requested"],
            "started_at": m["started_at"].isoformat() if m["started_at"] else None,
            "completed_at": m["completed_at"].isoformat() if m["completed_at"] else None,
            "error_message": m["error_message"],
            "error_code": m["error_code"],
            "filename": m["filename"],
            "media_type": m["media_type"],
            "file_size": m["file_size"],
            "thumbnail_url": f"/analysis/uploads/{m['upload_id']}/thumbnail" if m["thumbnail_path"] else None,
            "stage_logs": [
                {
                    "stage_name": l._mapping["stage_name"],
                    "stage_progress": l._mapping["stage_progress"],
                    "total_progress": l._mapping["total_progress"],
                    "status": l._mapping["status"],
                    "message": l._mapping["message"],
                    "eta_seconds": l._mapping["eta_seconds"],
                    "queue_position": l._mapping["queue_position"],
                    "source": l._mapping["source"],
                    "created_at": l._mapping["created_at"].isoformat() if l._mapping["created_at"] else None,
                }
                for l in logs
            ],
        }

        # STT job 정보 조회 (있는 경우)
        stt_job = db.execute(
            text("""
                SELECT status, total_progress, current_stage 
                FROM analysis_jobs 
                WHERE upload_id = :upload_id AND job_type = 'stt_analysis' 
                ORDER BY created_at DESC LIMIT 1
            """),
            {"upload_id": m["upload_id"]},
        ).fetchone()

        if stt_job:
            result["stt_job"] = {
                "status": stt_job._mapping["status"],
                "total_progress": stt_job._mapping["total_progress"],
                "current_stage": stt_job._mapping["current_stage"],
            }
        else:
            result["stt_job"] = None

        return result
    finally:
        db.close()


# ──────────────────────────────────────────────
# 파이프라인 연동 신규 함수
# ──────────────────────────────────────────────

def get_job_detections(job_id: str, user_id: str) -> dict:
    """탐지 결과 목록 + timeline_markers 반환 (AnalysisReport/ReplaceOptions 용)"""
    import json as _json
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id, status, job_type FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        upload_id = str(row._mapping["upload_id"])
        job_status = row._mapping["status"]
        job_type = row._mapping["job_type"]

        rows = db.execute(
            text("""
                SELECT d.detection_id, d.detection_type, d.label, d.confidence,
                       d.frame_no, d.start_time_sec, d.end_time_sec,
                       d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h, d.detected_text,
                       d.review_status, d.pii_id, d.polygon_json,
                       ra.is_user_selected, ra.ra_status
                FROM detections d
                LEFT JOIN (
                    SELECT detection_id, is_user_selected, status as ra_status,
                           ROW_NUMBER() OVER (PARTITION BY detection_id ORDER BY updated_at DESC, created_at DESC) as rn
                    FROM replacement_actions
                ) ra ON ra.detection_id = d.detection_id AND ra.rn = 1
                WHERE d.job_id IN (
                    SELECT job_id FROM (
                        SELECT job_id, ROW_NUMBER() OVER (PARTITION BY job_type ORDER BY created_at DESC) as rn
                        FROM analysis_jobs
                        WHERE upload_id = :upload_id AND job_type = 'analysis'
                    ) t WHERE rn = 1
                )
                ORDER BY d.created_at
            """),
            {"upload_id": upload_id},
        ).fetchall()

        detections = []
        for r in rows:
            m = r._mapping
            # polygon_json: [[x,y]*4] 리스트의 JSON 문자열 → 파싱
            poly_raw = m.get("polygon_json")
            polygon = _json.loads(poly_raw) if poly_raw else None

            detections.append({
                "detection_id": str(m["detection_id"]),
                "pii_id": m["pii_id"],
                "detection_type": m["detection_type"],
                "label": m["label"],
                "confidence": float(m["confidence"]) if m["confidence"] else None,
                "frame_no": m["frame_no"],
                "start_time_sec": float(m["start_time_sec"]) if m["start_time_sec"] else None,
                "end_time_sec": float(m["end_time_sec"]) if m["end_time_sec"] else None,
                "bbox": {
                    "x": float(m["bbox_x"]) if m["bbox_x"] else None,
                    "y": float(m["bbox_y"]) if m["bbox_y"] else None,
                    "w": float(m["bbox_w"]) if m["bbox_w"] else None,
                    "h": float(m["bbox_h"]) if m["bbox_h"] else None,
                },
                # polygons: 각 polygon은 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 형태
                # 여러 단어 박스가 있으면 복수 polygon — SVG <polygon> 렌더링용
                "polygons": polygon,
                "detected_text": m["detected_text"],
                "review_status": m["review_status"],
                "is_selected": bool(m["is_user_selected"]) if m["is_user_selected"] is not None else False,
                "is_masked": m["ra_status"] == "completed",
            })

        # result.json artifact metadata에서 timeline_markers/요약 추출
        artifact_row = db.execute(
            text("""
                SELECT stored_path, metadata
                FROM analysis_artifacts
                WHERE job_id IN (SELECT job_id FROM analysis_jobs WHERE upload_id = :upload_id)
                  AND artifact_type = 'pii_result'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"upload_id": upload_id},
        ).fetchone()

        timeline_markers = []
        summary = {}
        if artifact_row:
            meta = artifact_row._mapping["metadata"]
            if isinstance(meta, str):
                meta = _json.loads(meta)
            if isinstance(meta, dict):
                raw_markers = meta.get("timeline_markers", [])

                # pii_id → detection_id 매핑 빌드 (재생바 마커 선택 시각화용)
                # timeline_markers.id = pii_id, selected 맵 key = detection_id → 불일치 해결
                pii_id_to_det_id = {
                    d["pii_id"]: d["detection_id"]
                    for d in detections
                    if d.get("pii_id")
                }
                timeline_markers = []
                for m in raw_markers:
                    marker = dict(m)
                    # pii_id 기준으로 detection_id로 교체 → 프론트 selected 맵과 매칭
                    pii_id = marker.get("id")
                    if pii_id and pii_id in pii_id_to_det_id:
                        marker["id"] = pii_id_to_det_id[pii_id]
                    timeline_markers.append(marker)

                summary = {
                    "visual_pii_count": meta.get("visual_pii_count", 0),
                    "audio_pii_count": meta.get("audio_pii_count", 0),
                    "total_pii_count": meta.get("total_pii_count", 0),
                    "risk_score": meta.get("risk_score", 0),
                    "risk_level_counts": meta.get("risk_level_counts", {}),
                    "source_name": meta.get("source_name", ""),   # 파일명.확장자 (UUID 포함)
                    "source_type": meta.get("source_type", ""),   # image | video
                    "status": job_status,
                    "job_type": job_type,
                }

        paid_row = db.execute(
            text("""
                SELECT 1 FROM credit_ledger 
                WHERE user_id = :user_id 
                AND source_id = :job_id 
                AND amount < 0 
                AND description LIKE '상세보기%'
            """),
            {"user_id": user_id, "job_id": job_id}
        ).fetchone()
        summary["is_paid"] = bool(paid_row)

        return {
            "job_id": job_id,
            "detections": detections,
            "timeline_markers": timeline_markers,
            "summary": summary,
        }
    finally:
        db.close()


def get_job_result(job_id: str, user_id: str) -> dict:
    """result.json / 상세보기 / tracks artifact 경로 반환 (AnalysisReport 영상 플레이어 용)"""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        upload_id = str(row._mapping["upload_id"])

        artifacts = db.execute(
            text("""
                SELECT artifact_type, artifact_id, stored_path
                FROM analysis_artifacts
                WHERE job_id IN (SELECT job_id FROM analysis_jobs WHERE upload_id = :upload_id)
                  AND artifact_type IN ('pii_result', 'detail_image', 'detail_video', 'detail_tracks')
                ORDER BY created_at DESC
            """),
            {"upload_id": upload_id},
        ).fetchall()

        result = {"job_id": job_id}
        for a in artifacts:
            m = a._mapping
            key = {
                "pii_result":    "result_json_path",
                "detail_image":  "detail_image_path",  # 이미지 상세보기 파일
                "detail_video":  "detail_video_path",  # 영상 상세보기 파일
                "detail_tracks": "detail_tracks_path",
            }.get(m["artifact_type"])
            if key and key not in result:
                result[key] = m["stored_path"]
                result[key.replace("_path", "_id")] = str(m["artifact_id"])

        return result
    finally:
        db.close()


def save_selections(job_id: str, user_id: str, selections: list) -> dict:
    """사용자 선택 목록을 replacement_actions에 저장/갱신 (ReplaceOptions 용)"""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        upload_id = str(row._mapping["upload_id"])
        parent_job = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs 
                WHERE upload_id = :upload_id AND job_type = 'analysis'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"upload_id": upload_id}
        ).fetchone()
        target_job_id = str(parent_job._mapping["job_id"]) if parent_job else job_id

        updated_ids = []
        for sel in selections:
            detection_id = sel.get("detection_id")
            is_selected = bool(sel.get("is_selected", False))

            existing = db.execute(
                text("""
                    SELECT action_id, status FROM replacement_actions
                    WHERE detection_id = :detection_id AND job_id = :target_job_id
                    LIMIT 1
                """),
                {"detection_id": detection_id, "target_job_id": target_job_id},
            ).fetchone()

            if existing:
                # 이미 완료된 항목은 프론트엔드에서 false로 넘어오더라도 무시하고 보존한다. (누적 카운트 유지용)
                if str(existing._mapping["status"]) == "completed":
                    continue
                    
                db.execute(
                    text("""
                        UPDATE replacement_actions
                        SET is_user_selected = :is_selected, updated_at = now()
                        WHERE detection_id = :detection_id AND job_id = :target_job_id
                    """),
                    {"is_selected": is_selected, "detection_id": detection_id, "target_job_id": target_job_id},
                )
                updated_ids.append(str(existing._mapping["action_id"]))
            else:
                result = db.execute(
                    text("""
                        INSERT INTO replacement_actions
                            (detection_id, job_id, action_type, is_user_selected)
                        VALUES
                            (:detection_id, :target_job_id, 'mask', :is_selected)
                        RETURNING action_id
                    """),
                    {"detection_id": detection_id, "target_job_id": target_job_id, "is_selected": is_selected},
                ).fetchone()
                updated_ids.append(str(result._mapping["action_id"]))

        db.commit()
        return {"job_id": job_id, "updated_count": len(updated_ids)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_mask_job(job_id: str, user_id: str, mask_type: str, target_pii_id: str | None = None) -> dict:
    """마스킹 작업(mask_preview / mask_final) 생성 — 기존 워커 큐 패턴 재사용"""
    if mask_type not in ("mask_preview", "mask_final"):
        raise ValueError(f"지원하지 않는 mask_type입니다: {mask_type}")

    db = SessionLocal()
    try:
        parent = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not parent:
            raise ValueError("원본 분석 작업을 찾을 수 없습니다.")
        if str(parent._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        queue_count = db.execute(
            text("SELECT COUNT(*) FROM analysis_jobs WHERE status = 'queued'")
        ).scalar() or 0

        mask_job_id = str(uuid4())
        label = "마스킹 미리보기" if mask_type == "mask_preview" else "마스킹 본처리"

        # [핵심 로직 반영] 대표님의 지시사항: 처리진행 버튼 누르는 시점에 
        # 기존 부모 UID(job_id) 파일 중 상세보기, result 파일만 새 마스킹 UID를 붙여서 즉시 복사!
        if mask_type == "mask_final":
            import os, glob, shutil
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            output_dir = os.path.join(project_root, "output_file")
            
            # 1. 부모의 상세보기 영상 복사
            # 부모가 1번(mask_final)이라면 {job_id}_상세보기 파일이 이미 존재함.
            # 부모가 0번(최초 analysis)이라면 {upload_id}*_상세보기 파일이 존재함.
            detail_files = glob.glob(os.path.join(output_dir, f"{job_id}_상세보기.*"))
            if not detail_files:
                upload_id_str = str(parent._mapping["upload_id"])
                detail_files = glob.glob(os.path.join(output_dir, f"{upload_id_str}*_상세보기.*"))
            
            for detail_file in detail_files:
                ext = os.path.splitext(detail_file)[1]
                new_detail_path = os.path.join(output_dir, f"{mask_job_id}_상세보기{ext}")
                shutil.copy2(detail_file, new_detail_path)
                
            # 2. 부모의 result.json 복사
            # 부모가 mask_final 이면 {job_id}_result.json 이고, 최초면 {upload_id}_result.json 일 수 있음.
            # get_mask_context_handler 등에서 원본 json을 부를때 참조할 수도 있으므로 복사.
            json_files = glob.glob(os.path.join(output_dir, f"{job_id}_result.json"))
            if not json_files:
                upload_id_str = str(parent._mapping["upload_id"])
                json_files = glob.glob(os.path.join(output_dir, f"{upload_id_str}*_result.json"))
                
            for jf in json_files:
                new_json_path = os.path.join(output_dir, f"{mask_job_id}_result.json")
                shutil.copy2(jf, new_json_path)

        # message 는 진행상태 표시 전용(워커가 덮어씀). target_pii_id 는 별도 전용 컬럼에 저장하여
        # 진행상태 보고로 값이 사라지지 않도록 분리한다(영상 개별 PII 미리보기 누락 버그 수정).
        message_str = f"{label} 작업이 대기열에 등록되었습니다."
        db.execute(
            text("""
                INSERT INTO analysis_jobs (
                    job_id, upload_id, user_id, status, job_type,
                    current_stage, queue_position, total_progress, stage_progress, message,
                    target_pii_id
                ) VALUES (
                    :job_id, :upload_id, :user_id, 'queued', :job_type,
                    'queued', :queue_position, 0, 0, :message,
                    :target_pii_id
                )
            """),
            {
                "job_id": mask_job_id,
                "upload_id": str(parent._mapping["upload_id"]),
                "user_id": user_id,
                "job_type": mask_type,
                "queue_position": queue_count + 1,
                "message": message_str,
                "target_pii_id": target_pii_id,   # None 이면 사용자 선택(is_user_selected) 전체 대상
            },
        )
        db.commit()

        # 워커에 즉시 처리 신호 전달
        try:
            from core.worker_event import WORKER_EVENT
            WORKER_EVENT.set()
        except Exception:
            pass

        return {
            "mask_job_id": mask_job_id,
            "parent_job_id": job_id,
            "job_type": mask_type,
            "status": "queued",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_result_file(job_id: str, user_id: str) -> dict:
    """최종 처리 결과물 경로 반환 (Download 페이지 용)"""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        file_row = db.execute(
            text("""
                SELECT processed_file_id AS file_id,
                       filename          AS original_filename,
                       stored_path, file_size,
                       expires_at, created_at
                FROM processed_files
                WHERE job_id = :job_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"job_id": job_id},
        ).fetchone()

        if not file_row:
            raise ValueError("처리 완료된 결과물이 없습니다.")

        m = file_row._mapping
        return {
            "job_id": job_id,
            "file_id": str(m["file_id"]),
            "original_filename": m["original_filename"],
            "stored_path": m["stored_path"],
            "file_size": m["file_size"],
            "expires_at": m["expires_at"].isoformat() if m["expires_at"] else None,
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        }
    finally:
        db.close()


def download_result_file(
    job_id: str,
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """처리 완료된 파일의 경로·파일명 반환 및 다운로드 이력(download_events) 기록"""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        file_row = db.execute(
            text("""
                SELECT processed_file_id, filename AS original_filename,
                       stored_path, content_type, expires_at
                FROM processed_files
                WHERE job_id = :job_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"job_id": job_id},
        ).fetchone()

        if not file_row:
            raise ValueError("처리 완료된 파일이 없습니다.")

        m = file_row._mapping

        # 만료 여부 확인
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        expires_at = m["expires_at"]
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        is_expired = expires_at and now > expires_at

        # 다운로드 이력 기록
        import logging
        _logger = logging.getLogger(__name__)
        try:
            db.execute(
                text("""
                    INSERT INTO download_events
                        (processed_file_id, user_id, ip_address, user_agent, result)
                    VALUES
                        (:processed_file_id, :user_id, :ip_address, :user_agent, :result)
                """),
                {
                    "processed_file_id": str(m["processed_file_id"]),
                    "user_id": user_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "result": "expired" if is_expired else "success",
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            _logger.warning("download_events 기록 실패 (파일 서빙은 계속): %s", e)

        if is_expired:
            raise ValueError("다운로드 만료된 파일입니다.")

        return {
            "stored_path":       m["stored_path"],
            "original_filename": m["original_filename"] or "result",
            "content_type":      m["content_type"] or "application/octet-stream",
        }
    finally:
        db.close()


def reset_selections(job_id: str, user_id: str) -> dict:
    """마스킹 선택 전체 초기화 — 미리보기에서 뒤로가기 시 모든 is_user_selected를 False로.
    사용자가 ReplaceOptions로 돌아가 다시 체크할 수 있도록 상태 초기화."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        upload_id = str(row._mapping["upload_id"])
        parent_job = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs 
                WHERE upload_id = :upload_id AND job_type = 'analysis'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"upload_id": upload_id}
        ).fetchone()
        target_job_id = str(parent_job._mapping["job_id"]) if parent_job else job_id

        result = db.execute(
            text("""
                UPDATE replacement_actions
                SET is_user_selected = false, updated_at = now()
                WHERE job_id = :target_job_id
            """),
            {"target_job_id": target_job_id},
        )
        db.commit()
        return {"job_id": job_id, "reset_count": result.rowcount}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_mask_previews(job_id: str, user_id: str) -> dict:
    """해당 작업(upload_id)과 연관된 모든 mask_preview 결과물(파일 및 DB 레코드) 삭제"""
    import os
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT user_id, upload_id FROM analysis_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).fetchone()
        if not row:
            raise ValueError("분석 작업을 찾을 수 없습니다.")
        if str(row._mapping["user_id"]) != user_id:
            raise PermissionError("접근 권한이 없습니다.")

        upload_id = str(row._mapping["upload_id"])

        # 1. 해당 upload_id의 mask_preview job들 찾기
        preview_jobs = db.execute(
            text("""
                SELECT job_id FROM analysis_jobs
                WHERE upload_id = :upload_id AND job_type = 'mask_preview'
            """),
            {"upload_id": upload_id}
        ).fetchall()

        preview_job_ids = [str(pj._mapping["job_id"]) for pj in preview_jobs]

        deleted_count = 0
        if preview_job_ids:
            # 2. 결과물 파일 정보 조회 (job_id도 함께 가져오기 위함)
            files = db.execute(
                text("""
                    SELECT processed_file_id, stored_path, job_id
                    FROM processed_files
                    WHERE job_id = ANY(:job_ids)
                """),
                {"job_ids": preview_job_ids}
            ).fetchall()

            successful_job_ids = []

            # 3. 실제 파일 삭제
            for f in files:
                path = f._mapping["stored_path"]
                j_id = str(f._mapping["job_id"])
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        deleted_count += 1
                        successful_job_ids.append(j_id)
                    except Exception as e:
                        print(f"Failed to delete preview file {path}: {e}")
                else:
                    successful_job_ids.append(j_id)

            # 4. 파일 삭제에 성공한 작업만 DB에서 레코드 삭제 (순서 준수: FK 등 확인)
            if successful_job_ids:
                db.execute(
                    text("DELETE FROM job_stage_logs WHERE job_id = ANY(:job_ids)"),
                    {"job_ids": successful_job_ids}
                )
                db.execute(
                    text("DELETE FROM processed_files WHERE job_id = ANY(:job_ids)"),
                    {"job_ids": successful_job_ids}
                )
                db.execute(
                    text("DELETE FROM analysis_jobs WHERE job_id = ANY(:job_ids)"),
                    {"job_ids": successful_job_ids}
                )

        # 5. 캐싱된 클립 영상들(_clip_*.mp4) 도 함께 삭제
        import glob
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "output_file"))
        clip_files = glob.glob(os.path.join(output_dir, f"{upload_id}*_clip_*.mp4"))
        for clip_path in clip_files:
            try:
                os.remove(clip_path)
            except Exception:
                pass

        db.commit()
        return {"job_id": job_id, "deleted_files": deleted_count, "deleted_jobs": len(preview_job_ids)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_dashboard_data(user_id: str) -> dict:
    from services.payment import get_my_credit_balance
    from services.subscription import resolve_current_plan
    db = SessionLocal()
    try:
        completed_jobs = db.execute(
            text("SELECT COUNT(*) FROM analysis_jobs WHERE user_id = :user_id AND status = 'completed'"),
            {"user_id": user_id}
        ).scalar() or 0
        
        total_detections = db.execute(
            text("""
                SELECT COUNT(*) FROM detections d
                JOIN analysis_jobs j ON d.job_id = j.job_id
                WHERE j.user_id = :user_id AND j.job_type = 'analysis'
            """),
            {"user_id": user_id}
        ).scalar() or 0
        
        total_replacements = db.execute(
            text("""
                SELECT COUNT(*) FROM replacement_actions r
                JOIN analysis_jobs j ON r.job_id = j.job_id
                WHERE j.user_id = :user_id AND r.is_user_selected = true AND j.job_type = 'analysis'
            """),
            {"user_id": user_id}
        ).scalar() or 0

        uploads_rs = db.execute(
            text("""
                WITH ranked_ocr AS (
                    SELECT job_id, upload_id, status, total_progress, created_at,
                           ROW_NUMBER() OVER(PARTITION BY upload_id ORDER BY created_at DESC) as rn
                    FROM analysis_jobs
                    WHERE job_type = 'analysis'
                ),
                ranked_stt AS (
                    SELECT job_id, upload_id, status, total_progress, created_at,
                           ROW_NUMBER() OVER(PARTITION BY upload_id ORDER BY created_at DESC) as rn
                    FROM analysis_jobs
                    WHERE job_type = 'stt_analysis'
                ),
                ranked_mask AS (
                    SELECT job_id, upload_id, status, total_progress, created_at,
                           ROW_NUMBER() OVER(PARTITION BY upload_id ORDER BY created_at DESC) as rn
                    FROM analysis_jobs
                    WHERE job_type = 'mask_final'
                )
                SELECT u.upload_id, u.original_filename as filename, u.media_type, u.created_at, u.file_size, u.thumbnail_path,
                       COALESCE(m.job_id, o.job_id) as job_id,
                       CASE 
                           WHEN m.job_id IS NOT NULL THEN m.status
                           WHEN o.status = 'completed' AND (s.status IS NULL OR s.status = 'completed' OR s.status = 'failed') THEN 'review_pending'
                           ELSE o.status
                       END as current_status,
                       CASE
                           WHEN m.job_id IS NOT NULL THEN COALESCE(m.total_progress, 0)
                           WHEN u.media_type LIKE 'video%' AND s.job_id IS NOT NULL THEN 
                               (COALESCE(o.total_progress, 0) + COALESCE(s.total_progress, 0)) / 2
                           ELSE COALESCE(o.total_progress, 0)
                       END as progress,
                       CASE WHEN m.job_id IS NOT NULL THEN 'mask_final' ELSE 'analysis' END as job_type,
                       s.job_id as stt_job_id,
                       COALESCE(m.created_at, o.created_at, u.created_at) as latest_activity
                FROM uploads u
                LEFT JOIN ranked_ocr o ON u.upload_id = o.upload_id AND o.rn = 1
                LEFT JOIN ranked_stt s ON u.upload_id = s.upload_id AND s.rn = 1
                LEFT JOIN ranked_mask m ON u.upload_id = m.upload_id AND m.rn = 1
                WHERE u.user_id = :user_id AND o.job_id IS NOT NULL
                ORDER BY latest_activity DESC
            """),
            {"user_id": user_id}
        ).fetchall()
        
        active_jobs = []
        recent_jobs = []

        for r in uploads_rs:
            m = r._mapping
            job_obj = {
                "upload_id": str(m["upload_id"]),
                "job_id": str(m["job_id"]) if m["job_id"] else None,
                "stt_job_id": str(m["stt_job_id"]) if m["stt_job_id"] else None,
                "status": m["current_status"],
                "job_type": m["job_type"],
                "progress": m["progress"],
                "created_at": m["latest_activity"].isoformat() if m["latest_activity"] else None,
                "filename": m["filename"],
                "media_type": m["media_type"],
                "file_size": m["file_size"],
                "thumbnail_url": f"/analysis/uploads/{m['upload_id']}/thumbnail" if m.get("thumbnail_path") else None,
            }
            
            if m["current_status"] == "completed" and m["job_type"] == "mask_final":
                pass
            else:
                active_jobs.append(job_obj)

        recent_jobs = get_history_list(user_id, limit=5, offset=0)["items"]

        # 월 1일 초기화되는 무료 처리 횟수 계산
        import datetime
        current_month_start = datetime.datetime.now(datetime.timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        used_free_limit = db.execute(
            text("""
                SELECT COUNT(*) FROM analysis_jobs 
                WHERE user_id = :user_id 
                AND created_at >= :current_month_start
                AND job_type = 'analysis'
            """),
            {"user_id": user_id, "current_month_start": current_month_start}
        ).scalar() or 0

        # Fetch free balance and pending AI refund
        balances = db.execute(
            text("""
                SELECT free_balance, pending_ai_refund_usage
                FROM user_credit_balances
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()
        
        free_balance = int(balances._mapping["free_balance"]) if balances else 0
        pending_ai_refund_usage = int(balances._mapping["pending_ai_refund_usage"]) if balances else 0

        # Calculate expected refund (10%)
        expected_ai_refund = round(pending_ai_refund_usage * 0.1)

        return {
            "stats": {
                "completed_jobs": completed_jobs,
                "total_detections": total_detections,
                "total_replacements": total_replacements,
                "free_balance": free_balance,
                "used_free_limit": used_free_limit,
                "expected_ai_refund": expected_ai_refund
            },
            "active_jobs": active_jobs,
            "recent_jobs": recent_jobs
        }
    finally:
        db.close()

def get_history_list(user_id: str, limit: int = 10, offset: int = 0, search: str | None = None, sort: str = "desc") -> dict:
    db = SessionLocal()
    try:
        search_condition = ""
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        
        if search:
            search_condition = "AND (u.original_filename ILIKE :search OR CAST(j.created_at AS TEXT) ILIKE :search)"
            params["search"] = f"%{search}%"

        order_by = "j.created_at DESC" if sort != "asc" else "j.created_at ASC"

        total_count = db.execute(
            text(f"""
                SELECT COUNT(*) FROM analysis_jobs j
                JOIN uploads u ON j.upload_id = u.upload_id
                WHERE u.user_id = :user_id
                  AND j.job_type = 'mask_final' AND j.status = 'completed'
                  {search_condition}
            """),
            params
        ).scalar() or 0

        jobs_rs = db.execute(
            text(f"""
                SELECT j.job_id, j.status, j.job_type, j.created_at, j.total_progress,
                       u.original_filename as filename, u.media_type, u.file_size, u.upload_id, u.thumbnail_path,
                       (SELECT job_id FROM analysis_jobs p WHERE p.upload_id = j.upload_id AND p.job_type IN ('analysis', 'stt_analysis') ORDER BY CASE WHEN p.job_type = 'analysis' THEN 1 ELSE 2 END LIMIT 1) as stt_job_id,
                       (SELECT expires_at FROM processed_files pf WHERE pf.job_id = j.job_id ORDER BY created_at DESC LIMIT 1) as expires_at
                FROM analysis_jobs j
                JOIN uploads u ON j.upload_id = u.upload_id
                WHERE u.user_id = :user_id AND j.job_type = 'mask_final' AND j.status = 'completed'
                {search_condition}
                ORDER BY {order_by}
                LIMIT :limit OFFSET :offset
            """),
            params
        ).fetchall()

        jobs = []
        for r in jobs_rs:
            m = r._mapping
            det_stats = db.execute(
                text("""
                    SELECT 
                        COUNT(d.detection_id) as total,
                        SUM(CASE WHEN ra.is_user_selected = true AND ra.status = 'completed' THEN 1 ELSE 0 END) as replaced
                    FROM detections d
                    LEFT JOIN (
                        SELECT detection_id, is_user_selected, status,
                               ROW_NUMBER() OVER(PARTITION BY detection_id ORDER BY updated_at DESC) as rn
                        FROM replacement_actions
                    ) ra ON d.detection_id = ra.detection_id AND ra.rn = 1
                    WHERE d.job_id = :stt_job_id
                """),
                {"stt_job_id": m["stt_job_id"]}
            ).fetchone()._mapping
            
            jobs.append({
                "upload_id": str(m["upload_id"]),
                "job_id": str(m["job_id"]),
                "stt_job_id": str(m["stt_job_id"]) if m["stt_job_id"] else None,
                "status": m["status"],
                "job_type": m["job_type"],
                "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                "progress": m["total_progress"],
                "filename": m["filename"],
                "media_type": m["media_type"],
                "file_size": m["file_size"],
                "thumbnail_url": f"/analysis/uploads/{m['upload_id']}/thumbnail" if m.get("thumbnail_path") else None,
                "detected": int(det_stats["total"] or 0),
                "replaced": int(det_stats["replaced"] or 0),
                "expires_at": m["expires_at"].isoformat() if m.get("expires_at") else None
            })

        return {
            "total": total_count,
            "items": jobs,
            "page": (offset // limit) + 1,
            "size": limit
        }
    finally:
        db.close()

def delete_analysis_job(job_id: str, user_id: str):
    db = SessionLocal()
    try:
        # 소유권 확인
        job = db.execute(
            text("""
                SELECT j.job_id, u.user_id 
                FROM analysis_jobs j 
                JOIN uploads u ON j.upload_id = u.upload_id 
                WHERE j.job_id = :job_id AND u.user_id = :user_id
            """),
            {"job_id": job_id, "user_id": user_id}
        ).fetchone()
        
        if not job:
            raise ValueError("해당 작업을 찾을 수 없거나 권한이 없습니다.")

        pf_rows = db.execute(
            text("""
                SELECT processed_file_id, stored_path, expires_at
                FROM processed_files
                WHERE job_id = :job_id AND deleted_at IS NULL
            """),
            {"job_id": job_id}
        ).fetchall()
        pf_records = [r._mapping for r in pf_rows]

        try:
            import os, glob, shutil
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            g_drive_root = os.path.abspath(os.path.join(project_root, "..", "..", ".."))
            
            directories_to_clean = [
                os.path.join(project_root, "output_file"),
                os.path.join(g_drive_root, "garim_downloads"),
                os.path.join(g_drive_root, "garim_downloads", ".ipynb_checkpoints"),
                os.path.join(g_drive_root, "final_PJ_model", "output_file"),
                os.path.join(g_drive_root, "final_PJ_model", "ocr_video_output"),
                os.path.join(g_drive_root, "final_PJ_model", "ocr_image_output"),
            ]
            
            for d in directories_to_clean:
                if not os.path.exists(d):
                    continue
                for file_path in glob.glob(os.path.join(d, f"{job_id}*")):
                    try:
                        if os.path.isdir(file_path):
                            shutil.rmtree(file_path, ignore_errors=True)
                        else:
                            os.remove(file_path)
                    except Exception:
                        pass
        except Exception:
            pass
            
        db.execute(text("DELETE FROM analysis_artifacts WHERE job_id = :job_id"), {"job_id": job_id})
        
        db.execute(text("""
            DELETE FROM download_events
            WHERE processed_file_id IN (
                SELECT processed_file_id FROM processed_files WHERE job_id = :job_id
            )
        """), {"job_id": job_id})
        
        db.execute(text("DELETE FROM processed_files WHERE job_id = :job_id"), {"job_id": job_id})
        db.execute(text("DELETE FROM worker_tasks WHERE job_id = :job_id"), {"job_id": job_id})
        db.execute(text("DELETE FROM job_stage_logs WHERE job_id = :job_id"), {"job_id": job_id})
        db.execute(text("DELETE FROM job_queue_history WHERE job_id = :job_id"), {"job_id": job_id})
        db.execute(text("DELETE FROM analysis_jobs WHERE job_id = :job_id"), {"job_id": job_id})

        for pf in pf_records:
            try:
                db.execute(
                    text("""
                        INSERT INTO deletion_events
                            (target_type, target_id, target_path,
                             delete_reason, scheduled_delete_at,
                             deleted_at, result,
                             actor_type, actor_user_id)
                        VALUES
                            ('processed_file', :target_id, :target_path,
                             'user_request', :scheduled_at,
                             now(), 'success',
                             'user', :actor_user_id)
                    """),
                    {
                        "target_id": str(pf["processed_file_id"]),
                        "target_path": pf["stored_path"],
                        "scheduled_at": pf["expires_at"],
                        "actor_user_id": user_id,
                    },
                )
            except Exception:
                pass
                
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def delete_upload_and_jobs(upload_id: str, user_id: str):
    db = SessionLocal()
    try:
        # 소유권 확인
        upload = db.execute(
            text("SELECT * FROM uploads WHERE upload_id = :upload_id AND user_id = :user_id"),
            {"upload_id": upload_id, "user_id": user_id}
        ).fetchone()
        if not upload:
            raise ValueError("해당 업로드 건을 찾을 수 없습니다.")

        # 연관된 job_id 목록 조회
        jobs = db.execute(
            text("SELECT job_id FROM analysis_jobs WHERE upload_id = :upload_id"),
            {"upload_id": upload_id}
        ).fetchall()
        job_ids = [str(j[0]) for j in jobs]

        # deletion_events 기록용: 삭제 전에 processed_files 정보 사전 조회
        # (DELETE 후에는 조회 불가하므로 먼저 수집; job_id별 루프로 안전하게 처리)
        pf_records = []
        for jid in job_ids:
            pf_rows = db.execute(
                text("""
                    SELECT processed_file_id, stored_path, expires_at
                    FROM processed_files
                    WHERE job_id = :job_id AND deleted_at IS NULL
                """),
                {"job_id": jid}
            ).fetchall()
            pf_records.extend([r._mapping for r in pf_rows])

        # S3 / local files / Colab files
        try:
            import os
            import glob
            import shutil
            
            # Delete original file and chunks in storage
            stored_path = upload._mapping.get('stored_path')
            if stored_path and os.path.exists(stored_path):
                os.remove(stored_path)
                    
            temp_dir = upload._mapping.get('temp_dir_path')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                
            # Define all output directories to clean up
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            g_drive_root = os.path.abspath(os.path.join(project_root, "..", "..", ".."))
            
            directories_to_clean = [
                os.path.join(project_root, "output_file"),
                os.path.join(g_drive_root, "garim_downloads"),
                os.path.join(g_drive_root, "garim_downloads", ".ipynb_checkpoints"),
                os.path.join(g_drive_root, "final_PJ_model", "output_file"),
                os.path.join(g_drive_root, "final_PJ_model", "ocr_video_output"),
                os.path.join(g_drive_root, "final_PJ_model", "ocr_image_output"),
            ]
            
            prefixes_to_delete = [upload_id, f"upload_{upload_id}"] + job_ids
            
            for d in directories_to_clean:
                if not os.path.exists(d):
                    continue
                for prefix in prefixes_to_delete:
                    for file_path in glob.glob(os.path.join(d, f"{prefix}*")):
                        try:
                            if os.path.isdir(file_path):
                                shutil.rmtree(file_path, ignore_errors=True)
                            else:
                                os.remove(file_path)
                        except Exception:
                            pass
                            
        except Exception as e:
            pass # ignore storage errors
        
        # Delete related records
        for j in jobs:
            jid = j[0]
            # delete detections and replacement_actions
            db.execute(text("DELETE FROM replacement_actions WHERE detection_id IN (SELECT detection_id FROM detections WHERE job_id = :job_id)"), {"job_id": jid})
            db.execute(text("DELETE FROM detections WHERE job_id = :job_id"), {"job_id": jid})
            # delete artifacts
            db.execute(text("DELETE FROM analysis_artifacts WHERE job_id = :job_id"), {"job_id": jid})
            # download_events는 processed_files를 FK로 참조하므로 먼저 삭제
            db.execute(text("""
                DELETE FROM download_events
                WHERE processed_file_id IN (
                    SELECT processed_file_id FROM processed_files WHERE job_id = :job_id
                )
            """), {"job_id": jid})
            # delete processed_files
            db.execute(text("DELETE FROM processed_files WHERE job_id = :job_id"), {"job_id": jid})
            # worker tasks
            db.execute(text("DELETE FROM worker_tasks WHERE job_id = :job_id OR upload_id = :upload_id"), {"job_id": jid, "upload_id": upload_id})
        
        # delete analysis_jobs
        db.execute(text("DELETE FROM analysis_jobs WHERE upload_id = :upload_id"), {"upload_id": upload_id})

        # delete upload_chunks
        db.execute(text("DELETE FROM upload_chunks WHERE upload_id = :upload_id"), {"upload_id": upload_id})

        # delete upload
        db.execute(text("DELETE FROM uploads WHERE upload_id = :upload_id"), {"upload_id": upload_id})

        # 사용자 임의삭제 이력 기록 — actor_type='user' / delete_reason='user_request' 로
        # 자동만료 삭제(actor_type='system' / delete_reason='expired')와 명확히 구별
        for pf in pf_records:
            try:
                db.execute(
                    text("""
                        INSERT INTO deletion_events
                            (target_type, target_id, target_path,
                             delete_reason, scheduled_delete_at,
                             deleted_at, result,
                             actor_type, actor_user_id)
                        VALUES
                            ('processed_file', :target_id, :target_path,
                             'user_request', :scheduled_at,
                             now(), 'success',
                             'user', :actor_user_id)
                    """),
                    {
                        "target_id": str(pf["processed_file_id"]),
                        "target_path": pf["stored_path"],
                        "scheduled_at": pf["expires_at"],   # 원래 만료 예정 시각 (참고용)
                        "actor_user_id": user_id,
                    },
                )
            except Exception as e:
                # 이력 기록 실패는 경고만 남기고 삭제 자체는 계속 진행
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "deletion_events 기록 실패(사용자 삭제) — pf_id=%s err=%s",
                    pf.get("processed_file_id"), e,
                )

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def charge_detail_access(job_id: str, user_id: str, file_type: str) -> dict:
    from utils.database import SessionLocal
    from sqlalchemy import text
    from services.payment import _spend_user_credits
    
    db = SessionLocal()
    try:
        # Check ownership
        job = db.execute(
            text("SELECT * FROM analysis_jobs WHERE job_id = :job_id AND user_id = :user_id"),
            {"job_id": job_id, "user_id": user_id}
        ).fetchone()
        
        if not job:
            raise PermissionError("해당 작업에 접근할 수 없습니다.")
            
        # Check if already paid (re-access)
        paid = db.execute(
            text("""
                SELECT 1 FROM credit_ledger 
                WHERE user_id = :user_id 
                AND source_id = :job_id 
                AND amount < 0 
                AND description LIKE '상세보기%'
            """),
            {"user_id": user_id, "job_id": job_id}
        ).fetchone()
        
        is_reaccess = bool(paid)
        
        if file_type == "video":
            cost = 0 if is_reaccess else 3
        else:
            cost = 0 if is_reaccess else 2
            
        desc = f"상세보기 재접근 ({file_type})" if is_reaccess else f"상세보기 접근 ({file_type})"
        
        remaining = 0
        if cost > 0:
            # _spend_user_credits will raise ValueError if insufficient credits
            remaining = _spend_user_credits(db, user_id, cost, job_id, desc)
        else:
            bal = db.execute(text("SELECT balance FROM user_credit_balances WHERE user_id = :user_id"), {"user_id": user_id}).fetchone()
            remaining = float(bal[0]) if bal else 0.0
            
        db.commit()
        
        return {
            "credits_used": cost,
            "remaining_credits": remaining,
            "is_reaccess": is_reaccess
        }
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
