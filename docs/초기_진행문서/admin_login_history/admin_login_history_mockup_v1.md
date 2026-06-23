# GARIM 관리자 로그인 히스토리 메뉴 Mockup / Codex 작업 지시서

## 0. 목적

관리자 페이지에 **사용자 로그인 히스토리** 메뉴를 추가한다.  
기존 관리자 페이지의 사이드 메뉴, 카드형 지표, 필터/테이블 UI 패턴을 유지하면서 `user_login_histories` 테이블 기반의 로그인 이력 조회 화면을 구현한다.

---

## 1. 현재 관리자 메뉴 구조 기준

현재 `frontend/src/data/garim/pages.js`에는 다음 관리자 라우트가 등록되어 있다.

| 현재 메뉴 | path | component | current |
|---|---|---|---|
| 사용자 모니터링 | `/admin/monitoring` | `AdminMonitoring` | `monitoring` |
| 처리 큐 | `/admin/queue` | `AdminQueue` | `queue` |
| 컴플라이언스 | `/admin/compliance` | `AdminCompliance` | `compliance` |
| 사용자 | `/admin/users` | `AdminUsers` | `users` |
| 분석 | `/admin/analytics` | `AdminAnalytics` | `analytics` |
| 정책 및 상품 관리 | `/admin/policy` | `AdminPolicy` | `policy` |

현재 admin 페이지들은 공통적으로 다음 구조를 사용한다.

```jsx
<GarimPage screenLabel="...">
  <div className="adm-shell">
    <aside className="adm-side">
      <div className="sec">운영</div>
      <Link to="/admin/monitoring">사용자 모니터링</Link>
      <Link to="/admin/queue">처리 큐</Link>
      <Link to="/admin/compliance">컴플라이언스</Link>

      <div className="sec">시스템</div>
      <Link to="/admin/users">사용자</Link>
      <Link to="/admin/analytics">분석</Link>
      <Link to="/admin/policy">정책 및 상품 관리</Link>
    </aside>

    <main className="adm-main">
      ...content
    </main>
  </div>
</GarimPage>
```

---

## 2. 추가할 메뉴 위치

로그인 히스토리는 사용자 계정/보안 이력에 가까우므로 **시스템** 섹션의 `사용자` 바로 아래에 추가한다.

### 변경 후 관리자 사이드 메뉴

```text
운영
- 사용자 모니터링
- 처리 큐
- 컴플라이언스

시스템
- 사용자
- 로그인 히스토리      ← 추가
- 분석
- 정책 및 상품 관리
```

### 신규 라우트

| 항목 | 값 |
|---|---|
| path | `/admin/login-history` |
| component | `AdminLoginHistory` |
| file | `31-admin-login-history.html` |
| layout | `admin` |
| current | `login-history` |
| title | `로그인 히스토리 · Garim Admin` |

---

## 3. 화면 Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ GARIM ADMIN HEADER                                                           │
├───────────────┬──────────────────────────────────────────────────────────────┤
│               │ 로그인 히스토리                                  [CSV Export] │
│ 운영          │ 사용자 로그인 성공/실패 이력 · 최근 30일                     │
│  사용자 모니터링│                                                              │
│  처리 큐       │ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │
│  컴플라이언스   │ │ 전체 시도   │ │ 성공       │ │ 실패       │ │ 차단/삭제  │ │
│               │ │ 1,284      │ │ 1,193      │ │ 74         │ │ 17         │ │
│ 시스템         │ │ 최근 30일   │ │ 92.9%      │ │ 5.8%       │ │ 1.3%       │ │
│  사용자        │ └────────────┘ └────────────┘ └────────────┘ └────────────┘ │
│  로그인 히스토리│                                                              │
│  분석          │ ┌──────────────────────────────────────────────────────────┐ │
│  정책 및 상품   │ │ 검색어 [email/user_id/provider_email]  기간 [오늘 ▼]       │ │
│               │ │ 결과 [전체 ▼] 제공자 [전체 ▼] IP [선택]  [조회] [초기화]  │ │
│               │ └──────────────────────────────────────────────────────────┘ │
│               │                                                              │
│               │ ┌──────────────────────────────────────────────────────────┐ │
│               │ │ 로그인 이력                                             │ │
│               │ ├─────────────┬─────────────┬────────┬────────┬──────────┤ │
│               │ │ 시각        │ 사용자       │ 제공자  │ 결과   │ IP       │ │
│               │ ├─────────────┼─────────────┼────────┼────────┼──────────┤ │
│               │ │ 2026-06-09  │ user@...     │ kakao  │ 성공   │ 211...   │ │
│               │ │ 2026-06-09  │ guest@...    │ google │ 실패   │ 110...   │ │
│               │ │ 2026-06-08  │ deleted@...  │ naver  │ 차단   │ 203...   │ │
│               │ └─────────────┴─────────────┴────────┴────────┴──────────┘ │
│               │ 1–20 / 1,284                                      이전 다음 │
│               │                                                              │
│               │ ┌──────────────────────────────────────────────────────────┐ │
│               │ │ 선택된 로그인 상세                                      │ │
│               │ │ 사용자, OAuth 계정, provider_user_id, user_agent, 실패사유 │ │
│               │ └──────────────────────────────────────────────────────────┘ │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 4. 화면 구성 상세

