# Admin Policy Plan Management

## 목적

`/admin/policy` 페이지를 기존의 고정된 Free/Pro/Studio 정책 편집 화면에서, 관리자가 구독 플랜과 크레딧 플랜을 직접 추가/수정/삭제 처리할 수 있는 상품 관리 화면으로 개편한다.

이 페이지는 앞으로 `pricing` 페이지에 노출될 플랜 목록의 기준 데이터도 함께 관리한다. 따라서 구독 플랜과 크레딧 플랜 모두 표시 순서를 관리할 수 있어야 하며, 삭제는 실제 row 삭제가 아니라 상태 변경으로 처리한다.

## 메뉴 및 페이지 문구

### 메뉴명

기존:

```text
정책 설정
```

변경:

```text
정책 및 상품 관리
```

### 페이지 제목

```text
정책 및 상품 관리
```

### 제목 아래 설명 문구

```text
구독 플랜과 크레딧 플랜의 정책을 설정하고 관리할 수 있습니다.
```

## 화면 구성

### 기본 구조

`/admin/policy` 페이지 안에서 구독 플랜과 크레딧 플랜을 탭으로 분리한다.

```text
[구독 플랜] [크레딧 플랜]
```

각 탭은 서로 다른 테이블과 편집 폼을 가진다.

- 구독 플랜 탭: `plans` 테이블 관리
- 크레딧 플랜 탭: `credit_plans` 테이블 관리

### 공통 기능

구독 플랜과 크레딧 플랜 모두 다음 기능을 제공한다.

- 목록 조회
- 검색
- 추가
- 수정
- 삭제 처리
- 표시 순서 관리
- 관리 상태 관리 (운영, 중지, 삭제)

## 정렬 정책

구독 플랜과 크레딧 플랜 모두 `sort_order` 컬럼을 둔다.

목록 조회와 `pricing` 페이지 노출은 아래 순서를 따른다.

```sql
ORDER BY sort_order ASC, created_at ASC
```

관리자 화면에서는 `sort_order` 값을 직접 수정할 수 있어야 한다.

추후 드래그 앤 드롭 정렬을 추가할 수 있지만, 1차 구현에서는 숫자 입력 방식으로 충분하다.

## 삭제 정책

플랜 삭제는 실제 DB row 삭제가 아니라 상태 변경으로 처리한다.

권장 컬럼:

```sql
status varchar(20) NOT NULL DEFAULT 'active'
```

권장 상태값:

- `active`: 사용 중
- `inactive`: 비활성
- `deleted`: 삭제 처리

삭제 버튼을 누르면 해당 row의 `status`를 `deleted`로 변경한다.

```sql
UPDATE plans
SET status = 'deleted', updated_at = NOW()
WHERE plan_id = :plan_id;
```

```sql
UPDATE credit_plans
SET status = 'deleted', updated_at = NOW()
WHERE credit_plan_id = :credit_plan_id;
```

관리자 목록에서는 기본적으로 `deleted` 상태를 제외한다. 필요하면 추후 "삭제된 항목 보기" 필터를 추가한다.

플랜의 노출 제어와 상태 관리는 `status` 단일 컬럼으로 처리한다.

- `status = active`: 사용자 화면 노출 (운영)
- `status = inactive`: 사용자 화면 비노출 (중지)
- `status = deleted`: 사용자 및 관리자 기본 목록 미노출 (삭제)

## 구독 플랜 관리

### 대상 테이블

```text
plans
```

### 추가/수정 가능 필드

관리자 화면에서 구독 플랜 추가/수정 시 아래 필드를 관리할 수 있어야 한다.

| 필드 | 설명 | 예시 |
| --- | --- | --- |
| `plan_code` | 플랜 식별 코드 | `free`, `pro`, `studio` |
| `plan_name` | 사용자 표시명 | `Free`, `Pro`, `Studio` |
| `badge_label` | pricing 카드 상단 배지 문구 | `기본`, `추천`, `팀/스튜디오` |
| `badge_class` | pricing 카드 배지 스타일 클래스 | `mui-chip--primary`, `mui-chip--soft-warning` |
| `description` | pricing 카드 가격 아래 설명 문구 | `개인 테스트와 가벼운 분석을 위한 무료 플랜입니다.` |
| `sort_order` | 표시 순서 | `10`, `20`, `30` |
| `monthly_quota` | 월 처리 한도 | `5`, `50`, `500` |
| `result_retention_days` | 결과 보존 기간 | `3`, `7`, `30` |
| `watermark_required` | 워터마크 필수 여부 | `true`, `false` |
| `price_amount` | 월 결제 금액 | `0`, `19800` |
| `status` | 관리 상태 | `active`, `inactive`, `deleted` |
| `file_size_limit` | 최대 파일 크기 | `50`, `500`, `2048` |
| `max_jobs` | 동시 처리 가능 작업 수 | `3`, `10`, `30` |
| `auto_delete_original_hours` | 원본 파일 자동 삭제 시간 | `12` |
| `metadata_retention_days` | 메타데이터 보존 기간 | `90` |
| `credits` | 구독 시 제공 크레딧 | `5`, `50`, `500` |

