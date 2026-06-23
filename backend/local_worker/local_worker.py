"""
local_worker.py — 로컬 OCR + 마스킹 더미 워커

백엔드 큐를 polling하여 두 가지 job을 자동 처리:
  - analysis      : OCR 분석 → 결과 병합 → 백엔드 등록 → 완료
  - mask_preview  : 더미 완료 처리 (processed_files 등록)
  - mask_final    : 더미 완료 처리 (processed_files 등록)

실행:
  python backend/local_worker/local_worker.py

환경변수 (모두 선택 — 기본값으로 동작):
  WORKER_BASE      백엔드 URL          (기본: http://localhost:8000)
  WORKER_API_KEY   WORKER_SECRET 값    (기본: change_me_to_a_long_random_secret)
  POLL_INTERVAL_SEC  폴링 간격(초)     (기본: 5)
"""

import os
import sys
import time
import json
import threading
from pathlib import Path

# ── sys.path 설정 ──────────────────────────────────────────────────
_HERE         = Path(__file__).parent          # backend/local_worker/
_PROJECT_ROOT = _HERE.parent.parent            # Human_Final_PJ-main/

for p in (str(_HERE), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 환경설정 ───────────────────────────────────────────────────────
WORKER_BASE    = os.getenv("WORKER_BASE",    "http://localhost:8000/api/v1")
WORKER_API_KEY = os.getenv("WORKER_API_KEY", "change_me_to_a_long_random_secret")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL_SEC", "5"))

# OCR output_file 폴더 (OCR_pipeline_report.py 의 OUTPUT_DIR 와 동일해야 함)
import OCR_pipeline_report as _ocr_pipe
OUTPUT_DIR = _ocr_pipe.OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"Authorization": f"Bearer {WORKER_API_KEY}"}

# job 생성 시 외부에서 set() 호출 → 워커가 즉시 깨어남
# start_background_worker()에서 backend의 WORKER_EVENT로 교체됨
_wake_event: threading.Event = threading.Event()

# ── requests lazy import ───────────────────────────────────────────
try:
    import requests as _req
except ImportError as _e:
    # sys.exit() 대신 ImportError를 raise — 서버 프로세스가 죽지 않음
    raise ImportError(
        "❌ requests 패키지가 없습니다. pip install requests 후 백엔드를 재시작하세요."
    ) from _e


# ──────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────────

def _get(path, timeout=15):
    return _req.get(f"{WORKER_BASE}{path}", headers=HEADERS, timeout=timeout)


def _post(path, body=None, timeout=15):
    return _req.post(f"{WORKER_BASE}{path}", json=body or {}, headers=HEADERS, timeout=timeout)


def _put(path, body=None, timeout=15):
    return _req.put(f"{WORKER_BASE}{path}", json=body or {}, headers=HEADERS, timeout=timeout)


# 처리 중 사용자 취소(또는 업로드 삭제)를 감지하면 발생시키는 신호.
#  BaseException 상속 → 파이프라인 내부의 광범위한 `except Exception` 에 삼켜지지 않고
#  메인 루프까지 확실히 전파되어 즉시 중단된다(KeyboardInterrupt 와 동일 전략).
class JobCancelled(BaseException):
    pass


def _confirm_cancelled(job_id):
    """워커 중단을 백엔드에 확정 통보 → status='cancelled' (job 이 이미 삭제됐으면 조용히 무시)."""
    try:
        _post(f"/worker/jobs/{job_id}/cancelled", {})
    except Exception:
        pass


def report_progress(job_id, stage, stage_pct, total_pct, message=""):
    cancelled = False
    try:
        resp = _put(f"/worker/jobs/{job_id}/progress", {
            "worker_id":     "local_worker",
            "stage_name":    stage,
            "stage_progress": stage_pct,
            "total_progress": total_pct,
            "message":       message,
        })
        # 진행률 응답에 실려오는 취소신호 확인 — 추가 요청 없이 매 보고마다 즉시 감지.
        #  cancel_requested=true(사용자 취소) 또는 job 행 삭제(업로드 삭제) 둘 다 신호로 옴.
        if resp is not None and resp.status_code == 200:
            try:
                cancelled = bool(resp.json().get("cancel_requested"))
            except Exception:
                cancelled = False
    except Exception as e:
        print(f"  ⚠️  progress 보고 실패: {e}")
    if cancelled:
        raise JobCancelled(job_id)


