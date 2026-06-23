# # Garim STT 파이프라인
# 음성 → STT(Whisper) → PII 정규식 탐지 → pii_segments 반환

# 필요 패키지 설치
import subprocess, sys
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "faster-whisper", "pydub",
     "paddlepaddle", "paddleocr", "scenedetect[opencv]", "pandas"],
    check=True,
)
subprocess.run(["apt-get", "install", "-y", "-q", "ffmpeg"], check=True)

# Config

import os
import re
import subprocess
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

# ===== (환경설정) =====
# 1. 모델 설정
WHISPER_MODEL_SIZE = "large"  # 사용할 Whisper 모델 체급 (base / small / medium / large)
WHISPER_MODEL_PATH = "/content/drive/MyDrive/final_PJ_model/STT_Model/Large" # 구글 드라이브 내 오프라인 모델 경로 (없을 시 자동 다운로드)

# 2. STT 성능 및 가속 설정 (VRAM 및 속도 제어)
STT_BATCH_SIZE     = 16        # 배치 처리 단위 (숫자가 클수록 빠르나 VRAM을 더 사용함. L4/T4에서는 16~32 권장)
STT_BEAM_SIZE      = 5         # 탐색 범위 (기본 5. 숫자를 2~3으로 줄이면 정확도 손실 없이 연산 속도가 대폭 향상됨)
STT_LANGUAGE       = "ko"      # 음성 인식 언어 고정 (한국어로 고정 시 인식률 향상 및 처리 속도 증가)

# 3. 경로 설정
AUDIO_DIR          = "/content/drive/MyDrive/final_PJ_model/output_file"  # 추출된 임시 오디오 저장 경로 (index.json과 동일 폴더)
VISUAL_OCR_DIR     = "/content/drive/MyDrive/final_PJ_model/output_file"  # 임시 시각 정보 저장 경로

# 4. 탐지 구간 및 마스킹 설정
BEEP_FREQ          = 1000       # 삐 소리(Beep)의 주파수 (Hz)
BEEP_GAIN_DB       = -8         # 삐 소리(Beep)의 볼륨 크기 (dB)
PAD_SEC            = 0.08       # 개인정보가 탐지된 단어의 앞뒤 여유 시간 (초 단위로 조금 넉넉하게 마스킹)

# 5. 테스트 환경 설정 (실제 서버 구동시 제거 예정)
TEST_MEDIA_PATH    = "/content/drive/MyDrive/final_PJ_model/test_video_file/카드_음성_영상1.mp4" # 테스트에 사용할 미디어 파일 하드코딩 경로
# ==================================

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(VISUAL_OCR_DIR, exist_ok=True)
print(f"Pipeline Config 로드 | 모델: {WHISPER_MODEL_SIZE}")


# PipelineContext / Analyzer 인터페이스
@dataclass
class PipelineContext:
    job_id: str
    upload_id: str
    file_path: str
    media_type: str | None = None
    results: dict = field(default_factory=dict)
    progress_fn: Callable | None = None   # report_progress(job_id, stage, s_pct, t_pct, msg)
    cancel_fn:   Callable | None = None   # check_cancel(job_id) -> bool

    def report(
        self,
        stage: str,
        stage_pct: int,
        total_pct: int,
        msg: str | None = None,
    ) -> None:
        if self.progress_fn:
            self.progress_fn(self.job_id, stage, stage_pct, total_pct, msg)

    def is_cancelled(self) -> bool:
        return bool(self.cancel_fn and self.cancel_fn(self.job_id))


class Analyzer:
    """모든 analyzer의 기반 클래스. stage_name/total_start/total_end 설정 후 run() 구현."""

    stage_name:  str = "unknown"
    total_start: int = 0
    total_end:   int = 100

    def run(self, input_path: str, ctx: PipelineContext) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__}.run() 미구현")


print("PipelineContext / Analyzer 인터페이스 로드 완료")


# PII 탐지 헬퍼 (정규식 패턴 + word timestamp 매칭)


