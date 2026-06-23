# GARIM 관리자 로그인 히스토리 메뉴 구현 지시서 v2

## 1. 작업 목적

관리자 페이지에 **로그인 히스토리** 메뉴를 추가한다.

관리자는 사용자별 로그인 시도 이력을 조회할 수 있어야 하며, 각 이력의 `상세` 버튼을 누르면 우측 고정 패널이 아니라 **중앙 팝업 모달**로 상세 정보를 확인할 수 있어야 한다.

이번 화면 구성은 다음 방향으로 고정한다.

```text
기존 안:
- 로그인 이력 테이블 + 우측 고정 상세 패널

변경 안:
- 로그인 이력 테이블이 하단 전체 폭을 사용
- 상세 정보는 상세 버튼 클릭 시 모달 팝업으로 표시
```

---

## 2. 참고 mockup 이미지

작업 시 아래 두 이미지를 기준으로 구현한다.

### 2.1 기본 목록 화면

파일명:

```text
로그인_히스토리_대시보드_화면.png
```

구성:

- 좌측 관리자 사이드바 유지
- `로그인 히스토리` 메뉴 active 처리
- 상단 KPI 카드 4개
- 필터 영역
- 하단 전체 폭 로그인 이력 테이블
- 우측 고정 상세 패널 없음

### 2.2 상세 모달 화면

파일명:

```text
로그인_히스토리_관리_화면.png
```

구성:

- 목록 화면 위에 dim overlay
- 중앙 `로그인 상세` 모달 표시
- 선택된 row는 약한 highlight 처리
- 모달 우상단 X 닫기 버튼
- 하단 `닫기`, `확인` 버튼

---

## 3. 현재 프로젝트 기준 확인 사항

현재 admin 페이지 라우트는 `frontend/src/data/garim/pages.js`에서 관리된다.

현재 등록된 admin 라우트는 다음 형태다.

```js
{ path: "/admin/monitoring", name: "AdminMonitoring", component: AdminMonitoring, layout: "admin", current: "monitoring" }
{ path: "/admin/queue", name: "AdminQueue", component: AdminQueue, layout: "admin", current: "queue" }
{ path: "/admin/compliance", name: "AdminCompliance", component: AdminCompliance, layout: "admin", current: "compliance" }
{ path: "/admin/users", name: "AdminUsers", component: AdminUsers, layout: "admin", current: "users" }
{ path: "/admin/analytics", name: "AdminAnalytics", component: AdminAnalytics, layout: "admin", current: "analytics" }
{ path: "/admin/policy", name: "AdminPolicy", component: AdminPolicy, layout: "admin", current: "policy" }
```

`AdminUsers.jsx`는 기존 admin 화면의 레이아웃 기준으로 사용할 수 있다.

사용 중인 주요 구조:

```jsx
<GarimPage bodyClass="" screenLabel="28 Admin users">
  <div className="adm-shell">
    <aside className="adm-side">...</aside>
    <main className="adm-main">...</main>
  </div>
</GarimPage>
```

기존 class 계열:

```text
adm-shell
adm-side
adm-main
adm-head
metric-row
adm-card
```

가능하면 기존 관리자 화면과 스타일을 맞춘다.

---

## 4. 추가/수정할 프론트엔드 파일

### 4.1 신규 페이지 컴포넌트

새 파일 생성:

```text
frontend/src/pages/garim/AdminLoginHistory.jsx
```

역할:

- 로그인 히스토리 목록 화면
- 필터 상태 관리
- 목록 API 호출
- KPI metric 표시
- pagination 처리
- 상세 모달 open/close 처리

---

### 4.2 신규 CSS 파일

새 파일 생성:

```text
frontend/src/css/garim-pages/AdminLoginHistory.css
```

역할:

- 로그인 히스토리 전용 레이아웃
- full-width table section
- status/provider pill
- modal overlay
- modal table/detail layout

기존 admin 공통 클래스가 있으면 재사용하고, 필요한 부분만 추가한다.

---

### 4.3 라우트 등록

수정 파일:

```text
frontend/src/data/garim/pages.js
```

추가 import:

```js
import AdminLoginHistory from "../../pages/garim/AdminLoginHistory";
```

`garimPages` 배열에 추가:

