# GARIM Front/Back/Colab Upload Progress DB Master v8 (Final)

> **작업 에이전트 안내:** 본 문서는 초기 v7(단순 ngrok 연동)에서 발전하여, 현재 프로젝트에 최종 반영된 **로컬(CPU) + Colab(GPU) 완전 자동화 하이브리드 워커 시스템**의 작동 방식을 명세한 최종(v8) 마스터 문서입니다.

**목표:** 프론트엔드의 파일 업로드부터 시작해, 로컬 CPU(OCR/병합/렌더링)와 Colab GPU(STT/마스킹)가 Cloudflare Tunnel(또는 ngrok)을 통해 완벽히 협업하며 `result.json`과 DB 상태를 갱신하는 End-to-End 완전 자동화 파이프라인 구조를 확립합니다.

**최종 아키텍처:** 
- 백엔드(FastAPI)는 업로드, Job 큐 관리, DB 상태 저장, API 라우팅을 담당.
- 로컬 워커(`local_worker.py`)는 5초마다 백엔드를 폴링하여 OCR 탐지, 결과 병합, 상세보기용 영상/json 생성(Pre-rendering) 수행.
- Colab 워커(`garim_colab_worker.py` 등)는 외부 공개 터널(Cloudflare Tunnel)을 통해 백엔드에 접속하여 STT 및 인페인팅/Beep 마스킹 수행.
- 프론트엔드(React)는 백엔드를 폴링하여 진행률(progress)을 표시하고, 최종 마스킹 요청을 전달.

**기술 스택:** FastAPI, PostgreSQL v12 DB Schema, React/Vite, Python(requests), Google Colab, Cloudflare Tunnel(ngrok 대체 가능), Whisper/ffmpeg/EasyOCR.

---

## 0. v8 최종 방향 및 변경점

v8 시스템은 v7의 단순 다운로드/보고 기능을 넘어, 분산 파이프라인의 **병목 해소와 상태 동기화**에 초점을 맞춥니다.

**핵심 DB 테이블 구조:**
```text
uploads (원본 파일 보관)
analysis_jobs (상태: queued -> processing -> completed/failed, job_type: stt_analysis, ocr 등 세분화)
job_stage_logs (상세 스테이지 진행 기록)
job_worker_heartbeats (워커 생존 상태)
detections (시각/음성 PII 요약 정보 - pii_id, polygon_json 포함)
analysis_artifacts (result.json, 상세보기 영상 등 산출물 경로)
processed_files (최종 마스킹 완료본)
```

**네트워크 및 워크플로우 방향:**
```text
1. 로컬 PC에서 DB/Redis/Backend 실행
2. 로컬에서 Cloudflare Tunnel 실행하여 Public URL 생성
3. 프론트엔드에서 영상 업로드 -> Backend DB (uploads 기록, analysis_jobs 큐잉)
4. Local Worker가 큐를 확인하여 OCR 프로세스 시작 (CPU)
5. Colab Worker가 Tunnel URL을 통해 STT 작업을 가져가 분석 수행 (GPU)
6. STT/OCR 완료 후 Local Worker가 데이터를 병합하여 result.json 및 상세보기 데이터 사전 생성
7. Backend가 DB에 detections 요약 정보 bulk insert 및 상태 complete 전환
8. 프론트엔드 폴링 종료 후 결과창 렌더링
```

---

## 1단계: 하이브리드 워커 API 연동 (다운로드/업로드)

**목표:** 로컬 워커와 Colab 워커가 원본 미디어와 중간 산출물을 원활하게 주고받을 수 있도록 엔드포인트를 고도화합니다.

**API 구성:**
- `GET /worker/files/{upload_id}/download` : 워커가 원본 파일 획득
- `POST /worker/jobs/{job_id}/results/stt` : Colab이 STT 결과 전송
- `POST /worker/jobs/{job_id}/results/artifact` : 로컬 워커가 result.json 및 상세보기 산출물 등록

**상세 동작:**
- Colab 워커는 로컬 경로를 모르므로 철저히 Tunnel URL을 통해 다운로드 API를 호출.
- 완료된 분석 데이터는 즉시 JSON 형태로 백엔드에 전송되어 DB와 Storage에 반영.

---

## 2단계: 자동화 워커 클라이언트 시스템 (Local & Colab)

**목표:** 사람의 수동 개입 없이 무한 루프로 동작하는 워커 데몬을 구현합니다.

**Local Worker (`backend/local_worker/local_worker.py`):**
- 5초 간격 Polling.
- `OCR_pipeline_report.py` 실행 (텍스트/얼굴 기본 탐지).
- STT 완료 대기 후 `backend_json_merger.py` 호출하여 최종 `result.json` 생성.
- `pipeline_detail_view.py` 호출하여 프론트엔드 오버레이용 영상 선(先)생성.

