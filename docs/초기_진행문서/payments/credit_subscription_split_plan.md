# 구독 및 크레딧 분리 구현 계획

> **에이전트 작업자용:** 필수 하위 스킬: 이 계획을 작업 단위로 구현하려면 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용한다. 단계는 추적을 위해 체크박스(`- [ ]`) 문법을 사용한다.

**목표:** `plans`/`subscriptions`는 구독 전용으로 정리하고, 크레딧 상품과 실제 잔액은 `credit_plans`, `user_credit_balances`, `credit_ledger`로 분리한다.

**아키텍처:** 구독 상품 결제와 크레딧 충전 결제를 `payments.product_type` 기준으로 분기한다. 구독 결제는 `subscriptions`만 갱신하고, 크레딧 지급/차감/조회는 항상 `user_credit_balances`와 `credit_ledger`를 같은 트랜잭션에서 갱신한다. 현재는 실제 서비스 전 단계이므로 기존 `subscriptions.remaining_credits` 데이터 마이그레이션은 수행하지 않는다.

**기술 스택:** PostgreSQL 초기화 SQL, FastAPI, SQLAlchemy text query, React, Toss Payments.

---

## 현재 결합 지점

현재 프로젝트에서 문제가 될 수 있는 결합 지점은 다음과 같다.

- `docker/database/init/0_init_table_v8.sql`
  - `plans.credits`가 구독 플랜 지급 크레딧으로 쓰인다.
  - `subscriptions.remaining_credits`가 실제 사용자 잔액처럼 쓰인다.
  - `payments.subscription_id`가 있어 결제가 구독에 묶인 형태다.
- `backend/services/payment.py`
  - `create_temp_order()`가 `plans.plan_code`만 조회한다.
  - `confirm_payment()`가 결제 성공 후 `subscriptions.remaining_credits`를 갱신한다.
  - `_get_subscription_credits()`와 `_restore_free_plan_for_expired_subscriptions()`가 `remaining_credits`에 의존한다.
- `frontend/src/pages/garim/Pricing.jsx`, `frontend/src/pages/garim/Payment.jsx`
  - `credit_100`, `credit_500` 충전 상품이 UI에 있으나 백엔드에서는 아직 `plans` 기준으로 결제 검증한다.
- `backend/tests/test_payment.py`
  - 결제 성공 후 `subscriptions.remaining_credits`가 증가하는 기존 동작을 검증한다.

---

## 목표 데이터 모델

### `plans`

구독 플랜만 관리한다.

```sql
CREATE TABLE IF NOT EXISTS plans (
    plan_id uuid NOT NULL DEFAULT gen_random_uuid(),
    plan_code varchar(30) NOT NULL,
    plan_name varchar(100) NOT NULL,
    monthly_quota integer,
    result_retention_days integer NOT NULL,
    watermark_required boolean NOT NULL DEFAULT true,
    price_amount integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    file_size_limit integer,
    max_jobs integer,
    auto_delete_original_hours integer,
    metadata_retention_days integer,
    credits integer NOT NULL DEFAULT 0,
    created_at timestamp NOT NULL DEFAULT now(),
    CONSTRAINT pk_plans PRIMARY KEY (plan_id),
    CONSTRAINT uq_plans_plan_code UNIQUE (plan_code)
);
```

`plans.credits`는 구독 플랜이 매월 지급하는 기본 크레딧으로만 해석한다. 실제 잔액은 이 테이블에 저장하지 않는다.

### `credit_plans`

크레딧 충전 상품만 관리한다.

