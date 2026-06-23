"""
통합 OCR (이미지 + 영상)  / PaddleOCR
═══════════════════════════════════════════════════════════════════════════════
[엔진] PaddleOCR (한국어 PP-OCRv5). 로컬 실행이므로 API 불필요

[출력 JSON 규격 — colab_pipeline_mask.py 호환]
  source_type   : "image" / "video"
  source_name   : 원본 파일명
  frame_idx     : 영상=프레임번호 / 이미지=""(빈칸)
  timestamp_sec : 영상=재생초 / 이미지=""(빈칸)
  font_zones[]  : 구역(zone)별 단어 박스 목록 (zone_id, zone_comment, boxes)

═══════════════════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────────────────┐
│ [참고] 실제 서비스 업로드 처리 로직(골격만, UI 제외) — 추후 프론트/백엔드 연동    │
│  파일 업로드 시 OCR 전에 거쳐야 할 공통 전처리 단계 설계입니다.                  │
│  (NFR-04 다중파일 / NFR-07 멀티확장자 / NFR-08 용량제한 / NFR-10 EXIF제거 /     │
│   NFR-11 비동기). 지금은 주석으로만 두고, 연동 시 실제 구현으로 전환하세요.       │
│                                                                              │
│  def handle_upload(files):                                                   │
│      for f in files:                          # NFR-04 다중 파일 반복         │
│          if not _check_ext(f): reject(f)      # NFR-07 허용 확장자 검사       │
│          if not _check_size(f): reject(f)     # NFR-08 무료100MB/유료500MB    │
│          f = _strip_exif(f)                   # NFR-10 위치·기기정보 메타 제거 │
│          enqueue_async_job(f)                 # NFR-11 비동기 작업 큐 등록     │
│      return job_ids                            # 진행상황 polling용 ID 반환    │
└───────────────────────────────────────────────────────────────────────────────┘
"""

import os
import sys

# ── PaddlePaddle 환경 플래그 (플랫폼/GPU 자동 분기) ──────────────────────────
# Windows CPU에서만 PIR/oneDNN 비활성화: Paddle 3.x PIR이 Windows CPU에서 오류 발생
# Linux/GPU(Colab 포함) 환경에선 이 플래그가 오히려 GPU 성능을 낮추므로 스킵
# (os.environ은 라이브러리 로드 '전'에 설정해야 효과 → 반드시 paddlex import 전에 선언)
_use_gpu = os.environ.get('PADDLE_USE_GPU', '0') == '1'
if sys.platform == 'win32' and not _use_gpu:
    os.environ['FLAGS_use_mkldnn']             = '0'
    os.environ['FLAGS_enable_pir_api']         = '0'
    os.environ['FLAGS_enable_pir_in_executor'] = '0'
os.environ['FLAGS_call_stack_level'] = '2'
# ── 여기까지 os.environ ── (반드시 paddlex import 전에 위치해야 함)

from paddlex.inference import pipelines
import cv2
import json
import math
import numpy as np
import time
from pathlib import Path
from collections import defaultdict

# ── 콘솔 출력 인코딩 UTF-8 고정 ───────────────────────────────────────────────
# Windows 기본 콘솔(cp949)에서 이모지/한글 로그 출력 시 UnicodeEncodeError 방지
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from paddleocr import PaddleOCR
    _PADDLE_AVAILABLE = True
except ImportError:
    # import 단계에서 죽지 않게 함(다른 모듈이 이 파일을 import 가능). 실제 OCR 호출 시 에러.
    PaddleOCR = None
    _PADDLE_AVAILABLE = False

    print("[경고] paddleocr 미설치 — window 로컬에서 CPU로 OCR 사용하려면: pip install paddlepaddle paddleocr")
    print("""
    [경고] paddleocr gpu 버전 미설치 — Colab에서 OCR 사용하려면: 
    !pip uninstall paddlepaddle -y -q
    !pip install paddlepaddle-gpu -q
    !pip install paddleocr -q
    """)
    

# ═══════════════════════════════════════════════════════════════
# ▶ 환경설정 (OCR 옵션 전용)
#   ※ 경로/입출력/테스트경로는 colab_pipeline_report.py에서만 관리합니다.
#     이 파일은 colab이 import해 함수로 호출하며, 경로는 호출 측이 인자로 넘깁니다.
#     → 여기서는 OCR 성능 옵션만 변경하면 됩니다(경로는 건드릴 필요 없음).
# ═══════════════════════════════════════════════════════════════
# ── 영상 샘플링 ──
SAMPLE_INTERVAL_SEC = 1.0     # N초당 1프레임 (픽셀추적이 ±간격을 보완하므로 충분 + 속도 우선)
TEXT_FILTER_ENABLED = True    # OCR 전 엣지 밀도로 '텍스트 없는 프레임' 사전 스킵
TEXT_DENSITY_MIN    = 0.003   # Canny 엣지 최소 밀도 (흐린 텍스트도 통과)
TEXT_CANNY_LOW      = 40
TEXT_CANNY_HIGH     = 150

# ── OCR 전처리 (CLAHE + 선명화 + 업스케일): 흐린/저대비 텍스트 인식률 향상 ──
OCR_ENHANCE_ENABLED = True
OCR_ENHANCE_SCALE   = 1.3     # 업스케일 배율(기본1.0, 배율이 낮을수록 속도가 빠름)
OCR_CLAHE_CLIP      = 1.8     # CLAHE 국소 대비 강도
OCR_SHARP_STRENGTH  = 1.2     # 언샤프 마스킹 강도

# ── 조건부 고배율 재OCR: 작게 보이는 주소가 깨진 프레임만 n.n x 재OCR 시도 ──
# 트리거 = (한글 문서성 OR 도로 단서) AND 행정구역(시+구) 미완성
# → 주소가 이미 잘 잡힌 프레임은 스킵해 속도 절감 (카드 등 한글 적은 영상은 영향 없음)
OCR_HIRES_RETRY_ENABLED = True
OCR_HIRES_SCALE         = 2.0  # 추가 업 스케일 배율 (2.5배 이상 시 CPU 메모리 부족/멈춤 발생 가능)
OCR_HIRES_BOX_MIN       = 8    # 재OCR 판단용 최소 총 박스 수
OCR_HIRES_KR_MIN        = 2    # 재OCR 판단용 최소 한글 박스 수

# ── 단어별 타이트 박스 ──
#   PaddleOCR 줄(line) 박스를 '실제 글자 사이 빈 공간(잉크 갭)'으로 단어 단위로 끊고,
#   숫자/문자 사이의 . , - 구두점에서 추가로 끊어(구두점은 앞 토큰에 붙임) 단어별
#   타이트한 직각 4점 박스를 만든다. (PaddleOCR이 한글 단어 사이 공백을 안 넣어도 대응)
WORD_BOX_PAD   = 1.5   # 잉크와 테두리 사이 여백(px). 작을수록 타이트(0~2 권장)
WORD_GAP_RATIO = 0.45  # 단어경계 최소 갭 = 글자높이×이 비율 (실제 글자간격 중앙값×1.8과 비교, 큰 값 사용)
WORD_COL_THR   = 0.30  # 칸 점유 기준 = 칼럼 잉크 피크×이 비율 이상 (↑더 잘게 끊김 / ↓덜 끊김)
                       #   0.15=거의 안끊김 / 0.30=단어분리(단일단어 보존, 권장) / 0.40↑=음절 과분할

# ── 선명도 기반 최적 프레임 선택 (모션블러/흔들림 구간 대응, 영상 전용) ──
SHARP_SELECT_ENABLED = True   # 샘플 포인트 ±N프레임 중 가장 선명한 프레임을 OCR 대상으로
SHARP_SELECT_WINDOW  = 2      # 탐색 범위 ±N프레임 (30fps 기준 ±0.1초)

# ── 디버깅용 산출물(시각화 region jpg + 텍스트 txt) 생성 여부 ──
#   True 로 두면 OCR 결과 확인용 region_*.jpg / text_*.txt 를 함께 저장(디버깅).
#   서비스 기본은 False — 불필요한 파일 생성 안 함(ocr_data_*.json 은 파이프라인 필수라 항상 생성).
SAVE_DEBUG_OUTPUTS = False

# ── PaddleOCR ──
PADDLE_LANG             = "korean"
PADDLE_USE_TEXTLINE_ORI = True   # 활성화: 택배 송장 등 90도/180도 돌아간 세로쓰기/역방향 텍스트 정확도 대폭 향상

# ── 클러스터링/조립 ──
ANGLE_THRESH    = 10    # 각도 차이 임계값(도): 이상이면 다른 클러스터
GAP_MULT        = 1.5   # 간격 = 평균 글자높이 × N 이상이면 다른 클러스터
MIN_PROB        = 0.3   # OCR 신뢰도 하한
ANGLE_GAP_SPLIT = 6.0   # 각도 분포 최대 갭이 이 이상이면 강제 분리