```js
{
  path: "/admin/login-history",
  name: "AdminLoginHistory",
  component: AdminLoginHistory,
  file: "31-admin-login-history.html",
  layout: "admin",
  current: "login-history",
}
```

파일 번호는 현재 마지막 admin page 번호에 맞게 조정해도 된다.

---

### 4.4 관리자 사이드바 메뉴 추가

현재 각 admin page 안에 sidebar가 중복 구현되어 있다면, 이번 페이지에도 동일하게 sidebar를 구현한다.

기본 메뉴 구조:

```jsx
<aside className="adm-side">
  <div className="sec">운영</div>

  <a href="/admin/monitoring">
    <span className="material-icons">monitor_heart</span>
    사용자 모니터링
  </a>

  <a href="/admin/queue">
    <span className="material-icons">queue</span>
    처리 큐
  </a>

  <a href="/admin/compliance">
    <span className="material-icons">verified_user</span>
    컴플라이언스
  </a>

  <div className="sec">시스템</div>

  <a href="/admin/users">
    <span className="material-icons">people</span>
    사용자
  </a>

  <a href="/admin/login-history" className="active">
    <span className="material-icons">manage_history</span>
    로그인 히스토리
  </a>

  <a href="/admin/analytics">
    <span className="material-icons">analytics</span>
    분석
  </a>

  <a href="/admin/policy">
    <span className="material-icons">tune</span>
    정책 및 상품 관리
  </a>
</aside>
```

다른 admin 페이지에도 `로그인 히스토리` 메뉴를 노출하려면, 각 admin page sidebar에도 동일 메뉴를 추가한다.

가능하면 중복을 줄이기 위해 `AdminSidebar` 공통 컴포넌트를 만드는 것도 허용한다. 단, 작업 범위가 커질 경우 이번 작업에서는 신규 페이지에만 먼저 반영하고, 기존 페이지 공통화는 후순위로 둔다.

---

## 5. 화면 구성 상세

## 5.1 전체 레이아웃

화면은 다음 순서로 구성한다.

```text
GarimPage
└── adm-shell
    ├── adm-side
    └── adm-main
        ├── adm-head
        ├── metric-row
        ├── login-history-filter-card
        └── login-history-table-card
            └── LoginDetailModal(conditionally rendered)
```

---

## 5.2 상단 헤더

`adm-head` 구성:

```text
제목: 로그인 히스토리
설명: 사용자 로그인 성공/실패 이력 · 최근 30일
우측 버튼: CSV 내보내기
```

예시:

```jsx
<div className="adm-head">
  <div>
    <h1>로그인 히스토리</h1>
    <span className="meta">사용자 로그인 성공/실패 이력 · 최근 30일</span>
  </div>

  <button className="admin-export-btn">
    <span className="material-icons">download</span>
    CSV 내보내기
  </button>
</div>
```

---

## 5.3 KPI 카드

상단 카드 4개:

| 카드 | 값 | 보조 문구 |
|---|---:|---|
| 전체 시도 | total_attempts | 최근 30일 |
| 성공 | success_count | success_rate |
| 실패 | failed_count | failed_rate |
| 차단/삭제 | blocked_count | blocked_rate |

예시 mock data:

```js
const defaultMetrics = {
  total_attempts: 1284,
  success_count: 1193,
  failed_count: 74,
  blocked_count: 17,
  success_rate: "92.9%",
  failed_rate: "5.8%",
  blocked_rate: "1.3%",
};
```

---

## 5.4 필터 영역

필터는 KPI 아래에 한 줄 카드 형태로 배치한다.

필터 항목:

| 필터 | 타입 | query key |
|---|---|---|
| 검색어 | input | keyword |
| 기간 | select | period |
| 결과 | select | result |
| 제공자 | select | provider |
| IP | input | ip |

검색어는 다음 필드 검색에 사용한다.

```text
email
user_id
provider_email
```

결과 옵션:

```text
전체
성공
실패
차단
삭제
오류
```

provider 옵션:

```text
전체
kakao
google
naver
facebook
x
```

버튼:

```text
조회
초기화
```

---

## 5.5 로그인 이력 테이블

하단 테이블은 우측 상세 패널 없이 **전체 폭**을 사용한다.

테이블 카드 구성:

```text
제목: 로그인 이력
우측: 1-10 / 1,284, 이전/다음 버튼
```

컬럼:

| 컬럼명 | 데이터 |
|---|---|
| 로그인 시각 | logged_in_at |
| 사용자 | user_email + display_name |
| 제공자 | provider |
| 결과 | login_result |
| 실패 사유 | failure_reason |
| IP | ip_address |
| 브라우저/기기 | browser_device |
| 작업 | 상세 button |

예시 row:

```js
{
  login_history_id: "LOG-20260609-00001",
  user_id: "user01",
  user_email: "user01@example.com",
  display_name: "김가림",
  provider: "kakao",
  login_result: "success",
  failure_reason: null,
  ip_address: "211.***.12.8",
  browser_device: "Chrome · Windows",
  user_agent: "Mozilla/5.0 ... Chrome/126.0.0.0 Safari/537.36",
  oauth_account: "user01@kakao.com",
  logged_in_at: "2026-06-09 13:42:11",
}
```

---

## 5.6 제공자 badge

provider는 pill badge로 표시한다.

```text
kakao  → 보라/라벤더 계열
google → 파랑/라벤더 계열
naver  → 초록 또는 라벤더 계열
facebook → 파랑 계열
x → 회색 계열
```

class 예시:

```jsx
<span className={`provider-pill provider-${row.provider}`}>
  {row.provider}
</span>
```

---

## 5.7 결과 badge

`login_result`는 한글로 변환해서 표시한다.

| 원본 값 | 화면 표시 | 색상 |
|---|---|---|
| success | 성공 | green |
| failed | 실패 | orange |
| blocked | 차단 | red |
| deleted | 삭제 | gray/red |
| error | 오류 | red |

함수 예시:

```js
const RESULT_LABEL = {
  success: "성공",
  failed: "실패",
  blocked: "차단",
  deleted: "삭제",
  error: "오류",
};

const RESULT_CLASS = {
  success: "result-success",
  failed: "result-failed",
  blocked: "result-blocked",
  deleted: "result-deleted",
  error: "result-error",
};
```

---

## 6. 상세 모달 구성

## 6.1 동작

테이블 row의 `상세` 버튼 클릭 시:

```js
setSelectedLogin(row);
setDetailOpen(true);
```

닫기 시:

```js
setDetailOpen(false);
setSelectedLogin(null);
```

---

## 6.2 모달 레이아웃

모달은 화면 중앙에 표시한다.

구성:

```text
dim overlay
└── modal
    ├── header: 로그인 상세 + X
    ├── detail table
    └── footer: 닫기 / 확인
```

모달 제목:

```text
로그인 상세
```

상세 항목:

| 라벨 | 값 |
|---|---|
| 로그인 이력 ID | login_history_id |
| 사용자 ID | user_id |
| 사용자 이메일 | user_email |
| 사용자 이름 | display_name |
| 제공자 | provider badge |
| 결과 | result badge |
| 실패 사유 | failure_reason |
| 로그인 시각 | logged_in_at |
| IP | ip_address |
| 브라우저/기기 | browser_device |
| IP / User-Agent | ip_address + user_agent |
| OAuth 계정 | oauth_account |
| 비고 | note |

---

## 6.3 모달 예시 JSX

