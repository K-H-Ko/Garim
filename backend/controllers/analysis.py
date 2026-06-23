import logging
import os
import subprocess
from fastapi import Cookie, Request, status
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from services import auth, analysis


class CreateJobRequest(BaseModel):
    upload_id: str


class SelectionsRequest(BaseModel):
    selections: list  # [{ detection_id: str, is_selected: bool }]


class MaskPreviewRequest(BaseModel):
    pii_id: str | None = None


class DetailAccessRequest(BaseModel):
    file_type: str  # "image" | "video"


def create_job_handler(
    body: CreateJobRequest,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.create_analysis_job(
            upload_id=body.upload_id,
            user_id=str(current_user["id"]),
        )
        code = status.HTTP_200_OK if result.get("already_exists") else status.HTTP_201_CREATED
        return JSONResponse(result, status_code=code)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"analysis job creation failed: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_job_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_analysis_job(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"analysis job lookup failed: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def cancel_job_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.cancel_analysis_job(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"analysis job cancel failed: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_job_detections_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_job_detections(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"탐지 결과 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_job_result_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_job_result(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"결과 파일 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _make_detail_clip(detail_video_path: str, result_json_path: str, pii_id: str):
    """[원본 미리보기 클립 생성] 상세보기 영상에서 해당 pii_id 탐지구간 ±3초(총 6초)를 잘라 클립 생성.
    콜랩 워커(colab_pipeline_mask.preview_video)와 '동일한 구간 계산'을 백엔드에서 재현하여,
    원본 클립과 마스킹 클립의 시작/끝 시간축을 정확히 일치시킨다(가림바 비교용).
    - 구간: 해당 PII keyframe 최소 frame(anchor) ± (fps*3) → preview_video 와 동일 로직
    - 결과는 같은 폴더에 {영상}_clip_{pii_id}.mp4 로 캐싱 → 재요청 시 즉시 반환
    실패(파일/구간 없음) 시 None 반환 → 호출부에서 전체 영상으로 fallback."""
    import json as _json
    import subprocess as _sp
    # 입력 파일 검증
    if not (detail_video_path and os.path.exists(detail_video_path)):
        return None
    if not (result_json_path and os.path.exists(result_json_path)):
        return None
    try:
        with open(result_json_path, encoding="utf-8") as f:
            rj = _json.load(f)
    except Exception:
        return None

    fps = float(rj.get("fps") or 30.0)
    total = int(rj.get("total_frames") or 0)
    # 해당 pii_id 그룹의 keyframe 중 최소 frame = anchor (preview_video 의 events[0] 과 동일)
    grp = next((g for g in rj.get("pii_groups", []) if g.get("pii_id") == pii_id), None)
    if not grp or not grp.get("keyframes"):
        return None  # 영상 keyframe 없는 PII(예: 음성 PII) → 전체 영상 fallback
    try:
        anchor = min(int(kf["frame"]) for kf in grp["keyframes"])
    except Exception:
        return None

    margin = int(fps * 3.0)                       # PREVIEW_VIDEO_MARGIN_SEC = 3.0 와 동일
    lo = max(0, anchor - margin)
    hi = (min(total - 1, anchor + margin) if total else anchor + margin)
    start_sec = lo / fps
    dur_sec = max(0.1, (hi - lo) / fps)

    # 캐싱 경로 — pii_id 의 특수문자는 안전하게 치환
    base = os.path.splitext(detail_video_path)[0]
    safe = "".join(c if c.isalnum() else "_" for c in str(pii_id))
    clip_path = f"{base}_clip_{safe}.mp4"
    if os.path.exists(clip_path):
        return clip_path

    # imageio-ffmpeg 번들 ffmpeg 로 [start_sec, start_sec+dur_sec] 구간만 재인코딩하여 잘라낸다.
    # 재인코딩(libx264)으로 정확한 시작 프레임 + 브라우저 호환(yuv420p/faststart) 보장.
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start_sec:.3f}", "-i", detail_video_path,
        "-t", f"{dur_sec:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-map_metadata", "-1",  # GPS·카메라·날짜 등 모든 메타데이터 명시적 제거
        "-c:a", "aac",
        clip_path,
    ]
    try:
        _sp.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    except Exception:
        return None
    return clip_path if os.path.exists(clip_path) else None


def get_detail_file_handler(
    job_id: str,
    file_type: str = "image",   # "image" | "video"
    pii_id: str | None = None,  # 영상 개별 PII 미리보기 시: 해당 구간 6초 클립으로 서빙
    access_token: str | None = Cookie(default=None),
):
    """상세보기 파일 서빙 — {stem}_상세보기.jpg(이미지) / {stem}_상세보기.mp4(영상)
    DB artifact 경로 우선 → 없으면 output_file 폴더에서 업로드 파일명 기반 fallback 탐색.
    영상 + pii_id 지정 시: 마스킹 미리보기 클립과 동일한 6초 구간만 잘라서 반환(시간축 일치)."""
    import glob as _glob
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_job_result(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        # file_type에 따라 상세보기 파일 경로 선택
        if file_type == "video":
            file_path = result.get("detail_video_path")
            media_type = "video/mp4"
            suffix = "_상세보기.mp4"
        else:
            file_path = result.get("detail_image_path")
            media_type = "image/jpeg"
            suffix = "_상세보기.jpg"

        # [영상 개별 PII 미리보기] 해당 PII 탐지구간 6초 클립으로 서빙 → 마스킹 클립과 시간축 일치
        if file_type == "video" and pii_id:
            clip = _make_detail_clip(file_path, result.get("result_json_path"), pii_id)
            if clip and os.path.exists(clip):
                return FileResponse(clip, media_type=media_type, filename=os.path.basename(clip))
            # 클립 생성 실패(음성 PII 등) 시 아래 전체 영상 서빙으로 fallback

        # DB artifact 경로에 파일이 있으면 즉시 반환
        if file_path and os.path.exists(file_path):
            return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))

        # fallback: output_file 폴더에서 job_id 또는 upload_id 기반으로 파일 탐색
        from utils.database import SessionLocal
        from sqlalchemy import text as _text
        db = SessionLocal()
        try:
            row = db.execute(
                _text("SELECT upload_id FROM analysis_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).fetchone()
        finally:
            db.close()

        output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "output_file")
        output_dir = os.path.abspath(output_dir)

        # 1. 우선적으로 현재 job_id 접두어로 된 파일이 있는지 찾습니다 (이어달리기 복사본)
        pattern_job = os.path.join(output_dir, f"{job_id}*{suffix}")
        matches = _glob.glob(pattern_job)
        if matches:
            file_path = matches[0]
            return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))

        # 2. 없으면 upload_id(최초 원본) 기반으로 찾습니다
        if row:
            upload_id = str(row._mapping["upload_id"])
            pattern_up = os.path.join(output_dir, f"{upload_id}*{suffix}")
            matches = _glob.glob(pattern_up)
            if matches:
                file_path = matches[0]
                return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))

        return JSONResponse(
            {"message": "상세보기 파일이 아직 생성되지 않았습니다."},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"상세보기 파일 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def save_selections_handler(
    job_id: str,
    body: SelectionsRequest,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.save_selections(
            job_id=job_id,
            user_id=str(current_user["id"]),
            selections=body.selections,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"선택 저장 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def create_mask_preview_handler(
    job_id: str,
    body: MaskPreviewRequest | None = None,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        pii_id = body.pii_id if body else None
        result = analysis.create_mask_job(
            job_id=job_id,
            user_id=str(current_user["id"]),
            mask_type="mask_preview",
            target_pii_id=pii_id,
        )
        return JSONResponse(result, status_code=status.HTTP_201_CREATED)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"마스킹 미리보기 작업 생성 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def create_mask_final_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.create_mask_job(
            job_id=job_id,
            user_id=str(current_user["id"]),
            mask_type="mask_final",
        )
        return JSONResponse(result, status_code=status.HTTP_201_CREATED)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"마스킹 본처리 작업 생성 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def get_result_file_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_result_file(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"결과물 파일 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def download_handler(
    job_id: str,
    request: Request,
    access_token: str | None = Cookie(default=None),
):
    """처리 완료된 파일을 브라우저로 직접 스트리밍 (인증된 본인만 접근 가능)"""
    current_user = auth.authenticate_access_token(access_token)
    try:
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
        ua = request.headers.get("User-Agent")
        info = analysis.download_result_file(
            job_id=job_id,
            user_id=str(current_user["id"]),
            ip_address=ip,
            user_agent=ua,
        )
        stored_path  = info["stored_path"]
        filename     = info["original_filename"]
        content_type = info.get("content_type", "application/octet-stream")

        if not os.path.exists(stored_path):
            return JSONResponse({"message": "파일을 찾을 수 없습니다."}, status_code=status.HTTP_404_NOT_FOUND)

        return FileResponse(
            path=stored_path,
            filename=filename,
            media_type=content_type,
        )
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"파일 다운로드 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def trim_download_handler(
    job_id: str,
    request: Request,
    start: float = 0.0,
    end: float = 60.0,
    access_token: str | None = Cookie(default=None),
):
    """처리 완료 영상에서 [start, end](초) 구간을 잘라 MP4로 스트리밍.
    파일을 디스크에 저장하지 않고 ffmpeg stdout → StreamingResponse로 직접 전달."""
    current_user = auth.authenticate_access_token(access_token)
    try:
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
        ua = request.headers.get("User-Agent")
        info = analysis.download_result_file(
            job_id=job_id,
            user_id=str(current_user["id"]),
            ip_address=ip,
            user_agent=ua,
        )
        stored_path = info["stored_path"]
        filename    = info.get("original_filename", "result")

        if not os.path.exists(stored_path):
            return JSONResponse({"message": "파일을 찾을 수 없습니다."}, status_code=status.HTTP_404_NOT_FOUND)

        if start < 0 or end <= start:
            return JSONResponse({"message": "시간 범위가 올바르지 않습니다."}, status_code=status.HTTP_400_BAD_REQUEST)

        # imageio_ffmpeg 번들 ffmpeg 경로 취득
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return JSONResponse({"message": "ffmpeg를 찾을 수 없습니다."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 다운로드 파일명: {원본파일명}_0분30초~1분20초.mp4
        stem = os.path.splitext(filename)[0]
        def _fmt(sec):
            m, s = int(sec // 60), int(sec % 60)
            return f"{m}분{s:02d}초" if m else f"{s:02d}초"
        out_name = f"{stem}_{_fmt(start)}~{_fmt(end)}.mp4"

        dur = end - start
        # pipe:1(stdout)으로 출력 — 디스크 저장 없음
        # frag_keyframe+empty_moov: 파일 seek 없이 스트리밍 가능한 fragmented MP4
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", f"{start:.3f}", "-i", stored_path,
            "-t",  f"{dur:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "frag_keyframe+empty_moov",
            "-map_metadata", "-1",  # GPS·카메라·날짜 등 모든 메타데이터 명시적 제거
            "-c:a", "aac",
            "-f", "mp4", "pipe:1",
        ]

        logger.info(
            "영상 구간 다운로드 요청 — job=%s user=%s start=%.1f end=%.1f",
            job_id, current_user["id"], start, end,
        )

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # ffmpeg stdout을 청크 단위로 스트리밍 → 완료 시 프로세스 정리
        def _stream():
            try:
                while True:
                    chunk = proc.stdout.read(65536)  # 64 KB 단위
                    if not chunk:
                        break
                    yield chunk
            finally:
                proc.stdout.close()
                proc.wait()

        # RFC 5987 방식으로 한글 파일명 인코딩
        from urllib.parse import quote
        encoded = quote(out_name, safe="")
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        }
        return StreamingResponse(_stream(), media_type="video/mp4", headers=headers)

    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse({"message": f"구간 다운로드 실패: {exc}"}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


def reset_selections_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    """DELETE /analysis/jobs/{id}/selections — 마스킹 선택 전체 초기화 (뒤로가기 시 호출)"""
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.reset_selections(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"선택 초기화 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def delete_mask_preview_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    """DELETE /analysis/jobs/{id}/mask-preview — 마스킹 미리보기 결과물 삭제"""
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.delete_mask_previews(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"마스킹 미리보기 삭제 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def get_dashboard_handler(
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.get_dashboard_data(
            user_id=str(current_user["id"]),
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"대시보드 데이터 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def get_history_handler(
    page: int = 1,
    size: int = 10,
    search: str | None = None,
    sort: str = "desc",
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        limit = size
        offset = (page - 1) * size
        result = analysis.get_history_list(
            user_id=str(current_user["id"]),
            limit=limit,
            offset=offset,
            search=search,
            sort=sort
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except Exception as exc:
        return JSONResponse(
            {"message": f"히스토리 데이터 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def delete_job_handler(
    job_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        analysis.delete_analysis_job(
            job_id=job_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse({"message": "해당 작업이 성공적으로 삭제되었습니다."}, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"작업 삭제 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def delete_upload_handler(
    upload_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        analysis.delete_upload_and_jobs(
            upload_id=upload_id,
            user_id=str(current_user["id"]),
        )
        return JSONResponse({"message": "작업이 취소 및 삭제되었습니다."}, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return JSONResponse(
            {"message": f"삭제 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def get_thumbnail_handler(
    upload_id: str,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    from utils.database import SessionLocal
    from sqlalchemy import text as _text
    import os
    
    db = SessionLocal()
    try:
        row = db.execute(
            _text("SELECT user_id, thumbnail_path, media_type FROM uploads WHERE upload_id = :upload_id"),
            {"upload_id": upload_id},
        ).fetchone()
        
        if not row:
            return JSONResponse({"message": "업로드된 파일을 찾을 수 없습니다."}, status_code=status.HTTP_404_NOT_FOUND)
            
        m = row._mapping
        if str(m["user_id"]) != str(current_user["id"]):
            return JSONResponse({"message": "접근 권한이 없습니다."}, status_code=status.HTTP_403_FORBIDDEN)
            
        thumb_path = m["thumbnail_path"]
        if not thumb_path or not os.path.exists(thumb_path):
            return JSONResponse({"message": "썸네일 파일이 존재하지 않습니다."}, status_code=status.HTTP_404_NOT_FOUND)
            
        # Determine media type for response
        media_type = m["media_type"]
        if media_type.startswith("video/") and thumb_path.endswith(".jpg"):
            media_type = "image/jpeg" # If it's a video but the thumbnail is a generated image
            
        return FileResponse(thumb_path, media_type=media_type)
        
    except Exception as exc:
        return JSONResponse(
            {"message": f"썸네일 조회 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    finally:
        db.close()


def detail_access_handler(
    job_id: str,
    body: DetailAccessRequest,
    access_token: str | None = Cookie(default=None),
):
    current_user = auth.authenticate_access_token(access_token)
    try:
        result = analysis.charge_detail_access(
            job_id=job_id,
            user_id=str(current_user["id"]),
            file_type=body.file_type,
        )
        return JSONResponse(result, status_code=status.HTTP_200_OK)
    except PermissionError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)
    except ValueError as exc:
        msg = str(exc)
        if "Insufficient credits" in msg:
            return JSONResponse({
                "need_subscription": True,
                "message": "크레딧이 부족합니다."
            }, status_code=status.HTTP_400_BAD_REQUEST)
        return JSONResponse({"message": msg}, status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        return JSONResponse(
            {"message": f"상세보기 크레딧 처리 실패: {exc}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