# ── 객체 분리(배경색) — '같은 종이 위' 글자끼리만 한 구역으로 묶기 ──
#   배경/주변 색이 다르면(송장 흰 라벨 vs 갈색 박스) 다른 객체로 보고 병합 차단.
#   색이 같아도 각도가 다르면(겹친 A4 2장) 기존 각도 조건이 분리 → 색·각도 둘 다 봐야 정확.
BG_COLOR_ENABLED   = True   # 배경색 기반 객체 분리 사용 여부
BG_COLOR_THRESH    = 26.0   # 두 박스 '주변 배경색'의 LAB 거리 임계. 초과 시 다른 객체로 보고 병합 차단
                            #   (우편물3 실측: 30=다묶임 / 22=송장↔손글씨 분리 / 16↓=송장 과분리 → 22가 균형점)
BG_RING_PAD_RATIO  = 0.3    # 배경색 샘플용 박스 외곽 링 두께(박스 크기 대비 비율)

# ── 객체 분리(로컬 복잡도) — 색이 비슷해도 '주변 복잡도'로 갈리게 하는 보조 단서 ──
#   바코드/조밀 인쇄 라벨은 주변 엣지 밀도가 매우 높고, 손글씨/단순 배경은 낮음.
#   택배 박스≈흰 라벨처럼 색거리가 애매(임계 근처)할 때, 복잡도 차이로 다른 객체를 구분.
#   (특정 색 하드코딩 아님 — 일반 엣지 밀도 차이만 사용)
COMPLEXITY_ENABLED   = True   # 로컬 복잡도 기반 객체 분리 사용 여부
COMPLEXITY_THRESH    = 0.07   # 두 박스 '주변 엣지밀도' 차이 임계. 초과 시 다른 객체로 보고 병합 차단
                              #   (우편물3 실측: 0.07↑=즉납 섞임 / 0.05~0.065=손글씨주소↔송장라벨 분리 → 0.06)
                              #   (↑ 덜 분리 / ↓ 더 분리. 다른 송장서 과분리 시 0.07~0.08로 ↑)
COMPLEXITY_PAD_RATIO = 1.3    # 복잡도 샘플 영역(박스 크기 대비 주변 확장 비율)

# ── dHash 중복 프레임 제거 (영상 전용) ──
DEDUPE_HAMMING_THRESHOLD = 4   # Hamming 거리 이하면 중복 프레임
DEDUPE_HISTORY_SIZE      = 8   # 비교 대상 이전 해시 보관 수

# ── 문서 윤곽선 탐지 ──
CONTOUR_MIN_RATIO = 0.03
CONTOUR_MAX_RATIO = 0.90
CONTOUR_MIN_DIM   = 60

COLORS = [
    (255,  60,  60), ( 60, 180,  60), ( 60,  60, 255),
    (220, 150,   0), (160,   0, 220), (  0, 190, 190),
    (255, 100, 160), (100, 210, 100), (180, 100,  40), ( 40, 100, 180),
]


# ═══════════════════════════════════════════════════════════════
# ▶ PaddleOCR 엔진 (전역 1회만 초기화 — 프레임마다 로드 금지)
# ═══════════════════════════════════════════════════════════════
_paddle_engine = None

def get_paddle_engine() -> PaddleOCR:
    """PaddleOCR 엔진을 최초 1회만 초기화하고 이후 재사용."""
    global _paddle_engine
    if not _PADDLE_AVAILABLE:
        raise RuntimeError("paddleocr 미설치 — pip install paddlepaddle paddleocr")
    if _paddle_engine is None:
        # GPU 메모리 충돌(OOM) 방지 및 다른 모델(PyTorch 등)의 GPU 사용을 위해
        # PaddleOCR은 기본적으로 CPU 모드로 동작하게 변경합니다.
        # GPU 사용이 꼭 필요한 경우에만 환경변수 PADDLE_USE_GPU='1'을 설정하세요.
        if os.environ.get('PADDLE_USE_GPU', '0') == '1':
            try:
                import torch
                _device = "gpu" if torch.cuda.is_available() else "cpu"
            except ImportError:
                _device = "cpu"
        else:
            _device = "cpu"
        print(f"  🔄 PaddleOCR 엔진 초기화 중... (lang={PADDLE_LANG}, {_device.upper()})")
        print(f"     ※ 최초 실행이면 모델 다운로드로 1~2분 소요될 수 있습니다.")
        _paddle_engine = PaddleOCR(
            lang                         = PADDLE_LANG,                   # 한글 딕셔너리 로딩용 (매우 중요)
            text_detection_model_name    = "PP-OCRv5_server_det",         # mobile: OneDNN 오류 회피
            text_recognition_model_name  = "korean_PP-OCRv5_mobile_rec",  # 한국어 경량 모델
            use_doc_orientation_classify = False,  # 문서 방향 분류 off (속도)
            use_doc_unwarping            = False,  # 문서 왜곡 보정 off (속도)
            use_textline_orientation     = PADDLE_USE_TEXTLINE_ORI,
            device                       = _device,
        )
        print(f"  ✅ PaddleOCR 엔진 준비 완료")
    return _paddle_engine


