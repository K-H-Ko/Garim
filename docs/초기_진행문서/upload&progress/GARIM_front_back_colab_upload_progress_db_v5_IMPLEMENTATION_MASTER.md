# GARIM Front-Back-Colab 업로드/진행률/DB 구현 마스터 v5

파일명: `GARIM_front_back_colab_upload_progress_db_v5_IMPLEMENTATION_MASTER.md`

작성 목적: Codex, Claude Code, 또는 개발자가 이 문서 하나만 보고 GARIM 프로젝트의 대용량 업로드, Backend 중심 파일 관리, Colab Worker 연동, WebSocket/Polling 진행률 표시, PostgreSQL/Redis 상태 저장, Page09/Page17/Page19 화면 흐름을 누락 없이 구현할 수 있도록 한다.

---

## 0. 최종 결론

GARIM MVP의 현실적인 최종 구조는 아래와 같다.

```text
Frontend
→ Backend API
→ Backend Local Temp Storage
→ Redis Queue / Realtime Cache
→ Colab Worker via ngrok
→ Backend Callback API
→ PostgreSQL Persistent State
→ WebSocket / Polling
→ Frontend Progress UI
```

핵심 원칙:

```text
1. 사용자는 Colab에 직접 업로드하지 않는다.
2. Frontend는 Backend에 chunk upload 한다.
3. Backend가 파일 저장, 검증, 병합, Job 생성, 상태 저장을 책임진다.
4. Colab은 Backend에서 파일을 받아 처리하고, 진행률/heartbeat/result를 Backend로 callback 한다.
5. Redis는 실시간 상태와 큐를 담당한다.
6. PostgreSQL은 영속 상태와 이력을 담당한다.
7. WebSocket은 실시간 UI 표시를 담당한다.
8. Polling은 WebSocket 장애/새로고침/대시보드 복원 fallback을 담당한다.
9. 신규 jobs 테이블을 만들지 않고 기존 analysis_jobs를 확장한다.
10. 작업 단계 이력은 job_stage_logs, Worker 생존 이력은 job_worker_heartbeats, Queue 이력은 job_queue_history로 관리한다.
```

---

## 1. 문서 범위

이 문서는 다음 범위를 포함한다.

```text
- Page08 파일 업로드
- 대용량 chunk upload
- upload resume / 재시도
- Backend 임시 파일 저장
- 파일 병합 및 검증
- analysis_jobs 기반 Job 생성
- Redis queue enqueue
- Colab Worker 연동
- ngrok 기반 Colab endpoint 사용
- Colab heartbeat
- Colab progress callback
- WebSocket 진행률 push
- Polling fallback
- Page09 분석 진행률 화면
- Page10 분석 리포트 이동
- Page15 치환 옵션 설정 이후 render job 생성
- Page17 치환/렌더링 진행률 화면
- Page18 결과 다운로드
- Page19 마이페이지 진행중 작업 복원
- 작업 취소
- 작업 실패/worker_timeout/retry
- 완료 알림
- PostgreSQL/Redis 역할 분리
- FastAPI 구현 예시
- Next.js 구현 예시
- DB 추가/수정 SQL
- Codex/Claude Code 작업 지시문
- 테스트 체크리스트
```

---

## 2. 기준 화면 흐름

```text
Page08 파일 업로드
→ Page09 분석 처리 진행
→ Page10 분석 리포트
→ Page15 치환 옵션 설정
→ Page17 처리 진행
→ Page18 다운로드
→ Page19 마이 대시보드 진행중 작업 복원
```

화면별 책임:

| 화면 | 책임 |
|---|---|
| Page08 | 파일 선택, 확장자/용량 1차 검증, chunk upload, upload complete 요청 |
| Page09 | 분석 job 진행률 표시, WebSocket 연결, Polling fallback, 취소 |
| Page10 | 분석 결과 리포트 표시, 위험 구간 확인, 치환 옵션 진입 |
| Page15 | 치환/마스킹/블러/변환 옵션 설정, render job 생성 |
| Page17 | render job 진행률 표시, WebSocket 연결, Polling fallback, 취소 |
| Page18 | 결과 파일 다운로드, 작업 완료 상태 표시 |
| Page19 | 진행중/완료/실패 작업 복원, 이어보기 |

---

## 3. 서버 구조

```text
User Browser
  ↓ HTTP/WebSocket
Frontend Next.js
  ↓ REST API / WebSocket
Backend FastAPI
  ├─ Local Temp Storage
  ├─ PostgreSQL
  ├─ Redis
  └─ Internal API for Colab
       ↑ ↓ ngrok
Colab Worker
  ├─ AI 분석
  ├─ OCR/STT
  ├─ 개인정보 탐지
  ├─ 마스킹/블러/변환
  └─ 결과 업로드
```

### 3.1 역할 분리

| 영역 | 역할 |
|---|---|
| Frontend | 업로드 UI, 진행률 UI, WebSocket 연결, Polling fallback, 대시보드 복원 |
| Backend | 인증, 업로드 수신, 파일 임시 저장, chunk 병합, Job 생성, 상태 저장, Colab 연동, 알림 발송 |
| Redis | Queue, 실시간 progress cache, 최신 heartbeat, cancel flag, socket payload cache |
| PostgreSQL | analysis_jobs 대표 상태, upload/file metadata, stage log, heartbeat log, queue history, result metadata |
| Colab | AI 분석, OCR/STT, 개인정보 탐지, 치환/마스킹/렌더링 처리 |

---

## 4. 왜 Front → Back → Colab 구조인가

Colab은 다음 이유로 사용자 직접 업로드 endpoint로 부적합하다.

```text
- 런타임이 언제든 종료될 수 있다.
- ngrok 주소가 변경될 수 있다.
- 무료 환경에서는 연결 안정성이 낮다.
- 사용자가 500MB~1GB 파일 업로드 중 연결이 끊기면 복구가 어렵다.
- 인증/권한/파일 검증/감사 로그를 Colab에 두기 어렵다.
```

따라서 Backend가 업로드와 파일 소유권, Job 상태의 source of truth가 되어야 한다.

최종 업로드 흐름:

```text
Frontend
→ Backend chunk upload
→ Backend temp storage
→ Backend merge
→ Backend validation
→ analysis_jobs 생성
→ Redis enqueue
→ Colab worker processing
```

---

## 5. 대용량 Chunk Upload 설계

500MB~1GB 파일은 단일 요청으로 업로드하지 않는다. 반드시 chunk upload를 사용한다.

### 5.1 API 흐름