```sql
CREATE TABLE IF NOT EXISTS credit_plans (
    credit_plan_id uuid NOT NULL DEFAULT gen_random_uuid(),
    credit_plan_code varchar(40) NOT NULL,
    credit_plan_name varchar(100) NOT NULL,
    price_amount integer NOT NULL,
    base_credits integer NOT NULL,
    bonus_credits integer NOT NULL DEFAULT 0,
    expires_days integer,
    is_active boolean NOT NULL DEFAULT true,
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp,
    CONSTRAINT pk_credit_plans PRIMARY KEY (credit_plan_id),
    CONSTRAINT uq_credit_plans_code UNIQUE (credit_plan_code),
    CONSTRAINT ck_credit_plans_price_non_negative CHECK (price_amount >= 0),
    CONSTRAINT ck_credit_plans_base_positive CHECK (base_credits > 0),
    CONSTRAINT ck_credit_plans_bonus_non_negative CHECK (bonus_credits >= 0)
);
```

### `subscriptions`

구독 상태만 관리한다. `remaining_credits` 컬럼은 제거한다.

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    plan_id uuid NOT NULL REFERENCES plans(plan_id),
    status varchar(20) NOT NULL,
    started_at timestamp NOT NULL,
    ended_at timestamp,
    renew_at timestamp,
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp,
    CONSTRAINT pk_subscriptions PRIMARY KEY (subscription_id)
);
```

### `user_credit_balances`

사용자별 현재 크레딧 잔액을 관리한다.

```sql
CREATE TABLE IF NOT EXISTS user_credit_balances (
    user_id uuid NOT NULL REFERENCES users(user_id),
    balance integer NOT NULL DEFAULT 0,
    updated_at timestamp NOT NULL DEFAULT now(),
    CONSTRAINT pk_user_credit_balances PRIMARY KEY (user_id),
    CONSTRAINT ck_user_credit_balances_non_negative CHECK (balance >= 0)
);
```

### `credit_ledger`

크레딧 변동 이력을 관리한다.

```sql
CREATE TABLE IF NOT EXISTS credit_ledger (
    ledger_id uuid NOT NULL DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    amount integer NOT NULL,
    balance_after integer NOT NULL,
    entry_type varchar(30) NOT NULL,
    source_type varchar(30) NOT NULL,
    source_id uuid,
    description varchar(255),
    created_at timestamp NOT NULL DEFAULT now(),
    CONSTRAINT pk_credit_ledger PRIMARY KEY (ledger_id),
    CONSTRAINT ck_credit_ledger_amount_not_zero CHECK (amount <> 0),
    CONSTRAINT ck_credit_ledger_balance_after_non_negative CHECK (balance_after >= 0)
);
```

권장 `entry_type`:

- `grant`: 구독 플랜 기본 크레딧 지급
- `purchase`: 크레딧 충전
- `spend`: 분석 작업 사용
- `refund`: 환불 또는 복구
- `adjust`: 관리자 조정

권장 `source_type`:

- `subscription`
- `payment`
- `analysis`
- `admin`

### `payments`

결제 대상이 구독 플랜인지 크레딧 상품인지 구분한다.

```sql
ALTER TABLE payments
    ADD COLUMN product_type varchar(30),
    ADD COLUMN plan_id uuid REFERENCES plans(plan_id),
    ADD COLUMN credit_plan_id uuid REFERENCES credit_plans(credit_plan_id);