### 목록 컬럼 제안

구독 플랜 탭의 목록은 아래 컬럼을 우선 노출한다.

| 컬럼 | 설명 |
| --- | --- |
| 순서 | `sort_order` |
| 코드 | `plan_code` |
| 플랜명 | `plan_name` |
| 배지 | `badge_label` |
| 가격 | `price_amount` |
| 제공 크레딧 | `credits` |
| 월 처리 한도 | `monthly_quota` |
| 파일 크기 | `file_size_limit` |
| 상태 | `status` |
| 관리 | 수정, 삭제 |

### 검색 대상

구독 플랜 검색은 아래 필드를 대상으로 한다.

- `plan_code`
- `plan_name`
- `status`

## 크레딧 플랜 관리

### 대상 테이블

```text
credit_plans
```

### 필드명 정리

요구사항에 적힌 `credit_pan_code`, `base_crdits`는 오타로 보고 실제 테이블 기준 필드명을 사용한다.

- `credit_pan_code` -> `credit_plan_code`
- `base_crdits` -> `base_credits`

### 추가/수정 가능 필드

관리자 화면에서 크레딧 플랜 추가/수정 시 아래 필드를 관리할 수 있어야 한다.

| 필드 | 설명 | 예시 |
| --- | --- | --- |
| `credit_plan_code` | 크레딧 상품 식별 코드 | `credit_100` |
| `credit_plan_name` | 사용자 표시명 | `100 크레딧` |
| `sort_order` | 표시 순서 | `10`, `20` |
| `price_amount` | 결제 금액 | `5000`, `20000` |
| `base_credits` | 기본 지급 크레딧 | `100`, `500` |
| `bonus_credits` | 보너스 지급 크레딧 | `0`, `100` |
| `expires_days` | 유효 기간 | `NULL`, `365` |
| `status` | 관리 상태 | `active`, `inactive`, `deleted` |

`bonus_credits`는 기존 DB 설계에 포함되어 있으므로 관리자 화면에서도 함께 관리하는 것을 권장한다. 이벤트성 크레딧 상품을 만들 때 별도 컬럼 추가 없이 운영할 수 있다.

### 목록 컬럼 제안

크레딧 플랜 탭의 목록은 아래 컬럼을 우선 노출한다.

| 컬럼 | 설명 |
| --- | --- |
| 순서 | `sort_order` |
| 코드 | `credit_plan_code` |
| 상품명 | `credit_plan_name` |
| 가격 | `price_amount` |
| 기본 크레딧 | `base_credits` |
| 보너스 크레딧 | `bonus_credits` |
| 유효 기간 | `expires_days` |
| 상태 | `status` |
| 관리 | 수정, 삭제 |

### 검색 대상

크레딧 플랜 검색은 아래 필드를 대상으로 한다.

- `credit_plan_code`
- `credit_plan_name`
- `status`

## DB 변경 필요 사항

### `plans`

현재 `plans`에 없는 컬럼이 있다면 추가한다.

```sql
ALTER TABLE plans
    ADD COLUMN IF NOT EXISTS badge_label varchar(50),
    ADD COLUMN IF NOT EXISTS badge_class varchar(50),
    ADD COLUMN IF NOT EXISTS description text,
    ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS updated_at timestamp;
```

권장 제약조건:

```sql
ALTER TABLE plans
    ADD CONSTRAINT ck_plans_status
    CHECK (status IN ('active', 'inactive', 'deleted'));
```

이미 같은 이름의 제약조건이 있으면 중복 생성되지 않도록 init SQL에서 처리 방식을 정한다.

### `credit_plans`

현재 `credit_plans`에 없는 컬럼이 있다면 추가한다.

```sql
ALTER TABLE credit_plans
    ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'active';
```

권장 제약조건:

```sql
ALTER TABLE credit_plans
    ADD CONSTRAINT ck_credit_plans_status
    CHECK (status IN ('active', 'inactive', 'deleted'));
```