def paddle_ocr(image: np.ndarray) -> list:
    """
    BGR 이미지를 OCR 처리. 반환: [(bbox, text, conf), ...]
    bbox = [[tl_x,tl_y],[tr_x,tr_y],[br_x,br_y],[bl_x,bl_y]]
    """
    engine = get_paddle_engine()
    try:
        results = list(engine.predict(image))   # PaddleOCR 3.x: predict() 사용
    except Exception as e:
        print(f"  [!] PaddleOCR 실행 오류: {e}")
        return []
    if not results:
        return []

    boxes = []
    
    # 잉크 기반 타이트 다각형 보정 및 단어 분할 함수
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    def _split_and_snap_to_words(std_bbox, text_str, conf):
        """PaddleOCR 줄(line) 박스를 '실제 글자 사이 빈 공간(잉크 갭)'으로 단어 단위로 끊고,
        숫자/문자 사이의 . , - 구두점에서 추가로 끊어(구두점은 앞 토큰에 붙임) 단어별
        타이트한 4점 박스를 만든다. 라벨은 인식 텍스트를 위치 비율로 분배(구역 조립 시 원복).
        std_bbox = [tl, tr, br, bl]."""
        tl = np.array(std_bbox[0], dtype=np.float32)
        tr = np.array(std_bbox[1], dtype=np.float32)
        bl = np.array(std_bbox[3], dtype=np.float32)

        line_vec = tr - tl
        line_len = float(np.linalg.norm(line_vec))
        if line_len < 1e-3 or not text_str:
            return [(std_bbox, text_str, conf)]
        line_dir = line_vec / line_len
        perp_dir = np.array([-line_dir[1], line_dir[0]], dtype=np.float32)
        v_full_lo, v_full_hi = 0.0, float((bl - tl) @ perp_dir)   # 잉크 없을 때 세로 기본값
        if v_full_hi < v_full_lo:
            v_full_lo, v_full_hi = v_full_hi, v_full_lo

        # ── 줄 ROI 안 잉크 픽셀을 (u,v) 좌표로 수집 ──
        pts_int = np.int32(np.round(np.array(std_bbox)))
        x, y, w, h = cv2.boundingRect(pts_int)
        x, y = max(0, x), max(0, y)
        w = min(image.shape[1] - x, w); h = min(image.shape[0] - y, h)
        ink_u = ink_v = None
        if w > 0 and h > 0:
            roi = gray[y:y+h, x:x+w]
            bs = min(31, min(w, h))
            if bs % 2 == 0: bs -= 1
            if bs < 3: bs = 3
            # C>0: 흰 여백(단어 사이 빈 공간)의 잡음 픽셀을 억제 → 갭이 잡음으로 메워지지 않게
            ink_mask = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY_INV, bs, 10)
            poly_mask = np.zeros(roi.shape, dtype=np.uint8)
            cv2.fillPoly(poly_mask, [pts_int - [x, y]], 255)   # 줄 폴리곤 내부만
            ink = cv2.bitwise_and(ink_mask, poly_mask)
            ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                   cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))  # 점 잡음 제거
            ys, xs = np.nonzero(ink)
            if len(xs) > 0:
                rel = np.stack([xs + x, ys + y], axis=1).astype(np.float32) - tl
                ink_u = rel @ line_dir   # 진행 방향 거리
                ink_v = rel @ perp_dir   # 수직(높이) 거리

        pad = float(WORD_BOX_PAD)
        def _xy(uu, vv):
            p = tl + uu * line_dir + vv * perp_dir
            return [int(round(p[0])), int(round(p[1]))]
        def _box(u0, u1, v0, v1):
            return [_xy(u0 - pad, v0 - pad), _xy(u1 + pad, v0 - pad),
                    _xy(u1 + pad, v1 + pad), _xy(u0 - pad, v1 + pad)]

        # 글자폭 가중치 (한글2 / ascii1.1 / 공백0.6) — 라벨 분배·구두점 분할 비율용
        def _cw(c):
            if '가' <= c <= '힣': return 2.0
            if c.isspace():                 return 0.6
            if c.isascii():                 return 1.1
            return 2.0

        # 잉크가 없으면 줄 박스 통째 1개
        if ink_u is None or len(ink_u) < 4:
            return [(_box(0.0, line_len, v_full_lo, v_full_hi), text_str, conf)]

        # 글자 높이 H (갭 임계의 기준)
        H = float(np.percentile(ink_v, 95) - np.percentile(ink_v, 5))
        if H < 1.0:
            H = max(1.0, v_full_hi - v_full_lo)

        # ── 1) 잉크 갭으로 시각적 단어 경계 찾기 ──
        L = int(math.ceil(line_len)) + 1
        col = np.zeros(L, dtype=np.int32)
        np.add.at(col, np.clip(ink_u.astype(np.int32), 0, L - 1), 1)   # u축 1px 칸별 잉크량
        # 칸 점유 기준: 잡음/희미한 다리가 갭을 잇지 않도록 피크 대비 일정량 이상만 '글자 있음'
        #   (낮으면 기울어진 글자가 겹쳐 단어 갭이 메워짐 → 0.30이 단어분리 균형점)
        col_thr = max(2.0, WORD_COL_THR * float(col.max()))
        occ = col >= col_thr
        runs, in_run, s0 = [], False, 0
        for i in range(L):                       # 잉크가 이어진 구간(run) 추출
            if occ[i] and not in_run:
                s0, in_run = i, True
            elif not occ[i] and in_run:
                runs.append([s0, i - 1]); in_run = False
        if in_run:
            runs.append([s0, L - 1])
        if not runs:
            return [(_box(0.0, line_len, v_full_lo, v_full_hi), text_str, conf)]
        # 단어 갭 임계: 글자높이×비율을 바닥값으로, 실제 run 간격 중앙값의 1.8배와 비교(자가적응)
        gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
        word_gap = WORD_GAP_RATIO * H
        if gaps:
            word_gap = max(word_gap, float(np.median(gaps)) * 1.8)
        chunks = [list(runs[0])]
        for r in runs[1:]:
            if r[0] - chunks[-1][1] <= word_gap:
                chunks[-1][1] = r[1]              # 작은 갭(자모/음절 간격) → 같은 단어로 병합
            else:
                chunks.append(list(r))            # 큰 갭(단어 사이 공백) → 새 단어

        # ── 2) 인식 텍스트를 글자폭 비율로 각 시각 단어에 분배(라벨) ──
        widths  = [_cw(c) for c in text_str]
        tot_w   = sum(widths) or 1.0
        labels  = ["" for _ in chunks]
        centers = [(cs + ce) / 2.0 for cs, ce in chunks]
        acc = 0.0
        for c, wch in zip(text_str, widths):
            u_pos = (acc + wch / 2.0) / tot_w * line_len      # 글자의 예상 가로 위치
            ci = None
            for k, (cs, ce) in enumerate(chunks):
                if cs <= u_pos <= ce:
                    ci = k; break
            if ci is None:                                     # 갭에 떨어지면 가장 가까운 단어로
                ci = int(np.argmin([abs(cc - u_pos) for cc in centers]))
            if not c.isspace():
                labels[ci] += c
            acc += wch

        # ── 3) 구두점 분할 삭제 (전화번호 등이 찢어지지 않도록 단어 단위 유지) ──

        # ── 4) 청크별 잉크 타이트 박스 ──
        out = []
        for (cs, ce), label in zip(chunks, labels):
            if not label:
                continue
            pieces = [label]  # 구두점 분할 없이 그대로 하나로 사용
            pw = [sum(_cw(c) for c in p) for p in pieces]      # 토큰별 글자폭 합
            psum = sum(pw) or 1.0
            seg_u, span = float(cs), float(ce - cs)
            for p, ww in zip(pieces, pw):
                u_s = seg_u
                u_e = seg_u + span * (ww / psum)               # 청크 안에서 토큰 u구간 비율 분할
                seg_u = u_e
                m = (ink_u >= u_s - 0.5) & (ink_u <= u_e + 0.5)
                if np.count_nonzero(m) >= 3:                   # 잉크 실제 범위로 타이트화
                    iu0, iu1 = float(ink_u[m].min()), float(ink_u[m].max())
                    iv0, iv1 = float(ink_v[m].min()), float(ink_v[m].max())
                else:
                    iu0, iu1, iv0, iv1 = u_s, u_e, v_full_lo, v_full_hi
                out.append((_box(iu0, iu1, iv0, iv1), p, conf))
        if not out:
            out = [(_box(0.0, line_len, v_full_lo, v_full_hi), text_str, conf)]
        return out

    for res in results:
        polys  = res.get('rec_polys',  [])   # 인식 텍스트와 1:1 매칭된 폴리곤
        texts  = res.get('rec_texts',  [])
        scores = res.get('rec_scores', [])
        for poly, text, conf in zip(polys, texts, scores):
            text_str = str(text).strip()
            if len(poly) < 4 or not text_str:
                continue
            std_bbox = [[float(p[0]), float(p[1])] for p in poly[:4]]
            
            # 각 단어별로 타이트한 잉크 볼록 다각형을 분할해서 추출 (글자 훼손 없음)
            for box, txt, score in _split_and_snap_to_words(std_bbox, text_str, float(conf)):
                boxes.append((box, txt, score))
    return boxes


# ═══════════════════════════════════════════════════════════════
# ▶ 박스 병합 유틸 (고배율 재OCR 결과 합치기)
# ═══════════════════════════════════════════════════════════════
def _box_iou(b1: dict, b2: dict) -> float:
    """두 박스의 IoU(교집합/합집합 비율)."""
    x1 = max(b1['x_min'], b2['x_min']); y1 = max(b1['y_min'], b2['y_min'])
    x2 = min(b1['x_max'], b2['x_max']); y2 = min(b1['y_max'], b2['y_max'])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = (b1['x_max'] - b1['x_min']) * (b1['y_max'] - b1['y_min'])
    a2 = (b2['x_max'] - b2['x_min']) * (b2['y_max'] - b2['y_min'])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _merge_hires(base: list, hires: list, iou_thresh: float = 0.3) -> list:
    """
    1차(저배율) 결과(base)에 고배율 재OCR 결과(hires)를 '고배율 우선'으로 병합.
    - 겹치는 박스: 고배율 텍스트가 더 길거나 신뢰도 높으면 교체 (작은 한글 주소 보존)
    - 겹치지 않는 박스: 새 탐지로 추가 (1차가 놓친 작은 주소 등)
    """
    merged = list(base)
    for hb in hires:
        ov = None
        for i, bb in enumerate(merged):
            if _box_iou(bb, hb) >= iou_thresh:
                ov = i
                break
        if ov is None:
            merged.append(hb)
        elif len(hb['text']) >= len(merged[ov]['text']) or hb['prob'] > merged[ov]['prob']:
            merged[ov] = hb
    return merged


def _dedup_boxes(boxes: list, ov_thr: float = 0.5, txt_thr: float = 0.6,
                 ang_thr: float = 20.0) -> list:
    """겹치는 중복 박스 제거(같은 글자를 1차·고배율이 따로 잡은 재OCR 중복 정리).
    작은 박스가 큰 박스와 ① 공간적으로 겹치고(작은쪽 면적 기준 ov_thr 초과)
    ② 글자가 큰 박스 텍스트에 포함되며(char 비율 txt_thr 이상)
    ③ 각도가 비슷(차이 ang_thr 미만)할 때만 중복으로 보고 작은 박스를 제거한다.
    → 글자가 다른 숫자(주민번호 등)나 방향이 다른(세로) 박스는 bbox가 겹쳐도 보존."""
    def _area(b):
        return max(1, (b['x_max'] - b['x_min']) * (b['y_max'] - b['y_min']))
    def _inter(a, b):
        ix = max(0, min(a['x_max'], b['x_max']) - max(a['x_min'], b['x_min']))
        iy = max(0, min(a['y_max'], b['y_max']) - max(a['y_min'], b['y_min']))
        return ix * iy
    def _subset(small, big):
        s = [c for c in small if not c.isspace()]
        if not s:
            return 0.0
        bs = set(big)
        return sum(1 for c in s if c in bs) / len(s)
    def _adiff(a, b):
        dd = abs(a - b)
        return min(dd, 360.0 - dd)

    order = sorted(boxes, key=lambda b: -_area(b))   # 큰 박스 먼저 채택
    keep = []
    for b in order:
        dup = False
        for k in keep:
            if _inter(b, k) / min(_area(b), _area(k)) > ov_thr \
               and _subset(b['text'], k['text']) >= txt_thr \
               and _adiff(b.get('angle', 0.0), k.get('angle', 0.0)) < ang_thr:
                dup = True
                break
        if not dup:
            keep.append(b)
    return keep


