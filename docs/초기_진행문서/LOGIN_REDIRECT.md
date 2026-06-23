# 로그인 리다이렉트 정책

GARIM 로그인은 사용자가 어떤 버튼으로 로그인 흐름에 진입했는지에 따라 성공 후 이동 위치가 달라집니다. 단, 로그인 실패 시에는 항상 홈(`/`)으로 돌아갑니다.

## 기본 원칙

- 헤더의 일반 `로그인` 버튼으로 로그인하면 성공 후 `/`로 이동합니다.
- 특정 작업을 시작하려고 로그인한 경우에는 `next` 파라미터로 목적지를 전달합니다.
- OAuth 성공 후 백엔드는 `next` 값을 검증한 뒤 내부 경로일 때만 해당 경로로 리다이렉트합니다.
- 외부 URL, `//example.com` 같은 의심 경로, 빈 값은 모두 `/`로 처리합니다.
- 관리자 계정은 일반 `next` 흐름과 무관하게 `/admin/monitoring`으로 이동합니다.

## 사용자 시나리오

| 진입 위치 | 로그인 URL | 로그인 성공 후 |
| --- | --- | --- |
| 헤더 `로그인` | `/login` | `/` |
| 헤더 `탐지` 탭 | `/login?next=%2Fupload` | `/upload` |
| 헤더 `무료 시작` | `/login?next=%2Fupload` | `/upload` |
| `/`의 `무료로 시작하기` | `/login?next=%2Fupload` | `/upload` |
| `/pricing`의 Free `무료로 시작` | `/login?next=%2Fupload` | `/upload` |
| `/pricing`의 `결제하기` | `/login?next=<encoded payment path>` | `/payment?...` |
| `/pricing`의 `충전하기` | `/login?next=<encoded payment path>` | `/payment?...` |
| OAuth 실패 | 상황과 무관 | `/` |
| 관리자 OAuth 성공 | 상황과 무관 | `/admin/monitoring` |

## 프론트엔드 흐름

프론트엔드는 작업 목적지가 있는 로그인 진입점에서 `/login?next=...`를 사용합니다.

- 헤더: `frontend/src/components/garim/GarimHeader.jsx`
- 랜딩: `frontend/src/pages/garim/Landing.jsx`
- 요금제: `frontend/src/pages/garim/Pricing.jsx`
- OAuth 시작 URL 생성: `frontend/src/utils/api.js`
- 로그인 페이지: `frontend/src/pages/garim/Login.jsx`

`Login.jsx`는 query string의 `next` 값을 읽어서 OAuth 시작 URL에 전달합니다.

```text
/login?next=/upload
→ /auth/{provider}/start?next=/upload
→ OAuth provider
→ /auth/{provider}/callback
```

## 백엔드 흐름

백엔드는 OAuth 시작 시 `next` 값을 OAuth state에 저장합니다.

- OAuth controller: `backend/controllers/oauth.py`
- OAuth state 생성/소비: `backend/services/oauth.py`

성공 시:

```text
state.next_path 검증
→ 일반 사용자: 안전한 내부 경로로 redirect
→ 관리자: /admin/monitoring 으로 redirect
```

실패 시:

```text
provider error
code/state 누락
state 만료 또는 불일치
token 교환 실패
계정 비활성
기타 예외
→ 항상 /
```

## 안전 검증

백엔드는 `safe_frontend_path()`로 `next`를 검증합니다.

허용:

```text
/
/upload
/payment?plan=pro&price=2900&credits=50
```

차단 후 `/` 처리:

```text
https://evil.example/upload
//evil.example/upload
upload
빈 값
```

## 테스트

관련 테스트는 다음 파일에 있습니다.

- `backend/tests/test_oauth.py`
  - 성공 시 안전한 `next` 경로로 이동
  - 외부 `next` 경로 차단
  - 실패 시 `next`를 무시하고 `/` 이동
- `backend/tests/test_auth_architecture.py`
  - OAuth 성공 후 기본 리다이렉트 확인
- `tests/test_frontend_analysis_progress_static.py`
  - 헤더 로고가 `/`로 이동
  - 로그인 목적지 `next`가 주요 버튼에서 유지되는지 확인

검증 명령:

```bash
pytest backend/tests/test_oauth.py backend/tests/test_auth_architecture.py
pytest tests/test_frontend_analysis_progress_static.py
cd frontend && npm run test:garim
```