`sort_order`, `bonus_credits`, `expires_days`, `updated_at`은 v9 기준 설계에 이미 포함되어 있다.

## API 설계 제안

### 구독 플랜 API

관리자 전용 API로 분리한다.

```text
GET    /admin/plans
POST   /admin/plans
PUT    /admin/plans/{plan_id}
DELETE /admin/plans/{plan_id}
```

`DELETE`는 실제 삭제가 아니라 `status = deleted`로 변경한다.

목록 조회 query parameter:

| 이름 | 설명 |
| --- | --- |
| `q` | 검색어 |
| `include_deleted` | 삭제 항목 포함 여부 |

### 크레딧 플랜 API

```text
GET    /admin/credit-plans
POST   /admin/credit-plans
PUT    /admin/credit-plans/{credit_plan_id}
DELETE /admin/credit-plans/{credit_plan_id}
```

`DELETE`는 실제 삭제가 아니라 `status = deleted`로 변경한다.

목록 조회 query parameter:

| 이름 | 설명 |
| --- | --- |
| `q` | 검색어 |
| `include_deleted` | 삭제 항목 포함 여부 |

## Pricing 페이지 연동 방향

추후 `pricing` 페이지에서는 관리자에서 설정한 순서대로 플랜을 노출한다.

구독 플랜:

```sql
SELECT *
FROM plans
WHERE status = 'active'
ORDER BY sort_order ASC, created_at ASC;
```

크레딧 플랜:

```sql
SELECT *
FROM credit_plans
WHERE status = 'active'
ORDER BY sort_order ASC, created_at ASC;
```

사용자 화면에서는 `deleted`, `inactive` 항목을 노출하지 않는다.

또한, 구독 플랜의 pricing 버튼 문구(`cta_label`)는 더 이상 DB에서 관리하지 않으며, 프론트엔드 화면의 고정 규칙(예: 무료 플랜 또는 가격이 0원이면 '무료로 시작', 유료 구독 플랜은 '결제하기')에 맞춰 동적으로 표시한다.

## 구현 태스크

- [x] **Task 1: DB 스키마 확인 및 v9 SQL 보강**
  - `plans.sort_order`, `plans.status`, `plans.updated_at` 확인
  - `credit_plans.status` 확인
  - status check constraint 추가 여부 결정

- [x] **Task 2: 관리자 플랜 API 추가**
  - 구독 플랜 CRUD API 추가
  - 크레딧 플랜 CRUD API 추가
  - 삭제는 soft delete로 구현
  - 검색 및 정렬 query 지원

- [x] **Task 3: `/admin/policy` 화면 구조 개편**
  - 메뉴명 변경
  - 제목 및 설명 문구 추가
  - 구독 플랜/크레딧 플랜 탭 분리
  - 각 탭에 검색, 목록, 추가, 수정, 삭제 기능 구성

- [x] **Task 4: 구독 플랜 폼 구현**
  - `plans` 필드 전체 입력/수정
  - boolean 필드는 toggle 사용
  - numeric 필드는 number input 사용
  - `status = deleted` 항목 기본 숨김

- [x] **Task 5: 크레딧 플랜 폼 구현**
  - `credit_plans` 필드 전체 입력/수정
  - `bonus_credits`, `expires_days` 포함
  - `status = deleted` 항목 기본 숨김

- [x] **Task 6: Pricing 페이지 연동 준비**
  - 구독 플랜과 크레딧 플랜 응답에 `sort_order` 포함
  - 프론트에서 `sort_order` 기준 정렬
  - 사용자 화면에서는 active 상태만 노출

- [x] **Task 7: 테스트**
  - 관리자 API 테스트
  - soft delete 테스트
  - 검색 테스트
  - 정렬 테스트
  - 프론트 정적 테스트 또는 빌드 검증

  검증 완료:

  ```powershell
  pytest backend/tests/test_admin_policy.py -q
  pytest tests/test_frontend_analysis_progress_static.py -q
  cmd /c npm run build
  ```

## 주의 사항

- 기존 Free/Pro/Studio 하드코딩 의존성을 제거해야 한다.
- 구독 플랜과 크레딧 플랜은 결제 로직에서 `product_type`으로 명확히 구분되어야 한다.
- 삭제된 플랜이 과거 결제 이력과 연결되어 있을 수 있으므로 실제 row 삭제는 금지한다.
- `plan_code`, `credit_plan_code`는 결제 URL과 API 요청에서 사용될 수 있으므로 중복을 허용하지 않는다.
- `pricing` 페이지 노출 순서는 관리자 화면의 `sort_order`를 기준으로 한다.
