# GARIM Front/Back/Colab Upload Progress DB Master v7

> **작업 에이전트 안내:** 이 계획을 구현할 때는 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용해 단계별 체크박스(`- [ ]`)로 진행한다.

**목표:** v6 DB 스키마는 변경하지 않고, 로컬 백엔드를 ngrok으로 공개한 뒤 Colab 전용 worker가 해당 백엔드 worker API에 붙어 실제 분석 파이프라인을 실행하게 만든다.

**아키텍처:** 백엔드는 업로드, job 생성, DB 상태 저장, 프론트 진행률 API를 계속 담당한다. 로컬 백엔드는 ngrok으로 외부 공개 URL을 만들고, Colab worker는 그 URL의 `/worker/*` API를 호출해 job 조회, 파일 다운로드, progress/heartbeat/complete/fail 보고를 수행한다. 프론트는 기존처럼 백엔드의 `/analysis/jobs/{job_id}`만 polling한다.

**기술 스택:** FastAPI, SQLAlchemy text query, PostgreSQL v6 schema, React/Vite, Python requests, Google Colab, ngrok, Whisper/ffmpeg 기반 Colab 분석 파이프라인.

---

## 0. v7 최종 방향

v7에서는 DB 스키마를 바꾸지 않는다.

유지하는 DB 테이블:

```text
uploads
upload_chunks
analysis_jobs
job_stage_logs
job_worker_heartbeats
job_queue_history
```

v7의 네트워크 방향은 아래와 같다.

```text
1. 로컬 PC에서 백엔드 FastAPI 실행
2. 로컬 PC에서 ngrok 실행
3. 로컬 백엔드 public URL 생성
4. Colab worker에 BACKEND_URL로 ngrok URL 설정
5. Colab worker가 백엔드 /worker/jobs/next polling
6. Colab worker가 job accept
7. Colab worker가 백엔드에서 원본 파일 다운로드
8. Colab worker가 분석 실행
9. Colab worker가 백엔드에 progress/heartbeat/complete/fail 보고
10. 프론트는 백엔드 analysis job 상태만 polling
```

핵심 구조:

```text
Frontend
  -> Local Backend
       -> DB 상태 저장
       -> ngrok으로 외부 공개

Colab Worker
  -> Local Backend ngrok URL
       -> /worker/jobs/next
       -> /worker/files/{upload_id}/download
       -> /worker/jobs/{job_id}/progress
       -> /worker/heartbeat
       -> /worker/jobs/{job_id}/complete or fail
```

주의할 점:

- Colab은 로컬 PC의 `127.0.0.1` 또는 로컬 파일 경로를 직접 읽을 수 없다.
- Colab이 접근할 수 있는 백엔드 URL은 ngrok public URL이어야 한다.
- Colab worker가 job을 polling하므로, 백엔드가 Colab으로 직접 dispatch하지 않는다.
- ngrok URL은 매번 바뀔 수 있으므로 Colab 설정의 `BACKEND_URL`을 갱신해야 한다.
- DB 테이블을 새로 만들지 않고 기존 v6 job/progress/heartbeat 구조를 그대로 사용한다.

---

## 1단계: Worker 파일 다운로드 API 추가

**목표:** Colab worker가 `uploads.stored_path` 같은 로컬 경로를 몰라도 업로드된 원본 파일을 받을 수 있게 한다.

**수정 파일:**

- `backend/services/worker.py`
- `backend/controllers/worker.py`
- `backend/routes/worker.py`
- 테스트 파일: `tests/test_worker_file_download.py` 또는 기존 worker 테스트 파일

**추가 API:**

```text
GET /worker/files/{upload_id}/download
Authorization: Bearer {WORKER_SECRET}
```

**동작:**

