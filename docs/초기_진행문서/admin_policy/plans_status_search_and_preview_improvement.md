# Plans Admin Visibility & Preview Improvement Plan

이 문서는 요금제 관리 기능 고도화를 위한 검색 기능 추가, 관리 상태 한글 표기, 활성 구독 플랜 개수 제한(최대 4개) 및 플랜 미리보기 UI 고도화 작업에 대한 설계 지침을 기술합니다.

---

## 1. 요구사항 상세

### 1) 상태 값에 따른 검색 기능 추가
- 관리자 요금제 관리 화면(`AdminPolicy.jsx`)의 구독 플랜 및 크레딧 플랜 탭 목록의 상단 필터 영역에 **상태 필터(Status Filter)**를 추가합니다.
- 필터 조건: `전체(all)`, `사용중(active)`, `미사용(inactive)`.
- 필터 상태가 변경되면 API 요청 파라미터에 `status`를 실어 조회하며, 백엔드와 연동하여 조건 조회를 수행합니다.

### 2) 관리 상태 UI 한글 명칭 변경
- 플랜 생성/수정 모달의 관리 상태 select 옵션 및 목록 테이블의 상태 텍스트를 다음과 같이 변경합니다.
  - `active` ➔ **사용중**
  - `inactive` ➔ **미사용**
  - `deleted` ➔ **삭제** (목록에는 deleted 상태는 기본 제외되지만, 상태 문구 자체는 한글 매핑 적용)

### 3) 활성 구독 플랜 개수 제한 (최대 4개)
- 요금제 카드 그리드 레이아웃의 시각적 일관성을 지키기 위해, `status = 'active'` 상태인 구독 플랜(Subscription Plan) 카드는 **최대 4개**까지만 노출되도록 제한 조건을 추가합니다.
- **프론트엔드 검증**: 
  - 모달 폼 저장 시, 새로운 플랜을 `사용중(active)`으로 생성하거나 기존 플랜의 상태를 `사용중(active)`으로 변경하려고 할 때, 현재 활성화된(status가 active인) 구독 플랜 개수를 검사합니다.
  - 현재 활성 상태인 구독 플랜 개수가 4개이고, 수정하려는 플랜이 기존에 비활성(`inactive`) 상태였던 경우 저장을 차단하고 alert 경고창을 띄웁니다.
- **백엔드 검증 (데이터 무결성)**:
  - 백엔드 서비스 `create_subscription_plan` 및 `update_subscription_plan` 함수 실행 시, DB 상에서 `status = 'active'` 인 구독 플랜의 개수를 `COUNT` 쿼리로 검사합니다.
  - 4개를 초과하게 될 경우 `ValueError`를 발생시키고 API 에러(400 Bad Request)를 반환합니다.

### 4) 플랜 미리보기 패널 UI 고도화
- 관리자가 플랜 수정/등록 모달 창을 띄웠을 때 우측에 렌더링되는 실시간 미리보기(`PlanPreviewPanel`, `CreditPreviewPanel`) 화면을 프리미엄 디자인 요소를 가미하여 고도화합니다.
- **디자인 세부 사항**:
  - **글라스모피즘 스타일**: 부드러운 반투명 백그라운드, 그라데이션 보더라인, 미세한 입체감(`box-shadow`) 부여.
  - **시각적 위계(Typography)**: 플랜명, 금액, 원화 단위의 크기 및 볼드 처리를 조절하고, 혜택 항목(`feats`)들의 행간 정렬 및 체크 아이콘 정렬 개선.
  - **마이크로 인터랙션**: 미리보기이지만 프리미엄한 호버 효과나 활성화 상태를 체감할 수 있는 쉐도우 효과 정의.

---

## 2. Proposed Changes

### 1) Backend API 수정

#### [MODIFY] [admin.py (Controller)](file:///d:/final_project/Human_Final_PJ/backend/controllers/admin.py)
- `list_subscription_plans` 및 `list_credit_plans` API에 `status` 쿼리 파라미터를 추가하여 서비스로 전달하도록 변경합니다.