# ── 정규식 패턴 ────────────────────────────────────────────────────

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
    # [개선] 기존엔 앞자리가 '0+아무2자리'(014 등도 통과) + 뒷자리 4자리가 '선택적'이라
    #   신청서 표의 항목번호('014','015') 등이 전화번호로 오탐됐음.
    #   → 앞자리를 휴대폰(01X: 0+1+[0/1/6/7/8/9]) 또는 (+)82+1X 로 제한하고, 뒷자리 4자리를 '필수'화.
    #   한글/음성 표기(공일공·일이삼사 등)와 OCR오인식(영/공/빵/oO)은 그대로 유지. (report 와 동일)
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
    ("카드번호", re.compile(r'\b\d{4}[-\s]*\d{4}[-\s]*\d{4}[-\s]*\d{4}\b')),
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
                # 1-A: '도/시/군'으로 시작하면 뒤에 반드시 하위 행정구역(구/동/로/길/읍/면)이 1개 이상 와야 함 (예: '서울시 강남구', '수원시 영통동', '가평군 청평면')
                # (오탐지 방지: '국빈시 2009' 처럼 시 + 숫자 단독 등장 차단)
                r'(?:'
                    r'(?:(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|경상|전라)[가-힣]{0,4}?(?:특별시|광역시|특별자치시|도|특별자치도)?[\s,]+)?'
                    r'(?:[가-힣A-Za-z0-9]{1,10}(?:시|도|군)[\s,]+)'
                    r'(?:[가-힣A-Za-z0-9]{1,10}(?:군|구|동|대로|로|길|번길|읍|면|리|가)[\s,]+)+'
                r')'
                r'|'
                # 1-B: '구/동/읍/면'으로 시작하면 단독으로 숫자가 와도 허용 (예: '강남구 123', '신림동 123')
                r'(?:'
                    r'(?:[가-힣A-Za-z0-9]{1,10}(?:구|동|읍|면)[\s,]+)'
                    r'(?:[가-힣A-Za-z0-9]{1,10}(?:동|대로|로|길|번길|리|가)[\s,]+)*'
                r')'
            r')'
            r'|'
            # 분기 2: 예외적 허용 (OO로 OO길) - 시/구가 없더라도 정확히 '로'와 '길'이 연달아 나오고 뒤에 숫자가 오는 경우
            r'(?:'
                r'[가-힣A-Za-z0-9]{2,10}(?<!으로)(?:대로|로)[\s,]+[가-힣0-9]{1,10}(?:길|번길)(?=[ \t,.]+(?:[가-힣A-Za-z0-9]{1,10}\s*)?\d+)'
            r')'
        r')'
        
        # [공통 부가정보 (지번, 아파트, 층, 호 등)] -> 필수 항목으로 변경 (옵션 ? 제거하여 '신림동' 등 단독 오탐 원천 차단)
        r'(?:'
            r'[ \t,.]*' 
            r'(?:'
                # [케이스 A] 정상 번지수(숫자) + 부가정보
                r'(?:산)?\d+(?:-\d+)?(?:[ \t,.]*(?:번지|번길|호))?'
                r'(?:'
                    r'[ \t,.]*'
                    r'(?:\([가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                    r'[ \t,.]*'
                    r'(?:[가-힣A-Za-z0-9]+(?:아파트|빌라|빌딩|타워|파크|맨션|하이츠|힐|캐슬|레지던스|오피스텔|프라자|센터|타운|마을))?'
                    r'[ \t,.]*'
                    r'(?:(?:[가-힣0-9]+동)?[ \t,.]*(?:\d+[A-Za-z가-힣]*호|\d+층|\d+-\d+호|B\d+층|지하\d+층))?'
                    r'[ \t,.]*'
                    r'(?:\([가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                r'){0,2}'
                
                r'|'
                
                # [케이스 B] 번지수 누락 + 곧바로 아파트/빌딩 등 (숫자가 포함되거나 명확한 건물명)
                r'(?:'
                    r'[ \t,.]*'
                    r'(?:\([가-힣A-Za-z0-9, \t]{1,20}(?:동|호|아파트|빌라|빌딩|타워|파크|맨션|오피스텔|타운|마을|센터|프라자|캐슬|레지던스)(?:\))?)?'
                    r'[ 	,.]*'
                    r'(?:[가-힣A-Za-z0-9]+(?:아파트|빌라|빌딩|타워|파크|맨션|하이츠|힐|캐슬|레지던스|오피스텔|프라자|센터|타운))'
                    r'[ 	,.]*'
                    r'(?:(?:[가-힣0-9]+동)?[ 	,.]*(?:\d+[A-Za-z가-힣]*호|\d+층|\d+-\d+호|B\d+층|지하\d+층))?'
                r')'
            r')'
        r')'
        
        r')'
        # [분기 3 보강 — 사용자 규칙] 'OO시 + 중간(구/동으로 끝나거나 6글자 이내) + XX로 + 숫자'.
        #   기존 분기가 놓치는 '울산시 남구 33로 78'(숫자로 시작 도로명), '세종시 도음 3로 90'
        #   (구/동 없는 중간어)을 포착. STT 는 중복제거가 없어 별도 패턴 대신 기존 패턴 안에 OR 로
        #   합쳐 한 번만 매칭(중복 segment 방지).
        r'|(?:[가-힣]{2,3}시[\s,]+(?:[가-힣A-Za-z0-9]{1,6}[\s,]+){1,2}[가-힣0-9]{1,10}로[\s,]*\d+)',
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
]

