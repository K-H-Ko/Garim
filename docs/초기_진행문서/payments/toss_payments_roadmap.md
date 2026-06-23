# Toss Payments 결제 연동 구현 로드맵

본 문서는 토스페이먼츠(Toss Payments) 결제 및 구독 기능 연동을 안전하고 효율적으로 진행하기 위한 단계별 개발 로드맵입니다. AI 코딩 어시스턴트와 협업 시 아래 단계 순서대로 점진적인 구현 및 검증을 권장합니다.

---

## 1단계: 백엔드 임시 주문 생성 API 및 DB 테이블 대응

* **목표**: 결제창을 띄우기 전에 임시 주문을 등록하여 데이터 변조를 원천 차단하고 결제 데이터를 추적할 준비를 합니다.
* **주요 작업**:
  - 임시 결제 데이터를 삽입할 백엔드 컨트롤러/서비스 로직 작성 (`POST /api/payment/temp-order`)
  - 고유한 주문 ID(`orderId`) 및 요금제별 결제 금액(`amount`) 생성 및 검증
  - `payments` 테이블에 임시 결제 상태(`status = 'ready'`) 레코드 인서트
* **검증 방법**:
  - API 호출 시 `payments` 테이블에 임시 주문 데이터가 알맞은 값으로 적재되는지 확인

---

## 2단계: 프론트엔드 Toss SDK 연동 및 결제창 호출

* **목표**: 토스페이먼츠 클라이언트 SDK를 웹페이지에 연동하여 카드/간편결제 결제창을 호출하고 성공 URL로 리다이렉트되도록 합니다.
* **주요 작업**:
  - `Pricing.jsx` 및 `Payment.jsx` 등에 `@tosspayments/payment-sdk` 연동
  - 1단계 API를 호출하여 백엔드로부터 발급받은 `orderId`, `amount`, `orderName` 로드
  - Toss SDK의 `requestPayment` API를 호출하여 모달 결제창을 띄우고 테스트 결제 진행
  - 결제 완료 시 프론트엔드 성공 URL(`successUrl`)로 리다이렉트되어 `paymentKey`, `orderId`, `amount` 쿼리 파라미터가 획득되는지 확인
* **검증 방법**:
  - 샌드박스 테스트 결제창이 성공적으로 열리고, 결제 진행 후 프론트엔드 성공 페이지로 파라미터들이 유입되는지 확인

---

## 3단계: 백엔드 승인(Confirm) API 및 Toss API 연동

* **목표**: 프론트엔드 성공 리다이렉트를 수신하고, 백엔드에서 토스페이먼츠 승인 API를 호출하여 결제 승인을 최종 완료합니다.
* **주요 작업**:
  - 백엔드 승인 엔드포인트 구현 (`POST /api/payment/confirm`)
  - 인바운드로 수신한 `amount`, `orderId` 값이 1단계에서 저장해 둔 임시 주문 데이터와 일치하는지 DB 1차 검증
  - 멱등성 검사: 이미 승인 완료된 `orderId` 인지 중복 체크
    - Toss API 호출 전에 `payments` 테이블에서 해당 `orderId`의 현재 상태를 먼저 조회한다.
    - `status = 'success'`인 경우 Toss 승인 API를 다시 호출하지 않고, 기존 성공 결제 정보를 즉시 반환한다.
    - 새로고침, 네트워크 재시도, 브라우저 뒤로가기/앞으로가기, React 개발 모드 StrictMode 중복 실행으로 confirm 요청이 여러 번 들어와도 실제 Toss 승인 호출은 최초 1회만 수행되어야 한다.
    - 동일 `orderId`가 `ready` 또는 `pending` 상태일 때만 Toss 승인 API 호출을 진행한다.
  - Toss Payments 승인 API (`https://api.tosspayments.com/v1/payments/confirm`) 호출 및 결과 파싱
  - `PaymentSuccess.jsx` 프론트 보조 방어 구현
    - `useRef` 실행 가드를 두어 React `useEffect`가 개발 모드에서 두 번 실행되더라도 confirm API를 중복 호출하지 않도록 한다.
    - `sessionStorage`에 처리 완료된 `orderId` 목록을 저장하여 사용자가 성공 페이지를 새로고침했을 때 불필요한 confirm 재호출을 줄인다.
    - 단, 프론트 방어는 사용자 경험 개선용이며 실제 중복 과금 방지는 반드시 백엔드 멱등성 로직에서 보장한다.
* **검증 방법**:
  - 테스트 결제 완료 후 백엔드에서 토스페이먼츠와 통신하여 승인 완료 응답(Payment 객체)을 성공적으로 수신하는지 확인
  - 결제 성공 페이지에서 새로고침을 여러 번 수행해도 Toss 승인 API가 중복 호출되지 않고 동일 성공 결과가 반환되는지 확인
  - 동일 `orderId`로 confirm API를 2회 이상 직접 호출했을 때 두 번째 요청은 DB의 기존 성공 상태를 반환하는지 확인

---

## 4단계: DB 트랜잭션 처리 및 구독/크레딧 최종 반영

* **목표**: 결제 승인 결과를 로컬 DB에 영속화하고 유저의 구독 기간 설정 및 크레딧 충전을 한 번에 처리합니다.
* **주요 작업**:
  - 결제 승인 완료 즉시 DB 트랜잭션을 시작하여 다음 3가지 항목 통합 처리:
    1. `payments` 테이블 상태 변경 (`status = 'success'`), 승인 시각(`paid_at`), 거래 번호(`pg_transaction_id`) 업데이트
    2. `subscriptions` 테이블 상태 변경 (`status = 'active'`), 구독 기한 계산 및 설정
    3. `plans` 테이블(구독) 또는 `credit_plans` 테이블(크레딧 충전) 스펙에 따라 유저 잔액(`user_credit_balances.balance`) 충전 및 `credit_ledger` 기록
  - 트랜잭션 오류 발생 시 롤백 및 결제 망 취소 연동 처리
* **검증 방법**:
  - 전체 시나리오 결제 수행 후, 유저의 구독 등급 및 잔여 크레딧이 DB와 화면에 정상 반영되는지 최종 확인