```python
def list_subscription_plans(
    q: str = Query(None),
    include_deleted: bool = Query(False),
    status: str = Query(None), # 추가
):
    try:
        data = admin_service.list_subscription_plans(q, include_deleted, status)
```

#### [MODIFY] [admin.py (Service)](file:///d:/final_project/Human_Final_PJ/backend/services/admin.py)
- `list_subscription_plans` 및 `list_credit_plans` 함수에서 `status` 필터 파라미터를 받아 `_build_filter_clause` 에서 조건 조회를 하도록 SQL을 수정합니다.
- `create_subscription_plan` 및 `update_subscription_plan`에 **활성 플랜 4개 제한 유효성 검증 로직**을 추가합니다.

```python
def create_subscription_plan(payload: dict):
    # status = 'active' 인지 확인
    data = _clean_payload(payload, PLAN_FIELDS)
    if data.get("status") == "active":
        db = SessionLocal()
        try:
            # 현재 active 구독 플랜 개수 카운트
            active_count = db.execute(
                text("SELECT COUNT(*) FROM plans WHERE status = 'active'")
            ).scalar()
            if active_count >= 4:
                raise ValueError("활성화된 구독 플랜 카드는 최대 4개까지만 등록할 수 있습니다.")
        finally:
            db.close()
```

---

### 2) Frontend UI 수정

#### [MODIFY] [api.js](file:///d:/final_project/Human_Final_PJ/frontend/src/utils/api.js)
- `buildAdminPlanQuery` 유틸리티 함수에 `status` 쿼리 파라미터를 파싱하도록 로직을 반영합니다.

#### [MODIFY] [AdminPolicy.jsx](file:///d:/final_project/Human_Final_PJ/frontend/src/pages/garim/AdminPolicy.jsx)
- **상태 값 검색**: 탭 하단 검색 필드 옆에 `<select>` 드롭다운을 추가하여, `activeTab`에 맞게 `status` 필터를 적용하고 API를 재호출하도록 수정합니다.
- **상태 UI 한국어 노출**: 
  - 테이블 행 내의 뱃지 렌더링 부분과 모달 폼 내의 `SelectField` 옵션을 한국어로 변경합니다.
- **최대 4개 제한**:
  - 플랜 등록/수정 폼의 `onSave` 이벤트 실행 전, `form.status === "active"`인 경우 현재 목록 중 `status === "active"`인 구독 플랜의 개수를 세어 제한 유효성 검사를 적용합니다.
- **미리보기 고도화**:
  - `PlanPreviewPanel` 및 `CreditPreviewPanel` 구조를 개선하고 시각적 디자인을 향상시킬 수 있는 마크업과 전용 CSS 클래스를 적용합니다.

#### [MODIFY] [AdminPolicy.css](file:///d:/final_project/Human_Final_PJ/frontend/src/css/garim-pages/AdminPolicy.css)
- 미리보기 패널을 위한 스타일 추가:
  - 투명한 유광 효과(Background gradient + backdrop-filter)
  - 입체감 있는 부드러운 그림자 효과
  - 타이포그래피 비율 및 정렬 조절
  - 버튼의 세련된 디자인 및 배지(mui-chip)의 스타일 정밀화

---

## 3. 구현 단계 및 테스트 계획 (Step-by-Step)

안정적인 빌드와 무결성 확보를 위해 작업을 5개의 단계로 분할하고 각 단계별 검증 절차를 수행합니다.

### 🏁 Step 1: 백엔드 API 및 검증 로직 구현
- **작업 내용**:
  - `list_subscription_plans` 및 `list_credit_plans` API에 `status` 조건 추가
  - 구독 플랜 추가/수정 시 `status = 'active'` 인 활성 플랜이 4개를 초과하지 못하도록 검증 처리
