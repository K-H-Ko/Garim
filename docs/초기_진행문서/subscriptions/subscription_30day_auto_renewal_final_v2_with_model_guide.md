# GARIM 30일 자동결제 구독제 전환 최종 작업 지시서 v2

## 0. 문서 목적

이 문서는 GARIM 프로젝트의 `Free / Pro / Studio` 플랜을 **30일 자동결제 구독제**로 전환하기 위한 Codex 작업 지시서다.

이 문서는 기존 `subscription_30day_auto_renewal_implementation_v1.md` 내용을 기반으로 하되, 아래 부족했던 정책을 명확히 보강한다.

```text
1. 업그레이드 시 기존 하위 플랜 잔여 기간 이월
2. 업그레이드 시 기존 하위 플랜 중복 자동결제 방지
3. 다운그레이드 시 즉시 결제하지 않고 current_period_end 이후 적용 예약
4. Free 변경은 구독 취소 예약과 동일하게 처리
5. 플랜 변경 요청/예약/적용 이력 저장
6. 예약된 다운그레이드 적용 스케줄러
7. 사용자/관리자 화면에서 플랜 변경 예정 상태 표시
8. 관련 테스트 케이스 추가
```

작업은 반드시 Step 단위로 나누어 진행한다.  
한 번에 전체를 구현하지 말고, 각 Step 완료 후 사용자 확인을 받고 다음 Step으로 넘어간다.

---

## 1. 최종 구독 정책

## 1.1 플랜 종류

```text
Free
Pro
Studio
```

권장 `plan_rank`:

| 플랜 | plan_rank |
|---|---:|
| Free | 0 |
| Pro | 10 |
| Studio | 20 |

향후 플랜이 추가되어도 `plan_rank`만 추가하면 같은 구조로 확장 가능해야 한다.

예:

| 플랜 | plan_rank |
|---|---:|
| Enterprise | 30 |

---

## 1.2 기본 구독 정책

```text
- Free는 기본 플랜이다.
- Pro / Studio는 30일 단위 유료 구독이다.
- 유료 플랜은 결제 성공 시 30일 구독 기간을 가진다.
- 사용자가 취소하지 않으면 30일마다 자동 결제된다.
- 구독 취소 시 즉시 권한을 제거하지 않는다.
- 취소한 경우에도 current_period_end까지는 기존 플랜 권한이 유지된다.
- current_period_end 이후에는 자동결제가 중단된다.
- 현재 시점에 유효한 유료 구독이 없으면 Free가 적용된다.
```

---

## 1.3 현재 플랜 계산 원칙

현재 플랜은 `users.plan_id` 같은 단일 컬럼에 고정 저장하지 않는다.

현재 플랜은 매번 아래 기준으로 계산한다.

```text
현재 적용 플랜 =
현재 시점에 유효한 active subscriptions 중
plans.plan_rank가 가장 높은 플랜
```

유효 구독 조건:

```text
status = active
current_period_start <= now()
current_period_end > now()
```

SQL 개념:

```sql
SELECT s.*, p.*
FROM subscriptions s
JOIN plans p ON p.plan_id = s.plan_id
WHERE s.user_id = :user_id
  AND s.status = 'active'
  AND s.current_period_start <= now()
  AND s.current_period_end > now()
ORDER BY p.plan_rank DESC
LIMIT 1;
```

결과가 없으면 Free 플랜을 반환한다.

---

## 1.4 업그레이드 정책

업그레이드는 현재 적용 플랜보다 `plan_rank`가 높은 유료 플랜으로 변경하는 경우다.

예:

```text
Free → Pro
Free → Studio
Pro → Studio
Pro → Enterprise
Studio → Enterprise
```

### 핵심 정책

```text
업그레이드:
즉시 결제 + 즉시 적용
```

단, 기존 하위 플랜의 남은 기간은 소멸시키지 않는다.

### 매우 중요한 규칙

```text
업그레이드 시 기존 하위 플랜의 남은 기간은 상위 플랜 종료 이후로 이월한다.
```

예:

```text
2026-06-01 Pro 30일 구독 시작
Pro 기간: 2026-06-01 ~ 2026-07-01

2026-06-10 Studio로 업그레이드
Pro 잔여 기간: 2026-06-10 ~ 2026-07-01 = 21일

Studio는 즉시 결제되어 30일 적용
Studio 기간: 2026-06-10 ~ 2026-07-10

Pro 잔여 21일은 Studio 종료 이후로 이월
Pro 최종 기간: 2026-06-01 ~ 2026-07-31
```

현재 플랜 변화:

```text
2026-06-01 ~ 2026-06-10 : Pro
2026-06-10 ~ 2026-07-10 : Studio
2026-07-10 ~ 2026-07-31 : Pro
2026-07-31 이후 : Free 또는 다른 유효 구독
```

### 업그레이드 처리 규칙

```text
1. 현재 적용 플랜과 대상 플랜의 plan_rank를 비교한다.
2. 대상 플랜의 plan_rank가 더 높으면 upgrade로 판단한다.
3. 현재 적용 중인 하위 플랜 subscription을 찾는다.
4. 하위 플랜의 잔여 기간을 계산한다.
   remaining_duration = lower_subscription.current_period_end - now()
5. 대상 상위 플랜을 즉시 결제한다.
6. 결제 성공 시 상위 플랜 subscription을 생성한다.
   upper.current_period_start = now()
   upper.current_period_end = now() + 30 days
7. 기존 하위 플랜의 current_period_end를 재계산한다.
   lower.current_period_end = upper.current_period_end + remaining_duration
8. 기존 하위 플랜의 auto_renew는 false로 변경한다.
9. 기존 하위 플랜의 cancel_at_period_end는 true로 변경한다.
10. 기존 하위 플랜의 status는 active를 유지한다.
    이유: 상위 플랜 종료 후 잔여 기간 동안 다시 적용되어야 하기 때문이다.
11. 현재 플랜 계산은 plan_rank 기준을 유지한다.
12. 업그레이드 이력은 subscription_plan_changes에 기록한다.
```

### 업그레이드 시 하위 플랜 자동결제 중지 이유

업그레이드 후 하위 플랜의 `auto_renew`를 그대로 두면 다음 달에 하위 플랜과 상위 플랜이 모두 자동결제될 수 있다.

따라서 업그레이드 시 기존 하위 플랜은 다음처럼 처리한다.

```text
auto_renew = false
cancel_at_period_end = true
status = active 유지
current_period_end = 상위 플랜 종료일 + 기존 잔여 기간
```

이렇게 하면:

```text
- 하위 플랜 잔여 기간은 보존된다.
- 상위 플랜이 우선 적용된다.
- 중복 자동결제를 방지한다.
```

---

## 1.5 다운그레이드 정책