```text
1. POST /uploads/init
2. POST /uploads/{upload_id}/chunks
3. GET  /uploads/{upload_id}/status
4. POST /uploads/{upload_id}/complete
5. DELETE /uploads/{upload_id}
6. POST /jobs
```

### 5.2 Chunk 크기 권장값

```text
기본 chunk size: 5MB ~ 10MB
불안정 네트워크: 2MB ~ 5MB
고속 네트워크: 10MB ~ 20MB
```

MVP 기본값은 `5MB`를 권장한다.

### 5.3 upload session 데이터

```text
upload_id
user_id
file_name
file_size
mime_type
total_chunks
uploaded_chunks
chunk_size
file_hash
status
storage_path
merged_file_path
created_at
updated_at
expires_at
```

### 5.4 업로드 상태

```text
initialized
uploading
uploaded
failed
expired
cancelled
```

### 5.5 파일 저장 구조 예시

```text
storage/
  uploads/
    temp/
      {user_id}/
        {upload_id}/
          chunk_000000.part
          chunk_000001.part
          chunk_000002.part
    merged/
      {user_id}/
        {upload_id}/
          original_filename.mp4
    results/
      {user_id}/
        {job_id}/
          report.json
          masked_output.mp4
          thumbnail.jpg
```

---

## 6. Upload DB 설계

프로젝트에 이미 upload 관련 테이블이 있으면 이름은 기존 명세를 우선한다. 없으면 아래 구조를 추가한다.

### 6.1 upload_sessions

```sql
CREATE TABLE IF NOT EXISTS upload_sessions (
    upload_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100),
    file_hash VARCHAR(128),
    chunk_size INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    uploaded_chunks INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'initialized',
    temp_dir_path TEXT,
    merged_file_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP
);

COMMENT ON TABLE upload_sessions IS '대용량 파일 chunk upload 세션';
COMMENT ON COLUMN upload_sessions.upload_id IS '업로드 세션 ID';
COMMENT ON COLUMN upload_sessions.user_id IS '업로드 요청 사용자';
COMMENT ON COLUMN upload_sessions.file_name IS '원본 파일명';
COMMENT ON COLUMN upload_sessions.file_size IS '원본 파일 크기 byte';
COMMENT ON COLUMN upload_sessions.file_hash IS '파일 무결성 검증용 hash';
COMMENT ON COLUMN upload_sessions.chunk_size IS 'chunk 크기 byte';
COMMENT ON COLUMN upload_sessions.total_chunks IS '전체 chunk 수';
COMMENT ON COLUMN upload_sessions.uploaded_chunks IS '업로드 완료 chunk 수';
COMMENT ON COLUMN upload_sessions.status IS 'initialized/uploading/uploaded/failed/expired/cancelled';
```

### 6.2 upload_chunks

```sql
CREATE TABLE IF NOT EXISTS upload_chunks (
    upload_chunk_id UUID PRIMARY KEY,
    upload_id UUID NOT NULL REFERENCES upload_sessions(upload_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_size INTEGER NOT NULL,
    chunk_hash VARCHAR(128),
    storage_path TEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (upload_id, chunk_index)
);

COMMENT ON TABLE upload_chunks IS '업로드된 chunk 단위 파일 정보';
COMMENT ON COLUMN upload_chunks.chunk_index IS '0부터 시작하는 chunk 순번';
COMMENT ON COLUMN upload_chunks.chunk_hash IS 'chunk 무결성 검증용 hash';
```

### 6.3 uploaded_files

```sql
CREATE TABLE IF NOT EXISTS uploaded_files (
    file_id UUID PRIMARY KEY,
    upload_id UUID REFERENCES upload_sessions(upload_id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    original_file_name VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100),
    file_hash VARCHAR(128),
    storage_path TEXT NOT NULL,
    duration_seconds INTEGER,
    width INTEGER,
    height INTEGER,
    thumbnail_path TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'ready',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE uploaded_files IS '병합 및 검증 완료된 원본 파일 메타데이터';
```

---

## 7. Job DB 설계 v5

### 7.1 중요 결정

기존 `jobs` 테이블을 새로 만들지 않는다.

DB v4 이후 기준은 다음이다.

```text
기존 jobs 테이블 신규 생성 방식 제거
→ 기존 analysis_jobs 테이블 확장 방식으로 변경

job_progress_events 표현 제거
→ job_stage_logs 기준으로 변경

Colab heartbeat 이력
→ job_worker_heartbeats 기준으로 변경

Redis queue 이력
→ job_queue_history 기준으로 변경

SNS 진단 작업
→ sns_diagnosis_jobs.job_id가 analysis_jobs.job_id를 참조
```

### 7.2 analysis_jobs 역할

`analysis_jobs`는 모든 사용자 작업의 대표 상태를 저장한다.

담당 범위:

```text
- 분석 작업 상태
- 미리보기 작업 상태
- 치환/렌더링 작업 상태
- SNS 진단 작업 상태
- 진행률
- 현재 단계
- ETA
- 큐 위치
- 취소 요청 flag
- 결과 파일 경로
- 리포트 연결
- 대시보드 복원
```

### 7.3 analysis_jobs 추가 컬럼 SQL

이미 존재하는 컬럼은 중복 생성하지 않는다. PostgreSQL에서는 `ADD COLUMN IF NOT EXISTS`를 사용한다.

```sql
ALTER TABLE analysis_jobs
    ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_sessions(upload_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS file_id UUID REFERENCES uploaded_files(file_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS job_type VARCHAR(30) DEFAULT 'analysis',
    ADD COLUMN IF NOT EXISTS current_stage VARCHAR(50),
    ADD COLUMN IF NOT EXISTS stage_progress INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_progress INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS queue_position INTEGER,
    ADD COLUMN IF NOT EXISTS eta_seconds INTEGER,
    ADD COLUMN IF NOT EXISTS message TEXT,
    ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(100),
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS result_file_path TEXT,
    ADD COLUMN IF NOT EXISTS report_id UUID,
    ADD COLUMN IF NOT EXISTS worker_task_id UUID,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

COMMENT ON COLUMN analysis_jobs.job_type IS 'analysis/preview/render/sns_scan/white_list_scan/metadata_scan';
COMMENT ON COLUMN analysis_jobs.current_stage IS '현재 처리 단계';
COMMENT ON COLUMN analysis_jobs.stage_progress IS '현재 단계 진행률 0~100';
COMMENT ON COLUMN analysis_jobs.total_progress IS '전체 진행률 0~100';
COMMENT ON COLUMN analysis_jobs.queue_position IS '큐 대기 순번';
COMMENT ON COLUMN analysis_jobs.eta_seconds IS '예상 남은 시간 초';
COMMENT ON COLUMN analysis_jobs.cancel_requested IS '사용자 취소 요청 여부';
```