- `upload_id`로 `uploads` row를 조회한다.
- `status = 'uploaded'`인 파일만 다운로드 허용한다.
- 실제 파일 경로는 `uploads.stored_path` 또는 `uploads.merged_file_path`를 사용한다.
- 파일이 없으면 404를 반환한다.
- 인증 실패 시 401 또는 403 계열을 반환한다.
- 응답은 `FileResponse`로 내려준다.
- `Content-Disposition`에는 원본 파일명 기반 filename을 넣는다.

**완료 기준:**

- Colab 또는 외부 클라이언트가 ngrok 백엔드 URL로 파일 바이너리를 다운로드할 수 있다.
- 기존 `/worker/files/{upload_id}` 정보 조회 API는 유지된다.
- Colab worker는 로컬 PC의 파일 경로에 직접 의존하지 않는다.

**검증 명령:**

```bash
pytest tests/test_worker_file_download.py -q
pytest -q
```

**수동 검증 예시:**

```bash
curl -H "Authorization: Bearer ${WORKER_SECRET}" \
  "http://127.0.0.1:8000/worker/files/{upload_id}/download" \
  --output downloaded_input.mp4
```

ngrok 사용 시:

```bash
curl -H "Authorization: Bearer ${WORKER_SECRET}" \
  "https://xxxx.ngrok-free.app/worker/files/{upload_id}/download" \
  --output downloaded_input.mp4
```

---

## 2단계: Colab worker 클라이언트 스크립트 추가

**목표:** Colab에서 백엔드 worker API를 호출해 job을 가져오고, 진행률을 보고하는 worker loop를 만든다.

**생성 파일:**

- `docs/colab/garim_colab_worker.py`

**참고 파일:**

- `docs/colab/STT_implementation_plan.md`
- `docs/colab/korean_pii_beep_pipeline.py` 또는 실제 Colab 파이프라인 파일

**Colab 파일 작성 규칙:**

- `docs/colab/` 아래에 새로 만드는 worker/pipeline 파일은 Colab에서 바로 실행 가능한 형태로 작성한다.
- `.py` 파일로 저장하더라도 Colab 셀 단위 실행을 고려해 `# %% [markdown]`, `# %%` 셀 마커를 사용한다.
- 설치 셀, 설정 셀, worker API 함수 셀, pipeline 함수 셀, 실행 셀을 분리한다.
- 로컬 프로젝트 import에 의존하지 않고 Colab 런타임에서 필요한 패키지를 설치/로드할 수 있게 한다.
- 경로는 `/content/...` 기준을 기본으로 하고, 로컬 Windows 경로에 의존하지 않는다.

**필수 설정값:**

```python
BACKEND_URL = "https://xxxx.ngrok-free.app"
WORKER_SECRET = "same-value-as-backend"
WORKER_ID = "colab-worker-01"
POLL_INTERVAL_SECONDS = 10
HEARTBEAT_INTERVAL_SECONDS = 30
```

**구현 함수:**

```text
auth_headers()
get_next_job()
accept_job(job_id)
download_file(upload_id, output_dir)
report_progress(job_id, stage_name, stage_progress, total_progress, message)
send_heartbeat(job_id, stage_name, progress_percent, message)
complete_job(job_id, detection_count)
fail_job(job_id, error_code, error_message)
check_cancel(job_id)
run_once()
run_loop()
```

**최소 처리 흐름:**

```text
1. GET /worker/jobs/next
2. job이 없으면 대기
3. POST /worker/jobs/{job_id}/accept
4. heartbeat thread 시작
5. GET /worker/files/{upload_id}/download
6. PUT /worker/jobs/{job_id}/progress stage=file_download
7. dry-run 또는 실제 분석 실행
8. POST /worker/jobs/{job_id}/complete
9. heartbeat thread 종료
```

**완료 기준:**

- Colab에서 worker script를 실행하면 대기 job 하나를 가져올 수 있다.
- 파일 다운로드가 성공한다.
- progress와 heartbeat가 DB에 기록된다.
- 프론트 진행률 화면에서 Colab worker가 보낸 progress가 표시된다.

**검증 명령:**