# ═══════════════════════════════════════════════════════════════
# ▶ [전략 1] 프레임 샘플링 (영상 전용)
# ═══════════════════════════════════════════════════════════════
def extract_sample_frames(video_path: Path, interval_sec: float = SAMPLE_INTERVAL_SEC):
    """
    영상에서 N초당 1프레임 추출.
    반환: [(frame_idx, timestamp_sec, frame), ...], fps, total_frames
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"영상 파일을 열 수 없습니다: {video_path}")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step   = max(1, int(round(fps * interval_sec)))
    duration_sec = total_frames / fps

    print(f"  📹 {int(fps)} FPS | 총 {total_frames} 프레임 | {duration_sec:.1f}초")
    print(f"  📐 샘플링 간격: {interval_sec}초 ({frame_step} 프레임마다 1장)")

    samples, frame_idx = [], 0
    while cap.isOpened():
        if not cap.grab():   # 데이터를 읽지 않고 위치만 이동 (빠름)
            break
        if frame_idx % frame_step == 0:
            if SHARP_SELECT_ENABLED:
                # 샘플 포인트 ±window 중 가장 선명한 프레임 채택 (흔들림 구간 보정)
                best_frame, best_idx = _pick_sharpest_frame(cap, frame_idx, total_frames)
                if best_frame is not None:
                    if best_idx != frame_idx:
                        print(f"  🔍 [f{frame_idx:06d}] 선명도 보정: f{best_idx:06d}으로 교체")
                    samples.append((best_idx, best_idx / fps, best_frame))
            else:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    samples.append((frame_idx, frame_idx / fps, frame))
        frame_idx += 1

    cap.release()
    print(f"  ✅ 추출 완료: {len(samples)}장")
    return samples, fps, total_frames


def _laplacian_var(frame: np.ndarray) -> float:
    """프레임 선명도 점수 — 라플라시안 분산(높을수록 선명)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _pick_sharpest_frame(cap, center_idx: int, total_frames: int,
                         window: int = SHARP_SELECT_WINDOW):
    """center_idx ± window 중 가장 선명한 프레임 반환. (best_frame, best_idx)"""
    search_start = max(0, center_idx - window)
    search_end   = min(total_frames - 1, center_idx + window)
    best_frame, best_var, best_idx = None, -1.0, center_idx

    cap.set(cv2.CAP_PROP_POS_FRAMES, search_start)
    for si in range(search_start, search_end + 1):
        ok, sf = cap.read()
        if not ok or sf is None:
            break
        v = _laplacian_var(sf)
        if v > best_var:
            best_var, best_frame, best_idx = v, sf.copy(), si

    cap.set(cv2.CAP_PROP_POS_FRAMES, center_idx + 1)   # grab 위치 복원
    return best_frame, best_idx


# ═══════════════════════════════════════════════════════════════
# ▶ [전략 2] 로컬 텍스트 사전 필터
# ═══════════════════════════════════════════════════════════════
def has_text_in_frame(frame: np.ndarray) -> bool:
    """
    Canny 엣지 밀도로 '텍스트 있음' 여부 판단 → OCR 호출 전 사전 게이트(속도 절감).
    전체 엣지 밀도를 쓰므로 기울어진 카드번호·세로 텍스트도 감지.
    """
    small   = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
    gray    = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges   = cv2.Canny(blurred, TEXT_CANNY_LOW, TEXT_CANNY_HIGH)
    density = cv2.countNonZero(edges) / (small.shape[0] * small.shape[1])
    return density >= TEXT_DENSITY_MIN


# ═══════════════════════════════════════════════════════════════
# ▶ 유틸리티
# ═══════════════════════════════════════════════════════════════
def _angle(bbox) -> float:
    """박스 상단 엣지(tl→tr) 기울기(도)."""
    tl, tr = bbox[0], bbox[1]
    return math.degrees(math.atan2(float(tr[1]) - float(tl[1]),
                                   float(tr[0]) - float(tl[0])))


def _bbox_gap(b1: dict, b2: dict) -> float:
    """두 박스 중심거리에서 각 박스 너비 절반을 뺀 '순수 빈 공간(gap)'."""
    cx1 = (b1['x_min'] + b1['x_max']) / 2.0; cy1 = (b1['y_min'] + b1['y_max']) / 2.0
    cx2 = (b2['x_min'] + b2['x_max']) / 2.0; cy2 = (b2['y_min'] + b2['y_max']) / 2.0
    dist = math.hypot(cx2 - cx1, cy2 - cy1)
    if 'vertices' in b1 and 'vertices' in b2:
        v1, v2 = b1['vertices'], b2['vertices']
        tw1 = math.hypot(v1[0]['x'] - v1[1]['x'], v1[0]['y'] - v1[1]['y'])
        tw2 = math.hypot(v2[0]['x'] - v2[1]['x'], v2[0]['y'] - v2[1]['y'])
    else:
        tw1 = b1['x_max'] - b1['x_min']; tw2 = b2['x_max'] - b2['x_min']
    return max(0.0, dist - (tw1 + tw2) / 2.0)


def angle_gap_split(boxes: list, min_gap: float = ANGLE_GAP_SPLIT) -> list:
    """정렬된 각도 분포에 큰 갭이 있으면 강제 분리 (0도 본문 vs 13도 도장 구분)."""
    if len(boxes) < 4: return [boxes]
    angles_sorted = sorted(b['angle'] for b in boxes)
    max_gap, split_at = 0.0, None
    for i in range(1, len(angles_sorted)):
        gap = angles_sorted[i] - angles_sorted[i - 1]
        if gap > max_gap:
            max_gap, split_at = gap, (angles_sorted[i-1] + angles_sorted[i]) / 2.0
    if max_gap < min_gap: return [boxes]
    g0 = [b for b in boxes if b['angle'] <= split_at]
    g1 = [b for b in boxes if b['angle'] >  split_at]
    return [g for g in (g0, g1) if g]


class _UF:
    """Union-Find(서로소 집합) — 박스 클러스터링용."""
    def __init__(self, n):
        self.p = list(range(n))
    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a, b):
        pa, pb = self.find(a), self.find(b)
        if pa != pb:
            self.p[pa] = pb


# ═══════════════════════════════════════════════════════════════
# ▶ 문서 윤곽선 탐지 (배경색 차이 + 엣지로 서류 경계 검출)
# ═══════════════════════════════════════════════════════════════
def detect_document_contours(image: np.ndarray) -> list:
    ih, iw   = image.shape[:2]
    img_area = ih * iw

    # 전략 A: 배경색(네 모서리 중앙값) 대비 차이로 전경 마스크
    s       = max(int(min(ih, iw) * 0.08), 10)
    corners = [image[:s, :s], image[:s, -s:], image[-s:, :s], image[-s:, -s:]]
    all_px  = np.vstack([c.reshape(-1, 3) for c in corners]).astype(float)
    bg_color = np.median(all_px, axis=0)
    bg_std   = np.std(all_px, axis=0)
    diff      = np.abs(image.astype(float) - bg_color)
    dist_map  = np.max(diff, axis=2)
    thresh    = max(float(np.mean(bg_std) * 2.5), 25.0)
    fg_mask_a = (dist_map > thresh).astype(np.uint8) * 255

    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    k_open  = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    fg_mask_a = cv2.morphologyEx(fg_mask_a, cv2.MORPH_CLOSE, k_close, iterations=2)
    fg_mask_a = cv2.morphologyEx(fg_mask_a, cv2.MORPH_OPEN,  k_open,  iterations=1)

    # 전략 B: 엣지 검출
    gray      = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred   = cv2.GaussianBlur(gray, (5, 5), 0)
    edges     = cv2.Canny(blurred, 40, 120)
    k_edge    = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    fg_mask_b = cv2.dilate(edges, k_edge, iterations=2)

    fg_combined = cv2.bitwise_or(fg_mask_a, fg_mask_b)

    def _extract(mask):
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cands = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < img_area * CONTOUR_MIN_RATIO or area > img_area * CONTOUR_MAX_RATIO:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if w < CONTOUR_MIN_DIM or h < CONTOUR_MIN_DIM:
                continue
            cands.append({'x': x, 'y': y, 'w': w, 'h': h, 'area': float(area)})
        return cands

    candidates = _extract(fg_combined)
    if len(candidates) < 2: candidates = _extract(fg_mask_a)
    if len(candidates) < 2: candidates = _extract(fg_mask_b)

    candidates.sort(key=lambda r: -r['area'])
    filtered = []
    for r in candidates:
        rx0, ry0, rx1, ry1 = r['x'], r['y'], r['x']+r['w'], r['y']+r['h']
        dominated = False
        for kept in filtered:
            kx0, ky0, kx1, ky1 = kept['x'], kept['y'], kept['x']+kept['w'], kept['y']+kept['h']
            ix = max(0, min(rx1, kx1) - max(rx0, kx0))
            iy = max(0, min(ry1, ky1) - max(ry0, ky0))
            if (ix * iy) / max(r['area'], 1) > 0.75:
                dominated = True
                break
        if not dominated:
            filtered.append(r)
    return filtered


def assign_to_contours(boxes: list, contours: list) -> dict:
    """각 박스를 가장 많이 겹치는 문서 윤곽(서류)에 배정."""
    result = {i: [] for i in range(len(contours))}
    rest   = []
    for box in boxes:
        bx0, by0, bx1, by1 = box['x_min'], box['y_min'], box['x_max'], box['y_max']
        b_area = max((bx1 - bx0) * (by1 - by0), 1)
        best_ratio, best_idx = 0.0, -1
        for i, cnt in enumerate(contours):
            cx0, cy0, cx1, cy1 = cnt['x'], cnt['y'], cnt['x']+cnt['w'], cnt['y']+cnt['h']
            ix = max(0, min(bx1, cx1) - max(bx0, cx0))
            iy = max(0, min(by1, cy1) - max(by0, cy0))
            ratio = (ix * iy) / b_area
            if ratio > best_ratio:
                best_ratio, best_idx = ratio, i
        if best_ratio >= 0.3 and best_idx >= 0:
            result[best_idx].append(box)
        else:
            rest.append(box)
    final = {}
    for blist in result.values():
        if blist: final[len(final)] = blist
    if rest: final[len(final)] = rest
    return final


