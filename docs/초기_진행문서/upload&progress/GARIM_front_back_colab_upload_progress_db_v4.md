# GARIM Front-Back-Colab 업로드/진행률 처리 최종 개발 가이드 v2

## 1. 문서 목적

이 문서는 GARIM 프로젝트의 `Front → Back → Colab` 구조에서 대용량 파일 업로드, AI 분석/치환 처리, 실시간 진행률 표시, DB 진행률 저장, WebSocket/Polling 연동 방식을 개발자가 구현할 수 있도록 정리한 최종 개발 가이드다.

이번 버전은 DB 설계 v4 수정사항을 반영한다.

주요 반영 사항:

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
→ sns_diagnosis_jobs.job_id → analysis_jobs.job_id 연결
```

기준 화면 흐름은 다음과 같다.

```text
Page08 파일 업로드
→ Page09 분석 처리 진행
→ Page10 분석 리포트
→ Page15 치환 옵션 설정
→ Page17 처리 진행
→ Page18 다운로드
→ Page19 마이 대시보드 진행중 작업 복원
```

---

## 2. 최종 서버 구조

```text
User
  ↓
Frontend
  ↓
Backend API
  ↓
Redis Queue / Cache
  ↓
Colab Worker via ngrok
  ↓
Backend API
  ↓
Frontend
```

현재 MVP 환경에서는 별도 유료 Object Storage 없이 Backend 서버가 파일 업로드와 임시 저장을 담당한다.

### 역할 분리

| 영역 | 역할 |
|---|---|
| Frontend | 업로드 UI, 진행률 표시, WebSocket 연결, Polling fallback, 대시보드 복원 |
| Backend | 인증, 업로드 수신, 파일 임시 저장, Job 생성, 상태 저장, Colab 연동, 알림 발송 |
| Redis | 실시간 진행률 캐시, 큐, 최신 heartbeat, socket payload cache |
| PostgreSQL | 작업 이력, 단계 로그, heartbeat 이력, 큐 이력, 파일 메타데이터, 결과 메타데이터 |
| Colab | AI 분석, OCR/STT/마스킹/렌더링 처리 |

---

## 3. 업로드 처리 최종안

### 기본 방향

```text
Frontend
→ Backend chunk upload
→ Backend temp storage
→ upload complete
→ analysis_jobs row create
→ Redis enqueue
→ Colab processing
```

Colab에 사용자가 직접 업로드하지 않는다. Colab은 런타임 종료, ngrok 연결 끊김, 업로드 중단 가능성이 있기 때문에 사용자 업로드 endpoint로 사용하기에 불안정하다.

### Chunk Upload 필요성

500MB~1GB급 파일을 단일 요청으로 업로드하면 실패 시 처음부터 다시 업로드해야 한다. 따라서 Backend는 chunk 단위 업로드를 지원해야 한다.

```text
1. POST /uploads/init
2. POST /uploads/{upload_id}/chunks
3. POST /uploads/{upload_id}/complete
4. POST /jobs
```

### Upload Session 데이터

```text
upload_id
user_id
file_name
file_size
mime_type
total_chunks
uploaded_chunks
file_hash
status
created_at
updated_at
expires_at
```

### 업로드 상태

```text
initialized
uploading
uploaded
failed
expired
cancelled
```

---

## 4. Job 생성 구조

업로드 완료 후 Backend는 `analysis_jobs`에 작업을 생성한다.

```text
upload complete
→ file validation
→ file metadata save
→ analysis_jobs insert
→ Redis queue enqueue
→ job_queue_history insert
→ Page09 이동
```

### Job 생성 시점

Job은 파일이 Backend에 정상적으로 저장되고 서버 검증까지 통과한 뒤 생성한다.

검증 항목:

```text
파일 확장자
MIME type
파일 크기
hash 중복 여부
사용자 권한
콘텐츠 권리 확인 동의 여부
플랜별 제한
```

---

## 5. Page09 분석 처리 진행 구조

Page09는 단순 progress bar가 아니라 단계별 상태를 표시해야 한다.

### 분석 Stepper

```text
1. upload_completed
2. queued
3. visual_detection
4. audio_detection
5. report_generation
```

### Page09 표시 정보

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
```

---

## 6. Page17 처리 진행 구조

치환/렌더링 단계는 분석 단계와 별도 job_type 또는 stage로 관리한다.

### 치환 Stepper

```text
1. option_confirmed
2. preview_generation
3. render_processing
4. watermarking
5. output_encoding
6. completed
```

