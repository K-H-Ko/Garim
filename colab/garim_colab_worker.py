"""
코드 설명:
Cloudflare Tunnel로 백엔드 서버와 연결하여, STT(음성 인식) 및 영상 마스킹 작업을 처리하는 Colab 전용 워커(Worker) 스크립트입니다.
백엔드로부터 주기적으로 작업을 할당받아 다운로드, 분석(PII 탐지 등), 마스킹 처리를 수행한 후 결과물을 다시 서버로 업로드합니다.
"""

import subprocess
import sys

# Colab 환경의 경우 Numpy 버전 충돌 방지를 위해 필수 라이브러리를 워커 기동 시 미리 설치합니다.
try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"])

# numpy 2.0 이상 요구하는 라이브러리와의 충돌 해결
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy>=2.0.0", "simple-lama-inpainting"], check=True)
print("필수 라이브러리 및 numpy 설치 완료")

import os, time, threading, logging
import requests

# ===== 환경설정 (모든 환경설정은 이부분에서 변경) =====
# 정식 도메인이 있으면 정식 도메인 입력, 없으면 cloudflare_tunnel.py로 생성한 임시 URL 입력 (임시URL/api/v1)
BACKEND_URL                = "https://garim.shop/api/v1"  # Cloudflare Tunnel URL (마지막 슬래시 없이)
WORKER_SECRET              = "change_me_to_a_long_random_secret"
WORKER_ID                  = "colab-worker-01"
POLL_INTERVAL_SECONDS      = 10   # job이 없을 때 재polling 간격 (초)
HEARTBEAT_INTERVAL_SECONDS = 30   # heartbeat 전송 주기 (초)
DOWNLOAD_DIR               = "/content/garim_downloads"       # STT용 다운로드 디렉토리
MASK_DOWNLOAD_DIR          = "/content/garim_mask_downloads"  # Mask용 다운로드 디렉토리
# ======================

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MASK_DOWNLOAD_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("garim-worker")
log.info(f"Config 로드 완료 | BACKEND_URL={BACKEND_URL} | WORKER_ID={WORKER_ID}")

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {WORKER_SECRET}"}


