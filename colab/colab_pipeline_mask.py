"""
마스킹 파이프라인 (이미지 + 영상) - v3 아키텍처 대응
═══════════════════════════════════════════════════════════════════════════════
[코드 역할]
  본 코드는 Colab GPU(또는 로컬) 환경에서 실행되며, 로컬 단계에서 생성된 {stem}_result.json의 
  선택된 PII(is_selected=true) 좌표를 기반으로 실제 이미지/영상 마스킹(인페인팅)만 전담합니다.
  ※ 상세보기(오버레이 생성)는 이제 로컬의 pipeline_detail_view.py가 전담하므로, 본 코드의 역할에서 제외되었습니다.

[마스킹 흐름 (v3 기준 5, 6단계 담당)]
  5. 미리보기(샘플 마스킹) — mask_preview Job 트리거 시
     · 이미지: 원본 전체를 마스킹하여 1장 반환 (프론트에서 가림바를 통한 전/후 비교)
     · 영상  : 선택된 PII 구간의 6초 클립만 잘라서 마스킹 후 반환
  6. 본 처리(전체 마스킹) — mask_final Job 트리거 시
     · result.json의 is_selected=true 인 모든 PII 영역 전체 마스킹 적용
     · 최종 결과물에는 비가시(안 보이는) 워터마크를 삽입하여 제공
     · 처리 완료 후 서버로 결과 파일 전송

[완전 분리 — colab_pipeline_report.py 를 import 하지 않는다]
  · 입력은 {stem}_result.json + (원본 파일). 선택 여부는 json의 is_selected 로 확인.
  · 로컬에서 만들어 둔 좌표만 사용 → 여기서는 OCR/정규식을 다시 돌리지 않음.
  · 마스킹 엔진(적응형 인페인팅·픽셀추적), FFmpeg 처리에만 집중.

[result JSON 인터페이스 — backend_json_merger.py 산출물]
  공통 : pii_groups[].pii_id / pii_type / risk_level / is_selected / masked_coords / bbox / polygons / boxes
  영상 : pii_groups[].keyframes[].{frame,timestamp,bbox,boxes}  ← 픽셀추적 앵커
  참고 : ocr_data(비PII 포함 전체 박스)도 들어있으나 마스킹엔 pii_groups 만 사용

[마스킹 방식 — 적응형 inpaint_adaptive()]
  · 단순 배경=Telea(빠름) / 복잡 무늬 배경(신분증·지폐 등)=LaMa(AI 복원). 둘 다 비가역 삭제.

[워터마크]
  · 최종 결과물(본 처리)에는 무단 사용 방지 및 출처 추적을 위해 비가시(안 보이는) 워터마크를 삽입합니다.

[실행 환경] 
  · 본 마스킹(특히 영상+LaMa)은 무거우므로 Colab/GPU 권장.
  · (향후) 백엔드 워커 큐를 폴링하며 자동으로 마스킹을 수행하도록 연결될 예정.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
# (로컬) OpenMP 중복 로드 충돌 회피 — 실제 서비스시 리눅스 환경에선 제거 권장
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import re
import sys
import json
import math
import hashlib
import subprocess
from pathlib import Path

import cv2
import numpy as np

# 콘솔 UTF-8 (Windows cp949 한글/이모지 출력 오류 방지)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Pillow 10.0+ 에서 is_directory 제거됨 → simple_lama_inpainting 호환 패치
import PIL._util as _pil_util
if not hasattr(_pil_util, 'is_directory'):
    _pil_util.is_directory = os.path.isdir

# ═════════════════════════════════════════════════════════════════════════════
# ▶ 환경설정 (경로 · 마스킹/추적/FFmpeg/워터마크 파라미터 — 모든 설정은 여기서 변경)
# ═════════════════════════════════════════════════════════════════════════════
_DRIVE_BASE = Path("/content/drive/MyDrive/final_PJ_model")
try:
    _LOCAL_BASE = Path(__file__).parent
except NameError:                       # Colab exec() 실행 시 __file__ 없음
    _LOCAL_BASE = Path.cwd()
BASE_DIR        = _DRIVE_BASE if _DRIVE_BASE.exists() else _LOCAL_BASE
INPUT_IMAGE_DIR = BASE_DIR / "test_image_file"     # 원본 이미지 폴더(자동 탐색용)
INPUT_VIDEO_DIR = BASE_DIR / "test_video_file"     # 원본 영상 폴더(자동 탐색용)
OUTPUT_DIR      = BASE_DIR / "output_file"         # 리포트 JSON 위치 + 결과 저장 폴더
FONT_DIR        = BASE_DIR / "fonts"               # 워터마크/라벨용 한글 폰트(.ttf)
IMG_EXTS   = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
VIDEO_EXTS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm')

# ── 적응형 마스킹 ──
DEBUG_PLACEMENT_MODE   = False   # True: 지우지 않고 '지울 영역'을 빨강 반투명으로 표시(타이트한지 확인용) / False: 실제 마스킹
MASK_LAMA_ENABLED      = True   # True: 복잡 배경은 LaMa / False: 항상 Telea(최속)
MASK_COMPLEXITY_THRESH = 0.12   # 배경 엣지밀도 ≥ 이 값이면 '복잡 무늬'→LaMa
TELEA_RADIUS           = 3      # Telea 인페인팅 반경

# ── 일반 PII 마스크 방식 (전화번호·주소 등) ──
#  True : 박스(글자에 타이트한 OCR 영역) 전체를 채워 흐린 획까지 100% 제거 → 검은 잔상 0.
#         박스 '밖'은 안 건드려 주변은 보존되나, 박스 '안'에 걸친 표 선 등은 함께 지워짐(LaMa가 복원).
#  False: 글자 잉크 픽셀만 정교히 골라 지움 → 주변·배경 최대 보존, 단 흐린 획은 잔상으로 남을 수 있음.
MASK_FILL_BOX          = False
MASK_FILL_BOX_PAD      = 2      # 박스 채우기 모드의 외곽 여유(px). 안티앨리어싱 포함용. 잔상 더 있으면 3~4로.

# ── 영상 픽셀 추적 ──
VID_MATCH_THRESH      = 0.50   # NCC 매칭 임계 — 미만이면 동일 픽셀 없음으로 판단, 추적 중지
VID_EDGE_MATCH_THRESH = 0.50   # 추적 경계 NCC 임계
VID_REF_CORR          = 0.40   # 원본 PII와의 정규화상관 임계 — 미만이면 표류로 간주, 추적 중단
VID_REF_CORR_STREAK   = 2      # 연속 N프레임 VID_REF_CORR 미만 시 추적 중단 (순간 흐림 무시)
VID_FULL_ANCHOR_RATIO = 0.8    # keyframe 단어 병합면적이 그룹 최대의 이 비율 이상일 때만 앵커 사용
VID_JUMP_RATIO        = 0.6    # 한 프레임 이동량이 박스 폭의 이 비율 초과 시 순간이동 표류로 판단, 추적 중단
VID_JUMP_MIN_PX       = 12.0   # 프레임 이동 하한(px) — 작은 박스의 임계 과민 방지
VID_SEARCH_RATIO     = 0.8    # 다음 프레임 탐색 여백 확대. 빠르게 나타나는 카드 추적 안정성 강화
VID_DRIFT_LOCK_RATIO = 1.5   # [오매칭·표류 방지] 앵커 원점에서 박스 높이×N 이상 이탈 시 오매칭으로 판단
VID_DRIFT_MIN_PX     = 20.0  # drift lock 최소 허용 이탈(px) — 작은 박스 과민 방지
VID_DRIFT_RETRY_RATIO = 0.15 # 오매칭 판단 후 원점 근방 재탐색 범위(좁게 → 인근 PII 오매칭 차단)
VID_TRACK_EXPAND     = 0.40   # 추적용 박스 확장 비율 증가. 주변 픽셀을 넉넉히 물고 추적해 안정성 확보.
VID_MASK_PAD_PX      = 4      # 마스킹 박스 사방 여유 픽셀
VID_AFFINE_SCALE_MIN = 0.6    # 회전추적 허용 최소 스케일
VID_AFFINE_SCALE_MAX = 1.7    # 회전추적 허용 최대 스케일
VID_AFFINE_ANGLE_MAX = 25.0   # 회전추적 허용 최대 각도(도)
VID_AFFINE_PREFER_ROT   = 1.0  # 한 프레임 회전이 이 각도(도) 이상이면 shift 대신 affine 채택
VID_AFFINE_PREFER_SCALE = 0.02 # 한 프레임 크기변화가 이 비율 이상이면 affine 채택

# ── 구간별 정밀 블록 매칭(N등분) — 긴 텍스트를 여러 블록으로 쪼개 NCC 매칭, 화면 밖 일부 잘려도 추적 가능 ──
VID_BLOCK_MIN_PX     = 24     # 블록 최소 길이(px) — 너무 작으면 매칭 불안정
VID_BLOCK_MAX_N      = 8      # 블록 최대 개수 — 연산량 제한
VID_BLOCK_VIS_RATIO  = 0.6    # 블록이 화면 안에 이 비율 이상 보일 때만 신뢰

# ── 화면 밖 퇴장(exit) 외삽 — 경계 갇힘 방지, 마지막 속도로 박스를 계속 밀어냄 ──
VID_EXIT_BORDER_PX   = 2      # 이 픽셀 이내로 경계 접촉 시 퇴장 판정 (진짜 화면 끝에서만 외삽 — 화면 안 박스 오판 방지)
VID_EXIT_MAX_FILL    = 120    # 퇴장 외삽 최대 프레임 수(안전장치) — 화면 밖 완전 이탈(overlap=0) 시 자동 종료되므로 넉넉히
VID_EXIT_MIN_SPEED   = 1.0    # 이동속도(px/frame) 이상일 때만 외삽
VID_EXIT_STALL_RATIO = 0.35   # 진행방향 실제이동이 속도의 이 비율 미만이면 경계 갇힘 → 외삽 전환
VID_EXIT_VEL_EMA     = 0.6    # 이동속도 EMA 계수(클수록 과거 속도 반영)

# ── 장면 전환(컷) 감지 — 히스토그램 상관도 미만이면 컷 판정, 추적 즉시 중단 ──
SCENE_CUT_CORR = 0.6

# ── 상세보기 오버레이 트랙 다운샘플 ──
TRACK_FPS = 10   # 오버레이 track 다운샘플 fps(촘촘할수록 매끈하나 JSON↑, 8~12 권장)
TRACK_SMOOTH_EMA = 0.5  # 상세보기 박스 시간축 평활(EMA) 계수. 0=평활안함 ~ 1=과거100%(떨림↓, 반응↓)

# ── FFmpeg 인코딩 ──
FFMPEG_CRF    = 18
FFMPEG_PRESET = 'fast'

# ── 미리보기(5단계) ──
PREVIEW_VIDEO_MARGIN_SEC = 3.0   # 영상 샘플: 개인정보 탐지 지점 전/후 여유(초) → 총 약 6초

# ── 워터마크 ──
WATERMARK_TEXT        = "garim"  # 가시(우하단) 문구
WATERMARK_PAYLOAD     = "garim"  # 비가시 시드(서비스에선 사용자/잡 ID 권장 → 출처 추적)
WATERMARK_VISIBLE     = False    # 최종 결과물 우하단 'garim' 가시 워터마크 OFF — 비가시 워터마크만 삽입(요청)
WATERMARK_INVISIBLE   = True
WM_INVISIBLE_STRENGTH = 2.0      # 비가시 워터마크 세기(1~3 권장)

# LaMa 자동 설치 (Colab 등 미설치 대비)
try:
    import simple_lama_inpainting  # noqa: F401
except ImportError:
    print("📦 simple-lama-inpainting 설치 중...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "simple-lama-inpainting"])
    print("✅ 패키지 설치 완료!")

try:
    import torch
    USE_GPU = torch.cuda.is_available()
    print(f"🖥️  GPU 사용 가능: {USE_GPU} "
          f"({'CUDA: ' + torch.cuda.get_device_name(0) if USE_GPU else 'CPU 모드'})")
except Exception:
    USE_GPU = False

lama_model = None   # LaMa 모델 전역 1회 로딩 캐시

def _check_nvenc() -> bool:
    """FFmpeg h264_nvenc(GPU 인코더) 지원 여부 확인 (1회 캐싱)."""
    if not hasattr(_check_nvenc, '_result'):
        try:
            r = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
            _check_nvenc._result = 'h264_nvenc' in r.stdout
        except Exception:
            _check_nvenc._result = False
        if _check_nvenc._result:
            print("  ✅ FFmpeg h264_nvenc(GPU) 인코딩 활성화")
        else:
            print("  ℹ️  h264_nvenc 미지원 → libx264(CPU) 인코딩 사용")
    return _check_nvenc._result


# ═════════════════════════════════════════════════════════════════════════════
# 적응형 인페인팅 (Telea / LaMa 자동 선택) — 비가역 삭제
# ═════════════════════════════════════════════════════════════════════════════
def _bg_complexity(image_cv: np.ndarray, mask: np.ndarray) -> float:
    """마스크 '주변 배경'의 복잡도(0~1)를 엣지 밀도로 추정 → Telea/LaMa 선택 근거."""
    x, y, w, h = cv2.boundingRect(mask)
    if w == 0 or h == 0:
        return 0.0
    H, W = image_cv.shape[:2]
    pad = max(8, int(0.5 * max(w, h)))
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(W, x + w + pad), min(H, y + h + pad)
    roi      = image_cv[y1:y2, x1:x2]
    roi_mask = mask[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    gray  = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    bg    = cv2.bitwise_not(roi_mask)
    bg_edges = cv2.bitwise_and(edges, bg)
    bg_area  = max(1, cv2.countNonZero(bg))
    return cv2.countNonZero(bg_edges) / bg_area


def _get_lama():
    """LaMa 모델 최초 1회 로딩. 실패 시 False 캐싱 → 이후 전부 Telea(재시도/로그 폭주 방지)."""
    global lama_model
    if lama_model is None:
        try:
            from simple_lama_inpainting import SimpleLama
            print("🔄 LaMa 모델 로딩 중... (복잡 배경 복원용)")
            lama_model = SimpleLama()
        except Exception as e:
            print(f"⚠️ LaMa 미설치/로딩 실패 → 이후 전부 Telea 사용: {e}")
            lama_model = False
    return lama_model or None


def _lama_inpaint(image_cv: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """LaMa로 마스크 영역 복원. 마스크 bbox 주변만 crop해 처리(속도)."""
    model = _get_lama()
    if model is None:
        return cv2.inpaint(image_cv, mask, TELEA_RADIUS, cv2.INPAINT_TELEA)
    from PIL import Image as PILImage
    x, y, w, h = cv2.boundingRect(mask)
    H, W = image_cv.shape[:2]
    pad = 64
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(W, x + w + pad), min(H, y + h + pad)
    crop_img  = image_cv[y1:y2, x1:x2]
    crop_mask = mask[y1:y2, x1:x2]
    try:
        pil_img  = PILImage.fromarray(cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB))
        pil_mask = PILImage.fromarray(crop_mask)
        out      = model(pil_img, pil_mask)
        restored = cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)
        restored = cv2.resize(restored, (crop_img.shape[1], crop_img.shape[0]),
                              interpolation=cv2.INTER_LANCZOS4)
        _, bin_mask = cv2.threshold(crop_mask, 127, 255, cv2.THRESH_BINARY)
        bin_3c = cv2.cvtColor(bin_mask, cv2.COLOR_GRAY2BGR)
        result = image_cv.copy()
        result[y1:y2, x1:x2] = np.where(bin_3c == 255, restored, crop_img)
        return result
    except Exception as e:
        print(f"⚠️ LaMa 처리 오류 → Telea 대체: {e}")
        return cv2.inpaint(image_cv, mask, TELEA_RADIUS, cv2.INPAINT_TELEA)


def inpaint_adaptive(image_cv: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """마스크 주변 배경 복잡도에 따라 Telea/LaMa 자동 선택(둘 다 복원 불가 삭제)."""
    if cv2.countNonZero(mask) == 0:
        return image_cv
    if MASK_LAMA_ENABLED and _bg_complexity(image_cv, mask) >= MASK_COMPLEXITY_THRESH:
        return _lama_inpaint(image_cv, mask)
    return cv2.inpaint(image_cv, mask, TELEA_RADIUS, cv2.INPAINT_TELEA)


# ═════════════════════════════════════════════════════════════════════════════
# 이미지 PII 영역 마스킹 (Smart Bubble Mask + 적응형 복원)
# ═════════════════════════════════════════════════════════════════════════════
def synthesize_pii_region(image_cv, line_boxes, pii_type=""):
    """텍스트만 정교하게 마스크로 떠서 적응형 인페인팅으로 삭제.
    - 카드번호: 엠보싱 잔상까지 박멸 위해 박스 전체를 채워 팽창
    - 일반 PII: 글자 뼈대(잉크)만 따서 배경선 보존"""
    if not line_boxes:
        return image_cv
    solid_mask = np.zeros(image_cv.shape[:2], dtype=np.uint8)
    gray_image = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)

    for b in line_boxes:
        if b.get('vertices') and len(b['vertices']) >= 3:
            pts = np.array([[[p['x'], p['y']] for p in b['vertices']]], dtype=np.int32)
        else:
            x_min, y_min = b.get('x_min', 0), b.get('y_min', 0)
            x_max, y_max = b.get('x_max', 0), b.get('y_max', 0)
            pts = np.array([[[x_min, y_min], [x_max, y_min], [x_max, y_max], [x_min, y_max]]], dtype=np.int32)

        x, y, w, h = cv2.boundingRect(pts)
        pad = 15 if pii_type == "카드번호" else 8
        c_x1, c_y1 = max(0, x - pad), max(0, y - pad)
        c_x2, c_y2 = min(image_cv.shape[1], x + w + pad), min(image_cv.shape[0], y + h + pad)
        roi_gray = gray_image[c_y1:c_y2, c_x1:c_x2]
        
        if roi_gray.size == 0: continue
        pts_roi = pts - np.array([c_x1, c_y1])
        
        if pii_type == "카드번호":
            final_local_mask = np.zeros(roi_gray.shape, dtype=np.uint8)
            cv2.fillPoly(final_local_mask, pts_roi, 255)
            dil_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 7))
            final_local_mask = cv2.dilate(final_local_mask, dil_kernel, iterations=2)
            final_local_mask = final_local_mask[:roi_gray.shape[0], :roi_gray.shape[1]]
        elif MASK_FILL_BOX:
            # ── [방식 1 · 박스 채우기] 검은 잉크 잔상 0 ────────────────────────────────
            #  글자 픽셀만 고르면 흐린 획을 놓쳐 잔상이 남으므로, OCR 박스 영역 전체를 채워
            #  흐린 획까지 통째로 제거한다. 박스가 글자에 타이트해 박스 밖(표 선·다른 글자)은 보존.
            final_local_mask = np.zeros(roi_gray.shape, dtype=np.uint8)
            cv2.fillPoly(final_local_mask, pts_roi, 255)
            if MASK_FILL_BOX_PAD > 0:   # 글자 외곽 안티앨리어싱 포함(아주 약하게)
                k = 2 * MASK_FILL_BOX_PAD + 1
                final_local_mask = cv2.dilate(
                    final_local_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)), iterations=1)
        else:
            # ── [방식 2 · 잉크만] 주변 최대 보존 (단 흐린 획은 잔상 가능) ───────────────
            block_size = min(31, min(roi_gray.shape[0], roi_gray.shape[1]))
            if block_size % 2 == 0: block_size -= 1
            if block_size < 3: block_size = 3
            if block_size >= 3:
                # 텍스트 가장자리 픽셀까지 넉넉하게 잡기 위해 C 상수를 낮춤 (10 -> 5)
                ink_mask = cv2.adaptiveThreshold(roi_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                 cv2.THRESH_BINARY_INV, block_size, 0)
            else:
                _, ink_mask = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

            # 글자 획 사이의 끊긴 작은 틈을 메워(MORPH_CLOSE) '덜 지워진 검은 획'을 마스크에 포함.
            #  ※ 박스 '밖'은 아래 poly_mask AND 에서 전부 제거되므로 주변은 절대 건드리지 않음.
            ink_mask = cv2.morphologyEx(ink_mask, cv2.MORPH_CLOSE,
                                        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)

            # 텍스트 주변 훼손 없이 글자만 지우도록 타이트한 팽창 유지
            kernel_thin = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            thin_mask = cv2.dilate(ink_mask, kernel_thin, iterations=1)

            poly_mask = np.zeros(roi_gray.shape, dtype=np.uint8)
            cv2.fillPoly(poly_mask, pts_roi, 255)
            poly_mask = cv2.dilate(poly_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)

            final_local_mask = cv2.bitwise_and(thin_mask, poly_mask)

        solid_mask[c_y1:c_y2, c_x1:c_x2] = cv2.bitwise_or(
            solid_mask[c_y1:c_y2, c_x1:c_x2], final_local_mask)

    if DEBUG_PLACEMENT_MODE:
        # [위치 검증] 실제로 지우지 않고, '지울 영역(solid_mask)'을 빨강 반투명으로 덮어 표시.
        #   → 텍스트만 타이트하게 잡혔는지, 주변(다른 글자·배경)을 침범하지 않는지 눈으로 확인.
        vis = image_cv.copy()
        m = solid_mask > 0
        if np.any(m):
            vis[m] = (0.35 * image_cv[m].astype(np.float32)
                      + 0.65 * np.array([0, 0, 255], np.float32)).astype(np.uint8)  # BGR 빨강
        return vis
    return inpaint_adaptive(image_cv, solid_mask)


def mask_selected_on_image(image_cv, pii_groups, selected_ids=None):
    """report_json의 pii_groups 중 selected_ids 그룹만 마스킹(미리보기·본마스킹 공용).
      selected_ids=None → 전체 / [...] → 고른 pii_id만."""
    out = image_cv.copy()
    for g in pii_groups:
        if selected_ids is not None and g.get('pii_id') not in selected_ids:
            continue
        out = synthesize_pii_region(out, g.get('boxes', []), pii_type=g.get('pii_type', ''))
    return out


# ═════════════════════════════════════════════════════════════════════════════
# 상세보기 오버레이 — PII 박스 표시 (3단계 전용)
# ═════════════════════════════════════════════════════════════════════════════

# PII 타입별 색상 (BGR)
_PII_COLORS = {
    "주민등록번호": (50, 50, 255), "외국인등록번호": (50, 50, 255),
    "전화번호": (50, 255, 50), "주소": (255, 150, 50),
    "카드번호": (50, 150, 255), "계좌번호": (50, 255, 255), "이메일": (255, 50, 150),
}
_PII_DEFAULT_COLOR = (255, 100, 255)

# 한글 폰트 없을 때 라벨 fallback(영문)
_PII_ENG_LABELS = {
    "주민등록번호": "Resident ID", "외국인등록번호": "Foreigner ID", "여권번호": "Passport",
    "운전면허번호": "Driver License", "전화번호": "Phone", "카드번호": "Card Number",
    "계좌번호": "Bank Account", "이메일": "Email", "건강보험증번호": "Health Insurance",
    "생년월일": "Birthdate", "나이": "Age", "주소": "Address",
}


def _load_kor_font(size=15):
    """한글 폰트 우선 로딩(폰트폴더 → Windows → Linux). 실패 시 기본폰트."""
    from PIL import ImageFont
    try:
        font_list = list(FONT_DIR.glob("*.ttf"))
        if font_list:
            try: return ImageFont.truetype(str(font_list[0]), size)
            except Exception: pass
        if os.name == 'nt':
            for fn in ["malgun.ttf", "gulim.ttc", "batang.ttc"]:
                try: return ImageFont.truetype(f"C:/Windows/Fonts/{fn}", size)
                except Exception: continue
        for lf in ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                   "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"]:
            if os.path.exists(lf):
                try: return ImageFont.truetype(lf, size)
                except Exception: continue
    except Exception:
        pass
    return ImageFont.load_default()


def draw_pii_report(image_cv, pii_groups):
    """
    상세보기용 PII 오버레이 이미지 생성.
    각 PII 그룹의 polygon에 색상 박스 + 라벨('주소1', '전화번호1')을 그려 반환.
    pii_groups: report JSON의 pii_groups 구조 사용.
    """
    from PIL import Image as PILImage, ImageDraw
    pil_img = PILImage.fromarray(cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = PILImage.new("RGBA", pil_img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    label_font = _load_kor_font(15)

    for g in pii_groups:
        pii_type = g['pii_type']
        bgr = _PII_COLORS.get(pii_type, _PII_DEFAULT_COLOR)
        r, gg, b = bgr[2], bgr[1], bgr[0]   # BGR→RGB 변환
        display_text = g.get('pii_label', pii_type)

        first_top_left = None
        for poly in g.get('polygons', []):
            pts = [tuple(p) for p in poly]
            if len(pts) < 3:
                continue
            draw.polygon(pts, outline=(r, gg, b, 255), fill=(r, gg, b, 50))
            draw.line(pts + [pts[0]], fill=(r, gg, b, 255), width=2)
            tl = min(pts, key=lambda p: p[0] + p[1])
            if first_top_left is None or (tl[0] + tl[1]) < (first_top_left[0] + first_top_left[1]):
                first_top_left = tl

        # bbox fallback (polygon 없는 경우)
        if first_top_left is None and g.get('bbox'):
            bx = g['bbox']
            pts = [(bx[0], bx[1]), (bx[2], bx[1]), (bx[2], bx[3]), (bx[0], bx[3])]
            draw.polygon(pts, outline=(r, gg, b, 255), fill=(r, gg, b, 50))
            first_top_left = (bx[0], bx[1])

        # 라벨은 그룹당 1개(가장 좌상단)
        if first_top_left is not None:
            try:
                lb = label_font.getbbox(display_text)
                lw, lh = lb[2] - lb[0], lb[3] - lb[1]
            except Exception:
                lw, lh = 80, 15
            label_y = max(first_top_left[1] - lh - 6, 0)
            draw.rectangle([first_top_left[0], label_y,
                            first_top_left[0] + lw + 6, label_y + lh + 6], fill=(r, gg, b, 210))
            draw.text((first_top_left[0] + 3, label_y + 3), display_text,
                      fill=(255, 255, 255, 255), font=label_font)

    return cv2.cvtColor(np.array(PILImage.alpha_composite(pil_img, overlay).convert("RGB")),
                        cv2.COLOR_RGB2BGR)


# ═════════════════════════════════════════════════════════════════════════════
# 상세보기 오버레이 트랙 생성 (영상 전용 — NCC 픽셀 추적)
# ═════════════════════════════════════════════════════════════════════════════
def _is_scene_cut(prev_frame, cur_frame) -> bool:
    """연속 두 프레임이 '장면 전환(컷)'인지 판정. 그레이 히스토그램 상관도가 임계 미만이면 True.
    PII 가 컷으로 사라지거나(추적 표류 방지) 이전 장면까지 역추적되는 것을 막는 데 사용."""
    a = cv2.cvtColor(cv2.resize(prev_frame, (64, 36)), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cv2.resize(cur_frame, (64, 36)), cv2.COLOR_BGR2GRAY)
    ha = cv2.calcHist([a], [0], None, [32], [0, 256])
    hb = cv2.calcHist([b], [0], None, [32], [0, 256])
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    return cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL) < SCENE_CUT_CORR


def _ref_patch(frame, bbox, size: int = 48):
    """프레임의 bbox 영역을 그레이 48×48 패치로 추출(원본 카드 외형 기준). 영역이 없으면 None."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    patch = frame[y1:y2, x1:x2]
    if patch.size == 0:
        return None
    g = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if patch.ndim == 3 else patch
    return cv2.resize(g, (size, size))