다운그레이드는 현재 적용 플랜보다 `plan_rank`가 낮은 유료 플랜으로 변경하는 경우다.

예:

```text
Studio → Pro
Enterprise → Studio
Enterprise → Pro
```

### 핵심 정책

```text
다운그레이드:
즉시 결제하지 않고 current_period_end 이후 적용 예약
```

### 처리 규칙

```text
1. 현재 적용 플랜과 대상 플랜의 plan_rank를 비교한다.
2. 대상 플랜의 plan_rank가 낮으면 downgrade로 판단한다.
3. 현재 플랜의 current_period_end까지는 기존 상위 플랜을 유지한다.
4. 대상 하위 플랜은 즉시 결제하지 않는다.
5. subscription_plan_changes 테이블에 예약 정보를 저장한다.
6. effective_at = 현재 적용 subscription.current_period_end
7. effective_at 도래 시 대상 하위 플랜 결제/구독 생성이 진행된다.
8. 적용 성공 시 plan_change.status = applied
9. 적용 실패 시 plan_change.status = failed 또는 retry_scheduled
```

예:

```text
Studio 기간: 2026-06-01 ~ 2026-07-01
2026-06-15 Pro로 다운그레이드 요청

즉시 Pro 결제하지 않음
Studio는 2026-07-01까지 유지
subscription_plan_changes에 Pro 변경 예약 저장
2026-07-01 도래 시 Pro 결제 및 Pro subscription 생성
```

사용자 화면 안내:

```text
현재 플랜: Studio
Pro로 변경 예약됨
Studio는 2026-07-01까지 유지됩니다.
2026-07-01 이후 Pro 플랜으로 변경됩니다.
```

---

## 1.6 Free 변경 정책

Free로 변경하는 것은 구독 취소 예약과 동일하게 처리한다.

예:

```text
Pro → Free
Studio → Free
Enterprise → Free
```

처리 규칙:

```text
1. 즉시 권한을 제거하지 않는다.
2. 현재 플랜의 current_period_end까지 기존 유료 플랜을 유지한다.
3. auto_renew = false
4. cancel_at_period_end = true
5. cancelled_at = now()
6. status = active 유지
7. current_period_end 이후 유효한 다른 구독이 없으면 Free가 적용된다.
```

사용자 화면 안내:

```text
현재 플랜: Studio
구독 취소 예약됨
2026-07-01까지 Studio 플랜을 사용할 수 있습니다.
이후 Free 플랜으로 전환됩니다.
```

---

## 2. 최종 데이터 모델

## 2.1 핵심 테이블

```text
plans
subscriptions
payments
billing_keys
subscription_billing_attempts
subscription_plan_changes
```

---

## 2.2 plans

역할:

```text
Free / Pro / Studio 플랜 정의
plan_rank를 통해 현재 플랜 우선순위 판단
```

필수 컬럼:

```text
plan_id
plan_code
plan_name
plan_rank
price
active
```

---

## 2.3 subscriptions

역할:

```text
사용자별 구독 권리 저장
현재 결제 주기
자동결제 여부
취소 예약 여부
업그레이드로 인한 잔여 기간 이월 상태
```

필수/추가 컬럼:

```sql
ALTER TABLE subscriptions
ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMP,
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP,
ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS next_billing_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS billing_status VARCHAR(30),
ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT true,
ADD COLUMN IF NOT EXISTS billing_key_id UUID,
ADD COLUMN IF NOT EXISTS last_payment_id UUID,

-- 업그레이드 잔여 기간 이월 추적용
ADD COLUMN IF NOT EXISTS upgraded_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS superseded_by_subscription_id UUID,
ADD COLUMN IF NOT EXISTS carried_over_days INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS original_period_end TIMESTAMP;
```

컬럼 의미:

| 컬럼 | 의미 |
|---|---|
| `current_period_start` | 현재 구독 기간 시작 |
| `current_period_end` | 현재 구독 기간 종료 |
| `next_billing_at` | 다음 자동결제 예정일 |
| `auto_renew` | 자동결제 대상 여부 |
| `cancel_at_period_end` | 기간 종료 시 취소 예약 여부 |
| `cancelled_at` | 사용자가 취소 또는 자동결제 중지한 시각 |
| `billing_status` | 결제 상태 |
| `billing_key_id` | 자동결제 수단 |
| `last_payment_id` | 마지막 결제 |
| `upgraded_at` | 이 구독이 업그레이드로 밀려난 시각 |
| `superseded_by_subscription_id` | 이 구독보다 우선 적용되는 상위 구독 |
| `carried_over_days` | 업그레이드 시 이월된 잔여 일수 |
| `original_period_end` | 업그레이드 전 원래 종료일 |

---

## 2.4 subscription_plan_changes

역할:

```text
플랜 변경 요청, 예약, 적용, 실패, 취소 이력을 저장한다.
업그레이드/다운그레이드/Free 변경을 모두 추적한다.
```

생성 SQL 초안:

```sql
CREATE TABLE IF NOT EXISTS subscription_plan_changes (
    plan_change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(subscription_id) ON DELETE SET NULL,

    from_plan_id UUID REFERENCES plans(plan_id),
    to_plan_id UUID NOT NULL REFERENCES plans(plan_id),

    from_subscription_id UUID REFERENCES subscriptions(subscription_id) ON DELETE SET NULL,
    to_subscription_id UUID REFERENCES subscriptions(subscription_id) ON DELETE SET NULL,

    change_type VARCHAR(30) NOT NULL,
    apply_timing VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'scheduled',

    remaining_days INTEGER NOT NULL DEFAULT 0,
    remaining_seconds INTEGER NOT NULL DEFAULT 0,
    from_subscription_original_end TIMESTAMP,
    from_subscription_new_end TIMESTAMP,

    requested_at TIMESTAMP NOT NULL DEFAULT now(),
    effective_at TIMESTAMP,
    applied_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    failure_code VARCHAR(100),
    failure_message TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP
);
```

권장 상태값:

```text
change_type:
- upgrade
- downgrade
- cancel_to_free

apply_timing:
- immediate
- period_end

status:
- scheduled
- applied
- cancelled
- failed
- retry_scheduled
```

제약조건 초안:

```sql
ALTER TABLE subscription_plan_changes
ADD CONSTRAINT chk_subscription_plan_changes_type
CHECK (change_type IN ('upgrade', 'downgrade', 'cancel_to_free'));

ALTER TABLE subscription_plan_changes
ADD CONSTRAINT chk_subscription_plan_changes_timing
CHECK (apply_timing IN ('immediate', 'period_end'));

ALTER TABLE subscription_plan_changes
ADD CONSTRAINT chk_subscription_plan_changes_status
CHECK (status IN ('scheduled', 'applied', 'cancelled', 'failed', 'retry_scheduled'));
```