```

실서비스 전 초기화 기준으로는 기존 `payments` 정의에 위 컬럼을 직접 포함한다. `subscription_id`는 구독 결제 이력 추적용으로 nullable 유지할 수 있지만, 크레딧 결제에서는 null이어야 한다.

---

## 작업 1: DB 스키마 분리

**상태:** `docker/database/init/0_init_table_v9.sql` 및 `docs/db/Garim_DB_Design_final_clean_v9.xlsx`에 완료됨. v8 파일은 변경하지 않음.

**파일:**

- 수정: `docker/database/init/0_init_table_v8.sql`
- 확인: 프로젝트가 아직 이전 초기화 파일을 사용한다면 `docker/database/init/0_init_table.sql`, `docker/database/init/0_init_table_v4.sql` 확인

- [x] **1단계: 활성 init SQL에서 `subscriptions.remaining_credits` 제거**

`subscriptions`에서 이 컬럼을 제거한다.

```sql
remaining_credits integer,
```

이 주석도 제거한다.

```sql
COMMENT ON COLUMN subscriptions.remaining_credits IS '잔여 처리 횟수 - 잔여 처리 횟수 정보를 저장하는 컬럼';
```

- [x] **2단계: `plans` 뒤에 `credit_plans` 추가**

목표 데이터 모델 섹션의 `credit_plans` 테이블을 추가한다.

- [x] **3단계: `subscriptions` 뒤에 `user_credit_balances`와 `credit_ledger` 추가**

목표 데이터 모델 섹션의 `user_credit_balances`와 `credit_ledger` 테이블을 추가한다.

- [x] **4단계: `payments` 수정**

`payments` 테이블 정의에 다음 컬럼을 추가한다.

```sql
product_type varchar(30),
plan_id uuid REFERENCES plans(plan_id),
credit_plan_id uuid REFERENCES credit_plans(credit_plan_id),
```

다음 체크 제약조건을 추가한다.

```sql
CONSTRAINT ck_payments_product_type CHECK (
    product_type IN ('subscription', 'credit')
)
```

기존 `payments` 테이블에 제약조건 목록이 있다면, 다른 제약조건과 함께 테이블 정의 내부에 체크 제약조건을 추가한다.

- [x] **5단계: 크레딧 상품 시드 데이터 추가**

초기 크레딧 상품 시드 데이터를 추가한다.

```sql
INSERT INTO credit_plans (
    credit_plan_code,
    credit_plan_name,
    price_amount,
    base_credits,
    bonus_credits,
    expires_days,
    is_active,
    sort_order
)
VALUES
    ('credit_100', '100 크레딧', 5000, 100, 0, NULL, true, 10),
    ('credit_500', '500 크레딧', 20000, 500, 0, NULL, true, 20)
ON CONFLICT (credit_plan_code) DO UPDATE
SET
    credit_plan_name = EXCLUDED.credit_plan_name,
    price_amount = EXCLUDED.price_amount,
    base_credits = EXCLUDED.base_credits,
    bonus_credits = EXCLUDED.bonus_credits,
    expires_days = EXCLUDED.expires_days,
    is_active = EXCLUDED.is_active,
    sort_order = EXCLUDED.sort_order,
    updated_at = NOW();
```

- [x] **6단계: 스키마 참조 확인**

실행:

```powershell
rg -n "remaining_credits" docker backend frontend tests
```

예상 결과: 아직 이후 작업에서 리팩터링하지 않은 파일에만 결과가 남아 있어야 한다.

---

## 작업 2: 결제 요청 계약 변경

**파일:**

- 수정: `backend/schemas/payment.py`
- 수정: `backend/controllers/payment.py`
- 수정: `backend/services/payment.py`
- 테스트: `backend/tests/test_payment.py`

- [x] **1단계: 임시 주문 요청 스키마 변경**

`TempOrderRequest`를 수정한다.

```python
from typing import Literal
from pydantic import BaseModel


class TempOrderRequest(BaseModel):
    product_type: Literal["subscription", "credit"]
    product_code: str
    amount: int
```

`PaymentConfirmRequest`는 변경하지 않는다.

- [x] **2단계: 컨트롤러 인자 수정**

`create_temp_order()` 서비스 호출을 변경한다.

```python
result = await payment.create_temp_order(
    db=db,
    user_id=current_user["id"],
    product_type=body.product_type,
    product_code=body.product_code,
    amount=body.amount,
)
```

다음 응답 필드를 반환한다.

```python
return {
    "orderId": result["payment_id"],
    "amount": result["amount"],
    "orderName": result["order_name"],
    "productType": result["product_type"],
    "productCode": result["product_code"],
}
```

- [x] **3단계: product type 라우팅 실패 테스트 추가**

`backend/tests/test_payment.py`에 다음을 검증하는 테스트를 추가한다.

```python
async def test_service_create_temp_order_uses_plans_for_subscription():
    result = await payment_service.create_temp_order(
        db=db_mock,
        user_id="user-uuid-1",
        product_type="subscription",
        product_code="pro",
        amount=2900,
    )
    assert result["product_type"] == "subscription"
    assert result["product_code"] == "pro"