- **테스트 방법**:
  - Python 대화형 인터랙티브 쉘 혹은 임시 스크립트 실행을 통해 `admin_service.list_subscription_plans(status="active")` 등의 메서드가 올바르게 필터링된 목록을 반환하는지 테스트합니다.
  - 현재 활성 상태인 구독 플랜이 4개인 상황을 연출하고, 5번째 active 구독 플랜 생성을 시도할 때 `ValueError`가 정상적으로 발생하는지 비즈니스 로직을 호출하여 강제 검증합니다.

### 🏁 Step 2: 백엔드 유닛 테스트 보완 및 통과
- **작업 내용**:
  - `backend/tests/test_admin_policy.py` 에 status 필터 조회와 4개 초과 활성화 검증을 테스트하는 테스트 함수들을 추가합니다.
- **테스트 방법**:
  - 백엔드 관리 정책 테스트 스위트를 구동하여 작성한 테스트가 통과하는지 확인합니다.
    ```bash
    pytest backend/tests/test_admin_policy.py -q
    ```

### 🏁 Step 3: 프론트엔드 API 연동 및 상태 UI 수정
- **작업 내용**:
  - `api.js` 에서 `status` 쿼리 파라미터를 백엔드로 전달하도록 수정
  - `AdminPolicy.jsx` 요금제 목록 영역에 상태 필터 select 박스 추가 및 상태값 한글화 매핑 (`active` ➔ `사용중`, `inactive` ➔ `미사용`, `deleted` ➔ `삭제`)
  - 프론트엔드 저장 버튼 실행 전, 로컬 폼 상태 상 `status === 'active'`인 구독 플랜 개수가 4개를 초과할 시 `alert` 팝업을 띄우고 저장을 차단하는 프론트엔드 유효성 검사 추가
- **테스트 방법**:
  - 브라우저 개발자 도구(`F12`)의 네트워크(Network) 탭에서 필터 상태 선택 시 `/admin/plans?status=active` 와 같이 호출 인자가 정확히 붙는지 확인합니다.
  - 모달 폼에서 `사용중 / 미사용 / 삭제` 옵션 선택 시 UI가 문제없이 반응하는지 테스트합니다.
  - 이미 4개가 active인 상태에서 추가 요금제의 상태를 `사용중`으로 선택해 저장을 시도할 때, 브라우저 `alert` 팝업 창("활성화된 구독 플랜 카드는 최대 4개까지만 등록할 수 있습니다...")이 정상 노출되며 API 요청이 차단되는지 확인합니다.

### 🏁 Step 4: 미리보기 패널(Preview Panel) UI 및 CSS 고도화
- **작업 내용**:
  - `AdminPolicy.jsx` 의 `PlanPreviewPanel` 및 `CreditPreviewPanel` 마크업 구조 고도화
  - `AdminPolicy.css` 에 반투명 블러 효과(backdrop-filter), 입체감 쉐도우 효과, 타이포그래피 정렬 등 세련된 스타일시트 추가
- **테스트 방법**:
  - 요금제 추가/수정 모달창을 띄우고, 좌측 폼 입력값을 실시간으로 바꿀 때(예: 배지 명칭, 금액 등) 우측 미리보기 카드가 조화롭고 깨짐 없이 즉각 갱신되는지 시각적으로 검증합니다.
  - 글라스모피즘 반투명 마감, 그라데이션 보더라인, 뱃지 둥글기 톤이 기획대로 어우러져 프리미엄하게 연출되는지 다각도로 확인합니다.

### 🏁 Step 5: 전체 정적 테스트 및 최종 빌드 검증
- **작업 내용**:
  - `test_frontend_analysis_progress_static.py` 내의 정적 레이아웃 및 폼 필드 확인 어설션 재검토
  - 프로덕션 빌드 무결성 확인
- **테스트 방법**:
  - 프론트엔드 정적 분석 검사 실행:
    ```bash
    pytest tests/test_frontend_analysis_progress_static.py -q
    ```
  - 프론트엔드 최종 빌드 커맨드 실행하여 빌드 오류가 없는지 최종 보증:
    ```bash
    cmd /c npm run build
    ```