# ═══════════════════════════════════════════════════════════════
# ▶ 박스 주변 배경색 추출·비교 (객체 분리용 — 송장 라벨 vs 박스 구분)
# ═══════════════════════════════════════════════════════════════
def _bgr_to_lab(c) -> np.ndarray:
    """BGR 색 1개를 LAB로 변환(사람 눈에 가까운 색거리 계산용)."""
    px = np.uint8([[[int(c[0]), int(c[1]), int(c[2])]]])
    return cv2.cvtColor(px, cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)


def _color_dist(c1, c2) -> float:
    """두 BGR 색의 LAB 공간 유클리드 거리. 클수록 다른 색(다른 바탕)."""
    return float(np.linalg.norm(_bgr_to_lab(c1) - _bgr_to_lab(c2)))


def _box_bg_color(image: np.ndarray, box: dict, pad_ratio: float = None) -> tuple:
    """글자 박스 '바깥 테두리 링'의 대표 배경색(중앙값 BGR)을 추출.
    박스 내부(글자=잉크)는 제외하고 주변 바탕만 보므로, 송장 흰 라벨/갈색 박스의
    '바탕색'을 안정적으로 얻는다. 링이 비면 박스 내부 중앙값으로 대체."""
    if pad_ratio is None:
        pad_ratio = BG_RING_PAD_RATIO
    H, W = image.shape[:2]
    x0, y0, x1, y1 = box['x_min'], box['y_min'], box['x_max'], box['y_max']
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    px, py = max(3, int(bw * pad_ratio)), max(3, int(bh * pad_ratio))
    ox0, oy0 = max(0, x0 - px), max(0, y0 - py)
    ox1, oy1 = min(W, x1 + px), min(H, y1 + py)
    outer = image[oy0:oy1, ox0:ox1]
    if outer.size == 0:
        return (128.0, 128.0, 128.0)
    # 박스 내부(글자 영역)를 0으로 마스킹 → 외곽 링 픽셀만 수집
    mask = np.ones(outer.shape[:2], dtype=np.uint8)
    ix0, iy0 = max(0, x0 - ox0), max(0, y0 - oy0)
    ix1, iy1 = min(outer.shape[1], ix0 + bw), min(outer.shape[0], iy0 + bh)
    mask[iy0:iy1, ix0:ix1] = 0
    ring = outer[mask == 1]
    if ring.size == 0:
        ring = outer.reshape(-1, 3)
    med = np.median(ring.reshape(-1, 3), axis=0)
    return (float(med[0]), float(med[1]), float(med[2]))


def _box_complexity(image: np.ndarray, box: dict, pad_ratio: float = None) -> float:
    """박스를 중심으로 한 '주변 영역'의 엣지 밀도(0~1)를 계산.
    바코드/조밀 인쇄 라벨은 주변 엣지가 매우 빽빽해 값이 크고,
    손글씨/단순 배경(택배 박스)은 작다. 색이 비슷한 객체를 구분하는 보조 단서."""
    if pad_ratio is None:
        pad_ratio = COMPLEXITY_PAD_RATIO
    H, W = image.shape[:2]
    x0, y0, x1, y1 = box['x_min'], box['y_min'], box['x_max'], box['y_max']
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    px, py = max(4, int(bw * pad_ratio)), max(4, int(bh * pad_ratio))
    ox0, oy0 = max(0, x0 - px), max(0, y0 - py)
    ox1, oy1 = min(W, x1 + px), min(H, y1 + py)
    roi = image[oy0:oy1, ox0:ox1]
    if roi.size == 0:
        return 0.0
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    edges = cv2.Canny(g, 50, 150)
    return float(cv2.countNonZero(edges)) / float(edges.size)


def cluster_angle_gap(boxes: list) -> dict:
    """각도 유사 + 글자크기 유사 + 빈공간(gap) 가까운 박스끼리 한 구역으로 묶기."""
    n = len(boxes)
    if n == 0: return {}
    avg_h     = max(sum(b['h'] for b in boxes) / n, 1.0)
    gap_limit = avg_h * GAP_MULT * 0.8
    uf        = _UF(n)
    for i in range(n):
        for j in range(i + 1, n):
            b1, b2 = boxes[i], boxes[j]
            adiff  = abs(b1['angle'] - b2['angle'])
            adiff  = min(adiff, 360.0 - adiff)
            if adiff >= ANGLE_THRESH: continue
            # [객체 분리] 주변 배경색이 크게 다르면 다른 객체(송장 흰 라벨 vs 갈색 박스) → 병합 차단.
            # 단, 단어끼리 매우 가까우면(문장/단어 연속) 스탬프 겹침 등으로 색이 변해도 병합 허용.
            if BG_COLOR_ENABLED and ('bg_color' in b1) and ('bg_color' in b2):
                if _bbox_gap(b1, b2) > avg_h * 1.5:  # 가까이 붙은 단어는 색상 무시
                    if _color_dist(b1['bg_color'], b2['bg_color']) > BG_COLOR_THRESH: continue
            # [객체 분리·보조] 주변 복잡도가 크게 다르면 다른 객체(바코드 라벨 vs 손글씨) → 병합 차단.
            #   색이 비슷해 색상 조건으로 못 거른 경계(택배 박스≈흰 라벨)를 복잡도로 구분.
            #   (가까이 붙어 있어도 적용 — 라벨 옆 손글씨를 떼어내기 위함)
            if COMPLEXITY_ENABLED and ('complexity' in b1) and ('complexity' in b2):
                if abs(b1['complexity'] - b2['complexity']) > COMPLEXITY_THRESH: continue
            # 글자 높이가 40% 이상 다르면 다른 객체로 간주(배경 서류 등) → 병합 차단 (단, 점. 이나 짧은기호 예외처리 가능하도록 완화)
            h_ratio = min(b1['h'], b2['h']) / max(b1['h'], b2['h'])
            if h_ratio < 0.4: continue
            cx1 = (b1['x_min'] + b1['x_max']) / 2.0; cy1 = (b1['y_min'] + b1['y_max']) / 2.0
            cx2 = (b2['x_min'] + b2['x_max']) / 2.0; cy2 = (b2['y_min'] + b2['y_max']) / 2.0
            # 수직 1.8줄 또는 수평 4배 폭 이상 빈공간이면 '징검다리' 병합 차단
            gap_y = abs(cy2 - cy1) - (b1['h']/2 + b2['h']/2)
            gap_x = abs(cx2 - cx1) - ((b1['x_max']-b1['x_min'])/2 + (b2['x_max']-b2['x_min'])/2)
            if gap_y > avg_h * 1.8 or gap_x > avg_h * 4.0: continue
            if _bbox_gap(b1, b2) < gap_limit: uf.union(i, j)
    clusters = defaultdict(list)
    for i, box in enumerate(boxes):
        clusters[uf.find(i)].append(box)
    valid = sorted([bs for bs in clusters.values() if bs],
                   key=lambda bs: (min(b['y_min'] for b in bs), min(b['x_min'] for b in bs)))
    return {rid: cl for rid, cl in enumerate(valid)}


def _cluster_group(boxes: list) -> dict:
    final = {}
    for og in angle_gap_split(boxes):
        for sboxes in cluster_angle_gap(og).values():
            final[len(final)] = sboxes
    return final


def build_regions(image: np.ndarray, boxes: list) -> tuple:
    """문서 윤곽이 2개 이상이면 서류별로 먼저 나눈 뒤 구역 클러스터링."""
    # [객체 분리] 각 박스의 주변 배경색을 미리 계산해 부여 → 클러스터링 시 '같은 바탕'끼리만 묶이게.
    if BG_COLOR_ENABLED:
        for b in boxes:
            b['bg_color'] = _box_bg_color(image, b)
    # [객체 분리·보조] 각 박스의 주변 복잡도(엣지 밀도)도 부여 → 색이 비슷해도 복잡도로 구분.
    if COMPLEXITY_ENABLED:
        for b in boxes:
            b['complexity'] = _box_complexity(image, b)
    doc_contours = detect_document_contours(image)
    if len(doc_contours) >= 2:
        final = {}
        for cboxes in assign_to_contours(boxes, doc_contours).values():
            for rboxes in _cluster_group(cboxes).values():
                final[len(final)] = rboxes
        return final, doc_contours
    return _cluster_group(boxes), doc_contours