인덱스:

```sql
CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_user_status
ON subscription_plan_changes(user_id, status);

CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_effective
ON subscription_plan_changes(status, effective_at);

CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_subscription
ON subscription_plan_changes(subscription_id);

CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_type_status
ON subscription_plan_changes(change_type, status);
```

---

## 2.5 billing_keys

역할:

```text
Toss 자동결제용 Billing Key 저장
```

주의:

```text
billing_key는 반드시 암호화 저장한다.
프론트/관리자/API 응답에 원문 노출 금지.
로그에 원문 출력 금지.
```

---

## 2.6 subscription_billing_attempts

역할:

```text
자동결제 시도 이력 저장
결제 성공/실패/재시도 추적
다운그레이드 예약 적용 시 결제 시도도 기록
```

---

# 3. 전체 Step 구성

최종 작업은 아래 Step으로 진행한다.

```text
STEP 1. 현재 플랜/결제/구독 구조 분석
STEP 2. DB 구독 모델 확장 및 v11 SQL 작성
STEP 3. 현재 적용 플랜 계산 로직 구현
STEP 4. 플랜 변경 판단 로직 구현
STEP 5. 결제 성공 시 30일 구독 생성/연장 로직 구현
STEP 6. 업그레이드 즉시 적용 + 하위 플랜 잔여 기간 이월 구현
STEP 7. 다운그레이드 예약 구현
STEP 8. Free 변경/구독 취소 예약 구현
STEP 9. 구독 취소 철회/다운그레이드 예약 취소 구현
STEP 10. Billing Key 저장 구조 준비
STEP 11. 자동결제 스케줄러 구현
STEP 12. 예약된 다운그레이드 적용 스케줄러 구현
STEP 13. 사용자 플랜 화면 반영
STEP 14. 관리자 구독 관리 화면 반영
STEP 15. 테스트 및 리포트 작성
```
---

# 3.1 Codex 모델 사용 권장 기준

Codex 사용량 절약을 위해 모든 Step을 GPT-5.5로 진행하지 않는다.

## 기본 원칙

```text
- 정책 판단, DB 구조 변경, 결제/구독 핵심 로직은 GPT-5.5를 사용한다.
- 화면 반영, 단순 상태 변경, 테스트/리포트 작성은 GPT-5.4를 사용한다.
- GPT-5.4로 진행 중 정책 충돌, DB 무결성 문제, 결제 중복 가능성이 발견되면 즉시 GPT-5.5로 전환해 검토한다.
- 이 문서에 적힌 모델은 권장 모델이다. Codex 실행 전 사용자가 직접 모델 선택기 또는 CLI 옵션으로 모델을 변경해야 한다.
- 각 Step 시작 전에는 해당 Step의 권장 모델을 먼저 확인한 뒤 진행한다.
```

## Step별 권장 모델

| Step | 작업 내용 | 권장 모델 | 이유 |
|---|---|---|---|
| STEP 1 | 현재 플랜/결제/구독 구조 분석 | GPT-5.5 | 기존 DB/백엔드/프론트 구조를 종합 판단해야 함 |
| STEP 2 | DB 구독 모델 확장 및 v11 SQL 작성 | GPT-5.5 | 마이그레이션, 기존 데이터 보존, 결제 정책 영향이 큼 |
| STEP 3 | 현재 적용 플랜 계산 로직 구현 | GPT-5.5 | 구독 우선순위, 기간, 취소 상태 판단이 핵심 |
| STEP 4 | 플랜 변경 판단 로직 구현 | GPT-5.5 | upgrade/downgrade/cancel_to_free 분기 정책 중요 |
| STEP 5 | 결제 성공 시 30일 구독 생성/연장 로직 구현 | GPT-5.5 | 결제/구독 상태 데이터 무결성 중요 |
| STEP 6 | 업그레이드 즉시 적용 + 하위 플랜 잔여 기간 이월 구현 | GPT-5.5 | 가장 복잡하고 오류 위험이 높은 핵심 로직 |
| STEP 7 | 다운그레이드 예약 구현 | GPT-5.4 | 정책이 명확하면 구현 난도 중간 |
| STEP 8 | Free 변경/구독 취소 예약 구현 | GPT-5.4 | 정해진 컬럼 업데이트 중심 |
| STEP 9 | 구독 취소 철회/다운그레이드 예약 취소 구현 | GPT-5.4 | 비교적 단순한 상태 변경 |
| STEP 10 | Billing Key 저장 구조 준비 | GPT-5.5 | 보안, 암호화, 로그 노출 방지 중요 |
| STEP 11 | 자동결제 스케줄러 구현 | GPT-5.5 | 중복 결제 방지, 실패 처리 중요 |
| STEP 12 | 예약된 다운그레이드 적용 스케줄러 구현 | GPT-5.5 | 결제와 예약 상태 변경이 결합됨 |
| STEP 13 | 사용자 플랜 화면 반영 | GPT-5.4 | 백엔드 응답 기반 UI 표시 중심 |
| STEP 14 | 관리자 구독 관리 화면 반영 | GPT-5.4 | 조회, 필터, 상태 표시 중심 |
| STEP 15 | 테스트 및 리포트 작성 | GPT-5.4 | 케이스 반복 검증과 문서화 중심 |

## Codex 실행 예시

CLI에서 모델을 직접 지정할 수 있는 환경이라면 Step별로 아래처럼 실행한다.

```bash
# GPT-5.5 권장 Step
codex -m gpt-5.5

# GPT-5.4 권장 Step
codex -m gpt-5.4
```

IDE 또는 웹 UI를 사용하는 경우에는 Step 시작 전에 모델 선택기에서 권장 모델로 변경한 뒤 진행한다.

---

# STEP 1. 현재 플랜/결제/구독 구조 분석

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

기존 코드와 DB 구조를 분석한다.  
아직 파일 수정은 하지 않는다.

## Codex 지시문

<!-- GEMINI.md 규칙을 먼저 확인해줘. -->

```text
이번 작업은 GARIM 프로젝트의 Free/Pro/Studio 플랜을 30일 자동결제 구독제로 전환하는 작업이야.

먼저 코드 수정 없이 현재 구조를 분석해줘.

확인할 것:
1. DB SQL 파일에서 plans, subscriptions, payments 관련 테이블 구조 확인
2. plans에 plan_rank 또는 플랜 우선순위 컬럼이 있는지 확인
3. subscriptions에 30일 구독제 관련 컬럼이 있는지 확인
4. subscriptions에 업그레이드 잔여 기간 이월 추적 컬럼이 있는지 확인
5. subscription_plan_changes 같은 플랜 변경 이력 테이블이 있는지 확인
6. payments 테이블이 결제 성공 이력을 저장하기에 충분한지 확인
7. billing key 관련 테이블/코드가 있는지 확인
8. 백엔드에서 플랜/결제/구독 관련 routes/controllers/services/models 위치 확인
9. 프론트에서 플랜 구독/결제/마이페이지 관련 화면 위치 확인
10. 현재 적용 플랜을 어디서 판단하고 있는지 확인
11. Toss 결제 관련 코드가 어디까지 구현되어 있는지 확인

아직 파일 수정은 하지 말고, Implementation Plan과 수정 후보 파일 목록만 작성해줘.
```