def fail_job(job_id, code, message):
    try:
        _post(f"/worker/jobs/{job_id}/fail", {
            "worker_id":     "local_worker",
            "error_code":    code,
            "error_message": message,
        })
    except Exception as e:
        print(f"  ⚠️  fail 처리 실패: {e}")


def complete_job(job_id, detection_count=0):
    try:
        resp = _post(f"/worker/jobs/{job_id}/complete", {
            "worker_id":       "local_worker",
            "detection_count": detection_count,
        })
        resp.raise_for_status()
        print(f"  ✅ 완료 처리 (탐지 {detection_count}건)")
    except Exception as e:
        print(f"  ❌ 완료 처리 실패: {e}")


# ──────────────────────────────────────────────────────────────────
# analysis job 처리
# ──────────────────────────────────────────────────────────────────

def _register_pii(job_id, pii_groups):
    """visual_pii → detections 테이블 등록"""
    if not pii_groups:
        return
    segments = []
    for g in pii_groups:
        # keyframes에서 첫 번째 timestamp를 start_time_sec로 사용 → 미리보기 버튼 표시용
        kfs = g.get("keyframes", [])
        times = [kf["timestamp"] for kf in kfs if "timestamp" in kf]
        start_time_sec = min(times) if times else None
        end_time_sec   = max(times) if times else None
        segments.append({
            "pii_id":          g.get("pii_id", ""),
            "pii_label":       g.get("pii_type", g.get("pii_label", "")),
            "confidence":      g.get("confidence", 1.0),
            "rep_frame":       g.get("rep_frame"),
            "bbox":            g.get("bbox"),
            "detected_text":   g.get("detected_text", ""),
            "polygons":        g.get("polygons", []),   # 회전 폴리곤 좌표 — SVG 오버레이용
            "start_time_sec":  start_time_sec,          # 재생바 확인 버튼용
            "end_time_sec":    end_time_sec,
        })
    try:
        resp = _post(f"/worker/jobs/{job_id}/results/pii", {
            "pii_segments":   segments,
            "detection_type": "visual_pii",
        }, timeout=30)
        resp.raise_for_status()
        print(f"  ✅ visual_pii {len(segments)}건 등록")
    except Exception as e:
        print(f"  ⚠️  PII 등록 실패: {e}")


def _register_audio_pii(job_id, audio_pii_groups):
    """voice_pii → detections 테이블 등록 (음성 PII 체크박스 표시용)"""
    if not audio_pii_groups:
        return
    segments = []
    for g in audio_pii_groups:
        segments.append({
            "pii_id":          g.get("pii_id", ""),
            "label":           g.get("pii_type", ""),
            "confidence":      g.get("confidence", 1.0),
            "start_time_sec":  g.get("start_time_sec"),
            "end_time_sec":    g.get("end_time_sec"),
            "detected_text":   g.get("detected_text", ""),
        })
    try:
        resp = _post(f"/worker/jobs/{job_id}/results/pii", {
            "pii_segments":   segments,
            "detection_type": "voice_pii",
        }, timeout=30)
        resp.raise_for_status()
        print(f"  ✅ voice_pii {len(segments)}건 등록")
    except Exception as e:
        print(f"  ⚠️  음성 PII 등록 실패: {e}")


_IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
_VID_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv"}

