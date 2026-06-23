"""
상세보기 파이프라인 — 로컬 CPU 전용 (torch/LaMa 불필요)
merger 완료 직후 자동 호출 → PII 박스 오버레이 이미지/영상 미리 생성 (output_file/)
colab_pipeline_mask.py 에서 상세보기 전용 코드 분리 (마스킹은 mask.py 유지)
"""

import os
import sys
import json
import math
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

# ── 경로 설정 ──
try:
    _LOCAL_BASE = Path(__file__).parent
except NameError:
    _LOCAL_BASE = Path.cwd()

_DRIVE_BASE = Path("/content/drive/MyDrive/final_PJ_model")
BASE_DIR        = _DRIVE_BASE if _DRIVE_BASE.exists() else _LOCAL_BASE
INPUT_IMAGE_DIR = BASE_DIR / "test_image_file"
INPUT_VIDEO_DIR = BASE_DIR / "test_video_file"
OUTPUT_DIR      = BASE_DIR / "output_file"
FONT_DIR        = BASE_DIR / "fonts"
IMG_EXTS   = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
VIDEO_EXTS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm')

# ── 추적 파라미터 (mask.py와 동일 값 유지) ──
VID_MATCH_THRESH      = 0.50   # NCC 매칭 임계 — 미만이면 동일 픽셀 없음으로 판단, 추적 중지
VID_EDGE_MATCH_THRESH = 0.50   # keyframe 경계 구간(등장·퇴장) NCC 임계 — 흐릿한 구간 완화 가능
VID_REF_CORR          = 0.40   # 원본 PII와의 정규화상관 임계 — 미만이면 표류로 간주, 추적 중단
VID_REF_CORR_STREAK   = 2      # 연속 N프레임 VID_REF_CORR 미만 시 추적 중단 (순간 흐림 허용)
VID_FULL_ANCHOR_RATIO = 0.8    # keyframe 단어 병합면적이 그룹 최대의 이 비율 이상일 때만 앵커 사용
VID_JUMP_RATIO        = 0.6    # 박스 이동 예측: 이전 속도×이 비율을 현 프레임 위치에 가산
VID_JUMP_MIN_PX       = 12.0   # 프레임 이동 하한(px) — 작은 박스의 임계 과민 방지
VID_SEARCH_RATIO      = 0.8    # 다음 프레임 탐색 여백 배율 — 높을수록 빠른 이동 박스 추적 안정
VID_DRIFT_LOCK_RATIO  = 1.5    # [오매칭·표류 방지] 앵커 원점 대비 박스 높이×N 이탈 시 오매칭 판정
VID_DRIFT_MIN_PX      = 20.0   # drift lock 최소 이탈 거리(px) — 아주 작은 박스의 오탐 방지
VID_DRIFT_RETRY_RATIO = 0.15   # 오매칭 판정 시 원점 근방 좁은 범위에서 재탐색할 여백 배율
VID_TRACK_EXPAND      = 0.40   # 추적 패치 확장 배율 — 박스 외곽에 여유 영역 포함해 매칭 정확도↑
VID_AFFINE_SCALE_MIN  = 0.6    # 어파인 변환 허용 최소 스케일 (너무 줄면 오탐)
VID_AFFINE_SCALE_MAX  = 1.7    # 어파인 변환 허용 최대 스케일 (너무 커지면 오탐)
VID_AFFINE_ANGLE_MAX  = 25.0   # 어파인 변환 최대 회전 허용각(도) — 초과 시 회전 무효화
VID_AFFINE_PREFER_ROT   = 1.0  # 회전 후보 우선순위 가중치 (클수록 회전 변환 선호)
VID_AFFINE_PREFER_SCALE = 0.02 # 스케일 후보 우선순위 가중치
VID_BLOCK_MIN_PX      = 24     # 역방향 prefetch 블록: 이 크기 미만 박스는 블록 단위 건너뜀
VID_BLOCK_MAX_N       = 8      # 역방향 prefetch 최대 블록 수 (Colab RAM 상한 제어, 64프레임/블록)
VID_BLOCK_VIS_RATIO   = 0.6    # 블록 내 유효(비제로) 픽셀 비율 임계 — 미만이면 장면 전환으로 판정
VID_EXIT_BORDER_PX    = 2      # 화면 경계에서 N px 이내면 박스 퇴장 중으로 판정
VID_EXIT_TRIGGER_BORDER = 30   # 퇴장 외삽 진입 경계(px) — 화면 끝 이 범위에 박스가 닿고 바깥 방향이면 추적 대신 외삽으로 전환(드리프트 누적 전 안정 외삽)
VID_EXIT_MIN_SPEED    = 1.0    # 퇴장 판정 최소 이동 속도(px/프레임) — 미만이면 퇴장 외삽 중단
VID_EXIT_STALL_RATIO  = 0.35   # 속도가 초기 대비 이 비율 이하로 감속되면 퇴장 외삽 중단
VID_EXIT_VEL_EMA      = 0.6    # 퇴장 속도 EMA 계수 — 클수록 과거 속도 유지, 작을수록 즉각 반응
SCENE_CUT_CORR        = 0.6    # 장면 전환 판정 히스토그램 상관도 임계 — 미만이면 새 장면으로 처리
TRACK_FPS             = 10     # 오버레이 track 다운샘플 fps (8~12 권장, 높을수록 JSON 크기↑)
TRACK_SMOOTH_EMA      = 0.0    # 상세보기 박스 시간축 평활(EMA) 계수. 0.0으로 두어 빠른 이동 시 박스가 뒤처지는(Lag) 현상 방지
OVERLAY_BOX_PAD_RATIO = 0.13   # 상세보기 표시 박스 확대 비율 — 박스가 미세하게 떨릴 때 PII 맨 앞 글자/숫자가 박스 밖으로 새는 것 방지
VID_EXIT_MAX_FILL     = 120    # 퇴장 외삽 최대 프레임 수(안전장치) — 화면 밖 완전 이탈(overlap=0) 시 자동 종료되므로 넉넉히. 과거 15·40은 느린 퇴장에서 화면 끝 도달 전에 끊겨 박스가 갑자기 사라짐
FFMPEG_CRF            = 18     # FFmpeg 영상 품질 (낮을수록 고품질·파일 크기↑, 18~23 권장)
FFMPEG_PRESET         = 'fast' # FFmpeg 인코딩 속도 (ultrafast/fast/medium, 빠를수록 파일 크기↑)