### 4.1 Header

```text
제목: 로그인 히스토리
설명: 사용자 로그인 성공/실패 이력 · 최근 30일
액션: CSV Export
```

### 4.2 Metric Cards

기존 `AdminUsers`, `AdminAnalytics`의 `.metric-row`, `.metric` 패턴을 재사용한다.

| 카드 | 값 예시 | 설명 |
|---|---:|---|
| 전체 시도 | 1,284 | 기간 내 전체 로그인 시도 수 |
| 성공 | 1,193 | `login_result = success` |
| 실패 | 74 | `login_result = failed` 또는 `error` |
| 차단/삭제 | 17 | `login_result = blocked` 또는 `deleted` |

### 4.3 Filter Bar

필터는 상단 툴바 한 줄 또는 두 줄로 구성한다.

| 필터 | UI | Query Param 예시 |
|---|---|---|
| 검색어 | input | `q=` |
| 기간 시작 | date | `date_from=` |
| 기간 종료 | date | `date_to=` |
| 로그인 결과 | select | `result=success/failed/blocked/deleted/error` |
| 제공자 | select | `provider=kakao/google/naver/facebook/x` |
| IP | input | `ip_address=` |
| 페이지 크기 | select | `limit=20` |

검색어는 다음 필드를 대상으로 한다.

```text
users.email
users.display_name
user_login_histories.provider_email
user_login_histories.provider_user_id
user_login_histories.ip_address
```

### 4.4 Main Table

| 컬럼 | 표시값 | 비고 |
|---|---|---|
| 로그인 시각 | `logged_in_at` | `YYYY-MM-DD HH:mm:ss` |
| 사용자 | `email`, `display_name`, `user_id` | user_id는 mono small |
| 제공자 | `provider` | kakao/google/naver 등 chip |
| 결과 | `login_result` | success/failed/blocked/deleted/error chip |
| 실패 사유 | `failure_reason` | 없으면 `—` |
| IP | `ip_address` | 개인정보 보호상 일부 마스킹 고려 |
| 브라우저/기기 | `user_agent` | 너무 길면 ellipsis |
| 작업 | `상세` 버튼 | 우측 상세 패널 갱신 |

### 4.5 Detail Panel

테이블에서 `상세` 클릭 시 우측 또는 하단 패널에 표시한다. 기존 `AdminMonitoring`의 선택 사용자 상세 패널 패턴을 참고한다.

```text
선택된 로그인 상세
- 로그인 이력 ID
- 사용자 ID
- 이메일 / 표시명
- 계정 상태
- OAuth 계정 ID
- provider
- provider_user_id
- provider_email
- login_result
- failure_reason
- ip_address
- user_agent
- logged_in_at
```

---

## 5. 상태 Chip 기준

```js
const RESULT_CHIP = {
  success: "mui-chip--soft-success",
  failed: "mui-chip--soft-warning",
  blocked: "mui-chip--soft-error",
  deleted: "mui-chip--soft-error",
  error: "mui-chip--soft-error",
};

const RESULT_LABEL = {
  success: "성공",
  failed: "실패",
  blocked: "차단",
  deleted: "삭제 계정",
  error: "오류",
};
```

---

## 6. 프론트엔드 파일 추가/수정 범위

### 6.1 신규 파일

```text
frontend/src/pages/garim/AdminLoginHistory.jsx
frontend/src/css/garim-pages/AdminLoginHistory.css
```

### 6.2 수정 파일

```text
frontend/src/data/garim/pages.js
frontend/src/components/garim/GarimHeader.jsx 또는 각 Admin 페이지 사이드 메뉴 중복 구간
frontend/src/utils/api.js
```