## 산출물

```text
- 현재 구조 분석 결과
- 수정이 필요한 파일 목록
- DB 변경 필요 여부
- 백엔드 변경 필요 여부
- 프론트 변경 필요 여부
- 자동결제 구현 가능 범위
- 위험 요소
```

---

# STEP 2. DB 구독 모델 확장 및 v11 SQL 작성

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

30일 구독제, 플랜 변경, 업그레이드 잔여 기간 이월, 자동결제에 필요한 DB 변경 SQL을 작성한다.

## 필수 반영

```text
1. plans.plan_rank 추가
2. subscriptions 30일 구독 컬럼 추가
3. subscriptions 업그레이드 잔여 기간 이월 추적 컬럼 추가
4. billing_keys 테이블 추가 또는 보강
5. subscription_billing_attempts 테이블 추가 또는 보강
6. subscription_plan_changes 테이블 추가
7. 관련 인덱스 추가
8. 기존 insert 데이터 삭제 금지
```

## Codex 지시문

```text
STEP 2를 진행해줘.

목표는 30일 구독제와 플랜 변경 정책을 위한 DB 변경 SQL 작성이야.

주의:
1. 기존 0_init_table_v10.sql 구조를 먼저 확인해줘.
2. 기존 테이블/컬럼과 중복되는 컬럼은 다시 만들지 말고 IF NOT EXISTS 또는 안전한 방식으로 작성해줘.
3. 기존 데이터 insert 쿼리는 삭제하지 마.
4. 기존 init_table 전체를 수정해야 한다면 v11 파일로 복사해서 수정해줘.
5. 마이그레이션용 추가 SQL도 별도로 작성해줘.
6. subscription_plan_changes 테이블을 반드시 추가해줘.
7. 업그레이드 잔여 기간 이월 추적 컬럼을 subscriptions 또는 subscription_plan_changes에 반영해줘.
8. billing_key는 민감 정보이므로 주석에 암호화 저장 필요성을 명시해줘.
9. 작업 후 변경 파일과 실행 순서를 정리해줘.
```

## 권장 산출물

```text
0_init_table_v11.sql
```

---

# STEP 3. 현재 적용 플랜 계산 로직 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

사용자의 현재 적용 플랜을 계산하는 공통 서비스 함수를 구현한다.

## 구현 규칙

```text
1. 유효한 active subscriptions 중 current_period_start <= now() < current_period_end 인 구독만 본다.
2. 여러 구독이 유효하면 plans.plan_rank가 가장 높은 플랜을 선택한다.
3. cancel_at_period_end=true여도 current_period_end 전이면 유효하다.
4. auto_renew=false여도 current_period_end 전이면 유효하다.
5. 유효한 구독이 없으면 Free 플랜을 반환한다.
6. users.plan_id 하나로 현재 플랜을 판단하지 않는다.
```

## Codex 지시문

```text
STEP 3을 진행해줘.

목표는 사용자의 현재 적용 플랜을 계산하는 백엔드 공통 로직을 구현하는 것이야.

구현 규칙:
1. 유효한 subscriptions 중 current_period_start <= now() < current_period_end 인 active 구독만 본다.
2. 여러 구독이 유효하면 plans.plan_rank가 가장 높은 플랜을 현재 플랜으로 선택한다.
3. 유효한 구독이 없으면 Free 플랜을 반환한다.
4. cancel_at_period_end=true 또는 auto_renew=false라도 기간이 남아 있으면 현재 플랜 계산에서 제외하지 않는다.
5. 기존 코드에서 current_plan 또는 user plan을 판단하는 로직이 있다면 이 함수로 대체하거나 연결한다.
6. 기존 API 응답이 깨지지 않게 backward compatible하게 구현한다.
7. 코드 주석은 한국어로 작성한다.
```

## 완료 기준

```text
- Pro와 Studio가 동시에 유효하면 Studio 반환
- Studio가 만료되고 Pro가 유효하면 Pro 반환
- 모든 유료 구독이 없으면 Free 반환
- 취소 예약 상태라도 기간 중이면 유료 플랜 반환
```

---

# STEP 4. 플랜 변경 판단 로직 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

사용자가 다른 플랜을 선택했을 때 업그레이드/다운그레이드/Free 변경을 판단한다.

## 판단 기준

```text
current_plan_rank < target_plan_rank → upgrade
current_plan_rank > target_plan_rank → downgrade
target_plan_code = free → cancel_to_free
current_plan_rank = target_plan_rank → same_plan
```

## API 후보

```text
POST /subscriptions/change-plan
```

요청 예시:

```json
{
  "to_plan_id": "studio"
}
```

응답 예시:

```json
{
  "change_type": "upgrade",
  "apply_timing": "immediate",
  "requires_payment_now": true
}
```

## Codex 지시문

```text
STEP 4를 진행해줘.

목표는 플랜 변경 요청을 받았을 때 change_type을 판단하는 로직을 구현하는 것이야.

정책:
1. 대상 플랜이 Free면 cancel_to_free로 판단한다.
2. 대상 플랜의 plan_rank가 현재 플랜보다 높으면 upgrade다.
3. 대상 플랜의 plan_rank가 현재 플랜보다 낮으면 downgrade다.
4. 대상 플랜이 현재 플랜과 같으면 same_plan으로 처리한다.
5. upgrade는 즉시 결제가 필요하다.
6. downgrade는 즉시 결제하지 않고 period_end 적용 예약이다.
7. cancel_to_free는 구독 취소 예약과 동일하다.
```

---

# STEP 5. 결제 성공 시 30일 구독 생성/연장 로직 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

일반 결제 성공 시 30일 구독을 생성하거나 연장한다.

## 기본 신규 구독

```text
current_period_start = now()
current_period_end = now() + 30 days
next_billing_at = current_period_end
auto_renew = true
cancel_at_period_end = false
status = active
```

## 같은 플랜 재결제/연장

정책:

```text
같은 플랜의 active 구독이 있고 current_period_end가 미래라면 current_period_end를 30일 연장한다.
```

## Codex 지시문