# ═══════════════════════════════════════════════════════════════
# ▶ 텍스트 조립 (구역 내 박스를 각도 방향으로 투영해 줄 단위 문장으로)
# ═══════════════════════════════════════════════════════════════
def assemble_text(region_boxes: list) -> str:
    """대각선/세로쓰기도 기울기 벡터에 투영해 한 줄로 정렬 후 문장 조립."""
    if not region_boxes: return ""
    med_angle = float(np.median([b['angle'] for b in region_boxes]))
    rad   = math.radians(med_angle)
    v_dir = np.array([math.cos(rad), math.sin(rad)])   # 글자 진행 방향
    o_dir = np.array([-math.sin(rad), math.cos(rad)])  # 줄 바뀜 방향
    for b in region_boxes:
        c_vec = np.array([(b['x_min']+b['x_max'])/2, (b['y_min']+b['y_max'])/2])
        b['_proj_y'] = float(np.dot(c_vec, o_dir))
        b['_proj_x'] = float(np.dot(c_vec, v_dir))
    region_boxes.sort(key=lambda b: b['_proj_y'])
    avg_h = sum(b['h'] for b in region_boxes) / len(region_boxes)
    lines = [[region_boxes[0]]]
    for b in region_boxes[1:]:
        prev_line = lines[-1]
        prev_y    = sum(x['_proj_y'] for x in prev_line) / len(prev_line)
        is_same   = abs(b['_proj_y'] - prev_y) < max(avg_h * 0.8, 8.0)
        if is_same:  # Y축이 같아도 X축으로 이미 배치된 단어와 겹치면 다른 줄
            b_left  = b['_proj_x'] - (b['x_max']-b['x_min'])/2
            b_right = b['_proj_x'] + (b['x_max']-b['x_min'])/2
            for p in prev_line:
                p_left  = p['_proj_x'] - (p['x_max']-p['x_min'])/2
                p_right = p['_proj_x'] + (p['x_max']-p['x_min'])/2
                overlap = max(0, min(b_right, p_right) - max(b_left, p_left))
                if overlap > min(b_right-b_left, p_right-p_left) * 0.3:
                    is_same = False
                    break
        if is_same:
            lines[-1].append(b)
        else:
            lines.append([b])

    # 1) 각 줄을 읽기순(X축)으로 정렬하고, 간격이 너무 넓으면(컬럼 간격) 분리
    final_lines = []
    for ln in lines:
        ln.sort(key=lambda b: b['_proj_x'])
        avg_h = np.mean([b['h'] for b in ln])
        split_ln = [ln[0]]
        for b in ln[1:]:
            prev_b = split_ln[-1]
            dist_x = b['_proj_x'] - prev_b['_proj_x']
            gap = dist_x - ((prev_b['x_max'] - prev_b['x_min'])/2 + (b['x_max'] - b['x_min'])/2)
            if gap > avg_h * 2.5:  # 간격이 넓으면 분리
                final_lines.append(split_ln)
                split_ln = [b]
            else:
                split_ln.append(b)
        final_lines.append(split_ln)

    # 2) 분리된 줄(Sub-line)들을 수직으로 겹치는 '블록(단락)'으로 묶기
    blocks = []
    for ln in final_lines:
        min_x = min(b['_proj_x'] - (b['x_max'] - b['x_min'])/2 for b in ln)
        max_x = max(b['_proj_x'] + (b['x_max'] - b['x_min'])/2 for b in ln)
        avg_y = sum(b.get('_proj_y', b['y_center']) for b in ln) / len(ln)
        avg_h = np.mean([b['h'] for b in ln])

        placed = False
        for blk in reversed(blocks):
            b_min_x, b_max_x, b_max_y = blk['min_x'], blk['max_x'], blk['max_y']
            overlap_x = max(0, min(max_x, b_max_x) - max(min_x, b_min_x))
            width1 = max_x - min_x; width2 = b_max_x - b_min_x
            # X축으로 10% 이상 겹치거나 포함되고, Y축 거리가 너무 멀지 않을 때 (5줄 이내)
            if overlap_x > min(width1, width2) * 0.1 and (avg_y - b_max_y) < avg_h * 5.0:
                blk['lines'].append((avg_y, ln))
                blk['min_x'] = min(blk['min_x'], min_x)
                blk['max_x'] = max(blk['max_x'], max_x)
                blk['max_y'] = max(blk['max_y'], avg_y)
                blk['min_y'] = min(blk['min_y'], avg_y)
                placed = True
                break
        if not placed:
            blocks.append({
                'lines': [(avg_y, ln)],
                'min_x': min_x, 'max_x': max_x,
                'min_y': avg_y, 'max_y': avg_y
            })

    # 3) 블록 정렬: 비슷한 Y(2.5줄 높이 이내)면 X좌표 우선, 다르면 Y좌표 우선 (Top-to-Bottom, Left-to-Right)
    global_avg_h = np.mean([b['h'] for b in region_boxes])
    blocks.sort(key=lambda blk: (int(blk['min_y'] / (global_avg_h * 2.5)), blk['min_x']))

    # 4) 정렬된 블록 내에서 문자열 조립
    assembled = []
    for blk in blocks:
        blk['lines'].sort(key=lambda x: x[0])  # 블록 내에서는 Y좌표 순(위에서 아래)
        for _, ln in blk['lines']:
            line_str, prev_b = "", None
            for b in ln:
                if prev_b:
                    dist_x = b['_proj_x'] - prev_b['_proj_x']
                    gap = dist_x - ((prev_b['x_max'] - prev_b['x_min'])/2 + (b['x_max'] - b['x_min'])/2)
                    avg_ch_w = max(4.0, (prev_b['x_max']-prev_b['x_min']) / max(1, len(prev_b['text'])))
                    line_str += "  " if gap > avg_ch_w * 1.5 else (" " if gap > avg_ch_w * 0.5 else "")
                line_str += b['text']
                prev_b = b
            assembled.append(line_str)
        # 블록 간 구분을 위해 빈 줄 추가 (선택적)
        # assembled.append("")

    return "\n".join(assembled)


# ═══════════════════════════════════════════════════════════════
# ▶ dHash 중복 프레임 제거 (영상 전용)
# ═══════════════════════════════════════════════════════════════
def dhash(img: np.ndarray, hash_size: int = 9) -> int:
    """9×8 차분 해시 → 64비트 정수 (인접 프레임 중복 판단용)."""
    resized = cv2.resize(img, (hash_size + 1, hash_size))
    gray    = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else resized
    diff    = gray[:, 1:] > gray[:, :-1]
    return int(sum(int(bit) << i for i, bit in enumerate(diff.flatten())))


def hamming(h1: int, h2: int) -> int:
    """두 해시 간 비트 차이 수."""
    return bin(h1 ^ h2).count('1')


# ═══════════════════════════════════════════════════════════════
# ▶ OCR 전 이미지 전처리 (CLAHE + 선명화 + 업스케일)
# ═══════════════════════════════════════════════════════════════
def enhance_frame_for_ocr(frame: np.ndarray, scale: float = None) -> tuple:
    """
    업스케일 + CLAHE(국소 대비) + 언샤프(엣지 선명화)로 인식률 향상.
    반환: (전처리 이미지, 적용 배율) — 배율은 좌표 역변환에 사용.
    """
    if scale is None:
        scale = OCR_ENHANCE_SCALE
    h, w = frame.shape[:2]
    enhanced = cv2.resize(frame, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_LANCZOS4)
    lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=OCR_CLAHE_CLIP, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])   # 밝기 채널만 → 색조 변화 없음
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
    enhanced = cv2.addWeighted(enhanced, OCR_SHARP_STRENGTH,
                               gaussian, -(OCR_SHARP_STRENGTH - 1.0), 0)
    return enhanced, scale


def _to_boxes(ocr_raw: list, scale: float) -> list:
    """OCR 원시결과 [(bbox,text,prob)] → 정규화 박스 dict (좌표를 원본 기준으로 역변환)."""
    result = []
    for bbox, text, prob in ocr_raw:
        if prob < MIN_PROB or not text.strip():
            continue
        xs = [float(p[0]) / scale for p in bbox]
        ys = [float(p[1]) / scale for p in bbox]
        
        pts = np.array(bbox, dtype=np.float32) / scale
        if len(pts) >= 4:
            # 윗변(tl→tr=읽기 방향) 각도: 박스는 [tl,tr,br,bl] 순으로 만들어지므로
            #   단일 글자(정사각)도 minAreaRect처럼 90° 뒤집히지 않아 안정적이다.
            dx = float(pts[1][0] - pts[0][0]); dy = float(pts[1][1] - pts[0][1])
            a_top = math.degrees(math.atan2(dy, dx))   # 윗변(tl→tr)=읽기 방향 각도
            if a_top > 90: a_top -= 180
            elif a_top <= -90: a_top += 180
            rect = cv2.minAreaRect(pts)
            (rw, rh) = rect[1]
            # 회전 사각형 장단축 비(기울기 무관) — axis 비율은 기울어진 세로글자에서 작아져 부정확
            rect_aspect = max(rw, rh) / max(min(rw, rh), 1.0)
            a_rect = rect[-1]
            if rw < rh: a_rect += 90
            if a_rect > 90: a_rect -= 180
            elif a_rect < -90: a_rect += 180
            # 확실히 긴 텍스트 라인(장단축비 ≥ 2.5)만 minAreaRect 각도 신뢰(세로쓰기 보존).
            #   짧거나 정사각/좁은 단일 글자는 minAreaRect가 90° 뒤집히므로 윗변(읽기방향) 각도 사용
            #   (예: '구' 8x18 회전비 2.25 → 윗변 0° → 가로줄 '북구'와 합쳐짐).
            angle = a_rect if rect_aspect >= 2.5 else a_top
        elif len(pts) >= 3:
            rect = cv2.minAreaRect(pts)
            angle = rect[-1]
            if rect[1][0] < rect[1][1]:  # width < height
                angle += 90
            if angle > 90: angle -= 180
            elif angle < -90: angle += 180
        else:
            angle = 0.0
            
        result.append({
            'x_min': int(min(xs)), 'x_max': int(max(xs)),
            'y_min': int(min(ys)), 'y_max': int(max(ys)),
            'y_center': (min(ys) + max(ys)) / 2.0,
            'h': max(ys) - min(ys),
            'w': max(xs) - min(xs),
            'text': text,
            'angle': angle,
            'prob': prob,
            'vertices': [{'x': int(round(x)), 'y': int(round(y))} for x, y in zip(xs, ys)],
        })
    return result