```bash
python -m py_compile docs/colab/garim_colab_worker.py
pytest tests/test_analysis_progress_flow.py -q
```

**Colab 수동 검증:**

```python
job = get_next_job()
print(job)
```

```python
run_once()
```

---

## 3단계: Worker cancel 확인 흐름 보강

**목표:** 사용자가 프론트에서 분석 취소를 누르면 Colab worker가 다음 stage 전환 전에 취소 여부를 확인하고 중단할 수 있게 한다.

**수정 파일:**

- `backend/services/worker.py`
- `backend/controllers/worker.py`
- `backend/routes/worker.py`
- `docs/colab/garim_colab_worker.py`
- 테스트 파일: `tests/test_worker_cancel_flow.py`

**추가 API 후보:**

```text
GET /worker/jobs/{job_id}/status
Authorization: Bearer {WORKER_SECRET}
```

**응답 예시:**

```json
{
  "job_id": "uuid",
  "status": "processing",
  "cancel_requested": false,
  "current_stage": "stt",
  "total_progress": 45
}
```

**Colab 처리 규칙:**

- 긴 작업 전후로 `check_cancel(job_id)`를 호출한다.
- `cancel_requested = true`면 pipeline을 중단한다.
- cancel이면 더 이상 complete를 보내지 않는다.
- 필요하면 progress message에 `"취소 요청을 확인해 worker 처리를 중단했습니다."`를 기록한다.

**완료 기준:**

- 프론트 cancel 버튼이 `analysis_jobs.cancel_requested`를 true로 만든다.
- Colab worker가 cancel 상태를 조회할 수 있다.
- cancel 이후 worker가 complete로 덮어쓰지 않는다.

**검증 명령:**

```bash
pytest tests/test_worker_cancel_flow.py -q
pytest tests/test_analysis_progress_flow.py -q
```

---

## 4단계: 확장 가능한 분석 파이프라인 연결

**목표:** Colab worker의 dry-run 처리 대신 실제 분석 파이프라인을 연결한다. v7의 1차 대상은 Whisper STT, 개인정보 탐지, beep 처리이지만, 이후 얼굴/객체/장면/정책 위반 탐지 같은 다른 분석 로직도 같은 구조로 추가할 수 있게 만든다.

**수정 파일:**

- `docs/colab/garim_colab_worker.py`
- `docs/colab/korean_pii_beep_pipeline.py` 또는 새 모듈 `docs/colab/garim_pipeline.py`
- 필요 시 `backend/services/worker.py`
- 필요 시 `backend/controllers/worker.py`

**권장 분리:**

```text
docs/colab/garim_colab_worker.py
  - 백엔드 API 통신
  - worker polling loop
  - heartbeat
  - cancel check
  - progress/complete/fail 보고

docs/colab/garim_pipeline.py
  - 공통 pipeline registry
  - ffmpeg audio extract
  - Whisper STT analyzer
  - PII detection analyzer
  - beep processing analyzer
  - 이후 추가될 analyzer 모듈 연결 지점
  - result summary 생성
```

**pipeline 확장 규칙:**

```text
각 분석 로직은 analyzer 단위로 추가한다.
analyzer는 run(input_path, context) 형태의 단일 진입점을 가진다.
analyzer는 stage_name, stage_progress, total_progress, message를 worker에 보고한다.
새 analyzer를 추가해도 백엔드 DB 스키마는 바꾸지 않는다.
분석 결과 상세 저장 구조가 부족하면 v8에서 결과 저장 스키마를 별도 정의한다.
```

**1차 stage 정의:**

```text
file_download     total_progress 0  -> 10
audio_extract     total_progress 10 -> 20
stt               total_progress 20 -> 55
pii_detect        total_progress 55 -> 75
beep_render       total_progress 75 -> 90
result_upload     total_progress 90 -> 98
completed         total_progress 100
```

**최소 STT 결과 구조:**

