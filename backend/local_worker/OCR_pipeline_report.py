"""
리포트 파이프라인 (이미지 + 영상) — 로컬 CPU 전용
OCR → 정규식 PII 탐지 → {stem}_index.json 생성 (마스킹 없음, 좌표만 추출)
index.json = 리포트 요약 + PII 그룹(keyframes/boxes) + OCR 전체 박스(비PII 포함)
"""

import os
# ── [로컬 환경 전용] OpenMP 중복 로드 충돌 회피 (임시 우회) ──
# 왜: torch·numpy·opencv 등이 OpenMP 런타임(libiomp/libomp)을 중복 로드하면 크래시 발생
# (주로 로컬 Windows/conda) 그 충돌을 무시하도록 허용하는 우회 플래그.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# 서비스 시: 도커 등 깔끔한 리눅스 환경에선 보통 불필요 → 제거 권장(중복 OpenMP 없으면 불필요).

import re
import sys
import math
import json
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher   # 영상 PII 인스턴스 분리: 텍스트 유사도 비교용

# 콘솔 출력 인코딩 UTF-8 고정 (Windows cp949 콘솔의 이모지/한글 출력 오류 방지)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ── 환경설정 (경로·파라미터) ──
# 테스트 경로 (백엔드 연동 시 파일 업로더 함수로 대체)
TEST_TARGET = r"G:\내 드라이브\PJ(Human)\Final_PJ(Human_team)\Human_Final_PJ-main\test_image_file\우편물3.jpg"

# 경로 설정
try:
    _LOCAL_BASE = Path(__file__).resolve().parent
except NameError:                       # Colab 등 exec() 실행 시 __file__ 없음
    _LOCAL_BASE = Path.cwd()
BASE_DIR         = _LOCAL_BASE.parent.parent  # 작업 루트 (Human_Final_PJ-main 또는 /)
INPUT_IMAGE_DIR  = BASE_DIR / "test_image_file"    # 원본 이미지 폴더
INPUT_VIDEO_DIR  = BASE_DIR / "test_video_file"    # 원본 영상 폴더
OCR_IMAGE_OUTPUT = BASE_DIR / "ocr_image_output"   # 이미지 OCR JSON 폴더 (OCR_Setting 출력)
OCR_VIDEO_OUTPUT = BASE_DIR / "ocr_video_output"   # 영상 OCR JSON 폴더 (OCR_Setting 출력)
OUTPUT_DIR       = BASE_DIR / "output_file"        # 최종 결과({stem}_index.json) 저장 폴더
IMG_EXTS   = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')  # 처리할 이미지 확장자
VIDEO_EXTS = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm')    # 처리할 영상 확장자

# ── PII 줄 묶음(클러스터링) ──
LINE_GAP_RATIO  = 0.8   # 줄 분리 임계(글자높이 비율). 기울어진 텍스트는 자동 0.4 적용

# ── 한 줄 안에서 '쪼개진 한 토큰' 재결합 (예: '13'+'6길'→'136길', '204'+'호'→'204호') ──
#   단어 분리가 숫자/단위 토큰을 쪼개 넣은 공백 때문에 주소·번호 정규식이 깨지는 것 방지.
#   '틈이 작고(WORD_JOIN_GAP_RATIO 이내) + 숫자/단위가 이어질 때'만 공백 없이 결합(한글 단어는 보존).
WORD_JOIN_GAP_RATIO = 0.8   # 두 박스 틈 < 글자높이×이 비율이면 '붙은 토큰' 후보
WORD_JOIN_SUFFIX = ('호', '동', '층', '번지', '번', '가', '길', '리')  # 숫자에 붙는 주소/단위 접미

# ── 영상 PII 인스턴스 분리 ──
VID_INSTANCE_TEXT_SIM     = 0.7    # 정규화 텍스트 유사도 임계 — 이상이면 같은 인스턴스로 병합
VID_INSTANCE_IOU_MERGE    = 0.30   # bbox IoU 임계 — 위치 기반 2차 병합(OCR 오인식 그룹 복구)
VID_INSTANCE_TIME_GAP_SEC = 1.0    # 시간 간격(초) 임계 — 이내면 동일 등장으로 간주

# ── 영상 역소급(backfill) 텍스트 검증 임계 ──
# 역소급 후보 박스 텍스트가 원래 PII 텍스트와 이 값 미만이면 다른 PII 박스 오소급 차단
VID_BACKFILL_TEXT_SIM = 0.4

# ── OCR 모듈 연동: 같은 폴더의 OCR_Setting.py import (흐름: OCR → PII 탐지 → 리포트) ──
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
try:
    import OCR_Setting
except Exception as _e:
    OCR_Setting = None
    print(f"[경고] OCR_Setting import 실패 — OCR→마스킹 통합 실행 불가: {_e}")


# ─────────────────────────────────────────────────
# 위험도 등급 정의 (화면설계 리포트 페이지 기준)
# ─────────────────────────────────────────────────
_RISK_WEIGHTS = {
    "주민등록번호": ("위험", 3), "외국인등록번호": ("위험", 3),
    "카드번호":     ("위험", 3), "계좌번호":       ("위험", 3),
    "여권번호":     ("위험", 3), "운전면허번호":   ("위험", 3),
    "전화번호":     ("주의", 2), "주소":           ("주의", 2),
    "이메일":       ("주의", 2),
    "건강보험증번호": ("참고", 1), "생년월일": ("참고", 1),
    "나이": ("참고", 1),
}

def _risk_level(pii_type: str) -> str:
    """PII 타입 → 위험 등급 반환 ('위험' / '주의' / '참고')."""
    return _RISK_WEIGHTS.get(pii_type, ("참고", 1))[0]


def _calc_risk_score(pii_groups: list) -> float:
    """
    PII 그룹 목록 → 위험도 점수 0~10 반환.
    위험(3점)·주의(2점)·참고(1점) 가중합산 → 10점 만점 정규화.
    기준: 위험 항목 1건=3점 만점이 되도록 정규화. 최대 10점.
    """
    if not pii_groups:
        return 0.0
    total_weight = sum(_RISK_WEIGHTS.get(g['pii_type'], ("참고", 1))[1] for g in pii_groups)
    max_single = 3  # 위험 등급 최대 가중치
    # 가중합을 최대 가능 점수로 정규화(최대 10점)
    score = min(10.0, total_weight / max_single * 10 / max(len(pii_groups), 1) * min(len(pii_groups), 5) / 5)
    # 보정: 위험 항목 1개 이상이면 최소 5.0
    has_danger = any(_RISK_WEIGHTS.get(g['pii_type'], ("참고", 1))[0] == "위험" for g in pii_groups)
    if has_danger:
        score = max(score, 5.0)
    return round(min(10.0, score), 1)


def _build_risk_counts(pii_groups: list) -> dict:
    """PII 그룹 목록 → {'위험': n, '주의': n, '참고': n} 집계."""
    counts = {"위험": 0, "주의": 0, "참고": 0}
    for g in pii_groups:
        lvl = _risk_level(g['pii_type'])
        counts[lvl] = counts.get(lvl, 0) + 1
    return counts