# GPU 사용 여부 (FFmpeg nvenc 에만 사용 — LaMa/torch 불필요)
try:
    import torch as _torch
    USE_GPU = _torch.cuda.is_available()
except Exception:
    USE_GPU = False


def _get_ffmpeg_bin() -> str:
    """ffmpeg 실행 파일 경로 탐색. 시스템 PATH → imageio-ffmpeg 번들 순으로 시도."""
    import shutil
    # 1순위: 시스템 PATH의 ffmpeg
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    # 2순위: imageio-ffmpeg 패키지 번들 ffmpeg (pip install imageio-ffmpeg)
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled:
            return bundled
    except Exception:
        pass
    # 3순위: Windows 일반 설치 경로 직접 탐색
    import os
    for candidate in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "ffmpeg"  # fallback — 없으면 FileNotFoundError 발생


def _check_nvenc() -> bool:
    """FFmpeg h264_nvenc(GPU 인코더) 지원 여부 확인 (1회 캐싱)."""
    if not hasattr(_check_nvenc, '_result'):
        try:
            r = subprocess.run(
                [_get_ffmpeg_bin(), '-hide_banner', '-encoders'],
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


_PII_COLORS = {
    "주민등록번호": (50, 50, 255), "외국인등록번호": (50, 50, 255),
    "전화번호": (50, 255, 50), "주소": (255, 150, 50),
    "카드번호": (50, 150, 255), "계좌번호": (50, 255, 255), "이메일": (255, 50, 150),
}
_PII_DEFAULT_COLOR = (255, 100, 255)

# 위험도 분류: high(빨강) / medium(주황) / low(파랑)
_PII_SEVERITY = {
    "주민등록번호": "high", "외국인등록번호": "high",
    "카드번호": "high", "계좌번호": "high",
    "전화번호": "medium", "주소": "medium",
    "이메일": "low", "생년월일": "low", "나이": "low",
}

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


# ═════════════════════════════════════════════════════════════════════════════
# 이미지 PII 박스 오버레이 (상세보기 이미지 생성)
# ═════════════════════════════════════════════════════════════════════════════
def draw_pii_report(image_cv, pii_groups):
    """상세보기용 PII 오버레이 이미지 생성.
    각 PII 그룹의 polygon에 색상 박스 + 라벨을 그려 반환."""
    from PIL import Image as PILImage, ImageDraw
    pil_img = PILImage.fromarray(cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = PILImage.new("RGBA", pil_img.size, (0, 0, 0, 0))
    draw    = ImageDraw.Draw(overlay)
    label_font = _load_kor_font(15)

    for g in pii_groups:
        pii_type = g['pii_type']
        bgr = _PII_COLORS.get(pii_type, _PII_DEFAULT_COLOR)
        r, gg, b = bgr[2], bgr[1], bgr[0]
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

        if first_top_left is None and g.get('bbox'):
            bx = g['bbox']
            pts = [(bx[0], bx[1]), (bx[2], bx[1]), (bx[2], bx[3]), (bx[0], bx[3])]
            draw.polygon(pts, outline=(r, gg, b, 255), fill=(r, gg, b, 50))
            first_top_left = (bx[0], bx[1])

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
# 영상 회전 메타데이터 보정
# ═════════════════════════════════════════════════════════════════════════════
_FRAME_ROT = None


def _set_frame_rot(cap, ref_w, ref_h):
    """cap 해상도가 OCR 기준(ref_w×ref_h)과 90도 어긋나면 회전코드를 전역에 설정."""
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
        return None
    if (W, H) == (ref_h, ref_w):
        meta = 0
        try:
            meta = int(cap.get(cv2.CAP_PROP_ORIENTATION_META))
        except Exception:
            meta = 0
        if meta in (270, -90):
            _FRAME_ROT = cv2.ROTATE_90_COUNTERCLOCKWISE
        else:
            _FRAME_ROT = cv2.ROTATE_90_CLOCKWISE
    return _FRAME_ROT


def _rot_read(cap):
    """cap.read() + 전역 회전 보정 적용."""
    ret, frame = cap.read()
    if ret and _FRAME_ROT is not None:
        frame = cv2.rotate(frame, _FRAME_ROT)
    return ret, frame


# ═════════════════════════════════════════════════════════════════════════════
# NCC 픽셀 추적 헬퍼
# ═════════════════════════════════════════════════════════════════════════════
def _is_scene_cut(prev_frame, cur_frame) -> bool:
    """연속 두 프레임이 장면 전환인지 히스토그램 상관도로 판정."""
    a = cv2.cvtColor(cv2.resize(prev_frame, (64, 36)), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cv2.resize(cur_frame, (64, 36)), cv2.COLOR_BGR2GRAY)
    ha = cv2.calcHist([a], [0], None, [32], [0, 256])
    hb = cv2.calcHist([b], [0], None, [32], [0, 256])
    cv2.normalize(ha, ha); cv2.normalize(hb, hb)
    return cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL) < SCENE_CUT_CORR


def _ref_patch(frame, bbox, size: int = 48):
    """프레임의 bbox 영역을 그레이 48×48 패치로 추출(원본 PII 외형 기준). 없으면 None."""
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
    """두 그레이 패치의 정규화 상관계수 (-1~1). 추적 표류 검증용."""
    if a is None or b is None:
        return 1.0
    af = a.astype(np.float32); bf = b.astype(np.float32)
    af -= af.mean(); bf -= bf.mean()
    denom = (np.sqrt((af * af).sum()) * np.sqrt((bf * bf).sum()))
    return float((af * bf).sum() / denom) if denom > 1e-6 else 0.0


def _bbox_quad_from_boxes(boxes: list):
    """추적된 박스들 → (axis bbox, 개별 단어 quads 리스트). 오버레이 표시용."""
    pts = []; quads = []
    for b in boxes:
        if b.get('vertices') and len(b['vertices']) >= 3:
            q = [(p['x'], p['y']) for p in b['vertices']]
            pts += q; quads.append(q)
        elif 'x_min' in b:
            q = [(b['x_min'], b['y_min']), (b['x_max'], b['y_min']),
                 (b['x_max'], b['y_max']), (b['x_min'], b['y_max'])]
            pts += q; quads.append(q)
    if not pts:
        return None, None
    arr = np.array(pts, dtype=np.float32)
    return [int(arr[:, 0].min()), int(arr[:, 1].min()),
            int(arr[:, 0].max()), int(arr[:, 1].max())], quads


def _merge_boxes_to_quad(boxes: list):
    """단어 박스들을 감싸는 최소 회전 사각형(minAreaRect)으로 병합.
    기울어진 PII 전체를 딱 맞게 감싸는 박스 1개로 표시."""
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
    rect = cv2.minAreaRect(arr)
    quad = cv2.boxPoints(rect)
    x1, y1 = int(arr[:, 0].min()), int(arr[:, 1].min())
    x2, y2 = int(arr[:, 0].max()), int(arr[:, 1].max())
    return [x1, y1, x2, y2], [[float(p[0]), float(p[1])] for p in quad]


def _drop_container_boxes(boxes: list, pad: int = 3):
    """다른 박스 여러 개를 감싸는 컨테이너 박스를 제외하고 단어별 박스만 남긴다."""
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
            continue
        keep.append(b)
    return keep if keep else boxes


def _shift_boxes(boxes: list, dx: int, dy: int) -> list:
    """박스 전체를 (dx,dy) 평행이동."""
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
    """아핀 변환 M을 박스 꼭짓점에 적용 — 회전·크기·이동."""
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


def _vid_affine_sane(M) -> bool:
    """추정 변환이 1프레임 변화로 타당한지(스케일/회전 범위 내) 확인."""
    a, b = float(M[0, 0]), float(M[0, 1])
    scale = (a*a + b*b) ** 0.5
    angle = abs(math.degrees(math.atan2(b, a)))
    return VID_AFFINE_SCALE_MIN <= scale <= VID_AFFINE_SCALE_MAX and angle <= VID_AFFINE_ANGLE_MAX


def _vid_ncc_probe(prev_frame, cur_frame, sub_bbox: tuple, search_ratio: float):
    """sub_bbox 픽셀을 템플릿으로 cur_frame 근방에서 최유사 위치 탐색. 반환 (dx,dy,score) or None."""
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
    """bbox가 화면(0~W,0~H) 안에 보이는 면적 비율(0~1)."""
    x1, y1, x2, y2 = bbox
    a = (x2 - x1) * (y2 - y1)
    if a <= 0:
        return 0.0
    ix1, iy1 = max(0, x1), max(0, y1)
    ix2, iy2 = min(W, x2), min(H, y2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1) / a


def _split_blocks(bbox: tuple) -> list:
    """긴 텍스트 bbox를 긴 축 방향으로 N등분한 블록 bbox 리스트로 분할."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    w, h = x2 - x1, y2 - y1
    blocks = []
    if w >= h:
        n = max(2, min(VID_BLOCK_MAX_N, w // VID_BLOCK_MIN_PX))
        for k in range(n):
            bx1 = x1 + w * k // n; bx2 = x1 + w * (k + 1) // n
            blocks.append((bx1, y1, bx2, y2))
    else:
        n = max(2, min(VID_BLOCK_MAX_N, h // VID_BLOCK_MIN_PX))
        for k in range(n):
            by1 = y1 + h * k // n; by2 = y1 + h * (k + 1) // n
            blocks.append((x1, by1, x2, by2))
    return blocks


def _vid_match_shift(prev_frame, cur_frame, bbox: tuple, search_ratio: float, thresh: float):
    """① 전체 매칭 ② N등분 블록 매칭→affine ③ 모두 미달→None."""
    H, W = prev_frame.shape[:2]
    full = _vid_ncc_probe(prev_frame, cur_frame, bbox, search_ratio)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    affine_res, best = None, None
    if not ((x2 - x1) < 16 and (y2 - y1) < 16):
        pts_src, pts_dst = [], []
        for blk in _split_blocks(bbox):
            if _screen_vis_ratio(blk, W, H) < VID_BLOCK_VIS_RATIO:
                continue
            p = _vid_ncc_probe(prev_frame, cur_frame, blk, search_ratio)
            if p is None or p[2] < thresh:
                continue
            cx = (blk[0] + blk[2]) / 2.0; cy = (blk[1] + blk[3]) / 2.0
            pts_src.append((cx, cy)); pts_dst.append((cx + p[0], cy + p[1]))
            if best is None or p[2] > best[2]:
                best = p
        if len(pts_src) >= 2:
            src = np.array(pts_src, dtype=np.float32); dst = np.array(pts_dst, dtype=np.float32)
            M, _inl = cv2.estimateAffinePartial2D(src, dst)
            if M is not None and _vid_affine_sane(M):
                affine_res = ('affine', M)
    if affine_res is not None:
        M = affine_res[1]
        rot = abs(math.degrees(math.atan2(float(M[1, 0]), float(M[0, 0]))))
        scl = (float(M[0, 0]) ** 2 + float(M[1, 0]) ** 2) ** 0.5
        if rot >= VID_AFFINE_PREFER_ROT or abs(scl - 1.0) >= VID_AFFINE_PREFER_SCALE:
            return affine_res
    if full is not None and full[2] >= thresh:
        return ('shift', full[0], full[1])
    if affine_res is not None:
        return affine_res
    if best is not None:
        return ('shift', best[0], best[1])
    return None


def _bbox_screen_overlap(bbox, W: int, H: int) -> float:
    """bbox가 화면(0~W,0~H)과 겹치는 면적. 0이면 화면 밖."""
    x1, y1, x2, y2 = bbox
    ix1, iy1 = max(0, x1), max(0, y1)
    ix2, iy2 = min(W, x2), min(H, y2)
    return max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)


def _is_exiting(bbox, vel, W: int, H: int, border: int) -> bool:
    """박스가 경계에 닿아 있고 그 바깥 방향으로 움직이는 중이면 True."""
    x1, y1, x2, y2 = bbox
    vx, vy = vel
    return ((x1 <= border and vx < -0.3) or (x2 >= W - border and vx > 0.3)
            or (y1 <= border and vy < -0.3) or (y2 >= H - border and vy > 0.3))


def _exit_extrapolate(base_boxes, base_bbox, vel, fi, direction,
                      limit_fi, total_frames, W, H, record_fn) -> int:
    """경계 퇴장 후 마지막 속도로 박스를 외삽하며 record_fn 기록. 반환: 외삽 프레임 수."""
    vx, vy = vel
    if (vx * vx + vy * vy) ** 0.5 < VID_EXIT_MIN_SPEED:
        return 0
    ox = oy = 0.0
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
            break
        eboxes = _shift_boxes(base_boxes, int(round(ox)), int(round(oy)))
        record_fn(nfi, eboxes, ebbox)
        filled += 1
        if filled >= VID_EXIT_MAX_FILL:  # 무한 외삽 방지 — 단, 화면 밖 완전 이탈까지는 따라가도록 한도 상향
            break
    return filled


def _expand_bbox(bbox, ratio: float):
    """bbox를 중심 기준 ratio 만큼 확장."""
    x1, y1, x2, y2 = bbox
    dx = (x2 - x1) * ratio / 2.0
    dy = (y2 - y1) * ratio / 2.0
    return (x1 - dx, y1 - dy, x2 + dx, y2 + dy)


def _expand_boxes(boxes: list, ratio: float):
    """각 박스를 중심 기준 ratio 만큼 확장."""
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


def _pad_quad(quad, ratio: float):
    """quad(4점)를 중심 기준 ratio 만큼 확대 — 표시 박스가 PII를 살짝 여유 있게 감싸도록."""
    arr = np.array(quad, dtype=np.float32)
    c = arr.mean(axis=0)
    out = c + (arr - c) * (1.0 + ratio)
    return [[float(x), float(y)] for x, y in out]


def _smooth_track(pts: list, ema: float, ref_wh=None) -> list:
    """상세보기 트랙의 bbox를 EMA 평활하여 떨림 제거.
    ref_wh=(w,h)가 주어지면 크기를 키프레임 기준으로 고정하고 중심점만 평활 — 박스 크기 불일치 방지."""
    if not pts:
        return pts
    if ref_wh is not None:
        # 크기 고정 모드: 중심점만 EMA 평활
        rw, rh = ref_wh
        sx = float((pts[0]['bbox'][0] + pts[0]['bbox'][2]) / 2.0)
        sy = float((pts[0]['bbox'][1] + pts[0]['bbox'][3]) / 2.0)
        for p in pts:
            cx = (p['bbox'][0] + p['bbox'][2]) / 2.0
            cy = (p['bbox'][1] + p['bbox'][3]) / 2.0
            if ema > 0:
                sx = ema * sx + (1 - ema) * cx
                sy = ema * sy + (1 - ema) * cy
            else:
                sx, sy = cx, cy
            p['bbox'] = [int(sx - rw / 2), int(sy - rh / 2),
                         int(sx + rw / 2), int(sy + rh / 2)]
    else:
        sb = [float(v) for v in pts[0]['bbox']]
        for p in pts:
            if ema > 0:
                for i in range(4):
                    sb[i] = ema * sb[i] + (1 - ema) * p['bbox'][i]
                p['bbox'] = [int(round(v)) for v in sb]
    return pts


# ═════════════════════════════════════════════════════════════════════════════
# 상세보기 오버레이 트랙 생성 (_track_one_dir + _build_overlay_tracks)
# ═════════════════════════════════════════════════════════════════════════════
def _track_one_dir(cap, start_fi, boxes, bbox, direction, limit_fi, total_frames, frames: dict,
                   match_thresh=VID_MATCH_THRESH, anchor_bbox=None, exit_frames=None):
    """start_fi에서 한 방향(+1/-1)으로 픽셀 추적하며 frames[fi]=추적된 boxes 기록(마스킹 없음).
    exit_frames(set)가 주어지면 퇴장 외삽으로 채운 프레임 번호를 모아둔다 — 다운샘플에서 이 프레임을
    버리지 않고 살려야 화면 밖까지 박스가 끊김 없이 따라 나간다."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_fi)
    ret, prev = _rot_read(cap)
    if not ret:
        return
    H, W = prev.shape[:2]
    cur_boxes, cur_bbox, fi = boxes, bbox, start_fi
    vx, vy = 0.0, 0.0

    # 역방향 블록 prefetch — seek 횟수 1/64로 감소
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

    # 가까운 앵커 우선 기록
    def _rec(f, b):
        d = abs(f - start_fi)
        e = frames.get(f)
        if e is None or d < e[1]:
            frames[f] = (b, d)

    # 퇴장 외삽 전용 기록 — _rec 기록 + 외삽 프레임 번호를 exit_frames에 표시(다운샘플 보존용)
    def _exit_rec(f, b, bb):
        _rec(f, b)
        if exit_frames is not None:
            exit_frames.add(f)

    ref_patch = _ref_patch(prev, bbox)
    miss_streak = 0
    # 퇴장 외삽 기준점 — 마지막으로 corr 검증을 통과한(드리프트 적은) 박스/위치/프레임을 기억.
    # 화면 밖으로 나갈 때 이 '정상' 박스를 고정한 채 속도로만 평행이동 → 위로 뜨는 드리프트 방지.
    last_good_boxes, last_good_bbox, last_good_fi = boxes, bbox, start_fi

    while True:
        nfi = fi + direction
        if direction > 0 and nfi >= limit_fi: break
        if direction < 0 and nfi <= limit_fi: break
        if nfi < 0 or nfi >= total_frames: break
        ret, cur = _read_cur(nfi)
        if not ret: break
        res = _vid_match_shift(prev, cur, cur_bbox, VID_SEARCH_RATIO, match_thresh)
        if res is None:
            if direction > 0 and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_TRIGGER_BORDER):
                _exit_extrapolate(last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                                  limit_fi, total_frames, W, H, _exit_rec)
            break
        if res[0] == 'affine':
            new_boxes = _transform_boxes_affine(cur_boxes, res[1])
            xs = [b['x_min'] for b in new_boxes] + [b['x_max'] for b in new_boxes]
            ys = [b['y_min'] for b in new_boxes] + [b['y_max'] for b in new_boxes]
            new_bbox = (min(xs), min(ys), max(xs), max(ys))
        else:
            _, dx, dy = res
            new_boxes = _shift_boxes(cur_boxes, dx, dy)
            new_bbox = (cur_bbox[0]+dx, cur_bbox[1]+dy, cur_bbox[2]+dx, cur_bbox[3]+dy)
        # drift lock: 앵커 원점에서 허용 범위 이상 이탈 시 재탐색
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
                    new_boxes, new_bbox = cur_boxes, cur_bbox
        corr_ok = _patch_corr(ref_patch, _ref_patch(cur, new_bbox)) >= VID_REF_CORR
        if not corr_ok:
            miss_streak += 1
            if miss_streak >= VID_REF_CORR_STREAK:
                # corr 미달로 추적이 끊기는 시점이 '화면 밖 퇴장 중'이면, 마지막 정상 박스를
                # 속도로 외삽해 화면 끝까지 따라 나가게 한다(신분증이 흐려지며 끊겨 조기 종료되던 문제 해결).
                if direction > 0 and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_TRIGGER_BORDER):
                    _exit_extrapolate(last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                                      limit_fi, total_frames, W, H, _exit_rec)
                break
        else:
            miss_streak = 0
        rdx = ((new_bbox[0]+new_bbox[2]) - (cur_bbox[0]+cur_bbox[2])) / 2.0
        rdy = ((new_bbox[1]+new_bbox[3]) - (cur_bbox[1]+cur_bbox[3])) / 2.0
        speed = (vx*vx + vy*vy) ** 0.5
        cur_speed = (rdx*rdx + rdy*rdy) ** 0.5
        jump_limit = max(VID_JUMP_MIN_PX, VID_JUMP_RATIO * (cur_bbox[2] - cur_bbox[0]))
        if direction < 0 and cur_speed > jump_limit:
            break
        if direction > 0 and speed >= VID_EXIT_MIN_SPEED and _is_exiting(cur_bbox, (vx, vy), W, H, VID_EXIT_TRIGGER_BORDER):
            proj = (rdx*vx + rdy*vy) / speed
            if proj < VID_EXIT_STALL_RATIO * speed:
                _exit_extrapolate(last_good_boxes, last_good_bbox, (vx, vy), last_good_fi, direction,
                                  limit_fi, total_frames, W, H, _exit_rec)
                break
        if corr_ok:
            _rec(nfi, new_boxes)
            # 정상 추적 프레임 → 퇴장 외삽의 기준점 갱신
            last_good_boxes, last_good_bbox, last_good_fi = new_boxes, new_bbox, nfi
        vx = VID_EXIT_VEL_EMA * vx + (1 - VID_EXIT_VEL_EMA) * rdx
        vy = VID_EXIT_VEL_EMA * vy + (1 - VID_EXIT_VEL_EMA) * rdy
        cur_boxes, cur_bbox = new_boxes, new_bbox
        prev, fi = cur, nfi