def _patch_corr(a, b) -> float:
    """같은 크기 그레이 패치 a,b 의 정규화 상관계수(-1~1). 추적 영역이 '원본 카드'와
    얼마나 유사한지 판단 → 배경/장면전환으로 표류했는지 검증용."""
    if a is None or b is None:
        return 1.0                       # 비교 불가 시 통과(검증 생략)
    af = a.astype(np.float32); bf = b.astype(np.float32)
    af -= af.mean(); bf -= bf.mean()
    denom = (np.sqrt((af * af).sum()) * np.sqrt((bf * bf).sum()))
    return float((af * bf).sum() / denom) if denom > 1e-6 else 0.0


def _bbox_quad_from_boxes(boxes: list):
    """추적된 박스들 → (axis bbox [x1,y1,x2,y2], 개별 단어들의 회전 quads 리스트). 오버레이 표시용."""
    pts = []
    quads = []
    for b in boxes:
        if b.get('vertices') and len(b['vertices']) >= 3:
            q = [(p['x'], p['y']) for p in b['vertices']]
            pts += q
            quads.append(q)
        elif 'x_min' in b:
            q = [(b['x_min'], b['y_min']), (b['x_max'], b['y_min']),
                 (b['x_max'], b['y_max']), (b['x_min'], b['y_max'])]
            pts += q
            quads.append(q)
    if not pts:
        return None, None
    arr = np.array(pts, dtype=np.float32)
    x1, y1 = int(arr[:, 0].min()), int(arr[:, 1].min())
    x2, y2 = int(arr[:, 0].max()), int(arr[:, 1].max())
    return [x1, y1, x2, y2], quads


def _merge_boxes_to_quad(boxes: list):
    """추적된 단어 박스들을 '하나로 감싸는 회전된 박스 1개'(minAreaRect)로 병합.
    반환: (axis bbox [x1,y1,x2,y2], 병합 회전 quad [[x,y]*4]).

    [왜 minAreaRect 인가]
      같은 구역(zone)의 개인정보는 OCR 이 단어별 박스 여러 개로 잡는다(예: '5678','9012','3455').
      이를 단어 1개만 골라 표시하면(과거 _pick_overlay_box 방식) 큰 박스 없는 keyframe(frame 394)
      에서 단어 1개만 그려져 위치·범위가 틀어진다. 대신 '모든 단어 점'을 감싸는 최소 회전 사각형을
      구하면, 카드처럼 기울어진(angle) 개인정보도 전체를 딱 맞게 감싸는 박스 1개로 표시된다."""
    pts = []
    for b in boxes:
        if b.get('vertices') and len(b['vertices']) >= 3:
            pts += [(p['x'], p['y']) for p in b['vertices']]
        elif 'x_min' in b:
            pts += [(b['x_min'], b['y_min']), (b['x_max'], b['y_min']),
                    (b['x_max'], b['y_max']), (b['x_min'], b['y_max'])]
    if not pts:
        return None, None
    arr = np.array(pts, dtype=np.float32)
    rect = cv2.minAreaRect(arr)            # ((cx,cy),(w,h),angle) — 점들을 감싸는 최소 회전 사각형
    quad = cv2.boxPoints(rect)             # 회전 사각형의 꼭짓점 4개
    x1, y1 = int(arr[:, 0].min()), int(arr[:, 1].min())
    x2, y2 = int(arr[:, 0].max()), int(arr[:, 1].max())
    return [x1, y1, x2, y2], [[float(p[0]), float(p[1])] for p in quad]


def _drop_container_boxes(boxes: list, pad: int = 3):
    """다른 단어 박스 여러 개를 통째로 감싸는 '컨테이너 박스'(OCR 이 한 줄 전체를 한 번에 잡은 큰
    박스)를 제외하고 단어별 박스만 남긴다 → 마스킹을 단어 크기에 맞춰 타이트하게(주변 배경 보존).
    단, 단어별 박스가 하나도 없으면(큰 박스만 존재) 원본을 그대로 반환 → 미탐지 부위 노출 방지 우선."""
    if len(boxes) <= 1:
        return boxes

    def _contains(o, i):
        return (o.get('x_min', 0) <= i.get('x_min', 0) + pad and
                o.get('y_min', 0) <= i.get('y_min', 0) + pad and
                o.get('x_max', 0) >= i.get('x_max', 0) - pad and
                o.get('y_max', 0) >= i.get('y_max', 0) - pad)

    keep = []
    for b in boxes:
        others = [x for x in boxes if x is not b]
        if sum(1 for x in others if _contains(b, x)) >= 2:
            continue   # 단어 2개 이상을 포함 → 전체 묶음(컨테이너)으로 보고 제외
        keep.append(b)
    return keep if keep else boxes


# ── 영상 회전 메타데이터 보정 ────────────────────────────────────────────────
# 폰 세로영상은 가로로 저장 + '시계 90도 회전' 메타를 가진다. OCR(ffmpeg 백엔드)은 메타를
# 적용해 세로(예 720x1280)로 처리하지만, 일부 로컬 cv2 는 메타를 무시하고 가로(1280x720) raw
# 를 읽어 상세보기·결과가 90도 누워서 출력된다. → run_* 진입 시 index(OCR) 해상도와 비교해
# 회전코드를 전역에 설정하고, 모든 프레임 읽기(_rot_read)에서 동일 방향으로 보정한다.
_FRAME_ROT = None   # 현재 처리 중인 영상의 프레임 회전코드(None=보정 불필요). 단일 영상 순차처리 전제.


