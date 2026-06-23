# GARIM Front/Back/Colab Upload Progress DB Master v6

## 0. v6 최종 결정

v6에서는 v5에서 추가했던 `upload_sessions`, `uploaded_files`를 별도 테이블로 유지하지 않는다.

최종 구조는 다음과 같다.

```text
users
  └─ uploads                         # 기존 uploads 확장
        ├─ upload_chunks              # 신규 유지
        └─ analysis_jobs              # 기존 분석 job 흐름 유지
```

## 1. v5 대비 변경 요약

| 구분 | v5 | v6 최종 |
|---|---|---|
| 업로드 세션 | `upload_sessions` 신규 | `uploads` 확장으로 통합 |
| chunk 단위 관리 | `upload_chunks` 신규 | 유지 |
| 병합 완료 파일 메타 | `uploaded_files` 신규 | `uploads` 확장으로 통합 |
| 분석 job 연결 | `uploaded_files` 또는 `upload_sessions` 경유 가능 | 기존처럼 `uploads.upload_id` 기준 |
| 중복 위험 | 있음 | 최소화 |

## 2. 제거한 테이블

v6에서는 아래 테이블을 생성하지 않는다.

```text
upload_sessions
uploaded_files
```

제거 이유는 기존 `uploads`와 역할이 겹치기 때문이다.

`upload_sessions`의 역할인 업로드 진행률, chunk 개수, 임시 경로, 만료 기준은 `uploads`에 컬럼을 추가해서 관리한다.

`uploaded_files`의 역할인 최종 원본 파일 메타데이터, 미디어 정보, 썸네일 정보도 `uploads`에 컬럼을 추가해서 관리한다.

## 3. 유지/추가한 테이블

v6에서 새로 유지되는 별도 테이블은 아래 하나다.

```text
upload_chunks
```

이 테이블은 기존 테이블과 중복되지 않는다.

필요한 이유:

- chunk 단위 저장 경로 관리
- chunk index 기반 병합 순서 보장
- chunk hash 기반 무결성 검증
- 끊긴 업로드 재개 시 누락 chunk 확인
- 실패 chunk 재시도 관리

## 4. uploads 확장 설계

### 4.1 역할

`uploads`는 v6부터 다음 역할을 함께 담당한다.

1. 업로드 원본 파일 메타데이터
2. chunk upload 세션 상태
3. chunk upload 진행률
4. 병합 완료 파일 경로
5. 미디어 메타데이터
6. 분석 job과 연결되는 기준 upload entity

### 4.2 CREATE TABLE

```sql
CREATE TABLE IF NOT EXISTS uploads (
    upload_id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    original_filename varchar(255) NOT NULL,
    stored_filename varchar(255) NOT NULL,
    stored_path text NOT NULL,
    content_type varchar(100) NOT NULL,
    file_size bigint NOT NULL,
    file_hash varchar(128),
    media_type varchar(20) NOT NULL,
    chunk_size integer,
    total_chunks integer,
    uploaded_chunks integer NOT NULL DEFAULT 0,
    temp_dir_path text,
    merged_file_path text,
    duration_seconds integer,
    width integer,
    height integer,
    thumbnail_path text,
    status varchar(30) NOT NULL DEFAULT 'initialized',
    expires_at timestamp,
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now(),
    deleted_at timestamp,
    CONSTRAINT pk_uploads PRIMARY KEY (upload_id)
);
```

### 4.3 주요 컬럼 설명

| 컬럼 | 설명 |
|---|---|
| `upload_id` | 업로드 단위 식별자. chunk upload, 분석 job 연결 기준 |
| `user_id` | 업로드 요청 사용자 |
| `original_filename` | 사용자가 업로드한 원본 파일명 |
| `stored_filename` | 백엔드 저장 파일명 또는 병합 완료 파일명 |
| `stored_path` | 최종 원본 파일 저장 경로 |
| `content_type` | MIME type |
| `file_size` | 원본 파일 크기 byte |
| `file_hash` | 최종 병합 파일 무결성 검증용 hash |
| `media_type` | video/image/audio |
| `chunk_size` | chunk upload 사용 시 chunk 크기 |
| `total_chunks` | 전체 chunk 수 |
| `uploaded_chunks` | 업로드 완료 chunk 수 |
| `temp_dir_path` | chunk 임시 저장 디렉터리 |
| `merged_file_path` | chunk 병합 완료 파일 경로 |
| `duration_seconds` | 영상/음성 재생 시간 |
| `width` | 이미지/영상 가로 크기 |
| `height` | 이미지/영상 세로 크기 |
| `thumbnail_path` | 썸네일 파일 경로 |
| `status` | 업로드 상태 |
| `expires_at` | 원본 자동 삭제 또는 미완료 업로드 만료 기준 |
| `updated_at` | 진행률/상태 갱신 시각 |

### 4.4 status 값

```text
initialized
uploading
uploaded
failed
expired
cancelled
deleted
```

## 5. upload_chunks 설계

### 5.1 역할

`upload_chunks`는 업로드된 chunk 파일 단위를 기록한다.

`upload_sessions`를 따로 두지 않으므로 반드시 `uploads(upload_id)`를 참조한다.

### 5.2 CREATE TABLE

