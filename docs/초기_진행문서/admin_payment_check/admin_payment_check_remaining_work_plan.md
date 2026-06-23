# 사용자 결제 확인 페이지 미작업/보강 작업 계획

## 목적

이 문서는 `docs/admin_payment_check/admin_payment_check_page_plan.md` 기준으로 구현 상태를 점검한 뒤, 아직 완료 기준에 정확히 맞지 않는 항목을 정리한 보강 작업 지시서다.

현재 큰 기능은 대부분 구현되어 있다. 아래 항목은 “완료 기준까지 깔끔하게 맞추기 위한 보강 작업”이다.

## 현재 구현 완료로 판단되는 범위

- `/admin/payments` 라우팅
- 관리자 메뉴의 `사용자 결제 확인` 항목
- 목록 화면 기본 레이아웃
- 요약 카드
- 검색/필터/페이지네이션 UI
- 결제 목록 조회 API
- 결제 목록 프론트 연동
- `payment_id` 마스킹 표시
- 상세 팝업 UI
- 상세 조회 API
- 상세 조회 프론트 연동
- 결제 키/PG 거래 키/영수증 URL 비노출
- 기본 환불 API
- 환불 시 `payments.status`, `refunded_at`, `balance_amount` 갱신
- 환불 시 `audit_logs` insert 로직
- 기본 백엔드 테스트
- 기본 프론트 정적 테스트

## 보강 대상 요약

남은 보강 대상은 다음 5개다.

1. 초기 목록 자동 조회 보강
2. 환불 전 확인 UI를 `window.confirm`에서 전용 모달로 변경
3. 상세 팝업에 환불/취소 가능 여부 표시
4. 환불 감사 로그 테스트 보강
5. 프론트 동작 테스트 또는 정적 검증 보강

## 절대 유지해야 할 조건

보강 작업 중에도 아래 조건은 유지한다.

- 영수증 버튼을 추가하지 않는다.
- 영수증 URL을 화면/API 응답에 노출하지 않는다.
- `pg_transaction_id`를 관리자 화면/API 응답에 노출하지 않는다.
- `last_transaction_key`를 관리자 화면/API 응답에 노출하지 않는다.
- Toss `paymentKey`, `transactionKey`를 관리자 화면/API 응답에 노출하지 않는다.
- `order_no`, `order_id` 컬럼을 추가하지 않는다.
- 신규 DB 테이블을 추가하지 않는다.
- 주문 식별자는 `payments.payment_id`를 마스킹해서 표시한다.

## Step 1. 초기 목록 자동 조회 보강

### 문제

`AdminPaymentCheck.jsx`에서 최근 7일 기간을 `dateFrom`, `dateTo`에 세팅하지만, 목록 조회 `useEffect` 의존성에 날짜 값이 포함되어 있지 않아 최초 진입 시 목록 API가 호출되지 않을 수 있다.

### 대상 파일

- `frontend/src/pages/garim/AdminPaymentCheck.jsx`

### 작업 내용

- `dateFrom`, `dateTo`가 세팅된 이후 목록 조회가 실행되도록 수정한다.
- 검색/필터/페이지 변경에 따른 조회 흐름이 중복 호출되지 않도록 정리한다.
- 권장 방식:
  - 최근 7일 기본값을 state 초기값으로 계산하거나
  - `dateFrom`, `dateTo`를 조회 effect 의존성에 포함하고 조건부 호출한다.

### 완료 기준

- `/admin/payments` 최초 진입 시 목록 API가 자동 호출된다.
- 기본 기간은 최근 7일 또는 문서에서 정한 기본 기간으로 세팅된다.
- 페이지 변경 시 목록이 다시 조회된다.
- 페이지당 개수 변경 시 1페이지로 돌아가고 목록이 다시 조회된다.
- 검색 버튼 클릭 시 현재 검색 조건으로 목록이 조회된다.
- 초기화 버튼 클릭 시 기본 조건으로 목록이 다시 조회된다.

### 테스트

- 프론트 정적 테스트에 `dateFrom`, `dateTo` 기반 초기 조회 조건을 확인하는 항목을 추가한다.
- 가능하면 컴포넌트 테스트로 최초 렌더링 후 `getAdminPayments` 호출을 검증한다.

