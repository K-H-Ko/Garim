# Admin Policy 플랜 노출 상태 단일화 작업 지시서

## 목적

현재 구독 플랜과 크레딧 플랜은 사용자 화면 노출 여부를 `is_active`와 `status` 두 값으로 함께 판단한다.

```text
is_active = true/false
status = active/inactive/deleted
```

이 구조는 `status = active`인데 `is_active = false`인 모호한 상태를 만들 수 있다. 관리자 화면에서도 "관리 상태"와 "사용자 화면 노출"이 역할상 겹치기 때문에 운영자가 이해하기 어렵다.

따라서 플랜의 사용자 노출과 삭제 처리는 `status` 하나로 정리한다.

추가로 구독 플랜의 pricing 버튼 문구를 관리자가 직접 수정하는 기능도 제거한다. 버튼 문구는 화면 흐름에서 고정 규칙으로 결정되도록 하고, `plans.cta_label` 컬럼과 관련 UI/API 기능은 더 이상 사용하지 않는다.

## 결정 사항

구독 플랜과 크레딧 플랜의 상태 의미를 아래처럼 통일한다.

| status | 의미 | 사용자 화면 노출 |
| --- | --- | --- |
| `active` | 판매/노출 중 | 노출 |
| `inactive` | 판매 중지/비노출 | 비노출 |
| `deleted` | 삭제 처리 | 비노출, 관리자 기본 목록 제외 |

`is_active`는 더 이상 화면/API/가격 페이지의 노출 판단에 사용하지 않는다.

`cta_label`은 더 이상 구독 플랜 정책 데이터로 관리하지 않는다.

버튼 문구는 pricing 화면의 액션 목적에 맞춰 프론트에서 고정 처리한다.

예:

| 조건 | 버튼 문구 |
| --- | --- |
| 무료 플랜 또는 가격 0원 | `무료로 시작` |
| 유료 구독 플랜 | `결제하기` |

정확한 분기 기준은 기존 pricing 페이지의 결제 이동 흐름을 유지하면서 정한다. 핵심은 관리자가 플랜별 버튼 문구를 입력하지 않도록 하는 것이다.

## 작업 범위

### 1. 관리자 화면 수정

대상 파일:

- `frontend/src/pages/garim/AdminPolicy.jsx`

작업:

- 구독 플랜 폼의 `사용자 화면 노출` 토글 제거
- 크레딧 플랜 폼의 `사용자 화면 노출` 토글 제거
- 구독 플랜 폼의 `버튼 문구` 입력 필드 제거
- 폼 기본값에서 `is_active` 제거
- 폼 기본값에서 `cta_label` 제거
- 저장 payload에서 `is_active`가 전달되지 않도록 제거
- 저장 payload에서 `cta_label`이 전달되지 않도록 제거
- 화면에서 노출 여부는 `관리 상태` select의 `active/inactive/deleted`만 사용
- pricing 미리보기에서 버튼 문구는 `cta_label` 입력값이 아니라 고정 분기값을 사용

관리자에게 보여주는 상태 문구는 기존처럼 유지해도 된다.

```text
active -> 운영
inactive -> 중지
deleted -> 삭제
```

### 2. Pricing 노출 기준 수정

대상 파일:

- `frontend/src/hooks/usePricingPlans.js`

작업:

- 구독 플랜 필터에서 `plan.isActive` 조건 제거
- 크레딧 플랜 필터에서 `plan.isActive` 조건 제거
- 노출 기준은 `plan.status === "active"`만 사용
- 구독 플랜 데이터 매핑에서 `payment.ctaLabel` 또는 `cta_label` 기반 버튼 문구 override 제거
- 버튼 문구는 pricing 화면 또는 hook 내부의 고정 규칙으로 결정

예상 형태:

```js
.filter((plan) => plan.status === "active")
```

### 3. 백엔드 관리자/정책 API 수정

대상 파일:

- `backend/services/admin.py`
- 필요 시 `backend/controllers/admin.py`
- 필요 시 `backend/routes/admin.py`

작업:

- `PLAN_FIELDS`, `CREDIT_PLAN_FIELDS`에서 `is_active` 제거
- `PLAN_FIELDS`에서 `cta_label` 제거
- 생성/수정 payload 정리 시 `is_active`를 받지 않도록 제거
- 생성/수정 payload 정리 시 `cta_label`을 받지 않도록 제거
- 목록 조회용 필터에서 `is_active` 파라미터 제거
- 관리자 목록 조회는 기본적으로 `status <> 'deleted'`만 적용
- pricing 정책 조회는 `status = 'active'`만 적용
- pricing 정책 응답에서 `ctaLabel` 제거

기존 쿼리 예:

```sql
WHERE is_active = TRUE
  AND status = 'active'
```

변경 후:

```sql
WHERE status = 'active'
```

### 4. DB 초기화 SQL 수정

대상 파일:

- `docker/database/init/0_init_table_v9.sql`