```jsx
function LoginDetailModal({ item, onClose }) {
  if (!item) return null;

  return (
    <div className="login-detail-overlay" role="dialog" aria-modal="true">
      <div className="login-detail-modal">
        <div className="login-detail-modal__head">
          <h2>로그인 상세</h2>
          <button type="button" className="modal-close-btn" onClick={onClose}>
            <span className="material-icons">close</span>
          </button>
        </div>

        <div className="login-detail-grid">
          <div className="detail-label">로그인 이력 ID</div>
          <div className="detail-value">{item.login_history_id}</div>

          <div className="detail-label">사용자 ID</div>
          <div className="detail-value">{item.user_id || "-"}</div>

          <div className="detail-label">사용자 이메일</div>
          <div className="detail-value">{item.user_email || "-"}</div>

          <div className="detail-label">사용자 이름</div>
          <div className="detail-value">{item.display_name || "-"}</div>

          <div className="detail-label">제공자</div>
          <div className="detail-value">
            <span className={`provider-pill provider-${item.provider}`}>
              {item.provider || "-"}
            </span>
          </div>

          <div className="detail-label">결과</div>
          <div className="detail-value">
            <span className={`result-pill ${RESULT_CLASS[item.login_result] || ""}`}>
              {RESULT_LABEL[item.login_result] || item.login_result || "-"}
            </span>
          </div>

          <div className="detail-label">실패 사유</div>
          <div className="detail-value">{item.failure_reason || "-"}</div>

          <div className="detail-label">로그인 시각</div>
          <div className="detail-value">{item.logged_in_at || "-"}</div>

          <div className="detail-label">IP</div>
          <div className="detail-value">{item.ip_address || "-"}</div>

          <div className="detail-label">브라우저/기기</div>
          <div className="detail-value">{item.browser_device || "-"}</div>

          <div className="detail-label">IP / User-Agent</div>
          <div className="detail-value detail-user-agent">
            {item.ip_address || "-"} / {item.user_agent || "-"}
          </div>

          <div className="detail-label">OAuth 계정</div>
          <div className="detail-value">{item.oauth_account || "-"}</div>

          <div className="detail-label">비고</div>
          <div className="detail-value">{item.note || "-"}</div>
        </div>

        <div className="login-detail-modal__foot">
          <button type="button" className="btn-secondary" onClick={onClose}>
            닫기
          </button>
          <button type="button" className="btn-primary" onClick={onClose}>
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## 7. API 연동

## 7.1 신규 API util 추가

수정 파일 예시:

```text
frontend/src/utils/api.js
```

추가 함수:

```js
export function getAdminLoginHistories(params = {}) {
  return api.get("/admin/login-histories", { params });
}

export function getAdminLoginHistoryDetail(loginHistoryId) {
  return api.get(`/admin/login-histories/${loginHistoryId}`);
}

export function exportAdminLoginHistoriesCsv(params = {}) {
  return api.get("/admin/login-histories/export", {
    params,
    responseType: "blob",
  });
}
```

기존 API util 패턴에 맞춰 함수명과 axios instance 명칭은 조정한다.

---

## 7.2 목록 API 응답 형식

프론트가 기대하는 응답:

```json
{
  "metrics": {
    "total_attempts": 1284,
    "success_count": 1193,
    "failed_count": 74,
    "blocked_count": 17,
    "success_rate": "92.9%",
    "failed_rate": "5.8%",
    "blocked_rate": "1.3%"
  },
  "items": [
    {
      "login_history_id": "LOG-20260609-00001",
      "user_id": "user01",
      "user_email": "user01@example.com",
      "display_name": "김가림",
      "provider": "kakao",
      "login_result": "success",
      "failure_reason": null,
      "ip_address": "211.***.12.8",
      "browser_device": "Chrome · Windows",
      "user_agent": "Mozilla/5.0 ... Chrome/126.0.0.0 Safari/537.36",
      "oauth_account": "user01@kakao.com",
      "logged_in_at": "2026-06-09 13:42:11",
      "note": null
    }
  ],
  "page": 1,
  "limit": 10,
  "total": 1284
}
```

---

## 7.3 query params

목록 API query params:

| param | 설명 |
|---|---|
| page | 페이지 번호 |
| limit | 페이지당 개수 |
| keyword | email/user_id/provider_email 검색 |
| period | 최근 7일/30일/90일/custom |
| result | success/failed/blocked/deleted/error |
| provider | kakao/google/naver/facebook/x |
| ip | IP 검색 |
| start_date | custom 기간 시작일 |
| end_date | custom 기간 종료일 |

---

## 8. 백엔드 작업 범위

기존 v10 DB에 `user_login_histories` 테이블이 추가되어 있어야 한다.

백엔드에 추가할 엔드포인트:

```text
GET /admin/login-histories
GET /admin/login-histories/{login_history_id}
GET /admin/login-histories/export
```

가능하면 기존 `backend/routes/admin.py`, `backend/controllers/admin.py`, `backend/services/admin.py` 패턴에 맞춰 추가한다.

---

## 8.1 목록 조회 SQL 개념

```sql
SELECT
    ulh.login_history_id,
    ulh.user_id,
    u.email AS user_email,
    u.display_name,
    ulh.provider,
    ulh.login_result,
    ulh.failure_reason,
    ulh.ip_address,
    ulh.user_agent,
    ulh.logged_in_at,
    oa.provider_email AS oauth_account