## Step 2. 환불 확인 전용 모달 구현

### 문제

현재 환불 확인은 브라우저 기본 `window.confirm`을 사용한다. 원 계획의 Step 9는 “별도 확인 모달”을 요구한다.

### 대상 파일

- `frontend/src/pages/garim/AdminPaymentCheck.jsx`
- `frontend/src/css/garim-pages/AdminPaymentCheck.css`

### 작업 내용

- `window.confirm` 사용을 제거한다.
- 상세 팝업에서 `환불 처리` 버튼 클릭 시 환불 확인 모달을 연다.
- 확인 모달에는 다음 정보를 표시한다.
  - 주문 식별자
  - 사용자 이메일
  - 상품명
  - 환불 대상 금액
- 확인 모달 액션:
  - `환불 처리`
  - `취소`
- `환불 처리` 클릭 시 기존 `refundAdminPayment(paymentId)` 호출 흐름을 실행한다.
- 환불 성공 시:
  - 확인 모달 닫기
  - 상세 정보 다시 조회
  - 목록 다시 조회
  - 성공 메시지 표시
- 환불 실패 시:
  - 확인 모달은 유지하거나 닫지 않는다.
  - 오류 메시지를 표시한다.

### 완료 기준

- 코드에서 `window.confirm`을 사용하지 않는다.
- `환불 처리` 버튼 클릭 시 전용 확인 모달이 뜬다.
- 확인 모달에서 취소하면 환불 API를 호출하지 않는다.
- 확인 모달에서 환불 처리하면 환불 API를 호출한다.
- 환불 성공/실패 상태가 사용자에게 보인다.

### 테스트

- 프론트 정적 테스트에서 `window.confirm`이 없는지 확인한다.
- 프론트 정적 테스트에서 환불 확인 모달 관련 상태와 문구가 있는지 확인한다.
- 가능하면 컴포넌트 테스트로 `환불 처리` 클릭 후 확인 모달 표시를 검증한다.

## Step 3. 상세 팝업에 환불/취소 가능 여부 표시

### 문제

상세 팝업 표시 항목에는 `환불/취소 가능 여부`가 포함되어 있지만, 현재 UI에서는 명시적으로 표시되지 않는다.

### 대상 파일

- `frontend/src/pages/garim/AdminPaymentCheck.jsx`
- `frontend/src/css/garim-pages/AdminPaymentCheck.css`
- 필요 시 `backend/services/admin.py`

### 작업 내용

- 상세 팝업의 결제 상태 또는 결제 금액 섹션에 `환불 가능 여부` 행을 추가한다.
- 판단 기준은 우선 현재 응답 필드로 처리한다.
  - `status === "success"`이고
  - `balance_amount > 0`이면 환불 가능
  - `status`가 `refunded`, `canceled`, `failed`이면 환불 불가
- 상세 API 응답에 이미 `balance_amount`가 포함되어 있으므로 신규 컬럼은 추가하지 않는다.
- 화면 표시 예:
  - `환불 가능`
  - `환불 불가`
  - `이미 환불됨`

### 완료 기준

- 상세 팝업에서 환불 가능 여부가 명확히 보인다.
- 환불 불가능 상태에서는 `환불 처리` 버튼이 보이지 않거나 비활성화된다.
- 신규 DB 컬럼을 추가하지 않는다.

### 테스트

- 프론트 정적 테스트에서 `환불 가능 여부` 문구가 있는지 확인한다.
- 프론트 정적 테스트에서 `balance_amount` 또는 환불 가능 판단 로직이 있는지 확인한다.

## Step 4. 환불 감사 로그 테스트 보강

### 문제

서비스 로직에는 `audit_logs` insert가 있지만, 현재 백엔드 테스트는 `admin_service.refund_payment`를 monkeypatch해서 컨트롤러 호출만 확인한다. 실제 서비스 함수가 감사 로그를 남기는지는 테스트하지 않는다.

### 대상 파일

- `backend/tests/test_admin_payment_check.py`
- 필요 시 `backend/services/admin.py`

### 작업 내용

- `refund_payment` 서비스 함수가 다음 SQL을 실행하는지 테스트한다.
  - `UPDATE payments`
  - `INSERT INTO audit_logs`
