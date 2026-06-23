# Admin Policy 넓은 레이아웃 및 플랜별 페이지네이션 작업 지시서

## 목적

`/admin/policy` 페이지를 사용자 관리(`/admin/users`)와 분석 관리 화면처럼 가로 폭을 넓게 활용하도록 개편한다.

현재 admin/policy는 플랜 목록, 수정 폼, 미리보기 영역이 한 화면 안에서 제한된 폭으로 배치되어 있어 플랜 컬럼이 많아질수록 목록 확인이 답답해진다. 또한 구독 플랜과 크레딧 플랜 목록이 각각 독립적으로 페이지네이션되어야 하는데, 현재는 목록 전체를 한 번에 불러오거나 검색 결과 전체를 보여주는 구조에 가깝다.

이 작업의 목표는 다음 두 가지다.

- admin/policy 목록 영역을 가로로 넓게 사용한다.
- 구독 플랜과 크레딧 플랜 각각에 독립적인 `페이지`, `개수 선택`, `검색`, `상태 필터` 흐름을 제공한다.

## 대상 파일

- `frontend/src/pages/garim/AdminPolicy.jsx`
- `frontend/src/css/garim-pages/AdminPolicy.css`
- `frontend/src/utils/api.js`
- `backend/routes/admin.py`
- `backend/controllers/admin.py`
- `backend/services/admin.py`
- `backend/tests/test_admin_policy.py`
- `tests/test_frontend_analysis_progress_static.py`

필요 시 문서도 함께 수정한다.

- `docs/admin_policy/admin_policy_plan_management.md`

## 1. 넓은 레이아웃 개편

### 현재 문제

`AdminPolicy.css`에는 아래와 같은 정책 페이지 전용 폭 제한이 있다.

```css
.pol-content { padding: 32px 48px; }
.pol-content--wide { max-width: 1480px; }
.pol-manager { display: grid; ... }
```

현재 `AdminPolicy.jsx`는 `main`에 `adm-main pol-adm-main`, 내부에 `pol-content pol-content--wide`를 사용한다.

사용자 관리 페이지는 `adm-main`에 `padding: 24px 28px`만 두고 내부 카드를 넓게 사용한다. admin/policy도 이 방향에 맞춘다.

### 변경 방향

- `pol-content--wide`의 고정 최대 폭을 제거하거나 `width: 100%` 중심으로 변경한다.
- `pol-adm-main`은 사용자/분석 메뉴처럼 전체 가로 영역을 활용한다.
- 목록이 핵심인 화면이므로 `pol-list-panel`이 우선 넓게 보이도록 한다.
- 수정 폼과 미리보기는 목록 아래 또는 우측 보조 영역으로 둘 수 있지만, 목록 폭을 침범하지 않게 한다.

권장 레이아웃:

```text
[Sidebar] [Admin Policy Main ---------------------------------------]
          [Page title]
          [Tabs]
          [List toolbar: Add | Search | Status | Limit]
          [Wide table ------------------------------------------------]
          [Pagination]
          [Edit/Preview area]
```

### CSS 작업 지시

`AdminPolicy.css`에서 아래 방향으로 수정한다.

- `.pol-adm-main`
  - `padding: 24px 28px`
  - `background: #fafafa` 또는 기존 admin 배경과 통일
- `.pol-content`
  - `width: 100%`
  - `max-width` 제거
  - `padding` 과도하게 크지 않게 조정
- `.pol-content--wide`
  - `max-width: none` 또는 클래스 제거
- `.pol-manager--list-only`
  - 목록 전용이면 `display: block`
  - `.pol-list-panel`은 `width: 100%`
- 테이블 컬럼은 넓은 화면 기준으로 여유 있게 재조정한다.
- 모바일/좁은 화면에서는 기존처럼 1열로 떨어지게 유지한다.

## 2. 플랜별 독립 페이지네이션

## 요구사항

구독 플랜과 크레딧 플랜은 서로 다른 목록이므로 아래 상태를 각각 따로 가진다.

### 구독 플랜 상태

- `subscriptionPage`
- `subscriptionLimit`
- `subscriptionTotal`
- `subscriptionSearch`
- `subscriptionStatusFilter`

### 크레딧 플랜 상태

- `creditPage`
- `creditLimit`
- `creditTotal`
- `creditSearch`
- `creditStatusFilter`

탭을 전환해도 각 탭의 페이지/검색/개수 선택 상태는 유지한다.

검색어, 상태 필터, 개수 선택이 바뀌면 해당 탭의 page는 `1`로 초기화한다.

## 3. API 계약

현재 관리자 플랜 목록 API는 검색과 삭제 포함 여부 중심이다. 페이지네이션을 위해 아래 query parameter를 지원하도록 확장한다.

### GET `/admin/plans`

Query:

| 이름 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `page` | number | `1` | 조회 페이지 |
| `limit` | number | `20` | 페이지당 개수 |
| `q` | string | 없음 | 코드/이름 검색어 |
| `status` | string | 없음 | `active`, `inactive`, `deleted` |
| `include_deleted` | boolean | `false` | 삭제 항목 포함 여부 |

Response:

```json
{
  "data": [],
  "total": 0,
  "page": 1,
  "limit": 20
}
```

### GET `/admin/credit-plans`

Query/Response 구조는 `/admin/plans`와 동일하게 맞춘다.

## 4. 백엔드 작업 지시

### `backend/services/admin.py`

목록 조회 함수에 페이지네이션 인자를 추가한다.