def _set_frame_rot(cap, ref_w, ref_h):
    """cap 해상도가 index(OCR) 기준(ref_w×ref_h)과 90도 어긋나면 회전코드를 전역에 설정.
    메타(CAP_PROP_ORIENTATION_META)가 있으면 메타 우선, 없으면 폰 세로=시계방향 기본. 반환: 회전코드 or None."""
    global _FRAME_ROT
    _FRAME_ROT = None
    try:
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    except Exception:
        return None
    if not ref_w or not ref_h:
        return None
    ref_w, ref_h = int(ref_w), int(ref_h)
    if (W, H) == (ref_w, ref_h):
        return None                                   # 이미 일치 → 회전 불필요
    if (W, H) == (ref_h, ref_w):                       # 가로↔세로 90도 어긋남 → 회전 필요
        meta = 0
        try:
            meta = int(cap.get(cv2.CAP_PROP_ORIENTATION_META))
        except Exception:
            meta = 0
        if meta in (270, -90):
            _FRAME_ROT = cv2.ROTATE_90_COUNTERCLOCKWISE
        else:
            _FRAME_ROT = cv2.ROTATE_90_CLOCKWISE       # 폰 세로(시계) 기본
    return _FRAME_ROT


def _rot_read(cap):
    """cap.read() + 전역 회전보정 적용 → 회전메타를 무시하는 환경에서도 OCR 과 동일 방향 보장."""
    ret, frame = cap.read()
    if ret and _FRAME_ROT is not None:
        frame = cv2.rotate(frame, _FRAME_ROT)
    return ret, frame