- DB 연결은 실제 DB가 아니라 fake connection/session으로 대체한다.
- 테스트는 다음을 확인한다.
  - 환불 대상 결제를 조회한다.
  - 이미 환불/취소된 결제는 오류 처리한다.
  - 정상 결제는 `payments.status = 'refunded'`로 갱신한다.
  - `audit_logs.action = 'refund_payment'`로 기록한다.
  - `target_type = 'payment'`로 기록한다.

### 완료 기준

- 환불 서비스 테스트가 감사 로그 insert를 검증한다.
- 환불 불가 상태 테스트가 있다.
- 기존 컨트롤러 테스트도 계속 통과한다.

### 테스트

- `pytest backend/tests/test_admin_payment_check.py -q`

## Step 5. 프론트 동작 검증 보강

### 문제

현재 프론트 검증은 정적 문자열 검증 위주다. 원 계획 Step 10의 검색/필터/초기화/페이지네이션/상세 팝업 열기·닫기 동작 테스트가 부족하다.

### 대상 파일

- `tests/test_frontend_analysis_progress_static.py`
- 가능하면 신규 프론트 테스트 파일

### 작업 내용

우선 정적 테스트를 보강한다.

검증할 항목:

- `getAdminPayments` 호출이 있다.
- `getAdminPaymentDetail` 호출이 있다.
- `refundAdminPayment` 호출이 있다.
- `handleSearch`가 있다.
- `handleReset`이 있다.
- `setCurrentPage(1)`이 검색/초기화/limit 변경 시 사용된다.
- `pageLimit`이 API 파라미터로 전달된다.
- `product_type`, `status`, `q`, `search_key`, `date_from`, `date_to`가 API 파라미터로 전달된다.
- 상세 팝업 open/close 상태가 있다.
- `maskPaymentId`가 목록과 상세에서 사용된다.
- `receipt_url`, `pg_transaction_id`, `last_transaction_key`, `paymentKey`, `transactionKey`가 프론트 화면 코드에 없다.

가능하면 컴포넌트 테스트를 추가한다.

- 초기 렌더링 후 목록 API 호출
- 검색 버튼 클릭 시 API 재호출
- 초기화 버튼 클릭 시 조건 초기화
- 상세 버튼 클릭 시 상세 모달 표시
- 닫기 버튼 클릭 시 상세 모달 닫힘
- 환불 처리 버튼 클릭 시 환불 확인 모달 표시

### 완료 기준

- 프론트 정적 테스트가 보안 비노출 조건과 주요 동작 코드를 검증한다.
- 가능하면 컴포넌트 테스트도 추가된다.
- 기존 테스트가 모두 통과한다.

### 테스트

- `pytest tests/test_frontend_analysis_progress_static.py -q`
- 프론트 컴포넌트 테스트가 있다면 해당 테스트 실행
- `npm run build`

## Step 6. 최종 검증

### 작업 내용

보강 작업 후 아래 검증을 실행한다.

- `pytest tests/test_frontend_analysis_progress_static.py -q`
- `pytest backend/tests/test_admin_payment_check.py -q`
- `npm run build` from `frontend`

### 완료 기준

- 모든 테스트가 통과한다.
- 프론트 빌드가 성공한다.
- 관리자 결제 확인 화면에 영수증 관련 버튼이 없다.
- 관리자 결제 확인 화면에 결제 키 관련 정보가 없다.
- 관리자 API 응답에 결제 키 관련 정보가 없다.
- 관리자 API 응답에 `receipt_url`이 없다.
- 환불 처리 시 감사 로그가 기록된다.
- `payment_id`는 화면에서 마스킹되어 표시된다.

## 권장 작업 순서

1. Step 1 초기 목록 자동 조회 보강
2. Step 3 환불 가능 여부 표시
3. Step 2 환불 확인 전용 모달 구현
4. Step 4 환불 감사 로그 테스트 보강
5. Step 5 프론트 동작 검증 보강
6. Step 6 최종 검증

Step 1과 Step 3은 작은 수정으로 사용자 체감 품질을 바로 올릴 수 있으므로 먼저 진행한다. Step 2는 UI 상태가 늘어나므로 그 다음에 진행한다. Step 4와 Step 5는 구현 후 회귀 방지용으로 보강한다.