### 7.4 status enum

```text
queued
processing
completed
failed
cancelling
cancelled
retrying
worker_timeout
cleanup_required
```

### 7.5 job_type enum

```text
analysis
preview
render
sns_scan
white_list_scan
metadata_scan
```

### 7.6 current_stage enum 예시

분석 단계:

```text
upload_completed
queued
file_preparing
visual_detection
audio_detection
metadata_detection
report_generation
completed
```

치환/렌더링 단계:

```text
option_confirmed
preview_generation
render_processing
watermarking
output_encoding
completed
```

장애/취소 단계:

```text
cancelling
worker_timeout
cleanup_required
failed
cancelled
```

---

## 8. 보조 테이블

### 8.1 job_stage_logs

`job_stage_logs`는 단계 변경과 주요 진행률 이벤트를 저장한다.

저장 시점:

```text
- stage 변경 시
- progress가 일정 비율 이상 변할 때, 예: 5% 단위
- status가 failed/cancelled/completed로 변경될 때
- Colab callback에서 중요한 message가 발생할 때
```

SQL:

```sql
CREATE TABLE IF NOT EXISTS job_stage_logs (
    job_stage_log_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    stage_name VARCHAR(50) NOT NULL,
    stage_progress INTEGER DEFAULT 0,
    total_progress INTEGER DEFAULT 0,
    status VARCHAR(30),
    message TEXT,
    payload JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_stage_logs_job_id_created_at
    ON job_stage_logs(job_id, created_at DESC);

COMMENT ON TABLE job_stage_logs IS '작업 단계 변경 및 주요 진행률 이력';
```

### 8.2 job_worker_heartbeats

`job_worker_heartbeats`는 Colab/ngrok/Worker 생존 신호 이력을 저장한다.

Redis에는 최신 heartbeat만 저장하고 PostgreSQL에는 이력으로 남긴다.

SQL:

```sql
CREATE TABLE IF NOT EXISTS job_worker_heartbeats (
    heartbeat_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    worker_task_id UUID,
    worker_id VARCHAR(100),
    worker_type VARCHAR(50) DEFAULT 'colab',
    public_endpoint TEXT,
    current_stage VARCHAR(50),
    progress INTEGER DEFAULT 0,
    message TEXT,
    heartbeat_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_worker_heartbeats_job_id_heartbeat_at
    ON job_worker_heartbeats(job_id, heartbeat_at DESC);

COMMENT ON TABLE job_worker_heartbeats IS 'Colab/Worker heartbeat 이력';
```

### 8.3 job_queue_history

`job_queue_history`는 Redis Queue 진입/해제/취소/재시도 이력을 저장한다.

SQL:

```sql
CREATE TABLE IF NOT EXISTS job_queue_history (
    queue_log_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    worker_task_id UUID,
    queue_name VARCHAR(50) DEFAULT 'default',
    priority INTEGER DEFAULT 0,
    queue_position INTEGER,
    event_type VARCHAR(30) DEFAULT 'entered',
    entered_at TIMESTAMP,
    dequeued_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_queue_history_job_id_created_at
    ON job_queue_history(job_id, created_at DESC);

COMMENT ON TABLE job_queue_history IS 'Redis Queue 처리 이력';
```

`event_type`:

```text
entered
dequeued
reprioritized
cancelled
failed
retrying
```

### 8.4 job_results

결과 파일/리포트 메타데이터 저장용이다.

```sql
CREATE TABLE IF NOT EXISTS job_results (
    result_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    result_type VARCHAR(50) NOT NULL,
    file_path TEXT,
    file_name VARCHAR(255),
    file_size BIGINT,
    mime_type VARCHAR(100),
    report_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_results_job_id
    ON job_results(job_id);

COMMENT ON TABLE job_results IS '작업 결과 파일 및 리포트 메타데이터';
```

### 8.5 sns_diagnosis_jobs 연결

SNS 진단 작업은 다음 구조로 간다.

```text
analysis_jobs.job_type = 'sns_scan'
analysis_jobs.job_id = sns_diagnosis_jobs.job_id
```

즉:

```text
analysis_jobs → 작업 상태/진행률/큐/복원 담당
sns_diagnosis_jobs → SNS 진단 상세 결과/리포트 담당
```

---

## 9. Redis 설계

### 9.1 Key 목록

```text
job:{job_id}:progress
job:{job_id}:heartbeat
job:{job_id}:cancel
queue:analysis
queue:render
queue:sns_scan
socket:user:{user_id}
worker:colab:{worker_id}:heartbeat
```

### 9.2 progress cache 예시

```json
{
  "job_id": "uuid",
  "user_id": "uuid",
  "job_type": "analysis",
  "status": "processing",
  "current_stage": "visual_detection",
  "stage_progress": 55,
  "total_progress": 37,
  "queue_position": 2,
  "eta_seconds": 180,
  "message": "시각 개인정보 탐지 중입니다.",
  "updated_at": "2026-05-22T12:00:00+09:00"
}
```

### 9.3 heartbeat cache 예시

```json
{
  "job_id": "uuid",
  "worker_id": "colab-session-id",
  "worker_type": "colab",
  "public_endpoint": "https://xxxx.ngrok-free.app",
  "current_stage": "visual_detection",
  "progress": 37,
  "heartbeat_at": "2026-05-22T12:00:00+09:00"
}
```

### 9.4 TTL 권장

```text
job:{job_id}:progress     → 완료 후 24시간
job:{job_id}:heartbeat    → 5분
job:{job_id}:cancel       → 작업 종료까지 또는 24시간
queue:*                   → Redis queue 정책에 따름
socket:user:{user_id}     → 세션 유지 기간
```

---

## 10. Redis와 PostgreSQL 역할 분리

| 데이터 | Redis | PostgreSQL |
|---|---|---|
| 최신 진행률 | O | analysis_jobs에도 대표 상태 저장 |
| 모든 진행 이벤트 | X | job_stage_logs에 주요 이벤트만 저장 |
| 최신 heartbeat | O | job_worker_heartbeats에 이력 저장 |
| Queue 실제 처리 | O | job_queue_history에 이력 저장 |
| 작업 최종 상태 | X | analysis_jobs |
| 대시보드 복원 | 보조 | analysis_jobs 기준 |
| 관리자 분석 | X | job_stage_logs / job_queue_history / worker_tasks |
| cancel flag | O | analysis_jobs.cancel_requested |

원칙:

```text
Redis는 빠른 현재 상태.
PostgreSQL은 복구 가능한 영속 상태.
Frontend는 Redis만 믿지 말고 /jobs/{job_id}/status API를 통해 Backend가 조합한 상태를 받는다.
```

---

## 11. Job 생성 흐름

업로드 완료 후 Backend는 Job을 생성한다.

```text
POST /uploads/{upload_id}/complete
→ chunk 개수 검증
→ chunk hash 검증
→ 파일 병합
→ 전체 file hash 검증
→ uploaded_files row 생성
→ POST /jobs
→ analysis_jobs row 생성
→ Redis queue enqueue
→ job_queue_history insert(event_type=entered)
→ Page09 이동용 job_id 반환
```

### 11.1 Job 생성 payload

```json
{
  "upload_id": "uuid",
  "file_id": "uuid",
  "job_type": "analysis",
  "options": {
    "detect_visual_pii": true,
    "detect_audio_pii": true,
    "detect_metadata": true
  }
}
```

### 11.2 Job 생성 응답

```json
{
  "job_id": "uuid",
  "status": "queued",
  "current_stage": "queued",
  "stage_progress": 0,
  "total_progress": 0,
  "queue_position": 3,
  "eta_seconds": null,
  "next_url": "/jobs/{job_id}/progress"
}
```

---

## 12. Page09 분석 처리 진행 구조

Page09는 단순 progress bar가 아니라 단계별 Stepper를 표시한다.

### 12.1 분석 Stepper

```text
1. upload_completed
2. queued
3. visual_detection
4. audio_detection
5. metadata_detection
6. report_generation
7. completed
```

### 12.2 Page09 표시 정보

```text
파일명
썸네일
파일 크기
영상 길이
현재 단계
단계별 진행률
전체 진행률
ETA
Free 사용자 큐 위치
백그라운드 처리 안내
취소 버튼
장애 발생 시 retry 안내
```

### 12.3 단계별 progress 산정 예시

분석 작업 전체 진행률은 stage별 가중치를 둔다.

```text
upload_completed: 0~5%
queued: 5~10%
visual_detection: 10~45%
audio_detection: 45~70%
metadata_detection: 70~80%
report_generation: 80~98%
completed: 100%
```

---

## 13. Page17 치환/렌더링 처리 진행 구조

Page17은 분석 완료 후 사용자가 Page15에서 선택한 치환 옵션을 바탕으로 생성된 `job_type=render` 작업을 표시한다.

### 13.1 Render Stepper

```text
1. option_confirmed
2. preview_generation
3. render_processing
4. watermarking
5. output_encoding
6. completed
```

### 13.2 Page17 표시 정보

```text
선택된 치환 옵션
처리 대상 개수
현재 처리 단계
단계별 진행률
전체 진행률
워터마크 삽입 상태
예상 완료 시간
취소 가능 여부
```

### 13.3 Render Job 생성 payload

```json
{
  "source_job_id": "analysis-job-uuid",
  "job_type": "render",
  "options": {
    "mask_type": "blur",
    "apply_to_faces": true,
    "apply_to_text": true,
    "apply_to_audio": true,
    "watermark": true
  }
}
```

---

## 14. WebSocket 구조

### 14.1 연결 시점

Page09 또는 Page17 진입 시:

```text
1. GET /jobs/{job_id}/status 로 현재 상태 초기화
2. WebSocket 연결
3. job_id subscribe
4. progress event 수신
5. event 수신 시 UI 업데이트
6. 연결 끊김 또는 event 지연 시 polling fallback
```

### 14.2 WebSocket endpoint

```text
WS /ws/jobs/{job_id}
```

또는 사용자 단위 구독:

```text
WS /ws/users/me
subscribe message: { "type": "subscribe", "job_id": "uuid" }
```

MVP에서는 구현 단순화를 위해 `WS /ws/jobs/{job_id}`를 우선한다.

### 14.3 Event type

```text
job.progress
job.stage_changed
job.completed
job.failed
job.cancelled
job.worker_timeout
job.cleanup_required
```

### 14.4 WebSocket payload

```json
{
  "type": "job.progress",
  "job_id": "uuid",
  "job_type": "analysis",
  "status": "processing",
  "current_stage": "audio_detection",
  "stage_progress": 20,
  "total_progress": 62,
  "queue_position": null,
  "eta_seconds": 90,
  "message": "음성 개인정보 탐지 중입니다.",
  "updated_at": "2026-05-22T12:00:00+09:00"
}
```

### 14.5 완료 payload

```json
{
  "type": "job.completed",
  "job_id": "uuid",
  "job_type": "analysis",
  "status": "completed",
  "current_stage": "completed",
  "stage_progress": 100,
  "total_progress": 100,
  "result_url": "/jobs/{job_id}/report",
  "message": "분석이 완료되었습니다."
}
```

---

## 15. Polling fallback

WebSocket만 사용하면 안 된다.

### 15.1 fallback 조건

```text
WebSocket disconnected
WebSocket reconnect failed
마지막 progress event 수신 후 10초 이상 경과
페이지 새로고침
브라우저 절전 후 복귀
Page19 대시보드 복원
모바일 네트워크 전환
```

### 15.2 Polling endpoint

```text
GET /jobs/{job_id}/status
```

Backend 조회 순서:

```text
1. Redis job:{job_id}:progress 조회
2. 없으면 analysis_jobs 대표 상태 조회
3. file/result metadata 결합
4. response 반환
```

### 15.3 Polling 주기

```text
queued: 5~10초
processing: 3~5초
worker_timeout: 5초
completed/failed/cancelled: polling 중지
```

---

## 16. Page19 대시보드 복원

대시보드는 진행 중 작업을 복원해야 한다.

### 16.1 API

```text
GET /me/jobs/in-progress
GET /me/jobs
GET /me/jobs/{job_id}
```

### 16.2 진행중 조회 SQL

```sql
SELECT *
FROM analysis_jobs
WHERE user_id = :user_id
  AND status IN ('queued', 'processing', 'cancelling', 'retrying', 'worker_timeout')
ORDER BY created_at DESC;
```

### 16.3 응답 예시

```json
[
  {
    "job_id": "uuid",
    "file_name": "sample.mp4",
    "job_type": "analysis",
    "status": "processing",
    "current_stage": "visual_detection",
    "stage_progress": 55,
    "total_progress": 37,
    "eta_seconds": 180,
    "thumbnail_url": "/files/thumb/sample.jpg",
    "next_url": "/jobs/{id}/progress"
  }
]
```

### 16.4 이동 규칙