def _track_one_dir(cap, start_fi, boxes, bbox, direction, limit_fi, total_frames, frames: dict,
                   match_thresh=VID_MATCH_THRESH, anchor_bbox=None):
    """start_fi에서 한 방향(+1/-1)으로 픽셀 추적하며 frames[fi]=추적된 boxes 기록(마스킹 안 함).
    match_thresh: NCC 매칭 임계(keyframe 사이=기본, 흐릿한 edge 구간=VID_EDGE_MATCH_THRESH)."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_fi)
    ret, prev = _rot_read(cap)
    if not ret:
        return
    H, W = prev.shape[:2]
    cur_boxes, cur_bbox, fi = boxes, bbox, start_fi
    vx, vy = 0.0, 0.0          # 누적 이동속도(EMA) — 경계 퇴장 시 외삽에 사용(마스킹 함수와 동일 정책)

    # ── [속도개선] 역방향(등장 역추적) 프레임 공급기 ──────────────────────────────
    #  H.264 영상은 프레임별 random seek 시 직전 키프레임부터 재디코딩하므로(역방향 1칸
    #  뒤로 가는 데 수십 프레임 디코딩) 매우 느리다. 그래서 역방향은 [블록] 단위로 한 번만
    #  seek 하여 순차 디코딩한 뒤 캐시에서 역순으로 꺼내 쓴다.
    #  ★ 핵심: 같은 프레임 인덱스를 디코딩하므로 _rot_read() 결과 픽셀이 seek 방식과 100%
    #     동일 → matchTemplate·corr 판정·박스 좌표가 전혀 바뀌지 않는다(추적 정확도 보존).
    _rev_cache = {}            # {frame_index: BGR 프레임(회전 보정 적용)}
    _REV_BLOCK = 64            # 역방향 1회 순차 디코딩 블록 크기(프레임). 720x1280 기준 ~170MB 상한.

    def _read_cur(target_fi):
        """현재 진행 방향에 맞는 다음 프레임을 (ret, frame)으로 반환.
        정방향=순차 read(빠름) / 역방향=블록 prefetch 캐시(seek 1회/블록)."""
        if direction > 0:
            return _rot_read(cap)                       # 정방향은 기존과 동일(순차 디코딩)
        # 역방향: 캐시에 없으면 [block_lo, target_fi] 구간을 한 번 순차 디코딩해 채운다
        if target_fi not in _rev_cache:
            _rev_cache.clear()
            block_lo = max(0, target_fi - _REV_BLOCK + 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, block_lo)  # ← seek 는 블록당 단 1회
            for f in range(block_lo, target_fi + 1):
                r, fr = _rot_read(cap)
                if not r:
                    break
                _rev_cache[f] = fr
        fr = _rev_cache.pop(target_fi, None)
        return (fr is not None), fr

    # 가까운 앵커 우선 기록: frames[f] = (boxes, 앵커와의 거리). 여러 keyframe(앵커)이 같은
    #  프레임을 추적할 때, start_fi 에 더 가까운 앵커가 추적한 좌표만 유지한다(사용자 명세 ④).
    def _rec(f, b):
        d = abs(f - start_fi)
        e = frames.get(f)
        if e is None or d < e[1]:
            frames[f] = (b, d)

    ref_patch = _ref_patch(prev, bbox)   # 추적 시작 시점의 '원본 카드' 외형(표류 검증 기준)
    miss_streak = 0                      # 원본 PII 와 상관도가 연속으로 낮았던 프레임 수(사라짐 연속 판정)
    while True:
        nfi = fi + direction
        if direction > 0 and nfi >= limit_fi: break
        if direction < 0 and nfi <= limit_fi: break
        if nfi < 0 or nfi >= total_frames: break
        # 다음 프레임 획득(정방향=순차 read / 역방향=블록 prefetch 캐시).
        #  ※ 두 경로 모두 nfi 프레임의 동일 픽셀을 반환 — 추적 결과 불변, 속도만 개선.
        ret, cur = _read_cur(nfi)
        if not ret: break
        # [개선] 전체화면 장면전환(컷) 감지 제거 — 전체 프레임 히스토그램은 배경 움직임(거리·사람)
        #   이나 카드가 흐려지는 것을 '컷'으로 오판해, 카드가 화면에 있는데도 추적을 끊었다
        #   (첫 카드 5초 소멸 / 두번째 카드 흐릿한 등장 누락의 직접 원인).
        #   대신 픽셀 NCC 매칭 성공=같은 개인정보(픽셀) 존재로 보고 추적을 지속하고, 실패하면 중단한다.
        res = _vid_match_shift(prev, cur, cur_bbox, VID_SEARCH_RATIO, match_thresh)
        # 추적 실패: (퇴장=정방향) 화면 밖으로 나가는 중이면 마지막 속도로 끝까지 외삽 후 종료.
        #   ※ 등장=역방향(direction<0)에서는 외삽 금지 — 픽셀 매칭이 끊긴 지점에서 즉시 멈춘다.
        #     (외삽은 픽셀 비교 없이 속도로 박스를 만들어 '번호 없는 화면 밖에서 박스가 날아오는'
        #      현상을 유발하므로, 등장 역추적에는 적용하지 않는다.)
        if res is None:
            if direction > 0 and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_BORDER_PX):
                _exit_extrapolate(cur_boxes, cur_bbox, (vx, vy), fi, direction,
                                  limit_fi, total_frames, W, H,
                                  lambda f, b, bb: _rec(f, b))
            break
        # 새 위치 계산
        if res[0] == 'affine':
            new_boxes = _transform_boxes_affine(cur_boxes, res[1])
            xs = [b['x_min'] for b in new_boxes] + [b['x_max'] for b in new_boxes]
            ys = [b['y_min'] for b in new_boxes] + [b['y_max'] for b in new_boxes]
            new_bbox = (min(xs), min(ys), max(xs), max(ys))
        else:
            _, dx, dy = res
            new_boxes = _shift_boxes(cur_boxes, dx, dy)
            new_bbox = (cur_bbox[0]+dx, cur_bbox[1]+dy, cur_bbox[2]+dx, cur_bbox[3]+dy)
        # [오매칭·표류 방지 — drift lock]
        # 앵커 원점(keyframe)에서 허용 범위(박스 높이 × VID_DRIFT_LOCK_RATIO) 이상 이탈하면
        # 오매칭으로 판단하여 원점 근방에서 좁게 재탐색.
        # 재탐색 성공 → 원점 기준 위치로 교정 / 실패 → 이전 위치 유지 (박스 사라짐 없음).
        # 정상 케이스(drift 이내): float 연산 몇 개만 추가 → 속도 영향 없음.
        if anchor_bbox is not None:
            anc_cx = (anchor_bbox[0] + anchor_bbox[2]) / 2.0
            anc_cy = (anchor_bbox[1] + anchor_bbox[3]) / 2.0
            max_drift = max(VID_DRIFT_MIN_PX,
                            VID_DRIFT_LOCK_RATIO * (anchor_bbox[3] - anchor_bbox[1]))
            new_cx = (new_bbox[0] + new_bbox[2]) / 2.0
            new_cy = (new_bbox[1] + new_bbox[3]) / 2.0
            if ((new_cx - anc_cx)**2 + (new_cy - anc_cy)**2)**0.5 > max_drift:
                retry = _vid_ncc_probe(prev, cur, anchor_bbox, VID_DRIFT_RETRY_RATIO)
                if retry is not None and retry[2] >= match_thresh:
                    rx, ry = int(round(retry[0])), int(round(retry[1]))
                    new_boxes = _shift_boxes(boxes, rx, ry)
                    new_bbox = (anchor_bbox[0]+rx, anchor_bbox[1]+ry,
                               anchor_bbox[2]+rx, anchor_bbox[3]+ry)
                else:
                    new_boxes, new_bbox = cur_boxes, cur_bbox   # 이전 위치 유지
        # [원본 카드 검증 — 연속 판정] 추적 영역이 최초 탐지 카드와 얼마나 같은지 매 프레임 측정.
        #  단일 프레임이 임계 미만이어도 즉시 끊지 않고(순간 흐림/노이즈 허용), 'VID_REF_CORR_STREAK'
        #  프레임 연속으로 미달할 때만 중단 → 화면이 실제로 다른 장면으로 바뀐 경우에만 박스 제거.
        #  (사용자 명세: 좌표·픽셀이 같으면 같은 PII 로 보고 따라가고, 진짜 사라지면 박스도 사라지게.)
        corr_ok = _patch_corr(ref_patch, _ref_patch(cur, new_bbox)) >= VID_REF_CORR
        if not corr_ok:
            miss_streak += 1
            if miss_streak >= VID_REF_CORR_STREAK:
                break
        else:
            miss_streak = 0              # 다시 원본과 유사해지면 누적 초기화(흐렸다 또렷해지는 카드)
        rdx = ((new_bbox[0]+new_bbox[2]) - (cur_bbox[0]+cur_bbox[2])) / 2.0
        rdy = ((new_bbox[1]+new_bbox[3]) - (cur_bbox[1]+cur_bbox[3])) / 2.0
        speed = (vx*vx + vy*vy) ** 0.5
        # 역방향 한 프레임 이동이 박스 폭 비례 한계 초과 시 순간이동 표류로 판단, 추적 중단
        cur_speed = (rdx*rdx + rdy*rdy) ** 0.5
        jump_limit = max(VID_JUMP_MIN_PX, VID_JUMP_RATIO * (cur_bbox[2] - cur_bbox[0]))
        if direction < 0 and cur_speed > jump_limit:
            break
        # 경계 갇힘 감지 → 외삽 전환 (퇴장=정방향에서만; 등장 역추적은 외삽 금지)
        if direction > 0 and speed >= VID_EXIT_MIN_SPEED and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_BORDER_PX):
            proj = (rdx*vx + rdy*vy) / speed
            if proj < VID_EXIT_STALL_RATIO * speed:
                _exit_extrapolate(cur_boxes, cur_bbox, (vx, vy), fi, direction,
                                  limit_fi, total_frames, W, H,
                                  lambda f, b, bb: _rec(f, b))
                break
        # 원본 유사도 미달(miss) 프레임은 박스 기록 안 함 (장면전환 후 잔상 방지)
        if corr_ok:
            _rec(nfi, new_boxes)
        vx = VID_EXIT_VEL_EMA * vx + (1 - VID_EXIT_VEL_EMA) * rdx
        vy = VID_EXIT_VEL_EMA * vy + (1 - VID_EXIT_VEL_EMA) * rdy
        cur_boxes, cur_bbox = new_boxes, new_bbox
        prev, fi = cur, nfi


def _smooth_track(pts: list, ema: float) -> list:
    """상세보기 트랙(pts)의 bbox 를 프레임순으로 EMA 평활 → 박스 위치·크기 떨림 제거.
    다각형(quads)은 점 순서가 꼬일 수 있으므로 평활화하지 않고 원본 위치를 보존합니다."""
    if not pts:
        return pts
    sb = [float(v) for v in pts[0]['bbox']]
    for p in pts:
        if ema > 0:
            for i in range(4):
                sb[i] = ema * sb[i] + (1 - ema) * p['bbox'][i]
            p['bbox'] = [int(round(v)) for v in sb]
    return pts


def _expand_bbox(bbox, ratio: float):
    """bbox를 중심 기준 ratio 만큼 확장(가로/세로 각 ratio 비율). 화면 clamp 는 마스킹 단계에서."""
    x1, y1, x2, y2 = bbox
    dx = (x2 - x1) * ratio / 2.0
    dy = (y2 - y1) * ratio / 2.0
    return (x1 - dx, y1 - dy, x2 + dx, y2 + dy)


def _expand_boxes(boxes: list, ratio: float):
    """각 박스를 중심 기준 ratio 만큼 확장(타이트 텍스트박스 → 여유 있는 추적/마스킹 박스).
    vertices(회전 폴리곤)도 중심 기준 동일 비율 확대."""
    out = []
    for b in boxes:
        nb = dict(b)
        if 'x_min' in b:
            dx = int((b['x_max'] - b['x_min']) * ratio / 2.0)
            dy = int((b['y_max'] - b['y_min']) * ratio / 2.0)
            nb['x_min'] = b['x_min'] - dx; nb['y_min'] = b['y_min'] - dy
            nb['x_max'] = b['x_max'] + dx; nb['y_max'] = b['y_max'] + dy
        if b.get('vertices') and len(b['vertices']) >= 3:
            cx = sum(v['x'] for v in b['vertices']) / len(b['vertices'])
            cy = sum(v['y'] for v in b['vertices']) / len(b['vertices'])
            nb['vertices'] = [{'x': int(cx + (v['x'] - cx) * (1 + ratio)),
                               'y': int(cy + (v['y'] - cy) * (1 + ratio))} for v in b['vertices']]
        out.append(nb)
    return out


def _build_overlay_tracks(video_path: Path, pii_groups: list, fps: float, total_frames: int) -> dict:
    """각 PII 그룹의 keyframe을 앵커로 양방향 추적 → 프레임별 박스 위치를 TRACK_FPS로 다운샘플.
    반환: {pii_id: [{sec, frame, bbox:[x1,y1,x2,y2], quad:[[x,y]*4]}, ...]}  ← 프론트 오버레이용."""
    step = max(1, int(round(fps / max(1, TRACK_FPS))))
    # edge_max = int(fps * VID_EDGE_MAX_SEC)   # 마지막 keyframe '이후'(퇴장) 외삽 한계
    # enter_max = int(fps * VID_ENTER_MAX_SEC) # 첫 keyframe '이전'(등장 전) 역추적 한계 — 짧게(표류 방지)
    tracks = {}
    cap = cv2.VideoCapture(str(video_path))
    for g in pii_groups:
        kfs = g.get('keyframes', [])
        if not kfs:
            tracks[g['pii_id']] = []; continue
        # 병합 회전박스 면적이 최대인 keyframe을 대표로 선정 (일부만 잡힌 keyframe 제외)
        def _kf_quad_area(kf):
            _, q = _merge_boxes_to_quad(kf.get('boxes', []))
            return cv2.contourArea(np.array(q, np.float32)) if q else 0.0
        rep_kf = max(kfs, key=_kf_quad_area)
        rep_boxes = _expand_boxes(rep_kf['boxes'], VID_TRACK_EXPAND)
        rep_bbox  = _expand_bbox(tuple(rep_kf['bbox']), VID_TRACK_EXPAND)
        _, rq = _merge_boxes_to_quad(rep_boxes)
        if rq is None:
            tracks[g['pii_id']] = []; continue
        rrect = cv2.minAreaRect(np.array(rq, dtype=np.float32))
        rep_size, rep_ang = rrect[1], rrect[2]   # 표시 박스의 '크기·각도' 고정값(항상 일정한 박스)

        # 대표 박스를 단일 앵커로 전 구간 양방향 픽셀 추적 → 크기는 고정, 위치(중심)만 이동.
        frames = {}
        rf = int(rep_kf['frame'])
        frames[rf] = (rep_boxes, 0)
        _track_one_dir(cap, rf, rep_boxes, rep_bbox, +1, total_frames,
                       total_frames, frames, match_thresh=VID_EDGE_MATCH_THRESH,
                       anchor_bbox=rep_bbox)
        _track_one_dir(cap, rf, rep_boxes, rep_bbox, -1, -1,
                       total_frames, frames, match_thresh=VID_EDGE_MATCH_THRESH,
                       anchor_bbox=rep_bbox)

        pts = []
        for fi in sorted(frames):
            if (fi % step != 0) and (fi != rf):
                continue
            _, q = _merge_boxes_to_quad(frames[fi][0])
            if q is None:
                continue
            cen = cv2.minAreaRect(np.array(q, dtype=np.float32))[0]   # 추적된 위치(중심)
            quad = cv2.boxPoints((cen, rep_size, rep_ang))            # 크기·각도 고정 회전박스 1개
            axis = [int(quad[:, 0].min()), int(quad[:, 1].min()),
                    int(quad[:, 0].max()), int(quad[:, 1].max())]
            pts.append({'sec': round(fi / fps, 3), 'frame': int(fi), 'bbox': axis,
                        'quad': [[[float(x), float(y)] for x, y in quad]]})
        tracks[g['pii_id']] = _smooth_track(pts, TRACK_SMOOTH_EMA)   # 박스 떨림 평활(표시 전용)
    cap.release()
    return tracks


# ═════════════════════════════════════════════════════════════════════════════
# 영상 픽셀 템플릿 추적 (NCC matchTemplate + affine/shift) — report JSON keyframe이 앵커
# ═════════════════════════════════════════════════════════════════════════════
def _shrink_bbox(bbox, ratio: float):
    """_expand_bbox 의 역연산: 확장된 bbox 를 원래 타이트 크기로 복원(중심 유지, ÷(1+ratio))."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0; cy = (y1 + y2) / 2.0
    w = (x2 - x1) / (1.0 + ratio); h = (y2 - y1) / (1.0 + ratio)
    return (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _shrink_boxes(boxes: list, ratio: float):
    """_expand_boxes 의 역연산: 확장 박스를 타이트한 텍스트 범위로 복원(마스킹 정확도용).
    추적은 넓은 박스로 하되, 실제 지우기는 이 함수로 타이트하게 되돌려 주변 글자를 보존한다."""
    out = []
    f = 1.0 / (1.0 + ratio)
    for b in boxes:
        nb = dict(b)
        if 'x_min' in b:
            cx = (b['x_min'] + b['x_max']) / 2.0; cy = (b['y_min'] + b['y_max']) / 2.0
            w = (b['x_max'] - b['x_min']) * f; h = (b['y_max'] - b['y_min']) * f
            nb['x_min'] = int(round(cx - w / 2.0)); nb['x_max'] = int(round(cx + w / 2.0))
            nb['y_min'] = int(round(cy - h / 2.0)); nb['y_max'] = int(round(cy + h / 2.0))
        if b.get('vertices') and len(b['vertices']) >= 3:
            cx = sum(v['x'] for v in b['vertices']) / len(b['vertices'])
            cy = sum(v['y'] for v in b['vertices']) / len(b['vertices'])
            nb['vertices'] = [{'x': int(round(cx + (v['x'] - cx) * f)),
                               'y': int(round(cy + (v['y'] - cy) * f))} for v in b['vertices']]
        out.append(nb)
    return out


def _vid_add_mask(mask_map: dict, fi: int, pii_type: str, boxes, bbox: tuple):
    """마스킹 기록(모든 마스킹 경로가 여기를 통과). 추적은 확장 박스로 했지만, 실제 지우기는
    VID_TRACK_EXPAND 만큼 다시 축소해 '타이트한 텍스트 범위'만 저장 → 주변 글자·배경 보존(v16)."""
    tb = _shrink_boxes(boxes, VID_TRACK_EXPAND)
    tbb = _shrink_bbox(bbox, VID_TRACK_EXPAND)
    mask_map.setdefault(fi, []).append((pii_type, tb, tbb))


def _shift_boxes(boxes: list, dx: int, dy: int) -> list:
    """박스 전체를 (dx,dy) 평행이동(추적 fallback)."""
    out = []
    for b in boxes:
        nb = dict(b)
        nb['x_min'] = b['x_min'] + dx; nb['y_min'] = b['y_min'] + dy
        nb['x_max'] = b['x_max'] + dx; nb['y_max'] = b['y_max'] + dy
        if b.get('vertices'):
            nb['vertices'] = [{'x': v['x'] + dx, 'y': v['y'] + dy} for v in b['vertices']]
        out.append(nb)
    return out


def _transform_boxes_affine(boxes: list, M) -> list:
    """아핀 변환 M을 박스 꼭짓점에 적용 — 회전·크기·이동(기울어진 라벨 추적)."""
    out = []
    for b in boxes:
        nb = dict(b)
        if b.get('vertices') and len(b['vertices']) >= 3:
            pts = np.array([[v['x'], v['y']] for v in b['vertices']], dtype=np.float32).reshape(-1, 1, 2)
        elif 'x_min' in b:
            pts = np.array([[b['x_min'], b['y_min']], [b['x_max'], b['y_min']],
                            [b['x_max'], b['y_max']], [b['x_min'], b['y_max']]],
                           dtype=np.float32).reshape(-1, 1, 2)
        else:
            out.append(nb); continue
        pts_t = cv2.transform(pts, M).reshape(-1, 2)
        nb['vertices'] = [{'x': int(round(p[0])), 'y': int(round(p[1]))} for p in pts_t]
        nb['x_min'] = int(np.min(pts_t[:, 0])); nb['y_min'] = int(np.min(pts_t[:, 1]))
        nb['x_max'] = int(np.max(pts_t[:, 0])); nb['y_max'] = int(np.max(pts_t[:, 1]))
        out.append(nb)
    return out


def _apply_polygon_mask(mask, boxes: list, bbox: tuple, W: int, H: int, pad: int = 2):
    """박스 폴리곤을 마스크에 그리기(텍스트 범위만 정교 마스킹). vertices 없으면 bbox 직사각형."""
    drew = False
    if boxes:
        for b in boxes:
            if b.get('vertices') and len(b['vertices']) == 4:
                pts = np.array([[max(0, min(W-1, p['x'])), max(0, min(H-1, p['y']))]
                                for p in b['vertices']], dtype=np.int32)
                cv2.fillPoly(mask, [pts], 255); drew = True
            elif 'x_min' in b:
                cv2.rectangle(mask, (max(0, b['x_min']-pad), max(0, b['y_min']-pad)),
                              (min(W, b['x_max']+pad), min(H, b['y_max']+pad)), 255, -1)
                drew = True
    if not drew and bbox:
        bx1, by1, bx2, by2 = bbox
        cv2.rectangle(mask, (max(0, bx1-pad), max(0, by1-pad)),
                      (min(W, bx2+pad), min(H, by2+pad)), 255, -1)


def _vid_affine_sane(M) -> bool:
    """추정 변환이 1프레임 변화로 타당한지(스케일/회전 범위). 폭주 방지."""
    a, b = float(M[0, 0]), float(M[0, 1])
    scale = (a*a + b*b) ** 0.5
    angle = abs(math.degrees(math.atan2(b, a)))
    return VID_AFFINE_SCALE_MIN <= scale <= VID_AFFINE_SCALE_MAX and angle <= VID_AFFINE_ANGLE_MAX


def _vid_ncc_probe(prev_frame, cur_frame, sub_bbox: tuple, search_ratio: float):
    """sub_bbox 픽셀을 템플릿으로 cur_frame 근방에서 최유사 위치 탐색. 반환 (dx,dy,score) 또는 None."""
    x1, y1, x2, y2 = sub_bbox
    H, W = prev_frame.shape[:2]
    x1 = max(0, int(x1)); y1 = max(0, int(y1)); x2 = min(W, int(x2)); y2 = min(H, int(y2))
    w, h = x2 - x1, y2 - y1
    if w < 8 or h < 8:
        return None
    template = prev_frame[y1:y2, x1:x2]
    mx, my = int(w * search_ratio) + 8, int(h * search_ratio) + 8
    rx1, ry1 = max(0, x1 - mx), max(0, y1 - my)
    rx2, ry2 = min(W, x2 + mx), min(H, y2 + my)
    roi = cur_frame[ry1:ry2, rx1:rx2]
    if roi.shape[0] < h or roi.shape[1] < w:
        return None
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _mn, max_v, _ml, max_loc = cv2.minMaxLoc(res)
    return (rx1 + max_loc[0] - x1, ry1 + max_loc[1] - y1, float(max_v))


def _screen_vis_ratio(bbox, W: int, H: int) -> float:
    """bbox가 화면(0~W,0~H) 안에 보이는 면적 비율(0~1). 0이면 완전히 화면 밖."""
    x1, y1, x2, y2 = bbox
    a = (x2 - x1) * (y2 - y1)
    if a <= 0:
        return 0.0
    ix1, iy1 = max(0, x1), max(0, y1)
    ix2, iy2 = min(W, x2), min(H, y2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1) / a


def _split_blocks(bbox: tuple) -> list:
    """긴 텍스트 bbox를 긴 축 방향으로 N등분한 블록 bbox 리스트로 분할.
    예) 주민번호(가로로 긴) → 좌→우 여러 블록. 각 블록을 따로 픽셀 매칭하기 위함."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    w, h = x2 - x1, y2 - y1
    blocks = []
    if w >= h:                                   # 가로로 긴 텍스트 → 좌우로 분할
        n = max(2, min(VID_BLOCK_MAX_N, w // VID_BLOCK_MIN_PX))
        for k in range(n):
            bx1 = x1 + w * k // n; bx2 = x1 + w * (k + 1) // n
            blocks.append((bx1, y1, bx2, y2))
    else:                                        # 세로로 긴 텍스트 → 상하로 분할
        n = max(2, min(VID_BLOCK_MAX_N, h // VID_BLOCK_MIN_PX))
        for k in range(n):
            by1 = y1 + h * k // n; by2 = y1 + h * (k + 1) // n
            blocks.append((x1, by1, x2, by2))
    return blocks


def _vid_match_shift(prev_frame, cur_frame, bbox: tuple, search_ratio: float, thresh: float):
    """① 전체 매칭→이동 ② 구간별 N등분 블록 매칭→affine/평행이동 ③ 모두 미달→None(사라짐).
    ②에서 화면 밖으로 잘린 블록은 제외하고, 화면 안에 남은 블록들만으로 이동을 정밀 추정 →
    PII가 화면 가장자리로 빠져나가도 끝글자까지 흔들림 없이 추적한다(사용자 요청, v17)."""
    H, W = prev_frame.shape[:2]
    full = _vid_ncc_probe(prev_frame, cur_frame, bbox, search_ratio)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    # 구간별 N등분 블록 매칭: 화면 안(가시율 충분)에 남은 블록만 신뢰해 이동량 추정 → affine.
    affine_res, best = None, None
    if not ((x2 - x1) < 16 and (y2 - y1) < 16):
        pts_src, pts_dst = [], []
        for blk in _split_blocks(bbox):
            if _screen_vis_ratio(blk, W, H) < VID_BLOCK_VIS_RATIO:
                continue                          # 화면 밖으로 잘린 블록은 템플릿에서 제외
            p = _vid_ncc_probe(prev_frame, cur_frame, blk, search_ratio)
            if p is None or p[2] < thresh:
                continue                          # 매칭 실패(픽셀 사라짐) 블록 제외
            cx = (blk[0] + blk[2]) / 2.0; cy = (blk[1] + blk[3]) / 2.0
            pts_src.append((cx, cy)); pts_dst.append((cx + p[0], cy + p[1]))
            if best is None or p[2] > best[2]:
                best = p
        if len(pts_src) >= 2:                      # 2블록 이상 → 회전·스케일·이동(affine) 추정
            src = np.array(pts_src, dtype=np.float32); dst = np.array(pts_dst, dtype=np.float32)
            M, _inl = cv2.estimateAffinePartial2D(src, dst)
            if M is not None and _vid_affine_sane(M):
                affine_res = ('affine', M)
    # [회전·스케일 우선] affine 의 한 프레임 회전/크기변화가 유의미하면 전체 평행이동(shift)보다
    #   affine 을 우선 채택 → 카드가 회전·원근 변할 때 끝글자(예 '3456')가 박스 밖으로 나가 노출되는
    #   것을 막는다. 회전이 작으면 아래의 안정적인 전체 shift 를 쓴다.
    if affine_res is not None:
        M = affine_res[1]
        rot = abs(math.degrees(math.atan2(float(M[1, 0]), float(M[0, 0]))))
        scl = (float(M[0, 0]) ** 2 + float(M[1, 0]) ** 2) ** 0.5
        if rot >= VID_AFFINE_PREFER_ROT or abs(scl - 1.0) >= VID_AFFINE_PREFER_SCALE:
            return affine_res
    if full is not None and full[2] >= thresh:      # 회전 작음 → 전체 평행이동(안정)
        return ('shift', full[0], full[1])
    if affine_res is not None:                       # 전체 매칭 실패 → affine 으로라도 추종
        return affine_res
    if best is not None:                             # 1블록만 살아남음 → 그 블록 이동량으로 평행이동
        return ('shift', best[0], best[1])
    return None


# ── 화면 밖 퇴장 외삽 헬퍼 ───────────────────────────────────────────────────
def _bbox_screen_overlap(bbox, W: int, H: int) -> float:
    """bbox가 화면(0~W,0~H)과 겹치는 면적. 0이면 완전히 화면 밖(=소멸)."""
    x1, y1, x2, y2 = bbox
    ix1, iy1 = max(0, x1), max(0, y1)
    ix2, iy2 = min(W, x2), min(H, y2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


def _is_exiting(bbox, vel, W: int, H: int, border: int) -> bool:
    """박스가 경계에 닿아 있고(border 이내), 그 경계 '바깥 방향'으로 움직이는 중이면 True.
    즉 화면을 빠져나가려는 상태 — 이때 NCC가 갇히므로 속도 외삽으로 전환해야 한다."""
    x1, y1, x2, y2 = bbox
    vx, vy = vel
    return ((x1 <= border and vx < -0.3) or (x2 >= W - border and vx > 0.3)
            or (y1 <= border and vy < -0.3) or (y2 >= H - border and vy > 0.3))


def _exit_extrapolate(base_boxes, base_bbox, vel, fi, direction,
                      limit_fi, total_frames, W, H, record_fn) -> int:
    """경계 퇴장 감지 후, 마지막 이동속도 vel로 박스를 계속 외삽하며 record_fn(nfi,boxes,bbox) 기록.
    박스가 화면에서 완전히 벗어나면(겹침 0) 종료. 반환: 외삽으로 채운 프레임 수.
    base_boxes/base_bbox = 갇히기 직전(마지막 정상) 위치, fi = 그 프레임 번호."""
    vx, vy = vel
    if (vx * vx + vy * vy) ** 0.5 < VID_EXIT_MIN_SPEED:
        return 0                                  # 속도 미미 → 진짜 정지, 외삽 안 함
    ox = oy = 0.0          # 마지막 정상 위치 대비 누적 이동량(float 누적으로 반올림 오차 최소화)
    nfi, filled = fi, 0
    while True:
        nfi += direction
        if direction > 0 and nfi >= limit_fi: break
        if direction < 0 and nfi <= limit_fi: break
        if nfi < 0 or nfi >= total_frames: break
        ox += vx; oy += vy
        ebbox = (base_bbox[0] + ox, base_bbox[1] + oy,
                 base_bbox[2] + ox, base_bbox[3] + oy)
        if _bbox_screen_overlap(ebbox, W, H) <= 0.0:
            break                                 # 완전히 화면 밖 → 자연 소멸(종료)
        eboxes = _shift_boxes(base_boxes, int(round(ox)), int(round(oy)))
        record_fn(nfi, eboxes, ebbox)
        filled += 1
        if filled >= VID_EXIT_MAX_FILL:   # 무한 외삽 방지 — 화면 밖 완전 이탈까지는 따라가도록 한도 넉넉히
            break
    return filled


def _vid_track_run(cap, start_fi, start_boxes, start_bbox, direction, limit_fi,
                   total_frames, mask_map, pii_type, match_thresh=VID_MATCH_THRESH,
                   anchor_bbox=None) -> int:
    """한 keyframe에서 한 방향(+1/-1)으로 픽셀 추적하며 mask_map 채움. 매칭 실패 시 즉시 중단.
    match_thresh: NCC 매칭 임계(keyframe 사이=기본, 흐릿한 edge 구간=VID_EDGE_MATCH_THRESH)."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_fi)
    ret, prev = _rot_read(cap)
    if not ret:
        return 0
    H, W = prev.shape[:2]
    cur_boxes, cur_bbox, fi, filled = start_boxes, start_bbox, start_fi, 0
    vx, vy = 0.0, 0.0          # 누적 이동속도(EMA) — 경계 퇴장 시 외삽 방향/크기로 사용
    ref_patch = _ref_patch(prev, start_bbox)   # 원본 카드 외형(표류 검증 기준)
    miss_streak = 0                             # 원본 PII 와 상관도가 연속으로 낮았던 프레임 수(사라짐 연속 판정)
    # 퇴장 외삽 기준점 — 마지막으로 corr 검증을 통과한(드리프트 없는) '정상' 박스/위치/프레임을 기억.
    #  화면 밖으로 나갈 때 이 정상 박스를 고정한 채 속도로만 평행이동 → 추적이 망가지며 위로 밀리는(아래
    #  숫자 노출) 드리프트를 방지한다(detail_view 와 동일 정책).
    last_good_boxes, last_good_bbox, last_good_fi = start_boxes, start_bbox, start_fi

    # ── [속도개선] 역방향 프레임 공급기 (_track_one_dir 과 동일 정책) ──────────────
    #  역방향 per-frame seek(H.264 키프레임 재디코딩) 제거 → 블록 단위 1회 seek 후 순차
    #  디코딩하여 캐시에서 역순 pop. 동일 프레임 픽셀을 반환하므로 마스킹 추적 결과 불변.
    _rev_cache = {}
    _REV_BLOCK = 64

    def _read_cur(target_fi):
        if direction > 0:
            return _rot_read(cap)
        if target_fi not in _rev_cache:
            _rev_cache.clear()
            block_lo = max(0, target_fi - _REV_BLOCK + 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, block_lo)
            for f in range(block_lo, target_fi + 1):
                r, fr = _rot_read(cap)
                if not r:
                    break
                _rev_cache[f] = fr
        fr = _rev_cache.pop(target_fi, None)
        return (fr is not None), fr

    while True:
        nfi = fi + direction
        if direction > 0 and nfi >= limit_fi: break
        if direction < 0 and nfi <= limit_fi: break
        if nfi < 0 or nfi >= total_frames: break
        # 다음 프레임 획득(정방향=순차 read / 역방향=블록 prefetch 캐시) — 추적 결과 불변.
        ret, cur = _read_cur(nfi)
        if not ret: break
        # [개선] 전체화면 장면전환(컷) 감지 제거 — 배경 움직임/카드 흐림을 '컷'으로 오판해 카드가
        #   화면에 있는데도 마스킹 추적을 끊던 문제. 픽셀 NCC 매칭 성공=같은 픽셀 존재로 보고 지속.
        res = _vid_match_shift(prev, cur, cur_bbox, VID_SEARCH_RATIO, match_thresh)
        # 추적 실패: (퇴장=정방향) 화면 밖으로 나가는 중이면 마지막 속도로 끝까지 가린 뒤 종료.
        #   ※ 등장=역방향(direction<0)에서는 외삽 금지 — 픽셀 매칭이 끊긴 지점에서 즉시 멈춘다
        #     (등장 전 번호 없는 곳을 외삽으로 가려 원본을 훼손하는 것 방지).
        if res is None:
            # 추적 실패 지점이 '화면 밖 퇴장 중'이면, 드리프트된 cur_bbox 가 아니라 마지막 정상 위치
            #  (last_good)에서 속도로 외삽 → 위로 밀림 없이 아래 숫자까지 끝가지 덮는다.
            if direction > 0 and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_BORDER_PX):
                filled += _exit_extrapolate(
                    last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                    limit_fi, total_frames, W, H,
                    lambda f, b, bb: _vid_add_mask(mask_map, f, pii_type, b, bb))
            break
        # 새 위치 계산(affine 회전·크기 / shift 평행이동)
        if res[0] == 'affine':
            new_boxes = _transform_boxes_affine(cur_boxes, res[1])
            xs = [b['x_min'] for b in new_boxes] + [b['x_max'] for b in new_boxes]
            ys = [b['y_min'] for b in new_boxes] + [b['y_max'] for b in new_boxes]
            new_bbox = (min(xs), min(ys), max(xs), max(ys))
        else:
            _, dx, dy = res
            new_boxes = _shift_boxes(cur_boxes, dx, dy)
            new_bbox = (cur_bbox[0]+dx, cur_bbox[1]+dy, cur_bbox[2]+dx, cur_bbox[3]+dy)
        # [오매칭·표류 방지 — drift lock] (_track_one_dir 과 동일 정책)
        # 앵커 원점에서 허용 범위 이상 이탈하면 원점 근방 재탐색 → 실패 시 이전 위치 유지.
        if anchor_bbox is not None:
            anc_cx = (anchor_bbox[0] + anchor_bbox[2]) / 2.0
            anc_cy = (anchor_bbox[1] + anchor_bbox[3]) / 2.0
            max_drift = max(VID_DRIFT_MIN_PX,
                            VID_DRIFT_LOCK_RATIO * (anchor_bbox[3] - anchor_bbox[1]))
            new_cx = (new_bbox[0] + new_bbox[2]) / 2.0
            new_cy = (new_bbox[1] + new_bbox[3]) / 2.0
            if ((new_cx - anc_cx)**2 + (new_cy - anc_cy)**2)**0.5 > max_drift:
                retry = _vid_ncc_probe(prev, cur, anchor_bbox, VID_DRIFT_RETRY_RATIO)
                if retry is not None and retry[2] >= match_thresh:
                    rx, ry = int(round(retry[0])), int(round(retry[1]))
                    new_boxes = _shift_boxes(start_boxes, rx, ry)
                    new_bbox = (anchor_bbox[0]+rx, anchor_bbox[1]+ry,
                               anchor_bbox[2]+rx, anchor_bbox[3]+ry)
                else:
                    new_boxes, new_bbox = cur_boxes, cur_bbox   # 이전 위치 유지
        # [원본 카드 검증 — 연속 판정] 매 프레임 '최초 탐지 카드 vs 현재 위치' 상관도 측정.
        #  단일 프레임 미달은 순간 흐림으로 보고 견디고, VID_REF_CORR_STREAK 프레임 연속 미달 시에만
        #  마스킹 추적 중단 → 화면이 실제로 다른 장면으로 바뀐 경우에만 박스 제거(사용자 명세).
        corr_ok = _patch_corr(ref_patch, _ref_patch(cur, new_bbox)) >= VID_REF_CORR
        if not corr_ok:
            miss_streak += 1
            if miss_streak >= VID_REF_CORR_STREAK:
                # corr 미달로 추적이 끊기는 시점이 '화면 밖 퇴장 중'이면, 마지막 정상 박스(last_good)를
                #  속도로 외삽해 화면 끝까지 따라가며 가린다(신분증이 흐려지며 끊겨 아래 숫자가 노출되던 문제 해결).
                if direction > 0 and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_BORDER_PX):
                    filled += _exit_extrapolate(
                        last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                        limit_fi, total_frames, W, H,
                        lambda f, b, bb: _vid_add_mask(mask_map, f, pii_type, b, bb))
                break
        else:
            miss_streak = 0              # 다시 원본과 유사해지면 누적 초기화(흐렸다 또렷해지는 카드)
        # 이번 프레임의 실제 중심 이동량(rdx,rdy)
        rdx = ((new_bbox[0]+new_bbox[2]) - (cur_bbox[0]+cur_bbox[2])) / 2.0
        rdy = ((new_bbox[1]+new_bbox[3]) - (cur_bbox[1]+cur_bbox[3])) / 2.0
        speed = (vx*vx + vy*vy) ** 0.5
        
        # [역추적 표류 원천 차단 - 시간제한 의존 X]
        # 역방향(등장 전, direction < 0) 추적 시, PII 가 화면에서 완전히 사라졌는데도
        # 배경 무늬를 PII 로 착각해 엉뚱한 곳으로 박스가 순간이동(표류)하는 현상을 방지.
        # 한 프레임 이동이 'PII 박스 폭 비례' 한계를 넘으면 즉시 종료(절대 px 아님 → 모든 영상/PII 범용).
        cur_speed = (rdx*rdx + rdy*rdy) ** 0.5
        jump_limit = max(VID_JUMP_MIN_PX, VID_JUMP_RATIO * (cur_bbox[2] - cur_bbox[0]))
        if direction < 0 and cur_speed > jump_limit:
            break
            
        # 경계 갇힘 감지 → 외삽 전환 (퇴장=정방향에서만; 등장 역추적은 외삽 금지)
        if direction > 0 and speed >= VID_EXIT_MIN_SPEED and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_BORDER_PX):
            proj = (rdx*vx + rdy*vy) / speed     # 누적속도 방향으로의 실제 진행 성분
            if proj < VID_EXIT_STALL_RATIO * speed:
                # 갇힌 직전의 드리프트된 cur 대신, 마지막 정상 위치(last_good)에서 외삽 → 위로 밀림 방지.
                filled += _exit_extrapolate(
                    last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                    limit_fi, total_frames, W, H,
                    lambda f, b, bb: _vid_add_mask(mask_map, f, pii_type, b, bb))
                break
        # 정상 진행: 마스킹 기록 + 속도(EMA) 갱신
        _vid_add_mask(mask_map, nfi, pii_type, new_boxes, new_bbox)
        filled += 1
        # corr 검증을 통과한 프레임만 퇴장 외삽의 기준점(last_good)으로 갱신 → 드리프트된 위치가
        #  기준점이 되는 것을 막아, 퇴장 시 항상 '마지막 정상 위치'에서 외삽되도록 한다.
        if corr_ok:
            last_good_boxes, last_good_bbox, last_good_fi = new_boxes, new_bbox, nfi
        vx = VID_EXIT_VEL_EMA * vx + (1 - VID_EXIT_VEL_EMA) * rdx
        vy = VID_EXIT_VEL_EMA * vy + (1 - VID_EXIT_VEL_EMA) * rdy
        cur_boxes, cur_bbox = new_boxes, new_bbox
        prev, fi = cur, nfi
    return filled