```

```python
async def test_service_create_temp_order_uses_credit_plans_for_credit():
    result = await payment_service.create_temp_order(
        db=db_mock,
        user_id="user-uuid-1",
        product_type="credit",
        product_code="credit_100",
        amount=5000,
    )
    assert result["product_type"] == "credit"
    assert result["product_code"] == "credit_100"
```

실행:

```powershell
pytest backend/tests/test_payment.py -q
```

예상 결과: `create_temp_order()`가 아직 `plan_code`를 받기 때문에 실패한다.

---

## 작업 3: 임시 주문 상품 분리

**파일:**

- 수정: `backend/services/payment.py`
- 테스트: `backend/tests/test_payment.py`

- [x] **1단계: `plan_code`를 `product_type` 및 `product_code`로 교체**

다음 시그니처를 사용한다.

```python
async def create_temp_order(
    db: Session,
    user_id: str,
    product_type: str,
    product_code: str,
    amount: int,
):
```

- [x] **2단계: 구독 상품 조회 추가**

`product_type == "subscription"`인 경우에만 `plans`를 사용한다.

```python
SELECT
    plan_id AS product_id,
    plan_code AS product_code,
    plan_name AS product_name,
    price_amount,
    is_active,
    credits
FROM plans
WHERE LOWER(plan_code) = :product_code
```

- [x] **3단계: 크레딧 상품 조회 추가**

`product_type == "credit"`인 경우에만 `credit_plans`를 사용한다.

```python
SELECT
    credit_plan_id AS product_id,
    credit_plan_code AS product_code,
    credit_plan_name AS product_name,
    price_amount,
    is_active,
    base_credits,
    bonus_credits
FROM credit_plans
WHERE LOWER(credit_plan_code) = :product_code
```

- [x] **4단계: 상품별 payment row 삽입**

구독의 경우:

```sql
INSERT INTO payments (
    user_id,
    subscription_id,
    product_type,
    plan_id,
    amount,
    status,
    pg_provider,
    order_name,
    created_at
)
VALUES (
    :user_id,
    :subscription_id,
    'subscription',
    :plan_id,
    :amount,
    'ready',
    'toss',
    :order_name,
    NOW()
)
RETURNING payment_id, amount, subscription_id, product_type
```

크레딧의 경우:

```sql
INSERT INTO payments (
    user_id,
    subscription_id,
    product_type,
    credit_plan_id,
    amount,
    status,
    pg_provider,
    order_name,
    created_at
)
VALUES (
    :user_id,
    NULL,
    'credit',
    :credit_plan_id,
    :amount,
    'ready',
    'toss',
    :order_name,
    NOW()
)
RETURNING payment_id, amount, subscription_id, product_type
```

- [x] **5단계: 임시 주문 테스트 실행**

실행:

```powershell
pytest backend/tests/test_payment.py -q
```

예상 결과: 임시 주문 라우팅 테스트는 통과한다. 결제 확인 테스트는 작업 4 전까지 실패할 수 있다.

---

## 작업 4: 결제 확인 로직 분리

**파일:**

- 수정: `backend/services/payment.py`
- 테스트: `backend/tests/test_payment.py`

- [ ] **1단계: 두 상품 조인을 모두 포함하도록 payment 조회**

기존 confirm select를 다음 정보를 포함하는 쿼리로 교체한다.

```sql
SELECT
    p.payment_id,
    p.amount,
    p.status,
    p.pg_transaction_id,
    p.paid_at,
    p.order_name,
    p.payment_method,
    p.receipt_url,
    p.approved_at,
    p.user_id,
    p.subscription_id,
    p.product_type,
    p.plan_id,
    p.credit_plan_id,
    pl.credits AS plan_credits,
    pl.plan_code,
    cp.base_credits,
    cp.bonus_credits,
    cp.credit_plan_code