FROM user_login_histories ulh
LEFT JOIN users u ON u.user_id = ulh.user_id
LEFT JOIN oauth_accounts oa ON oa.oauth_account_id = ulh.oauth_account_id
WHERE 1=1
ORDER BY ulh.logged_in_at DESC
LIMIT :limit OFFSET :offset;
```

---

## 8.2 필터 조건

검색어:

```sql
AND (
  u.email ILIKE :keyword
  OR CAST(ulh.user_id AS TEXT) ILIKE :keyword
  OR ulh.provider_email ILIKE :keyword
)
```

결과:

```sql
AND ulh.login_result = :result
```

제공자:

```sql
AND ulh.provider = :provider
```

IP:

```sql
AND ulh.ip_address ILIKE :ip
```

기간:

```sql
AND ulh.logged_in_at >= :start_date
AND ulh.logged_in_at < :end_date
```

---

## 8.3 metrics 계산

목록 API에서 같은 필터 기간 기준으로 metric도 함께 내려준다.

```sql
COUNT(*) AS total_attempts
COUNT(*) FILTER (WHERE login_result = 'success') AS success_count
COUNT(*) FILTER (WHERE login_result = 'failed') AS failed_count
COUNT(*) FILTER (WHERE login_result IN ('blocked', 'deleted')) AS blocked_count
```

비율은 백엔드 또는 프론트에서 계산 가능하다.

---

## 9. CSV 내보내기

`CSV 내보내기` 버튼 클릭 시 현재 필터 값을 그대로 사용해 다운로드한다.

파일명 예시:

```text
garim_login_histories_20260609.csv
```

CSV 컬럼:

```text
로그인 이력 ID
사용자 ID
사용자 이메일
사용자 이름
제공자
결과
실패 사유
로그인 시각
IP
브라우저/기기
User-Agent
OAuth 계정
```

---

## 10. 프론트 구현 시 mock data

백엔드 API가 아직 준비되지 않았거나 연결이 실패할 경우, 개발 중에는 아래 mock data로 화면을 먼저 구성한다.

```js
const MOCK_LOGIN_HISTORIES = [
  {
    login_history_id: "LOG-20260609-00001",
    user_id: "user01",
    user_email: "user01@example.com",
    display_name: "김가림",
    provider: "kakao",
    login_result: "success",
    failure_reason: null,
    ip_address: "211.***.12.8",
    browser_device: "Chrome · Windows",
    user_agent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    oauth_account: "user01@kakao.com",
    logged_in_at: "2026-06-09 13:42:11",
    note: null,
  },
  {
    login_history_id: "LOG-20260609-00002",
    user_id: null,
    user_email: "guest@google.com",
    display_name: "게스트",
    provider: "google",
    login_result: "failed",
    failure_reason: "oauth_error",
    ip_address: "110.***.45.2",
    browser_device: "Safari · iOS",
    user_agent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    oauth_account: "guest@google.com",
    logged_in_at: "2026-06-09 13:35:22",
    note: null,
  },
  {
    login_history_id: "LOG-20260608-00003",
    user_id: "deleted-user",
    user_email: "deleted@naver.com",
    display_name: "삭제된 계정",
    provider: "naver",
    login_result: "blocked",
    failure_reason: "deleted_user",
    ip_address: "203.***.3.41",
    browser_device: "Edge · Windows",
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/126.0.0.0",
    oauth_account: "deleted@naver.com",
    logged_in_at: "2026-06-08 22:17:03",
    note: null,
  },
];
```

---

## 11. CSS 구현 방향

### 11.1 테이블이 하단 전체 폭을 채우도록 구성

```css
.login-history-table-card {
  width: 100%;
  margin-top: 16px;
}

.login-history-table-wrap {
  width: 100%;
  overflow-x: auto;
}

.login-history-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
```

우측 상세 패널을 위한 grid/flex column은 만들지 않는다.

잘못된 레이아웃 예:

```css
/* 금지: 우측 고정 상세 패널용 2-column 구조 */
.login-history-content {
  display: grid;
  grid-template-columns: 1fr 320px;
}
```

올바른 레이아웃 예:

```css
.login-history-content {
  display: block;
}
```

---

### 11.2 모달 CSS

```css
.login-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 23, 42, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.login-detail-modal {
  width: min(560px, 100%);
  max-height: calc(100vh - 64px);
  overflow: auto;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.28);
}