```json
{
  "language": "ko",
  "full_text": "인식된 전체 텍스트",
  "segments": [
    {
      "id": 0,
      "start_ms": 0,
      "end_ms": 2500,
      "text": "구간 텍스트",
      "no_speech_prob": 0.01
    }
  ]
}
```

**완료 기준:**

- Colab에서 다운로드한 영상으로 1차 분석 파이프라인이 실행된다.
- stage별 progress가 프론트에 표시된다.
- 오디오 없는 파일은 실패가 아니라 빈 STT 결과 또는 별도 message로 정상 처리한다.
- 파이프라인 실패 시 `/worker/jobs/{job_id}/fail`로 error_code와 error_message를 남긴다.
- 이후 analyzer를 추가할 때 worker loop, progress API, 프론트 진행 화면을 다시 설계하지 않아도 된다.

**검증 명령:**

```bash
python -m py_compile docs/colab/garim_colab_worker.py
python -m py_compile docs/colab/garim_pipeline.py
```

---

## 5단계: 분석 결과 저장 API 추가

**목표:** Colab에서 만든 STT/PII/beep 및 이후 추가될 분석 결과를 백엔드에 저장할 수 있게 한다.

**DB 방침:**

- v7에서는 DB 스키마를 새로 바꾸지 않는다.
- 기존 DB에 `analysis_artifacts` 또는 결과 저장용 테이블이 이미 있으면 그 테이블을 사용한다.
- 결과 테이블이 아직 명확하지 않으면 이 단계에서는 파일 저장 + job message/detection_count 저장까지만 하고, 결과 상세 저장은 별도 v8로 분리한다.

**수정 파일:**

- `backend/services/worker.py`
- `backend/controllers/worker.py`
- `backend/routes/worker.py`
- `docs/colab/garim_colab_worker.py`
- 테스트 파일: `tests/test_worker_results_flow.py`

**추가 API 후보:**

```text
POST /worker/jobs/{job_id}/results/stt
POST /worker/jobs/{job_id}/results/pii
POST /worker/jobs/{job_id}/results/artifact
```

**STT 저장 요청 예시:**

```json
{
  "worker_id": "colab-worker-01",
  "upload_id": "uuid",
  "language": "ko",
  "full_text": "전체 텍스트",
  "segments": [
    {
      "id": 0,
      "start_ms": 0,
      "end_ms": 2500,
      "text": "구간 텍스트",
      "no_speech_prob": 0.01
    }
  ]
}
```

**완료 기준:**

- Colab worker가 분석 결과를 백엔드로 전송할 수 있다.
- 백엔드는 job_id/upload_id와 결과를 연결한다.
- 저장 실패 시 job은 failed가 되고 error_message가 남는다.
- 저장 성공 후 complete_job에서 detection_count 또는 result summary를 반영한다.

**검증 명령:**

```bash
pytest tests/test_worker_results_flow.py -q
pytest -q
```

---

## 6단계: 로컬 ngrok 실행/설정 문서화

**목표:** 로컬 백엔드를 ngrok으로 열고 Colab worker가 붙는 절차를 재현 가능하게 만든다.

**수정 파일:**

- `docs/colab/COLAB_WORKER_RUNBOOK.md`
- `backend/.env.sample`
- 필요 시 `backend/ngrok.py`

**문서에 포함할 내용:**

```text
1. 로컬 DB/Redis 실행
2. 로컬 백엔드 실행
3. WORKER_SECRET 설정
4. 로컬에서 ngrok으로 8000 포트 공개
5. Colab에서 BACKEND_URL/WORKER_SECRET/WORKER_ID 설정
6. Colab worker 실행
7. 업로드 후 analysis-progress 화면 확인
8. 실패 시 확인할 로그와 DB 테이블
```

**환경변수 예시:**

```env
WORKER_SECRET=change-me-worker-secret
PUBLIC_BACKEND_URL=https://xxxx.ngrok-free.app
```

**완료 기준:**