FROM payments p
LEFT JOIN plans pl
    ON pl.plan_id = p.plan_id
LEFT JOIN credit_plans cp
    ON cp.credit_plan_id = p.credit_plan_id
WHERE p.payment_id = CAST(:order_id AS uuid)
```

- [ ] **2단계: Toss 검증 및 payment 업데이트는 그대로 유지**

Toss 금액/id 검증은 그대로 유지한다.

```python
_validate_toss_result(toss_result, order_id, amount)
```

결제 응답에서는 여전히 `paymentKey`, `secret`, `checkout.url`, 원본 Toss 응답을 숨겨야 한다.

- [ ] **3단계: 구독 결제 처리**

`product_type == "subscription"`인 경우 `subscriptions`만 업데이트한다.

```sql
UPDATE subscriptions
SET
    plan_id = :plan_id,
    status = 'active',
    started_at = NOW(),
    ended_at = NOW() + INTERVAL '30 days',
    renew_at = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE subscription_id = :subscription_id
```

그 다음 플랜 크레딧은 크레딧 테이블을 통해 지급한다.

```python
grant_amount = int(payment.get("plan_credits") or 0)
if grant_amount > 0:
    _add_user_credits(
        db=db,
        user_id=payment["user_id"],
        amount=grant_amount,
        entry_type="grant",
        source_type="subscription",
        source_id=payment["subscription_id"],
        description=f"구독 플랜 기본 크레딧 지급: {payment.get('plan_code')}",
    )
```

- [ ] **4단계: 크레딧 결제 처리**

`product_type == "credit"`인 경우 `subscriptions`를 업데이트하지 않는다.

```python
purchase_amount = int(payment.get("base_credits") or 0) + int(payment.get("bonus_credits") or 0)
if purchase_amount <= 0:
    raise ValueError("지급할 크레딧이 없는 크레딧 상품입니다.")

_add_user_credits(
    db=db,
    user_id=payment["user_id"],
    amount=purchase_amount,
    entry_type="purchase",
    source_type="payment",
    source_id=payment["payment_id"],
    description=f"크레딧 충전: {payment.get('credit_plan_code')}",
)
```

- [ ] **5단계: `_add_user_credits()` 헬퍼 추가**

결제 확인 흐름과 같은 트랜잭션에서 사용한다.

```python
def _add_user_credits(
    db: Session,
    user_id,
    amount: int,
    entry_type: str,
    source_type: str,
    source_id,
    description: str | None = None,
):
    row = db.execute(
        text("""
            INSERT INTO user_credit_balances (user_id, balance, updated_at)
            VALUES (:user_id, :amount, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET
                balance = user_credit_balances.balance + EXCLUDED.balance,
                updated_at = NOW()
            RETURNING balance
        """),
        {"user_id": user_id, "amount": amount},
    ).fetchone()

    balance_after = int(row._mapping["balance"])

    db.execute(
        text("""
            INSERT INTO credit_ledger (
                user_id,
                amount,
                balance_after,
                entry_type,
                source_type,
                source_id,
                description,
                created_at
            )
            VALUES (
                :user_id,
                :amount,
                :balance_after,
                :entry_type,
                :source_type,
                :source_id,
                :description,
                NOW()
            )
        """),
        {
            "user_id": user_id,
            "amount": amount,
            "balance_after": balance_after,
            "entry_type": entry_type,
            "source_type": source_type,
            "source_id": source_id,
            "description": description,
        },
    )

    return balance_after