# ─────────────────────────────────────────────────
# 정규표현식 패턴 (개인정보 식별)
# ─────────────────────────────────────────────────
PII_PATTERNS = [
    # 1. 주민등록번호 (6자리-7자리)
    ("주민등록번호", re.compile(r'\b\d{6}[-\s]*[1-4]\d{6}\b')),
    # 2. 외국인등록번호
    ("외국인등록번호", re.compile(r'\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[- ]?[5-8]\d{6}\b')),
    # 3. 여권번호
    ("여권번호", re.compile(r'\b[a-zA-Z]{1,2}[-\s]*\d{7,8}\b')),
    # 4. 운전면허번호
    ("운전면허번호", re.compile(r'\b\d{2}\s*-\s*\d{2}\s*-\s*\d{6}\s*-\s*\d{2}\b')),
    # 5. 전화번호 (휴대전화, 날짜 오인 방지 적용)
    ("전화번호", re.compile(
        r'(?<!\d)(?:'
        # 국제표기: (+)82 + 휴대폰앞(1X, 010의 0 생략) + 중간 + 뒷4(필수)
        r'(?:(?:\+|＋)?\s*82[\s\-.\)국번호에의]*'
        r'[1일][016789영공빵oO일육륙여섯칠일곱팔여덟구아홉]'
        r'[\s\-.\)국번호에의]*[0-9영공빵oO일하나둘이삼셋사넷오다섯육륙여섯칠일곱팔여덟구아홉]{3,4}'
        r'[\s\-.\)국번호에의]*[0-9영공빵oO일하나둘이삼셋사넷오다섯육륙여섯칠일곱팔여덟구아홉]{4})'
        r'|'
        # 국내 휴대폰: 01X(0+1+[0/1/6/7/8/9]) + 중간3~4 + 뒷4(필수)
        r'(?:[0영공빵oO][1일][016789영공빵oO일육륙여섯칠일곱팔여덟구아홉]'
        r'[\s\-.\)국번호에의]*[0-9영공빵oO일하나둘이삼셋사넷오다섯육륙여섯칠일곱팔여덟구아홉]{3,4}'
        r'[\s\-.\)국번호에의]*[0-9영공빵oO일하나둘이삼셋사넷오다섯육륙여섯칠일곱팔여덟구아홉]{4})'
        r')(?!\d)(?!\s*(?:년|월|일|시|분|원))'
    )),
    # 6. 신용/체크카드 번호
    ("카드번호", re.compile(
        r'(?<!\d)(?:'
        r'\d{4}(?:[-\s]+\d{4}){2,3}'   # 4-4-4 또는 4-4-4-4 (구분자 필수)
        r'|\d{15,16}'                  # 구분자 없는 15~16자리 연속 카드
        r'|\d{8}'                      # OCR이 두 줄 카드 한 줄(4-4)을 공백 없이 합쳐 인식한 경우
        r')(?!\d)'
    )),
    # 7. 계좌번호
    ("계좌번호", re.compile(
        r'(?:(?<=계좌|은행|농협|국민|우리|신한|기업|하나)|(?<=카카오)|(?<=Account))'
        r'[\s:]*(\d{1,6}(?:[-. ]\d{1,6}){2,5})\b'
        r'|\b(\d{1,6}(?:[-. ]\d{1,6}){2,5})'
        r'(?=[\s:]*(?:계좌|은행|Account|농협|국민|우리|신한|기업|하나|카카오))'
    )),
    # 8. 이메일
    ("이메일", re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')),
    # 9. 건강보험증번호
    ("건강보험증번호", re.compile(
        r'(?:(?<=번호)|(?<=증번호|보험증|보장증))[\s:]*([1257][- ]\d{4}[- ]\d{6})\b'
        r'|\b([1257][- ]\d{4}[- ]\d{6})\b'
    )),
    # 10. 생년월일
    ("생년월일", re.compile(
        r'(?:(?<=생일|생년)|(?<=DOB)|(?<=생년월일|Born))'
        r'[\s:]*(?:(?:19|20)?\d{2}[\s./-]*\d{1,2}[\s./-]*\d{1,2}'
        r'|(?:\d{2,4}년\s?\d{1,2}월\s?\d{1,2}일))'
        r'|\b(?:19|20)?\d{2}\s?년\s?월\b'
    )),
    # 11. 나이
    ("나이", re.compile(
        r'(?:(?<=나이|연령)|(?<=Age))[\s:]*\d{1,3}(?!\d)'
        r'|\b(?:만\s*)?\d{1,3}\s*세\b'
    )),
    # 12. 주소 (계층적 구조화 - 블랙홀 오탐지 방지 및 명확한 시/구/동 필수 규칙 적용)
    ("주소", re.compile(
        r'(?:'
        
        # [주소 메인 분기]
        r'(?:'
            # 분기 1: 행정구역(시/군/구/동) 포함
            r'(?:'
                # 1-A: '도/시/군'으로 시작하면 뒤에 반드시 하위 행정구역(구/동/로/길/읍/면)이 1개 이상 와야 함
                r'(?:'
                    # OCR 오타 내결함성을 위해 공백을 선택적([\s,]*)으로 완화
                    r'(?:(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|경상|전라)[가-힣]{0,4}?[\s,]*(?:특별시|광역시|특별자치시|도|특별자치도)?[\s,]*)?'
                    r'(?:[가-힣A-Za-z0-9]{1,10}[\s,]*(?:시|도|군)[\s,]*)'
                    r'(?:[가-힣A-Za-z0-9]{1,10}[\s,]*(?:군|구|동|대로|로|길|번길|읍|면|리|가)[\s,]+)+'
                r')'
                r'|'
                # 1-B: '구/동/읍/면'으로 시작하면 단독으로 숫자가 와도 허용
                r'(?:'
                    r'(?:(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|경상|전라)[가-힣]{0,4}?[\s,]*(?:특별시|광역시|특별자치시|도|특별자치도)?[\s,]*)?'
                    r'(?:[가-힣A-Za-z0-9]{1,10}[\s,]*(?:구|동|읍|면)[\s,]+)'
                    r'(?:[가-힣A-Za-z0-9]{1,10}[\s,]*(?:동|대로|로|길|번길|리|가)[\s,]*)*'
                r')'
            r')'
            r'|'
            # 분기 2: 예외적 허용 (OO로 OO길)
            r'(?:'
                r'(?:[가-힣]{1,4}[\s,]*(?:구|군|시)[\s,]+[가-힣\s]{0,8})?'
                r'[가-힣A-Za-z0-9]{2,10}(?<!으로)[\s,]*(?:대로|로)[\s,]+[가-힣0-9]{1,10}[\s,]*(?:길|번길)(?=[ \t,.]+(?:[가-힣A-Za-z0-9]{1,10}\s*)?\d+)'
            r')'
        r')'
        
        # [공통 부가정보 (지번, 아파트, 층, 호 등)]
        r'(?:'
            r'[ \t,.]*' 
            r'(?:'
                # [케이스 A] 정상 번지수(숫자) + 부가정보
                r'(?:산)?\d+(?:-\d+)?(?:[ \t,.]*(?:번지|번길|길|호))?'
                r'(?:'
                    r'[ \t,.]*'
                    r'(?:\(?[가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                    r'[ \t,.]*'
                    r'(?:[가-힣A-Za-z0-9]+(?:아파트|빌라|빌딩|타워|파크|맨션|하이츠|힐|캐슬|레지던스|오피스텔|프라자|센터|타운|마을))?'
                    r'[ \t,.]*'
                    r'(?:(?:[가-힣0-9]+[ \t]*동)?[ \t,.]*(?:\d+[ \t]*[A-Za-z가-힣]*[ \t]*호|\d+[ \t]*층|\d+-\d+[ \t]*호|B\d+[ \t]*층|지하\d+[ \t]*층))?'
                    r'[ \t,.]*'
                    r'(?:\(?[가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                r'){0,2}'
                
                r'|'
                
                # [케이스 B] 번지수 누락 + 곧바로 아파트/빌딩 등
                r'(?:'
                    r'[ \t,.]*'
                    r'(?:\(?[가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                    r'[ \t,.]*'
                    r'(?:[가-힣A-Za-z0-9]+(?:아파트|빌라|빌딩|타워|파크|맨션|하이츠|힐|캐슬|레지던스|오피스텔|프라자|센터|타운))'
                    r'[ 	,.]*'
                    r'(?:(?:[가-힣0-9]+[ 	]*동)?[ 	,.]*(?:\d+[ 	]*[A-Za-z가-힣]*[ 	]*호|\d+[ 	]*층|\d+-\d+[ 	]*호|B\d+[ 	]*층|지하\d+[ 	]*층))?'
                r')'
            r')'
        r')'
        
        r')',
        re.UNICODE | re.IGNORECASE
    )),
    # 13. 차량번호 (현재/이전 형식, 주소 번지와 구분)
    ("차량번호", re.compile(
        r'(?<![\d가-힣])'  # 음의 후방탐색: 앞에 숫자나 한글이 없어야 함 (주소와 구분)
        r'(?:'
            r'\d{2}[\s-]*[가나다라마바사아자차카타파하][\s-]*\d{4}'  # 현재 형식: 12가3456, 12-가-3456
            r'|'
            r'(?<!\d)\d{1}[\s-]*[가나다라마바사아자차카타파하][\s-]*\d{4}'  # 이전 형식: 1가3456 (숫자 1자리만)
        r')'
        r'(?![\d호번지동])'  # 음의 전방탐색: 뒤에 숫자나 주소 키워드가 없어야 함
    )),
    # 14. 주소(보강) — OCR이 공백 없이 붙여 인식한 경우도 포착 ([\s,]+ → [\s,]*)
    #   예: '서울시노원구동일로228길35 청수빌딩 204호' (공백 없는 도로명 + 빌딩명 + 층/호까지 포함)
    ("주소", re.compile(
        r'[가-힣]{2,3}시[\s,]*'                          # OO시 시작 (공백 선택적)
        r'(?:[가-힣A-Za-z0-9]{1,6}[\s,]*){1,2}'           # 중간 1~2단어 (공백 선택적)
        r'[가-힣0-9]{1,10}로[\s,]*\d+'                    # XX로 + 번지 숫자 (필수)
        r'(?:길(?:[\s,]*\d+)?)?'                         # 228길 또는 228길35 (숫자 선택적)
        r'(?:[\s,]*[가-힣A-Za-z0-9\s]+'                    # 건물명 앞 한글/영문/숫자/공백 (선택)
        r'(?:빌딩|타워|아파트|빌라|오피스텔|프라자|센터|파크|맨션|캐슬|레지던스|하이츠|힐))?'
        r'(?:[\s,]*(?:\d+[ \t]*층|\d+-?\d*[ \t]*호|B\d+[ \t]*층|지하\d+[ \t]*층))?',  # 층/호 (선택)
        re.UNICODE | re.IGNORECASE
    )),
]


def _norm_pii_text(s: str) -> str:
    """PII 텍스트 정규화 — 공백·하이픈·점 제거 후 비교용 키 생성.
    (수정사항1: 같은 개인정보는 같은 pii_id 부여 → '010-1234-5678'과 '010 1234 5678'을 동일 취급)"""
    return re.sub(r'[\s\-.]', '', str(s))