```text
STEP 5를 진행해줘.

목표는 결제 성공 시 30일 구독을 생성하거나 연장하는 기본 로직을 구현하는 것이야.

구현 규칙:
1. 결제 성공 후 plan_id와 user_id를 기준으로 subscriptions를 생성/연장한다.
2. 신규 구독은 now부터 30일 동안 active로 생성한다.
3. 같은 플랜의 active 구독이 이미 있고 current_period_end가 미래라면 current_period_end를 30일 연장한다.
4. 기존 구독이 만료되었거나 inactive라면 새 기간으로 갱신한다.
5. 다른 플랜의 active 구독은 이 Step에서 삭제하거나 덮어쓰지 않는다.
6. 업그레이드 잔여 기간 이월은 STEP 6에서 별도 처리한다.
7. last_payment_id를 연결할 수 있으면 연결한다.
8. 결제 성공 후 current plan은 resolve 함수로 다시 계산한다.
```

---

# STEP 6. 업그레이드 즉시 적용 + 하위 플랜 잔여 기간 이월 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

업그레이드 시 상위 플랜을 즉시 적용하고, 기존 하위 플랜의 남은 기간을 상위 플랜 종료 이후로 이월한다.

## 핵심 예시

```text
Pro: 2026-06-01 ~ 2026-07-01
2026-06-10 Studio 업그레이드

Pro 잔여 기간 = 21일
Studio: 2026-06-10 ~ 2026-07-10
Pro 새 종료일 = 2026-07-10 + 21일 = 2026-07-31
```

## 처리 순서

```text
1. 현재 적용 subscription 조회
2. 대상 상위 플랜 조회
3. plan_rank 비교로 upgrade 확인
4. 하위 플랜 잔여 기간 계산
5. 상위 플랜 결제 진행
6. 결제 성공 시 상위 플랜 subscription 생성
7. 기존 하위 플랜 current_period_end를 상위 플랜 종료 이후로 연장
8. 기존 하위 플랜 auto_renew=false
9. 기존 하위 플랜 cancel_at_period_end=true
10. 기존 하위 플랜 status=active 유지
11. subscription_plan_changes에 upgrade applied 기록
```

## 잔여 기간 계산

```python
remaining_seconds = max(0, lower_subscription.current_period_end - now)
remaining_days = ceil(remaining_seconds / 86400)
```

정확한 계산은 초 단위로 저장하고, 화면 표시만 일 단위로 해도 된다.

## DB 업데이트 개념

```sql
UPDATE subscriptions
SET
    original_period_end = current_period_end,
    current_period_end = :upper_current_period_end + (:remaining_seconds || ' seconds')::interval,
    auto_renew = false,
    cancel_at_period_end = true,
    upgraded_at = now(),
    superseded_by_subscription_id = :upper_subscription_id,
    carried_over_days = :remaining_days,
    updated_at = now()
WHERE subscription_id = :lower_subscription_id;
```

## Codex 지시문

```text
STEP 6을 진행해줘.

목표는 업그레이드 시 상위 플랜 즉시 적용과 기존 하위 플랜 잔여 기간 이월을 구현하는 것이야.

정책:
1. 업그레이드는 현재 플랜보다 plan_rank가 높은 플랜으로 변경하는 경우다.
2. 업그레이드는 즉시 결제한다.
3. 결제 성공 시 상위 플랜 subscription을 now부터 30일로 생성한다.
4. 기존 하위 플랜의 잔여 기간은 소멸시키지 않는다.
5. 기존 하위 플랜의 잔여 기간은 상위 플랜 current_period_end 이후로 이월한다.
6. 기존 하위 플랜의 auto_renew는 false로 바꾼다.
7. 기존 하위 플랜의 cancel_at_period_end는 true로 바꾼다.
8. 기존 하위 플랜의 status는 active로 유지한다.
9. subscription_plan_changes에 upgrade 이력을 applied 상태로 저장한다.
10. 현재 플랜 계산은 plan_rank 기준으로 유지한다.

반드시 테스트할 예:
- Pro가 20일 남은 상태에서 Studio로 업그레이드
- Studio 30일이 즉시 적용
- Studio 종료 후 Pro 20일이 적용
```

## 완료 기준

```text
- Pro 잔여 기간이 사라지지 않음
- Studio 기간 중 current plan = Studio
- Studio 종료 후 Pro 잔여 기간 동안 current plan = Pro
- Pro auto_renew=false라서 중복 자동결제되지 않음
```

---

# STEP 7. 다운그레이드 예약 구현

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

다운그레이드는 즉시 결제하지 않고 현재 플랜 종료 후 적용되도록 예약한다.

## 처리 순서

```text
1. 현재 적용 플랜 조회
2. 대상 플랜 조회
3. 대상 plan_rank가 더 낮으면 downgrade로 판단
4. 현재 subscription.current_period_end를 effective_at으로 설정
5. subscription_plan_changes에 scheduled 기록 생성
6. 즉시 결제하지 않음
7. 현재 플랜은 current_period_end까지 유지
```

## Codex 지시문

```text
STEP 7을 진행해줘.

목표는 다운그레이드 예약 기능을 구현하는 것이야.

정책:
1. 다운그레이드는 현재 플랜보다 낮은 plan_rank의 유료 플랜으로 변경하는 경우다.
2. 다운그레이드는 즉시 결제하지 않는다.
3. 현재 적용 subscription.current_period_end 이후 적용되도록 예약한다.
4. subscription_plan_changes에 change_type='downgrade', apply_timing='period_end', status='scheduled'로 저장한다.
5. effective_at은 현재 적용 subscription.current_period_end로 설정한다.
6. 기존 상위 플랜은 current_period_end까지 유지한다.
7. 사용자 응답에는 변경 예정 플랜과 적용 예정일을 포함한다.
```

## 완료 기준

```text
- Studio → Pro 요청 시 즉시 Pro 결제 없음
- Studio는 만료일까지 유지
- subscription_plan_changes에 scheduled downgrade 생성
- 사용자 화면에서 Pro 변경 예정 표시 가능
```

---

# STEP 8. Free 변경/구독 취소 예약 구현

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

Free 변경을 구독 취소 예약과 동일하게 처리한다.

## 처리 규칙

```text
1. target_plan이 Free이면 cancel_to_free
2. 즉시 권한 제거 금지
3. 현재 subscription.status는 active 유지
4. auto_renew=false
5. cancel_at_period_end=true
6. cancelled_at=now()
7. subscription_plan_changes에 cancel_to_free 기록
8. current_period_end 이후 유효한 다른 구독이 없으면 Free 적용
```

## Codex 지시문

```text
STEP 8을 진행해줘.

목표는 Free 변경과 구독 취소 예약을 구현하는 것이야.

정책:
1. Free로 변경하는 것은 구독 취소와 동일하다.
2. 즉시 권한을 제거하지 않는다.
3. current_period_end까지 기존 플랜을 유지한다.
4. auto_renew=false, cancel_at_period_end=true, cancelled_at=now()로 저장한다.
5. status는 active로 유지한다.
6. subscription_plan_changes에 cancel_to_free 이력을 저장한다.
7. current_period_end 이후에는 유효한 다른 구독이 없으면 Free가 적용되어야 한다.
```