def _build_overlay_tracks(video_path: Path, pii_groups: list, fps: float, total_frames: int) -> dict:
    """각 PII 그룹의 '모든 keyframe'을 앵커로 양방향 픽셀 추적 → 가까운 앵커 우선 병합 → TRACK_FPS 다운샘플.
    반환: {pii_id: [{sec, frame, bbox, quad}, ...]}  ← 프론트 오버레이용.

    [왜 모든 keyframe을 앵커로 쓰는가]
      과거에는 면적 최대 keyframe 1개만 대표 앵커로 추적했다. 하지만 신분증이 다가오다(작음→큼)
      다시 화면 밖으로 나가는 영상은 대표 앵커가 '가장 큰 = 화면 밖 직전' 시점으로 잡혀,
      그 시점 외형(ref_patch) 기준으로 시작 프레임까지 역추적하다 초반의 작고 흐린 구간에서
      VID_REF_CORR 미달로 추적이 끊겨 '시작 구간 박스 누락'이 발생했다.
      → keyframe(예: frame 0,28,58,88,118)을 '각각' 앵커로 양방향 추적하면, 시작 keyframe이
        시작부터 박스를 만들고 각 앵커가 자기 주변을 빠짐없이 커버한다. 여러 앵커가 같은 프레임을
        추적하면 _track_one_dir 의 _rec 가 'start_fi 에 더 가까운 앵커' 결과만 남긴다(표류 최소화)."""
    step = max(1, int(round(fps / max(1, TRACK_FPS))))
    tracks = {}
    cap = cv2.VideoCapture(str(video_path))
    for g in pii_groups:
        kfs = g.get('keyframes', [])
        if not kfs:
            tracks[g['pii_id']] = []; continue

        # 제일 컸던 앵커 크기 추출 (사용자가 박스 크기 고정을 원함)
        rep_size = None
        def _kf_quad_area(kf):
            _, q = _merge_boxes_to_quad(kf.get('boxes', []))
            return cv2.contourArea(np.array(q, np.float32)) if q else 0.0
        rep_kf = max(kfs, key=_kf_quad_area)
        _, rq = _merge_boxes_to_quad(rep_kf.get('boxes', []))
        if rq is not None:
            _rs = cv2.minAreaRect(np.array(rq, dtype=np.float32))[1]
            # 박스를 PII에 딱 맞추면 떨림 시 맨 앞 글자가 새므로 살짝 키워서 고정
            rep_size = (_rs[0] * (1.0 + OVERLAY_BOX_PAD_RATIO),
                        _rs[1] * (1.0 + OVERLAY_BOX_PAD_RATIO))

        frames = {}            # {fi: (boxes, 앵커와의 거리)} — _track_one_dir 가 가까운 앵커 우선으로 갱신
        kf_frames = set()      # keyframe 프레임 번호(다운샘플에서 항상 포함시키기 위함)
        exit_frames = set()    # 퇴장 외삽으로 채운 프레임 번호(다운샘플에서 보존 → 화면 밖까지 박스 유지)
        # ── 모든 keyframe을 앵커로 양방향 추적 ──
        for kf in kfs:
            kf_boxes = kf.get('boxes', [])
            kf_bbox, _ = _bbox_quad_from_boxes(kf_boxes)
            if kf_bbox is None:
                continue
            kf_frame = int(kf['frame'])
            kf_frames.add(kf_frame)
            exp_boxes = _expand_boxes(kf_boxes, VID_TRACK_EXPAND)   # 추적은 여유 확장 박스로
            exp_bbox  = _expand_bbox(tuple(kf_bbox), VID_TRACK_EXPAND)
            _track_one_dir(cap, kf_frame, exp_boxes, exp_bbox, +1, total_frames,
                           total_frames, frames, match_thresh=VID_EDGE_MATCH_THRESH,
                           anchor_bbox=kf_bbox, exit_frames=exit_frames)
            _track_one_dir(cap, kf_frame, exp_boxes, exp_bbox, -1, -1,
                           total_frames, frames, match_thresh=VID_EDGE_MATCH_THRESH,
                           anchor_bbox=kf_bbox, exit_frames=exit_frames)
        if not kf_frames:
            tracks[g['pii_id']] = []; continue
        # keyframe 위치는 OCR 원본 박스로 확정(거리 0 = 최우선 → 추적 오차 없이 정확)
        for kf in kfs:
            frames[int(kf['frame'])] = (kf.get('boxes', []), 0)

        # ── TRACK_FPS 다운샘플 (keyframe 프레임은 step 배수가 아니어도 항상 포함) ──
        sampled = []
        for fi in sorted(frames.keys()):
            # keyframe·퇴장 외삽 프레임은 step 배수가 아니어도 항상 포함(외삽 구간 끊김 방지)
            if (fi % step != 0) and (fi not in kf_frames) and (fi not in exit_frames):
                continue
            bs = frames[fi][0]
            bbox_s, quads_s = _bbox_quad_from_boxes(bs)
            if bbox_s is None:
                continue
            _, merged_quad = _merge_boxes_to_quad(bs)
            
            # 박스 크기를 최대 키프레임 크기(rep_size)로 고정하여 늘었다 줄었다 하는 현상(Jitter) 방지
            if rep_size is not None and merged_quad is not None:
                rrect_cur = cv2.minAreaRect(np.array(merged_quad, dtype=np.float32))
                cen_cur, _, ang_cur = rrect_cur
                quad_fixed = cv2.boxPoints((cen_cur, rep_size, ang_cur))
                merged_quad = [[float(x), float(y)] for x, y in quad_fixed]
                xs = [p[0] for p in quad_fixed]; ys = [p[1] for p in quad_fixed]
                bbox_s = [min(xs), min(ys), max(xs), max(ys)]
            elif merged_quad is not None:
                # rep_size 고정을 못 쓰는 경우에도 살짝 키워 앞글자 새는 것 방지
                merged_quad = _pad_quad(merged_quad, OVERLAY_BOX_PAD_RATIO)
                xs = [p[0] for p in merged_quad]; ys = [p[1] for p in merged_quad]
                bbox_s = [min(xs), min(ys), max(xs), max(ys)]

            sampled.append({
                'sec'  : round(fi / fps, 3),
                'frame': fi,
                'bbox' : bbox_s,
                'quad' : merged_quad or (quads_s[0] if quads_s else None),
            })
        # 박스 크기는 각 구간 추적값을 그대로 사용(신분증 크기 변화 반영) → 중심 떨림만 EMA 평활
        tracks[g['pii_id']] = _smooth_track(sampled, TRACK_SMOOTH_EMA)
        print(f"    🎯 [{g['pii_id']}] 오버레이 트랙 {len(sampled)}점 (앵커 {len(kf_frames)}개)")
    cap.release()
    return tracks