```sql
CREATE TABLE IF NOT EXISTS upload_chunks (
    upload_chunk_id uuid NOT NULL DEFAULT gen_random_uuid(),
    upload_id uuid NOT NULL REFERENCES uploads(upload_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    chunk_size integer NOT NULL,
    chunk_hash varchar(128),
    storage_path text NOT NULL,
    status varchar(30) NOT NULL DEFAULT 'uploaded',
    created_at timestamp NOT NULL DEFAULT now(),
    CONSTRAINT pk_upload_chunks PRIMARY KEY (upload_chunk_id),
    CONSTRAINT uq_upload_chunks_upload_index UNIQUE (upload_id, chunk_index)
);
```

### 5.3 주요 컬럼 설명

| 컬럼 | 설명 |
|---|---|
| `upload_chunk_id` | chunk 레코드 식별자 |
| `upload_id` | `uploads.upload_id` 참조 |
| `chunk_index` | 0부터 시작하는 chunk 순번 |
| `chunk_size` | 실제 업로드된 chunk 크기 |
| `chunk_hash` | chunk 무결성 검증용 hash |
| `storage_path` | chunk 임시 저장 경로 |
| `status` | uploaded/failed |
| `created_at` | chunk 레코드 생성 시각 |

## 6. 인덱스

```sql
CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at
ON uploads (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_uploads_status_created_at
ON uploads (status, created_at);

CREATE INDEX IF NOT EXISTS idx_uploads_expires_at
ON uploads (expires_at)
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_upload_chunks_upload_index
ON upload_chunks (upload_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_upload_chunks_status_created_at
ON upload_chunks (status, created_at);
```

## 7. 업로드 진행 흐름

### 7.1 업로드 초기화

1. Frontend가 파일명, 파일 크기, MIME type, chunk 크기 등을 Backend에 전달한다.
2. Backend는 `uploads`에 row를 생성한다.
3. 상태는 `initialized`로 시작한다.
4. `total_chunks`, `chunk_size`, `temp_dir_path`, `expires_at`을 저장한다.

### 7.2 chunk 업로드

1. Frontend가 chunk를 순서 또는 병렬로 업로드한다.
2. Backend는 chunk 파일을 임시 디렉터리에 저장한다.
3. `upload_chunks`에 `upload_id`, `chunk_index`, `storage_path`를 저장한다.
4. 같은 `upload_id + chunk_index`는 unique 제약으로 중복 저장을 막는다.
5. 성공한 chunk 수만큼 `uploads.uploaded_chunks`를 갱신한다.
6. `uploads.status`는 `uploading`으로 갱신한다.

### 7.3 병합

1. `uploaded_chunks = total_chunks`가 되면 병합 가능 상태다.
2. Backend는 `upload_chunks`의 `chunk_index` 순서대로 파일을 병합한다.
3. 병합 완료 후 최종 파일 hash를 계산한다.
4. `uploads.stored_path`, `uploads.merged_file_path`, `uploads.file_hash`를 갱신한다.
5. 상태를 `uploaded`로 변경한다.

### 7.4 분석 job 생성

1. 업로드 상태가 `uploaded`가 되면 분석 job을 생성할 수 있다.
2. 기존 구조대로 `analysis_jobs.upload_id`는 `uploads.upload_id`를 참조한다.
3. AI 분석 내부 구현은 별도 개발자가 담당하므로 DB 기준으로는 job trigger 가능한 상태까지만 보장한다.

## 8. Colab 연동 기준

v6 DB 기준 Colab 연동은 다음처럼 본다.

```text
Frontend
  → Backend uploads 생성
  → Backend chunk 수신
  → Backend chunk 병합
  → uploads.status = uploaded
  → analysis_jobs 생성
  → Backend/Worker/Colab job 실행
  → job_stage_logs / progress 갱신
  → WebSocket 또는 polling으로 frontend에 진행률 전달
```

## 9. WebSocket / Progress 기준

업로드 진행률은 `uploads` 기준으로 계산한다.

```text
upload_progress = uploaded_chunks / total_chunks * 100
```

분석 진행률은 기존처럼 `analysis_jobs`, `job_stage_logs` 기준으로 관리한다.

즉, 업로드 진행률과 분석 진행률은 분리한다.

| 구분 | 기준 테이블 |
|---|---|
| 파일 업로드 진행률 | `uploads`, `upload_chunks` |
| 분석 job 진행률 | `analysis_jobs`, `job_stage_logs` |

## 10. 기존 v5 대비 주의사항

v5에서 만들어졌던 아래 테이블은 v6에서는 사용하지 않는다.

```text
upload_sessions
uploaded_files
```

따라서 기존 DB에 이미 v5를 적용했다면 운영/개발 환경에 따라 migration에서 아래 처리가 필요할 수 있다.

```sql
DROP TABLE IF EXISTS uploaded_files;
DROP TABLE IF EXISTS upload_sessions;
```

단, 실제 데이터가 존재하는 환경에서는 반드시 백업 후 마이그레이션해야 한다.

## 11. v6 파일 구성

이번 v6 산출물은 다음 3개다.

1. `GARIM_front_back_colab_upload_progress_db_v6_IMPLEMENTATION_MASTER.md`
2. `Garim_DB_Design_final_clean_v6.xlsx`
3. `0_init_table_v6.sql`

## 12. 최종 결론

GARIM 현재 구조에서는 아래 방식이 가장 적합하다.

```text
uploads 확장 + upload_chunks 추가
```

이 구조는 다음 장점이 있다.

- 기존 `uploads → analysis_jobs` 흐름 유지
- `upload_sessions`, `uploaded_files`와의 중복 제거
- chunk upload 재개/검증/병합 가능
- DB 구조가 단순해짐
- Front/Back/Colab 파이프라인 연결 기준이 명확해짐