**Colab Worker (`colab/garim_colab_worker.py` / `colab_pipeline_mask.py`):**
- `BACKEND_URL` (Tunnel URL) 설정 후 무한 Polling.
- STT Job이 잡히면 음성 추출 및 Whisper 구동 후 결과 API 전송.
- 마스킹 Job이 잡히면 다운로드 후 GPU 인페인팅 적용, 완성본을 백엔드 API로 업로드.

---

## 3단계: Worker Progress, Heartbeat 및 Cancel 제어

**진행률(Progress) & 하트비트(Heartbeat):**
- 각 워커(로컬, Colab)는 주기적으로 `PUT /worker/jobs/{job_id}/progress`를 호출.
- 프론트엔드는 이 진행률 데이터를 받아 UI의 프로그레스 바를 동적으로 업데이트.

**Cancel(취소) 흐름:**
- 프론트에서 작업 취소 시 `analysis_jobs.cancel_requested` 플래그가 DB에 기록.
- 워커는 긴 작업(루프) 중 주기적으로 `check_cancel(job_id)`를 호출.
- 취소 감지 시 즉각 처리를 중단하고 자원을 회수하며 `failed` (취소됨) 상태로 전환.

---

## 4단계: 확장 가능한 분석 및 병합 파이프라인

단순 STT -> PII 처리를 넘어 병렬 처리 후 병합(Merge)하는 구조로 확장되었습니다.

**데이터 분리 전략:**
1. **DB (`detections`)**: 프론트 렌더링을 위한 최소한의 메타데이터(타임라인, 라벨, bbox, pii_id)만 신속하게 반환.
2. **Storage (`result.json`)**: 상세 좌표(keyframes, 다각형 데이터) 보관. 필요할 때만 워커 및 프론트에서 로드하여 병목 해소.

**파이프라인 실행 요약:**
```text
[프론트] 업로드 
   │
   ├─ [Colab GPU] STT 분석 진행 -> 결과 전송
   └─ [Local CPU] OCR 분석 진행 -> 결과 전송
         │
   [Local CPU] backend_json_merger 가 STT+OCR 병합 (result.json 생성)
         │
   [Local CPU] 미리생성(Pre-render) 모듈 구동 (상세보기 파일 생성)
         │
[프론트] 결과 조회 및 렌더링 -> PII 선택 및 마스킹 요청
         │
   [Colab GPU] 최종 Inpainting 마스킹 수행 -> 파일 리턴
```

---

## 5단계: 상세보기 최적화 (Pre-Rendering)

사용자 경험(UX) 극대화를 위해 v8 아키텍처에 추가된 핵심 최적화 요소입니다.

- 사용자가 "상세보기" 버튼을 누를 때 딜레이를 없애기 위해, 분석 파이프라인의 **가장 마지막 단계에서 상세보기용 보조 파일(`_상세보기.mp4`, `_tracks.json`)을 미리 생성**하여 등록해 둡니다.
- 6초 샘플링 미리보기: 영상 미리보기 마스킹 요청 시, 전체를 처리하지 않고 해당 PII 발생 전후 3초만 잘라서 빠르게 마스킹 후 응답.

---

## 6단계: 외부 공개 터널 (Cloudflare / Ngrok) 설정

**Colab과의 통신 보장:**
- 로컬 백엔드를 외부에서 접근 가능하게 만들기 위해 Cloudflare Tunnel (또는 ngrok)을 활용.
- 터널 실행 스크립트(`cloudflare_tunnel.py` 등)를 통해 8000번 포트 연결.
- Colab 노트북 셀에서 환경 변수 `BACKEND_URL`에 할당된 터널 공개 주소와 `WORKER_SECRET`을 설정 후 워커를 구동.

---

## 7단계: 최종 통합 검증 (End-to-End)

**검증 흐름:**
1. 로컬 환경 `docker-compose up` (DB, Redis 기동).
2. 터널 스크립트 실행 (공개 URL 획득).
3. FastAPI 백엔드 및 React 프론트 구동.
4. `local_worker.py` 로컬 스크립트 백그라운드 실행.
5. Colab에서 워커 스크립트 실행.
6. **프론트엔드 업로드 테스트**: 파일 업로드 시 로컬/Colab 워커가 동시에 잡을 폴링하며 작업 처리.
7. **진행률 연동 확인**: 프론트에 STT, OCR 등 실시간 상태 프로그레스 표출.
8. **결과 확인**: 병합 로직 정상 수행 및 DB `detections` 데이터 생성 확인.
9. **마스킹 및 다운로드**: 최종 인페인팅 적용 후 프론트에서 MP4 다운로드 검증.

---

## v8 성공 및 완료 기준

- [x] 프론트엔드 업로드부터 마스킹 파일 다운로드까지 100% 자동화 달성.
- [x] 로컬 워커와 Colab 워커가 각자의 자원(CPU, GPU)에 맞는 역할을 분담.
- [x] 무거운 데이터는 JSON 스토리지로, 가벼운 메타데이터는 DB로 분리 완료.
- [x] Cancel 흐름 및 실시간 Progress 보고 정상 작동.
- [x] Cloudflare/Ngrok 터널을 통한 양방향 통신 검증 완료.