# ═══════════════════════════════════════════════════════════════
# ▶ OCR 코어 — 한 장(이미지/프레임)에서 박스 추출 (이미지·영상 공용)
# ═══════════════════════════════════════════════════════════════
def ocr_extract_boxes(frame: np.ndarray, tag: str = "") -> list:
    """
    한 장의 이미지에서 OCR 박스를 추출(전처리 → 1차 OCR → 조건부 고배율 재OCR).
    이미지/영상 프레임 모두 이 함수를 공유합니다.
    """
    # 1) 전처리 후 1차 OCR
    if OCR_ENHANCE_ENABLED:
        ocr_frame, ocr_scale = enhance_frame_for_ocr(frame)
    else:
        ocr_frame, ocr_scale = frame, 1.0
    boxes = _to_boxes(paddle_ocr(ocr_frame), ocr_scale)
    print(f"    📋 [{tag}] 1차 OCR: {len(boxes)}개")

    # 2) 조건부 고배율 재OCR: (한글 문서성 OR 도로 단서) AND 행정구역 미완성일 때만 2.0x
    if OCR_HIRES_RETRY_ENABLED:
        texts  = [b['text'] for b in boxes]
        joined = ' '.join(texts)
        kr_cnt = sum(1 for t in texts if any('가' <= c <= '힣' for c in t))
        # 신뢰도가 높더라도, 주소 단서가 있는데 시/구가 없다면(미완성 주소) 작은 글씨를 놓친 것일 수 있으므로 재OCR 시도
        has_full_region = (('시' in joined) and ('구' in joined or '군' in joined)) \
                          or ('특별시' in joined) or ('광역시' in joined)
        has_road  = any(k in joined for k in ('로', '길', '동', '읍', '면', '번지', '호', '아파트', '빌딩', '타워'))
        has_shipping = any(k in joined for k in ('택배', '송장', '배송', '보내는', '받는', '운송장', '우체국', '고객', '주문', '수령'))
        is_kr_doc = (len(boxes) >= OCR_HIRES_BOX_MIN and kr_cnt >= OCR_HIRES_KR_MIN)
        
        # 도로명 단서가 있거나, 한글 문서이면서 택배/송장 단서가 있는 경우에만 재OCR (일반 뉴스/카드 오탐 방지)
        if (has_road or (is_kr_doc and has_shipping)) and not has_full_region:

            print(f"    🔬 [{tag}] 한글 문서/주소 단서 → {OCR_HIRES_SCALE}x 재OCR")
            # 메모리 폭주(멈춤 현상) 방지를 위해 최대 해상도 제한 (최대 변 3840px = 4K 급)
            h, w = frame.shape[:2]
            target_scale = OCR_HIRES_SCALE
            if max(h, w) * target_scale > 3840:
                target_scale = 3840 / max(h, w)
                
            hi_frame = cv2.resize(frame, (int(w * target_scale), int(h * target_scale)),
                                  interpolation=cv2.INTER_LANCZOS4)
            boxes_hi = _to_boxes(paddle_ocr(hi_frame), target_scale)
            before   = len(boxes)
            boxes    = _merge_hires(boxes, boxes_hi)   # 고배율 우선(작은 주소 보존)
            print(f"    🔬 [{tag}] 재OCR 병합: {before}개 → {len(boxes)}개")

    # 3) 겹치는 중복 박스 제거 (1차·고배율이 같은 글자를 따로 잡은 재OCR 중복 정리)
    #    → 같은 글자가 두 번 나오거나, 이름 줄의 '()' 등이 주민번호 줄에 끼어 정규식이 깨지는 문제 방지
    before = len(boxes)
    boxes = _dedup_boxes(boxes)
    if len(boxes) != before:
        print(f"    🧹 [{tag}] 중복 박스 제거: {before}개 → {len(boxes)}개")
    return boxes