def _is_plausible_address(s: str) -> bool:
    """주소 매칭 오탐 필터: 진짜 한글 주소인지 검증.
    카드의 영문/숫자 텍스트('SA크리 09/19' 등)에서 '리/로/동' 조각이 우연히 매칭되는 것을 제거.
    - 행정구역(시/도/구/군/읍/면) 단서가 있으면 진짜 주소로 인정
    - 아니면 한글이 3자 이상이어야 인정(영문/숫자 위주의 짧은 오탐 차단)"""
    if re.search(r'(특별시|광역시|특별자치시|특별자치도|[가-힣]시|[가-힣]도|[가-힣]구|[가-힣]군|[가-힣]읍|[가-힣]면)', s):
        return True
    return len(re.findall(r'[가-힣]', s)) >= 3


def _normalize_ocr_for_card(text: str) -> str:
    """카드번호 탐지 전용 OCR 오인식 보정.
    PaddleOCR이 숫자를 영문자로 혼동하는 패턴을 역치환:
      O→0, I/l→1, E→7 (7이 E로 오인식), S→5, G→6
    카드번호 패턴 매칭 시에만 사용하며 전체 텍스트를 오염시키지 않음."""
    return text.translate(str.maketrans('OIlESG', '011758'))


def analyze_and_mask_text_all(joined_text):
    """텍스트에서 모든 PII 정규식을 순회해 매칭 반환.
    반환: [(pii_type, "", start, end, 원본텍스트), ...] (겹치는 매칭은 제외)"""
    results = []
    matched_ranges = []

    # 카드번호 전용: OCR 오인식 보정 텍스트 (O→0, I→1, E→7 등)
    card_text = _normalize_ocr_for_card(joined_text)

    def is_overlap(start, end):
        for rs, re_end in matched_ranges:
            if max(start, rs) < min(end, re_end):
                return True
        return False

    for pii_type, pattern in PII_PATTERNS:
        # 카드번호는 OCR 오인식 보정 텍스트로 검색 (원본 위치는 동일하게 사용)
        search_text = card_text if pii_type == "카드번호" else joined_text
        for match in pattern.finditer(search_text):
            ms, me = match.start(), match.end()
            if is_overlap(ms, me):
                continue
            # 주소는 오탐이 잦으므로 한글 행정구역/글자수로 한 번 더 검증
            if pii_type == "주소" and not _is_plausible_address(match.group(0)):
                continue
            # 원본 텍스트 기준 위치와 실제 텍스트 사용 (후처리 텍스트가 아닌 원본 반환)
            results.append((pii_type, "", ms, me, joined_text[ms:me]))
            matched_ranges.append((ms, me))
    return results

# ─────────────────────────────────────────────────
# OCR JSON 로드
# ─────────────────────────────────────────────────

def _split_box_by_words(b: dict) -> list:
    """공백이 포함된 OCR 박스를 단어별 타이트한 박스로 분할.
    한글은 고정폭에 가까우므로 글자 수 기준 선형 보간으로 분할 좌표 계산.
    vertices(4점 회전 폴리곤)도 동일 비율로 보간 → 마스킹이 단어 단위로 정교하게 동작."""
    text = b['text']
    words = text.split()
    if len(words) <= 1:
        return [b]

    # 각 단어의 시작/끝 비율(전체 텍스트 길이 기준)
    positions = []
    idx = 0
    for word in words:
        start = text.find(word, idx)
        end = start + len(word)
        positions.append((start / len(text), end / len(text)))
        idx = end

    result = []
    for word, (t_start, t_end) in zip(words, positions):
        nb = dict(b)
        nb['text'] = word

        if b.get('vertices') and len(b['vertices']) == 4:
            # vertices 기준 선형 보간: [TL, TR, BR, BL] 순서 가정
            v = b['vertices']
            tl = (v[0]['x'], v[0]['y'])
            tr = (v[1]['x'], v[1]['y'])
            br = (v[2]['x'], v[2]['y'])
            bl = (v[3]['x'], v[3]['y'])

            def _lerp(p1, p2, t):
                return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)

            # 단어의 왼쪽/오른쪽 경계를 상단선·하단선에서 각각 보간
            lt = _lerp(tl, tr, t_start)
            rt = _lerp(tl, tr, t_end)
            lb = _lerp(bl, br, t_start)
            rb = _lerp(bl, br, t_end)

            nb['vertices'] = [
                {'x': int(round(lt[0])), 'y': int(round(lt[1]))},
                {'x': int(round(rt[0])), 'y': int(round(rt[1]))},
                {'x': int(round(rb[0])), 'y': int(round(rb[1]))},
                {'x': int(round(lb[0])), 'y': int(round(lb[1]))},
            ]
            xs = [p['x'] for p in nb['vertices']]
            ys = [p['y'] for p in nb['vertices']]
            nb['x_min'] = min(xs); nb['x_max'] = max(xs)
            nb['y_min'] = min(ys); nb['y_max'] = max(ys)
        else:
            # vertices 없으면 x_min/x_max 만 비율로 분할
            orig_w = b['x_max'] - b['x_min']
            nb['x_min'] = int(b['x_min'] + orig_w * t_start)
            nb['x_max'] = int(b['x_min'] + orig_w * t_end)

        nb['y_center'] = float((nb['y_min'] + nb['y_max']) / 2)
        nb['h']        = float(nb['y_max'] - nb['y_min'])
        result.append(nb)

    return result


def load_ocr_boxes(json_path: Path) -> list:
    """ocr_data_*.json → 박스 목록. font_zones 우선(없으면 regions 하위호환).
    공백이 포함된 OCR 박스는 단어별로 분할해 마스킹이 타이트하게 동작하도록 함."""
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    boxes = []
    zones = data.get("font_zones") or data.get("regions", [])
    for zone in zones:
        zone_id = zone.get("zone_id", zone.get("region_id", 0))
        for b in zone.get("boxes", []):
            base = {
                'text':      b['text'],
                'x_min':     int(b['x_min']), 'y_min': int(b['y_min']),
                'x_max':     int(b['x_max']), 'y_max': int(b['y_max']),
                'y_center':  float(b.get('y_center', (b['y_min'] + b['y_max']) / 2)),
                'h':         float(b.get('h', b['y_max'] - b['y_min'])),
                'angle':     float(b.get('angle', 0.0)),
                'prob':      float(b.get('prob', 1.0)),
                'zone_id':   zone_id,
                'region_id': zone_id,   # clustering 함수 호환
                'vertices':  b.get('vertices', None),
            }
            boxes.append(base)
    return boxes


def universal_directional_clustering(boxes: list, line_gap_ratio: float = LINE_GAP_RATIO) -> list:
    """
    [유니버셜 전방위 클러스터링]
    텍스트 기울기(angle)를 2D 벡터로 변환해 읽기방향/줄바꿈방향 축에 투영 →
    대각선·세로쓰기·투시 텍스트도 한 줄로 정확히 병합.
    """
    if not boxes: return []

    regions = {}
    for b in boxes:
        regions.setdefault(b.get('region_id', 0), []).append(b)

    all_lines = []
    for rid, rboxes in regions.items():
        if not rboxes: continue
        med_angle = np.median([b['angle'] for b in rboxes])
        rad = math.radians(med_angle)
        v_dir = np.array([math.cos(rad), math.sin(rad)])   # 읽기 방향
        o_dir = np.array([-math.sin(rad), math.cos(rad)])  # 줄바꿈 방향

        for b in rboxes:
            c_vec = np.array([(b['x_min'] + b['x_max']) / 2, (b['y_min'] + b['y_max']) / 2])
            b['_proj_y'] = float(np.dot(c_vec, o_dir))
            b['_proj_x'] = float(np.dot(c_vec, v_dir))

        rboxes.sort(key=lambda b: b['_proj_y'])
        avg_h = np.mean([b['h'] for b in rboxes])
        lines = [[rboxes[0]]]
        for b in rboxes[1:]:
            prev_line = lines[-1]
            prev_y = sum(x['_proj_y'] for x in prev_line) / len(prev_line)
            is_same_line = abs(b['_proj_y'] - prev_y) < max(avg_h * line_gap_ratio, 8.0)
            if is_same_line:   # Y 비슷해도 X로 겹치면 다른 줄
                b_left  = b['_proj_x'] - (b['x_max'] - b['x_min'])/2
                b_right = b['_proj_x'] + (b['x_max'] - b['x_min'])/2
                for p in prev_line:
                    p_left  = p['_proj_x'] - (p['x_max'] - p['x_min'])/2
                    p_right = p['_proj_x'] + (p['x_max'] - p['x_min'])/2
                    overlap_x = max(0, min(b_right, p_right) - max(b_left, p_left))
                    if overlap_x > min(b_right - b_left, p_right - p_left) * 0.3:
                        is_same_line = False
                        break
            if is_same_line:
                lines[-1].append(b)
            else:
                lines.append([b])

        # 줄 안에서 읽기순 정렬 + 넓은 간격(컬럼) 강제 분리
        final_lines = []
        for ln in lines:
            ln.sort(key=lambda b: b['_proj_x'])
            avg_h = np.mean([b['h'] for b in ln])
            split_ln = [ln[0]]
            for b in ln[1:]:
                prev_b = split_ln[-1]
                dist_x = b['_proj_x'] - prev_b['_proj_x']
                gap = dist_x - ((prev_b['x_max'] - prev_b['x_min'])/2 + (b['x_max'] - b['x_min'])/2)
                if gap > avg_h * 2.5:
                    final_lines.append(split_ln)
                    split_ln = [b]
                else:
                    split_ln.append(b)
            final_lines.append(split_ln)

        # 블록(단락) 단위로 묶기
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

        # 블록 정렬: 비슷한 Y(2.5줄 높이 이내)면 X좌표 우선, 다르면 Y좌표 우선
        global_avg_h = np.mean([b['h'] for b in rboxes])
        blocks.sort(key=lambda blk: (int(blk['min_y'] / (global_avg_h * 2.5)), blk['min_x']))

        for blk in blocks:
            blk['lines'].sort(key=lambda x: x[0])  # 블록 내에서는 Y좌표 순(위에서 아래)
            for _, ln in blk['lines']:
                all_lines.append(ln)

    # region_id 기준으로만 정렬 (블록 정렬 유지)
    all_lines.sort(key=lambda ln: ln[0].get('region_id', 0))
    return all_lines