현재 admin 사이드 메뉴가 각 Admin 페이지에 반복되어 있으므로, 가능한 경우 다음 공통 컴포넌트로 분리하는 것이 좋다.

```text
frontend/src/components/garim/AdminSidebar.jsx
```

단, Codex 작업 범위를 줄이려면 우선 기존 방식처럼 `AdminLoginHistory.jsx` 안에 동일한 사이드바 마크업을 넣고, 기존 Admin 페이지 사이드 메뉴에는 `로그인 히스토리` 링크만 추가한다.

---

## 7. `pages.js` 추가 예시

```js
import AdminLoginHistory from "../../pages/garim/AdminLoginHistory";

export const garimPages = [
  // ...existing routes
  {
    path: "/admin/login-history",
    name: "AdminLoginHistory",
    component: AdminLoginHistory,
    file: "31-admin-login-history.html",
    layout: "admin",
    current: "login-history",
  },
];
```

---

## 8. API 함수 Mockup

`frontend/src/utils/api.js`에 다음 함수를 추가한다.

```js
export async function getAdminLoginHistories({
  page = 1,
  limit = 20,
  q,
  result,
  provider,
  ipAddress,
  dateFrom,
  dateTo,
} = {}) {
  const params = new URLSearchParams();
  params.set("page", page);
  params.set("limit", limit);
  if (q) params.set("q", q);
  if (result) params.set("result", result);
  if (provider) params.set("provider", provider);
  if (ipAddress) params.set("ip_address", ipAddress);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);

  return apiFetch(`/admin/login-history?${params.toString()}`);
}
```

---

## 9. 백엔드 API 필요 스펙

### 9.1 목록 조회

```http
GET /admin/login-history?page=1&limit=20&q=&result=&provider=&ip_address=&date_from=&date_to=
```

### 9.2 응답 예시

```json
{
  "items": [
    {
      "login_history_id": "uuid",
      "user_id": "uuid",
      "email": "user@example.com",
      "display_name": "홍길동",
      "user_status": "active",
      "oauth_account_id": "uuid",
      "provider": "kakao",
      "provider_user_id": "123456789",
      "provider_email": "user@example.com",
      "login_result": "success",
      "failure_reason": null,
      "ip_address": "211.123.45.67",
      "user_agent": "Chrome 124 / Windows",
      "logged_in_at": "2026-06-09T13:40:10"
    }
  ],
  "total": 1284,
  "page": 1,
  "limit": 20,
  "metrics": {
    "total": 1284,
    "success": 1193,
    "failed": 74,
    "blocked": 17,
    "deleted": 0,
    "error": 0
  }
}
```

---

## 10. DB 조회 기준

기준 테이블은 v10에서 추가한 `user_login_histories`다.

### 목록 조회 SQL 예시

```sql
SELECT
    ulh.login_history_id,
    ulh.user_id,
    u.email,
    u.display_name,
    u.status AS user_status,
    ulh.oauth_account_id,
    ulh.provider,
    ulh.provider_user_id,
    ulh.provider_email,
    ulh.login_result,
    ulh.failure_reason,
    ulh.ip_address,
    ulh.user_agent,
    ulh.logged_in_at
FROM user_login_histories ulh
LEFT JOIN users u ON u.user_id = ulh.user_id
WHERE 1 = 1
ORDER BY ulh.logged_in_at DESC
LIMIT :limit OFFSET :offset;
```

---

## 11. `AdminLoginHistory.jsx` UI Skeleton