```text
job_type=analysis + 진행중 → /jobs/{id}/progress
job_type=analysis + completed → /jobs/{id}/report
job_type=preview + 진행중 → /jobs/{id}/preview-progress
job_type=render + 진행중 → /jobs/{id}/processing
job_type=render + completed → /jobs/{id}/download
job_type=sns_scan + 진행중 → /sns/jobs/{id}/progress
job_type=sns_scan + completed → /sns/jobs/{id}/report
failed → 실패 상세 화면 또는 재시도 안내
cancelled → 취소됨 표시
worker_timeout → Worker 연결 재시도 또는 관리자 안내
```

---

## 17. Colab Worker 연동

### 17.1 기본 방식

```text
Backend가 파일을 임시 저장
→ Colab에 job_id와 input_file_url 전달
→ Colab이 Backend에서 파일 다운로드
→ Colab이 처리 진행
→ Colab이 progress/heartbeat callback
→ Colab이 결과 파일 Backend로 업로드
→ Backend가 analysis_jobs completed 처리
```

### 17.2 Colab job start payload

```json
{
  "job_id": "uuid",
  "job_type": "analysis",
  "input_file_url": "https://backend.example.com/internal/files/{file_id}/download",
  "callback_progress_url": "https://backend.example.com/internal/jobs/{job_id}/progress",
  "callback_heartbeat_url": "https://backend.example.com/internal/jobs/{job_id}/heartbeat",
  "callback_result_url": "https://backend.example.com/internal/jobs/{job_id}/result",
  "callback_failed_url": "https://backend.example.com/internal/jobs/{job_id}/failed",
  "auth_token": "internal-worker-token"
}
```

### 17.3 Colab → Backend progress callback

```text
POST /internal/jobs/{job_id}/progress
```

Payload:

```json
{
  "job_id": "uuid",
  "status": "processing",
  "current_stage": "visual_detection",
  "stage_progress": 55,
  "total_progress": 37,
  "queue_position": 2,
  "eta_seconds": 180,
  "message": "시각 개인정보 탐지 중입니다.",
  "payload": {
    "processed_frames": 1200,
    "total_frames": 3200
  }
}
```

Backend 처리:

```text
1. internal token 검증
2. analysis_jobs 대표 상태 update
3. Redis job:{job_id}:progress update
4. stage 변경 또는 주요 이벤트면 job_stage_logs insert
5. WebSocket broadcast
```

### 17.4 Colab heartbeat

```text
POST /internal/jobs/{job_id}/heartbeat
```

Payload:

```json
{
  "job_id": "uuid",
  "worker_id": "colab-session-id",
  "worker_type": "colab",
  "public_endpoint": "https://xxxx.ngrok-free.app",
  "current_stage": "visual_detection",
  "progress": 37,
  "message": "worker alive",
  "timestamp": "2026-05-22T12:00:00+09:00"
}
```

Backend 처리:

```text
1. Redis job:{job_id}:heartbeat update
2. job_worker_heartbeats insert
3. analysis_jobs.updated_at update
4. 필요 시 worker 상태 관리
```

### 17.5 heartbeat timeout 기준

```text
마지막 heartbeat 30초 초과: warning
마지막 heartbeat 60초 초과: worker_timeout
마지막 heartbeat 120초 초과: failed 또는 retry 대기
```

worker_timeout 처리:

```text
analysis_jobs.status = worker_timeout
analysis_jobs.current_stage = worker_timeout
job_stage_logs insert
WebSocket job.worker_timeout broadcast
Page09/Page17에서 재시도 안내
```

---

## 18. ngrok 장애 대응

ngrok 주소는 변경될 수 있고 연결이 끊길 수 있다.

### 18.1 Worker 등록 API

```text
POST /internal/workers/register
```

Payload:

```json
{
  "worker_id": "colab-session-id",
  "worker_type": "colab",
  "public_endpoint": "https://xxxx.ngrok-free.app",
  "capacity": 1,
  "supported_job_types": ["analysis", "render"]
}
```

### 18.2 장애 시나리오

```text
- Colab 런타임 종료
- ngrok endpoint 변경
- ngrok 502
- Colab 메모리 부족
- 처리 중 예외 발생
- 결과 업로드 실패
```

### 18.3 대응 정책

```text
1. heartbeat timeout 감지
2. analysis_jobs.status = worker_timeout
3. queue 재진입 가능 여부 판단
4. retry_count 제한
5. 사용자에게 재시도/대기 안내
6. cleanup_required 상태면 temp/result 중간 파일 정리
```

---

## 19. 작업 취소

Page09, Page17에서 취소 버튼을 제공한다면 Backend 중심으로 처리한다.

### 19.1 취소 흐름

```text
Frontend
→ POST /jobs/{job_id}/cancel
→ Backend analysis_jobs.cancel_requested = true
→ analysis_jobs.status = cancelling
→ Redis job:{job_id}:cancel = true
→ Colab heartbeat/progress loop에서 cancel 확인
→ safe stop
→ temp/intermediate file cleanup
→ analysis_jobs.status = cancelled
→ job_stage_logs insert
→ job_queue_history insert(event_type=cancelled)
→ WebSocket job.cancelled
```

### 19.2 취소 상태 전이

```text
processing
→ cancelling
→ cancelled
```

Colab이 이미 끊긴 경우:

```text
cancelling
→ worker_timeout
→ cleanup_required
```

### 19.3 Colab cancel 확인 위치

Colab Worker는 다음 루프마다 cancel flag를 확인한다.

```text
- 파일 다운로드 직후
- 프레임 batch 처리 사이
- OCR/STT batch 처리 사이
- 렌더링 segment 처리 사이
- 결과 업로드 직전
```

---

## 20. 완료 알림

완료 알림은 2-track으로 처리한다.

### 20.1 실시간 접속 사용자

```text
WebSocket job.completed
→ Front toast/modal 표시
→ Page10 또는 Page18 이동 버튼 제공
```

### 20.2 이탈 사용자

```text
Email notification
Browser notification
Dashboard 진행중 카드 상태 변경
```

DB 예시:

```sql
CREATE TABLE IF NOT EXISTS notifications (
    notification_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id UUID REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

## 21. Backend API 정리

### 21.1 Upload API

```text
POST   /uploads/init
POST   /uploads/{upload_id}/chunks
GET    /uploads/{upload_id}/status
POST   /uploads/{upload_id}/complete
DELETE /uploads/{upload_id}
```

### 21.2 Job API

```text
POST /jobs
GET  /jobs/{job_id}/status
GET  /jobs/{job_id}/report
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
```

### 21.3 Render API

```text
POST /jobs/{source_job_id}/render
GET  /jobs/{job_id}/download
```

### 21.4 Internal Colab Callback

```text
POST /internal/workers/register
POST /internal/jobs/{job_id}/start
POST /internal/jobs/{job_id}/progress
POST /internal/jobs/{job_id}/heartbeat
POST /internal/jobs/{job_id}/result
POST /internal/jobs/{job_id}/failed
GET  /internal/files/{file_id}/download
```

### 21.5 My Page

```text
GET /me/jobs
GET /me/jobs/in-progress
GET /me/jobs/{job_id}
```

### 21.6 SNS

```text
POST /sns/diagnosis-jobs
GET  /sns/diagnosis-jobs/{job_id}
GET  /sns/diagnosis-jobs/{job_id}/report
```

---

## 22. FastAPI 구현 예시

아래 코드는 구조 이해용 예시다. 실제 프로젝트 구조에 맞춰 service/repository/schema로 분리한다.

### 22.1 Upload init

```python
from uuid import uuid4
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class UploadInitRequest(BaseModel):
    file_name: str
    file_size: int
    mime_type: str | None = None
    chunk_size: int = 5 * 1024 * 1024
    file_hash: str | None = None

@router.post("/uploads/init")
def init_upload(req: UploadInitRequest, user=Depends(get_current_user)):
    upload_id = uuid4()
    total_chunks = (req.file_size + req.chunk_size - 1) // req.chunk_size
    temp_dir = f"storage/uploads/temp/{user.user_id}/{upload_id}"

    # 1. temp_dir 생성
    # 2. upload_sessions insert
    # 3. response 반환

    return {
        "upload_id": str(upload_id),
        "chunk_size": req.chunk_size,
        "total_chunks": total_chunks,
        "uploaded_chunks": [],
        "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
    }
```

### 22.2 Chunk upload

```python
from fastapi import UploadFile, File, Form, HTTPException

@router.post("/uploads/{upload_id}/chunks")
async def upload_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    chunk_hash: str | None = Form(None),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # 1. upload_session 조회 및 user 검증
    # 2. chunk_index 범위 검증
    # 3. 이미 업로드된 chunk면 idempotent response
    # 4. chunk 저장
    # 5. hash 검증
    # 6. upload_chunks upsert
    # 7. upload_sessions.uploaded_chunks update

    return {
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "status": "uploaded"
    }
```

### 22.3 Upload complete

```python
@router.post("/uploads/{upload_id}/complete")
def complete_upload(upload_id: str, user=Depends(get_current_user)):
    # 1. upload_session 조회
    # 2. total_chunks == uploaded_chunks 검증
    # 3. chunk 순서대로 merge
    # 4. 전체 file_hash 검증
    # 5. uploaded_files insert
    # 6. upload_sessions.status = uploaded

    return {
        "upload_id": upload_id,
        "file_id": "uuid",
        "status": "uploaded"
    }
```

### 22.4 Job 생성

```python
class JobCreateRequest(BaseModel):
    upload_id: str
    file_id: str
    job_type: str = "analysis"
    options: dict = {}

@router.post("/jobs")
def create_job(req: JobCreateRequest, user=Depends(get_current_user)):
    job_id = uuid4()

    # 1. uploaded_file 권한 검증
    # 2. analysis_jobs insert
    # 3. Redis queue enqueue
    # 4. job_queue_history insert

    return {
        "job_id": str(job_id),
        "status": "queued",
        "current_stage": "queued",
        "stage_progress": 0,
        "total_progress": 0,
        "next_url": f"/jobs/{job_id}/progress"
    }
```

### 22.5 Job status

```python
@router.get("/jobs/{job_id}/status")
def get_job_status(job_id: str, user=Depends(get_current_user)):
    # 1. analysis_jobs 권한 검증
    # 2. Redis progress 조회
    # 3. 없으면 analysis_jobs 조회
    # 4. file/result metadata 결합

    return {
        "job_id": job_id,
        "job_type": "analysis",
        "status": "processing",
        "current_stage": "visual_detection",
        "stage_progress": 55,
        "total_progress": 37,
        "queue_position": 2,
        "eta_seconds": 180,
        "message": "시각 개인정보 탐지 중입니다."
    }
```

### 22.6 Internal progress callback

```python
class JobProgressRequest(BaseModel):
    status: str
    current_stage: str
    stage_progress: int
    total_progress: int
    queue_position: int | None = None
    eta_seconds: int | None = None
    message: str | None = None
    payload: dict | None = None

@router.post("/internal/jobs/{job_id}/progress")
def internal_job_progress(job_id: str, req: JobProgressRequest, worker=Depends(verify_worker_token)):
    # 1. analysis_jobs update
    # 2. Redis progress set
    # 3. stage 변경/주요 이벤트면 job_stage_logs insert
    # 4. WebSocket broadcast

    return {"ok": True}
