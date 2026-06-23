# 토스페이먼츠 연동 1단계: 백엔드 임시 주문 생성 API 구현 계획

토스페이먼츠 결제창을 띄우기 전에 클라이언트에서의 결제 금액 위변조를 막고 결제 상태를 추적하기 위해 백엔드에서 임시 주문을 등록하는 API(`POST /payment/temp-order`)를 구현하는 단계입니다.

## 사용자 검토 필요 사항

> [!IMPORTANT]
> **주문 ID(orderId) 매핑 설계**
> - `payments` 테이블에는 별도의 `order_id` 컬럼이 없으므로, 기본 키인 `payment_id` (UUID)를 문자열로 변환하여 토스페이먼츠의 `orderId`로 활용합니다.
> - 승인(Confirm) 단계에서는 토스로부터 받은 `orderId`를 UUID로 변환하여 `payments` 테이블을 조회 및 갱신합니다.

> [!NOTE]
> **보안 및 유효성 검증**
> - 관리자가 등록해 둔 `plans` 테이블의 가격 정보(`price_amount`)와 프론트엔드에서 요청한 금액(`amount`)이 정확히 일치하는지 백엔드에서 실시간 검증합니다.
> - 어드민 권한이 아닌, 현재 결제를 진행하는 일반 로그인 유저의 세션(`access_token` 쿠키)을 기반으로 `user_id`를 매핑합니다.

---

## 변경 항목 설명

### 1. 스키마/DTO 정의

#### [NEW] [payment.py](file:///d:/final_project/Human_Final_PJ/backend/schemas/payment.py) 수정 (혹은 신규 클래스 추가)
- `TempOrderRequest` Pydantic 모델 정의:
  ```python
  class TempOrderRequest(BaseModel):
      plan_code: str
      amount: int
  ```
- `TempOrderResponse` Pydantic 모델 정의:
  ```python
  class TempOrderResponse(BaseModel):
      orderId: str
      amount: int
      orderName: str
  ```

---

### 2. 백엔드 컨트롤러 및 서비스 구현

#### [MODIFY] [payment.py](file:///d:/final_project/Human_Final_PJ/backend/services/payment.py)
- `create_temp_order(user_id: str, plan_code: str, amount: int) -> dict` 함수 구현:
  - `plans` 테이블에서 `plan_code`에 해당하는 요금제 정보(활성 상태 체크) 조회
  - 요금제 가격과 요청받은 결제 요청 금액(`amount`) 일치 검증 (불일치 시 ValueError 발생)
  - `payments` 테이블에 새로운 행 삽입:
    - `payment_id`: 신규 생성된 UUID
    - `user_id`: 결제 수행 유저 ID
    - `amount`: 요청 금액
    - `status`: `'ready'` (결제창 진입 및 입금 대기 상태 의미)
    - `pg_provider`: `'toss'`
  - 생성된 임시 결제 정보를 사전 객체 형태로 반환

#### [MODIFY] [payment.py](file:///d:/final_project/Human_Final_PJ/backend/controllers/payment.py)
- `create_temp_order(body: TempOrderRequest, access_token: str | None)` 함수 추가:
  - `access_token` 쿠키를 이용해 사용자 인증 (`auth_service.authenticate_access_token` 활용)
  - `payment_service.create_temp_order`를 호출하여 임시 주문 처리
  - 성공 시 `TempOrderResponse` 형식의 JSONResponse 반환 (상태 코드 `200` 혹은 `201`)
  - 실패 시 오류 메시지와 함께 적절한 에러 코드 반환

#### [MODIFY] [payment.py](file:///d:/final_project/Human_Final_PJ/backend/routes/payment.py)
- `@router.post("/temp-order")` 라우트 등록 및 `controllers.payment.create_temp_order` 호출 처리

---

## 검증 계획

### 자동화 테스트
- 임시 주문 생성 엔드포인트에 대한 유닛 테스트 코드 작성 혹은 테스트 호출 실행:
  - 유효하지 않은 요금제 코드 전송 시 `400 Bad Request` 에러 검증
  - 요금제 가격과 결제 금액이 다를 시 `400 Bad Request` 에러 검증
  - 정상적인 요청 시 `200 OK` 응답과 함께 `orderId`, `amount`, `orderName` 반환 검증

### 수동 검증
- 테스트 결제용 사용자로 로그인 후 API 호출을 테스트하여 DB `payments` 테이블에 임시 주문행이 잘 들어갔는지 데이터베이스 확인