def build_full_text(lines: list) -> tuple:
    """라인들을 하나의 이어진 문장(full_text)과 (start, end, box) 매핑으로 변환.
    줄바꿈을 공백으로 치환해 줄을 넘는 전화번호/주소도 끊기지 않고 매칭되게 함."""
    full_text = ""
    box_spans = []
    prev_line = None
    for line_boxes in lines:
        if prev_line:
            prev_region = prev_line[0].get('region_id', -1)
            curr_region = line_boxes[0].get('region_id', -2)
            prev_angle = sum(b['angle'] for b in prev_line) / len(prev_line)
            curr_angle = sum(b['angle'] for b in line_boxes) / len(line_boxes)
            
            # 유저 알고리즘 반영: 줄바꿈 문장 병합
            is_word_wrap = False
            if prev_region == curr_region and abs(curr_angle - prev_angle) < 5:
                last_b = prev_line[-1]
                first_b = line_boxes[0]
                first_of_prev = prev_line[0]
                
                avg_h = max((last_b.get('y_max', 0) - last_b.get('y_min', 0)), 10.0)
                y_gap = first_b.get('y_min', 0) - last_b.get('y_max', 0)
                x_diff_start = abs(first_b.get('x_min', 0) - first_of_prev.get('x_min', 0))
                
                # 바로 아랫줄(Y간격이 좁음)이고 시작점(X)이 거의 같으면 줄바꿈된 하나의 문장으로 판별
                if -avg_h * 2.0 < y_gap < avg_h * 3.0 and x_diff_start < avg_h * 3.0:
                    is_word_wrap = True

            if is_word_wrap:
                full_text += " " # 줄바꿈 문장이므로 하나의 공백으로 이어붙임
            else:
                # 구역이 다르거나 각도 크게 차이 → 3칸(강한 분리), 아니면 1칸
                full_text += "   " if (prev_region != curr_region or abs(curr_angle - prev_angle) >= 10) else " "
                
        avg_h = max(sum((b['y_max'] - b['y_min']) for b in line_boxes) / max(len(line_boxes), 1), 1.0)
        prev_b = None
        for b in line_boxes:
            if prev_b is not None:
                # 읽기방향 틈(_proj_x 우선, 없으면 x좌표)
                if ('_proj_x' in b) and ('_proj_x' in prev_b):
                    gap = (b['_proj_x'] - prev_b['_proj_x']
                           - ((prev_b['x_max'] - prev_b['x_min']) / 2 + (b['x_max'] - b['x_min']) / 2))
                else:
                    gap = b['x_min'] - prev_b['x_max']
                pt = prev_b['text']; ct = b['text']
                # '쪼개진 한 토큰' 판정: 틈이 작고 + 숫자가 이어지거나(13+6길) 숫자에 단위접미가 붙음(204+호)
                num_join = (gap < avg_h * WORD_JOIN_GAP_RATIO) and bool(pt) and bool(ct) and pt[-1].isdigit() and (
                    ct[0].isdigit() or ct.startswith(WORD_JOIN_SUFFIX)
                )
                avg_ch_w = max(4.0, (prev_b['x_max'] - prev_b['x_min']) / max(1, len(pt)))
                tight = gap < avg_ch_w * 0.5
                full_text += "" if (num_join or tight) else " "   # 붙은 토큰이면 공백 없이 결합
            start = len(full_text)
            full_text += b['text']
            box_spans.append((start, len(full_text), b))
            prev_b = b
        prev_line = line_boxes
    return full_text, box_spans


def get_polygon_contour(boxes: list) -> np.ndarray:
    """여러 단어 박스의 상단선·하단선을 이어 곡선 텍스트를 감싸는 타이트 다각형 생성."""
    if not boxes: return []
    top_pts, bottom_pts = [], []
    for i, b in enumerate(boxes):
        if b.get('vertices') and len(b['vertices']) == 4:
            v = b['vertices']
            top_pts.append((v[0]['x'], v[0]['y']))
            bottom_pts.append((v[3]['x'], v[3]['y']))
            if i == len(boxes) - 1:
                top_pts.append((v[1]['x'], v[1]['y']))
                bottom_pts.append((v[2]['x'], v[2]['y']))
        else:
            x1, y1, x2, y2 = b['x_min'], b['y_min'], b['x_max'], b['y_max']
            top_pts.append((x1, y1)); bottom_pts.append((x1, y2))
            if i == len(boxes) - 1:
                top_pts.append((x2, y1)); bottom_pts.append((x2, y2))
    bottom_pts.reverse()
    return np.array([top_pts + bottom_pts], dtype=np.int32)