```

---

## 23. Next.js Frontend 구현 예시

### 23.1 upload 상태

```ts
type UploadState = {
  uploadId?: string;
  file?: File;
  uploadedChunks: number[];
  uploadProgress: number;
  status: 'idle' | 'initialized' | 'uploading' | 'uploaded' | 'failed' | 'cancelled';
  error?: string;
};
```

### 23.2 job 상태

```ts
type JobState = {
  jobId?: string;
  jobType?: 'analysis' | 'preview' | 'render' | 'sns_scan';
  status?: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelling' | 'cancelled' | 'retrying' | 'worker_timeout' | 'cleanup_required';
  currentStage?: string;
  stageProgress: number;
  totalProgress: number;
  queuePosition?: number;
  etaSeconds?: number;
  message?: string;
  cancelRequested?: boolean;
};
```

### 23.3 chunk upload pseudo code

```ts
async function uploadFileInChunks(file: File) {
  const initRes = await api.post('/uploads/init', {
    file_name: file.name,
    file_size: file.size,
    mime_type: file.type,
    chunk_size: 5 * 1024 * 1024,
  });

  const { upload_id, chunk_size, total_chunks } = initRes.data;

  for (let index = 0; index < total_chunks; index++) {
    const start = index * chunk_size;
    const end = Math.min(start + chunk_size, file.size);
    const blob = file.slice(start, end);

    const form = new FormData();
    form.append('chunk_index', String(index));
    form.append('file', blob);

    await api.post(`/uploads/${upload_id}/chunks`, form);

    updateUploadProgress(((index + 1) / total_chunks) * 100);
  }

  const completeRes = await api.post(`/uploads/${upload_id}/complete`);
  return completeRes.data;
}
```

### 23.4 WebSocket + Polling fallback hook

```ts
function useJobProgress(jobId: string) {
  const [job, setJob] = useState<JobState | null>(null);
  const [lastEventAt, setLastEventAt] = useState<number>(Date.now());
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pollingTimer: ReturnType<typeof setInterval> | null = null;
    let watchdogTimer: ReturnType<typeof setInterval> | null = null;

    async function fetchStatus() {
      const res = await api.get(`/jobs/${jobId}/status`);
      setJob(res.data);
      if (['completed', 'failed', 'cancelled'].includes(res.data.status)) {
        if (pollingTimer) clearInterval(pollingTimer);
      }
    }

    function startPolling(intervalMs = 5000) {
      setFallback(true);
      if (pollingTimer) return;
      pollingTimer = setInterval(fetchStatus, intervalMs);
    }

    fetchStatus();

    ws = new WebSocket(`${process.env.NEXT_PUBLIC_WS_URL}/ws/jobs/${jobId}`);

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      setLastEventAt(Date.now());
      setJob(payload);
      if (payload.status === 'completed' || payload.status === 'failed' || payload.status === 'cancelled') {
        ws?.close();
        if (pollingTimer) clearInterval(pollingTimer);
      }
    };

    ws.onerror = () => startPolling(5000);
    ws.onclose = () => startPolling(5000);

    watchdogTimer = setInterval(() => {
      if (Date.now() - lastEventAt > 10000) {
        startPolling(5000);
      }
    }, 3000);

    return () => {
      ws?.close();
      if (pollingTimer) clearInterval(pollingTimer);
      if (watchdogTimer) clearInterval(watchdogTimer);
    };
  }, [jobId]);

  return { job, fallback };
}
```

---

## 24. 전체 Sequence

```text
User selects file on Page08
→ Front validates file
→ Front creates upload session
→ Front uploads chunks to Backend
→ Backend stores chunks
→ Backend merges chunks
→ Backend validates file
→ Backend creates uploaded_files row
→ Backend creates analysis_jobs row
→ Backend enqueues Redis job
→ Backend inserts job_queue_history
→ Front moves to Page09
→ Front calls GET /jobs/{job_id}/status
→ Front connects WebSocket
→ Colab worker receives job
→ Colab downloads file from Backend
→ Colab sends heartbeat periodically
→ Colab sends progress periodically
→ Backend updates Redis progress
→ Backend updates analysis_jobs representative state
→ Backend inserts job_stage_logs on important events
→ Backend inserts job_worker_heartbeats
→ Backend broadcasts WebSocket event
→ Front updates stepper/progress
→ WebSocket fails if network issue
→ Front starts polling fallback
→ Colab uploads result/report metadata
→ Backend inserts job_results
→ Backend marks analysis_jobs completed
→ Backend broadcasts job.completed
→ Front moves to Page10
→ User requests substitution on Page15
→ Backend creates analysis_jobs row with job_type=render
→ Page17 displays render progress
→ Render result completed
→ Page18 download
→ Page19 history/dashboard updated
```

---

## 25. 실패/재시도 정책

### 25.1 실패 유형

```text
upload_failed
merge_failed
validation_failed
queue_failed
worker_timeout
colab_runtime_error
ngrok_disconnected
result_upload_failed
cancelled_by_user
```

### 25.2 retry 가능 여부

| 상태 | retry 가능 | 설명 |
|---|---:|---|
| upload_failed | O | chunk resume 가능 |
| merge_failed | O | chunk가 모두 있으면 재병합 가능 |
| validation_failed | X | 파일 자체 문제 |
| worker_timeout | O | queue 재진입 가능 |
| colab_runtime_error | O | retry_count 제한 |
| result_upload_failed | O | 결과 재업로드 요청 가능 |
| cancelled | X | 사용자 의도 취소 |

### 25.3 retry_count 권장

```text
기본 최대 2회
worker_timeout은 최대 1~2회
validation_failed는 retry 불가
```

---

## 26. 보안 원칙

```text
- 사용자 파일 다운로드 URL은 internal token 또는 short-lived signed token 필요
- Colab callback은 internal worker token 검증 필요
- upload_id/job_id는 반드시 user_id 소유권 검증
- 파일 확장자와 MIME type 모두 검증
- path traversal 방지
- temp path는 user_id/upload_id 기준으로 격리
- 결과 파일 다운로드도 user_id 권한 검증
- WebSocket 연결 시 인증 필요
- job_id 구독 시 소유권 검증 필요
```

---

## 27. 환경변수 예시

```env
UPLOAD_TEMP_DIR=storage/uploads/temp
UPLOAD_MERGED_DIR=storage/uploads/merged
RESULT_STORAGE_DIR=storage/results
DEFAULT_CHUNK_SIZE_BYTES=5242880
MAX_UPLOAD_SIZE_BYTES=1073741824
UPLOAD_SESSION_TTL_HOURS=24

REDIS_URL=redis://localhost:6379/0
JOB_PROGRESS_TTL_SECONDS=86400
JOB_HEARTBEAT_TTL_SECONDS=300

COLAB_WORKER_INTERNAL_TOKEN=change-me
INTERNAL_FILE_DOWNLOAD_TOKEN_TTL_SECONDS=600
WORKER_HEARTBEAT_WARNING_SECONDS=30
WORKER_HEARTBEAT_TIMEOUT_SECONDS=60
WORKER_HEARTBEAT_FAIL_SECONDS=120

WS_BASE_URL=ws://localhost:8000
API_BASE_URL=http://localhost:8000
```

---

## 28. 구현 우선순위

### Phase 1: 필수 MVP

```text
1. upload_sessions/upload_chunks/uploaded_files 추가
2. analysis_jobs 확장 컬럼 추가
3. chunk upload API 구현
4. upload complete merge 구현
5. analysis job 생성 구현
6. Redis queue enqueue 구현
7. /jobs/{job_id}/status 구현
8. internal progress callback 구현
9. WebSocket progress broadcast 구현
10. Page09 진행률 UI 연결
```

### Phase 2: 안정성

```text
1. Polling fallback
2. Page19 진행중 작업 복원
3. Colab heartbeat
4. worker_timeout 처리
5. 작업 취소
6. retry
```

### Phase 3: 확장

```text
1. Page17 render job
2. job_results
3. 완료 알림
4. SNS scan 연결
5. 관리자 모니터링
```

---

## 29. Codex / Claude Code 작업 지시문

아래 지시문을 그대로 전달하면 된다.

```text
GARIM 프로젝트의 대용량 파일 업로드 및 Colab 진행률 처리 구조를 구현한다.

반드시 이 문서의 v5 기준을 따른다.