- 새 사람이 문서만 보고 로컬 백엔드와 Colab worker를 연결할 수 있다.
- ngrok URL이 바뀌어도 Colab의 `BACKEND_URL`만 바꾸면 재연결할 수 있다.
- worker 인증 실패, 파일 다운로드 실패, job 없음 상태의 대응이 문서화되어 있다.

**검증 명령:**

```bash
pytest -q
cmd /c npm run build
```

---

## 7단계: End-to-End 통합 검증

**목표:** 실제 브라우저 업로드부터 Colab 분석 완료까지 한 번에 검증한다.

**검증 흐름:**

```text
1. Docker DB/Redis 실행
2. 로컬 백엔드 실행
3. 프론트 dev server 실행
4. 로컬에서 ngrok으로 백엔드 공개
5. Colab worker 실행
6. 프론트에서 샘플 영상 업로드
7. 업로드 완료 후 analysis-progress 화면 이동 확인
8. Colab worker가 job polling/수신 확인
9. 파일 다운로드 성공 확인
10. stage progress가 프론트에 반영되는지 확인
11. complete 후 프론트 polling 중단 확인
12. DB의 analysis_jobs/job_stage_logs/job_worker_heartbeats 확인
```

**확인할 DB 테이블:**

```text
uploads
analysis_jobs
job_stage_logs
job_worker_heartbeats
job_queue_history
```

**성공 기준:**

- 업로드한 파일이 `uploads.status = uploaded`가 된다.
- `analysis_jobs.status`가 `queued -> processing -> completed`로 이동한다.
- `job_stage_logs`에 stage별 진행 기록이 남는다.
- `job_worker_heartbeats`에 Colab worker heartbeat가 남는다.
- 프론트 진행률 화면이 mock 값 없이 실제 progress를 표시한다.
- worker 실패 시 `analysis_jobs.status = failed`와 error_message가 표시된다.

**검증 명령:**

```bash
pytest -q
cmd /c npm run lint
cmd /c npm run build
cmd /c npm run test:garim
```

---

## v7에서 하지 않는 것

다음 항목은 v7 범위에서 제외한다.

```text
DB 스키마 변경
uploads/upload_chunks/analysis_jobs 구조 재설계
프론트 진행률 화면 전면 재디자인
백엔드를 Colab으로 통째로 이전
Colab worker를 FastAPI 서버로 공개하고 백엔드가 dispatch하는 구조
멀티 worker 스케줄러 고도화
S3/GCS 같은 외부 스토리지 전환
```

단, 분석 로직은 STT/PII/beep에 고정하지 않는다. v7에서는 확장 가능한 analyzer 구조를 만들고, 추가 분석기는 같은 worker/pipeline 인터페이스에 얹는 방식으로 확장한다.

---

## 권장 작업 순서 요약

```text
1. /worker/files/{upload_id}/download 추가
2. Colab worker dry-run 스크립트 작성
3. progress/heartbeat/complete 실제 연동 확인
4. cancel 확인 API 추가
5. 확장 가능한 분석 파이프라인 연결
6. 결과 저장 API 추가 여부 결정 및 구현
7. 로컬 ngrok/Colab 실행 문서화
8. 브라우저 업로드부터 Colab 완료까지 E2E 검증
```

---

## 최종 완료 기준

v7은 아래 조건을 모두 만족하면 완료로 본다.

- DB v6 스키마 변경 없이 Colab worker가 실제 job을 처리한다.
- 로컬에서 ngrok을 실행해 백엔드 API가 공개된다.
- Colab worker는 로컬 백엔드 ngrok URL의 `/worker/*` API를 사용한다.
- 파일 다운로드, heartbeat, progress, complete, fail 흐름이 동작한다.
- 프론트 진행률 화면은 Colab worker가 보고한 값을 표시한다.
- ngrok URL이 바뀌어도 Colab의 `BACKEND_URL`만 수정하면 다시 붙을 수 있다.
- `pytest -q`, `npm run lint`, `npm run build`, `npm run test:garim`이 통과한다.
