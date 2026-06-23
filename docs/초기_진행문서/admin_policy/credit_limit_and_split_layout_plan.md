# Credit Plan Max Limit (8) & Balanced Pricing Layout Plan

이 문서는 크레딧 플랜의 운영 최적화 및 프리미엄 레이아웃 구현을 위해, 관리자 화면에서 활성화할 수 있는 크레딧 상품 개수를 최대 8개로 제한하고, 요금제 페이지에서 이 크레딧 카드들이 대칭 구조로 매끄럽게 렌더링되도록 균형 분할 배치(React Balanced Split) 작업을 처리하는 설계 지침을 기술합니다.

---

## 1. 요구사항 상세

### 1) 활성 크레딧 플랜 개수 제한 (최대 8개)
- **백엔드 검증 (데이터 무결성)**:
  - `admin_service.create_credit_plan` 및 `admin_service.update_credit_plan` 실행 시, DB 상에서 `status = 'active'` 상태인 크레딧 플랜의 개수를 `COUNT` 쿼리로 검사합니다.
  - 생성/수정 후 8개를 초과하게 될 경우 `ValueError`를 발생시키고 API 에러(400 Bad Request)를 반환합니다.
- **프론트엔드 검증**:
  - `AdminPolicy.jsx` 요금제 관리 화면에서 크레딧 저장 전, 저장하려는 상태가 `active(사용중)`인 경우 활성 크레딧 카드 수가 8개를 넘지 않는지 검사합니다.
  - 현재 활성 상태인 크레딧 플랜 개수가 8개이고 수정하려는 플랜이 기존에 비활성(`inactive`) 상태였던 경우 저장을 차단하고 alert 경고창("활성화된 크레딧 플랜 카드는 최대 8개까지만 등록할 수 있습니다.")을 띄웁니다.

### 2) Pricing 페이지 크레딧 카드 균형 분할 레이아웃 (React Balanced Split)
- Pricing 페이지(`Pricing.jsx`)에서 노출되는 활성 크레딧 카드를 단순 Flex Wrapping 대신, 카드 총 개수($N$)에 맞춰 Row를 균형 있게 강제 분할하여 완벽한 좌우 대칭 구조를 보장합니다.
- **개수별 분할 맵핑 테이블**:
  - **$N \le 4$**: 1개 Row에 전체 배치 (`[N]`)
  - **$N = 5$**: 1Row(3개), 2Row(2개) 분할 (`[3, 2]`)
  - **$N = 6$**: 1Row(3개), 2Row(3개) 분할 (`[3, 3]`)
  - **$N = 7$**: 1Row(4개), 2Row(3개) 분할 (`[4, 3]`)
  - **$N = 8$**: 1Row(4개), 2Row(4개) 분할 (`[4, 4]`)

---

## 2. Proposed Changes

### 1) Backend API 수정

#### [MODIFY] [admin.py (Service)](file:///d:/final_project/Human_Final_PJ/backend/services/admin.py)
- `create_credit_plan` 및 `update_credit_plan` 비즈니스 로직에 active 크레딧 카드 개수 검증 조건을 추가합니다.

```python
def create_credit_plan(payload: dict):
    data = _clean_payload(payload, CREDIT_PLAN_FIELDS)
    if data.get("status") == "active":
        db = SessionLocal()
        try:
            active_count = db.execute(
                text("SELECT COUNT(*) FROM credit_plans WHERE status = 'active'")
            ).scalar()
            if active_count >= 8:
                raise ValueError("활성화된 크레딧 플랜 카드는 최대 8개까지만 등록할 수 있습니다.")
        finally:
            db.close()
```

---

### 2) Frontend UI 수정

#### [MODIFY] [AdminPolicy.jsx](file:///d:/final_project/Human_Final_PJ/frontend/src/pages/garim/AdminPolicy.jsx)
- `saveCreditPlan` 이벤트 실행 전, 로컬 폼 상태 상 `status === 'active'`인 크레딧 플랜 개수가 8개를 초과할 시 `alert` 팝업을 띄우고 저장을 차단하는 검증 로직을 추가합니다.