---

# STEP 9. 구독 취소 철회/다운그레이드 예약 취소 구현

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

사용자가 취소 예약이나 다운그레이드 예약을 철회할 수 있게 한다.

## 취소 예약 철회

```text
auto_renew=true
cancel_at_period_end=false
cancelled_at=null
```

단, current_period_end가 이미 지났으면 철회 불가.

## 다운그레이드 예약 취소

```text
subscription_plan_changes.status = cancelled
cancelled_at = now()
```

## API 후보

```text
POST /subscriptions/{subscription_id}/resume
POST /subscriptions/plan-changes/{plan_change_id}/cancel
```

## Codex 지시문

```text
STEP 9를 진행해줘.

목표는 구독 취소 철회와 다운그레이드 예약 취소 기능을 구현하는 것이야.

정책:
1. current_period_end가 지나지 않은 취소 예약 구독은 철회 가능하다.
2. 철회 시 auto_renew=true, cancel_at_period_end=false, cancelled_at=null로 복구한다.
3. 이미 만료된 구독은 철회하지 않는다.
4. scheduled 상태의 다운그레이드 예약은 취소 가능하다.
5. 예약 취소 시 subscription_plan_changes.status='cancelled', cancelled_at=now()로 저장한다.
6. 본인 구독/본인 예약만 취소할 수 있어야 한다.
```

---

# STEP 10. Billing Key 저장 구조 준비

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

Toss 자동결제용 Billing Key를 저장하고 사용할 수 있는 구조를 만든다.

## 주의사항

```text
billing_key는 민감 정보다.
절대 프론트에 내려주지 않는다.
DB 저장 시 암호화한다.
로그에 남기지 않는다.
관리자 화면에도 원문 표시하지 않는다.
```

## Codex 지시문

```text
STEP 10을 진행해줘.

목표는 Toss 자동결제를 위한 Billing Key 저장 구조를 준비하는 것이야.

구현 규칙:
1. billing_keys 테이블을 사용한다.
2. billing_key 원문은 평문 저장하지 않는다.
3. 기존 프로젝트에 암호화 유틸이 있으면 재사용한다.
4. 없으면 환경변수 기반 대칭키 암호화 유틸을 추가하되, 실제 운영키는 .env에서 받도록 한다.
5. billing_key 원문은 API 응답이나 로그에 절대 노출하지 않는다.
6. 관리자/사용자 화면에는 카드사, 마스킹 카드번호, status 정도만 표시한다.
7. Toss Billing Key 발급 API 연동이 이미 있으면 연결하고, 없으면 TODO와 인터페이스만 준비한다.
```

---

# STEP 11. 자동결제 스케줄러 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

`next_billing_at`이 도래한 active 구독을 찾아 자동결제를 수행한다.

## 자동결제 대상 조건

```sql
WHERE status = 'active'
  AND auto_renew = true
  AND cancel_at_period_end = false
  AND next_billing_at <= now()
```

중요:

```text
업그레이드로 밀려난 하위 플랜은 auto_renew=false이므로 자동결제 대상에서 제외된다.
취소 예약 구독도 cancel_at_period_end=true이므로 자동결제 대상에서 제외된다.
```

## Codex 지시문

```text
STEP 11을 진행해줘.

목표는 30일 자동결제 스케줄러를 구현하는 것이야.

구현 규칙:
1. next_billing_at <= now()인 active 구독 중 auto_renew=true, cancel_at_period_end=false인 구독을 조회한다.
2. active billing_key가 없는 구독은 결제 실패 또는 billing_key_missing 상태로 기록한다.
3. Toss 자동결제 API 호출부는 기존 결제 코드가 있으면 재사용한다.
4. 실제 API 연동이 부담되면 결제 호출 인터페이스와 mock/test mode를 먼저 구현한다.
5. 결제 성공 시 구독 기간을 30일 연장한다.
6. 결제 실패 시 subscription_billing_attempts에 실패 사유를 저장한다.
7. 같은 구독이 중복 결제되지 않도록 처리한다.
8. 업그레이드로 auto_renew=false 처리된 하위 구독은 자동결제하지 않는다.
9. 취소 예약 구독은 자동결제하지 않는다.
```

---

# STEP 12. 예약된 다운그레이드 적용 스케줄러 구현

## 권장 모델

```text
권장 모델: GPT-5.5
이 Step은 정책 판단, DB 무결성, 결제/구독 핵심 로직에 영향이 크므로 GPT-5.5로 진행한다.
```

## 목표

`effective_at`이 도래한 다운그레이드 예약을 적용한다.

## 대상 조건

```sql
WHERE change_type = 'downgrade'
  AND status = 'scheduled'
  AND effective_at <= now()
```

## 처리 규칙

```text
1. 예약된 to_plan_id를 조회한다.
2. 사용자의 active billing_key를 조회한다.
3. Billing Key가 없으면 failed 또는 retry_scheduled 처리한다.
4. Billing Key가 있으면 대상 하위 플랜 결제를 진행한다.
5. 결제 성공 시 대상 하위 플랜 subscription을 30일로 생성한다.
6. plan_change.status = applied
7. applied_at = now()
8. to_subscription_id를 연결한다.
9. 결제 실패 시 plan_change.status = failed 또는 retry_scheduled
10. 실패 이력은 subscription_billing_attempts에도 남긴다.
```

## Codex 지시문

```text
STEP 12를 진행해줘.

목표는 예약된 다운그레이드를 effective_at 도래 시 적용하는 스케줄러를 구현하는 것이야.

정책:
1. subscription_plan_changes에서 change_type='downgrade', status='scheduled', effective_at<=now()인 항목을 조회한다.
2. 예약된 to_plan_id로 결제를 진행한다.
3. 결제 성공 시 새 subscription을 30일로 생성한다.
4. plan_change.status='applied', applied_at=now(), to_subscription_id를 저장한다.
5. 결제 실패 시 failed 또는 retry_scheduled로 기록한다.
6. 실패 이력은 subscription_billing_attempts에도 남긴다.
7. 같은 plan_change가 중복 적용되지 않도록 처리한다.
```

---

# STEP 13. 사용자 플랜 화면 반영

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

사용자가 현재 플랜, 다음 결제일, 취소 상태, 플랜 변경 예약 상태를 이해할 수 있게 한다.

## 표시 항목

```text
현재 플랜
현재 플랜 만료일
다음 결제일
자동결제 여부
취소 예약 여부
다운그레이드 예약 여부
상위 플랜 업그레이드 후 하위 플랜 잔여 기간
다음 적용 예정 플랜
구독 취소 버튼
취소 철회 버튼
다운그레이드 예약 취소 버튼
```

