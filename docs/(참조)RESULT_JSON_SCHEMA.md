# {stem}_result.json (최종 병합 JSON) 스키마 설명서

## 📌 개요

본 문서는 파이프라인의 최종 산출물인 `{stem}_result.json` 파일의 데이터 구조(스키마)와 각 컬럼의 의미를 정의합니다. 이 파일은 백엔드 및 마스킹 파이프라인의 핵심 기준으로 사용되는 **"최종 마스터 데이터"**입니다.

### ⚙️ 파일 생성 과정 (데이터 파이프라인)
1. **시각 탐지 (`OCR_pipeline_report.py`)**: 영상/이미지 화면에서 개인정보(PII)를 찾아 좌표를 저장한 `{stem}_index.json` 을 생성합니다.
2. **음성 탐지 (`colab_pipeline_stt.py`)**: 영상 내 음성을 텍스트로 변환(STT)하여 PII 발음 구간을 저장한 `{stem}_stt.json` 을 생성합니다.
3. **최종 병합 (`backend_json_merger.py`)**: 위 두 개의 결과물을 합쳐서 시각 및 음성 정보를 모두 포함한 최종 `{stem}_result.json` 파일을 완성합니다.

### 🚀 데이터 사용 목적 (활용처)
- **리포트 뷰 (프론트엔드/백엔드)**: 화면 내 개인정보의 렌더링, 통계 요약 시각화, 모자이크 처리 여부(`is_selected`) 갱신 등 웹 UI 처리에 사용됩니다.
- **마스킹 처리 (`colab_pipeline_mask.py`)**: 이 파일에 들어있는 영상 시각 좌표(`pii_groups`)와 음성 발화 구간(`audio_pii_groups`)을 앵커 포인트로 삼아 실제 영상에 모자이크/블러 및 묵음/삐 소리 처리를 완벽하게 수행합니다.
---

## 1. 최상위 메타데이터 (소스 및 영상 스펙)
이 파일이 어떤 미디어(영상/이미지)에서 파생되었는지 알려주는 기본 정보입니다.

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `source_type` | string | 파일의 종류 (`"video"` 또는 `"image"`) |
| `source_name` | string | 원본 파일명 (예: `"카드_음성_영상1.mp4"`) |
| `source_stem` | string | 확장자를 제외한 파일명 (예: `"카드_음성_영상1"`) |
| `source_file_path` | string | 서버/로컬 환경 내 원본 파일의 절대 경로 (상세보기 생성 시 참조용) |
| `image_width` | integer | 미디어의 가로 해상도 픽셀 |
| `image_height` | integer | 미디어의 세로 해상도 픽셀 |
| `fps` | float | **영상 전용** — 초당 프레임 수 |
| `total_frames` | integer | **영상 전용** — 전체 프레임 수 |

---

## 2. PII 탐지 통계 요약 ⭐️ (Merger 추가 항목)
시각(영상/이미지)과 음성에서 각각 몇 건의 개인정보가 탐지되었는지 종합한 리포트 요약본입니다.

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `visual_pii_count` | integer | 영상 화면(OCR)에서 탐지된 개인정보 건수 |
| `audio_pii_count` | integer | 음성(STT)에서 탐지된 개인정보 건수 |
| `total_pii_count` | integer | 시각 + 음성 총 개인정보 건수 |
| `risk_score` | float | 위험도 총합 점수 (0~10점) |
| `risk_level_counts` | object | 등급별 건수 딕셔너리 (`{"위험": n, "주의": n, "참고": n}`) |

---

## 3. `pii_groups` 배열 (시각/영상 개인정보 상세 데이터)
영상 화면(OCR)에서 찾아낸 개인정보들의 좌표와 프레임 정보가 담겨있습니다. (프론트엔드 모자이크 및 렌더링의 핵심 자료)

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `pii_id` | string | 개인정보 고유 식별자 (`"카드번호_1"` 등) |
| `pii_label` | string | 화면 표시용 라벨 이름 |
| `pii_type` | string | 개인정보 종류 (`"카드번호"`, `"주소"` 등) |
| `seq` | integer | 동일 타입 내 고유 순번 |
| `zone_id` | integer | 내부 OCR 구역 ID 번호 |
| `risk_level` | string | 위험 등급 (`"위험"`, `"주의"`, `"참고"`) |
| `is_selected` | boolean | **(중요)** 사용자 선택값,모자이크 처리 여부 선택 (초기값: `false`) |
| `masked_coords` | object/null | 실제 모자이크 적용 픽셀 좌표 (마스킹 파이프라인에서 채워넣음) |
| `rep_frame` | integer | 가장 잘 보이는 대표 프레임 번호 |
| `rep_timestamp` | float | 대표 프레임 시간(초) |
| `bbox` | array | 전체를 감싸는 사각형 좌표 `[x1, y1, x2, y2]` |
| `polygons` | array | 기울기를 고려한 다각형 좌표 모음 |
| `boxes` | array | 세부 텍스트 단어들(`"9012"`, `"3456"` 등)의 개별 좌표 모음 |
| `frames` | array | 해당 정보가 등장하는 모든 프레임 번호 목록 `[394, 400, ...]` |
| `keyframes` | array | 각 탐지 프레임별 상세 좌표 추적 데이터 (모자이크 추적 앵커) |