# ─────────────────────────────────────────────────
# 이미지 마스킹 파이프라인
# ─────────────────────────────────────────────────
def process_images():
    """INPUT_IMAGE_DIR 내 모든 이미지 PII 탐지+리포트 (경로는 환경설정 사용)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_files = sorted(list(INPUT_IMAGE_DIR.glob("*.jpg")) + list(INPUT_IMAGE_DIR.glob("*.jpeg")) +
                         list(INPUT_IMAGE_DIR.glob("*.png")))
    if not image_files:
        print(f"❌ 처리할 이미지 없음: {INPUT_IMAGE_DIR}")
        return

    print(f"\n📋 총 {len(image_files)}개 이미지 처리\n{'=' * 60}")
    for idx, img_path in enumerate(image_files, 1):
        print(f"\n{'─' * 60}\n[{idx}/{len(image_files)}] {img_path.name}\n{'─' * 60}")
        analyze_image_one(img_path, OCR_IMAGE_OUTPUT, OUTPUT_DIR)

    print(f"\n{'=' * 60}\n🎉 전체 완료! → {OUTPUT_DIR}\n{'=' * 60}")


def _bbox_near(b1, b2, gap_ratio=1.2) -> bool:
    """두 bbox가 겹치거나 근접한지 판정(같은 영역/라벨 묶기용).
    x·y 빈 간격이 둘 중 작은 박스 높이의 gap_ratio배 이내면 '인접'."""
    ax1, ay1, ax2, ay2 = b1
    bx1, by1, bx2, by2 = b2
    dx = max(0, max(ax1, bx1) - min(ax2, bx2))   # 가로 빈 간격(겹치면 0)
    dy = max(0, max(ay1, by1) - min(ay2, by2))   # 세로 빈 간격
    thr = max(min(ay2 - ay1, by2 - by1), 1) * gap_ratio
    return dx <= thr and dy <= thr


def _group_pii_matches(matches, gap_ratio=1.2):
    """
    같은 PII를 '인스턴스(영역)' 단위로 병합. (사용자 규칙: 같은 영역=1개 / 다른 구역=별개)
    병합 조건: 같은 타입이고  (같은 zone  OR  bbox가 공간적으로 인접).
    → OCR이 한 주소를 여러 zone으로 쪼개도 인접하면 하나로 묶임.
    → 텍스트가 동일해도 위치가 다르면 별개 인스턴스 (전화번호1, 전화번호2 구분).
    반환: 병합된 매치 그룹 리스트 [[match, ...], ...] (위→아래 순 정렬)
    """
    n = len(matches)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(n):
        for j in range(i + 1, n):
            if matches[i]['pii_type'] != matches[j]['pii_type']:
                continue
            same_zone = matches[i]['zone'] == matches[j]['zone']
            # 위치(bbox)가 공간적으로 인접할 때만 병합 — 텍스트 동일성은 무시
            # (같은 전화번호가 스탬프/송장 두 곳에 있으면 전화번호1, 전화번호2로 분리)
            if same_zone or _bbox_near(matches[i]['bbox'], matches[j]['bbox'], gap_ratio):
                union(i, j)

    buckets = defaultdict(list)
    for i in range(n):
        buckets[find(i)].append(matches[i])
    groups = list(buckets.values())
    groups.sort(key=lambda grp: min(m['bbox'][1] for m in grp))  # 위에서 아래로
    return groups


def analyze_image_one(img_path: Path, ocr_dir: Path, output_dir: Path):
    """이미지 1장 PII 탐지 + 통합 index JSON 생성.
    산출물: {stem}_index.json (리포트 요약 + PII 그룹 + OCR 전체 박스 / 상세페이지·미리보기·본마스킹 공용 입력).
    ※ 박스 오버레이 이미지(리포트_*.jpg)는 생성하지 않음 — 3단계(mask.py run_detail_view)에서 생성.
    OCR JSON은 ocr_dir/{stem}/ocr_data_{stem}.json 또는 ocr_dir/ocr_data_{stem}.json."""
    arr   = np.fromfile(str(img_path), np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        print(f"  ⚠️  이미지 읽기 실패: {img_path}")
        return
    print(f"  📐 크기: {image.shape[1]}x{image.shape[0]}")

    # OCR JSON 경로: OCR_Setting.py는 ocr_image_output/{stem}/ 하위에 저장
    cand = [ocr_dir / img_path.stem / f"ocr_data_{img_path.stem}.json",
            ocr_dir / f"ocr_data_{img_path.stem}.json"]
    json_path = next((p for p in cand if p.exists()), None)
    if json_path is None:
        print(f"  ⚠️  OCR JSON 없음: {cand[0]}")
        return

    boxes = load_ocr_boxes(json_path)
    print(f"  📄 OCR 박스 {len(boxes)}개")

    lines = universal_directional_clustering(boxes)
    full_text, box_spans = build_full_text(lines)
    pii_matches = analyze_and_mask_text_all(full_text)

    if pii_matches:
        print(f"  📌 감지: {', '.join(set(p for p, *_ in pii_matches))}")

    # ── 1) 매치별 메타 수집 (마스킹 안 함 — 좌표만 수집 → report JSON) ──
    raw_matches = []
    for pii_type, _, ms, me, original in pii_matches:
        matched_boxes = [b for s, e, b in box_spans if max(s, ms) < min(e, me)]
        if not matched_boxes:
            continue
        # 주소: 앞뒤 비PII 토막(영문코드/날짜/항목명) 제거
        if pii_type == "주소":
            refined = []
            for b in matched_boxes:
                t = b['text'].strip()
                if re.match(r'^[A-Za-z]+$', t) or re.search(r'\d{4}[/.-]\d{2}', t): break
                if re.match(r'^(?:합계|총요금|수납요금|신용카드|현금|우편번호|수취인|등기번호|요금|통수|중량|종별|보통|영수증|접수일자|접수자|발송인)$', t): break
                if re.match(r'^주소\s*:?$', t): continue  # "주소"라는 라벨 단어가 박스에 포함되는 것 방지
                refined.append(b)
            if refined:
                matched_boxes = refined

        # PII 박스를 단어 단위로 분할 (마스킹 정교화: 단어 경계에 맞게 타이트하게)
        split_boxes = []
        for b in matched_boxes:
            split_boxes.extend(_split_box_by_words(b))
        polys, boxes_ser = [], []
        for line_boxes in universal_directional_clustering(split_boxes):
            poly = get_polygon_contour(line_boxes)
            if len(poly):
                polys.append(poly[0].tolist())
            for b in line_boxes:
                boxes_ser.append({'text': b['text'],
                                  'x_min': b['x_min'], 'y_min': b['y_min'],
                                  'x_max': b['x_max'], 'y_max': b['y_max'],
                                  'vertices': b.get('vertices')})
        bbox = (min(b['x_min'] for b in matched_boxes), min(b['y_min'] for b in matched_boxes),
                max(b['x_max'] for b in matched_boxes), max(b['y_max'] for b in matched_boxes))
        raw_matches.append({'pii_type': pii_type, 'zone': matched_boxes[0].get('zone_id', 0),
                            'bbox': bbox, 'text': original, 'polygons': polys, 'boxes': boxes_ser})

    # ── 2) 같은 PII를 영역 단위로 병합 ──
    type_seq = defaultdict(int)
    pii_groups = []
    for grp in _group_pii_matches(raw_matches):
        pii_type = grp[0]['pii_type']
        type_seq[pii_type] += 1
        seq      = type_seq[pii_type]
        zone_id  = grp[0]['zone']
        polys, boxes, texts = [], [], []
        xs1, ys1, xs2, ys2 = [], [], [], []
        for m in grp:
            polys += m['polygons']; boxes += m['boxes']; texts.append(m['text'])
            xs1.append(m['bbox'][0]); ys1.append(m['bbox'][1])
            xs2.append(m['bbox'][2]); ys2.append(m['bbox'][3])
        pii_groups.append({
            'pii_id':       f"{pii_type}_{seq}",
            'pii_label':    f"{pii_type}{seq}",
            'pii_type':     pii_type, 'seq': seq, 'zone_id': zone_id,
            'risk_level':   _risk_level(pii_type),   # 위험/주의/참고
            'is_selected':  False,   # 흐름4(미리보기 버튼)에서 백엔드가 선택값만 True 로 변경
            'masked_coords': None,   # mask.py 가 마스킹 후 채울 좌표(현재는 미정 → null)
            'text':         ' '.join(texts),
            'bbox':         [min(xs1), min(ys1), max(xs2), max(ys2)],
            'polygons':     polys, 'boxes': boxes,
        })
        print(f"  🚨 [{pii_type}{seq}] [{_risk_level(pii_type)}] → 탐지")

    if not pii_groups:
        print("  ℹ️  개인정보 없음")

    # ── OCR 전체 박스 보존(비PII 포함) + is_pii 마킹 ──
    #   (수정사항1: 프레임/구역의 모든 박스를 index.json 에 그대로 병합, PII 박스만 is_pii=True)
    with open(str(json_path), encoding='utf-8') as f:
        ocr_raw = json.load(f)
    font_zones = ocr_raw.get('font_zones') or ocr_raw.get('regions', [])
    # PII 로 탐지된 박스 식별 키 집합(텍스트+좌표)
    pii_box_keys = set()
    for g in pii_groups:
        for b in g['boxes']:
            pii_box_keys.add((b['text'], b['x_min'], b['y_min'], b['x_max'], b['y_max']))
    for zone in font_zones:
        for b in zone.get('boxes', []):
            key = (b.get('text'), int(b.get('x_min', 0)), int(b.get('y_min', 0)),
                   int(b.get('x_max', 0)), int(b.get('y_max', 0)))
            b['is_pii'] = key in pii_box_keys          # 개인정보 박스만 True
            b.setdefault('is_selected', False)         # 선택 전이므로 False

    # ── 통합 result JSON (리포트 요약 + PII 그룹 + OCR 전체 박스) ──
    #   이미지는 merger 불필요 — OCR 단계에서 바로 _result.json 으로 최종 저장.
    #   (영상은 _index.json → merger → _result.json 순서)
    #   mask.py 는 이 JSON의 pii_groups[].boxes/polygons 와 '사용자 선택(is_selected)'로 마스킹을 재현.
    #   박스 오버레이 이미지 생성은 mask.py run_detail_view() 에서 수행.
    index_json = {
        'source_type':        'image',
        'source_name':        img_path.name,
        'source_stem':        img_path.stem,
        'source_file_path':   str(img_path),   # 상세보기 이미지 원본 경로
        'image_width':        image.shape[1],
        'image_height':       image.shape[0],
        'visual_pii_count':   len(pii_groups),
        'audio_pii_count':    0,               # 이미지는 음성 PII 없음
        'total_pii_count':    len(pii_groups),
        'risk_score':         _calc_risk_score(pii_groups),
        'risk_level_counts':  _build_risk_counts(pii_groups),
        'pii_groups':         pii_groups,
        'audio_pii_groups':   [],              # 이미지는 음성 PII 없음
        'ocr_data':           {'font_zones': font_zones},   # 비PII 포함 전체 박스
    }
    # 이미지는 _result.json 으로 직접 저장 (merger 단계 없이 최종 파일)
    jpath = output_dir / f"{img_path.stem}_result.json"
    with open(str(jpath), 'w', encoding='utf-8') as f:
        json.dump(index_json, f, ensure_ascii=False, indent=2)
    print(f"  🧾 result JSON → {jpath.name}  (PII {len(pii_groups)}건 / 위험도 {index_json['risk_score']}/10)")
    return index_json

# ── 영상 PII 탐지 파이프라인 ──

def _vid_frame_num(filename: str) -> int:
    """'ocr_data_f000420.json' → 420"""
    m = re.search(r'f(\d+)', str(filename))
    return int(m.group(1)) if m else 0

def _shift_boxes(boxes: list, dx: int, dy: int) -> list:
    """박스 전체를 (dx,dy) 평행이동. (역추적 소급용)"""
    out = []
    for b in boxes:
        nb = dict(b)
        nb['x_min'] = b['x_min'] + dx; nb['y_min'] = b['y_min'] + dy
        nb['x_max'] = b['x_max'] + dx; nb['y_max'] = b['y_max'] + dy
        if b.get('vertices'):
            nb['vertices'] = [{'x': v['x'] + dx, 'y': v['y'] + dy} for v in b['vertices']]
        out.append(nb)
    return out

def _overlaps_other_pii(cand_bbox, occupied_list, my_type, iou_thresh: float = 0.3) -> bool:
    """후보 박스가 같은 프레임에서 '다른 종류(type) PII'가 이미 점유한 박스와 겹치면 True.
    (역소급 시 주소를 주민번호 박스 같은 다른 PII 자리에 잘못 붙이는 것을 차단)."""
    for pt, bb in occupied_list:
        if pt == my_type:
            continue
        if _bbox_iou(cand_bbox, bb) >= iou_thresh:
            return True
    return False


def _vid_collect_pii(ocr_dir: Path) -> tuple:
    """
    OCR JSON들을 읽어 PII 이벤트 목록 + OCR 실행 프레임 집합 + 전체 박스(원본) + 임시 json 경로 반환.
    반환: (events, all_ocr_frames, ocr_frames_raw, ocr_json_files)
      events         = [(frame_idx, pii_type, matched_boxes, bbox), ...]
      ocr_frames_raw = [{'frame_idx', 'timestamp_sec', 'font_zones'}, ...]  ← index.json 병합용(비PII 포함)
      ocr_json_files = [Path, ...]  ← 병합 후 삭제할 임시 프레임 json 목록
    """
    events, all_ocr_frames, ocr_frames_raw = [], set(), []
    jsons = sorted(ocr_dir.glob("ocr_data_f*.json"), key=lambda p: _vid_frame_num(p.name))
    if not jsons:
        print(f"  ⚠️  OCR JSON 없음: {ocr_dir}")
        return events, all_ocr_frames, ocr_frames_raw, jsons
    print(f"  📂 OCR JSON {len(jsons)}개 로드 중...")

    for jf in jsons:
        fi = _vid_frame_num(jf.name)
        all_ocr_frames.add(fi)
        try:
            with open(jf, encoding='utf-8') as f:
                raw_data = json.load(f)
        except Exception as e:
            print(f"  ⚠️  JSON 로드 실패 ({jf.name}): {e}")
            continue

        # ── 전체 박스 보존(비PII 포함) — index.json 의 ocr_data.frames 로 병합 ──
        ocr_frames_raw.append({
            'frame_idx':     raw_data.get('frame_idx', fi),
            'timestamp_sec': raw_data.get('timestamp_sec', ''),
            'font_zones':    raw_data.get('font_zones') or raw_data.get('regions', []),
        })

        for zone in (raw_data.get('font_zones') or raw_data.get('regions', [])):
            zone_id = zone.get('zone_id', zone.get('region_id', 0))
            raw_boxes = zone.get('boxes', [])
            if not raw_boxes: continue

            zone_box_list = [{
                'text': b['text'],
                'x_min': int(b['x_min']), 'y_min': int(b['y_min']),
                'x_max': int(b['x_max']), 'y_max': int(b['y_max']),
                'y_center': float((b['y_min'] + b['y_max']) / 2),
                'h': float(b['y_max'] - b['y_min']),
                'angle': float(b.get('angle', 0.0)), 'prob': float(b.get('prob', 1.0)),
                'zone_id': zone_id, 'region_id': zone_id, 'vertices': b.get('vertices', None),
            } for b in raw_boxes]

            avg_angle = sum(abs(b['angle']) for b in zone_box_list) / len(zone_box_list)
            gap_ratio = 0.4 if avg_angle > 5.0 else LINE_GAP_RATIO

            lines = universal_directional_clustering(zone_box_list, line_gap_ratio=gap_ratio)
            full_text, box_spans = build_full_text(lines)
            for pii_type, _, ms, me, orig in analyze_and_mask_text_all(full_text):
                mb = [b for s, e, b in box_spans if max(s, ms) < min(e, me)]
                if not mb: continue

                # 주소: 앞뒤 비PII 토막 및 "주소" 라벨 제거
                if pii_type == "주소":
                    refined = []
                    for b in mb:
                        t = b['text'].strip()
                        if re.match(r'^[A-Za-z]+$', t) or re.search(r'\d{4}[/.-]\d{2}', t): break
                        if re.match(r'^(?:합계|총요금|수납요금|신용카드|현금|우편번호|수취인|등기번호|요금|통수|중량|종별|보통|영수증|접수일자|접수자|발송인)$', t): break
                        if re.match(r'^주소\s*:?$', t): continue
                        refined.append(b)
                    if refined:
                        mb = refined
                    else:
                        continue

                bbox = (min(b['x_min'] for b in mb), min(b['y_min'] for b in mb),
                        max(b['x_max'] for b in mb), max(b['y_max'] for b in mb))
                events.append((fi, pii_type, mb, bbox))
                print(f"    📌 Frame {fi:05d} [zone{zone_id}] [{pii_type}]: '{orig[:30]}'")

    # 역추적: 첫 keyframe 이전 동일 위치 박스 소급 (가드①: 다른 PII 박스 겹침 제외, 가드②: 텍스트 유사도 검증)
    if events:
        jsons_map = {_vid_frame_num(jf.name): jf for jf in jsons}
        first_events = {}
        for fi, pii_type, mb, bbox in events:
            if pii_type not in first_events or fi < first_events[pii_type][0]:
                first_events[pii_type] = (fi, mb, bbox)

        # 프레임별로 '이미 탐지된 PII'가 점유한 영역(가드① 판정용)
        occupied = defaultdict(list)   # {frame_idx: [(pii_type, bbox), ...]}
        for fi, pt, mb, bbox in events:
            occupied[fi].append((pt, bbox))

        backfill = []
        for pii_type, (first_fi, first_mb, first_bbox) in first_events.items():
            ref_bbox = first_bbox
            ref_text = _vid_norm_pii_text(first_mb)   # 소급 검증용 기준 텍스트(정규화)
            for prev_fi in sorted([f for f in jsons_map if f < first_fi], reverse=True):
                try:
                    with open(jsons_map[prev_fi], encoding='utf-8') as f:
                        prev_data = json.load(f)
                except Exception:
                    continue
                found, found_bbox, best_iou = False, None, 0.0
                for pz in (prev_data.get('font_zones') or prev_data.get('regions', [])):
                    for pb in pz.get('boxes', []):
                        pb_bbox = (int(pb['x_min']), int(pb['y_min']), int(pb['x_max']), int(pb['y_max']))
                        iou = _bbox_iou(ref_bbox, pb_bbox)
                        if iou < 0.3 or iou <= best_iou:
                            continue
                        # 가드①: 같은 프레임의 '다른 PII'가 점유한 박스면 제외(주민번호 자리 회피)
                        if _overlaps_other_pii(pb_bbox, occupied.get(prev_fi, []), pii_type):
                            continue
                        # 가드②: 후보 박스 텍스트가 원래 PII 텍스트와 너무 다르면 제외
                        cand_text = _norm_pii_text(pb.get('text', ''))
                        if ref_text and cand_text and \
                           SequenceMatcher(None, ref_text, cand_text).ratio() < VID_BACKFILL_TEXT_SIM:
                            continue
                        best_iou, found_bbox, found = iou, pb_bbox, True
                    if found: break
                if found:
                    ref_bbox = found_bbox
                    dx = found_bbox[0] - first_bbox[0]; dy = found_bbox[1] - first_bbox[1]
                    backfill.append((prev_fi, pii_type, _shift_boxes(first_mb, dx, dy), found_bbox))
                    print(f"    🔙 Frame {prev_fi:05d} [{pii_type}] 역소급 IoU={best_iou:.2f}")
                else:
                    break
        events = sorted(events + backfill, key=lambda e: e[0])
    return events, all_ocr_frames, ocr_frames_raw, jsons


def _vid_norm_pii_text(mb: list) -> str:
    """[영상] 추적 박스(mb)들의 텍스트를 합쳐 공백·구분자를 제거한 정규화 문자열 반환.
    인스턴스(같은 카드 등) 동일성 비교용. 예: '1234 5678 9012' → '123456789012'.
    ※ 위쪽 _norm_pii_text(s:str) 와 이름이 겹치지 않도록 _vid_ 접두사 사용(인자 타입 다름)."""
    s = ''.join(str(b.get('text', '')) for b in (mb or []))
    return re.sub(r'[\s\-./,()]', '', s)


def _vid_cluster_events(evs: list) -> list:
    """같은 type 의 이벤트들을 '정규화 텍스트 유사도'로 인스턴스별로 나눈다.
    같은 개인정보(같은 카드번호 등)는 한 묶음, 서로 다른 값(다른 카드)은 별도 묶음.
    evs: [(fi, mb, bbox), ...]  반환: [[ev,...], [ev,...], ...] (인스턴스별 이벤트 목록)."""
    clusters = []   # [{'keys': [정규화텍스트...], 'evs': [...]}], 시간순 처리
    for ev in sorted(evs, key=lambda e: e[0]):
        key = _vid_norm_pii_text(ev[1])
        best, best_r = None, 0.0
        for c in clusters:
            # 모든 멤버 텍스트와 최대 유사도 비교 (대표 1개로 고정 시 OCR 중복 인식 오류로 분리될 수 있음)
            if not key and all(not k for k in c['keys']):
                r = 1.0                          # 둘 다 빈 텍스트 → 동일 인스턴스로 간주
            else:
                r = max(SequenceMatcher(None, key, k).ratio() for k in c['keys'])
            if r > best_r:
                best_r, best = r, c
        if best is not None and best_r >= VID_INSTANCE_TEXT_SIM:
            best['evs'].append(ev)
            best['keys'].append(key)             # 멤버 텍스트 누적(다음 비교에 모두 활용)
        else:
            clusters.append({'keys': [key], 'evs': [ev]})
    return [c['evs'] for c in clusters]


def _bbox_iou(a, b) -> float:
    """두 bbox (x1,y1,x2,y2) 의 IoU(교집합/합집합)."""
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    u = area_a + area_b - inter
    return inter / u if u > 0 else 0.0


def _cluster_repr_bbox(evs):
    """클러스터 이벤트(ev=(fi,mb,bbox))들의 대표 bbox(좌표별 중앙값) — 한두 프레임 튐에 강건."""
    n = len(evs); m = n // 2
    xs1 = sorted(e[2][0] for e in evs); ys1 = sorted(e[2][1] for e in evs)
    xs2 = sorted(e[2][2] for e in evs); ys2 = sorted(e[2][3] for e in evs)
    return (xs1[m], ys1[m], xs2[m], ys2[m])


def _cluster_zone(evs):
    """클러스터 이벤트들의 대표 zone_id(매칭 박스 mb 의 최빈 zone). 박스에 zone 정보 없으면 None."""
    from collections import Counter
    zs = []
    for e in evs:
        mb = e[1]
        if mb:
            z = mb[0].get('zone_id')
            if z is not None:
                zs.append(z)
    if not zs:
        return None
    return Counter(zs).most_common(1)[0][0]


def _merge_clusters_by_location(clusters: list, fps: float) -> list:
    """텍스트로 갈린 클러스터를 '위치(bbox IoU) + 시간 근접' 기준으로 2차 병합.
    OCR 이 같은 카드를 다르게 읽어 분리된 것을 복구한다. 서로 다른 위치의 PII 는
    IoU 가 낮아 병합되지 않으므로, 진짜 다른 개인정보는 그대로 분리 유지된다."""
    clusters = [list(c) for c in clusters]
    gap_max = int(max(1.0, fps) * VID_INSTANCE_TIME_GAP_SEC)
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                fi_i = [e[0] for e in clusters[i]]; fi_j = [e[0] for e in clusters[j]]
                # 시간 간격: 두 프레임 구간이 겹치면 0, 아니면 떨어진 프레임 수
                gap = max(0, max(min(fi_i), min(fi_j)) - min(max(fi_i), max(fi_j)))
                if gap > gap_max:
                    continue
                iou = _bbox_iou(_cluster_repr_bbox(clusters[i]), _cluster_repr_bbox(clusters[j]))
                if iou >= VID_INSTANCE_IOU_MERGE:
                    # zone이 명확히 다르면 별도 PII로 유지 (같은 위치라도 zone 다름 = 다른 개인정보)
                    zi, zj = _cluster_zone(clusters[i]), _cluster_zone(clusters[j])
                    if zi is not None and zj is not None and zi != zj:
                        continue
                    clusters[i].extend(clusters[j]); clusters.pop(j)
                    changed = True; break
            if changed:
                break
    return clusters


def _merge_evs_by_frame(inst_evs: list) -> list:
    """같은 프레임의 여러 매칭(부분 박스)을 '박스 합집합'으로 통합 → 1프레임당 1 keyframe.
    OCR 이 카드번호를 여러 박스로 쪼개 읽어 프레임마다 일부만 잡힌 것을, 같은 프레임 안에서
    모두 합쳐 카드번호 전체를 감싸도록 한다. 위치병합으로 생긴 같은 프레임 중복 keyframe 도 제거.
    반환: [(fi, 합친_boxes, 합집합_bbox), ...] (프레임순)."""
    by_fi = defaultdict(list)
    for ev in inst_evs:
        by_fi[ev[0]].append(ev)
    out = []
    for fi in sorted(by_fi):
        evs_f = by_fi[fi]
        boxes, seen = [], set()
        for _fi, mb, _bb in evs_f:
            for b in (mb or []):
                key = (b.get('x_min'), b.get('y_min'), b.get('x_max'), b.get('y_max'), b.get('text'))
                if key not in seen:
                    seen.add(key); boxes.append(b)
        # bbox 는 같은 프레임 매칭들의 bbox 외접(합집합) → 카드번호 전체를 감싸는 범위
        x1 = min(e[2][0] for e in evs_f); y1 = min(e[2][1] for e in evs_f)
        x2 = max(e[2][2] for e in evs_f); y2 = max(e[2][3] for e in evs_f)
        out.append((fi, boxes, (x1, y1, x2, y2)))
    return out


def _vid_build_pii_groups(pii_events: list, fps: float = 30.0) -> list:
    """
    영상 PII 이벤트를 '인스턴스(그룹)' 단위로 묶어 리포트용 메타 생성.
    ※ 같은 type 이라도 텍스트가 다른 개인정보(예: 서로 다른 카드)는 별도 그룹으로 분리.
    반환: [{pii_id, pii_label, pii_type, seq, zone_id, rep_frame, rep_mb, rep_bbox, frames, events}, ...]
    """
    by_type = defaultdict(list)
    for fi, pt, mb, bbox in pii_events:
        by_type[pt].append((fi, mb, bbox))

    type_seq, groups = defaultdict(int), []
    for pt, evs in by_type.items():
        # 1차: 텍스트 유사도로 인스턴스 분리 → 2차: 같은 구역(위치 IoU)+시간 근접이면 재병합
        #   (OCR 이 같은 카드를 다르게 읽어 쪼개진 그룹을 위치 기준으로 다시 합쳐 박스 중복 방지)
        text_clusters = _vid_cluster_events(evs)
        for inst_evs in _merge_clusters_by_location(text_clusters, fps):
            # 3차: 같은 프레임의 부분 박스들을 합집합으로 통합(카드번호 전체 범위 + 중복 keyframe 제거)
            inst_evs = _merge_evs_by_frame(inst_evs)
            type_seq[pt] += 1
            seq = type_seq[pt]
            rep_fi, rep_mb, rep_bbox = max(inst_evs, key=lambda e: len(e[1]))  # 박스 최다 keyframe
            zone_id = rep_mb[0].get('zone_id', 0) if rep_mb else 0
            groups.append({
                'pii_id': f"{pt}_{seq}", 'pii_label': f"{pt}{seq}", 'pii_type': pt, 'seq': seq,
                'zone_id': zone_id, 'rep_frame': rep_fi, 'rep_mb': rep_mb, 'rep_bbox': rep_bbox,
                'frames': sorted(e[0] for e in inst_evs),
                'events': sorted(inst_evs, key=lambda e: e[0]),  # (fi, mb, bbox) — mask.py 추적 앵커
            })
    return groups


def analyze_video(video_name_or_path, ocr_dir: Path = None, output_dir: Path = None):
    """[영상] OCR JSON → PII 탐지 → 통합 index JSON 생성 (1~2단계만).
    ※ 상세보기 오버레이 트랙 생성·박스 표시 이미지는 3단계(colab_pipeline_mask.py run_detail_view)에서 수행.

    video_name_or_path: 실제 파일 경로(Path) 또는 영상 이름(str — 하위 호환용).
      · Path 객체로 전달하면 INPUT_VIDEO_DIR 탐색을 건너뛰고 그 경로를 그대로 사용.
      · str 전달 시 기존처럼 INPUT_VIDEO_DIR 에서 파일을 찾음(폴백 포함).
    ocr_dir:     OCR JSON 폴더(기본: OCR_VIDEO_OUTPUT/{stem}).
    output_dir:  결과 JSON 저장 폴더(기본: OUTPUT_DIR).
    """
    # ── 영상 파일 경로 확정 ──
    if isinstance(video_name_or_path, Path) and video_name_or_path.is_file():
        # 실제 파일 경로가 넘어온 경우 — 탐색 없이 그대로 사용
        video_path = video_name_or_path
        video_name = video_path.stem
    else:
        # 이름만 전달된 경우(하위 호환) — INPUT_VIDEO_DIR 에서 탐색
        video_name = str(video_name_or_path)
        video_dir  = INPUT_VIDEO_DIR
        video_path = None
        for ext in ('.mp4', '.avi', '.mov', '.mkv', '.MP4', '.AVI'):
            p = video_dir / f"{video_name}{ext}"
            if p.exists():
                video_path = p; break
        if video_path is None:
            cands = sorted(video_dir.glob("*.mp4")) + sorted(video_dir.glob("*.avi"))
            if not cands:
                print(f"❌ 영상 파일 없음: {video_dir}"); return
            video_path = cands[0]; video_name = video_path.stem

    # ── 경로 기본값 ──
    if ocr_dir is None:
        ocr_dir = OCR_VIDEO_OUTPUT / video_name
    if output_dir is None:
        output_dir = OUTPUT_DIR
    out_dir = output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}\n🎬 영상 PII 탐지: {video_name}\n{'='*60}")
    print(f"  영상: {video_path}\n  OCR : {ocr_dir}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"❌ 영상 열기 실패: {video_path}"); return
    fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    print(f"  {width}×{height} @ {fps:.2f}fps | {total_frames}프레임 ({total_frames/fps:.1f}초)")

    # PII 탐지 (OCR JSON → 정규식)
    print(f"\n  [탐지] PII 탐지...")
    pii_events, all_ocr_frames, ocr_frames_raw, ocr_json_files = _vid_collect_pii(ocr_dir)
    # PII 0건이어도 index.json 항상 생성 (이미지와 동일 정책)
    if not pii_events:
        print("  ℹ️  개인정보 없음 — PII 없이 OCR 전체 박스만 index.json 에 기록")
    else:
        from collections import Counter
        print(f"\n  → PII 이벤트 {len(pii_events)}건")
        for t, c in Counter(e[1] for e in pii_events).items():
            print(f"     {t}: {c}건")

    # PII 그룹 빌드
    print(f"\n  [리포트] PII 그룹 생성...")
    pii_groups = _vid_build_pii_groups(pii_events, fps)

    cap = cv2.VideoCapture(str(video_path))
    report_groups = []
    for g in pii_groups:
        cap.set(cv2.CAP_PROP_POS_FRAMES, g['rep_frame'])
        ret, frame = cap.read()
        if not ret:
            continue
        polys, boxes_ser = [], []
        for line_boxes in universal_directional_clustering(g['rep_mb']):
            poly = get_polygon_contour(line_boxes)
            if len(poly):
                polys.append(poly[0].tolist())
            for b in line_boxes:
                boxes_ser.append({'text': b['text'],
                                  'x_min': b['x_min'], 'y_min': b['y_min'],
                                  'x_max': b['x_max'], 'y_max': b['y_max'],
                                  'vertices': b.get('vertices')})
        bx = g['rep_bbox']
        # mask.py 가 OCR/정규식 재실행 없이 추적할 수 있도록 '모든 keyframe의 박스'를 직렬화(추적 앵커)
        keyframes = [{
            'frame': int(kf_fi), 'timestamp': round(kf_fi / fps, 3),
            'bbox': [int(kf_bbox[0]), int(kf_bbox[1]), int(kf_bbox[2]), int(kf_bbox[3])],
            'boxes': [{'text': b['text'],
                       'x_min': int(b['x_min']), 'y_min': int(b['y_min']),
                       'x_max': int(b['x_max']), 'y_max': int(b['y_max']),
                       'vertices': b.get('vertices')} for b in kf_mb],
        } for kf_fi, kf_mb, kf_bbox in g['events']]
        report_groups.append({
            'pii_id':        g['pii_id'],
            'pii_label':     g['pii_label'],
            'pii_type':      g['pii_type'],
            'seq':           g['seq'],
            'zone_id':       g['zone_id'],
            'risk_level':    _risk_level(g['pii_type']),  # 위험/주의/참고
            'is_selected':   False,   # 흐름4(미리보기 버튼)에서 백엔드가 선택값만 True 로 변경
            'masked_coords': None,    # mask.py 가 마스킹 후 채울 좌표(현재는 미정 → null)
            'rep_frame':     g['rep_frame'],
            'rep_timestamp': round(g['rep_frame'] / fps, 3),
            'bbox':          [bx[0], bx[1], bx[2], bx[3]],
            'polygons':      polys,
            'boxes':         boxes_ser,
            'frames':        g['frames'],
            'keyframes':     keyframes,   # ← mask.py 영상 추적 입력(전 keyframe 박스/좌표/시간)
            # 'track' 필드 없음 — 상세보기 오버레이는 mask.py run_detail_view()에서 생성
        })
        print(f"  🚨 [{g['pii_label']}] [{_risk_level(g['pii_type'])}] rep={round(g['rep_frame']/fps,1)}s → 탐지")
    cap.release()

    # ── OCR 전체 박스(비PII 포함)에 is_pii 마킹 ──
    #   PII 이벤트의 박스를 (frame, text, 좌표) 키로 식별 → 해당 박스만 is_pii=True
    pii_box_keys = set()
    for fi, _pt, mb, _bbox in pii_events:
        for b in mb:
            pii_box_keys.add((int(fi), b.get('text'),
                              int(b.get('x_min', 0)), int(b.get('y_min', 0)),
                              int(b.get('x_max', 0)), int(b.get('y_max', 0))))
    for fr in ocr_frames_raw:
        fr_idx = int(fr.get('frame_idx', 0))
        for zone in fr.get('font_zones', []):
            for b in zone.get('boxes', []):
                key = (fr_idx, b.get('text'),
                       int(b.get('x_min', 0)), int(b.get('y_min', 0)),
                       int(b.get('x_max', 0)), int(b.get('y_max', 0)))
                b['is_pii'] = key in pii_box_keys
                b.setdefault('is_selected', False)

    pii_g_list = [{'pii_type': r['pii_type']} for r in report_groups]
    # ── 통합 index JSON (리포트 요약 + PII 그룹 + OCR 전체 박스) ──
    index_json = {
        'source_type':       'video',
        'source_name':       video_name,
        'source_stem':       video_name,
        'image_width':       width,
        'image_height':      height,
        'fps':               fps,
        'total_frames':      total_frames,
        'total_pii_count':   len(report_groups),
        'risk_score':        _calc_risk_score(pii_g_list),
        'risk_level_counts': _build_risk_counts(pii_g_list),
        'pii_groups':        report_groups,
        'ocr_data':          {'frames': ocr_frames_raw},   # 비PII 포함 전 프레임 박스
    }
    jpath = out_dir / f"{video_name}_index.json"  # output_dir 기준 저장 (analyze_video 인수)
    with open(str(jpath), 'w', encoding='utf-8') as f:
        json.dump(index_json, f, ensure_ascii=False, indent=2)
    print(f"\n  🧾 통합 index JSON: {len(report_groups)}개 그룹 → {jpath.name}"
          f"\n     위험도 {index_json['risk_score']}/10 | {index_json['risk_level_counts']}"
          f"\n     ※ 상세보기 오버레이·박스 이미지는 mask.py run_detail_view()에서 생성")

    # 임시 프레임 json 삭제 (region jpg·txt는 디버깅용 유지)
    merged_frames = {int(fr.get('frame_idx', -1)) for fr in ocr_frames_raw}
    deleted = 0
    for jf in ocr_json_files:
        if _vid_frame_num(jf.name) in merged_frames:
            try:
                jf.unlink(); deleted += 1
            except Exception as e:
                print(f"  ⚠️  임시 json 삭제 실패 ({jf.name}): {e}")
    print(f"     🧹 임시 프레임 json {deleted}개 삭제 (region jpg·txt 는 디버깅용 유지)\n{'='*60}")
    return index_json


# ── 통합 실행 파이프라인 진입점 ──
def _run_one(p: Path, progress_callback=None):
    """단일 파일 1건: OCR 먼저(1단계) → PII 탐지+리포트 JSON(2단계). 본 마스킹은 mask.py."""
    ext = p.suffix.lower()
    if OCR_Setting is None:
        print("[오류] OCR_Setting 모듈 없음 — OCR_Setting.py를 같은 폴더에 두세요."); return
    if ext in VIDEO_EXTS:
        print(f"\n▶ OCR 단계 — {p.name}")
        OCR_Setting.process_video(p, OCR_VIDEO_OUTPUT, progress_callback=progress_callback)        # OCR JSON 생성
        print(f"\n▶ PII 탐지·리포트 단계 — {p.name}")
        # 실제 파일 Path 와 OCR 폴더를 직접 전달 — INPUT_VIDEO_DIR 폴백 탐색 방지
        res = analyze_video(p,
                             ocr_dir=OCR_VIDEO_OUTPUT / p.stem,
                             output_dir=OUTPUT_DIR)
        import shutil
        shutil.rmtree(OCR_VIDEO_OUTPUT / p.stem, ignore_errors=True)
        return res
    elif ext in IMG_EXTS:
        print(f"\n▶ OCR 단계 — {p.name}")
        OCR_Setting.process_image(p, OCR_IMAGE_OUTPUT)
        print(f"\n▶ PII 탐지·리포트 단계 — {p.name}")
        res = analyze_image_one(p, OCR_IMAGE_OUTPUT, OUTPUT_DIR)

        import shutil
        shutil.rmtree(OCR_IMAGE_OUTPUT / p.stem, ignore_errors=True)
        return res
    else:
        print(f"[!] 지원하지 않는 형식: {ext}")


def run_pipeline(input_path, progress_callback=None):
    """
    [진입점] 파일 1개 또는 폴더를 받아 OCR → PII 탐지 → 리포트 JSON 자동 실행.
      • 파일 경로  : 그 파일 1건 처리 (이미지/영상 자동 구분)
      • 폴더 경로  : 폴더 안 모든 이미지/영상 처리
      • 이름만(확장자X): 영상 폴더에서 매칭 파일 탐색
    반환: 단일 파일이면 index_json(dict), 폴더면 None(개별 {stem}_index.json은 OUTPUT_DIR에 저장).
    예) run_pipeline("/content/drive/.../카드_영상1.mp4")
        run_pipeline("/content/drive/.../test_image_file")   # 폴더 전체
    ※ 상세보기·미리보기·본마스킹은 colab_pipeline_mask.py 가 {stem}_index.json 을 입력으로 이어받는다.
    """
    p = Path(input_path)
    if p.is_dir():
        targets = sorted([f for f in p.iterdir() if f.suffix.lower() in IMG_EXTS + VIDEO_EXTS])
        if not targets:
            print(f"[!] 폴더에 처리할 파일 없음: {p}"); return
        print(f"📂 폴더 처리: {len(targets)}개")
        for f in targets:
            _run_one(f, progress_callback)
    elif p.is_file():
        _run_one(p, progress_callback)
    else:
        # 확장자 없이 이름만 → 영상 폴더에서 탐색
        cand = next((INPUT_VIDEO_DIR / f"{p.name}{e}"
                     for e in VIDEO_EXTS if (INPUT_VIDEO_DIR / f"{p.name}{e}").exists()), None)
        if cand:
            _run_one(cand, progress_callback)
        else:
            print(f"[!] 경로/파일을 찾을 수 없습니다: {p}")


# 3~7단계(상세보기·미리보기·마스킹)는 colab_pipeline_mask.py 에서 {stem}_index.json 을 입력으로 처리


# ── 테스트 실행 (경로는 상단 환경설정에서 변경) ──
if __name__ == "__main__":
    cli_args = [a for a in sys.argv[1:] if not a.startswith('-') and not a.endswith('.json')]
    _rep = run_pipeline(cli_args[0] if cli_args else TEST_TARGET)  # CLI 인수 우선, 없으면 테스트 경로
    print(f"\n{'='*62}\n🎉 OCR·탐지·리포트 완료!"
          f"\n{'='*62}")