```javascript
  async function saveCreditPlan() {
    try {
      setSaveMessage("");
      const payload = buildPayload(creditForm, CREDIT_NUMBER_FIELDS);

      if (payload.status === "active") {
        const activeRes = await getAdminCreditPlans({ status: "active" });
        const activeCount = (activeRes.data || []).length;
        const isCurrentlyActive =
          selectedCreditPlanId &&
          creditPlans.find((p) => p.credit_plan_id === selectedCreditPlanId)?.status === "active";

        if (!isCurrentlyActive && activeCount >= 8) {
          alert("활성화된 크레딧 플랜 카드는 최대 8개까지만 등록할 수 있습니다.");
          return;
        }
      }
      ...
```

#### [MODIFY] [Pricing.jsx](file:///d:/final_project/Human_Final_PJ/frontend/src/pages/garim/Pricing.jsx)
- 활성 크레딧 리스트(`creditPlans`)의 길이에 따라 row 배열을 생성하는 분할 알고리즘을 추가하고, 이를 활용해 이중 map 형태로 Row 단위 렌더링을 진행합니다.

```javascript
  // 크레딧 카드 React 기반 대칭 분할 알고리즘
  const displayedCredits = creditPlans.slice(0, 8);
  const creditCount = displayedCredits.length;
  let creditRows = [];
  
  if (creditCount <= 4) {
    creditRows = [displayedCredits];
  } else if (creditCount === 5) {
    creditRows = [displayedCredits.slice(0, 3), displayedCredits.slice(3, 5)];
  } else if (creditCount === 6) {
    creditRows = [displayedCredits.slice(0, 3), displayedCredits.slice(3, 6)];
  } else if (creditCount === 7) {
    creditRows = [displayedCredits.slice(0, 4), displayedCredits.slice(4, 7)];
  } else if (creditCount === 8) {
    creditRows = [displayedCredits.slice(0, 4), displayedCredits.slice(4, 8)];
  }
```

- 마크업에서 `creditRows.map((row, rIdx) => ...)` 와 `row.map(plan => ...)` 구조를 사용해 깔끔하게 분리 출력합니다.

#### [MODIFY] [Pricing.css](file:///d:/final_project/Human_Final_PJ/frontend/src/css/garim-pages/Pricing.css)
- 크레딧 렌더링을 위한 전용 `.credit-row` 및 정렬 관련 스타일을 정의합니다.

```css
.credit-row-wrap {
  display: flex;
  flex-direction: column;
  gap: 24px;
  align-items: center;
  width: 100%;
}
.credit-row {
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
  width: 100%;
}
```

---

## 3. 구현 단계 및 테스트 계획

### 🏁 Step 1: 백엔드 API & 검증 로직 구현
- **작업**:
  - `admin_service.py` 내 크레딧 생성/수정 시 `status = 'active'` 개수 카운트 및 8개 초과 차단 추가.
- **검증**:
  - `backend/tests/test_admin_policy.py` 에 8개 초과 에러 유닛 테스트를 추가하고, pytest가 통과하는지 확인.
    ```bash
    pytest backend/tests/test_admin_policy.py -q
    ```

### 🏁 Step 2: 프론트엔드 관리자 validation 연동
- **작업**:
  - `AdminPolicy.jsx` 모달 저장 시 크레딧 8개 초과 제한 검사 alert 추가.
- **검증**:
  - 8개가 활성화된 상태에서 추가로 크레딧을 활성화하려고 시도할 때 저장 차단 팝업이 노출되는지 수동 검증.

### 🏁 Step 3: Pricing 크레딧 Row 대칭 분할 알고리즘 구현
- **작업**:
  - `Pricing.jsx` 내 `creditRows` 분할 변수 선언 및 Row 렌더링 마크업 변경.
  - `Pricing.css` 에 Row 정렬 스타일 추가.
- **검증**:
  - 활성 크레딧 카드를 5개, 6개, 7개 등으로 설정한 후 화면 새로고침 시 의도된 구조(3+2, 3+3 등)로 예쁘게 가운데 정렬되어 출력되는지 브라우저에서 교차 검증.

### 🏁 Step 4: 전체 정적 검사 및 최종 프로덕션 빌드 성공 확인
- **작업**:
  - 정적 테스트 통과 및 Vite 최종 빌드 무결성 재점검.
- **검증**:
  - 정적 분석 및 최종 빌드 실행:
    ```bash
    pytest tests/test_frontend_analysis_progress_static.py -q
    cmd /c "npm run build --prefix frontend"
    ```