def _vid_track_template(video_path: Path, pii_events: list, fps: float, total_frames: int, progress_cb=None) -> dict:
    """OCR 확정 keyframe(report JSON)을 앵커로 앞/뒤 픽셀 추적하며 마스킹.
    ※ pii_id 단위로 추적 → 같은 type 의 서로 다른 PII(예: 카드 2개)를 섞지 않고 각자 추적.
    반환: {frame_idx: [(pii_id, boxes, bbox), ...]}"""
    from collections import defaultdict
    # edge_max = int(fps * VID_EDGE_MAX_SEC)   # 첫/마지막 keyframe 바깥(흐릿한 등장/퇴장) 추적 한계
    mask_map = {}
    pii_by_id = defaultdict(list)
    for fi, pii_id, mb, bbox in pii_events:
        # 추적/마스킹 박스를 타이트한 텍스트박스보다 넓게 확장(빠른 움직임 추적 + 노출 방지)
        pii_by_id[pii_id].append((fi, _expand_boxes(mb, VID_TRACK_EXPAND),
                                  _expand_bbox(tuple(bbox), VID_TRACK_EXPAND)))
    cap = cv2.VideoCapture(str(video_path))
    for pii_id, evs in pii_by_id.items():
        evs = sorted({e[0]: e for e in evs}.values(), key=lambda x: x[0])
        if not evs: continue

        # [다중 '완전' 앵커 — 미탐지 부위 포함 + 누적오차 차단(깜빡임 방지)] 각 keyframe 의 단어
        #   병합면적을 재서, '카드번호 전체가 충분히 잡힌' keyframe(그룹 최대의 VID_FULL_ANCHOR_RATIO
        #   이상)만 앵커로 쓴다. 일부 단어만 잡힌 keyframe(frame 394='1234' 누락)은 제외 → 미탐지
        #   노출 방지. 여러 완전 keyframe 을 '각자 실측 위치·각도'로 앵커 삼아 인접 구간만 추적하므로,
        #   단일 앵커 대비 누적 오차가 작아 카드 미세 움직임을 정확히 따라가며 지운다(삐짐/깜빡임 방지).
        def _ev_area(e):
            _, q = _merge_boxes_to_quad(e[1])
            return cv2.contourArea(np.array(q, dtype=np.float32)) if q else 0.0
        areas = [(_ev_area(e), e) for e in evs]
        amax = max((a for a, _ in areas), default=0.0) or 1.0
        full = [e for a, e in areas if a >= VID_FULL_ANCHOR_RATIO * amax]
        if not full:
            full = [max(evs, key=_ev_area)]
        n = len(full)
        for i, (fi, mb, bbox) in enumerate(full):
            if progress_cb:
                progress_cb(i, n)
            rmb = _drop_container_boxes(mb)   # 컨테이너(전체 묶음) 제외 → 단어별 타이트 마스킹
            _vid_add_mask(mask_map, fi, pii_id, rmb, bbox)
            # keyframe '사이'는 기본 임계로 추적, 첫 이전/마지막 이후(흐릿한 등장·퇴장)는 edge 임계로.
            nxt = full[i + 1][0] if i + 1 < n else total_frames
            prv = full[i - 1][0] if i - 1 >= 0 else -1
            thr_f = VID_MATCH_THRESH if i + 1 < n else VID_EDGE_MATCH_THRESH
            thr_b = VID_MATCH_THRESH if i - 1 >= 0 else VID_EDGE_MATCH_THRESH
            _vid_track_run(cap, fi, rmb, bbox, +1, nxt, total_frames, mask_map, pii_id, match_thresh=thr_f, anchor_bbox=bbox)
            _vid_track_run(cap, fi, rmb, bbox, -1, prv, total_frames, mask_map, pii_id, match_thresh=thr_b, anchor_bbox=bbox)
        print(f"    🎯 [{pii_id}] 완전 keyframe {n}개 다중 앵커 양방향 픽셀 추적 마스킹 완료")
    if progress_cb:
        progress_cb(1, 1)
    cap.release()
    return mask_map


def _events_from_groups(report_json, selected_ids=None):
    """report JSON(영상)의 선택 그룹 keyframes → 추적용 pii_events [(fi,pii_id,boxes,bbox),...].
    ※ pii_id 를 키로 사용 → 같은 type 의 다른 PII(카드 2개 등)를 분리 추적."""
    events = []
    for g in report_json.get('pii_groups', []):
        if selected_ids is not None and g.get('pii_id') not in selected_ids:
            continue
        pid = g.get('pii_id', '')
        for kf in g.get('keyframes', []):
            events.append((int(kf['frame']), pid, kf.get('boxes', []), tuple(kf.get('bbox', (0, 0, 0, 0)))))
    return sorted(events, key=lambda e: e[0])


# ═════════════════════════════════════════════════════════════════════════════
# 워터마크 (가시 + 비가시 + 미리보기 검토용)
# ═════════════════════════════════════════════════════════════════════════════
def _payload_seed(payload: str) -> int:
    return int(hashlib.sha256(payload.encode('utf-8')).hexdigest(), 16) % (2**32)


def make_invisible_pattern(payload: str, h: int, w: int) -> np.ndarray:
    """payload 시드로 ±가우시안 패턴 생성(영상은 1회 만들어 전 프레임 재사용)."""
    rng = np.random.default_rng(_payload_seed(payload))
    return rng.standard_normal((h, w)).astype(np.float32)


def embed_invisible_watermark(image_cv: np.ndarray, pattern: np.ndarray = None,
                              payload: str = WATERMARK_PAYLOAD,
                              strength: float = WM_INVISIBLE_STRENGTH) -> np.ndarray:
    """[비가시] 휘도(Y)에 payload 패턴 미세 가산(스프레드 스펙트럼). 육안 불가, 상관검출로 출처 추적."""
    h, w = image_cv.shape[:2]
    if pattern is None:
        pattern = make_invisible_pattern(payload, h, w)
    ycrcb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    ycrcb[:, :, 0] = np.clip(ycrcb[:, :, 0] + strength * pattern, 0, 255)
    return cv2.cvtColor(ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)