# ── 텍스트 정규화 ──────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\-\.\,\:\;]", "", text or "")

def _only_digits(text: str) -> str:
    # 한글 발음 숫자(공일공 등)를 아라비아 숫자로 변환 후 숫자만 반환
    kor_num_map = {
        '공': '0', '영': '0', '빵': '0', 'o': '0', 'O': '0',
        '하나': '1', '일': '1',
        '둘': '2', '이': '2',
        '셋': '3', '삼': '3',
        '넷': '4', '사': '4',
        '다섯': '5', '오': '5',
        '여섯': '6', '육': '6', '륙': '6',
        '일곱': '7', '칠': '7',
        '여덟': '8', '팔': '8',
        '아홉': '9', '구': '9'
    }
    t = text or ""
    for k, v in kor_num_map.items():
        t = t.replace(k, v)
    return re.sub(r"\D", "", t)

# ── word timestamp 정밀 매칭 ───────────────────────────────────────
# words: [{"word": str, "start": float, "end": float}, ...]

def _find_entity_time(entity_text: str, words: list, pad_sec: float = PAD_SEC) -> dict | None:
    if not words:
        return None
    entity_norm = _normalize_text(entity_text)
    if not entity_norm:
        return None
    max_window = min(12, len(words))
    best = None
    best_score = 0.0
    for size in range(1, max_window + 1):
        for i in range(len(words) - size + 1):
            chunk = words[i:i + size]
            chunk_text = "".join(w["word"] for w in chunk)
            chunk_norm = _normalize_text(chunk_text)
            if not chunk_norm:
                continue
            score = SequenceMatcher(None, entity_norm, chunk_norm).ratio()
            if entity_norm in chunk_norm or chunk_norm in entity_norm:
                score = max(score, 0.95)
            if score > best_score:
                best_score = score
                best = {
                    "start": max(0.0, float(chunk[0]["start"]) - pad_sec),
                    "end": float(chunk[-1]["end"]) + pad_sec,
                    "match_score": round(score, 4),
                }
    return best if best and best_score >= 0.72 else None


def _find_phone_time(phone_text: str, words: list, pad_sec: float = PAD_SEC) -> dict | None:
    if not words:
        return None
    target_digits = _only_digits(phone_text)
    if not target_digits or len(target_digits) < 9:
        return None
    max_window = min(16, len(words))
    best = None
    best_score = 0.0
    for size in range(1, max_window + 1):
        for i in range(len(words) - size + 1):
            chunk = words[i:i + size]
            chunk_digits = _only_digits("".join(w["word"] for w in chunk))
            if not chunk_digits:
                continue
            if target_digits == chunk_digits:
                return {
                    "start": max(0.0, float(chunk[0]["start"]) - pad_sec),
                    "end": float(chunk[-1]["end"]) + pad_sec,
                    "match_score": 1.0,
                }
            score = SequenceMatcher(None, target_digits, chunk_digits).ratio()
            if target_digits in chunk_digits or chunk_digits in target_digits:
                score = max(score, min(len(target_digits), len(chunk_digits)) / len(target_digits))
            if score > best_score:
                best_score = score
                best = {
                    "start": max(0.0, float(chunk[0]["start"]) - pad_sec),
                    "end": float(chunk[-1]["end"]) + pad_sec,
                    "match_score": round(score, 4),
                }
    return best if best and best_score >= 0.85 else None


print("PII 탐지 헬퍼 로드 완료")