def get_next_job() -> dict | None:
    """GET /worker/jobs/next?worker_type=colab_full — stt_analysis + mask_preview + mask_final 처리"""
    r = requests.get(
        f"{BACKEND_URL}/worker/jobs/next",
        params={"worker_type": "colab_full"},  # STT + Mask 통합 처리
        headers=auth_headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("job")


def accept_job(job_id: str) -> dict:
    """POST /worker/jobs/{job_id}/accept — job 처리 시작 선언"""
    r = requests.post(
        f"{BACKEND_URL}/worker/jobs/{job_id}/accept",
        headers=auth_headers(),
        json={"worker_id": WORKER_ID},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def download_file(upload_id: str, output_dir: str = DOWNLOAD_DIR) -> str:
    """GET /worker/files/{upload_id}/download — 원본 파일 바이너리 수신 후 저장

    Returns:
        저장된 로컬 파일 경로
    """
    import mimetypes
    import urllib.parse

    url = f"{BACKEND_URL}/worker/files/{upload_id}/download"
    r = requests.get(url, headers=auth_headers(), stream=True, timeout=60)
    r.raise_for_status()

    cd = r.headers.get("content-disposition", "")
    filename = f"upload_{upload_id}"
    if "filename=" in cd:
        # filename*=UTF-8''... 형태도 처리 (한글 파일명 URL 인코딩 대응)
        raw = cd.split("filename=")[-1].strip().strip('"').strip("'")
        # UTF-8'' 접두어가 있으면 제거 후 디코딩
        if raw.upper().startswith("UTF-8''"):
            raw = urllib.parse.unquote(raw[7:])
        elif "%" in raw:
            raw = urllib.parse.unquote(raw)
        # 파싱된 파일명에서 추가 세미콜론 이후 잘라냄 (다른 파라미터)
        if ";" in raw:
            raw = raw.split(";")[0].strip()
        filename = raw

    # 확장자가 없으면 Content-Type 헤더에서 추론하여 보완
    if not os.path.splitext(filename)[1]:
        ct = r.headers.get("content-type", "")
        ext_guess = mimetypes.guess_extension(ct.split(";")[0].strip())
        if ext_guess:
            # mimetypes가 .jpe 를 반환하는 경우 .jpg 로 보정
            if ext_guess in (".jpe", ".jpeg"):
                ext_guess = ".jpg"
            filename += ext_guess

    out_path = os.path.join(output_dir, filename)
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    log.info(f"파일 다운로드 완료: {out_path} ({size_mb:.1f} MB)")
    return out_path


def report_progress(
    job_id: str,
    stage_name: str,
    stage_progress: int,
    total_progress: int,
    message: str | None = None,
) -> dict:
    """PUT /worker/jobs/{job_id}/progress — 진행률 업데이트"""
    r = requests.put(
        f"{BACKEND_URL}/worker/jobs/{job_id}/progress",
        headers=auth_headers(),
        json={
            "worker_id": WORKER_ID,
            "stage_name": stage_name,
            "stage_progress": stage_progress,
            "total_progress": total_progress,
            "message": message,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def send_heartbeat(
    job_id: str,
    current_stage: str | None = None,
    progress_percent: int = 0,
    message: str | None = None,
) -> None:
    """POST /worker/heartbeat — 생존 신호 전송 (실패해도 worker 중단 안 함)"""
    try:
        r = requests.post(
            f"{BACKEND_URL}/worker/heartbeat",
            headers=auth_headers(),
            json={
                "job_id": job_id,
                "worker_id": WORKER_ID,
                "worker_type": "colab_full",
                "current_stage": current_stage,
                "progress_percent": progress_percent,
                "message": message,
            },
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        log.warning(f"heartbeat 실패 (무시): {e}")


def complete_job(job_id: str, detection_count: int = 0) -> dict:
    """POST /worker/jobs/{job_id}/complete — 정상 완료 보고"""
    r = requests.post(
        f"{BACKEND_URL}/worker/jobs/{job_id}/complete",
        headers=auth_headers(),
        json={"worker_id": WORKER_ID, "detection_count": detection_count},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def fail_job(
    job_id: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """POST /worker/jobs/{job_id}/fail — 실패 보고 (전송 실패해도 로그만 남김)"""
    try:
        r = requests.post(
            f"{BACKEND_URL}/worker/jobs/{job_id}/fail",
            headers=auth_headers(),
            json={
                "worker_id": WORKER_ID,
                "error_code": error_code,
                "error_message": error_message,
            },
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        log.error(f"fail_job 전송 실패: {e}")


def check_cancel(job_id: str) -> bool:
    """GET /worker/jobs/{job_id}/status — 취소 여부 확인.
    - cancel_requested=true (사용자 취소) → 취소
    - 404 (job 행 삭제 = 업로드 삭제 경로) → 취소로 간주
    - 그 외 네트워크/서버 오류 → 취소 아님(오작동 방지, 계속 진행)"""
    try:
        r = requests.get(
            f"{BACKEND_URL}/worker/jobs/{job_id}/status",
            headers=auth_headers(),
            timeout=10,
        )
        if r.status_code == 404:
            return True  # job 이 사라짐(업로드 삭제) → 즉시 중단해야 함
        r.raise_for_status()
        return r.json().get("cancel_requested", False)
    except Exception:
        return False  # 그 외 오류 시 취소 없음으로 간주

def submit_stt_result(
    job_id: str,
    language: str,
    full_text: str,
    segment_count: int,
) -> dict:
    """POST /worker/jobs/{job_id}/results/stt — STT 결과 저장"""
    r = requests.post(
        f"{BACKEND_URL}/worker/jobs/{job_id}/results/stt",
        headers=auth_headers(),
        json={
            "worker_id": WORKER_ID,
            "language": language,
            "full_text": full_text,
            "segment_count": segment_count,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def submit_pii_result(job_id: str, pii_segments: list) -> dict:
    """POST /worker/jobs/{job_id}/results/pii — PII 탐지 결과 저장"""
    r = requests.post(
        f"{BACKEND_URL}/worker/jobs/{job_id}/results/pii",
        headers=auth_headers(),
        json={"worker_id": WORKER_ID, "pii_segments": pii_segments},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def submit_artifact(
    job_id: str,
    artifact_type: str,
    stored_path: str,
    content_type: str | None = None,
    file_size: int | None = None,
    metadata: dict | None = None,
) -> dict:
    """POST /worker/jobs/{job_id}/results/artifact — 분석 산출물 저장"""
    r = requests.post(
        f"{BACKEND_URL}/worker/jobs/{job_id}/results/artifact",
        headers=auth_headers(),
        json={
            "worker_id": WORKER_ID,
            "artifact_type": artifact_type,
            "stored_path": stored_path,
            "content_type": content_type,
            "file_size": file_size,
            "metadata": metadata,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_mask_context(job_id: str) -> dict:
    """GET /worker/jobs/{job_id}/mask-context — result_json + selected_pii_ids 조회"""
    r = requests.get(
        f"{BACKEND_URL}/worker/jobs/{job_id}/mask-context",
        headers=auth_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def upload_mask_result(job_id: str, file_path: str, content_type: str) -> dict:
    """POST /worker/jobs/{job_id}/results/upload-file — 마스킹 결과 파일 multipart 업로드"""
    import urllib.parse
    raw_filename = os.path.basename(file_path)
    safe_filename = urllib.parse.quote(raw_filename)  # 한글 파일명 latin-1 에러 방지
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{BACKEND_URL}/worker/jobs/{job_id}/results/upload-file",
            headers=auth_headers(),
            files={"file": (safe_filename, f, content_type)},
            timeout=180,  # 영상 파일 대용량 고려
        )
    r.raise_for_status()
    return r.json()


log.info("API 헬퍼 함수 로드 완료")

def peek_next_job() -> dict | None:
    """Print and return the next queued analysis job, if one exists."""
    job = get_next_job()
    if not job:
        log.info("No queued analysis job yet. Upload may still be in progress or analysis job was not created.")
        return None

    log.info(
        "Queued job found | job_id=%s | upload_id=%s | file=%s | size=%s",
        job.get("job_id"),
        job.get("upload_id"),
        job.get("original_filename"),
        job.get("file_size"),
    )
    return job


def watch_for_next_job(timeout_seconds: int = 300, interval_seconds: int = 3) -> dict | None:
    """Wait until frontend upload creates a queued analysis job."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = peek_next_job()
        if job:
            return job
        time.sleep(interval_seconds)

    log.warning("Timed out waiting for a queued analysis job. Check frontend upload status and backend logs.")
    return None


def get_job_progress(job_id: str) -> dict:
    """Read worker-visible analysis job status."""
    r = requests.get(
        f"{BACKEND_URL}/worker/jobs/{job_id}/status",
        headers=auth_headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def watch_job_status(job_id: str, interval_seconds: int = 2, stop_on_terminal: bool = True) -> None:
    """Print analysis job progress until it reaches a terminal state."""
    terminal = {"completed", "failed", "cancelled"}
    last_line = None
    while True:
        status = get_job_progress(job_id)
        line = (
            f"job={status.get('job_id')} | status={status.get('status')} | "
            f"stage={status.get('current_stage')} | total={status.get('total_progress')}% | "
            f"cancel={status.get('cancel_requested')}"
        )
        if line != last_line:
            print(line)
            last_line = line

        if stop_on_terminal and status.get("status") in terminal:
            break
        time.sleep(interval_seconds)


# Usage examples:
# job = watch_for_next_job()
# if job:
#     watch_job_status(job["job_id"])
log.info("Upload / Job progress helper loaded")

class HeartbeatThread(threading.Thread):
    def __init__(self, job_id: str):
        super().__init__(daemon=True)
        self.job_id = job_id
        self._stop = threading.Event()
        self._stage: str | None = None
        self._progress: int = 0
        self._message: str | None = None

    def update(self, stage: str, progress: int, message: str | None = None) -> None:
        self._stage = stage
        self._progress = progress
        self._message = message

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            send_heartbeat(self.job_id, self._stage, self._progress, self._message)

log.info("HeartbeatThread 로드 완료")

from google.colab import drive
import importlib
import os
import sys

# [구글 드라이브 마운트 및 파이프라인 연동 안내]
# 다른 계정이나 새로운 환경에서 실행 시, 본인 계정의 구글 드라이브를 마운트하도록 권한 허용이 필요합니다.
# 워커가 정상적으로 동작하려면 아래 `GARIM_COLAB_DIR`로 지정된 구글 드라이브 폴더 경로 안에 다음 2개의 파일(.py 확장자)이 반드시 미리 준비되어 있어야 합니다:
#  1. colab_pipeline_stt.py (음성 인식 및 개인정보 탐지)
#  2. colab_pipeline_mask.py (영상 마스킹/인페인팅 처리)
#
# ※ 참고사항: 영상 처리를 위해 임시로 다운로드하는 원본 파일이나 결과물이 저장되는 폴더
# (`/content/garim_downloads`, `/content/garim_mask_downloads`)는 코랩 런타임 내부에 자동으로 생성되므로 직접 만드실 필요가 없습니다.
#
# [구글 드라이브 용량 관리 주의사항 (테스트 목적 시)]
# 파이프라인에서 추출/생성된 최종 결과물(마스킹된 영상 등)은 본인 구글 드라이브에 자동으로 폴더가 생성되어 저장됩니다.
# 플랫폼에서 파일을 삭제하면 드라이브에서도 자동 삭제되도록 연동되어 있으나, 구글 드라이브 정책상 '휴지통'으로 이동할 뿐 용량은 계속 차지하게 됩니다.
# 따라서 테스트 용도로 사용할 때 드라이브 용량이 작다면, 원활한 구동을 위해 주기적으로 구글 드라이브의 '휴지통 비우기'를 진행해야 합니다.

GARIM_COLAB_DIR      = "/content/drive/MyDrive/final_PJ_model"  # 본인의 구글 드라이브 내 실제 파이프라인 파일이 있는 폴더 경로로 변경하세요.
PIPELINE_FILENAME    = "colab_pipeline_stt.py"                  
MASK_PIPELINE_FILE   = "colab_pipeline_mask.py"                 

# 런타임이 재시작되어도 파이프라인 파일을 유지하기 위해 구글 드라이브를 고정 저장소로 마운트합니다.
drive.mount("/content/drive")
os.makedirs(GARIM_COLAB_DIR, exist_ok=True)

if GARIM_COLAB_DIR not in sys.path:
    sys.path.insert(0, GARIM_COLAB_DIR)

# ── STT 파이프라인 로드 ──────────────────────────────────────────────
pipeline_path = os.path.join(GARIM_COLAB_DIR, PIPELINE_FILENAME)

if not os.path.exists(pipeline_path):
    _pipeline = None
    _PIPELINE_AVAILABLE = False
    log.warning(
        f"{PIPELINE_FILENAME} 없음: {pipeline_path} — "
        "Drive의 garim_colab 폴더에 colab_pipeline_stt.py 파일이 필요합니다. "
        "현재는 dry-run 모드로 실행합니다."
    )
else:
    try:
        _module_name = os.path.splitext(PIPELINE_FILENAME)[0]
        _pipeline = importlib.import_module(_module_name)
        _pipeline = importlib.reload(_pipeline)
        registry = getattr(_pipeline, "PIPELINE_REGISTRY", [])
        _PIPELINE_AVAILABLE = True
        log.info(f"STT 파이프라인 로드 완료 | 경로: {pipeline_path} | analyzer: {[a.stage_name for a in registry]}")
    except Exception as e:
        _pipeline = None
        _PIPELINE_AVAILABLE = False
        log.warning(f"STT 파이프라인 import 실패 — dry-run 모드로 실행: {e}")

# ── Mask 파이프라인 로드 ─────────────────────────────────────────────
mask_pipeline_path = os.path.join(GARIM_COLAB_DIR, MASK_PIPELINE_FILE)

if not os.path.exists(mask_pipeline_path):
    _mask_pipeline = None
    _MASK_PIPELINE_AVAILABLE = False
    log.warning(f"{MASK_PIPELINE_FILE} 없음 — mask job은 dry-run으로 처리됩니다.")
else:
    try:
        _mask_module_name = os.path.splitext(MASK_PIPELINE_FILE)[0]
        _mask_pipeline = importlib.import_module(_mask_module_name)
        _mask_pipeline = importlib.reload(_mask_pipeline)
        _MASK_PIPELINE_AVAILABLE = True
        log.info(f"Mask 파이프라인 로드 완료 | 경로: {mask_pipeline_path}")
    except Exception as e:
        _mask_pipeline = None
        _MASK_PIPELINE_AVAILABLE = False
        log.warning(f"Mask 파이프라인 import 실패 — dry-run: {e}")

# dry-run 에서 파이프라인 구간만 통과 (result_upload 는 Phase 3 에서 별도 처리)
_DRY_RUN_STAGES = [
    ("visual_ocr",    40),
    ("audio_extract", 48),
    ("stt",           68),
    ("pii_detect",    78),
    ("beep_render",   90),
]


def _handle_cancel(job_id: str) -> None:
    """취소 감지 시 progress 메시지를 남기고, status='cancelled' 로 확정한 뒤 중단한다."""
    log.info(f"취소 요청 확인 — 처리 중단: {job_id}")
    try:
        report_progress(job_id, "cancelled", 0, 0,
                        "취소 요청을 확인해 worker 처리를 중단했습니다.")
    except Exception:
        pass
    # status='cancelled' 확정 (job 이 이미 삭제됐으면 백엔드가 0건 업데이트로 조용히 통과)
    try:
        requests.post(
            f"{BACKEND_URL}/worker/jobs/{job_id}/cancelled",
            headers=auth_headers(),
            timeout=10,
        )
    except Exception:
        pass


def _run_mask_job(job_id: str, upload_id: str, job_type: str, hb: "HeartbeatThread") -> None:
    """mask_preview / mask_final job 처리 — 미리보기 또는 본 마스킹.

    흐름:
      1. 원본 파일 다운로드 (0 → 15%)
      2. mask-context 조회 (result_json + selected_pii_ids) (15 → 20%)
      3. run_preview() 또는 run_masking() 실행 (20 → 80%)
      4. 결과 파일 업로드 (80 → 95%)
      5. complete (95 → 100%)
    """
    import tempfile, json as _json, mimetypes

    # 1. 원본 파일 다운로드
    report_progress(job_id, "file_download", 0, 0, "원본 파일 다운로드 시작")
    hb.update("file_download", 0)
    file_path = download_file(upload_id, output_dir=MASK_DOWNLOAD_DIR)
    report_progress(job_id, "file_download", 100, 15,
                    f"다운로드 완료: {os.path.basename(file_path)}")
    hb.update("file_download", 15)

    # 2. mask-context 조회 (result_json + selected_pii_ids)
    report_progress(job_id, "mask_context", 0, 15, "분석 결과 로드 중")
    hb.update("mask_context", 15)
    ctx_data     = get_mask_context(job_id)
    result_json  = ctx_data.get("result_json", {})
    selected_ids = ctx_data.get("selected_pii_ids", [])
    report_progress(job_id, "mask_context", 100, 20,
                    f"selected_pii_ids={len(selected_ids)}개")
    hb.update("mask_context", 20)

    # result_json을 임시 파일로 저장 (colab_pipeline_mask 인터페이스 호환)
    tmp_json = tempfile.NamedTemporaryFile(
        mode="w", suffix="_result.json", delete=False, encoding="utf-8"
    )
    _json.dump(result_json, tmp_json, ensure_ascii=False)
    tmp_json.close()
    tmp_json_path = tmp_json.name

    try:
        # 3. 마스킹 실행
        report_progress(job_id, "masking", 0, 20, "인페인팅 마스킹 시작")
        hb.update("masking", 20)

        if _MASK_PIPELINE_AVAILABLE:
            if job_type == "mask_preview":
                # 미리보기 — 사용자가 미리보기 클릭 시 이벤트 발생
                # run_preview() 반환값: dict {'preview': path} 또는 {'preview_clip': path}
                mask_result = _mask_pipeline.run_preview(
                    tmp_json_path,
                    input_path=file_path,
                    selected_ids=selected_ids,
                )
                if mask_result is None:
                    raise ValueError("미리보기 생성 실패 — 원본 파일 없음 또는 선택 PII 없음")
                # 이미지: result['preview'] / 영상: result['preview_clip']
                output_file = mask_result.get("preview") or mask_result.get("preview_clip")
            else:
                # 본 처리(전체 마스킹) — 최종 다운로드 버튼 클릭 시
                # run_masking() 반환값: Path 객체 직접 반환 (dict 아님!)
                out_path = _mask_pipeline.run_masking(
                    tmp_json_path,
                    input_path=file_path,
                    selected_ids=selected_ids,
                )
                if out_path is None:
                    raise ValueError("마스킹 처리 실패 — 원본 파일 없음 또는 처리 오류")
                output_file = str(out_path)
        else:
            # dry-run: 원본 파일을 그대로 결과로 사용
            log.warning("Mask 파이프라인 없음 — dry-run (원본 파일 반환)")
            output_file = file_path

        if not output_file or not os.path.exists(str(output_file)):
            raise FileNotFoundError(f"마스킹 결과 파일 없음: {output_file}")

        report_progress(job_id, "masking", 100, 80, "마스킹 완료")
        hb.update("masking", 80)

        # 4. 결과 파일 업로드
        report_progress(job_id, "result_upload", 0, 80, "결과 파일 업로드 중")
        hb.update("result_upload", 80)

        ext = os.path.splitext(output_file)[1].lower()
        ctype = mimetypes.types_map.get(ext, "application/octet-stream")
        upload_mask_result(job_id, output_file, ctype)
        report_progress(job_id, "result_upload", 100, 95, "업로드 완료")
        hb.update("result_upload", 95)

        # 5. 완료
        complete_job(job_id, detection_count=len(selected_ids))
        log.info(f"mask job 완료: {job_id} ({job_type})")

    finally:
        # 임시 JSON 파일 정리
        try:
            if 'tmp_json_path' in locals() and os.path.exists(tmp_json_path):
                os.unlink(tmp_json_path)
        except Exception:
            pass
        # 다운로드받은 원본 파일 정리
        try:
            if 'file_path' in locals() and file_path and os.path.exists(file_path):
                os.unlink(file_path)
        except Exception:
            pass
        # 생성된 마스킹 결과물 정리 (서버에 업로드 했으므로 워커에는 필요없음)
        try:
            if 'output_file' in locals() and output_file and os.path.exists(output_file):
                os.unlink(output_file)
        except Exception:
            pass


def run_once() -> bool:
    """job 하나를 처리한다.

    job_type별 라우팅:
      stt_analysis              → STT 파이프라인 (분석 시작 클릭 시)
      mask_preview / mask_final → Mask 파이프라인 (미리보기/본처리 클릭 시)

    Returns:
        True  — job을 처리했음 (성공/실패 불문)
        False — 대기 중인 job이 없었음
    """
    job = get_next_job()
    if job is None:
        log.info("대기 중인 작업 없음")
        return False

    job_id    = job["job_id"]
    upload_id = job["upload_id"]
    job_type  = job.get("job_type", "stt_analysis")
    log.info(f"job 수신: {job_id} | upload: {upload_id} | type: {job_type}")

    hb = HeartbeatThread(job_id)
    hb.start()

    try:
        accept_job(job_id)
        log.info(f"job 수락 완료: {job_id}")

        # ── Mask job 분기 (미리보기/본처리 — 이벤트성) ─────────────────
        if job_type in ("mask_preview", "mask_final"):
            _run_mask_job(job_id, upload_id, job_type, hb)
            return True

        # ── STT 분석 job (분석 시작 클릭 시 이벤트) ─────────────────────

        # Phase 1: 파일 다운로드 (0 → 10%)
        report_progress(job_id, "file_download", 0, 0, "파일 다운로드 시작")
        hb.update("file_download", 0)
        file_path = download_file(upload_id)
        report_progress(job_id, "file_download", 100, 10,
                        f"다운로드 완료: {os.path.basename(file_path)}")
        hb.update("file_download", 10)

        if check_cancel(job_id):
            _handle_cancel(job_id)
            return True

        # Phase 2: 분석 파이프라인 (10 → 90%)
        if _PIPELINE_AVAILABLE:
            ctx = _pipeline.PipelineContext(
                job_id=job_id,
                upload_id=upload_id,
                file_path=file_path,
                media_type=job.get("media_type"),
                progress_fn=report_progress,
                cancel_fn=check_cancel,
            )
            try:
                pipeline_result = _pipeline.run_pipeline(ctx)
            except RuntimeError as e:
                if "CANCELLED" in str(e):
                    _handle_cancel(job_id)
                    return True
                raise
            detection_count = pipeline_result.get("detection_count", 0)
            hb.update("beep_render", 90)
            log.info(f"파이프라인 완료 | detection_count={detection_count}")
        else:
            # dry-run 모드
            detection_count = 0
            for stage, total_end in _DRY_RUN_STAGES:
                if check_cancel(job_id):
                    _handle_cancel(job_id)
                    return True
                report_progress(job_id, stage, 100, total_end, f"{stage} 완료 (dry-run)")
                hb.update(stage, total_end)
                log.info(f"  [dry-run] stage={stage} total_progress={total_end}")

        # Phase 3: 결과 저장 (90 → 98%)
        report_progress(job_id, "result_upload", 0, 90, "결과 저장 시작")
        hb.update("result_upload", 90)

        if _PIPELINE_AVAILABLE:
            stt = ctx.results.get("stt", {})
            if stt.get("full_text"):
                try:
                    submit_stt_result(
                        job_id,
                        language=stt.get("language", "unknown"),
                        full_text=stt["full_text"],
                        segment_count=len(stt.get("segments", [])),
                    )
                    log.info(f"STT 결과 저장 완료: {len(stt.get('segments', []))}개 세그먼트")
                except Exception as e:
                    log.warning(f"STT 결과 저장 실패 (무시): {e}")

            pii = ctx.results.get("pii_detect", {})
            if pii.get("pii_segments"):
                try:
                    submit_pii_result(job_id, pii["pii_segments"])
                    log.info(f"PII 결과 저장 완료: {len(pii['pii_segments'])}건")
                except Exception as e:
                    log.warning(f"PII 결과 저장 실패 (무시): {e}")

            beep = ctx.results.get("beep_render", {})
            if beep.get("output_path"):
                try:
                    fsize = os.path.getsize(beep["output_path"]) if os.path.exists(beep["output_path"]) else None
                    submit_artifact(job_id, "beep_output", beep["output_path"], "video/mp4", fsize)
                    log.info(f"beep 결과물 저장 완료: {beep['output_path']}")
                except Exception as e:
                    log.warning(f"beep 결과물 저장 실패 (무시): {e}")

            visual_ocr = ctx.results.get("visual_ocr", {})
            visual_metadata = {
                "scene_count": visual_ocr.get("scene_count", 0),
                "sampled_frame_count": visual_ocr.get("sampled_frame_count", 0),
                "ocr_hit_count": visual_ocr.get("ocr_hit_count", 0),
                "detection_count": visual_ocr.get("detection_count", 0),
                "review_thumbnail_count": len(visual_ocr.get("review_thumbnails", [])),
            }
            for artifact_type, content_type, path_key in (
                ("visual_ocr_json", "application/json", "json"),
                ("visual_ocr_csv", "text/csv", "csv"),
            ):
                stored_path = visual_ocr.get("result_paths", {}).get(path_key)
                if not stored_path:
                    continue
                try:
                    fsize = os.path.getsize(stored_path) if os.path.exists(stored_path) else None
                    submit_artifact(
                        job_id,
                        artifact_type,
                        stored_path,
                        content_type,
                        fsize,
                        visual_metadata,
                    )
                    log.info(f"시각 OCR 결과물 저장 완료: {stored_path}")
                except Exception as e:
                    log.warning(f"시각 OCR 결과물 저장 실패 (무시): {e}")

        report_progress(job_id, "result_upload", 100, 98, "결과 저장 완료")
        hb.update("result_upload", 98)

        # Phase 4: 완료
        complete_job(job_id, detection_count=detection_count)
        log.info(f"job 완료: {job_id}")
        return True

    except Exception as e:
        log.error(f"job 처리 실패: {e}")
        fail_job(job_id, error_code="WORKER_ERROR", error_message=str(e))
        return False

    finally:
        hb.stop()


def run_loop() -> None:
    """job을 계속 polling하며 처리한다. Colab ■ 버튼으로 중단."""
    log.info(f"worker 루프 시작 | WORKER_ID={WORKER_ID} | POLL_INTERVAL={POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            has_job = run_once()
            if not has_job:
                time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            log.info("worker 루프 종료 (KeyboardInterrupt)")
            break
        except Exception as e:
            log.error(f"루프 오류 (재시도 대기): {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

log.info("Worker Loop 함수 로드 완료")

# ===== 실행 방식 선택 =====
# 단건 테스트: job 1개만 처리하고 종료
# run_once()

# 루프 실행: 대기 job을 계속 처리 (■ 로 중단)
run_loop()