### Page17 표시 정보

```text
선택된 치환 옵션
처리 대상 개수
현재 처리 단계
렌더링 진행률
워터마크 삽입 상태
예상 완료 시간
취소 가능 여부
```

---

## 7. DB 저장 구조 v4

진행률을 단순히 메모리나 WebSocket 이벤트로만 관리하면 안 된다. 새로고침, 페이지 이탈, 소켓 끊김, Colab 장애 상황에서 복원할 수 없기 때문이다.

DB v4에서는 신규 `jobs` 테이블을 만들지 않고, 기존 `analysis_jobs`를 작업 오케스트레이션 중심 테이블로 확장한다.

### 7.1 analysis_jobs 역할

`analysis_jobs`는 사용자에게 보이는 작업의 대표 상태를 저장한다.

역할:

```text
분석 작업 상태 관리
치환/렌더링 작업 상태 관리
SNS 스캔 작업 상태 관리
진행률/ETA/큐 위치 저장
취소 요청 flag 저장
결과 파일/리포트 연결
대시보드 진행중 작업 복원
```

### analysis_jobs 주요 컬럼

```sql
-- 기존 analysis_jobs에 추가/확장되는 주요 컬럼
job_type VARCHAR(30) DEFAULT 'analysis'
current_stage VARCHAR(50)
stage_progress INTEGER DEFAULT 0
total_progress INTEGER DEFAULT 0
queue_position INTEGER
eta_seconds INTEGER
message TEXT
cancel_requested BOOLEAN DEFAULT FALSE
error_code VARCHAR(100)
error_message TEXT
result_file_path TEXT
report_id UUID
```

### status enum

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

### job_type enum

```text
analysis
preview
render
sns_scan
white_list_scan
metadata_scan
```

### current_stage 예시

분석:

```text
upload_completed
queued
visual_detection
audio_detection
metadata_detection
report_generation
completed
```

치환/렌더링:

```text
option_confirmed
preview_generation
render_processing
watermarking
output_encoding
completed
```

장애/취소:

```text
cancelling
worker_timeout
cleanup_required
failed
cancelled
```

---

## 8. 보조 테이블 구조

### 8.1 job_stage_logs

`job_stage_logs`는 작업 단계 변경과 진행률 변경 이력을 저장한다.

용도:

```text
Page09/Page17 진행 단계 이력
디버깅
장애 추적
관리자 처리 로그 확인
진행률 이벤트 audit
```

권장 저장 시점:

```text
stage 변경 시
progress가 일정 비율 이상 변할 때
상태가 failed/cancelled/completed로 바뀔 때
Colab callback 중 중요한 message가 발생할 때
```

예시:

```sql
CREATE TABLE job_stage_logs (
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
```

---

### 8.2 job_worker_heartbeats

`job_worker_heartbeats`는 Colab/ngrok/Worker 생존 신호 이력을 저장한다.

Redis에는 최신 heartbeat만 저장하고, PostgreSQL에는 이력성 데이터로 남긴다.

용도:

```text
Colab 런타임 종료 감지
ngrok 연결 끊김 감지
worker_timeout 판단
작업 재시도 판단
관리자 장애 분석
```

예시:

```sql
CREATE TABLE job_worker_heartbeats (
    heartbeat_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    worker_task_id UUID REFERENCES worker_tasks(worker_task_id) ON DELETE SET NULL,
    worker_id VARCHAR(100),
    worker_type VARCHAR(50) DEFAULT 'colab',
    public_endpoint TEXT,
    current_stage VARCHAR(50),
    progress INTEGER DEFAULT 0,
    message TEXT,
    heartbeat_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

---

### 8.3 job_queue_history

`job_queue_history`는 Redis Queue의 진입, 해제, 우선순위 변경 이력을 저장한다.

Redis는 실제 큐 처리를 담당하고, PostgreSQL은 큐 이력과 분석용 데이터를 담당한다.

용도:

```text
Page09 Free 사용자 큐 위치 표시 근거
v1 플랜별 우선순위 큐 분석
관리자 큐 모니터링
취소/재시도 이력 추적
```

예시:

```sql
CREATE TABLE job_queue_history (
    queue_log_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    worker_task_id UUID REFERENCES worker_tasks(worker_task_id) ON DELETE SET NULL,
    queue_name VARCHAR(50) DEFAULT 'default',
    priority INTEGER DEFAULT 0,
    queue_position INTEGER,
    event_type VARCHAR(30) DEFAULT 'entered',
    entered_at TIMESTAMP,
    dequeued_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

event_type:

```text
entered
dequeued
reprioritized
cancelled
failed
retrying
```

---

### 8.4 sns_diagnosis_jobs 연결

SNS 진단 작업은 `analysis_jobs.job_type = 'sns_scan'`으로 대표 작업을 만들고, `sns_diagnosis_jobs`는 SNS 진단 상세/요약 정보를 저장한다.

관계:

```text
analysis_jobs.job_id
  ↓
sns_diagnosis_jobs.job_id
```

즉, `analysis_jobs`는 작업 상태/진행률/큐를 담당하고, `sns_diagnosis_jobs`는 SNS 계정 진단 결과와 리포트 성격의 정보를 담당한다.

---

## 9. 진행률 이벤트 저장 방식

Colab은 Backend에 진행률을 주기적으로 전달한다.

```text
Colab
→ POST /internal/jobs/{job_id}/progress
→ Backend
→ Redis update
→ analysis_jobs update
→ 필요 시 job_stage_logs insert
→ WebSocket broadcast
```

### progress payload 예시

```json
{
  "job_id": "uuid",
  "status": "processing",
  "current_stage": "visual_detection",
  "stage_progress": 55,
  "total_progress": 37,
  "queue_position": 2,
  "eta_seconds": 180,
  "message": "시각 개인정보 탐지 중입니다."
}
```

### 저장 원칙

```text
Redis: 매 이벤트마다 최신 상태 저장
analysis_jobs: 화면 복원에 필요한 대표 상태 저장
job_stage_logs: stage 변경 또는 주요 이벤트만 저장
WebSocket: 사용자에게 즉시 push
```

PostgreSQL에 모든 이벤트를 초 단위로 저장하면 write 부하가 커질 수 있으므로, `job_stage_logs`는 stage 변경/주요 progress 변경/audit/debug 기준으로 저장한다.

---

## 10. Redis와 PostgreSQL 역할 분리

### Redis

```text
job:{job_id}:progress
job:{job_id}:heartbeat
job:{job_id}:cancel
queue:analysis
queue:render
queue:sns_scan
socket:user:{user_id}
```

Redis는 빠르게 변하는 실시간 상태와 큐 처리를 담당한다.

### PostgreSQL

```text
analysis_jobs
upload_sessions / uploaded_files
job_stage_logs
job_worker_heartbeats
job_queue_history
sns_diagnosis_jobs
notifications
worker_tasks
```

PostgreSQL은 영속적으로 남겨야 하는 작업 이력과 결과 메타데이터를 담당한다.

### 역할 기준

| 데이터 | Redis | PostgreSQL |
|---|---|---|
| 최신 진행률 | O | analysis_jobs에도 대표 상태 저장 |
| 모든 진행 이벤트 | X | job_stage_logs에 주요 이벤트 저장 |
| 최신 heartbeat | O | job_worker_heartbeats에 이력 저장 |
| Queue 실제 처리 | O | job_queue_history에 이력 저장 |
| 작업 최종 상태 | X | analysis_jobs |
| 대시보드 복원 | 보조 | analysis_jobs 기준 |
| 관리자 분석 | X | job_stage_logs / job_queue_history / worker_tasks |

---

## 11. WebSocket 구조

### 연결 시점

Page09 또는 Page17 진입 시 연결한다.

```text
GET /jobs/{job_id}/status
→ 현재 상태 초기화
→ WebSocket subscribe
→ progress event 수신
```

### WebSocket event type

```text
job.progress
job.stage_changed
job.completed
job.failed
job.cancelled
job.worker_timeout
job.cleanup_required
```

### WebSocket payload

```json
{
  "type": "job.progress",
  "job_id": "uuid",
  "status": "processing",
  "current_stage": "audio_detection",
  "stage_progress": 20,
  "total_progress": 62,
  "eta_seconds": 90,
  "message": "음성 개인정보 탐지 중입니다."
}
```

---

## 12. Polling fallback 구조

WebSocket만 사용하면 안 된다. 브라우저 네트워크, 프록시, Colab/ngrok 문제로 이벤트가 끊길 수 있다.

### fallback 조건

```text
WebSocket disconnected
WebSocket reconnect failed
마지막 progress event 수신 후 10초 이상 경과
페이지 새로고침
대시보드 복원
```

### Polling endpoint

```text
GET /jobs/{job_id}/status
```

이 endpoint는 Redis 최신 상태를 우선 조회하고, 없으면 `analysis_jobs` 대표 상태를 조회한다.

### 권장 주기

```text
processing: 3~5초
queued: 5~10초
completed/failed/cancelled: polling 중지
```

---

## 13. Page19 대시보드 복원

대시보드는 진행 중 작업을 복원해야 한다.

### API

```text
GET /me/jobs/in-progress
```

### 조회 기준

```sql
SELECT *
FROM analysis_jobs
WHERE user_id = :user_id
  AND status IN ('queued', 'processing', 'cancelling', 'retrying', 'worker_timeout')
ORDER BY created_at DESC;
```

### 응답 예시

```json
[
  {
    "job_id": "uuid",
    "file_name": "sample.mp4",
    "job_type": "analysis",
    "status": "processing",
    "current_stage": "visual_detection",
    "total_progress": 37,
    "eta_seconds": 180,
    "thumbnail_url": "/files/thumb/sample.jpg"
  }
]
```

### 이동 규칙

```text
job_type=analysis + 진행중 → /jobs/{id}/progress
job_type=analysis + completed → /jobs/{id}/report
job_type=preview + 진행중 → /jobs/{id}/preview-progress
job_type=render + 진행중 → /jobs/{id}/processing
job_type=render + completed → /jobs/{id}/download
job_type=sns_scan + 진행중 → /sns/jobs/{id}/progress
job_type=sns_scan + completed → /sns/jobs/{id}/report
failed → 실패 상세 화면 또는 재시도 안내
```

---

## 14. 작업 취소 로직

Page09, Page17에서 취소 버튼을 제공할 경우 Backend 중심으로 취소해야 한다.

```text
Frontend
→ POST /jobs/{job_id}/cancel
→ Backend analysis_jobs.cancel_requested = true
→ analysis_jobs.status = cancelling
→ Redis cancel flag set
→ Colab heartbeat/progress loop에서 cancel 확인
→ safe stop
→ temp file cleanup
→ analysis_jobs.status = cancelled
→ job_stage_logs insert
→ job_queue_history insert(event_type=cancelled)
→ WebSocket job.cancelled
```

### 취소 상태

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

---

## 15. Colab heartbeat / 장애 대응

Colab은 처리 중 일정 주기로 heartbeat를 Backend에 보내야 한다.

```text
POST /internal/jobs/{job_id}/heartbeat
```

### heartbeat payload

```json
{
  "job_id": "uuid",
  "worker_id": "colab-session-id",
  "worker_type": "colab",
  "public_endpoint": "https://xxxx.ngrok-free.app",
  "current_stage": "visual_detection",
  "progress": 37,
  "timestamp": "2026-05-22T10:00:00Z"
}
```

### Backend 처리

```text
Redis job:{job_id}:heartbeat update
job_worker_heartbeats insert
analysis_jobs.updated_at update
필요 시 WebSocket 상태 유지
```

### timeout 기준

```text
마지막 heartbeat 30초 초과: warning
마지막 heartbeat 60초 초과: worker_timeout
마지막 heartbeat 120초 초과: failed 또는 retry 대기
```

worker_timeout 발생 시:

```text
analysis_jobs.status = worker_timeout
analysis_jobs.current_stage = worker_timeout
job_stage_logs insert
WebSocket job.worker_timeout
```

---

## 16. Colab 연동 방식

Backend가 Colab에 직접 파일을 전송하거나, Colab이 Backend에서 파일을 다운로드한다.

MVP에서는 다음 방식이 현실적이다.

```text
Backend가 파일을 임시 저장
→ Colab에 job_id와 download_url 전달
→ Colab이 Backend에서 파일 다운로드
→ 처리 진행
→ 결과 파일 Backend로 업로드
```

### Colab job start 예시

```json
{
  "job_id": "uuid",
  "input_file_url": "https://backend/internal/files/{file_id}",
  "callback_progress_url": "https://backend/internal/jobs/{job_id}/progress",
  "callback_heartbeat_url": "https://backend/internal/jobs/{job_id}/heartbeat",
  "callback_result_url": "https://backend/internal/jobs/{job_id}/result"
}
```

---

## 17. 완료 알림 2-track

완료 알림은 두 갈래로 처리한다.

### 1) 실시간 접속 사용자

```text
WebSocket job.completed
→ Front 즉시 Page10 또는 Page18 이동 안내
```

### 2) 이탈 사용자

```text
Email notification
Browser notification
Dashboard 진행중 카드 상태 변경
```

---

## 18. Frontend 상태관리 설계

Frontend에서는 다음 상태를 분리해서 관리한다.

```text
uploadState
jobState
socketState
historyState
notificationState
```

### uploadState

```text
upload_id
file
uploaded_chunks
upload_progress
status
error
```

### jobState

```text
job_id
job_type
status
current_stage
stage_progress
total_progress
eta_seconds
queue_position
message
cancel_requested
```

### socketState

```text
connected
reconnecting
last_event_at
fallback_polling_enabled
```

---

## 19. API 엔드포인트 정리

### Upload

```text
POST /uploads/init
POST /uploads/{upload_id}/chunks
POST /uploads/{upload_id}/complete
DELETE /uploads/{upload_id}
```

### Job

```text
POST /jobs
GET /jobs/{job_id}/status
GET /jobs/{job_id}/report
POST /jobs/{job_id}/cancel
POST /jobs/{job_id}/retry
```

### Internal Colab Callback

```text
POST /internal/jobs/{job_id}/start
POST /internal/jobs/{job_id}/progress
POST /internal/jobs/{job_id}/heartbeat
POST /internal/jobs/{job_id}/result
POST /internal/jobs/{job_id}/failed
```

### My Page

```text
GET /me/jobs
GET /me/jobs/in-progress
GET /me/jobs/{job_id}
```

### SNS

```text
POST /sns/diagnosis-jobs
GET /sns/diagnosis-jobs/{job_id}
GET /sns/diagnosis-jobs/{job_id}/report
```

---

## 20. 전체 Sequence

```text
User selects file on Page08
→ Front validates file
→ Front creates upload session
→ Front uploads chunks to Backend
→ Backend merges chunks
→ Backend validates file
→ Backend creates analysis_jobs row
→ Backend enqueues Redis job
→ Backend inserts job_queue_history
→ Front moves to Page09
→ Front connects WebSocket
→ Colab worker receives job
→ Colab downloads file from Backend
→ Colab sends heartbeat/progress
→ Backend updates Redis
→ Backend updates analysis_jobs
→ Backend inserts job_stage_logs on stage changes
→ Backend inserts job_worker_heartbeats
→ Backend broadcasts WebSocket
→ Front updates stepper/progress
→ Colab uploads result/report metadata
→ Backend marks analysis_jobs completed
→ Front moves to Page10
→ User requests substitution
→ Backend creates analysis_jobs row with job_type=render
→ Page17 render progress
→ Result completed
→ Page18 download
→ Page19 history/dashboard updated
```

---

## 21. 개발 시 주의사항

### 피해야 할 구조

```text
Front → Colab 직접 업로드
진행률을 메모리에만 저장
WebSocket만 사용하고 fallback 없음
Colab 결과만 믿고 Backend 상태 미저장
작업 취소 flag 없이 프로세스 강제 종료
신규 jobs 테이블을 별도로 만들어 analysis_jobs와 역할 중복
```

### 권장 구조

```text
Front → Backend 업로드
Backend 중심 analysis_jobs 관리
Redis 실시간 상태
PostgreSQL 영속 상태
job_stage_logs 단계 이력
job_worker_heartbeats Worker 생존 이력
job_queue_history 큐 이력
WebSocket + Polling fallback
Colab heartbeat
작업 취소 safe stop
```

---

## 22. 최종 결론

GARIM MVP 기준 가장 현실적인 구조는 다음과 같다.

```text
Frontend
  - 업로드 UI
  - 진행률 UI
  - WebSocket 연결
  - Polling fallback
  - 대시보드 복원

Backend
  - 파일 업로드 수신
  - 임시 저장
  - analysis_jobs 생성/관리
  - 상태 저장
  - Colab 연동
  - 알림 발송

Redis
  - Queue
  - 실시간 progress
  - 최신 heartbeat
  - cancel flag

PostgreSQL
  - analysis_jobs 대표 작업 상태
  - job_stage_logs 단계 이력
  - job_worker_heartbeats heartbeat 이력
  - job_queue_history 큐 이력
  - 파일 메타데이터
  - 결과 메타데이터
  - 감사 로그

Colab
  - AI 분석
  - 개인정보 탐지
  - 치환/마스킹/렌더링
```

이 구조는 현재 비용 없이 구현 가능하면서도, 이후 Object Storage, 독립 GPU Worker, Kubernetes Worker 구조로 확장할 수 있다.