# ═════════════════════════════════════════════════════════════════════════════
# 상세보기 영상 렌더링 헬퍼
# ═════════════════════════════════════════════════════════════════════════════
def _quad_label_angle(q):
    """quad(4점)의 긴 변 방향 각도. 라벨을 박스와 평행하게 배치하기 위함."""
    e01 = (q[1][0] - q[0][0], q[1][1] - q[0][1])
    e12 = (q[2][0] - q[1][0], q[2][1] - q[1][1])
    e = e01 if (e01[0] ** 2 + e01[1] ** 2) >= (e12[0] ** 2 + e12[1] ** 2) else e12
    a = float(np.degrees(np.arctan2(e[1], e[0])))
    while a > 45:  a -= 90
    while a < -45: a += 90
    return a


def _put_label_pil(frame, text, quad, color):
    """PIL로 한글 레이블을 박스 왼쪽 위 코너에 배치 (이미지와 동일 방식).
    x+y가 최소인 점을 왼쪽 위 코너로 사용 — 기울어진 quad에서도 올바른 위치 보장."""
    from PIL import Image as PILImage, ImageDraw
    H, W = frame.shape[:2]
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    # x+y가 최소인 점 = 기울어진 quad의 실제 왼쪽 위 코너 (draw_pii_report와 동일 방식)
    tl = min(zip(xs, ys), key=lambda p: p[0] + p[1])
    left = int(tl[0])
    top  = int(tl[1])
    bot  = int(max(ys))

    # BGR → RGB (PIL용)
    r_ch, g_ch, b_ch = color[2], color[1], color[0]
    font = _load_kor_font(14)
    pad = 3

    try:
        lb = font.getbbox(text)
        lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    except Exception:
        lw, lh = len(text) * 9, 14

    # 박스 위에 배치, 화면 위로 벗어나면 박스 아래에
    label_y = top - lh - pad * 2 - 2
    if label_y < 0:
        label_y = bot + 2
        
    # clamp 제거: 화면 끝에 걸쳐있지 않고 박스와 함께 화면 밖으로 자연스럽게 사라지도록 함
    label_x = left

    pil_img = PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    draw.rectangle(
        [label_x, label_y, label_x + lw + pad * 2, label_y + lh + pad * 2],
        fill=(r_ch, g_ch, b_ch)
    )
    draw.text((label_x + pad, label_y + pad), text, fill=(255, 255, 255), font=font)
    frame[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _draw_box_on_frame(frame, pt: dict, g: dict):
    """영상 프레임 위에 PII 박스(quad/bbox) + 한글 라벨 그리기.
    pt['quad']는 단일 quad [[x,y]*4] 형태 (_build_overlay_tracks 에서 merged_quad 저장)."""
    color = _PII_COLORS.get(g['pii_type'], _PII_DEFAULT_COLOR)
    quad, bbox = pt.get('quad'), pt.get('bbox')
    # 영문 대신 한글 pii_type 직접 사용 — 이미지 오버레이와 동일
    seq = g.get('seq', '')
    label = g['pii_type'] + (str(seq) if seq else '')
    if quad:
        # quad는 단일 [[x,y]*4] — reshape으로 OpenCV가 요구하는 (N,1,2) 형태 변환
        cv2.polylines(frame, [np.array(quad, np.int32).reshape((-1, 1, 2))], True, color, 2)
        _put_label_pil(frame, label, quad, color)
    elif bbox:
        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
        q = [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]
        _put_label_pil(frame, label, q, color)


def _mux_audio(temp_path, video_path, final_path, audio_offset_sec=None, audio_path=None):
    """무음 임시 영상 + 원본 오디오 합성. FFmpeg 없으면 임시 파일을 그대로 복사."""
    import shutil
    audio_src = str(audio_path) if audio_path else str(video_path)
    ffmpeg_bin = _get_ffmpeg_bin()
    cmd = [ffmpeg_bin, '-y', '-i', str(temp_path)]
    if audio_offset_sec is not None:
        cmd += ['-ss', str(round(audio_offset_sec, 3))]
    # -pix_fmt yuv420p: 브라우저 H.264 재생 필수 (Chrome/Safari/Firefox 모두 요구)
    # -movflags +faststart: moov atom을 파일 앞으로 이동 → 스트리밍(206 Partial) 즉시 재생
    cmd += ['-i', audio_src, '-map', '0:v:0', '-map', '1:a:0?',
            '-c:v', 'libx264', '-preset', FFMPEG_PRESET, '-crf', str(FFMPEG_CRF),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-c:a', 'aac', '-b:a', '192k', '-shortest', str(final_path)]
    try:
        # encoding='utf-8', errors='replace': Windows cp949 기본 인코딩으로 ffmpeg stderr(한글 경로 포함)
        # 디코딩 시 UnicodeDecodeError 발생 방지 — 반드시 명시 지정 필요
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', check=False)
        if r.returncode != 0:
            print(f"  ⚠️  FFmpeg 오류(임시 파일 복사로 대체):\n{r.stderr[-300:]}")
            shutil.copy(str(temp_path), str(final_path))
        else:
            print(f"  ✅ FFmpeg H.264 인코딩 성공 → {Path(final_path).name}")
    except FileNotFoundError:
        # FFmpeg 없음 — 임시 파일(avc1이면 브라우저 재생 가능, mp4v면 불가)을 그대로 복사
        print("  ℹ️  FFmpeg 없음 → 무음 영상으로 저장 (오디오 합성 생략)")
        shutil.copy(str(temp_path), str(final_path))
    except Exception as e:
        # UnicodeDecodeError 등 기타 예외 — fallback으로 무음 파일 복사
        print(f"  ⚠️  FFmpeg 예외({type(e).__name__}): {e} → 무음 영상으로 저장")
        shutil.copy(str(temp_path), str(final_path))
    if Path(temp_path).exists():
        Path(temp_path).unlink()


def _render_overlay_video(video_path, pii_groups, tracks, fps, total, W, H, out_path):
    """원본 위에 PII 박스가 이동하는 상세보기 영상(mp4) 생성. cv2.VideoWriter 사용(FFmpeg 불필요)."""
    step = max(1, int(round(fps / max(1, TRACK_FPS))))
    group_pts = {g['pii_id']: sorted(tracks.get(g['pii_id'], []), key=lambda p: p['frame'])
                 for g in pii_groups}
    ptr  = {gid: 0 for gid in group_pts}
    last = {gid: None for gid in group_pts}

    # cv2.VideoWriter로 무음 임시 영상 생성 (FFmpeg 의존 없음)
    temp = Path(out_path).with_name(f"_temp_overlay_{Path(out_path).stem}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') # OpenH264 의존성 이슈로 mp4v 복구
    vw = cv2.VideoWriter(str(temp), fourcc, fps, (W, H))
    if not vw.isOpened():
        print("  ⚠️  VideoWriter 초기화 실패")
        return None

    cap = cv2.VideoCapture(str(video_path))
    try:
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
                nxt = pts[ptr[gid]] if ptr[gid] < len(pts) else None
                if nxt is not None and (nxt['frame'] - cur['frame']) <= 2 * step + 1:
                    visible = True
                else:
                    visible = abs(fi - cur['frame']) <= 2
                if visible:
                    _draw_box_on_frame(frame, cur, g)
            vw.write(frame)
    finally:
        vw.release()
        cap.release()

    # FFmpeg 있으면 오디오 합성, 없으면 무음 mp4 그대로 저장
    _mux_audio(temp, video_path, out_path)
    return out_path


# ═════════════════════════════════════════════════════════════════════════════
# 타임라인 마커 데이터 빌더 (시각 PII + 음성 PII → markers.json)
# ═════════════════════════════════════════════════════════════════════════════
def _build_timeline_markers(rep: dict, total_duration: float) -> list:
    """result.json의 pii_groups(시각) + audio_pii_groups(음성) → 타임라인 마커 배열.
    프론트엔드 재생바 마커 렌더링용 — left_pct = start_sec / total_duration × 100."""
    if total_duration <= 0:
        return []
    markers = []

    # 시각 PII: keyframes 시간 범위에서 시작/종료 추출
    for g in rep.get('pii_groups', []):
        kfs   = g.get('keyframes', [])
        times = [kf['timestamp'] for kf in kfs if 'timestamp' in kf]
        if not times:
            continue
        start_sec = min(times)
        end_sec   = max(times)
        markers.append({
            'id'       : g['pii_id'],
            'source'   : 'visual',
            'pii_type' : g.get('pii_type', ''),
            'start_sec': round(start_sec, 3),
            'end_sec'  : round(end_sec, 3),
            'left_pct' : round(start_sec / total_duration * 100, 2),
            'severity' : _PII_SEVERITY.get(g.get('pii_type', ''), 'low'),
        })

    # 음성 PII: start_time_sec / end_time_sec 그대로 사용
    for g in rep.get('audio_pii_groups', []):
        start_sec = float(g.get('start_time_sec', 0.0))
        end_sec   = float(g.get('end_time_sec', start_sec))
        markers.append({
            'id'       : g['pii_id'],
            'source'   : 'audio',
            'pii_type' : g.get('pii_type', ''),
            'start_sec': round(start_sec, 3),
            'end_sec'  : round(end_sec, 3),
            'left_pct' : round(start_sec / total_duration * 100, 2),
            'severity' : _PII_SEVERITY.get(g.get('pii_type', ''), 'low'),
        })

    markers.sort(key=lambda m: m['start_sec'])
    return markers


# ═════════════════════════════════════════════════════════════════════════════
# 공통 유틸 — JSON 로드 + 원본 경로 해석
# ═════════════════════════════════════════════════════════════════════════════
def _load_report(report_json_path):
    """{stem}_result.json 로드."""
    with open(Path(report_json_path), encoding='utf-8') as f:
        return json.load(f)


def _resolve_source(report_json, report_json_path, input_path):
    """원본 파일 경로 결정: 인자 우선 → 없으면 입력폴더에서 자동 탐색."""
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
        stem = Path(src_name).stem
        cand = next((INPUT_VIDEO_DIR / f"{stem}{e}" for e in VIDEO_EXTS
                     if (INPUT_VIDEO_DIR / f"{stem}{e}").exists()), None)
    return src_type, src_name, cand


# ═════════════════════════════════════════════════════════════════════════════
# 3단계 — 상세보기 (run_detail_view)
# ═════════════════════════════════════════════════════════════════════════════
def run_detail_view(index_json_path, input_path=None):
    """
    [3단계] 상세보기 — 원본 위에 모든 PII 탐지 구역을 박스로 표시.
    - 이미지: output_file/{stem}_상세보기.jpg
    - 영상  : output_file/{stem}_상세보기.mp4 + overlay_tracks 반환
    입력: {stem}_result.json (backend_json_merger.py 가 생성한 파일)
    반환: {'source_type', 'pii_groups', 'overlay_image'/'overlay_video', 'overlay_tracks'(영상)}
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
        overlay_img = draw_pii_report(image, pii_groups)
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
        if _set_frame_rot(cap, rep.get('image_width'), rep.get('image_height')) is not None:
            W, H = H, W
        cap.release()

        # 타임라인 마커는 result.json의 timeline_markers 키에서 읽음 (merger에서 생성됨)
        markers = rep.get('timeline_markers') or []
        if not markers:
            # merger 없이 단독 실행 시 폴백: 직접 생성
            total_duration = total / fps if fps > 0 else rep.get('total_duration', 0.0)
            markers = _build_timeline_markers(rep, total_duration)
        result['markers'] = markers
        v_cnt = sum(1 for m in markers if m['source'] == 'visual')
        a_cnt = sum(1 for m in markers if m['source'] == 'audio')
        print(f"  📍 타임라인 마커 {len(markers)}개 확인  (시각 {v_cnt}건 + 음성 {a_cnt}건)")

        print(f"  🎯 오버레이 트랙 생성 (TRACK_FPS={TRACK_FPS})...")
        overlay_tracks = _build_overlay_tracks(src_path, pii_groups, fps, total)
        result['overlay_tracks'] = overlay_tracks

        print(f"  🎬 상세보기 오버레이 영상 생성...")
        save_path = OUTPUT_DIR / f"{stem}_상세보기.mp4"
        rendered = _render_overlay_video(src_path, pii_groups, overlay_tracks, fps, total, W, H, save_path)
        if rendered:
            result['overlay_video'] = str(save_path)
            print(f"  ✅ 상세보기 영상 저장 완료 → {save_path.name}  (PII {len(pii_groups)}건)")
        else:
            print(f"  ⚠️  상세보기 영상 생성 실패")

    print(f"\n{'='*60}\n[상세보기 생성 완료]\n{'='*60}")
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 단독 실행 테스트
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import re as _re
    import os as _os

    OUTPUT_FILE_DIR = str(OUTPUT_DIR)
    TARGET_NAME = "카드_음성_영상1"
    try:
        report_py = _LOCAL_BASE / "OCR_pipeline_report.py"
        with open(str(report_py), "r", encoding="utf-8") as f:
            m = _re.search(r'TEST_TARGET\s*=\s*[rR]?["\'](.*?)["\']', f.read())
            if m:
                TARGET_NAME = _os.path.splitext(_os.path.basename(m.group(1)))[0]
                print(f"💡 타겟 자동 감지: '{TARGET_NAME}'")
    except Exception as e:
        print(f"⚠️  타겟 자동 감지 실패 (기본값 사용): {e}")

    result_json = _os.path.join(OUTPUT_FILE_DIR, f"{TARGET_NAME}_result.json")
    if not _os.path.exists(result_json):
        print(f"❌ result.json 없음: {result_json}")
    else:
        print(f"🔍 상세보기 생성 시작: {result_json}")
        out = run_detail_view(result_json)
        print(f"\n✅ 완료: {out}")