def verify_invisible_watermark(image_cv: np.ndarray, payload: str = WATERMARK_PAYLOAD) -> float:
    """삽입 payload 패턴과 휘도의 정규화 상관(↑면 해당 payload로 워터마킹된 파일). 분쟁 검증용."""
    h, w = image_cv.shape[:2]
    pattern = make_invisible_pattern(payload, h, w)
    y = cv2.cvtColor(image_cv, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    y -= y.mean(); p = pattern - pattern.mean()
    denom = (np.linalg.norm(y) * np.linalg.norm(p)) or 1.0
    return float(np.sum(y * p) / denom)


def add_visible_watermark(image_cv: np.ndarray, text: str = WATERMARK_TEXT) -> np.ndarray:
    """[가시] 우하단 작은 반투명 마크(본 처리물용)."""
    from PIL import Image as PILImage, ImageDraw
    base = PILImage.fromarray(cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = PILImage.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = base.size
    font = _load_kor_font(max(14, W // 45))
    try:
        bb = font.getbbox(text); tw, th = bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        tw, th = 60, 16
    x, y = W - tw - 12, H - th - 10
    draw.text((x + 1, y + 1), text, fill=(0, 0, 0, 110), font=font)
    draw.text((x, y), text, fill=(255, 255, 255, 160), font=font)
    return cv2.cvtColor(np.array(PILImage.alpha_composite(base, overlay).convert("RGB")),
                        cv2.COLOR_RGB2BGR)


def add_preview_watermark(image_cv: np.ndarray) -> np.ndarray:
    """[검토용 큰 워터마크] 미리보기 전용 — 대각선 반복 'Garim'으로 무단 사용 방지."""
    from PIL import Image as PILImage, ImageDraw
    base = PILImage.fromarray(cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = PILImage.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = base.size
    font = _load_kor_font(max(30, W // 12))
    step = max(100, W // 6)
    for yy in range(0, H + step, step):
        for xx in range(-step, W, step):
            draw.text((xx, yy), "Garim", fill=(255, 255, 255, 90), font=font)
    return cv2.cvtColor(np.array(PILImage.alpha_composite(base, overlay).convert("RGB")),
                        cv2.COLOR_RGB2BGR)


def apply_watermarks(image_cv: np.ndarray, inv_pattern: np.ndarray = None,
                     preview: bool = False) -> np.ndarray:
    """본 처리물(preview=False): 우하단 작은 가시 + 비가시.
    미리보기(preview=True): 검토용 큰 워터마크 + 비가시."""
    out = image_cv
    if WATERMARK_INVISIBLE:
        out = embed_invisible_watermark(out, inv_pattern)
    if preview:
        out = add_preview_watermark(out)
    elif WATERMARK_VISIBLE:
        out = add_visible_watermark(out)
    return out


# ═════════════════════════════════════════════════════════════════════════════
# 공통 유틸 — report JSON 로드 + 원본 경로 해석
# ═════════════════════════════════════════════════════════════════════════════
def _load_report(report_json_path):
    """{stem}_result.json 로드(report 단계 산출물 — 모든 정보 포함)."""
    with open(Path(report_json_path), encoding='utf-8') as f:
        return json.load(f)


def _resolve_source(report_json, report_json_path, input_path):
    """원본 파일 경로 결정: 인자 우선 → 없으면 index.json + 입력폴더에서 자동 탐색."""
    src_type = report_json.get('source_type')
    src_name = report_json.get('source_name') \
        or report_json.get('source_stem') \
        or Path(report_json_path).stem.replace('_result', '').replace('_index', '')
    if input_path:
        return src_type, src_name, Path(input_path)
    if src_type == 'image':
        return src_type, src_name, (INPUT_IMAGE_DIR / src_name)
    cand = next((INPUT_VIDEO_DIR / f"{src_name}{e}" for e in VIDEO_EXTS
                 if (INPUT_VIDEO_DIR / f"{src_name}{e}").exists()), None)
    if cand is None:
        # source_name이 확장자 포함인 경우 직접 탐색
        stem = Path(src_name).stem
        cand = next((INPUT_VIDEO_DIR / f"{stem}{e}" for e in VIDEO_EXTS
                     if (INPUT_VIDEO_DIR / f"{stem}{e}").exists()), None)
    return src_type, src_name, cand


def _video_mask_to_temp(video_path, mask_map, fps, total, W, H, out_dir, tag,
                        frame_lo=0, frame_hi=None, watermark_preview=False,
                        progress_cb=None):
    """mask_map대로 [frame_lo, frame_hi] 구간을 마스킹+워터마크하여 무음 임시 mp4 작성. 경로 반환."""
    frame_hi = total - 1 if frame_hi is None else min(frame_hi, total - 1)
    inv_pattern = make_invisible_pattern(WATERMARK_PAYLOAD, H, W) if WATERMARK_INVISIBLE else None
    temp_path = out_dir / f"_temp_{tag}.mp4"

    # Colab GPU(NVENC) 사용 가능 여부 확인 → 가능하면 h264_nvenc, 아니면 libx264(CPU)
    _nvenc_ok = USE_GPU and _check_nvenc()
    _vcodec   = 'h264_nvenc' if _nvenc_ok else 'libx264'
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24',
        '-s', f'{W}x{H}', '-r', str(fps),
        '-i', 'pipe:0',
        '-c:v', _vcodec,
        '-preset', 'fast' if _nvenc_ok else FFMPEG_PRESET,
        '-crf',  str(FFMPEG_CRF),
        '-an',  # 무음 (오디오는 별도 단계에서 합침)
        str(temp_path)
    ]

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_lo)
    masked_cnt = 0
    proc = None
    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        frames_to_process = frame_hi - frame_lo + 1
        for i, fi in enumerate(range(frame_lo, frame_hi + 1)):
            if progress_cb and i % 5 == 0:
                progress_cb(i, frames_to_process)
            ret, frame = _rot_read(cap)
            if not ret: break
            if fi in mask_map:
                combined = np.zeros((H, W), dtype=np.uint8)
                for _pt, boxes, bbox in mask_map[fi]:
                    _apply_polygon_mask(combined, boxes, bbox, W, H, pad=VID_MASK_PAD_PX)
                if cv2.countNonZero(combined) > 0:
                    frame = inpaint_adaptive(frame, combined)
                    masked_cnt += 1
            frame = apply_watermarks(frame, inv_pattern, preview=watermark_preview)
            proc.stdin.write(frame.tobytes())  # GPU 파이프로 프레임 전달
        if progress_cb:
            progress_cb(frames_to_process, frames_to_process)
    finally:
        if proc:
            proc.stdin.close()
            proc.wait()
        cap.release()
    return temp_path, masked_cnt


# ── 오디오 비프음(삐) 합성 상수 ──
# (이 상수들이 없으면 _generate_beeped_audio 가 NameError 로 죽어 비프음이 안 났음)
BEEP_FREQ    = 1000.0   # 비프음 주파수(Hz) — 1kHz (garim_pipeline.py STT 원본과 동일)
BEEP_GAIN_DB = -8.0     # 비프음 음량 보정(dB) — garim_pipeline.py STT 원본값(-8)과 동일


def _generate_beeped_audio(video_path, report_json, selected_ids, output_dir, stem):
    """영상에서 오디오를 추출하고, audio_pii_groups 에 따라 비프음을 합성한 임시 wav 파일을 반환한다."""
    audio_groups = report_json.get('audio_pii_groups', [])
    if not audio_groups:
        return None
    
    to_beep = []
    for g in audio_groups:
        if selected_ids is not None and g.get('pii_id') not in selected_ids:
            continue
        if g.get('is_selected', False) or selected_ids is not None:
            to_beep.append(g)
            
    if not to_beep:
        return None

    import subprocess
    from pydub import AudioSegment
    from pydub.generators import Sine

    audio_hq_path = output_dir / f"_temp_{stem}_hq.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
         str(audio_hq_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None

    print(f"  🎙 오디오 추출 완료, {len(to_beep)}건 비프음 합성 중..")
    audio = AudioSegment.from_wav(str(audio_hq_path))
    
    for seg in to_beep:
        start_ms = int(seg.get("start_time_sec", 0) * 1000)
        end_ms = int(seg.get("end_time_sec", 0) * 1000)
        duration_ms = max(0, end_ms - start_ms)
        if duration_ms <= 0: continue
        beep = Sine(BEEP_FREQ).to_audio_segment(duration=duration_ms).apply_gain(BEEP_GAIN_DB)
        beep = beep.set_frame_rate(audio.frame_rate).set_channels(audio.channels).set_sample_width(audio.sample_width)
        audio = audio[:start_ms] + beep + audio[end_ms:]

    beeped_path = output_dir / f"_temp_{stem}_beeped.wav"
    audio.export(str(beeped_path), format="wav")
    
    if audio_hq_path.exists():
        audio_hq_path.unlink()
        
    return beeped_path

def _mux_audio(temp_path, video_path, final_path, audio_offset_sec=None, audio_path=None):
    """temp(무음 영상) + 오디오 → final. audio_offset_sec 지정 시 그 지점부터 오디오 사용(샘플용).
    audio_path 지정 시 그 파일을 오디오 소스로 사용(비프음 합성 wav). 미지정 시 원본 영상 오디오."""
    # 오디오 소스 선택: 비프 wav 가 있으면 그것, 없으면 원본 영상에서 추출
    audio_src = str(audio_path) if audio_path else str(video_path)
    cmd = ['ffmpeg', '-y', '-i', str(temp_path)]
    if audio_offset_sec is not None:
        cmd += ['-ss', str(round(audio_offset_sec, 3))]
    cmd += ['-i', audio_src, '-map', '0:v:0', '-map', '1:a:0?',
            '-c:v', 'libx264', '-preset', FFMPEG_PRESET, '-crf', str(FFMPEG_CRF),
            '-c:a', 'aac', '-b:a', '192k',
            '-map_metadata', '-1',   # 원본 GPS·카메라·날짜 등 모든 메타데이터 명시적 제거
            '-shortest', str(final_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"  ⚠️  FFmpeg 오류(무음으로 대체):\n{r.stderr[-300:]}")
            import shutil; shutil.copy(str(temp_path), str(final_path))
    except FileNotFoundError:
        print("  ⚠️  FFmpeg 없음 → apt-get install -y ffmpeg 후 재시도")
        import shutil; shutil.copy(str(temp_path), str(final_path))
    if Path(temp_path).exists():
        Path(temp_path).unlink()


# ═════════════════════════════════════════════════════════════════════════════
# 선택(is_selected)·마스킹좌표(masked_coords) 헬퍼 — index.json 연동
# ═════════════════════════════════════════════════════════════════════════════
def _selected_ids_from_index(rep: dict) -> list:
    """index.json 의 선택된 PII pii_id 목록(시각 pii_groups + 음성 audio_pii_groups).
    (수정사항3: 사용자 선택은 별도 파일 없이 index 의 is_selected 로 관리)
    ※ 음성(audio_pii_groups)도 포함해야 마스킹 단계에서 비프음 합성이 동작한다.
      (이게 빠져 있어 음성 PII 가 선택돼도 비프음이 안 만들어지던 문제 수정)"""
    vis = [g['pii_id'] for g in rep.get('pii_groups', []) if g.get('is_selected')]
    aud = [g.get('pii_id', 'audio_pii') for g in rep.get('audio_pii_groups', []) if g.get('is_selected')]
    return vis + aud


def _write_masked_coords(index_json_path, rep: dict, coords_map: dict):
    """마스킹 후 실제 적용된 좌표를 index.json 의 pii_groups[].masked_coords 에 기록(덮어쓰기).
    coords_map: {pii_id: 좌표}  (이미지=박스리스트 / 영상={frame: 박스리스트})"""
    for g in rep.get('pii_groups', []):
        if g.get('pii_id') in coords_map:
            g['masked_coords'] = coords_map[g['pii_id']]
    with open(str(index_json_path), 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"  📝 masked_coords {len(coords_map)}건 → {Path(index_json_path).name} 갱신")


def _quad_label_angle(q):
    """quad(4점)의 '긴 변' 방향 각도(도). 라벨을 박스와 평행하게 쓰기 위함.
    가독성 위해 -45~45 로 정규화 → 박스가 많이 기울어도 글자가 거꾸로/세로로 안 뒤집힌다."""
    e01 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
    e12 = (q[2][0] - q[1][0], q[2][1] - q[1][1])
    e = e01 if (e01[0] ** 2 + e01[1] ** 2) >= (e12[0] ** 2 + e12[1] ** 2) else e12
    a = float(np.degrees(np.arctan2(e[1], e[0])))
    while a > 45:  a -= 90
    while a < -45: a += 90
    return a


def _put_rotated_label(frame, text, quad, color, font_scale=0.6, thick=2):
    """박스(quad) 각도에 맞춰 회전한 라벨을, 박스 '밖'(위 우선·짤리면 아래)에 배치해 합성한다.
    화면 경계를 벗어나지 않게 클램프 → 박스 안 내용과 안 겹치고 잘리지 않게 표시."""
    H, W = frame.shape[:2]
    angle = _quad_label_angle(quad)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), bl = cv2.getTextSize(text, font, font_scale, thick)
    pad = 4
    cw, ch = tw + pad * 2, th + bl + pad * 2
    # 라벨 캔버스: 검은 외곽(가독) + 색 글자
    canvas = np.zeros((ch, cw, 3), np.uint8)
    cv2.putText(canvas, text, (pad, th + pad), font, font_scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(canvas, text, (pad, th + pad), font, font_scale, color, thick, cv2.LINE_AA)
    # 박스 각도로 회전(확장 캔버스)
    M = cv2.getRotationMatrix2D((cw / 2.0, ch / 2.0), -angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw, nh = int(ch * sin + cw * cos), int(ch * cos + cw * sin)
    M[0, 2] += (nw - cw) / 2.0; M[1, 2] += (nh - ch) / 2.0
    rot = cv2.warpAffine(canvas, M, (nw, nh))
    # 위치: 기본은 '박스 좌상단 바로 위'(좌측 정렬). 위가 잘리면 박스 바로 아래로,
    #   우측이 잘리면 우측 정렬로 당겨 → 박스 안 내용을 안 가리고 화면에서 안 잘리게.
    xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
    left, top, right, bot = min(xs), min(ys), max(xs), max(ys)
    gap = 4
    ax = int(left); ay = int(top - gap - nh)
    if ay < 0:
        ay = int(bot + gap)                       # 위 공간 부족 → 박스 바로 아래
    if ax + nw > W:
        ax = int(right - nw)                      # 우측 잘림 → 우측 정렬로 당김
    ax = max(0, min(W - nw, ax)); ay = max(0, min(H - nh, ay))
    if nw <= 0 or nh <= 0 or ay + nh > H or ax + nw > W:
        return
    roi = frame[ay:ay + nh, ax:ax + nw]
    mask = rot.sum(2) > 0                          # 글자 픽셀만 합성(배경 투명)
    roi[mask] = rot[mask]


def _draw_box_on_frame(frame, pt: dict, g: dict):
    """영상 프레임 위에 PII 박스(quad/bbox) + 영문 라벨 그리기. (cv2는 한글 불가 → 영문 라벨)
    라벨은 박스 각도에 맞춰 회전 + 박스 밖(위/아래 자동)에 배치 → 박스 안 내용과 겹치지 않게."""
    color = _PII_COLORS.get(g['pii_type'], _PII_DEFAULT_COLOR)
    quads, bbox = pt.get('quad'), pt.get('bbox')
    label = _PII_ENG_LABELS.get(g['pii_type'], 'PII') + str(g.get('seq', ''))
    if quads:
        for q in quads:
            cv2.polylines(frame, [np.array(q, np.int32)], True, color, 2)
        _put_rotated_label(frame, label, quads[0], color)
    elif bbox:
        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
        q = [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]
        _put_rotated_label(frame, label, q, color)
    else:
        return


def _render_overlay_video(video_path, pii_groups, tracks, fps, total, W, H, out_path):
    """[상세보기 영상] 원본 위에 PII 박스가 텍스트 따라 이동하는 오버레이 영상(mp4) 생성.
    tracks(TRACK_FPS 다운샘플)를 프레임별로 hold 하여 그린 뒤 원본 오디오를 합성.
    (수정사항6: 영상은 재생 중 픽셀 따라다니며 개인정보 범위 표시)"""
    step = max(1, int(round(fps / max(1, TRACK_FPS))))
    group_pts = {g['pii_id']: sorted(tracks.get(g['pii_id'], []), key=lambda p: p['frame'])
                 for g in pii_groups}
    ptr = {gid: 0 for gid in group_pts}
    last = {gid: None for gid in group_pts}      # 직전 표시 박스(hold)

    temp = Path(out_path).with_name(f"_temp_overlay_{Path(out_path).stem}.mp4")
    # GPU(NVENC) 인코더 사용 가능 시 FFmpeg 파이프, 아니면 libx264(CPU)
    _nvenc_ok = USE_GPU and _check_nvenc()
    _vcodec   = 'h264_nvenc' if _nvenc_ok else 'libx264'
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24',
        '-s', f'{W}x{H}', '-r', str(fps),
        '-i', 'pipe:0',
        '-c:v', _vcodec,
        '-preset', 'fast',
        '-crf', str(FFMPEG_CRF),
        '-an', str(temp)
    ]
    cap = cv2.VideoCapture(str(video_path))
    proc = None
    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for fi in range(total):
            ret, frame = _rot_read(cap)
            if not ret:
                break
            for g in pii_groups:
                gid, pts = g['pii_id'], group_pts[g['pii_id']]
                while ptr[gid] < len(pts) and pts[ptr[gid]]['frame'] <= fi:
                    last[gid] = pts[ptr[gid]]; ptr[gid] += 1
                cur = last[gid]
                if cur is None:
                    continue
                # [잔상 박스 제거] track 은 TRACK_FPS 로 균일 샘플되어 정상 추적 구간의 점 간격은 step.
                #  '다음 추적점'이 곧 이어지면(연속 추적, 단발 블러 1점 누락까지 허용) 그 점에 도달할 때까지
                #  박스를 유지(점 사이 자연 보간). 다음 점이 없거나 한참 뒤면(장면전환·소멸로 추적이 끊긴
                #  구간) 마지막 점 직후 즉시 박스를 제거한다 — 개인정보가 실제로 사라지면 표시 박스도 바로
                #  사라져야 하며(사용자 요구), step·간격 비례 판정이라 모든 영상/PII 에 동일 적용된다.
                nxt = pts[ptr[gid]] if ptr[gid] < len(pts) else None
                if nxt is not None and (nxt['frame'] - cur['frame']) <= 2 * step + 1:
                    visible = True                            # 다음 점이 곧 옴 → 유지(while 루프가 점 교체)
                else:
                    visible = abs(fi - cur['frame']) <= 2     # 추적 종료(소멸) → 마지막 점 직후 즉시 제거
                if visible:
                    _draw_box_on_frame(frame, cur, g)
            proc.stdin.write(frame.tobytes())
    finally:
        if proc:
            proc.stdin.close()
            proc.wait()
        cap.release()
    _mux_audio(temp, video_path, out_path)        # 원본 오디오 유지
    return out_path


# ═════════════════════════════════════════════════════════════════════════════
# 3단계 — 상세보기 (run_detail_view)
# ═════════════════════════════════════════════════════════════════════════════
def run_detail_view(index_json_path, input_path=None):
    """
    [3단계] '상세보기' — 원본 위에 모든 PII 탐지 구역을 박스로 표시.
    - 이미지: output_file/{stem}_상세보기.jpg (원본 + PII 박스 오버레이)
    - 영상  : output_file/{stem}_상세보기.mp4 (박스가 텍스트 따라 이동) + 오버레이 트랙 반환
    입력: report 단계가 만든 {stem}_result.json (모든 정보가 여기에 있음)
    반환: {'source_type','pii_groups','overlay_image'/'overlay_video','overlay_tracks'(영상)}
    ※ 테스트 단계: 멈춤 없이 결과 파일 생성(상세보기 UI·선택은 추후 백엔드 연동).
    """
    rep = _load_report(index_json_path)
    src_type, src_name, src_path = _resolve_source(rep, index_json_path, input_path)
    pii_groups = rep.get('pii_groups', [])
    stem = rep.get('source_stem') or Path(src_name).stem
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not pii_groups:
        print("  ℹ️  PII 없음 — 상세보기 생략")
        return {'source_type': src_type, 'pii_groups': []}

    print(f"\n{'='*60}\n📋 상세보기 생성: {src_name}\n{'='*60}")
    result = {'source_type': src_type, 'pii_groups': pii_groups}

    if src_type == 'image':
        if src_path is None or not Path(src_path).exists():
            print(f"  ⚠️  원본 이미지 없음: {src_name}"); return result
        image = cv2.imdecode(np.fromfile(str(src_path), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            print(f"  ⚠️  이미지 읽기 실패: {src_path}"); return result
        overlay_img = draw_pii_report(image, pii_groups)        # PII 박스+라벨 오버레이
        save_path = OUTPUT_DIR / f"{stem}_상세보기.jpg"
        ok, enc = cv2.imencode('.jpg', overlay_img)
        if ok:
            enc.tofile(str(save_path))
        result['overlay_image'] = str(save_path)
        print(f"  📊 상세보기 이미지 → {save_path.name}  (PII {len(pii_groups)}건)")

    elif src_type == 'video':
        if src_path is None or not Path(src_path).exists():
            print(f"  ⚠️  원본 영상 없음: {src_name}"); return result
        cap = cv2.VideoCapture(str(src_path))
        fps   = cap.get(cv2.CAP_PROP_FPS) or rep.get('fps', 30.0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or rep.get('total_frames', 0)
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # [회전 보정] OCR(index) 기준 해상도와 90도 어긋나면 전역 회전코드 설정 + 출력 W,H 스왑.
        if _set_frame_rot(cap, rep.get('image_width'), rep.get('image_height')) is not None:
            W, H = H, W
        cap.release()

        # 1) 오버레이 트랙(프레임별 박스 좌표) 생성 — 픽셀 추적
        print(f"  🎯 오버레이 트랙 생성 (TRACK_FPS={TRACK_FPS})...")
        overlay_tracks = _build_overlay_tracks(src_path, pii_groups, fps, total)
        # 2) 트랙으로 박스가 따라 움직이는 상세보기 영상 렌더링
        print(f"  🎬 상세보기 오버레이 영상 생성...")
        save_path = OUTPUT_DIR / f"{stem}_상세보기.mp4"
        _render_overlay_video(src_path, pii_groups, overlay_tracks, fps, total, W, H, save_path)
        result['overlay_tracks'] = overlay_tracks
        result['overlay_video'] = str(save_path)
        print(f"  ✅ 상세보기 영상 저장 완료 → {save_path}  (PII {len(pii_groups)}건)")

    print(f"\n{'='*60}\n[3단계 완료] (테스트: 멈춤 없이 다음 단계 진행)\n{'='*60}")
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 4단계 — 사용자 선택 (별도 파일 없음 / index.json 의 is_selected 사용)
#   (수정사항3) 사용자가 고른 PII 는 백엔드가 index.json 의 pii_groups[].is_selected 를
#   True 로 갱신한다 → mask 단계는 _selected_ids_from_index() 로 읽어 사용.
#   ※ 기존 save_user_selection()/user_index.json 은 폐지(삭제).
# ═════════════════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════════════════
# 5단계 — 미리보기 (샘플 마스킹)
# ═════════════════════════════════════════════════════════════════════════════
def preview_image(img_path, report_json, selected_ids=None, output_dir=None, multi=False):
    """[이미지] 선택 PII 마스킹 검토용 미리보기.
    반환: {'original', 'preview'}  → 프론트가 Before/After 슬라이더로 비교."""
    output_dir = Path(output_dir or OUTPUT_DIR); output_dir.mkdir(parents=True, exist_ok=True)
    img_path = Path(img_path)
    image = cv2.imdecode(np.fromfile(str(img_path), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        print(f"  ⚠️  미리보기: 이미지 읽기 실패 {img_path}"); return None
    masked = mask_selected_on_image(image, report_json.get('pii_groups', []), selected_ids)
    preview = apply_watermarks(masked, preview=True)        # 검토용 큰 워터마크(+비가시)
    pp = output_dir / f"미리보기_{img_path.stem}.jpg"
    ok, enc = cv2.imencode('.jpg', preview)
    if ok: enc.tofile(str(pp))
    print(f"  👁  이미지 미리보기 → {pp.name} (선택: {selected_ids or '전체'})")
    return {'original': str(img_path), 'preview': str(pp)}


def preview_video(video_path, report_json, selected_ids=None, output_dir=None, progress_cb=None):
    """[영상] 개인정보 탐지 지점 [이전 3초 ~ 이후 3초] 샘플 1개만 마스킹한 미리보기 클립.
    반환: {'original', 'preview_clip', 'start_sec', 'end_sec'} → 프론트가 해당 구간 슬라이더 비교."""
    output_dir = Path(output_dir or OUTPUT_DIR); output_dir.mkdir(parents=True, exist_ok=True)
    video_path = Path(video_path)
    events = _events_from_groups(report_json, selected_ids)
    if not events:
        print("  ℹ️  미리보기: 선택된 PII 없음"); return None

    cap = cv2.VideoCapture(str(video_path))
    fps   = cap.get(cv2.CAP_PROP_FPS) or report_json.get('fps') or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or report_json.get('total_frames', 0)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # [회전 보정] OCR(index) 기준과 90도 어긋나면 회전코드 설정 + 출력 W,H 스왑.
    if _set_frame_rot(cap, report_json.get('image_width'), report_json.get('image_height')) is not None:
        W, H = H, W
    cap.release()

    margin = int(fps * PREVIEW_VIDEO_MARGIN_SEC)
    anchor = events[0][0]                                   # 가장 먼저 탐지된 지점
    lo = max(0, anchor - margin); hi = min(total - 1, anchor + margin)
    win_events = [e for e in events if lo <= e[0] <= hi] or [events[0]]

    print(f"  👁  영상 미리보기 샘플 [{round(lo/fps,1)}s ~ {round(hi/fps,1)}s] 마스킹...")
    def track_cb(c, t):
        if progress_cb: progress_cb(c / max(1, t) * 0.4)
    mask_map = _vid_track_template(video_path, win_events, fps, hi + 1, progress_cb=track_cb)
    
    def mask_cb(c, t):
        if progress_cb: progress_cb(0.4 + (c / max(1, t)) * 0.6)
    temp_path, _ = _video_mask_to_temp(video_path, mask_map, fps, total, W, H, output_dir,
                                       tag=f"preview_{video_path.stem}",
                                       frame_lo=lo, frame_hi=hi, watermark_preview=True,
                                       progress_cb=mask_cb)
    clip_path = output_dir / f"미리보기_{video_path.stem}.mp4"
    _mux_audio(temp_path, video_path, clip_path, audio_offset_sec=lo / fps)
    print(f"  ✅ 미리보기 클립 → {clip_path.name}")
    return {'original': str(video_path), 'preview_clip': str(clip_path),
            'start_sec': round(lo / fps, 3), 'end_sec': round(hi / fps, 3)}


# ═════════════════════════════════════════════════════════════════════════════
# 6~7단계 — 본 처리 (전체 마스킹 + 워터마크 + 다운로드 파일)
# ═════════════════════════════════════════════════════════════════════════════
def mask_image_full(img_path, report_json, selected_ids=None, output_dir=None, stem=None):
    """[이미지] 선택 PII 전체 마스킹 → 우하단/비가시 워터마크 → {stem}_결과 저장.
    반환: (out_path, coords_map)  coords_map={pii_id: [[x1,y1,x2,y2],...]} (masked_coords 기록용)"""
    output_dir = Path(output_dir or OUTPUT_DIR); output_dir.mkdir(parents=True, exist_ok=True)
    img_path = Path(img_path)
    stem = stem or img_path.stem
    image = cv2.imdecode(np.fromfile(str(img_path), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        print(f"  ⚠️  이미지 읽기 실패: {img_path}"); return None, {}
    masked = mask_selected_on_image(image, report_json.get('pii_groups', []), selected_ids)
    masked = apply_watermarks(masked, preview=False)
    # 코랩 워커에서 다운로드된 파일에 확장자가 없을 수 있으므로 안전하게 폴백
    ext = img_path.suffix if img_path.suffix else '.jpg'
    out_path = output_dir / f"{stem}_결과{ext}"
    ok, enc = cv2.imencode(ext, masked)
    if ok:
        enc.tofile(str(out_path)); print(f"  💾 결과(다운로드용) → {out_path.name}")
    # 마스킹된 영역 좌표 수집(선택 그룹의 박스 좌표)
    coords_map = {}
    for g in report_json.get('pii_groups', []):
        if selected_ids is not None and g.get('pii_id') not in selected_ids:
            continue
        coords_map[g['pii_id']] = [[b['x_min'], b['y_min'], b['x_max'], b['y_max']]
                                   for b in g.get('boxes', [])]
    return out_path, coords_map


def mask_video_full(video_path, report_json, selected_ids=None, output_dir=None, stem=None, progress_cb=None):
    """[영상] 선택 PII 전체 추적 마스킹 → 전 프레임 워터마크 → FFmpeg 오디오 합성 → {stem}_결과.
    반환: (final_path, coords_map)  coords_map={pii_id: {frame: [[x1,y1,x2,y2],...]}} (masked_coords 기록용)"""
    output_dir = Path(output_dir or OUTPUT_DIR); output_dir.mkdir(parents=True, exist_ok=True)
    video_path = Path(video_path)
    stem = stem or video_path.stem
    events = _events_from_groups(report_json, selected_ids)
    if not events:
        print("  ℹ️  마스킹할 PII 없음 — 종료."); return None, {}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"❌ 영상 열기 실패: {video_path}"); return None, {}
    fps   = cap.get(cv2.CAP_PROP_FPS) or report_json.get('fps') or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or report_json.get('total_frames', 0)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # [회전 보정] OCR(index) 기준과 90도 어긋나면 회전코드 설정 + 출력 W,H 스왑.
    if _set_frame_rot(cap, report_json.get('image_width'), report_json.get('image_height')) is not None:
        W, H = H, W
    cap.release()

    print(f"  픽셀 템플릿 추적...")
    def track_cb(c, t):
        if progress_cb: progress_cb(c / max(1, t) * 0.4)
    mask_map = _vid_track_template(video_path, events, fps, total, progress_cb=track_cb)
    print(f"  → 마스킹 대상 프레임 {len(mask_map)}개")
    print(f"  적응형 인페인팅 + 워터마크(전 프레임)...")
    def mask_cb(c, t):
        if progress_cb: progress_cb(0.4 + (c / max(1, t)) * 0.6)
    temp_path, masked_cnt = _video_mask_to_temp(video_path, mask_map, fps, total, W, H, output_dir,
                                                tag=stem, watermark_preview=False, progress_cb=mask_cb)
    print(f"  ✅ 마스킹 {masked_cnt}프레임")
    print(f"  FFmpeg 오디오 합성...")
    final_path = output_dir / f"{stem}_결과.mp4"
    # 오디오 PII(선택분)에 비프음 합성. 비프 wav 가 만들어지면 그것을 오디오 소스로,
    # 없으면(오디오 PII 미선택/없음) 원본 오디오를 그대로 사용한다.
    beeped_path = _generate_beeped_audio(video_path, report_json, selected_ids, output_dir, stem)
    _mux_audio(temp_path, video_path, final_path, audio_path=beeped_path)
    
    if beeped_path and Path(beeped_path).exists():
         Path(beeped_path).unlink()   # 비프 임시 wav 정리
    # if beeped_path:
    #    print(f"  🎙️ [테스트용] 비프음 합성 오디오 별도 저장: {beeped_path}")
        
    print(f"  🎉 결과(다운로드용) → {final_path}")

    # 마스킹된 영역 좌표 수집(프레임별 추적 bbox). mask_map 은 pii_id 키 → 그룹별 정확 매핑.
    coords_map = {}
    for g in report_json.get('pii_groups', []):
        if selected_ids is not None and g.get('pii_id') not in selected_ids:
            continue
        pid = g.get('pii_id'); per_frame = {}
        for fi, items in mask_map.items():
            for ipid, _boxes, bbox in items:
                if ipid == pid:
                    per_frame.setdefault(str(fi), []).append(
                        [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])])
        coords_map[g['pii_id']] = per_frame
    return final_path, coords_map


# ── 진입점 함수 (입력: {stem}_result.json + 원본 + 선택 pii_id) ──
def run_preview(index_json_path, input_path=None, selected_ids=None, progress_cb=None):
    """[5단계] 샘플 마스킹 미리보기 생성. selected_ids 미지정 시 is_selected==True 사용."""
    rep = _load_report(index_json_path)
    src_type, src_name, src_path = _resolve_source(rep, index_json_path, input_path)
    if src_path is None or not Path(src_path).exists():
        print(f"❌ 원본 파일을 찾을 수 없음: {src_name}"); return None

    if selected_ids is None:
        selected_ids = _selected_ids_from_index(rep) or None   # 선택 없으면 전체

    print(f"\n{'='*60}\n👁  미리보기: {src_name} (선택: {selected_ids or '전체'})\n{'='*60}")
    if src_type == 'image':
        # 이미지는 상대적으로 빠르므로 콜백 호출 대신 바로 완료로 처리
        if progress_cb: progress_cb(0.5)
        res = preview_image(src_path, rep, selected_ids)
        if progress_cb: progress_cb(1.0)
        return res
    elif src_type == 'video':
        return preview_video(src_path, rep, selected_ids, progress_cb=progress_cb)
    print(f"[!] 알 수 없는 source_type: {src_type}"); return None


def run_masking(index_json_path, input_path=None, selected_ids=None, progress_cb=None):
    """[6~7단계] 선택 PII 전체 마스킹 + 워터마크 → 다운로드 파일 생성. selected_ids 미지정 시 is_selected==True 사용."""
    rep = _load_report(index_json_path)
    src_type, src_name, src_path = _resolve_source(rep, index_json_path, input_path)
    stem = rep.get('source_stem') or Path(src_name).stem
    if src_path is None or not Path(src_path).exists():
        print(f"❌ 원본 파일을 찾을 수 없음: {src_name}"); return None

    if selected_ids is None:
        selected_ids = _selected_ids_from_index(rep) or None   # 선택 없으면 전체

    print(f"\n{'='*60}\n🎯 본 마스킹: {src_name} (선택: {selected_ids or '전체'})\n{'='*60}")
    out_path, coords_map = (None, {})
    if src_type == 'image':
        if progress_cb: progress_cb(0.5)
        out_path, coords_map = mask_image_full(src_path, rep, selected_ids, stem=stem)
        if progress_cb: progress_cb(1.0)
    elif src_type == 'video':
        out_path, coords_map = mask_video_full(src_path, rep, selected_ids, stem=stem, progress_cb=progress_cb)
    else:
        print(f"[!] 알 수 없는 source_type: {src_type}"); return None

    # 마스킹 좌표를 index.json 에 기록(Q1: mask 가 masked_coords 채움)
    if coords_map:
        _write_masked_coords(index_json_path, rep, coords_map)
    return out_path


def _mark_first_selected(result_json_path) -> list:
    """[테스트 전용] 흐름4 UI 미구현 → '가장 위 1번' PII 만 is_selected=True 로 세팅 후 저장.
    (수정사항5) 실제 서비스에선 백엔드가 사용자 선택값으로 is_selected 갱신.
    반환: 선택된 pii_id 목록."""
    rep = _load_report(result_json_path)
    groups = rep.get('pii_groups', [])
    audio_groups = rep.get('audio_pii_groups', [])
    
    if not groups and not audio_groups:
        return []
    for i, g in enumerate(groups):
        g['is_selected'] = (i == 0)        # 첫 번째만 선택
    for i, g in enumerate(audio_groups):
        g['is_selected'] = (i == 0 and not groups) # 시각이 없으면 첫 오디오라도 선택

    with open(str(result_json_path), 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    sel = [g.get('pii_id', 'audio_pii') for g in groups + audio_groups if g.get('is_selected')]
    print(f"  ✅ [테스트] 첫 PII 선택: {sel}")
    return sel


def _mark_all_selected(result_json_path) -> list:
    """[테스트 전용] 모든 PII 를 is_selected=True 로 세팅 후 저장(전체 마스킹 확인용).
    같은 type 의 다른 PII(카드 2개 등)가 분리되어도 전부 마스킹되도록 한다.
    실제 서비스에선 백엔드가 사용자 선택값으로 is_selected 갱신."""
    rep = _load_report(result_json_path)
    groups = rep.get('pii_groups', [])
    audio_groups = rep.get('audio_pii_groups', [])
    
    if not groups and not audio_groups:
        return []
    for g in groups:
        g['is_selected'] = True
    for g in audio_groups:
        g['is_selected'] = True
        
    with open(str(result_json_path), 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    sel = [g.get('pii_id', 'audio_pii') for g in groups + audio_groups if g.get('is_selected')]
    print(f"  ✅ [테스트] 전체 PII 선택({len(sel)}개): {sel}")
    return sel


def _read_report_test_target_stem():
    """colab_pipeline_report.py 의 TEST_TARGET 값을 텍스트로 읽어 파일명(stem)만 반환.
    report 를 import 하지 않으므로 무거운 의존성(PaddleOCR 등) 로드 없이 빠르고 안전하다.
    찾지 못하면 None."""
    rp = BASE_DIR / "OCR_pipeline_report.py"
    if not rp.exists():
        return None
    try:
        txt = rp.read_text(encoding='utf-8')
    except Exception:
        return None
    # 예: TEST_TARGET = r"...\test_video_file\카드_영상1.mp4"  → '카드_영상1'
    m = re.search(r'^\s*TEST_TARGET\s*=\s*[rR]?["\'](.+?)["\']', txt, re.MULTILINE)
    if not m:
        return None
    # ※ Path(...).stem 은 실행 OS 기준이라 Colab(Linux)에서 Windows 경로(\)를 못 쪼갬.
    #    → \ 와 / 둘 다 직접 분리해 OS 무관하게 파일명(stem)만 추출.
    name = re.split(r'[\\/]', m.group(1).strip())[-1]
    return name.rsplit('.', 1)[0] if '.' in name else name


# ═════════════════════════════════════════════════════════════════════════════
# [STEP J] Colab Mask Worker — 백엔드 폴링 루프
# STT 워커(garim_colab_worker.py)와 동일한 패턴으로 구현.
# mask_preview / mask_final job을 감지해 인페인팅 마스킹 처리 후 결과 파일 업로드.
#
# Colab 셀에서 실행 방법:
#   import importlib, colab_pipeline_mask as m; importlib.reload(m); m.mask_run_loop()
# 또는 단건 테스트:
#   m.mask_run_once()
# ═════════════════════════════════════════════════════════════════════════════

import threading as _threading
import tempfile as _tempfile
import requests as _requests

# ===== Colab에서 직접 수정하는 설정값 =====
MASK_BACKEND_URL           = "https://your-cloudflare-url"   # Cloudflare Tunnel URL (슬래시 없이)
MASK_WORKER_SECRET         = "change_me_to_a_long_random_secret"
MASK_WORKER_ID             = "colab-mask-worker-01"
MASK_POLL_INTERVAL_SECONDS = 10    # job 없을 때 재폴링 간격(초) — 이벤트성이므로 짧게 유지
MASK_HEARTBEAT_INTERVAL    = 30    # heartbeat 전송 주기(초)
MASK_DOWNLOAD_DIR          = "/content/garim_mask_downloads"
# ==========================================

import os as _os
_os.makedirs(MASK_DOWNLOAD_DIR, exist_ok=True)

import logging as _logging
_mlog = _logging.getLogger("garim-mask-worker")
if not _mlog.handlers:
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ── API 헬퍼 ────────────────────────────────────────────────────────────────

def _mauth():
    """Bearer 인증 헤더 반환"""
    return {"Authorization": f"Bearer {MASK_WORKER_SECRET}"}


def _m_get_next_job():
    """GET /worker/jobs/next?worker_type=colab_mask — mask_preview/mask_final job 가져오기"""
    r = _requests.get(
        f"{MASK_BACKEND_URL}/worker/jobs/next",
        params={"worker_type": "colab_mask"},
        headers=_mauth(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("job")


def _m_accept(job_id):
    """POST /worker/jobs/{id}/accept — job 처리 시작 선언"""
    r = _requests.post(
        f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/accept",
        headers=_mauth(),
        json={"worker_id": MASK_WORKER_ID},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _m_progress(job_id, stage, sp, tp, msg=None):
    """PUT /worker/jobs/{id}/progress — 진행률 업데이트"""
    r = _requests.put(
        f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/progress",
        headers=_mauth(),
        json={
            "worker_id":      MASK_WORKER_ID,
            "stage_name":     stage,
            "stage_progress": sp,
            "total_progress": tp,
            "message":        msg,
        },
        timeout=10,
    )
    r.raise_for_status()


def _m_heartbeat(job_id, stage=None, progress=0):
    """POST /worker/heartbeat — 생존 신호 (실패해도 워커 중단 안 함)"""
    try:
        _requests.post(
            f"{MASK_BACKEND_URL}/worker/heartbeat",
            headers=_mauth(),
            json={
                "job_id":          job_id,
                "worker_id":       MASK_WORKER_ID,
                "worker_type":     "colab_mask",
                "current_stage":   stage,
                "progress_percent": progress,
            },
            timeout=10,
        ).raise_for_status()
    except Exception as _e:
        _mlog.warning(f"heartbeat 실패 (무시): {_e}")


def _m_download_file(upload_id):
    """GET /worker/files/{upload_id}/download — 원본 파일 바이너리 다운로드"""
    r = _requests.get(
        f"{MASK_BACKEND_URL}/worker/files/{upload_id}/download",
        headers=_mauth(),
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    cd = r.headers.get("content-disposition", "")
    filename = f"upload_{upload_id}"
    if "filename=" in cd:
        filename = cd.split("filename=")[-1].strip().strip('"').strip("'")
    out_path = _os.path.join(MASK_DOWNLOAD_DIR, filename)
    with open(out_path, "wb") as _f:
        for chunk in r.iter_content(65536):
            _f.write(chunk)
    size_mb = _os.path.getsize(out_path) / 1024 / 1024
    _mlog.info(f"원본 다운로드 완료: {out_path} ({size_mb:.1f} MB)")
    return out_path, filename


def _m_get_mask_context(job_id):
    """GET /worker/jobs/{id}/mask-context — result_json 내용 + selected_pii_ids 반환"""
    r = _requests.get(
        f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/mask-context",
        headers=_mauth(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _m_upload_result(job_id, file_path, content_type):
    """POST /worker/jobs/{id}/results/upload-file — 처리 완료 파일 multipart 업로드"""
    import urllib.parse
    raw_filename = Path(file_path).name
    safe_filename = urllib.parse.quote(raw_filename)  # 한글 파일명 전송 시 latin-1 에러 방지
    with open(file_path, "rb") as _f:
        r = _requests.post(
            f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/results/upload-file",
            headers=_mauth(),
            files={"file": (safe_filename, _f, content_type)},
            timeout=300,
        )
    r.raise_for_status()
    _mlog.info(f"결과 파일 업로드 완료: {raw_filename}")
    return r.json()


def _m_complete(job_id):
    """POST /worker/jobs/{id}/complete — 정상 완료 보고"""
    r = _requests.post(
        f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/complete",
        headers=_mauth(),
        json={"worker_id": MASK_WORKER_ID},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _m_fail(job_id, code, msg):
    """POST /worker/jobs/{id}/fail — 실패 보고 (전송 실패해도 로그만)"""
    try:
        _requests.post(
            f"{MASK_BACKEND_URL}/worker/jobs/{job_id}/fail",
            headers=_mauth(),
            json={"worker_id": MASK_WORKER_ID, "error_code": code, "error_message": msg},
            timeout=10,
        ).raise_for_status()
    except Exception as _e:
        _mlog.error(f"fail_job 전송 실패: {_e}")


# ── Heartbeat 스레드 ────────────────────────────────────────────────────────

class _MaskHeartbeat(_threading.Thread):
    """마스킹 처리 중 주기적으로 생존 신호 전송"""
    def __init__(self, job_id):
        super().__init__(daemon=True)
        self.job_id = job_id
        self._stop  = _threading.Event()
        self._stage = None
        self._prog  = 0

    def update(self, stage, progress):
        self._stage = stage
        self._prog  = progress

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(MASK_HEARTBEAT_INTERVAL):
            _m_heartbeat(self.job_id, self._stage, self._prog)


# ── 워커 루프 ───────────────────────────────────────────────────────────────

def mask_run_once():
    """mask job 1개를 처리한다.

    Returns:
        True  — job 처리했음 (성공/실패 불문)
        False — 대기 중인 job 없음
    """
    job = _m_get_next_job()
    if job is None:
        return False

    job_id    = job["job_id"]
    upload_id = job["upload_id"]
    job_type  = job.get("job_type", "mask_preview")
    _mlog.info(f"mask job 수신: {job_id} | type={job_type} | upload={upload_id}")

    hb = _MaskHeartbeat(job_id)
    hb.start()

    try:
        _m_accept(job_id)

        # Phase 1: 원본 파일 다운로드 (0→15%)
        _m_progress(job_id, "file_download", 0, 0, "원본 파일 다운로드 중...")
        hb.update("file_download", 0)
        src_path, src_filename = _m_download_file(upload_id)
        _m_progress(job_id, "file_download", 100, 15, f"다운로드 완료: {src_filename}")
        hb.update("file_download", 15)

        # Phase 2: mask context 조회 (result_json + selected_pii_ids) (15→20%)
        _m_progress(job_id, "load_context", 0, 15, "마스킹 컨텍스트 조회 중...")
        ctx          = _m_get_mask_context(job_id)
        result_json  = ctx.get("result_json") or {}
        selected_ids = ctx.get("selected_pii_ids") or None
        _mlog.info(f"context 조회 완료 | selected_ids={selected_ids}")
        _m_progress(job_id, "load_context", 100, 20, "컨텍스트 로드 완료")
        hb.update("load_context", 20)

        # result_json을 임시 파일로 저장 (run_preview/run_masking 파일 인터페이스 호환)
        tmp = _tempfile.NamedTemporaryFile(
            suffix="_result.json", delete=False, mode="w", encoding="utf-8"
        )
        json.dump(result_json, tmp, ensure_ascii=False)
        tmp.close()
        tmp_json_path = tmp.name

        # Phase 3: 인페인팅 마스킹 처리 (20→80%)
        _m_progress(job_id, "masking", 0, 20, "인페인팅 마스킹 중...")
        hb.update("masking", 20)
        def mask_progress_cb(fraction):
            # fraction goes from 0.0 to 1.0 within the masking phase
            pct = 20 + int(fraction * 60)
            sp = int(fraction * 100)
            _m_progress(job_id, "masking", sp, pct, f"인페인팅 마스킹 중... ({sp}%)")
            hb.update("masking", pct)

        output_file = None
        try:
            if job_type == "mask_preview":
                # 미리보기: 검토용 큰 워터마크 적용, 영상은 6초 클립
                result = run_preview(tmp_json_path, input_path=src_path, selected_ids=selected_ids, progress_cb=mask_progress_cb)
                if result is None:
                    raise RuntimeError("run_preview() 반환값 없음 — 선택된 PII 없거나 파일 오류")
                # 이미지: result['preview'] / 영상: result['preview_clip']
                output_file = result.get("preview") or result.get("preview_clip")
            else:
                # 본처리: 비가시 워터마크 적용, 전체 마스킹
                out = run_masking(tmp_json_path, input_path=src_path, selected_ids=selected_ids, progress_cb=mask_progress_cb)
                if out is None:
                    raise RuntimeError("run_masking() 반환값 없음 — 선택된 PII 없거나 파일 오류")
                output_file = str(out)
        finally:
            try:
                _os.unlink(tmp_json_path)
            except Exception:
                pass

        if not output_file or not _os.path.exists(output_file):
            raise RuntimeError(f"마스킹 결과 파일 없음: {output_file}")

        _mlog.info(f"마스킹 완료: {output_file}")
        _m_progress(job_id, "masking", 100, 80, f"마스킹 완료: {Path(output_file).name}")
        hb.update("masking", 80)

        # Phase 4: 결과 파일 업로드 (80→95%)
        _m_progress(job_id, "upload", 0, 80, "결과 파일 업로드 중...")
        hb.update("upload", 80)
        ext = Path(output_file).suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            ctype = "image/jpeg"
        elif ext == ".png":
            ctype = "image/png"
        else:
            ctype = "video/mp4"
        _m_upload_result(job_id, output_file, ctype)
        _m_progress(job_id, "upload", 100, 95, "업로드 완료")
        hb.update("upload", 95)

        # Phase 5: 완료 (95→100%)
        _m_complete(job_id)
        _mlog.info(f"mask job 완료: {job_id}")
        return True

    except Exception as _e:
        _mlog.error(f"mask job 처리 실패: {_e}")
        _m_fail(job_id, "MASK_WORKER_ERROR", str(_e))
        return False
    finally:
        hb.stop()


def mask_run_loop():
    """mask job을 계속 polling하며 처리한다. Colab ■ 버튼으로 중단.

    STT 워커와 동일한 패턴 — job이 있으면 즉시 처리, 없으면 MASK_POLL_INTERVAL_SECONDS 대기.
    미리보기 클릭은 이벤트성이므로 폴링 간격을 10초로 설정해 빠르게 반응한다.
    """
    _mlog.info(
        f"Mask Worker 루프 시작 | ID={MASK_WORKER_ID} | POLL={MASK_POLL_INTERVAL_SECONDS}s"
    )
    while True:
        try:
            has_job = mask_run_once()
            if not has_job:
                import time as _time
                _time.sleep(MASK_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            _mlog.info("Mask Worker 루프 종료 (KeyboardInterrupt)")
            break
        except Exception as _e:
            _mlog.error(f"루프 오류 (재시도 대기): {_e}")
            import time as _time
            _time.sleep(MASK_POLL_INTERVAL_SECONDS)


# ── 테스트 실행: report TEST_TARGET 기준 _result.json → 3~7단계 순서대로 실행 ──
if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    # Colab/Jupyter: sys.argv 에 커널 런타임 json이 섞임 → _index.json 으로 끝나야 유효한 인수
    # Colab/Jupyter: sys.argv에 커널 런타임 json 섞임 → _result.json 으로 끝나야 유효
    if args and not str(args[0]).endswith('_result.json'):
        args = []

    if args:
        ij  = args[0]
        inp = args[1] if len(args) > 1 else None
    else:
        # report TEST_TARGET 기준 우선, 없으면 OUTPUT_DIR의 *_result.json 폴백
        stem   = _read_report_test_target_stem()
        target = (OUTPUT_DIR / f"{stem}_result.json") if stem else None
        if target and target.exists():
            ij, inp = str(target), None
            print(f"ℹ️  {target.name} 으로 실행")
        else:
            if stem:
                print(f"[!] {stem}_result.json 없음 → 자동 탐색으로 폴백")
            cands = sorted(OUTPUT_DIR.glob("*_result.json"))
            if not cands:
                print(f"[!] *_result.json 없음 → backend_json_merger.py 먼저 실행: {OUTPUT_DIR}")
                sys.exit(0)
            ij, inp = str(cands[0]), None
            print(f"ℹ️  자동 탐색 → {Path(ij).name}")

    print(f"\n[3단계] 상세보기 생성...")
    run_detail_view(ij, input_path=inp)
    print(f"\n[4단계] 사용자 선택 (테스트: 전체 PII is_selected=True)...")
    _mark_all_selected(ij)        # 테스트: 모든 PII 마스킹(분리된 카드 2개 등 전부)
    print(f"\n[5단계] 미리보기 — 테스트 단계 패스(추후 개발)")
    print(f"\n[6~7단계] 본 마스킹 실행...")
    run_masking(ij, input_path=inp)