## 필수 안내 문구

### 업그레이드 후

```text
현재 플랜: Studio
Studio가 즉시 적용되었습니다.
기존 Pro 잔여 기간 21일은 Studio 종료 후 이어서 적용됩니다.
기존 Pro 자동결제는 중지되었습니다.
```

### 다운그레이드 예약 후

```text
현재 플랜: Studio
Pro로 변경 예약됨
Studio는 2026-07-01까지 유지됩니다.
2026-07-01 이후 Pro 플랜으로 변경됩니다.
```

### Free 변경 후

```text
현재 플랜: Studio
구독 취소 예약됨
2026-07-01까지 Studio 플랜을 사용할 수 있습니다.
이후 유효한 다른 구독이 없으면 Free 플랜으로 전환됩니다.
```

## Codex 지시문

```text
STEP 13을 진행해줘.

목표는 사용자 화면에서 30일 구독 상태와 플랜 변경 예정 상태를 명확히 표시하는 것이야.

구현 규칙:
1. 현재 적용 플랜은 백엔드 current plan API 결과를 사용한다.
2. next_billing_at, current_period_end, cancel_at_period_end, auto_renew를 표시한다.
3. 업그레이드 후 이월된 하위 플랜 잔여 기간을 표시한다.
4. 다운그레이드 예약이 있으면 다음 적용 예정 플랜과 effective_at을 표시한다.
5. 구독 취소 버튼은 cancel API와 연결한다.
6. 취소 예약 상태에서는 취소 철회 버튼을 표시한다.
7. 다운그레이드 예약 상태에서는 예약 취소 버튼을 표시한다.
8. 결제/구독 API가 아직 없으면 mock data fallback으로 UI를 먼저 구성한다.
```

---

# STEP 14. 관리자 구독 관리 화면 반영

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

관리자가 사용자별 구독 상태, 자동결제 상태, 플랜 변경 이력을 확인할 수 있게 한다.

## 표시 항목

```text
사용자
현재 적용 플랜
보유 중인 active 구독 목록
구독 상태
current_period_start
current_period_end
next_billing_at
auto_renew
cancel_at_period_end
업그레이드 이월 여부
carried_over_days
superseded_by_subscription_id
최근 결제 성공/실패
billing_status
예약된 다운그레이드
플랜 변경 이력
```

## 필터

```text
사용자 검색
플랜
구독 상태
자동결제 여부
취소 예약 여부
결제 실패 여부
플랜 변경 예약 여부
```

## Codex 지시문

```text
STEP 14를 진행해줘.

목표는 관리자 화면에서 구독 상태와 플랜 변경 이력을 조회할 수 있도록 하는 것이야.

구현 규칙:
1. 기존 admin 화면 스타일을 따른다.
2. 사용자별 현재 적용 플랜과 active 구독 목록을 보여준다.
3. 자동결제 여부, 취소 예약 여부, 다음 결제일을 표시한다.
4. 업그레이드로 이월된 하위 플랜 잔여 기간을 표시한다.
5. 다운그레이드 예약 상태를 표시한다.
6. 결제 실패 상태를 필터링할 수 있게 한다.
7. 상세 모달 또는 상세 페이지에서 결제 시도 이력과 플랜 변경 이력을 확인할 수 있게 한다.
8. 강제 취소/강제 변경 기능은 이번 Step에서는 만들지 말고 조회 중심으로 구현한다.
```

---

# STEP 15. 테스트 및 리포트 작성

## 권장 모델

```text
권장 모델: GPT-5.4
이 Step은 이미 정의된 정책을 구현/표시/검증하는 작업이므로 GPT-5.4로 진행한다. 정책 충돌이나 결제 중복 가능성이 보이면 작업을 중단하고 GPT-5.5로 재검토한다.
```

## 목표

전체 정책이 의도대로 동작하는지 확인한다.

## 필수 테스트 케이스

### 15.1 Free → Pro

```text
Free 사용자
→ Pro 결제
→ current plan = Pro
→ current_period_end = 결제일 + 30일
```

### 15.2 Free → Studio

```text
Free 사용자
→ Studio 결제
→ current plan = Studio
→ current_period_end = 결제일 + 30일
```

### 15.3 Pro → Studio 업그레이드 + Pro 잔여 기간 이월

```text
Pro가 20일 남은 상태
→ Studio 업그레이드
→ Studio 즉시 결제
→ current plan = Studio
→ Pro current_period_end = Studio 종료일 + Pro 잔여 기간
→ Pro auto_renew=false
→ Studio 종료 후 current plan = Pro
```

### 15.4 업그레이드 후 중복 자동결제 방지

```text
Pro → Studio 업그레이드
→ Pro auto_renew=false
→ Pro는 자동결제 대상에서 제외
→ Studio만 자동결제 대상
```

### 15.5 Studio → Pro 다운그레이드 예약

```text
Studio active 상태
→ Pro 변경 요청
→ 즉시 Pro 결제 없음
→ subscription_plan_changes에 downgrade scheduled 생성
→ effective_at = Studio current_period_end
```

### 15.6 다운그레이드 예약 적용

```text
effective_at 도래
→ Pro 자동결제 진행
→ 결제 성공
→ Pro subscription 생성
→ plan_change status=applied
```

### 15.7 다운그레이드 예약 취소

```text
Studio → Pro 예약 상태
→ 예약 취소
→ plan_change status=cancelled
→ 기존 Studio 유지
```

### 15.8 Studio → Free 변경

```text
Studio active
→ Free 변경
→ auto_renew=false
→ cancel_at_period_end=true
→ current_period_end까지 Studio 유지
→ 이후 Free 적용
```

### 15.9 구독 취소 철회

```text
cancel_at_period_end=true
→ 취소 철회
→ auto_renew=true
→ cancel_at_period_end=false
```

### 15.10 자동결제 성공

```text
next_billing_at 도래
→ 결제 성공
→ current_period_end + 30일
→ next_billing_at 갱신
```

### 15.11 자동결제 실패

```text
next_billing_at 도래
→ 결제 실패
→ subscription_billing_attempts failed 저장
→ billing_status 갱신
```

### 15.12 모든 유료 플랜 만료

```text
Pro/Studio 모두 만료
→ current plan = Free
```

## Codex 지시문

```text
STEP 15를 진행해줘.

목표는 30일 구독제 전환과 플랜 변경 정책의 테스트 및 리포트를 작성하는 것이야.

반드시 확인할 테스트:
1. Free → Pro
2. Free → Studio
3. Pro → Studio 업그레이드 + Pro 잔여 기간 이월
4. 업그레이드 후 하위 플랜 중복 자동결제 방지
5. Studio → Pro 다운그레이드 예약
6. 다운그레이드 예약 적용
7. 다운그레이드 예약 취소
8. Studio → Free 변경
9. 구독 취소 철회
10. 자동결제 성공
11. 자동결제 실패
12. 모든 유료 플랜 만료 후 Free 적용

테스트 결과를 report 폴더에 md 파일로 작성해줘.
기존 report 폴더가 없으면 생성해줘.
```

