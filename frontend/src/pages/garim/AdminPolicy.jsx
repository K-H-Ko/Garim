import { useEffect, useMemo, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/AdminPolicy.css";

import GarimPage from "../../components/garim/GarimPage";
import {
  createAdminCreditPlan,
  createAdminPlan,
  deleteAdminCreditPlan,
  deleteAdminPlan,
  getAdminCreditPlans,
  getAdminPlans,
  updateAdminCreditPlan,
  updateAdminPlan,
} from "../../utils/api";

const SUBSCRIPTION_DEFAULT = {
  plan_code: "",
  plan_name: "",
  badge_label: "",
  badge_class: "mui-chip--primary",
  description: "",
  monthly_quota: "",
  result_retention_days: "",
  watermark_required: false,
  price_amount: "0",
  sort_order: "0",
  status: "active",
  file_size_limit: "50",
  max_jobs: "3",
  auto_delete_original_hours: "12",
  metadata_retention_days: "90",
  credits: "0",
};

const CREDIT_DEFAULT = {
  credit_plan_code: "",
  credit_plan_name: "",
  price_amount: "0",
  base_credits: "",
  bonus_credits: "0",
  expires_days: "",
  sort_order: "0",
  status: "active",
};

const SUBSCRIPTION_NUMBER_FIELDS = [
  "monthly_quota",
  "result_retention_days",
  "price_amount",
  "sort_order",
  "file_size_limit",
  "max_jobs",
  "auto_delete_original_hours",
  "metadata_retention_days",
  "credits",
];

const CREDIT_NUMBER_FIELDS = [
  "price_amount",
  "base_credits",
  "bonus_credits",
  "expires_days",
  "sort_order",
];

const BADGE_CLASS_OPTIONS = [
  "mui-chip--primary",
  "mui-chip--secondary",
  "mui-chip--soft-warning",
  "mui-chip--soft-info",
  "mui-chip--soft-success",
  "mui-chip--soft-error",
  "mui-chip--warning",
  "mui-chip--success",
  "mui-chip--info",
  "mui-chip--error",
];

const STATUS_OPTIONS = ["active", "inactive", "deleted"];
const PAGE_LIMIT_OPTIONS = [5, 10, 20, 50, 100];

function normalizeForm(row, defaults) {
  const next = { ...defaults };
  for (const key of Object.keys(defaults)) {
    if (typeof defaults[key] === "boolean") {
      next[key] = Boolean(row?.[key]);
    } else if (key === "badge_class" && !row?.[key]) {
      next[key] = defaults[key];
    } else if (row?.[key] === null || row?.[key] === undefined) {
      next[key] = "";
    } else {
      next[key] = String(row[key]);
    }
  }
  return next;
}

function numberOrNull(value) {
  if (value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildPayload(form, numberFields) {
  const payload = {};
  for (const [key, value] of Object.entries(form)) {
    if (numberFields.includes(key)) {
      payload[key] = numberOrNull(value);
    } else {
      payload[key] = value;
    }
  }
  return payload;
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function statusLabel(status) {
  if (status === "deleted") return "삭제";
  if (status === "inactive") return "미사용";
  return "사용중";
}

export default function AdminPolicy() {
  useDocumentTitle("정책 및 상품 관리 · Garim Admin");

  const [activeTab, setActiveTab] = useState("subscription");
  const [plans, setPlans] = useState([]);
  const [creditPlans, setCreditPlans] = useState([]);
  const [planSearch, setPlanSearch] = useState("");
  const [creditSearch, setCreditSearch] = useState("");
  const [subscriptionPage, setSubscriptionPage] = useState(1);
  const [subscriptionLimit, setSubscriptionLimit] = useState(10);
  const [subscriptionTotal, setSubscriptionTotal] = useState(0);
  const [creditPage, setCreditPage] = useState(1);
  const [creditLimit, setCreditLimit] = useState(10);
  const [creditTotal, setCreditTotal] = useState(0);
  const [selectedPlanId, setSelectedPlanId] = useState(null);
  const [selectedCreditPlanId, setSelectedCreditPlanId] = useState(null);
  const [planForm, setPlanForm] = useState(SUBSCRIPTION_DEFAULT);
  const [creditForm, setCreditForm] = useState(CREDIT_DEFAULT);
  const [isLoading, setIsLoading] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");

  // 모달 열림 상태
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [creditModalOpen, setCreditModalOpen] = useState(false);

  // 상태 필터 (전체/사용중/미사용)
  const [planStatus, setPlanStatus] = useState("all");
  const [creditStatus, setCreditStatus] = useState("all");

  const selectedPlan = useMemo(
    () => plans.find((plan) => plan.plan_id === selectedPlanId),
    [plans, selectedPlanId],
  );
  const selectedCreditPlan = useMemo(
    () =>
      creditPlans.find((plan) => plan.credit_plan_id === selectedCreditPlanId),
    [creditPlans, selectedCreditPlanId],
  );

  async function loadSubscriptionPlans(
    search = planSearch,
    status = planStatus,
    page = subscriptionPage,
    limit = subscriptionLimit,
  ) {
    setIsLoading(true);
    try {
      const response = await getAdminPlans({
        page,
        limit,
        q: search,
        status: status === "all" ? undefined : status,
        include_deleted: status === "deleted",
      });
      const rows = response.data || [];
      const total = response.total || 0;
      const lastPage = Math.max(1, Math.ceil(total / limit));
      if (page > lastPage) {
        setSubscriptionPage(lastPage);
        setSubscriptionTotal(total);
        return;
      }
      setPlans(rows);
      setSubscriptionTotal(total);
    } catch (error) {
      console.error("Failed to load subscription plans", error);
      setSaveMessage("구독 플랜 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadCreditPlans(
    search = creditSearch,
    status = creditStatus,
    page = creditPage,
    limit = creditLimit,
  ) {
    setIsLoading(true);
    try {
      const response = await getAdminCreditPlans({
        page,
        limit,
        q: search,
        status: status === "all" ? undefined : status,
        include_deleted: status === "deleted",
      });
      const rows = response.data || [];
      const total = response.total || 0;
      const lastPage = Math.max(1, Math.ceil(total / limit));
      if (page > lastPage) {
        setCreditPage(lastPage);
        setCreditTotal(total);
        return;
      }
      setCreditPlans(rows);
      setCreditTotal(total);
    } catch (error) {
      console.error("Failed to load credit plans", error);
      setSaveMessage("크레딧 플랜 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadSubscriptionPlans(planSearch, planStatus, subscriptionPage, subscriptionLimit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planStatus, subscriptionPage, subscriptionLimit]);

  useEffect(() => {
    loadCreditPlans(creditSearch, creditStatus, creditPage, creditLimit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creditStatus, creditPage, creditLimit]);

  function openEditSubscriptionPlan(plan) {
    setSelectedPlanId(plan.plan_id);
    setPlanForm(normalizeForm(plan, SUBSCRIPTION_DEFAULT));
    setPlanModalOpen(true);
  }

  function openNewSubscriptionPlan() {
    setSelectedPlanId(null);
    setPlanForm(SUBSCRIPTION_DEFAULT);
    setPlanModalOpen(true);
  }

  function openEditCreditPlan(plan) {
    setSelectedCreditPlanId(plan.credit_plan_id);
    setCreditForm(normalizeForm(plan, CREDIT_DEFAULT));
    setCreditModalOpen(true);
  }

  function openNewCreditPlan() {
    setSelectedCreditPlanId(null);
    setCreditForm(CREDIT_DEFAULT);
    setCreditModalOpen(true);
  }

  function updatePlanForm(field, value) {
    setPlanForm((prev) => ({ ...prev, [field]: value }));
  }

  function updateCreditForm(field, value) {
    setCreditForm((prev) => ({ ...prev, [field]: value }));
  }

  async function saveSubscriptionPlan() {
    try {
      setSaveMessage("");
      const payload = buildPayload(planForm, SUBSCRIPTION_NUMBER_FIELDS);

      if (payload.status === "active") {
        const activeRes = await getAdminPlans({ status: "active" });
        const activeCount = (activeRes.data || []).length;
        const isCurrentlyActive =
          selectedPlanId &&
          plans.find((p) => p.plan_id === selectedPlanId)?.status === "active";

        if (!isCurrentlyActive && activeCount >= 4) {
          alert("활성화된 구독 플랜 카드는 최대 4개까지만 등록할 수 있습니다.");
          return;
        }
      }

      if (selectedPlanId) {
        await updateAdminPlan(selectedPlanId, payload);
        setSaveMessage("구독 플랜을 수정했습니다.");
      } else {
        await createAdminPlan(payload);
        setSaveMessage("구독 플랜을 추가했습니다.");
      }
      setPlanModalOpen(false);
      await loadSubscriptionPlans();
    } catch (error) {
      console.error("Failed to save subscription plan", error);
      setSaveMessage("구독 플랜 저장에 실패했습니다.");
    }
  }

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

      if (selectedCreditPlanId) {
        await updateAdminCreditPlan(selectedCreditPlanId, payload);
        setSaveMessage("크레딧 플랜을 수정했습니다.");
      } else {
        await createAdminCreditPlan(payload);
        setSaveMessage("크레딧 플랜을 추가했습니다.");
      }
      setCreditModalOpen(false);
      await loadCreditPlans();
    } catch (error) {
      console.error("Failed to save credit plan", error);
      setSaveMessage("크레딧 플랜 저장에 실패했습니다.");
    }
  }

  async function removeSubscriptionPlan(plan) {
    if (!window.confirm(`${plan.plan_name} 플랜을 삭제 처리할까요?`)) return;
    try {
      await deleteAdminPlan(plan.plan_id);
      setSaveMessage("구독 플랜을 삭제 처리했습니다.");
      setSelectedPlanId(null);
      await loadSubscriptionPlans();
    } catch (error) {
      console.error("Failed to delete subscription plan", error);
      setSaveMessage("구독 플랜 삭제 처리에 실패했습니다.");
    }
  }

  async function removeCreditPlan(plan) {
    if (!window.confirm(`${plan.credit_plan_name} 플랜을 삭제 처리할까요?`)) {
      return;
    }
    try {
      await deleteAdminCreditPlan(plan.credit_plan_id);
      setSaveMessage("크레딧 플랜을 삭제 처리했습니다.");
      setSelectedCreditPlanId(null);
      await loadCreditPlans();
    } catch (error) {
      console.error("Failed to delete credit plan", error);
      setSaveMessage("크레딧 플랜 삭제 처리에 실패했습니다.");
    }
  }

  return (
    <GarimPage bodyClass="" screenLabel="30 Admin policy">
      <div className="adm-shell">
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring">
            <span className="material-icons">monitor_heart</span>
            사용자 모니터링
          </a>
          <a href="/admin/queue">
            <span className="material-icons">queue</span>
            처리 큐
          </a>
          <a href="/admin/compliance">
            <span className="material-icons">verified_user</span>
            컴플라이언스
          </a>
          <div className="sec">시스템</div>
          <a href="/admin/users">
            <span className="material-icons">people</span>
            사용자
          </a>
          <a href="/admin/analytics">
            <span className="material-icons">analytics</span>
            분석
          </a>
          <a href="/admin/policy" className="active">
            <span className="material-icons">tune</span>
            정책 및 상품 관리
          </a>
          <a href="/admin/subscriptions">
            <span className="material-icons">subscriptions</span>
            구독 관리
          </a>
          <a href="/admin/payments">
            <span className="material-icons">payments</span>
            사용자 결제 확인
          </a>
                  <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>

        <main className="adm-main pol-adm-main">
          <div className="pol-content pol-content--wide">
            <div className="pol-page-head">
              <div>
                <h1>정책 및 상품 관리</h1>
                <p>
                  구독 플랜과 크레딧 플랜의 정책을 설정하고 관리할 수 있습니다.
                </p>
              </div>
            </div>


            <div className="pol-tabs" role="tablist">
              <button
                type="button"
                className={`pol-tab ${activeTab === "subscription" ? "active" : ""}`}
                onClick={() => setActiveTab("subscription")}
              >
                <span className="material-icons">credit_card</span>
                구독 플랜
              </button>
              <button
                type="button"
                className={`pol-tab ${activeTab === "credit" ? "active" : ""}`}
                onClick={() => setActiveTab("credit")}
              >
                <span className="material-icons">toll</span>
                크레딧 플랜
              </button>
            </div>


            {saveMessage && (
              <div className="mui-alert mui-alert--info pol-message">
                {saveMessage}
              </div>
            )}

            {activeTab === "subscription" ? (
              <section className="pol-manager pol-manager--list-only">
                <div className="pol-list-panel">
                  <div className="pol-card-head">
                    <div>
                      <h2>구독 플랜</h2>
                      <p>pricing 페이지에 표시될 구독 상품 정책입니다.</p>
                    </div>
                    <div className="pol-card-controls">
                      <div className="pol-card-title-tools">
                        <select
                          className="pol-limit-select"
                          value={subscriptionLimit}
                          onChange={(e) => {
                            setSubscriptionLimit(Number(e.target.value));
                            setSubscriptionPage(1);
                          }}
                        >
                          {PAGE_LIMIT_OPTIONS.map((limit) => (
                            <option value={limit} key={limit}>{limit}</option>
                          ))}
                        </select>
                        <span className="pol-limit-label">개씩 보기</span>
                      </div>

                      <div className="pol-toolbar">
                        <div className="pol-toolbar-actions">
                          <button
                            type="button"
                            className="mui-btn mui-btn--contained pol-add-btn"
                            onClick={openNewSubscriptionPlan}
                          >
                            <span className="material-icons">add</span>
                            구독 플랜 추가
                          </button>
                          <select
                            className="pol-status-select"
                            value={planStatus}
                            onChange={(e) => {
                              setPlanStatus(e.target.value);
                              setSubscriptionPage(1);
                            }}
                          >
                            <option value="all">전체</option>
                            <option value="active">사용중</option>
                            <option value="inactive">미사용</option>
                            <option value="deleted">삭제</option>
                          </select>
                          <div className="pol-search">
                            <span className="material-icons">search</span>
                            <input
                              type="search"
                              value={planSearch}
                              onChange={(e) => setPlanSearch(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  setSubscriptionPage(1);
                                  loadSubscriptionPlans(planSearch, planStatus, 1, subscriptionLimit);
                                }
                              }}
                              placeholder="코드, 이름, 상태 검색"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="pol-data-table pol-data-table--subscription">
                    <div className="pol-data-row pol-data-head">
                      <span>플랜명</span>
                      <span>상태</span>
                      <span>월 결제 금액</span>
                      <span>월 제공 크레딧</span>
                      <span>최대 파일 크기</span>
                      <span>결과 보존 기간</span>
                      <span>작업</span>
                    </div>
                    {plans.map((plan) => (
                      <div
                        className="pol-data-row"
                        key={plan.plan_id}
                      >
                        <span className="pol-name-cell">
                          <span className="pol-name-row">
                            <strong>{plan.plan_name}</strong>
                            {plan.badge_label && (
                              <span className={`pol-badge ${plan.badge_class || "mui-chip--primary"}`}>
                                {plan.badge_label}
                              </span>
                            )}
                          </span>
                          <small>{plan.plan_code}</small>
                        </span>
                        <span>
                          <span className={`pol-status ${plan.status}`}>
                            {statusLabel(plan.status)}
                          </span>
                        </span>
                        <span className="pol-price-cell">
                          ₩{formatMoney(plan.price_amount)}
                          {Number(plan.price_amount) > 0 && (
                            <small className="pol-subprice">
                              연 ₩{formatMoney(Number(plan.price_amount) * 10)} (2개월 무료)
                            </small>
                          )}
                        </span>
                        <span>{formatMoney(plan.credits)} 크레딧</span>
                        <span>{formatMoney(plan.file_size_limit)}MB</span>
                        <span>{plan.result_retention_days ?? "-"}일</span>
                        <span className="pol-row-actions">
                          <button
                            type="button"
                            className="pol-icon-btn pol-icon-btn--edit"
                            title="수정"
                            onClick={(e) => {
                              e.stopPropagation();
                              openEditSubscriptionPlan(plan);
                            }}
                          >
                            <span className="material-icons">edit</span>
                          </button>
                          <button
                            type="button"
                            className="pol-icon-btn pol-icon-btn--delete"
                            title="삭제"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeSubscriptionPlan(plan);
                            }}
                          >
                            <span className="material-icons">delete</span>
                          </button>
                        </span>
                      </div>
                    ))}
                    {!plans.length && (
                      <div className="pol-empty">
                        {isLoading ? "불러오는 중입니다." : "플랜이 없습니다."}
                      </div>
                    )}
                  </div>
                  <PlanPagination
                    page={subscriptionPage}
                    limit={subscriptionLimit}
                    total={subscriptionTotal}
                    onPageChange={setSubscriptionPage}
                  />
                </div>
              </section>
            ) : (
              <section className="pol-manager pol-manager--list-only">
                <div className="pol-list-panel">
                  <div className="pol-card-head">
                    <div>
                      <h2>크레딧 플랜</h2>
                      <p>
                        일회성 크레딧 충전 상품을 구독 플랜과 별도로 관리합니다.
                      </p>
                    </div>
                    <div className="pol-card-controls">
                      <div className="pol-card-title-tools">
                        <select
                          className="pol-limit-select"
                          value={creditLimit}
                          onChange={(e) => {
                            setCreditLimit(Number(e.target.value));
                            setCreditPage(1);
                          }}
                        >
                          {PAGE_LIMIT_OPTIONS.map((limit) => (
                            <option value={limit} key={limit}>{limit}</option>
                          ))}
                        </select>
                        <span className="pol-limit-label">개씩 보기</span>
                      </div>

                      <div className="pol-toolbar">
                        <div className="pol-toolbar-actions">
                          <button
                            type="button"
                            className="mui-btn mui-btn--contained pol-add-btn"
                            onClick={openNewCreditPlan}
                          >
                            <span className="material-icons">add</span>
                            크레딧 플랜 추가
                          </button>
                          <select
                            className="pol-status-select"
                            value={creditStatus}
                            onChange={(e) => {
                              setCreditStatus(e.target.value);
                              setCreditPage(1);
                            }}
                          >
                            <option value="all">전체</option>
                            <option value="active">사용중</option>
                            <option value="inactive">미사용</option>
                            <option value="deleted">삭제</option>
                          </select>
                          <div className="pol-search">
                            <span className="material-icons">search</span>
                            <input
                              type="search"
                              value={creditSearch}
                              onChange={(e) => setCreditSearch(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  setCreditPage(1);
                                  loadCreditPlans(creditSearch, creditStatus, 1, creditLimit);
                                }
                              }}
                              placeholder="코드, 이름, 상태 검색"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="pol-data-table pol-data-table--credit">
                    <div className="pol-data-row pol-data-head">
                      <span>플랜명</span>
                      <span>상태</span>
                      <span>결제 방식</span>
                      <span>결제 금액</span>
                      <span>제공 크레딧</span>
                      <span>보너스 크레딧</span>
                      <span>유효 기간</span>
                      <span>작업</span>
                    </div>
                    {creditPlans.map((plan) => (
                      <div
                        className="pol-data-row"
                        key={plan.credit_plan_id}
                      >
                        <span className="pol-name-cell">
                          <span className="pol-name-row">
                            <strong>{plan.credit_plan_name}</strong>
                          </span>
                          <small>{plan.credit_plan_code}</small>
                        </span>
                        <span>
                          <span className={`pol-status ${plan.status}`}>
                            {statusLabel(plan.status)}
                          </span>
                        </span>
                        <span>일회성 결제</span>
                        <span>₩{formatMoney(plan.price_amount)}</span>
                        <span>{formatMoney(plan.base_credits)} 크레딧</span>
                        <span>{formatMoney(plan.bonus_credits)} 크레딧</span>
                        <span>{plan.expires_days ? `${plan.expires_days}일` : "-"}</span>
                        <span className="pol-row-actions">
                          <button
                            type="button"
                            className="pol-icon-btn pol-icon-btn--edit"
                            title="수정"
                            onClick={(e) => {
                              e.stopPropagation();
                              openEditCreditPlan(plan);
                            }}
                          >
                            <span className="material-icons">edit</span>
                          </button>
                          <button
                            type="button"
                            className="pol-icon-btn pol-icon-btn--delete"
                            title="삭제"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeCreditPlan(plan);
                            }}
                          >
                            <span className="material-icons">delete_outline</span>
                          </button>
                        </span>
                      </div>
                    ))}
                    {!creditPlans.length && (
                      <div className="pol-empty">
                        {isLoading ? "불러오는 중입니다." : "플랜이 없습니다."}
                      </div>
                    )}
                  </div>
                  <PlanPagination
                    page={creditPage}
                    limit={creditLimit}
                    total={creditTotal}
                    onPageChange={setCreditPage}
                  />
                </div>
              </section>
            )}
          </div>
        </main>
      </div>

      {/* 구독 플랜 수정/추가 모달 */}
      {planModalOpen && (
        <div className="pol-modal-backdrop" onClick={() => setPlanModalOpen(false)}>
          <div className="pol-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pol-modal-header">
              <h2>
                {selectedPlan
                  ? `${selectedPlan.plan_name} 정책 수정`
                  : "구독 플랜 추가"}
              </h2>
              <button
                type="button"
                className="pol-modal-close"
                onClick={() => setPlanModalOpen(false)}
              >
                <span className="material-icons">close</span>
              </button>
            </div>
            <div className="pol-modal-body">
              <div className="pol-modal-form-col">
                <PlanFormPanel
                  title={
                    selectedPlan
                      ? `${selectedPlan.plan_name} 정책`
                      : "구독 플랜 추가"
                  }
                  form={planForm}
                  onChange={updatePlanForm}
                  onSave={saveSubscriptionPlan}
                  onReset={() => setPlanForm(SUBSCRIPTION_DEFAULT)}
                  onClose={() => setPlanModalOpen(false)}
                />
              </div>
              <div className="pol-modal-preview-col">
                <PlanPreviewPanel form={planForm} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 크레딧 플랜 수정/추가 모달 */}
      {creditModalOpen && (
        <div className="pol-modal-backdrop" onClick={() => setCreditModalOpen(false)}>
          <div className="pol-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pol-modal-header">
              <h2>
                {selectedCreditPlan
                  ? `${selectedCreditPlan.credit_plan_name} 정책 수정`
                  : "크레딧 플랜 추가"}
              </h2>
              <button
                type="button"
                className="pol-modal-close"
                onClick={() => setCreditModalOpen(false)}
              >
                <span className="material-icons">close</span>
              </button>
            </div>
            <div className="pol-modal-body">
              <div className="pol-modal-form-col">
                <CreditFormPanel
                  title={
                    selectedCreditPlan
                      ? `${selectedCreditPlan.credit_plan_name} 정책`
                      : "크레딧 플랜 추가"
                  }
                  form={creditForm}
                  onChange={updateCreditForm}
                  onSave={saveCreditPlan}
                  onReset={() => setCreditForm(CREDIT_DEFAULT)}
                  onClose={() => setCreditModalOpen(false)}
                />
              </div>
              <div className="pol-modal-preview-col">
                <CreditPreviewPanel form={creditForm} />
              </div>
            </div>
          </div>
        </div>
      )}
    </GarimPage>
  );
}

function PlanPagination({ page, limit, total, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = total === 0 ? 0 : (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);

  return (
    <div className="pol-pagination">
      <span className="meta">
        {start}-{end} / {total.toLocaleString()}
      </span>
      <div className="pol-pagination-actions">
        <button
          type="button"
          className="mui-btn mui-btn--outlined mui-btn--sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          이전
        </button>
        <button
          type="button"
          className="mui-btn mui-btn--outlined mui-btn--sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          다음
        </button>
      </div>
    </div>
  );
}

function PlanFormPanel({ title, form, onChange, onSave, onReset, onClose }) {
  return (
    <aside className="pol-edit-panel pol-edit-panel--modal">
      <div className="pol-card-head">
        <h3>{title}</h3>
      </div>
      <div className="pol-form-grid">
        <TextField
          label="플랜 코드"
          value={form.plan_code}
          onChange={(v) => onChange("plan_code", v)}
        />
        <TextField
          label="플랜명"
          value={form.plan_name}
          onChange={(v) => onChange("plan_name", v)}
        />
        <TextField
          label="배지 문구"
          value={form.badge_label}
          onChange={(v) => onChange("badge_label", v)}
        />
        <SelectField
          label="배지 스타일"
          value={form.badge_class || SUBSCRIPTION_DEFAULT.badge_class}
          onChange={(v) => onChange("badge_class", v)}
          options={BADGE_CLASS_OPTIONS}
        />
        <NumberField
          label="노출 순서"
          value={form.sort_order}
          onChange={(v) => onChange("sort_order", v)}
        />
        <SelectField
          label="관리 상태"
          value={form.status}
          onChange={(v) => onChange("status", v)}
        />
      </div>

      <FormSection title="카드 문구">
        <TextAreaField
          label="설명 문구"
          value={form.description}
          onChange={(v) => onChange("description", v)}
        />
      </FormSection>

      <FormSection title="파일 처리 정책">
        <NumberField
          label="최대 파일 크기(MB)"
          value={form.file_size_limit}
          onChange={(v) => onChange("file_size_limit", v)}
        />
        <NumberField
          label="동시 처리 수"
          value={form.max_jobs}
          onChange={(v) => onChange("max_jobs", v)}
        />
        <NumberField
          label="월 처리 한도"
          value={form.monthly_quota}
          onChange={(v) => onChange("monthly_quota", v)}
        />
        <ToggleField
          label="워터마크 필수"
          checked={form.watermark_required}
          onChange={(v) => onChange("watermark_required", v)}
        />
      </FormSection>

      <FormSection title="결제 정책">
        <NumberField
          label="월 결제 금액"
          value={form.price_amount}
          onChange={(v) => onChange("price_amount", v)}
        />
        <NumberField
          label="제공 크레딧"
          value={form.credits}
          onChange={(v) => onChange("credits", v)}
        />
      </FormSection>

      <FormSection title="데이터 보존 정책">
        <NumberField
          label="결과 보존 일수"
          value={form.result_retention_days}
          onChange={(v) => onChange("result_retention_days", v)}
        />
        <NumberField
          label="원본 자동 삭제 시간"
          value={form.auto_delete_original_hours}
          onChange={(v) => onChange("auto_delete_original_hours", v)}
        />
        <NumberField
          label="메타데이터 보존 일수"
          value={form.metadata_retention_days}
          onChange={(v) => onChange("metadata_retention_days", v)}
        />
      </FormSection>

      <div className="pol-save-bar">
        <button
          type="button"
          className="mui-btn mui-btn--outlined"
          onClick={onReset}
        >
          초기화
        </button>
        <button
          type="button"
          className="mui-btn mui-btn--contained"
          onClick={onSave}
        >
          저장
        </button>
      </div>
              <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
  );
}

function CreditFormPanel({ title, form, onChange, onSave, onReset, onClose }) {
  return (
    <aside className="pol-edit-panel pol-edit-panel--credit pol-edit-panel--modal">
      <div className="pol-card-head">
        <h3>{title}</h3>
      </div>
      <div className="pol-form-grid">
        <TextField
          label="상품 코드"
          value={form.credit_plan_code}
          onChange={(v) => onChange("credit_plan_code", v)}
        />
        <TextField
          label="상품명"
          value={form.credit_plan_name}
          onChange={(v) => onChange("credit_plan_name", v)}
        />
        <NumberField
          label="노출 순서"
          value={form.sort_order}
          onChange={(v) => onChange("sort_order", v)}
        />
        <SelectField
          label="관리 상태"
          value={form.status}
          onChange={(v) => onChange("status", v)}
        />
      </div>

      <FormSection title="크레딧 상품 정책">
        <NumberField
          label="결제 금액"
          value={form.price_amount}
          onChange={(v) => onChange("price_amount", v)}
        />
        <NumberField
          label="기본 크레딧"
          value={form.base_credits}
          onChange={(v) => onChange("base_credits", v)}
        />
        <NumberField
          label="보너스 크레딧"
          value={form.bonus_credits}
          onChange={(v) => onChange("bonus_credits", v)}
        />
        <NumberField
          label="유효 기간"
          value={form.expires_days}
          onChange={(v) => onChange("expires_days", v)}
        />
      </FormSection>

      <div className="pol-save-bar">
        <button
          type="button"
          className="mui-btn mui-btn--outlined"
          onClick={onReset}
        >
          초기화
        </button>
        <button
          type="button"
          className="mui-btn mui-btn--contained"
          onClick={onSave}
        >
          저장
        </button>
      </div>
              <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
  );
}

function PlanPreviewPanel({ form }) {
  const badgeClass = form.badge_class || "mui-chip--primary";
  const badgeLabel = form.badge_label || "플랜";
  const planName = form.plan_name || "플랜명";
  const description =
    form.description || "pricing 페이지에 표시될 플랜 설명입니다.";
  // 버튼 문구는 price_amount 기준 고정 분기값 사용 (cta_label 제거)
  const ctaLabel = Number(form.price_amount || 0) === 0 ? "무료로 시작" : "결제하기";

  return (
    <aside className="pol-preview-panel pol-preview-panel--modal">
      <div className="pol-card-head">
        <h3>플랜 미리보기</h3>
      </div>
      <div className="pol-preview-body">
        <div className="pol-price-preview">
          <span className={`mui-chip ${badgeClass} price-card__badge`}>
            {badgeLabel}
          </span>
          <span className="overline-k">{planName}</span>
          <div className="price-card__price">
            {formatMoney(form.price_amount)}
            <small>원 / 월</small>
          </div>
          {/* 연 결제 파생 금액 — 월 × 10 (2개월 무료), pricing 페이지와 동일 공식 */}
          {Number(form.price_amount || 0) > 0 && (
            <div className="pol-preview-yearly">
              연 결제 {formatMoney(Number(form.price_amount) * 10)}원
              <span> (2개월 무료 · 월 {formatMoney(Math.round(Number(form.price_amount) * 10 / 12))}원 상당)</span>
            </div>
          )}
          <p className="caption-k">{description}</p>
          <ul className="price-card__feats">
            <li>
              <span className="material-icons">check</span>크레딧{" "}
              {formatMoney(form.credits)}개
            </li>
            <li>
              <span className="material-icons">check</span>월 처리 한도{" "}
              {form.monthly_quota || "무제한"}건
            </li>
            <li>
              <span className="material-icons">check</span>최대 파일 크기{" "}
              {formatMoney(form.file_size_limit)}MB
            </li>
            <li>
              <span className="material-icons">check</span>결과 파일{" "}
              {form.result_retention_days || 0}일 보관
            </li>
          </ul>
          <button
            type="button"
            className="mui-btn mui-btn--contained mui-btn--block"
          >
            {ctaLabel}
          </button>
        </div>
      </div>
              <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
  );
}

function CreditPreviewPanel({ form }) {
  const name = form.credit_plan_name || "크레딧 플랜";
  const baseCredits = Number(form.base_credits || 0);
  const bonusCredits = Number(form.bonus_credits || 0);
  const totalCredits = baseCredits + bonusCredits;

  return (
    <aside className="pol-preview-panel pol-preview-panel--credit pol-preview-panel--modal">
      <div className="pol-card-head">
        <h3>플랜 미리보기</h3>
      </div>
      <div className="pol-preview-body">
        <div className="pol-credit-preview">
          <div className="pol-credit-preview__title">
            <span className="material-icons">toll</span>
            <h3>{name}</h3>
          </div>
          <div className="pol-credit-preview__price">
            {formatMoney(form.price_amount)}
            <small>원</small>
          </div>
          <p>
            크레딧 {formatMoney(totalCredits)}개 충전
            {bonusCredits
              ? ` (보너스 ${formatMoney(bonusCredits)}개 포함)`
              : ""}
          </p>
          <button
            type="button"
            className="mui-btn mui-btn--contained mui-btn--block"
          >
            충전하기
          </button>
        </div>
      </div>
              <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
  );
}

function FormSection({ title, children }) {
  return (
    <section className="pol-form-section">
      <h4>{title}</h4>
      <div className="pol-form-grid">{children}</div>
    </section>
  );
}

function TextField({ label, value, onChange }) {
  return (
    <label className="pol-field">
      <span>{label}</span>
      <input
        type="text"
        className="pol-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function TextAreaField({ label, value, onChange }) {
  return (
    <label className="pol-field pol-field--full">
      <span>{label}</span>
      <textarea
        className="pol-input pol-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function NumberField({ label, value, onChange }) {
  return (
    <label className="pol-field">
      <span>{label}</span>
      <input
        type="number"
        className="pol-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function SelectField({ label, value, onChange, options = STATUS_OPTIONS }) {
  return (
    <label className="pol-field">
      <span>{label}</span>
      <select
        className="pol-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((option) => {
          let labelText = option;
          if (option === "active") labelText = "사용중";
          if (option === "inactive") labelText = "미사용";
          if (option === "deleted") labelText = "삭제";
          return (
            <option value={option} key={option}>
              {labelText}
            </option>
          );
        })}
      </select>
    </label>
  );
}

function ToggleField({ label, checked, onChange }) {
  return (
    <label className="pol-switch-wrap pol-switch-wrap--field">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}