```jsx
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import GarimPage from "../../components/garim/GarimPage";
import { getAdminLoginHistories } from "../../utils/api";
import "../../css/garim-pages/AdminLoginHistory.css";

const RESULT_CHIP = {
  success: "mui-chip--soft-success",
  failed: "mui-chip--soft-warning",
  blocked: "mui-chip--soft-error",
  deleted: "mui-chip--soft-error",
  error: "mui-chip--soft-error",
};

const RESULT_LABEL = {
  success: "성공",
  failed: "실패",
  blocked: "차단",
  deleted: "삭제 계정",
  error: "오류",
};

export default function AdminLoginHistory() {
  useDocumentTitle("로그인 히스토리 · Garim Admin");

  const [items, setItems] = useState([]);
  const [metrics, setMetrics] = useState({ total: 0, success: 0, failed: 0, blocked: 0 });
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [q, setQ] = useState("");
  const [result, setResult] = useState("");
  const [provider, setProvider] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError(null);

    getAdminLoginHistories({ page, limit, q, result, provider })
      .then((res) => {
        if (ignore) return;
        const data = res.data ?? res;
        setItems(data.items ?? []);
        setMetrics(data.metrics ?? { total: 0, success: 0, failed: 0, blocked: 0 });
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [page, limit, result, provider]);

  return (
    <GarimPage screenLabel="Admin Login History">
      <div className="adm-shell adm-login-history">
        <aside className="adm-side">
          <div className="sec">운영</div>
          <Link to="/admin/monitoring"><span className="material-icons">monitor_heart</span>사용자 모니터링</Link>
          <Link to="/admin/queue"><span className="material-icons">queue</span>처리 큐</Link>
          <Link to="/admin/compliance"><span className="material-icons">verified_user</span>컴플라이언스</Link>
          <div className="sec">시스템</div>
          <Link to="/admin/users"><span className="material-icons">people</span>사용자</Link>
          <Link className="active" to="/admin/login-history"><span className="material-icons">login</span>로그인 히스토리</Link>
          <Link to="/admin/analytics"><span className="material-icons">analytics</span>분석</Link>
          <Link to="/admin/policy"><span className="material-icons">tune</span>정책 및 상품 관리</Link>
        </aside>

        <main className="adm-main">
          <div className="adm-head">
            <div>
              <h1>로그인 히스토리</h1>
              <div className="meta">사용자 로그인 성공/실패 이력 · 최근 30일</div>
            </div>
            <button className="mui-btn mui-btn--outlined">file_download CSV Export</button>
          </div>

          <div className="metric-row">
            <div className="metric"><div className="lbl">전체 시도</div><div className="num">{metrics.total}</div><div className="delta">최근 30일</div></div>
            <div className="metric"><div className="lbl">성공</div><div className="num">{metrics.success}</div><div className="delta">성공 로그인</div></div>
            <div className="metric warn"><div className="lbl">실패</div><div className="num">{metrics.failed}</div><div className="delta">실패/오류</div></div>
            <div className="metric danger"><div className="lbl">차단/삭제</div><div className="num">{metrics.blocked}</div><div className="delta">차단 계정 접근</div></div>
          </div>

          {/* filter toolbar + table + detail panel 구현 */}
        </main>
      </div>
    </GarimPage>
  );
}
```

---

## 12. CSS 방향

기존 `AdminUsers.css`의 `.adm-shell`, `.adm-side`, `.adm-main`, `.adm-head`, `.metric-row`, `.metric`, `.adm-card`, `.mui-chip--soft-*`를 최대한 재사용한다.

로그인 히스토리 전용 테이블만 별도 class로 추가한다.

```css
.login-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.login-history-row {
  display: grid;
  grid-template-columns: 170px 260px 110px 110px 160px 160px 1fr 80px;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--mui-divider);
  font: 400 13px var(--font-sans);
}

.login-history-row.tbl-head {
  background: #fafafa;
  font: 500 11px var(--font-sans);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--fg-2);
}

.login-detail-panel {
  margin-top: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--mui-border);
  border-radius: 4px;
}
```

---

## 13. Codex 작업 지시 요약

아래 순서로 작업한다.

1. `AdminLoginHistory.jsx` 신규 생성
2. `AdminLoginHistory.css` 신규 생성
3. `frontend/src/data/garim/pages.js`에 `/admin/login-history` 라우트 추가
4. 기존 admin 사이드 메뉴에 `로그인 히스토리` 링크 추가
5. `frontend/src/utils/api.js`에 `getAdminLoginHistories()` 추가
6. 백엔드에 `GET /admin/login-history` API 추가
7. `user_login_histories` + `users`를 LEFT JOIN해서 목록/metrics 반환
8. pagination, 필터, loading, empty, error 상태 처리
9. 테이블 행 클릭 또는 상세 버튼 클릭 시 detail panel 표시
10. CSV Export는 우선 버튼 UI만 만들고, 구현은 후순위로 둔다

---

## 14. 우선순위

### MVP에서 반드시 구현

- 메뉴 추가
- 목록 조회
- 필터: 검색어, 결과, 제공자
- 페이지네이션
- 성공/실패/차단 지표 카드
- 상세 패널

### 후순위

- CSV Export 실제 다운로드
- IP 기반 의심 로그인 탐지
- 동일 IP 다계정 로그인 알림
- user_agent 파싱해서 브라우저/OS 분리 표시
- 로그인 실패율 차트