```

- [ ] **6단계: 기존 크레딧 헬퍼 제거**

`subscriptions.remaining_credits`를 읽고 쓰는 다음 함수를 제거한다.

```python
def _get_subscription_credits(db: Session, subscription_id):
```

`_restore_free_plan_for_expired_subscriptions()`에서 `remaining_credits` 쓰기도 제거한다.

- [ ] **7단계: confirm 테스트 수정**

현재 다음을 검증하는 테스트를 변경한다.

```python
assert "remaining_credits = :remaining_credits" in subscription_update_sql
```

다음 검증으로 교체한다.

```python
assert "INSERT INTO user_credit_balances" in balance_sql
assert "INSERT INTO credit_ledger" in ledger_sql
```

실행:

```powershell
pytest backend/tests/test_payment.py -q
```

예상 결과: 통과.

---

## 작업 5: 잔액 API

**파일:**

- 수정: `backend/services/payment.py`
- 수정: `backend/controllers/payment.py`
- 수정: `backend/routes/payment.py`
- 테스트: `backend/tests/test_payment.py`

- [ ] **1단계: 현재 잔액 조회 서비스 쿼리 추가**

추가:

```python
def get_my_credit_balance(db: Session, user_id: str):
    row = db.execute(
        text("""
            SELECT COALESCE(balance, 0) AS balance
            FROM user_credit_balances
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).fetchone()

    if not row:
        return {"balance": 0}

    return {"balance": int(row._mapping["balance"] or 0)}
```

- [ ] **2단계: 컨트롤러 함수 추가**

```python
def get_my_credit_balance(current_user: dict, db: Session):
    try:
        return payment.get_my_credit_balance(
            db=db,
            user_id=current_user["id"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **3단계: 라우트 추가**

다음과 같은 라우트를 추가한다.

```python
@router.get("/credits/me")
def get_my_credit_balance(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return payment_controller.get_my_credit_balance(current_user, db)
```

`backend/routes/payment.py`의 기존 라우트 파일 명명 규칙과 의존성 스타일을 따른다.

- [ ] **4단계: payment info는 구독 전용으로 유지**

`get_my_payment_info()`는 premium/subscription 결제 정보를 계속 반환하되, `subscriptions`에서 크레딧 잔액을 추론하지 않아야 한다.

- [ ] **5단계: 백엔드 테스트 실행**

실행:

```powershell
pytest backend/tests/test_payment.py -q
```

예상 결과: 통과.

---

## 작업 6: 프론트엔드 결제 상품 분리

**파일:**

- 수정: `frontend/src/utils/api.js`
- 수정: `frontend/src/pages/garim/Pricing.jsx`
- 수정: `frontend/src/pages/garim/Payment.jsx`
- 수정: `frontend/src/pages/garim/PaymentSuccess.jsx`
- 테스트: `tests/test_frontend_analysis_progress_static.py`

- [ ] **1단계: 임시 주문 payload 수정**

프론트엔드에서 임시 주문 API를 호출하는 위치에서 다음을 보낸다.

```js
{
  product_type: productType,
  product_code: productCode,
  amount
}
```

크레딧 상품에는 `plan_code`를 보내지 않는다.

- [ ] **2단계: 상품 타입을 포함한 결제 URL 구성**

구독의 경우:

```js
const paymentPath = `/payment?productType=subscription&productCode=${plan.key}&price=${plan.payment.price}&credits=${plan.payment.credits}`;
```

크레딧의 경우:

```js
const paymentPath = `/payment?productType=credit&productCode=${credit.key}&price=${credit.payment.price}&credits=${credit.payment.credits}`;
```

- [ ] **3단계: 로그인 리다이렉트 동작 유지**

인증되지 않은 사용자가 구독 또는 크레딧 결제 버튼을 누르면 계속 다음 형식을 사용한다.

```js
`/login?next=${encodeURIComponent(paymentPath)}`;
```

- [ ] **4단계: 잔액 API에서 잔액 표시**

새 잔액 API 결과를 사용한다.

```js
const creditBalance = balanceResponse?.balance ?? 0;
```

구독/결제 정보 응답에서 크레딧 잔액을 읽지 않는다.

- [ ] **5단계: 프론트엔드 정적 테스트 수정**

`Pricing.jsx` 또는 `Payment.jsx`에 다음이 포함되어 있는지 검증하는 assertion을 추가한다.

```python
assert "productType=subscription" in pricing
assert "productType=credit" in pricing
assert "product_type" in payment
assert "product_code" in payment
```

실행:

```powershell
pytest tests/test_frontend_analysis_progress_static.py -q
```

예상 결과: 통과.

---

## 작업 7: 관리자 정책 및 가격 출처

**파일:**

- 수정: `backend/services/admin.py`
- 수정: `backend/tests/test_admin_policy.py`
- 수정: `frontend/src/hooks/usePricingPlans.js`
- 수정: `frontend/src/pages/garim/Pricing.jsx`

- [ ] **1단계: 구독 플랜은 `payment.plans` 아래에 유지**

`backend/services/admin.py`는 구독 플랜 가격과 월별/기본 크레딧을 계속 `plans`에서 읽어야 한다.

- [ ] **2단계: `payment.creditPlans` 아래에 크레딧 상품 추가**

관리자 정책 응답에는 다음이 포함되어야 한다.

```json
{
  "payment": {
    "plans": {
      "free": { "credits": 5, "price": 0 },
      "pro": { "credits": 50, "price": 2900 },
      "studio": { "credits": 500, "price": 19800 }
    },
    "creditPlans": {
      "credit_100": { "credits": 100, "bonusCredits": 0, "price": 5000 },
      "credit_500": { "credits": 500, "bonusCredits": 0, "price": 20000 }
    }
  }
}
```

- [ ] **3단계: 관리자 정책 테스트 수정**

`backend/tests/test_admin_policy.py`에 다음을 추가한다.

```python
assert response.json()["data"]["payment"]["creditPlans"]["credit_100"]["credits"] == 100
assert response.json()["data"]["payment"]["creditPlans"]["credit_500"]["price"] == 20000
```

- [ ] **4단계: 하드코딩된 크레딧 패키지를 `creditPlans` 기반으로 이동**

`usePricingPlans.js`는 둘 다 노출해야 한다.

```js
{
  (plans, creditPlans, policy, loading, error);
}
```

`Pricing.jsx`는 `creditPlans`에서 크레딧 충전 카드를 렌더링해야 한다.

- [ ] **5단계: 정책 및 프론트엔드 테스트 실행**

실행:

```powershell
pytest backend/tests/test_admin_policy.py -q
pytest tests/test_frontend_analysis_progress_static.py -q
```

예상 결과: 통과.

---

## 작업 8: 크레딧 사용 차감 지점

**파일:**

- 검사: `backend/services/analysis.py`
- 검사: `backend/controllers/analysis.py`
- 수정: 유료 분석 작업을 확정하거나 시작하는 서비스
- 테스트: 가장 가까운 analysis/payment 테스트 추가 또는 수정

- [ ] **1단계: 분석 진입 지점 찾기**

실행:

```powershell
rg -n "analysis|remaining_credits|credit|quota|upload" backend/services backend/controllers backend/routes backend/tests
```

- [ ] **2단계: `_spend_user_credits()` 헬퍼 추가**

음수 잔액을 방지하는 원자적 업데이트를 사용한다.

```python
def _spend_user_credits(
    db: Session,
    user_id,
    amount: int,
    source_id,
    description: str | None = None,
):
    row = db.execute(
        text("""
            UPDATE user_credit_balances
            SET
                balance = balance - :amount,
                updated_at = NOW()
            WHERE user_id = :user_id
              AND balance >= :amount
            RETURNING balance
        """),
        {"user_id": user_id, "amount": amount},
    ).fetchone()

    if not row:
        raise ValueError("크레딧 잔액이 부족합니다.")

    balance_after = int(row._mapping["balance"])

    db.execute(
        text("""
            INSERT INTO credit_ledger (
                user_id,
                amount,
                balance_after,
                entry_type,
                source_type,
                source_id,
                description,
                created_at
            )
            VALUES (
                :user_id,
                :amount,
                :balance_after,
                'spend',
                'analysis',
                :source_id,
                :description,
                NOW()
            )
        """),
        {
            "user_id": user_id,
            "amount": -amount,
            "balance_after": balance_after,
            "source_id": source_id,
            "description": description,
        },
    )

    return balance_after
```

- [ ] **3단계: 명확한 비즈니스 지점 한 곳에서 차감 헬퍼 호출**

분석 작업이 승인될 때 또는 실제 처리가 시작될 때 호출한다. 두 지점 모두에서 호출하면 안 된다.

첫 구현 권장안:

```python
_spend_user_credits(
    db=db,
    user_id=current_user_id,
    amount=required_credits,
    source_id=analysis_id,
    description="AI 분석 작업 크레딧 사용",
)
```

- [ ] **4단계: 잔액 부족 테스트 추가**

`user_credit_balances`에 row가 없거나 `balance`가 부족한 사용자가 유료 분석 작업을 시작할 수 없는지 검증한다.

실행:

```powershell
pytest backend/tests -q
```

예상 결과: 영향을 받는 테스트를 수정한 뒤 통과.

---

## 작업 9: 문서 업데이트

**파일:**

- 수정: `docs/payments/toss_payments.md`
- 수정: `docs/payments/toss_payments_roadmap.md`
- 수정: `docs/payments/toss_payments_data_policy.md`
- 수정: 결제 URL query 이름이 바뀌는 경우 `docs/LOGIN_REDIRECT.md`

- [x] **1단계: 기존 잔액 표현 교체**

다음 참조를 교체한다.

```text
subscriptions.remaining_credits
```

다음으로 교체한다.

```text
user_credit_balances.balance and credit_ledger
```

- [x] **2단계: 결제 상품 분리 규칙 문서화**

다음 규칙을 추가한다.

```text
product_type=subscription 결제는 subscriptions를 갱신하고 플랜 기본 크레딧을 credit_ledger에 grant로 기록한다.
product_type=credit 결제는 subscriptions를 건드리지 않고 user_credit_balances와 credit_ledger에 purchase로 기록한다.
```

- [x] **3단계: 오래된 문서가 남아 있지 않은지 확인**

실행:

```powershell
rg -n "remaining_credits|plan_code=|plan=" docs frontend backend tests
```

예상 결과: 이력 메모 또는 주석처럼 의도적인 참조만 남아 있어야 한다.

---

## 최종 검증

모든 작업 완료 후 다음 명령어를 실행한다.

```powershell
pytest backend/tests/test_payment.py -q
pytest backend/tests/test_admin_policy.py -q
pytest tests/test_frontend_analysis_progress_static.py -q
cmd /c npm run lint
cmd /c npm run build
```

예상 결과:

- 백엔드 payment 테스트 통과.
- 관리자 정책 테스트 통과.
- 프론트엔드 정적 테스트 통과.
- lint 통과.
- 프로덕션 빌드 성공.

---

## 권장 구현 순서

1. DB 스키마 분리
2. 백엔드 결제 요청 계약 변경
3. 임시 주문 상품 분리
4. 결제 확인 로직 분리
5. 잔액 API
6. 프론트엔드 결제 상품 분리
7. 관리자 정책 및 가격 출처
8. 크레딧 사용 차감 지점
9. 결제 문서 업데이트

아직 실제 서비스가 아니므로 `subscriptions.remaining_credits`에서 데이터 백필은 생략한다. 분리 이후 새로 생성되는 모든 잔액은 반드시 `credit_ledger` 항목에서 비롯되어야 한다.