# Analyzers
class AudioExtractAnalyzer(Analyzer):
    """ffmpeg 로 영상에서 16kHz 모노 WAV 추출 (STT 입력용)"""

    stage_name  = "audio_extract"
    total_start = 40
    total_end   = 48

    def run(self, input_path: str, ctx: PipelineContext) -> dict:
        ctx.report(self.stage_name, 0, self.total_start, "오디오 추출 시작")

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1", input_path],
            capture_output=True, text=True,
        )
        if "audio" not in probe.stdout:
            ctx.report(self.stage_name, 100, self.total_end, "오디오 스트림 없음")
            return {"audio_path": None, "has_audio": False}

        audio_path = os.path.join(AUDIO_DIR, f"{ctx.upload_id}.wav")
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             audio_path],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg 오디오 추출 실패: {r.stderr[-300:]}")

        size_mb = os.path.getsize(audio_path) / 1024 / 1024
        ctx.report(self.stage_name, 100, self.total_end,
                   f"오디오 추출 완료 ({size_mb:.1f} MB)")
        return {"audio_path": audio_path, "has_audio": True}



class STTAnalyzer(Analyzer):
    """faster-whisper 음성 인식 — word timestamps 포함 (PII 탐지에 필요)"""

    stage_name  = "stt"
    total_start = 48
    total_end   = 68

    def __init__(self):
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            # bfloat16 호환성 문제 방지 → float16 고정
            compute_type = "float16" if device == "cuda" else "int8"

            model_path_to_load = WHISPER_MODEL_SIZE
            if os.path.exists(WHISPER_MODEL_PATH) and os.path.exists(os.path.join(WHISPER_MODEL_PATH, "model.bin")):
                model_path_to_load = WHISPER_MODEL_PATH
                print(f"[STT] 로컬 모델 로드: {WHISPER_MODEL_PATH} ({device}/{compute_type})")
            else:
                print(f"[STT] 로컬 모델 없음 → '{WHISPER_MODEL_SIZE}' 온라인 다운로드 ({device}/{compute_type})")

            self._model = WhisperModel(
                model_path_to_load, device=device, compute_type=compute_type
            )
        return self._model

    def run(self, input_path: str, ctx: PipelineContext) -> dict:
        ctx.report(self.stage_name, 0, self.total_start, "STT 시작")

        audio_result = ctx.results.get("audio_extract", {})
        if not audio_result.get("has_audio"):
            ctx.report(self.stage_name, 100, self.total_end, "오디오 없음 — STT 건너뜀")
            return {"language": "none", "full_text": "", "segments": []}

        audio_path = audio_result["audio_path"]
        ctx.report(self.stage_name, 10, self.total_start + 4, "WhisperModel 로드 중")
        model = self._load_model()

        ctx.report(self.stage_name, 30, self.total_start + 10, "음성 인식 중 (배치 처리 가속 적용)")
        
        from faster_whisper import BatchedInferencePipeline
        batched_pipeline = BatchedInferencePipeline(model=model)
        
        segments_iter, info = batched_pipeline.transcribe(
            audio_path,
            language=STT_LANGUAGE,
            batch_size=STT_BATCH_SIZE,
            beam_size=STT_BEAM_SIZE,
            word_timestamps=True  # PII 구간 정밀 매칭에 필수
        )
        raw_segments = list(segments_iter)

        segments = []
        for i, seg in enumerate(raw_segments):
            words = []
            if seg.words:
                words = [
                    {"word": w.word, "start": float(w.start), "end": float(w.end)}
                    for w in seg.words
                ]
            segments.append({
                "id": i,
                "start_ms": int(seg.start * 1000),
                "end_ms":   int(seg.end   * 1000),
                "text":     seg.text.strip(),
                "words":    words,
                "no_speech_prob": round(float(getattr(seg, "no_speech_prob", 0.0)), 4),
            })

        full_text = " ".join(s["text"] for s in segments)
        ctx.report(self.stage_name, 100, self.total_end,
                   f"STT 완료 — {len(segments)}개 세그먼트, 언어: {info.language}")
        return {
            "language": info.language,
            "full_text": full_text,
            "segments": segments,
        }