```python
def list_subscription_plans(
    q=None,
    status=None,
    include_deleted=False,
    page=1,
    limit=20,
):
    ...
```

```python
def list_credit_plans(
    q=None,
    status=None,
    include_deleted=False,
    page=1,
    limit=20,
):
    ...
```

필터 규칙:

- `include_deleted = false`이면 기본적으로 `status <> 'deleted'`
- `status` 값이 있으면 해당 status만 조회
- `q`는 기존처럼 코드/이름 검색
- 정렬은 `sort_order ASC, created_at ASC`
- `LIMIT :limit OFFSET :offset` 적용
- 동일 조건으로 `COUNT(*)`를 조회해 `total` 반환

주의:

- `status` 값은 `active`, `inactive`, `deleted`만 허용한다.
- `page`는 최소 1, `limit`은 허용 범위 내 숫자로 제한한다.
- 권장 limit 옵션은 `5`, `10`, `20`, `50`, `100`이다.

### `backend/controllers/admin.py`, `backend/routes/admin.py`

라우트에서 `page`, `limit`, `status` query parameter를 받아 service에 전달한다.

## 5. 프론트엔드 작업 지시

### `frontend/src/utils/api.js`

`getAdminPlans`, `getAdminCreditPlans`에서 아래 query를 지원한다.

```js
getAdminPlans({
  page,
  limit,
  q,
  status,
  include_deleted,
})
```

크레딧 플랜도 동일하게 지원한다.

### `frontend/src/pages/garim/AdminPolicy.jsx`

구독/크레딧 탭별로 독립 상태를 둔다.

```js
const [subscriptionPage, setSubscriptionPage] = useState(1);
const [subscriptionLimit, setSubscriptionLimit] = useState(20);
const [subscriptionTotal, setSubscriptionTotal] = useState(0);

const [creditPage, setCreditPage] = useState(1);
const [creditLimit, setCreditLimit] = useState(20);
const [creditTotal, setCreditTotal] = useState(0);
```

검색/필터/개수 변경 시:

- 현재 탭의 page를 1로 초기화
- 해당 탭 목록만 다시 조회

목록 요청 예:

```js
getAdminPlans({
  page: subscriptionPage,
  limit: subscriptionLimit,
  q: subscriptionSearch,
  status: subscriptionStatusFilter || undefined,
  include_deleted: false,
})
```

### UI 구성

각 탭의 목록 상단 toolbar는 아래 순서로 배치한다.

```text
[플랜 추가] [검색 입력] [상태 select] [개수 select] [개씩 보기]
```

각 탭의 목록 하단에는 독립 페이지네이션을 둔다.

```text
1-20 / 53     [이전] [다음]
```

표시 문구 계산:

```js
const start = total === 0 ? 0 : (page - 1) * limit + 1;
const end = Math.min(page * limit, total);
```

버튼 상태:

- `이전`: `page <= 1`이면 disabled
- `다음`: `page >= totalPages`이면 disabled

## 6. 상태 필터

상태 필터는 각 탭마다 별도로 둔다.

옵션:

```text
전체 상태
active
inactive
deleted
```

기본적으로 `include_deleted=false`인 경우 `deleted`는 목록에 나오지 않는다. 다만 상태 필터에서 `deleted`를 선택하면 삭제 상태 조회가 가능해야 한다.

권장 구현:

- `status === "deleted"`이면 API 요청에 `include_deleted: true`를 함께 전달한다.
- 그 외에는 `include_deleted: false`.

## 7. 테스트 계획

### 백엔드 테스트

`backend/tests/test_admin_policy.py`에 아래 내용을 추가/수정한다.

- `/admin/plans`가 `page`, `limit`, `q`, `status`를 service에 전달하는지
- service SQL에 `LIMIT`, `OFFSET`, `COUNT(*)`가 포함되는지
- `status=deleted` 조회 시 `include_deleted` 흐름이 올바른지
- `/admin/credit-plans`도 동일하게 동작하는지

### 프론트 정적 테스트

`tests/test_frontend_analysis_progress_static.py`에 아래 내용을 추가/수정한다.

- `subscriptionPage`, `subscriptionLimit`, `subscriptionTotal` 존재
- `creditPage`, `creditLimit`, `creditTotal` 존재
- `getAdminPlans({ page` 형태의 호출 존재
- `getAdminCreditPlans({ page` 형태의 호출 존재
- `개씩 보기`, `이전`, `다음` UI 문구 존재
- `pol-pagination` 또는 이에 준하는 페이지네이션 클래스 존재

## 8. 완료 기준

- `/admin/policy`가 사용자/분석 메뉴처럼 가로 폭을 넓게 사용한다.
- 구독 플랜 목록과 크레딧 플랜 목록이 각각 독립적인 페이지 상태를 가진다.
- 각 탭에서 페이지당 개수를 `5`, `10`, `20`, `50`, `100` 중 선택할 수 있다.
- 검색어 또는 상태 필터 변경 시 현재 탭의 page가 1로 초기화된다.
- 각 탭 하단에 `이전`, `다음`, `현재 표시 범위 / 전체 개수`가 표시된다.
- API는 `page`, `limit`, `q`, `status`, `include_deleted`를 처리한다.
- 목록 조회는 `sort_order ASC, created_at ASC` 정렬을 유지한다.
- 관련 테스트와 프론트 빌드가 통과한다.

권장 검증 명령:

```bash
pytest backend/tests/test_admin_policy.py -q
pytest tests/test_frontend_analysis_progress_static.py -q
cd frontend && npm run build
```
