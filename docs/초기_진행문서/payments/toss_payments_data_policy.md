# Toss Payments 결제 데이터 저장 정책

## 목적

Toss Payments 결제 승인 응답(Payment 객체)을 DB에 저장할 때:

- 운영에 필요한 데이터는 저장
- 보안상 불필요한 데이터는 저장하지 않음
- 프론트에 노출할 데이터와 내부 보관 데이터를 분리
- 결제 조회/환불/정산/CS 대응이 가능하도록 구성

---

# 저장 권장 데이터

아래 데이터는 결제 관리 및 운영에 필요하므로 저장한다.

```json
{
  "orderId": "...",
  "paymentKey": "...",
  "lastTransactionKey": "...",
  "orderName": "...",
  "method": "...",
  "easyPay": {
    "provider": "카카오페이"
  },
  "status": "DONE",
  "totalAmount": 2900,
  "balanceAmount": 2900,
  "currency": "KRW",
  "approvedAt": "...",
  "requestedAt": "...",
  "receipt": {
    "url": "..."
  },
  "isPartialCancelable": true
}
```

---

# paymentKey 저장 이유

paymentKey는 Toss Payments에서 결제를 식별하는 고유 키이다.

사용 목적:

- 결제 조회 API
- 결제 취소 API
- 환불 처리
- 결제 상태 재검증

예시:

```http
GET /v1/payments/{paymentKey}

POST /v1/payments/{paymentKey}/cancel
```

반드시 DB에 저장한다.

공식 문서:
https://docs.tosspayments.com/reference

---

# lastTransactionKey 저장 이유

용도:

- 거래 추적
- 고객센터 대응
- 결제 로그 분석

사용자에게 노출할 필요는 없지만 내부 보관은 가능하다.

---

# receipt.url 저장 이유

용도:

- 영수증 조회
- 결제 내역 화면 제공

프론트에는 필요 시에만 전달한다.

예:

"영수증 보기" 버튼

---

# 저장 비권장 데이터

## secret

```json
{
  "secret": "ps_xxxxxxxxx"
}
```

설명:

- 결제별 비밀 토큰
- 일반 서비스 운영에는 거의 사용하지 않음
- 프론트 전달 금지
- 로그 출력 금지

정책:

저장하지 않는 것을 권장

---

## checkout.url

```json
{
  "checkout": {
    "url": "..."
  }
}
```

설명:

결제 완료 후 재사용 가치가 거의 없음

정책:

저장하지 않음

---

## version

```json
{
  "version": "2024-06-01"
}
```

설명:

API 응답 버전 정보

정책:

저장하지 않음

---

## mId

```json
{
  "mId": "tvivarepublica"
}
```

설명:

상점 식별자(MID)

정책:

필요 시 저장 가능

필수는 아님

---

# 절대 저장/노출 주의

아래 값은 Payment 객체 응답값이 아니라 서버 환경변수이다.

```env
TOSS_SECRET_KEY=live_sk_xxxxxxxxx
```

절대:

- 프론트 전달 금지
- GitHub 업로드 금지
- 로그 출력 금지

Toss API 인증에 사용된다.

공식 문서:
https://docs.tosspayments.com/reference/using-api/api-keys

---

# 권장 payments 테이블

```sql
CREATE TABLE payments (
    payment_id UUID PRIMARY KEY,

    user_id UUID NOT NULL,
    plan_id UUID,

    order_id VARCHAR(100) NOT NULL UNIQUE,
    payment_key VARCHAR(200) NOT NULL UNIQUE,

    last_transaction_key VARCHAR(255),

    order_name VARCHAR(255),

    method VARCHAR(50),
    provider VARCHAR(50),

    status VARCHAR(30) NOT NULL,

    total_amount INTEGER NOT NULL,
    balance_amount INTEGER,

    currency VARCHAR(10) DEFAULT 'KRW',

    receipt_url TEXT,

    requested_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,

    is_partial_cancelable BOOLEAN,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 프론트 응답 정책

프론트에 내려줄 데이터:

```json
{
  "orderId": "...",
  "orderName": "Garim Pro",
  "amount": 2900,
  "method": "카카오페이",
  "status": "DONE",
  "approvedAt": "...",
  "receiptUrl": "..."
}
```

프론트에 내려주지 않을 데이터:

```json
{
  "paymentKey": "...",
  "lastTransactionKey": "...",
  "secret": "...",
  "checkout": {
    "url": "..."
  }
}
```

---

# 결제 검증 필수 정책

결제 성공 여부는 status만 확인하지 않는다.

반드시 아래 조건을 모두 검증한다.

```python
assert payment["status"] == "DONE"
assert payment["orderId"] == db_order.order_id
assert payment["totalAmount"] == db_order.amount
assert payment["orderName"] == db_order.product_name
```

검증 성공 시에만:

- Pro 플랜 활성화
- 구독 상태 변경
- 서비스 권한 부여

를 수행한다.

---

# 최종 저장 정책

저장:

- orderId
- paymentKey
- lastTransactionKey
- orderName
- method
- provider
- status
- totalAmount
- balanceAmount
- currency
- receiptUrl
- requestedAt
- approvedAt
- isPartialCancelable

저장하지 않음:

- secret
- checkout.url
- version

절대 노출 금지:

- TOSS_SECRET_KEY
- live*sk*\*
- test*sk*\*

```

```