class PIIDetectAnalyzer(Analyzer):
    """Regex + NER + word timestamp 정밀 매칭으로 개인정보 구간 탐지

    입력: ctx.results["stt"]["segments"]  (words 필드 포함)
    출력: {"pii_count": int, "pii_segments": list[dict]}

    pii_segments 항목 형식:
        start_time_sec, end_time_sec, detected_text, label, confidence
    """

    stage_name  = "pii_detect"
    total_start = 68
    total_end   = 78

    _BEEP_TYPES = {"주민등록번호", "외국인등록번호", "여권번호", "운전면허번호", "전화번호", "카드번호", "계좌번호", "이메일", "건강보험증번호", "생년월일", "나이", "주소", "차량번호"}

    def _detect_regex(self, text: str) -> list:
        results = []
        for pii_type, pattern in PII_PATTERNS:
            for match in pattern.finditer(text):
                results.append({"type": pii_type, "text": match.group(0).strip(),
                                 "confidence": 0.95, "source": "regex"})
        return results

    def run(self, input_path: str, ctx: PipelineContext) -> dict:
        ctx.report(self.stage_name, 0, self.total_start, "개인정보 탐지 시작")

        stt_result = ctx.results.get("stt", {})
        segments   = stt_result.get("segments", [])
        if not segments:
            ctx.report(self.stage_name, 100, self.total_end, "STT 결과 없음 — 탐지 건너뜀")
            return {"pii_count": 0, "pii_segments": []}

        pii_segments = []
        n = len(segments)
        for idx, seg in enumerate(segments):
            text  = seg.get("text", "").strip()
            words = seg.get("words", [])
            if not text:
                continue

            for ent in self._detect_regex(text):
                if ent["type"] not in self._BEEP_TYPES or not ent["text"]:
                    continue
                if ent["type"] == "전화번호":
                    t = _find_phone_time(ent["text"], words)
                else:
                    t = _find_entity_time(ent["text"], words)
                if t is None:
                    continue
                pii_segments.append({
                    "start_time_sec": round(t["start"], 3),
                    "end_time_sec":   round(t["end"],   3),
                    "detected_text":  ent["text"],
                    "label":          ent["type"],
                    "confidence":     round(float(ent.get("confidence", 0.0)), 4),
                })

            stage_pct = int(10 + 85 * (idx + 1) / n)
            total_pct = int(self.total_start + (self.total_end - self.total_start) * (idx + 1) / n)
            ctx.report(self.stage_name, stage_pct, total_pct)

        ctx.report(self.stage_name, 100, self.total_end,
                   f"개인정보 탐지 완료 — {len(pii_segments)}건")
        return {"pii_count": len(pii_segments), "pii_segments": pii_segments}




print("Analyzer 클래스 로드 완료 (AudioExtract / STT / PIIDetect)")


# Pipeline Registry
PIPELINE_REGISTRY: list[Analyzer] = [
    AudioExtractAnalyzer(),
    STTAnalyzer(),
    PIIDetectAnalyzer(),
]

def run_pipeline(ctx: PipelineContext) -> dict:
    """PIPELINE_REGISTRY 순서대로 analyzer 를 실행한다.

    Returns:
        {"detection_count": int, "results": dict}

    Raises:
        RuntimeError("CANCELLED") — 취소 감지 시
        RuntimeError            — analyzer 실패 시
    """
    for analyzer in PIPELINE_REGISTRY:
        if ctx.is_cancelled():
            raise RuntimeError("CANCELLED")
        result = analyzer.run(ctx.file_path, ctx)
        ctx.results[analyzer.stage_name] = result

    detection_count = ctx.results.get("pii_detect", {}).get("pii_count", 0)
    return {"detection_count": detection_count, "results": ctx.results}


print(f"Pipeline Registry 로드 완료")
print(f"등록된 analyzer: {[a.stage_name for a in PIPELINE_REGISTRY]}")


# 테스트 실행 (실제 서버 구동시 제거 예정)


if __name__ == "__main__":
    import os
    
    print(f"[{TEST_MEDIA_PATH}] 파이프라인 테스트 시작...")
    if os.path.exists(TEST_MEDIA_PATH):
        def console_progress(job_id, stage, stage_pct, total_pct, msg=None):
            msg_str = f" - {msg}" if msg else ""
            print(f"[진행도] {stage} : {total_pct}% {msg_str}")
            
        test_ctx = PipelineContext(
            job_id="test_job_123",
            upload_id="test_up_123",
            file_path=TEST_MEDIA_PATH,
            progress_fn=console_progress
        )
        
        try:
            import json
            final_result = run_pipeline(test_ctx)
            print(f"\n✅ 완료! 탐지 PII: {final_result.get('detection_count', 0)}건")
            test_media_name  = os.path.splitext(os.path.basename(TEST_MEDIA_PATH))[0]
            output_json_path = os.path.join(AUDIO_DIR, f"{test_media_name}_stt.json")
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(final_result, f, ensure_ascii=False, indent=2)
            print(f"📁 저장: {output_json_path}")
        except Exception as e:
            print(f"\n❌ 오류: {e}")
    else:
        print(f"\n⚠️ 파일 없음: {TEST_MEDIA_PATH} — Config의 TEST_MEDIA_PATH를 확인하세요.")