<!-- 파일명은 GEMINI.md 규칙에 맞춰 일자별 버전으로 작성해줘. -->

---

## 4. API 설계 초안

실제 라우트는 기존 프로젝트 구조에 맞춰 조정한다.

## 4.1 사용자용 API

```text
GET  /subscriptions/me
GET  /plans/current
POST /subscriptions/checkout
POST /subscriptions/change-plan
POST /subscriptions/{subscription_id}/cancel
POST /subscriptions/{subscription_id}/resume
POST /subscriptions/plan-changes/{plan_change_id}/cancel
```

## 4.2 관리자용 API

```text
GET /admin/subscriptions
GET /admin/subscriptions/{subscription_id}
GET /admin/subscriptions/{subscription_id}/billing-attempts
GET /admin/subscriptions/{subscription_id}/plan-changes
```

## 4.3 내부 서비스 함수 후보

```text
resolve_current_plan(user_id)
classify_plan_change(user_id, to_plan_id)
create_or_extend_subscription(user_id, plan_id, payment_id)
apply_upgrade_with_carryover(user_id, from_subscription_id, to_plan_id, payment_id)
schedule_downgrade(user_id, from_subscription_id, to_plan_id)
cancel_to_free(user_id, subscription_id)
resume_subscription(subscription_id)
cancel_scheduled_plan_change(plan_change_id)
run_subscription_renewals()
run_scheduled_downgrades()
charge_subscription_with_billing_key(subscription_id)
```

---

## 5. 프론트 응답 데이터 예시

## 5.1 현재 플랜 응답

```json
{
  "current_plan": {
    "plan_id": "studio",
    "plan_code": "studio",
    "plan_name": "Studio",
    "plan_rank": 20
  },
  "current_subscription": {
    "subscription_id": "sub_studio_001",
    "status": "active",
    "current_period_start": "2026-06-10T00:00:00",
    "current_period_end": "2026-07-10T00:00:00",
    "next_billing_at": "2026-07-10T00:00:00",
    "auto_renew": true,
    "cancel_at_period_end": false
  },
  "carried_over_subscription": {
    "plan_code": "pro",
    "plan_name": "Pro",
    "carried_over_days": 21,
    "current_period_end": "2026-07-31T00:00:00",
    "auto_renew": false
  },
  "scheduled_plan_change": {
    "plan_change_id": "chg_001",
    "change_type": "downgrade",
    "to_plan_code": "pro",
    "to_plan_name": "Pro",
    "status": "scheduled",
    "effective_at": "2026-07-10T00:00:00"
  }
}
```

---

## 6. 가장 중요한 예외 케이스

| 케이스 | 처리 |
|---|---|
| Pro가 남아 있는데 Studio 업그레이드 | Studio 즉시 적용, Pro 잔여 기간은 Studio 이후로 이월 |
| 업그레이드 후 Pro 자동결제 | Pro auto_renew=false로 중복 결제 방지 |
| Studio에서 Pro로 다운그레이드 | 즉시 결제하지 않고 period_end 예약 |
| Studio에서 Free로 변경 | 구독 취소 예약과 동일 |
| 다운그레이드 예약 취소 | subscription_plan_changes.status=cancelled |
| 취소 예약 철회 | auto_renew=true, cancel_at_period_end=false |
| Billing Key 없음 | 자동결제 실패 기록 |
| 모든 유료 구독 만료 | Free 적용 |

---

## 7. Codex 전체 시작 프롬프트

아래 프롬프트로 시작한다.

<!-- GEMINI.md 규칙을 먼저 확인해줘. -->

```text
이 프로젝트는 GARIM 영상 개인정보 탐지/마스킹 서비스입니다.
Free / Pro / Studio 플랜을 30일 자동결제 구독제로 전환하려고 합니다.

작업 지시서는 프로젝트 루트의 subscription_30day_auto_renewal_final_v2.md 파일에 있습니다.

먼저 STEP 1만 진행해주세요.
코드 수정은 하지 말고 현재 DB/백엔드/프론트 구조를 분석한 뒤 Implementation Plan을 작성해주세요.

핵심 정책:
- Pro / Studio는 30일 단위 구독입니다.
- 사용자가 취소하지 않으면 30일마다 자동 결제됩니다.
- 취소하면 즉시 권한 제거가 아니라 current_period_end까지 유지됩니다.
- 현재 플랜은 users.plan_id 하나로 고정하지 말고 active subscriptions에서 계산해야 합니다.
- 업그레이드는 즉시 결제 + 즉시 적용입니다.
- 업그레이드 시 기존 하위 플랜의 잔여 기간은 상위 플랜 종료 이후로 이월해야 합니다.
- 업그레이드 시 기존 하위 플랜은 auto_renew=false로 바꿔 중복 자동결제를 막아야 합니다.
- 다운그레이드는 즉시 결제하지 않고 current_period_end 이후 적용 예약입니다.
- Free 변경은 구독 취소 예약과 동일합니다.
```

---

## 8. 최종 완료 기준

전체 Step 완료 후 아래가 가능해야 한다.

```text
- Free / Pro / Studio 플랜 우선순위가 명확하다.
- Pro/Studio 30일 구독 생성이 가능하다.
- 현재 적용 플랜은 plan_rank 기반으로 계산된다.
- Pro → Studio 업그레이드 시 Studio가 즉시 적용된다.
- 업그레이드 시 Pro 잔여 기간이 사라지지 않고 Studio 종료 이후로 이월된다.
- 업그레이드 후 Pro auto_renew=false로 중복 자동결제가 방지된다.
- Studio → Pro 다운그레이드는 즉시 결제하지 않고 예약된다.
- 예약된 다운그레이드는 effective_at 도래 시 결제/적용된다.
- Free 변경은 구독 취소 예약으로 처리된다.
- 구독 취소 시 current_period_end까지 권한이 유지된다.
- 취소 예약 구독은 자동결제 대상에서 제외된다.
- 취소 철회가 가능하다.
- 자동결제 성공 시 30일 연장된다.
- 자동결제 실패 이력이 남는다.
- 사용자 화면에서 현재 플랜/다음 결제일/취소 상태/변경 예약/이월 기간을 볼 수 있다.
- 관리자 화면에서 구독 상태/자동결제 상태/결제 실패/플랜 변경 이력을 볼 수 있다.
- 기존 결제/플랜/크레딧 데이터가 삭제되지 않는다.
```