# ═══════════════════════════════════════════════════════════════
# ▶ 결과 저장 — 구역 클러스터링 + 시각화/텍스트/JSON (이미지·영상 공용)
# ═══════════════════════════════════════════════════════════════
def export_result(frame: np.ndarray, boxes: list, file_tag: str, output_dir: Path,
                  source_type: str, source_name: str,
                  frame_idx=None, timestamp: float = None) -> str:
    """
    박스를 구역으로 묶고 시각화/텍스트/JSON을 저장합니다.
    이미지는 frame_idx/timestamp 가 None → JSON에 빈칸("")으로 저장.
    반환: 저장된 JSON 파일명
    """
    ih, iw = frame.shape[:2]
    regions, doc_contours = build_regions(frame, boxes)
    mode = "contour+cluster" if len(doc_contours) >= 2 else "angle+gap only"

    # ── 시각화 이미지 + 텍스트 리포트 (디버깅용, SAVE_DEBUG_OUTPUTS=True 일 때만 생성) ──
    if SAVE_DEBUG_OUTPUTS:
        vis = frame.copy()
        for cnt in doc_contours:
            cv2.rectangle(vis, (cnt['x']-2, cnt['y']-2),
                          (cnt['x']+cnt['w']+2, cnt['y']+cnt['h']+2), (200, 200, 0), 2)
        for rid, rboxes in regions.items():
            col = COLORS[rid % len(COLORS)]
            for b in rboxes:
                if 'vertices' in b and len(b['vertices']) >= 3:
                    pts = np.array([[v['x'], v['y']] for v in b['vertices']], np.int32)
                    cv2.polylines(vis, [pts], True, col, 1)
                else:
                    cv2.rectangle(vis, (b['x_min'], b['y_min']), (b['x_max'], b['y_max']), col, 1)
            rx0 = max(min(b['x_min'] for b in rboxes) - 4, 0)
            ry0 = max(min(b['y_min'] for b in rboxes) - 4, 0)
            rx1 = min(max(b['x_max'] for b in rboxes) + 4, iw - 1)
            ry1 = min(max(b['y_max'] for b in rboxes) + 4, ih - 1)
            cv2.rectangle(vis, (rx0, ry0), (rx1, ry1), col, 3)
            cv2.putText(vis, f"R{rid}", (rx0, max(ry0-6, 16)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2, cv2.LINE_AA)
        if source_type == "video":
            label = f"[PaddleOCR] {int(timestamp//60):02d}:{timestamp%60:05.2f}  frame:{frame_idx}"
        else:
            label = f"[PaddleOCR] image: {source_name}"
        cv2.putText(vis, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        ok, enc = cv2.imencode('.jpg', vis, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if ok: enc.tofile(str(output_dir / f"region_{file_tag}.jpg"))

        with open(str(output_dir / f"text_{file_tag}.txt"), 'w', encoding='utf-8') as f:
            head = f"frame {frame_idx} | {timestamp:.3f}s" if source_type == "video" else source_name
            f.write(f"=== [PaddleOCR] {head} ===\n")
            f.write(f"size: {iw}x{ih} | mode: {mode} | regions: {len(regions)}\n\n")
            for rid, rboxes in regions.items():
                a_lo = min(b['angle'] for b in rboxes); a_hi = max(b['angle'] for b in rboxes)
                f.write(f"--- Region {rid} [{len(rboxes)} boxes] angle {a_lo:.1f}~{a_hi:.1f}\n")
                txt = assemble_text(rboxes)
                for line in txt.split('\n'):
                    if line.strip(): f.write(f"  {line}\n")
                joined = " ".join(l.strip() for l in txt.split('\n') if l.strip())
                f.write(f"  [JOINED] {joined}\n\n")

    # ── OCR JSON (colab_pipeline_mask.py 호환: font_zones 규격) ──
    global_avg_h = sum(b['h'] for b in boxes) / len(boxes) if boxes else 1.0
    json_export = {
        "source_type":   source_type,                       # "image" / "video"
        "source_name":   source_name,
        "frame_idx":     frame_idx if source_type == "video" else "",            # 이미지는 빈칸
        "timestamp_sec": round(timestamp, 3) if source_type == "video" else "",  # 이미지는 빈칸
        "image_width":   iw,
        "image_height":  ih,
        "ocr_engine":    "paddleocr",
        "mode":          mode,
        "font_zones":    [],
    }
    for rid, rboxes in regions.items():
        angles   = [b['angle'] for b in rboxes]
        a_med    = float(np.median(angles)); a_spread = max(angles) - min(angles)
        avg_h_z  = sum(b['h'] for b in rboxes) / len(rboxes)
        if a_spread >= ANGLE_GAP_SPLIT and abs(a_med) > 5: font_type = "기울어진 인감/스탬프 서체 영역"
        elif abs(a_med) <= 1.5:  font_type = "수평 정렬 출력 서체 영역"
        elif abs(a_med) <= 5:    font_type = "소량 기울어진 서체 영역"
        else:                    font_type = "고각도 회전 서체 영역"
        if avg_h_z > global_avg_h * 1.6:   size_desc = "대형 제목/헤더"
        elif avg_h_z < global_avg_h * 0.7: size_desc = "소형 주석/보조 텍스트"
        else:                              size_desc = "본문 일반 텍스트"
        contour_desc = " (외곽 경계 내부 구역)" if len(doc_contours) >= 2 else ""
        json_export["font_zones"].append({
            "zone_id":      rid,
            "zone_comment": f"Zone {rid}: {font_type} — {size_desc}{contour_desc}",
            "boxes": [{
                "text": b['text'], "x_min": b['x_min'], "y_min": b['y_min'],
                "x_max": b['x_max'], "y_max": b['y_max'],
                "angle": round(b['angle'], 2), "vertices": b.get('vertices'),
                # ── 수정사항(1차) 추가 컬럼 ──
                # is_pii: 개인정보 유/무. OCR 단계에선 정규식을 모르므로 일단 False.
                #         → report 단계의 index 병합 때 정규식 탐지로 True/False 확정.
                # is_selected: 사용자선택 유/무. 선택 전이므로 전부 False.
                #         → 흐름4(미리보기 버튼) 때 백엔드가 선택된 박스만 True 로 변경.
                "is_pii": False,
                "is_selected": False,
            } for b in rboxes],
        })

    json_filename = f"ocr_data_{file_tag}.json"
    with open(str(output_dir / json_filename), 'w', encoding='utf-8') as f:
        json.dump(json_export, f, ensure_ascii=False, indent=2)
    print(f"    💾 [{file_tag}] 저장: {json_filename}  |  regions: {len(regions)}")
    return json_filename


# ═══════════════════════════════════════════════════════════════
# ▶ 단일 프레임 처리 (영상용 — 사전필터 + dry_run + 코어 호출)
# ═══════════════════════════════════════════════════════════════
def process_frame(frame_idx: int, timestamp: float, frame: np.ndarray,
                  video_stem: str, output_dir: Path, dry_run: bool = False) -> dict:
    frame_tag = f"f{frame_idx:06d}"
    rec = {"frame_idx": frame_idx, "timestamp_sec": round(timestamp, 3),
           "text_detected": False, "ocr_called": False, "box_count": 0, "json_path": None}

    # 사전 필터
    if TEXT_FILTER_ENABLED:
        rec["text_detected"] = has_text_in_frame(frame)
        if not rec["text_detected"]:
            print(f"    ⏭  [{frame_tag}] {timestamp:.2f}s — 텍스트 없음 (OCR 스킵)")
            return rec
    else:
        rec["text_detected"] = True

    if dry_run:
        print(f"    🔍 [{frame_tag}] {timestamp:.2f}s — 텍스트 감지 (DRY RUN: OCR 생략)")
        return rec

    # OCR 코어 + 저장
    print(f"    🔎 [{frame_tag}] {timestamp:.2f}s — OCR 실행 중...")
    rec["ocr_called"] = True
    boxes = ocr_extract_boxes(frame, frame_tag)
    rec["box_count"] = len(boxes)
    if not boxes:
        print(f"    ⚠️  [{frame_tag}] 유효 박스 없음")
        return rec
    rec["json_path"] = export_result(frame, boxes, frame_tag, output_dir,
                                     source_type="video", source_name=video_stem,
                                     frame_idx=frame_idx, timestamp=timestamp)
    return rec


# ═══════════════════════════════════════════════════════════════
# ▶ 영상 파일 처리
# ═══════════════════════════════════════════════════════════════
def process_video(video_path: Path, output_base: Path, dry_run: bool = False, progress_callback=None):
    print(f"\n{'=' * 62}")
    print(f"  🎬 영상 처리: {video_path.name}  |  엔진: PaddleOCR(CPU)")
    print(f"  ⚙️  간격 {SAMPLE_INTERVAL_SEC}s | 필터 {'ON' if TEXT_FILTER_ENABLED else 'OFF'} | DRY {'ON' if dry_run else 'OFF'}")
    print(f"{'=' * 62}")

    video_stem = video_path.stem
    output_dir = output_base / video_stem
    output_dir.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        get_paddle_engine()   # 첫 프레임 전에 엔진 준비(다운로드 완료)

    samples, fps, total_frames = extract_sample_frames(video_path, SAMPLE_INTERVAL_SEC)
    if not samples:
        print("  ❌ 추출된 프레임이 없습니다.")
        return

    index_records, ocr_call_count, skip_count, dedup_count = [], 0, 0, 0
    prev_hashes = []
    print(f"\n  📦 {len(samples)}장 처리 시작 (dHash 중복 제거 ON)...")
    for frame_idx, timestamp, frame in samples:
        # dHash 중복 프레임 스킵
        h = dhash(frame)
        if any(hamming(h, ph) <= DEDUPE_HAMMING_THRESHOLD for ph in prev_hashes[-DEDUPE_HISTORY_SIZE:]):
            dedup_count += 1
            print(f"    ⏭  [f{frame_idx:06d}] {timestamp:.2f}s — 중복 프레임 스킵")
            if progress_callback:
                progress_callback(frame_idx + 1, total_frames)
            continue
        prev_hashes.append(h)

        rec = process_frame(frame_idx, timestamp, frame, video_stem, output_dir, dry_run)
        index_records.append(rec)
        if rec["ocr_called"]:          ocr_call_count += 1
        elif not rec["text_detected"]: skip_count += 1

        if progress_callback:
            progress_callback(frame_idx + 1, total_frames)

    index_data = {
        "source_type": "video", "video_name": video_path.name, "video_stem": video_stem,
        "fps": fps, "total_frames": total_frames, "sample_interval_sec": SAMPLE_INTERVAL_SEC,
        "ocr_engine": "paddleocr", "dry_run": dry_run,
        "ocr_calls_made": ocr_call_count, "frames_skipped": skip_count,
        "frames_deduped": dedup_count, "total_sampled": len(samples), "frames": index_records,
    }
    with open(str(output_dir / "ocr_index.json"), 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"\n{'─' * 62}")
    print(f"  ✅ 완료: {video_path.name}")
    print(f"  📊 샘플 {len(samples)} | OCR {ocr_call_count} | 중복스킵 {dedup_count} | 텍스트없음 {skip_count}")
    print(f"  💾 {output_dir}")
    print(f"{'─' * 62}")


# ═══════════════════════════════════════════════════════════════
# ▶ 이미지 파일 처리 (영상의 '프레임 1장'과 동일한 OCR 코어 사용)
# ═══════════════════════════════════════════════════════════════
def process_image(img_path: Path, output_base: Path):
    """
    이미지 1장 처리. 프레임/재생시간 개념이 없으므로 JSON의 frame_idx·timestamp는 빈칸.
    사전 텍스트 필터/선명도 선택/중복 제거는 '1장'이라 불필요 → 바로 OCR.
    """
    print(f"\n{'=' * 62}")
    print(f"  🖼  이미지 처리: {img_path.name}  |  엔진: PaddleOCR(CPU)")
    print(f"{'=' * 62}")

    # 한글 경로 호환 위해 imdecode 사용
    arr   = np.fromfile(str(img_path), np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        print("  ❌ 이미지 로드 실패")
        return

    img_stem   = img_path.stem
    output_dir = output_base / img_stem
    output_dir.mkdir(parents=True, exist_ok=True)
    get_paddle_engine()

    ih, iw = image.shape[:2]
    print(f"  size: {iw}x{ih}")
    boxes = ocr_extract_boxes(image, img_stem)
    if not boxes:
        print("  ⚠️  유효 박스 없음")
        return
    export_result(image, boxes, img_stem, output_dir,
                  source_type="image", source_name=img_path.name)
    print(f"  ✅ 완료: {img_path.name}  |  💾 {output_dir}")


# ═══════════════════════════════════════════════════════════════════════════════
# 이 파일은 colab_pipeline_mask.py가 import해서 사용하는 'OCR 함수 모듈'입니다.
# 단독 실행 진입점(__main__)은 두지 않습니다 — 실행/경로는 colab_pipeline_mask.py에서.
#   외부 호출 함수:  process_image(img_path, output_base)
#                    process_video(video_path, output_base, dry_run=False)
# ═══════════════════════════════════════════════════════════════════════════════