.login-detail-modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 12px;
}

.login-detail-grid {
  margin: 8px 24px 20px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  overflow: hidden;
  display: grid;
  grid-template-columns: 150px 1fr;
}

.detail-label,
.detail-value {
  padding: 12px 14px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 14px;
}

.detail-label {
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
}

.detail-value {
  color: #111827;
  word-break: break-word;
}

.detail-user-agent {
  font-size: 12px;
  line-height: 1.5;
}

.login-detail-modal__foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 24px 24px;
}
```

---

## 12. 상태 처리

필수 처리:

```text
- loading: 목록 로딩 중 skeleton 또는 "불러오는 중..."
- error: API 실패 시 오류 메시지 표시
- empty: 검색 결과 없음 표시
- modal open/close
- pagination prev/next disabled 처리
- 필터 변경 후 조회 시 page = 1 초기화
- 초기화 버튼 클릭 시 모든 필터 초기화
```

---

## 13. 개인정보/보안 표시 기준

관리자 화면이라도 IP와 User-Agent는 과도하게 노출하지 않도록 한다.

권장:

```text
목록: IP masking 표시
상세: IP masking 또는 전체 IP는 admin 권한에서만 표시
User-Agent: 상세 모달에서만 표시
CSV: 필요 시 masking 유지
```

현재 mockup은 IP를 다음처럼 masking한다.

```text
211.***.12.8
110.***.45.2
```

---

## 14. 완료 기준

아래 조건을 모두 만족하면 완료로 본다.

- `/admin/login-history` 접속 가능
- 좌측 사이드바에 `로그인 히스토리` 메뉴 표시
- 해당 메뉴 active 표시
- KPI 카드 4개 표시
- 필터 영역 표시
- 하단 테이블이 전체 폭 사용
- 우측 고정 상세 패널 없음
- `상세` 클릭 시 중앙 모달 표시
- 모달 X, 닫기, 확인으로 닫기 가능
- API 실패 시 화면이 깨지지 않음
- mock data 또는 실제 API 데이터로 화면 확인 가능
- CSV 내보내기 버튼 동작 또는 TODO 주석 처리
- 기존 admin 페이지 `/admin/users`, `/admin/analytics`, `/admin/policy` 등 라우트가 깨지지 않음

---

## 15. Codex 작업 순서

1. `AdminLoginHistory.jsx` 생성
2. `AdminLoginHistory.css` 생성
3. `pages.js`에 import와 route 추가
4. sidebar에 `로그인 히스토리` 메뉴 추가
5. mock data로 화면 우선 구현
6. 테이블 full-width 레이아웃 확인
7. 상세 모달 구현
8. `utils/api.js`에 API 함수 추가
9. 백엔드 API가 있으면 연동, 없으면 mock fallback 유지
10. CSV 버튼은 API 연동 또는 TODO 처리
11. 화면 확인 후 기존 admin 메뉴 영향 없는지 점검

---

## 16. Codex에게 줄 핵심 지시 요약

```text
관리자 페이지에 /admin/login-history 경로의 로그인 히스토리 화면을 추가해줘.
기존 AdminUsers.jsx의 adm-shell/adm-side/adm-main 스타일을 참고해서 구현하고,
좌측 메뉴의 시스템 섹션에 로그인 히스토리를 추가해줘.

화면 구성은:
1) 상단 제목: 로그인 히스토리
2) KPI 카드 4개: 전체 시도, 성공, 실패, 차단/삭제
3) 필터: 검색어, 기간, 결과, 제공자, IP, 조회, 초기화
4) 하단 로그인 이력 테이블은 전체 폭을 사용
5) 우측 고정 상세 패널은 만들지 말 것
6) 각 row의 상세 버튼을 누르면 중앙 모달로 로그인 상세 정보를 보여줄 것

API는 /admin/login-histories, /admin/login-histories/{id}, /admin/login-histories/export 기준으로 util 함수를 만들고,
백엔드가 아직 없거나 실패하면 mock data로 화면이 깨지지 않게 fallback 처리해줘.
```
