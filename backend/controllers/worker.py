from fastapi import Header, Query, UploadFile, File, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from services import worker


class AcceptJobRequest(BaseModel):
    worker_id: str | None = None


class ProgressRequest(BaseModel):
    worker_id: str | None = None
    stage_name: str
    stage_progress: int = Field(ge=0, le=100)
    total_progress: int = Field(ge=0, le=100)
    message: str | None = None


class CompleteRequest(BaseModel):
    worker_id: str | None = None
    detection_count: int = Field(default=0, ge=0)
    # 영상·이미지 메타데이터 (선택 — 없으면 None)
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None


class FailRequest(BaseModel):
    worker_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class HeartbeatRequest(BaseModel):
    job_id: str
    worker_id: str | None = None
    worker_type: str = "colab"
    ngrok_url: str | None = None
    current_stage: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str | None = None


def _check_auth(authorization: str | None):
    try:
        worker.authenticate_worker(authorization)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_401_UNAUTHORIZED)
    return None


def get_next_job_handler(
    worker_type: str | None = Query(default=None, description="local | colab"),
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    result = worker.get_next_job(worker_type=worker_type)
    if result is None:
        return JSONResponse(
            {"job": None, "message": "대기 중인 작업이 없습니다."},
            status_code=status.HTTP_200_OK,
        )
    return JSONResponse({"job": result}, status_code=status.HTTP_200_OK)


def accept_job_handler(
    job_id: str,
    body: AcceptJobRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.accept_job(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"작업 수락에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_file_handler(
    upload_id: str,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        info = worker.get_upload_file_info(upload_id)
        return FileResponse(
            path=info["stored_path"],
            media_type=info["content_type"],
            filename=info["original_filename"],
        )
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"파일 조회에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_job_status_handler(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.get_job_status(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"job 상태 조회에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def download_file_handler(
    upload_id: str,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        info = worker.get_upload_file_info(upload_id)
        return FileResponse(
            path=info["stored_path"],
            media_type=info["content_type"],
            filename=info["original_filename"],
        )
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"파일 다운로드에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def update_progress_handler(
    job_id: str,
    body: ProgressRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.update_job_progress(
            job_id=job_id,
            worker_id=body.worker_id,
            stage_name=body.stage_name,
            stage_progress=body.stage_progress,
            total_progress=body.total_progress,
            message=body.message,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"진행률 업데이트에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def complete_job_handler(
    job_id: str,
    body: CompleteRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.complete_job(
            job_id=job_id,
            worker_id=body.worker_id,
            detection_count=body.detection_count,
            duration_seconds=body.duration_seconds,
            width=body.width,
            height=body.height,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"작업 완료 처리에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def cancelled_job_handler(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    """워커가 처리 중단을 확정 → status='cancelled' 로 마무리."""
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.finalize_cancelled_job(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"작업 취소 확정에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def fail_job_handler(
    job_id: str,
    body: FailRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.fail_job(
            job_id=job_id,
            worker_id=body.worker_id,
            error_code=body.error_code,
            error_message=body.error_message,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"작업 실패 처리에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class STTResultRequest(BaseModel):
    worker_id: str | None = None
    language: str = "unknown"
    full_text: str = ""
    segment_count: int = 0


class PIIResultRequest(BaseModel):
    worker_id: str | None = None
    pii_segments: list = Field(default_factory=list)
    detection_type: str = "voice_pii"  # 'voice_pii' 또는 'visual_pii'


class ArtifactResultRequest(BaseModel):
    worker_id: str | None = None
    artifact_type: str
    stored_path: str
    content_type: str | None = None
    file_size: int | None = None
    metadata: dict | None = None


class ProcessedFileRequest(BaseModel):
    worker_id: str | None = None
    filename: str
    stored_path: str
    content_type: str = "video/mp4"
    file_size: int = 0
    expires_days: int = 7


def save_stt_result_handler(
    job_id: str,
    body: STTResultRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.save_stt_result(
            job_id=job_id,
            language=body.language,
            full_text=body.full_text,
            segment_count=body.segment_count,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"STT 결과 저장에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def save_pii_result_handler(
    job_id: str,
    body: PIIResultRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.save_pii_result(
            job_id=job_id,
            pii_segments=body.pii_segments,
            detection_type=body.detection_type,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"PII 결과 저장에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def save_artifact_handler(
    job_id: str,
    body: ArtifactResultRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.save_artifact(
            job_id=job_id,
            artifact_type=body.artifact_type,
            stored_path=body.stored_path,
            content_type=body.content_type,
            file_size=body.file_size,
            metadata=body.metadata,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"분석 산출물 저장에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def save_processed_file_handler(
    job_id: str,
    body: ProcessedFileRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.save_processed_file(
            job_id=job_id,
            filename=body.filename,
            stored_path=body.stored_path,
            content_type=body.content_type,
            file_size=body.file_size,
            expires_days=body.expires_days,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"결과 파일 등록에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_audio_pii_handler(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    """GET /worker/jobs/{job_id}/results/audio-pii
    로컬 워커가 merger 실행 전에 코랩 STT 결과(voice_pii segments)를 가져오는 엔드포인트."""
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.get_audio_pii_segments(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"audio PII 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_stt_job_id_handler(
    upload_id: str,
    authorization: str | None = Header(default=None),
):
    """GET /worker/uploads/{upload_id}/stt-job
    로컬 워커가 업로드 ID로 코랩 stt_analysis job_id를 조회하는 엔드포인트."""
    if (err := _check_auth(authorization)):
        return err
    try:
        stt_job_id = worker.get_stt_job_id(upload_id)
        return JSONResponse({"stt_job_id": stt_job_id}, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"STT job 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_selected_detections_handler(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    """GET /worker/jobs/{job_id}/selected-detections
    local_worker가 mask job 처리 시 실제 마스킹할 bbox 목록을 조회하는 엔드포인트."""
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.get_selected_detections_for_mask(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"선택 detection 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_mask_context_handler(
    job_id: str,
    authorization: str | None = Header(default=None),
):
    """GET /worker/jobs/{job_id}/mask-context
    Colab mask 워커가 처리 전 호출 — result_json 내용 + selected_pii_ids 반환."""
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.get_mask_job_context(job_id)
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"mask context 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


async def upload_processed_file_handler(
    job_id: str,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    """POST /worker/jobs/{job_id}/results/upload-file
    Colab mask 워커가 처리 완료 파일을 multipart로 업로드 → 서버 저장 + processed_files 등록."""
    if (err := _check_auth(authorization)):
        return err
    try:
        from urllib.parse import unquote
        file_bytes   = await file.read()
        content_type = file.content_type or "application/octet-stream"
        
        # Colab 워커가 전송한 URL 인코딩된 파일명 디코딩
        raw_filename = file.filename or f"result_{job_id}"
        decoded_filename = unquote(raw_filename)
        
        result = worker.save_uploaded_processed_file(
            job_id=job_id,
            filename=decoded_filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"결과 파일 업로드 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def heartbeat_handler(
    body: HeartbeatRequest,
    authorization: str | None = Header(default=None),
):
    if (err := _check_auth(authorization)):
        return err
    try:
        result = worker.record_heartbeat(
            job_id=body.job_id,
            worker_id=body.worker_id,
            worker_type=body.worker_type,
            ngrok_url=body.ngrok_url,
            current_stage=body.current_stage,
            progress_percent=body.progress_percent,
            message=body.message,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"heartbeat 기록에 실패했습니다: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
