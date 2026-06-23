# Garim Colab Worker 실행 가이드

로컬 백엔드를 Cloudflare Tunnel로 공개하고 Colab worker를 연결하는 전체 절차.

---

## 사전 준비

| 항목              | 버전/조건                    |
| ----------------- | ---------------------------- |
| Docker Desktop    | 실행 중                      |
| Python 3.10+      | 백엔드 가상환경              |
| Node.js 18+       | 프론트 dev server            |
| Cloudflare Tunnel | `cloudflared` 실행 가능 환경 |
| Google Colab      | GPU 런타임 권장 (STT 속도)   |

---

## 1단계: 통합 서버 환경 실행

이제 DB, Redis, 백엔드, 프론트엔드가 프로젝트 최상위 폴더에서 Docker Compose 하나로 통합 실행됩니다.

1. 프로젝트 최상위 폴더(`Human_Final_PJ-main`)에서 `docker-compose -f docker-compose.dev.yml up -d --build` 실행
2. `http://localhost` 에 접속하여 프론트엔드와 백엔드가 정상 동작하는지 확인

> `.env.development` 파일에 `WORKER_SECRET`이 설정되어 있어야 합니다. (기본값 제공됨)

---

## 2단계: 백엔드 접속 URL 확인 및 외부 공개 (Cloudflare Tunnel)

구글 코랩(Colab) 환경에서 내 컴퓨터에서 실행 중인 백엔드에 접근하려면 외부에서 접속 가능한 도메인이나 터널 주소가 필요합니다.

**✅ [옵션 1] 정식 도메인이 있는 경우 (권장)**
이미 Cloudflare Zero Trust 등으로 도커 환경과 `garim.shop` 같은 정식 도메인이 영구적으로 연결되어 있다면, 별도의 스크립트 실행 없이 **이 단계를 건너뛰셔도 됩니다.** 
코랩 설정에서 백엔드 주소(`https://garim.shop/api/v1`)를 그대로 입력하시면 됩니다.

**⚠️ [옵션 2] 정식 도메인이 없는 경우 (일회성 임시 터널 사용)**
도메인이 없다면 `cloudflare_tunnel.py` 스크립트를 실행하여 1회용 임시 터널을 개통해야 합니다.
새 터미널을 열고 `backend` 폴더로 이동한 뒤 스크립트를 실행합니다.

```bash
cd backend
python cloudflare_tunnel.py
```

출력 예시에서 `https://xxxx.trycloudflare.com` 형태의 임시 터널 주소를 복사해 둡니다.
> **참고**: 임시 터널 세션이 종료되면 URL이 바뀝니다. 코랩을 다시 시작할 때마다 새 URL을 복사해서 코랩 설정에 입력해야 합니다.

---

## 3단계: Colab worker 설정 및 실행

### 3-1. 분석 파이프라인 파일을 Drive에 업로드

Google Drive의 `MyDrive/garim_colab` 폴더에 아래 2개 파이프라인 파일을 업로드합니다.

```text
colab_pipeline_stt.py
colab_pipeline_mask.py
```

### 3-2. garim_colab_worker.py 파이썬 실행 혹은 Colab 셀에 붙여넣기

`colab/garim_colab_worker.py` 코드를 열고 상단의 환경 설정 변수들을 반드시 수정해야 합니다.

```python
# ===== 환경설정 (모든 환경설정은 이부분에서 변경) =====
# 정식 도메인이 있으면 정식 도메인 입력, 없으면 2단계에서 복사한 trycloudflare 임시 URL 입력 (마지막 슬래시 제외)
BACKEND_URL   = "https://garim.shop/api/v1"      
WORKER_SECRET = "여기에_백엔드_env와_동일한_값"
WORKER_ID     = "colab-worker-01"                # 식별 이름 (자유)
```

수정 후 코드를 Colab 노트북에 붙여넣고 전체 실행하거나, `python garim_colab_worker.py` 명령어로 스크립트를 직접 실행합니다.

## 4단계: 업로드 확인 및 진행률 모니터링

통합 환경에 포함된 Nginx 및 프론트엔드를 사용해 테스트합니다.

브라우저에서 `http://localhost` 접속 후:

1. 로그인
2. `업로드` 페이지에서 영상 파일 업로드
3. 업로드 완료 후 자동으로 `analysis-progress` 페이지(`/analysis-progress`)로 이동
4. 진행률 바가 `file_download → visual_ocr → audio_extract → stt → pii_detect → beep_render → result_upload → completed` 순으로 업데이트되는지 확인

Colab 콘솔에서도 아래와 같은 로그가 출력되어야 한다:

```
09:01:23 [INFO] job 수신: <job_id> | upload: <upload_id>
09:01:24 [INFO] job 수락 완료
09:01:25 [INFO] 파일 다운로드 완료: upload_xxx.mp4 (45.3 MB)
09:01:50 [INFO] 시각 OCR 결과물 저장 완료: /content/garim_visual_pii/<upload_id>/visual_pii_detections.json
09:02:10 [INFO] 파이프라인 완료 | detection_count=3
09:02:11 [INFO] STT 결과 저장 완료: 42개 세그먼트
09:02:11 [INFO] job 완료: <job_id>
```

---

## 💡 구글 드라이브 용량 관리 주의사항 (테스트 목적 시)

본인 계정의 구글 드라이브를 연동하여 테스트하는 경우 다음 사항을 반드시 주의해야 합니다:

1. 파이프라인에서 추출/생성된 최종 결과물(특히 마스킹된 원본 영상 등 대용량 파일)은 **본인 구글 드라이브에 자동으로 생성된 폴더 내에 저장**됩니다.
2. 웹 플랫폼 히스토리 페이지에서 파일을 삭제하면 드라이브에서도 연동되어 자동 삭제됩니다.
3. **[핵심 주의사항]** 구글 드라이브 정책상 연동 삭제된 파일은 영구 삭제가 아닌 **'휴지통'**으로 이동합니다. 즉, 휴지통을 비우지 않으면 구글 드라이브 용량을 계속 차지합니다.
4. 따라서 본인 계정의 용량이 작을 경우, 수차례 테스트 시 용량 부족으로 오류가 발생할 수 있으므로 **주기적으로 구글 드라이브에 접속하여 '휴지통 비우기'**를 진행해야 합니다.

---

## 실패 시 확인 항목

### 로그

| 위치                   | 확인 방법                                    |
| ---------------------- | -------------------------------------------- |
| 백엔드 콘솔            | `uvicorn` 터미널 — HTTP 요청/응답, 오류 스택 |
| Colab 셀 출력          | `[ERROR]` 또는 `[WARNING]` 라인              |
| Cloudflare 터미널 로그 | 터널 URL 출력 및 연결 로그                   |

### DB 테이블

```sql
-- job 상태 확인
SELECT job_id, status, current_stage, total_progress, error_code, error_message
FROM analysis_jobs
ORDER BY created_at DESC
LIMIT 5;

-- 단계별 로그 확인
SELECT stage_name, stage_progress, total_progress, message, created_at
FROM job_stage_logs
WHERE job_id = '<job_id>'
ORDER BY created_at ASC;

-- Heartbeat 확인 (worker가 살아있는지)
SELECT worker_id, current_stage, progress_percent, heartbeat_at
FROM job_worker_heartbeats
WHERE job_id = '<job_id>'
ORDER BY heartbeat_at DESC
LIMIT 10;

-- STT/artifact 결과 확인
SELECT artifact_type, stored_path, metadata, created_at
FROM analysis_artifacts
WHERE job_id = '<job_id>';

-- PII 탐지 결과 확인
SELECT detection_type, label, start_time_sec, end_time_sec, detected_text
FROM detections
WHERE job_id = '<job_id>';
```

### 자주 발생하는 오류

| 오류                              | 원인                                          | 해결                                                        |
| --------------------------------- | --------------------------------------------- | ----------------------------------------------------------- |
| `401 Unauthorized`                | WORKER_SECRET 불일치                          | 프로젝트 최상위 `.env.development`의 값과 워커 코드 상단의 `WORKER_SECRET` 일치 여부 확인 |
| `Connection refused`              | Cloudflare Tunnel URL 만료 또는 백엔드 미실행 | Cloudflare Tunnel URL 재발급 후 워커 코드 `BACKEND_URL` 수정 및 재실행 |
| 저장/업로드 실패 또는 용량 오류   | 구글 드라이브 용량 초과 (휴지통 포함)         | 본인 구글 드라이브에 접속하여 파일 삭제 및 **'휴지통 비우기'** 완료 후 재실행 |
| `파일이 아직 준비되지 않았습니다` | 업로드 status 가 `uploaded` 아님              | DB `uploads` 테이블의 status 컬럼 상태 확인                 |
| `대기 중인 작업 없음`             | job이 큐에 없음                               | DB `analysis_jobs` 테이블의 status=`queued` 상태 확인       |
| 분석/마스킹 속도가 매우 느림      | Colab이 CPU 런타임으로 동작 중                | Colab 상단 메뉴 [런타임] > [런타임 유형 변경]에서 **T4 GPU**로 변경 후 재실행 |