---

## 4. `audio_pii_groups` 배열 ⭐️ (음성 개인정보 상세 데이터)
STT 파이프라인(`colab_pipeline_stt.py`)에서 추출된 원시 `pii_segments`를 `backend_json_merger.py`가 아래 스키마로 **변환하여 삽입**합니다.
(영상에서 삐- 소리나 묵음 처리를 할 때 사용하는 핵심 자료)

> ⚠️ STT 원시 데이터의 `label` 필드는 Merger 단계에서 `pii_type`으로 이름이 바뀝니다.
> 최종 `result.json`에는 `label` 컬럼이 없고 `pii_type`이 해당 역할을 합니다.

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `pii_id` | string | 고유 식별자 (Merger 자동 생성, 예: `"음성_전화번호_1"`) |
| `pii_type` | string | 탐지된 정보 종류 (`"전화번호"` 등) — STT 원시의 `label`이 변환됨 |
| `detected_text` | string | 실제 인식된 음성 텍스트 (`"공일공 둘둘둘둘..."`) |
| `is_selected` | boolean | **(중요)** 사용자 선택값, 묵음/삐 처리 여부 선택 (초기값: `false`) |
| `start_time_sec` | float | 단어가 발음된 시작 시간(초) |
| `end_time_sec` | float | 단어가 발음된 끝 시간(초) |
| `confidence` | float | 탐지 신뢰도 점수 |

---

## 5. `timeline_markers` 배열 ⭐️ NEW (재생바 마커 데이터) — Merger 자동 생성
`backend_json_merger.py`가 `pii_groups`(시각)와 `audio_pii_groups`(음성)를 합산하여
재생바 위에 표시할 마커 배열을 자동 생성합니다. **프론트엔드 타임라인 렌더링 전용 데이터**입니다.

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `id` | string | 원본 PII의 `pii_id`와 동일 (예: `"카드번호_1"`, `"음성_전화번호_1"`) |
| `source` | string | 출처 구분 (`"visual"` = 시각 OCR / `"audio"` = 음성 STT) |
| `pii_type` | string | 개인정보 종류 (`"카드번호"`, `"전화번호"` 등) |
| `start_sec` | float | 마커 시작 시간(초) |
| `end_sec` | float | 마커 종료 시간(초) |
| `left_pct` | float | 재생바 위치(%) — `start_sec / total_duration × 100` |
| `severity` | string | 심각도 (`"high"`, `"medium"`, `"low"`) — PII 종류별 미리 정의값 |

> 💡 **활용**: 프론트엔드 `AnalysisReport` 재생바에서 `left_pct`를 `style={{ left: "XX%" }}`로
> 직접 사용. `id`로 카드 클릭 ↔ 마커 연동.

---

## 6. `ocr_data` 객체 (전체 배경 텍스트 백업)
개인정보가 아닌 일반 글자들을 포함하여, 화면에서 읽어들인 **모든 원본 텍스트 정보** 보관소입니다. 모자이크 마스킹에는 직접 사용되지 않지만 디버깅을 위해 보존됩니다.

| 컬럼명 | 자료형 | 설명 |
|--------|--------|------|
| `frames` | array | **영상 전용** — 프레임별로 묶인 데이터 목록 |
| `frame_idx` | integer | └ 해당 프레임 번호 |
| `timestamp_sec`| float | └ 프레임 단위 초 시간 |
| `font_zones` | array | └ 구역별 텍스트 박스(`boxes`)들의 묶음 (`is_pii` 여부 포함). **(주의: 이미지 파일인 경우 `frames` 배열 없이 `ocr_data` 바로 아래에 `font_zones`가 위치합니다)** |

> 💡 **최종 핵심 가이드:**
> - **마스킹 파이프라인**: `pii_groups`(시각) + `audio_pii_groups`(음성) 두 배열만 사용.
>   각 항목의 `is_selected: true`인 것만 골라서 처리.
> - **프론트엔드 타임라인**: `timeline_markers` 배열의 `left_pct` 값으로 재생바 마커 렌더링.
>   `id` 값으로 마커 클릭 ↔ 카드 스크롤 연동.
> - **DB 적재 전략**: `result.json` 전체는 `analysis_artifacts`에 파일로 저장.
>   `detections` 테이블에는 경량 메타(label, frame_no, bbox 요약)만 삽입 — 무거운 좌표(keyframes/polygons)는 DB에 넣지 않음.
> - **컬럼명 변환 주의**: DB 삽입 시 `pii_label→label`, `rep_frame→frame_no`,
>   `bbox[x1,y1,x2,y2]→bbox_x/y/w/h 분해` 변환 필요.