def _register_artifacts(job_id, stem, detail_result=None):
    """result.json + 상세보기 파일 → analysis_artifacts 등록.
    detail_result: run_detail_view() 반환값 {'overlay_image': ..., 'overlay_video': ...}"""
    result_path = OUTPUT_DIR / f"{stem}_result.json"

    # result.json에서 요약 메타데이터 추출 → DB에 캐싱 (리포트 페이지 API 응답에 사용됨)
    metadata = {}
    if result_path.exists():
        try:
            with open(result_path, encoding="utf-8") as f:
                rj = json.load(f)
            metadata = {
                "visual_pii_count":  rj.get("visual_pii_count", 0),
                "audio_pii_count":   rj.get("audio_pii_count", 0),
                "total_pii_count":   rj.get("total_pii_count", 0),
                "risk_score":        rj.get("risk_score", 0),
                "risk_level_counts": rj.get("risk_level_counts", {}),
                "timeline_markers":  rj.get("timeline_markers", []),
                "source_type":       rj.get("source_type", ""),
                "source_name":       rj.get("source_name", ""),
            }
        except Exception as e:
            print(f"  ⚠️  result.json 메타데이터 추출 실패: {e}")

    artifacts = [
        {
            "artifact_type": "pii_result",
            "stored_path": str(result_path),
            "metadata": metadata,
        },
    ]

    # 상세보기 파일 등록 (run_detail_view 결과)
    if detail_result:
        if detail_result.get("overlay_image"):
            artifacts.append({
                "artifact_type": "detail_image",
                "stored_path": detail_result["overlay_image"],
                "metadata": {},
            })
        if detail_result.get("overlay_video"):
            artifacts.append({
                "artifact_type": "detail_video",
                "stored_path": detail_result["overlay_video"],
                "metadata": {},
            })

    for art in artifacts:
        if not Path(art["stored_path"]).exists():
            print(f"  ⚠️  파일 없음, 건너뜀: {Path(art['stored_path']).name}")
            continue
        try:
            resp = _post(f"/worker/jobs/{job_id}/results/artifact", art)
            resp.raise_for_status()
            print(f"  ✅ artifact: {art['artifact_type']}")
        except Exception as e:
            print(f"  ⚠️  artifact 등록 실패 ({art['artifact_type']}): {e}")


_STT_POLL_INTERVAL = 5    # 초 — STT job 완료 대기 폴링 간격
_STT_POLL_TIMEOUT  = 300  # 초 — 코랩 STT 최대 대기 시간 (5분)