작업:

- `plans.is_active` 컬럼 제거
- `credit_plans.is_active` 컬럼 제거
- `plans.cta_label` 컬럼 제거
- 관련 COMMENT 제거
- 관련 INSERT seed에서 `is_active` 컬럼과 값 제거
- 관련 INSERT seed에서 `cta_label` 컬럼과 값 제거
- 관련 UPSERT update 문에서 `is_active = EXCLUDED.is_active` 제거
- 관련 UPSERT update 문에서 `cta_label = EXCLUDED.cta_label` 제거
- 관련 인덱스 변경

기존 인덱스 예:

```sql
idx_plans_active_status_sort ON plans (is_active, status, sort_order)
idx_credit_plans_active_status_sort ON credit_plans (is_active, status, sort_order)
```

변경 후 예:

```sql
idx_plans_status_sort ON plans (status, sort_order)
idx_credit_plans_status_sort ON credit_plans (status, sort_order)
```

### 5. DB 설계 엑셀 수정

대상 파일:

- `docs/db/Garim_DB_Design_final_clean_v9.xlsx`

작업:

- `plans` 시트에서 `is_active` 컬럼 제거
- `credit_plans` 시트에서 `is_active` 컬럼 제거
- `plans` 시트에서 `cta_label` 컬럼 제거
- 변경 요약 시트가 있다면 `is_active 제거, status 단일화` 내용 추가
- 변경 요약 시트가 있다면 `cta_label 제거, 버튼 문구 프론트 고정 처리` 내용 추가

### 6. 문서 수정

대상 파일:

- `docs/admin_policy/admin_policy_plan_management.md`

작업:

- `is_active`를 유지한다는 설명 제거
- `cta_label` 또는 `버튼 문구`를 플랜 정책으로 수정한다는 설명 제거
- 사용자 화면 노출 기준을 `status = active`로 변경
- 삭제는 `status = deleted` 소프트 삭제로 유지
- API query parameter 설명에서 `is_active` 필터 제거
- pricing 조회 SQL 예시에서 `is_active = true` 제거
- pricing 버튼 문구는 플랜 정책 컬럼이 아니라 화면 고정 규칙으로 처리한다고 정리

## 테스트 수정

대상 파일:

- `backend/tests/test_admin_policy.py`
- `tests/test_frontend_analysis_progress_static.py`

작업:

- `is_active` 필드 존재를 기대하는 assertion 제거
- `cta_label` 필드 존재를 기대하는 assertion 제거
- `사용자 화면 노출` 토글 존재를 기대하는 assertion 제거
- `버튼 문구` 입력 필드 존재를 기대하는 assertion 제거
- pricing 필터 기대값을 `status === "active"` 기준으로 수정
- pricing hook에서 `ctaLabel` override를 기대하는 assertion 제거
- 백엔드 SQL 기대값에서 `WHERE is_active = TRUE` 제거
- 백엔드 SQL 기대값에서 `cta_label` select/insert/update를 기대하는 assertion 제거
- 새 인덱스명 또는 SQL 문구를 검사한다면 `status_sort` 기준으로 수정

## 완료 기준

- 관리자 플랜 추가/수정 화면에서 `사용자 화면 노출` 토글이 보이지 않는다.
- 구독 플랜과 크레딧 플랜은 `관리 상태`만으로 노출 여부가 결정된다.
- pricing 페이지에는 `status = active`인 플랜만 표시된다.
- `inactive`, `deleted` 플랜은 pricing 페이지에 표시되지 않는다.
- 삭제 버튼은 실제 삭제가 아니라 기존처럼 `status = deleted`로 변경한다.
- `is_active`가 frontend payload, backend field whitelist, pricing filter, DB schema, seed SQL에서 제거된다.
- `cta_label`이 frontend payload, backend field whitelist, pricing 정책 응답, DB schema, seed SQL에서 제거된다.
- 관리자 화면에서 `버튼 문구` 입력 필드가 보이지 않는다.
- pricing 카드 버튼 문구는 기존 사용자 흐름을 유지하는 고정 규칙으로 표시된다.
- 관련 테스트가 통과한다.

권장 검증 명령:

```bash
pytest backend/tests/test_admin_policy.py -q
pytest tests/test_frontend_analysis_progress_static.py -q
cd frontend && npm run build
```

## 주의 사항

- 이 프로젝트는 아직 실제 서비스가 아니므로 별도 migration 파일보다 v9 초기화 SQL과 DB 설계 문서를 직접 수정하는 방향이 현재 흐름에 맞다.
- `subscriptions.status`나 사용자 계정 `users.status` 등 다른 테이블의 status 의미는 건드리지 않는다.
- `plans.status`, `credit_plans.status`의 check constraint는 유지한다.
- `deleted` 상태는 관리자 기본 목록에서 숨기되, 추후 필요하면 `include_deleted` 옵션으로 조회할 수 있게 유지해도 된다.