핵심 제약:
1. 신규 jobs 테이블을 만들지 않는다.
2. 기존 analysis_jobs 테이블을 확장해서 job 상태를 관리한다.
3. 진행률 이벤트 테이블명은 job_progress_events가 아니라 job_stage_logs를 사용한다.
4. Colab heartbeat 이력은 job_worker_heartbeats를 사용한다.
5. Redis queue 이력은 job_queue_history를 사용한다.
6. Frontend는 Colab에 직접 파일을 업로드하지 않는다.
7. Frontend는 Backend에 chunk upload 한다.
8. Backend가 파일 병합, 검증, Job 생성, 상태 저장의 중심이다.
9. Colab은 Backend에서 파일을 다운로드하고 progress/heartbeat/result를 Backend로 callback 한다.
10. WebSocket만 믿지 말고 Polling fallback을 반드시 구현한다.
11. Page09 분석 진행률, Page17 render 진행률, Page19 진행중 작업 복원을 구현한다.
12. Redis는 실시간 상태, PostgreSQL은 영속 상태로 역할을 분리한다.

구현 범위:
- upload_sessions/upload_chunks/uploaded_files 테이블
- analysis_jobs 확장 컬럼
- job_stage_logs/job_worker_heartbeats/job_queue_history/job_results 테이블
- POST /uploads/init
- POST /uploads/{upload_id}/chunks
- GET /uploads/{upload_id}/status
- POST /uploads/{upload_id}/complete
- POST /jobs
- GET /jobs/{job_id}/status
- POST /jobs/{job_id}/cancel
- POST /jobs/{job_id}/retry
- POST /internal/jobs/{job_id}/progress
- POST /internal/jobs/{job_id}/heartbeat
- POST /internal/jobs/{job_id}/result
- POST /internal/jobs/{job_id}/failed
- WS /ws/jobs/{job_id}
- GET /me/jobs/in-progress

작업 후 다음을 확인한다.
- 500MB 이상 파일도 chunk 단위 업로드 가능
- 업로드 중 실패 후 재시도 가능
- upload complete 시 chunk 병합 가능
- Job 생성 후 Page09에서 진행률 표시 가능
- WebSocket이 끊겨도 Polling으로 복원 가능
- Colab heartbeat가 끊기면 worker_timeout 처리 가능
- Page19에서 진행중 작업 복원 가능
- 취소 요청 시 cancelling → cancelled 흐름 동작
```

---

## 30. 테스트 체크리스트

### 30.1 Upload

```text
[ ] /uploads/init 호출 시 upload_id 생성
[ ] chunk 파일이 temp 경로에 저장됨
[ ] 같은 chunk 재업로드 시 중복 오류 없이 idempotent 처리
[ ] /uploads/{upload_id}/status가 uploaded_chunks 반환
[ ] 일부 chunk 누락 시 complete 실패
[ ] 모든 chunk 업로드 후 complete 성공
[ ] merged 파일 생성
[ ] uploaded_files row 생성
```

### 30.2 Job

```text
[ ] /jobs 호출 시 analysis_jobs row 생성
[ ] status=queued 저장
[ ] current_stage=queued 저장
[ ] Redis queue에 job_id 진입
[ ] job_queue_history entered 저장
```

### 30.3 Progress

```text
[ ] Colab progress callback 수신
[ ] Redis progress 갱신
[ ] analysis_jobs 대표 상태 갱신
[ ] stage 변경 시 job_stage_logs 저장
[ ] WebSocket으로 Front에 push
[ ] /jobs/{job_id}/status로 같은 상태 조회
```

### 30.4 WebSocket/Polling

```text
[ ] Page09 진입 시 status 초기 조회
[ ] WebSocket 연결 성공
[ ] progress event 수신 시 UI 업데이트
[ ] WebSocket 강제 종료 시 polling 시작
[ ] polling으로 진행률 복원
[ ] completed/failed/cancelled 시 polling 중지
```

### 30.5 Heartbeat

```text
[ ] Colab heartbeat callback 수신
[ ] Redis heartbeat 갱신
[ ] job_worker_heartbeats 저장
[ ] 60초 이상 미수신 시 worker_timeout 처리
[ ] WebSocket job.worker_timeout push
```

### 30.6 Page19

```text
[ ] /me/jobs/in-progress가 queued/processing/cancelling/retrying/worker_timeout 반환
[ ] analysis job 진행중이면 Page09로 이동
[ ] render job 진행중이면 Page17로 이동
[ ] completed면 report/download 화면으로 이동
[ ] failed면 실패 상세 또는 재시도 안내
```

### 30.7 Cancel

```text
[ ] POST /jobs/{job_id}/cancel 호출
[ ] analysis_jobs.cancel_requested=true
[ ] status=cancelling
[ ] Redis cancel flag 생성
[ ] Colab loop에서 cancel 감지
[ ] safe stop 후 status=cancelled
[ ] WebSocket job.cancelled push
```

---

## 31. 피해야 할 구조

```text
Front → Colab 직접 업로드
진행률을 메모리에만 저장
WebSocket만 사용하고 fallback 없음
Colab 결과만 믿고 Backend 상태 미저장
작업 취소 flag 없이 프로세스 강제 종료
신규 jobs 테이블을 별도로 만들어 analysis_jobs와 역할 중복
job_progress_events와 job_stage_logs를 동시에 사용해 중복 저장
heartbeat를 Redis에만 저장하고 이력 미보관
Queue 처리 이력을 남기지 않음
Page19에서 진행중 작업 복원 불가
```

---

## 32. 권장 구조 요약

```text
Front → Backend 업로드
Backend 중심 analysis_jobs 관리
Redis 실시간 상태
PostgreSQL 영속 상태
job_stage_logs 단계 이력
job_worker_heartbeats Worker 생존 이력
job_queue_history Queue 이력
WebSocket + Polling fallback
Colab heartbeat
작업 취소 safe stop
Page19 진행중 작업 복원
```

---

## 33. 최종 구현 기준

이 문서의 최종 구현 기준은 다음이다.

```text
1. Backend가 시스템의 중심이다.
2. Colab은 교체 가능한 Worker다.
3. Frontend는 진행률 표시와 사용자 조작에 집중한다.
4. Redis는 빠른 실시간 데이터에만 사용한다.
5. PostgreSQL은 복구 가능한 상태와 이력에 사용한다.
6. WebSocket은 UX 향상 수단이며 유일한 상태 저장소가 아니다.
7. Polling은 필수 fallback이다.
8. analysis_jobs가 Job 대표 테이블이다.
9. Page09/Page17/Page19 흐름이 끊기면 안 된다.
10. 작업자가 이 문서만 보고 구현해도 누락이 없어야 한다.
```