def _wait_for_stt(job_id: str, upload_id: str) -> list:
    """코랩 stt_analysis job 완료를 폴링하고 audio_pii_segments 반환.
    코랩 미연결이거나 타임아웃 시 빈 리스트 반환 (STT 없이 merger 진행)."""
    try:
        resp = _get(f"/worker/uploads/{upload_id}/stt-job", timeout=10)
        resp.raise_for_status()
        stt_job_id = resp.json().get("stt_job_id")
    except Exception as e:
        print(f"  ⚠️  STT job 조회 실패 (STT 없이 진행): {e}")
        return []

    if not stt_job_id:
        print("  ℹ️  이미지 파일 — stt_analysis job 없음")
        return []

    print(f"  ⏳ 코랩 STT 완료 대기 중... (최대 {_STT_POLL_TIMEOUT}s | stt_job={stt_job_id[:8]}…)")
    deadline = time.time() + _STT_POLL_TIMEOUT
    while time.time() < deadline:
        # STT 진행 상황을 메인 job의 진행도에 반영 (STT 0~100% -> 메인 50~70%)
        try:
            job_resp = _get(f"/worker/jobs/{stt_job_id}", timeout=5)
            if job_resp.ok:
                stt_prog = job_resp.json().get("total_progress", 0)
                if stt_prog > 0:
                    main_prog = int(50 + (stt_prog * 0.2))
                    report_progress(job_id, "stt_wait", stt_prog, main_prog, f"음성 분석 중... ({stt_prog}%)")
        except Exception:
            pass

        try:
            resp = _get(f"/worker/jobs/{stt_job_id}/results/audio-pii", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            status_val = data.get("status")
            if status_val == "completed":
                segs = data.get("pii_segments", [])
                print(f"  ✅ 코랩 STT 완료 — 음성 PII {len(segs)}건")
                return segs
            elif status_val in ("failed", "cancelled"):
                print(f"  ⚠️  코랩 STT {status_val} — STT 없이 merger 진행")
                return []
            else:
                print(f"  ⏳ STT 상태: {status_val} — 대기 중...")
        except Exception as e:
            print(f"  ⚠️  STT 상태 확인 오류: {e}")
        time.sleep(_STT_POLL_INTERVAL)

    print(f"  ⚠️  코랩 STT 타임아웃 ({_STT_POLL_TIMEOUT}s) — STT 없이 merger 진행")
    return []


def process_analysis_job(job):
    """analysis job — OCR → (영상만 STT 대기 후 merger) → 등록 → 완료.
    이미지: OCR 단계에서 _result.json 직접 생성 → merger 없이 리포트 페이지로 바로 전달.
    영상:   OCR 단계에서 _index.json 생성 → 코랩 STT 완료 대기 → merger로 _result.json 생성."""
    from OCR_pipeline_report import run_pipeline
    from backend_json_merger import merge_visual_and_audio_reports

    job_id    = job["job_id"]
    upload_id = job.get("upload_id", "")
    file_path = job.get("file_path", "")
    stem      = Path(file_path).stem
    ext       = Path(file_path).suffix.lower()
    is_image  = ext in _IMG_EXTS

    print(f"\n🔍 [analysis] job={job_id[:8]}… | 파일={Path(file_path).name}")

    # 1. 수락
    try:
        _post(f"/worker/jobs/{job_id}/accept", {"worker_id": "local_worker"}).raise_for_status()
    except Exception as e:
        print(f"  ❌ job 수락 실패: {e}")
        return

    # 2. 파일 존재 확인
    if not Path(file_path).exists():
        print(f"  ❌ 파일 없음: {file_path}")
        fail_job(job_id, "FILE_NOT_FOUND", f"파일 없음: {file_path}")
        return

    # 3. OCR 실행
    #    이미지 → _result.json 직접 생성
    #    영상   → _index.json 생성 (STT 대기 후 merger)
    report_progress(job_id, "ocr", 0, 0, "영상 프레임 추출 및 엔진 준비 중...")
    result_path = OUTPUT_DIR / f"{stem}_result.json"
    index_path  = OUTPUT_DIR / f"{stem}_index.json"
    
    import threading
    stt_thread_result = {"segments": [], "completed": False, "failed": False}
    stt_job_id_box = []

    def stt_poller():
        try:
            resp = _get(f"/worker/uploads/{upload_id}/stt-job", timeout=10)
            if not resp.ok: return
            stt_job_id = resp.json().get("stt_job_id")
            if not stt_job_id: return
            stt_job_id_box.append(stt_job_id)
            
            while not stt_thread_result["completed"] and not stt_thread_result["failed"]:
                resp = _get(f"/worker/jobs/{stt_job_id}/results/audio-pii", timeout=10)
                if resp.ok:
                    data = resp.json()
                    status_val = data.get("status")
                    if status_val == "completed":
                        segs = data.get("pii_segments", [])
                        print(f"\n  ✅ 코랩 STT 완료 (병렬 확인) — 음성 PII {len(segs)}건")
                        stt_thread_result["segments"] = segs
                        stt_thread_result["completed"] = True
                        break
                    elif status_val in ("failed", "cancelled"):
                        print(f"\n  ⚠️  코랩 STT {status_val} (병렬 확인) — STT 없이 진행")
                        stt_thread_result["failed"] = True
                        break
                time.sleep(_STT_POLL_INTERVAL)
        except Exception:
            pass

    if not is_image:
        threading.Thread(target=stt_poller, daemon=True).start()

    def _ocr_progress(current_frame, total_frames):
        if total_frames > 0:
            # 0% ~ 50% 구간에서 진행도 업데이트 (10% 즉시 점프 제거하여 ETA 널뛰기 방지)
            pct = int((current_frame / total_frames) * 50)
            report_progress(job_id, "ocr", int(current_frame / total_frames * 100), pct, f"OCR 분석 중... ({current_frame}/{total_frames})")

    try:
        run_pipeline(file_path, progress_callback=_ocr_progress)
        check_path = result_path if is_image else index_path
        if not check_path.exists():
            raise FileNotFoundError(f"{'result' if is_image else 'index'}.json 미생성: {check_path}")
        print(f"  ✅ OCR 완료 → {check_path.name}")
    except Exception as e:
        print(f"  ❌ OCR 실패: {e}")
        fail_job(job_id, "OCR_FAILED", str(e))
        return

    report_progress(job_id, "ocr_done", 100, 50, "OCR 완료")

    # 4. 최종 result.json 확보 + 상세보기 파일 생성
    detail_result = {}
    try:
        if is_image:
            # 이미지: merger 불필요 — OCR 단계에서 이미 result.json 생성됨
            with open(str(result_path), encoding='utf-8') as f:
                final_data = json.load(f)
            print(f"  ✅ 이미지 result.json 로드 완료")

            # 상세보기 이미지 생성 (PII 박스 오버레이 → {stem}_상세보기.jpg)
            report_progress(job_id, "detail_view", 0, 70, "상세보기 이미지 생성 중...")
            try:
                from pipeline_detail_view import run_detail_view
                import pipeline_detail_view as _pdv
                _pdv.OUTPUT_DIR = OUTPUT_DIR  # local_worker의 출력 폴더로 동기화
                detail_result = run_detail_view(str(result_path), input_path=file_path) or {}
                print(f"  ✅ 상세보기 이미지 생성 완료")
            except Exception as dv_err:
                print(f"  ⚠️  상세보기 이미지 생성 오류 (계속 진행): {dv_err}")

        else:
            # 영상: 코랩 STT 대기 후 merger
            stt_job_id = stt_job_id_box[0] if stt_job_id_box else None
            
            if stt_thread_result["completed"]:
                audio_pii_segments = stt_thread_result["segments"]
            elif stt_thread_result["failed"] or not stt_job_id:
                audio_pii_segments = []
            else:
                print(f"  ⏳ 코랩 STT 완료 대기 중... (최대 {_STT_POLL_TIMEOUT}s | stt_job={stt_job_id[:8]}…)")
                report_progress(job_id, "stt_wait", 0, 55, "코랩 STT 완료 대기 중...")
                
                deadline = time.time() + _STT_POLL_TIMEOUT
                while time.time() < deadline:
                    if stt_thread_result["completed"]:
                        audio_pii_segments = stt_thread_result["segments"]
                        break
                    if stt_thread_result["failed"]:
                        audio_pii_segments = []
                        break
                    
                    try:
                        job_resp = _get(f"/worker/jobs/{stt_job_id}", timeout=5)
                        if job_resp.ok:
                            stt_prog = job_resp.json().get("total_progress", 0)
                            if stt_prog > 0:
                                main_prog = int(50 + (stt_prog * 0.2))
                                report_progress(job_id, "stt_wait", stt_prog, main_prog, f"음성 분석 중... ({stt_prog}%)")
                    except Exception:
                        pass
                    time.sleep(_STT_POLL_INTERVAL)
                else:
                    print(f"  ⚠️  코랩 STT 타임아웃 ({_STT_POLL_TIMEOUT}s) — STT 없이 merger 진행")
                    audio_pii_segments = []

            report_progress(job_id, "merge", 0, 70, "결과 병합 중...")
            final_data = merge_visual_and_audio_reports(
                visual_index_path=str(index_path),
                audio_pii_segments=audio_pii_segments,
                output_path=str(result_path),
            )
            print(f"  ✅ 병합 완료 → {result_path.name}")

            # 병합 성공 후 중간 산출물 정리 — result.json만 남김
            for tmp_path, label in [(index_path, "index.json"), (OUTPUT_DIR / f"{stem}_stt.json", "stt.json")]:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                        print(f"  🗑️  {label} 삭제 완료")
                    except Exception as rm_err:
                        print(f"  ⚠️  {label} 삭제 실패: {rm_err}")
            
            # OCR 중간 산출물 (수백MB) 용량 확보를 위해 일괄 삭제
            try:
                for f in OUTPUT_DIR.glob("ocr_data_f*.json"): f.unlink()
                for f in OUTPUT_DIR.glob("region_f*.jpg"): f.unlink()
                for f in OUTPUT_DIR.glob("text_f*.txt"): f.unlink()
                print("  🗑️  OCR 중간 산출물(json, jpg, txt) 정리 완료")
            except Exception as rm_err:
                print(f"  ⚠️  OCR 중간 산출물 삭제 실패: {rm_err}")

            # 상세보기 영상 생성 (PII 박스 오버레이 → {stem}_상세보기.mp4)
            report_progress(job_id, "detail_view", 0, 80, "상세보기 영상 생성 중...")
            try:
                from pipeline_detail_view import run_detail_view
                import pipeline_detail_view as _pdv
                _pdv.OUTPUT_DIR = OUTPUT_DIR  # local_worker의 출력 폴더로 동기화
                detail_result = run_detail_view(str(result_path), input_path=file_path) or {}
                print(f"  ✅ 상세보기 영상 생성 완료")
            except Exception as dv_err:
                print(f"  ⚠️  상세보기 영상 생성 오류 (계속 진행): {dv_err}")

    except Exception as e:
        print(f"  ❌ {'로드' if is_image else '병합'} 실패: {e}")
        fail_job(job_id, "MERGE_FAILED", str(e))
        return

    report_progress(job_id, "register", 0, 90, "결과 등록 중...")

    # 5. PII + artifact 등록 (상세보기 파일 포함)
    _register_pii(job_id, final_data.get("pii_groups", []))
    # 음성 PII 별도 등록 (음성 체크박스 UI 표시용 — visual과 분리하여 DB에 저장)
    _register_audio_pii(job_id, final_data.get("audio_pii_groups", []))
    _register_artifacts(job_id, stem, detail_result=detail_result)

    # 6. 완료
    total = len(final_data.get("pii_groups", [])) + len(final_data.get("audio_pii_groups", []))
    complete_job(job_id, detection_count=total)


# ──────────────────────────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("🚀 Garim 로컬 워커 시작")
    print(f"   백엔드  : {WORKER_BASE}")
    print(f"   출력폴더: {OUTPUT_DIR}")
    print("   처리범위: analysis job만 (mask_preview/mask_final → Colab GPU 워커 전담)")
    print("   대기방식: 이벤트 기반 (job 생성 시 즉시 반응, 안전망 60초)")
    print("   Ctrl+C 로 종료")
    print("=" * 60)

    while True:
        # job 생성 신호를 기다림 (최대 60초 대기 — 안전망 폴링)
        # event.set() 되는 순간 즉시 깨어남, CPU 점유 없음
        _wake_event.wait(timeout=60)
        _wake_event.clear()

        try:
            resp = _req.get(
                f"{WORKER_BASE}/worker/jobs/next",
                params={"worker_type": "local"},   # analysis/mask job만 처리 (stt_analysis는 코랩)
                headers=HEADERS,
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                job  = data.get("job")   # {"job": {...}} 또는 {"job": null}

                if job:
                    jtype = job.get("job_type", "")
                    if jtype == "analysis":
                        try:
                            process_analysis_job(job)
                        except JobCancelled:
                            jid = job.get("job_id", "")
                            print(f"\n🛑 작업 취소 감지 — 처리 즉시 중단 (job={jid[:8]}…)")
                            _confirm_cancelled(jid)   # status='cancelled' 확정(삭제된 경우 무시)
                    else:
                        # mask_preview / mask_final 은 Colab GPU 워커 전담 — 로컬에서 처리 안 함
                        print(f"⚠️  로컬 워커 범위 외 job_type: {jtype} — 건너뜀 (Colab 워커 담당)")
                    # 처리 후 큐에 남은 job이 있을 수 있으므로 즉시 재확인
                    _wake_event.set()
                else:
                    print(".", end="", flush=True)
            else:
                print(f"\n⚠️  polling 응답 오류: {resp.status_code}")

        except _req.exceptions.ConnectionError:
            print(f"\n⚠️  백엔드 연결 실패 ({WORKER_BASE}) — 재시도 대기 중")
        except KeyboardInterrupt:
            print("\n\n👋 워커 종료")
            break
        except Exception as e:
            print(f"\n❌ 예외 발생: {e}")


def start_background_worker(wake_event: threading.Event | None = None):
    """backend/main.py lifespan에서 호출 — 데몬 스레드로 워커 자동 실행
    wake_event: backend의 WORKER_EVENT를 주입하면 job 생성 즉시 반응
    """
    global _wake_event
    if wake_event is not None:
        _wake_event = wake_event
    t = threading.Thread(target=main, daemon=True, name="garim-local-worker")
    t.start()
    return t


if __name__ == "__main__":
    main()
