import { useEffect, useMemo, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/AdminSubscriptions.css";
import GarimPage from "../../components/garim/GarimPage";
import {
  cancelAdminSubscription,
  getAdminSubscriptionDetail,
  getAdminSubscriptions,
} from "../../utils/api";

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function mapStatusLabel(value) {
  switch (value) {
    case "active":
      return "활성";
    case "free":
      return "Free";
    case "failed":
      return "실패";
    case "billing_key_missing":
      return "키 없음";
    case "scheduled":
      return "예약";
    case "success":
      return "성공";
    case "cancelled":
      return "취소";
    case "applied":
      return "적용";
    case "downgrade":
      return "다운그레이드";
    case "cancel_to_free":
      return "Free 변경";
    case "renewal":
      return "자동결제";
    case "scheduled_downgrade":
      return "예약 다운그레이드";
    case "retry_scheduled":
      return "재시도 예약";
    default:
      return value || "-";
  }
}

function boolLabel(value) {
  return value ? "Y" : "N";
}

function statusChipClass(value) {
  if (value === "failed" || value === "billing_key_missing") return "mui-chip--soft-error";
  if (value === "scheduled" || value === "downgrade" || value === "cancel_to_free") return "mui-chip--soft-warning";
  if (value === "success" || value === "active" || value === "applied") return "mui-chip--soft-success";
  return "mui-chip--soft-primary";
}

function getPlanTone(planCode) {
  if (planCode === "studio") return "sb-plan-badge studio";
  if (planCode === "pro") return "sb-plan-badge pro";
  return "sb-plan-badge free";
}

export default function AdminSubscriptions() {
  useDocumentTitle("구독 관리 · Garim Admin");

  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({
    total_users: 0,
    paid_users: 0,
    billing_failed_users: 0,
    scheduled_change_users: 0,
  });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(10);

  const [searchKey, setSearchKey] = useState("email");
  const [searchValue, setSearchValue] = useState("");
  const [planCode, setPlanCode] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] = useState("");
  const [autoRenew, setAutoRenew] = useState("");
  const [cancelScheduled, setCancelScheduled] = useState("");
  const [billingFailed, setBillingFailed] = useState("");
  const [scheduledChange, setScheduledChange] = useState("");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [queryVersion, setQueryVersion] = useState(0);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailData, setDetailData] = useState(null);

  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelLoading, setCancelLoading] = useState(false);

  useEffect(() => {
    let ignore = false;

    setIsLoading(true);
    setError("");

    getAdminSubscriptions({
      page,
      limit,
      q: searchValue || undefined,
      search_key: searchKey,
      plan_code: planCode || undefined,
      subscription_status: subscriptionStatus || undefined,
      auto_renew: autoRenew,
      cancel_scheduled: cancelScheduled,
      billing_failed: billingFailed,
      scheduled_change: scheduledChange,
    })
      .then((res) => {
        if (ignore) return;
        setRows(res.data || []);
        setSummary(
          res.summary || {
            total_users: 0,
            paid_users: 0,
            billing_failed_users: 0,
            scheduled_change_users: 0,
          },
        );
        setTotal(res.total || 0);
      })
      .catch((err) => {
        if (!ignore) {
          setError(err.message || "구독 목록을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (!ignore) setIsLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [page, limit, queryVersion]);

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const pageMeta = useMemo(() => {
    if (!total) return "0건";
    const start = (page - 1) * limit + 1;
    const end = Math.min(page * limit, total);
    return `${start}-${end} / ${total.toLocaleString()}`;
  }, [page, limit, total]);

  const handleSearch = (event) => {
    if (event) event.preventDefault();
    if (page === 1) {
      setQueryVersion((value) => value + 1);
    } else {
      setPage(1);
    }
  };

  const handleReset = () => {
    setSearchKey("email");
    setSearchValue("");
    setPlanCode("");
    setSubscriptionStatus("");
    setAutoRenew("");
    setCancelScheduled("");
    setBillingFailed("");
    setScheduledChange("");
    setShowAdvancedFilters(false);
    setLimit(10);
    setPage(1);
    setQueryVersion((value) => value + 1);
  };

  const handleOpenDetail = async (userId) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError("");
    setDetailData(null);

    try {
      const res = await getAdminSubscriptionDetail(userId);
      setDetailData(res.data);
    } catch (err) {
      setDetailError(err.message || "상세 정보를 불러오지 못했습니다.");
    } finally {
      setDetailLoading(false);
    }
  };

  /* 구독 강제 취소 — 취소 사유 입력 모달 열기 */
  const handleCancelSubscriptionClick = (subscription) => {
    const userEmail = detailData?.user?.email || "해당 사용자";

    // ── 구독 취소 경고 조건 체크 ──
    const warnings = [];

    // 조건 1: 최근 결제일 기준 14일 경과
    if (subscription.days_since_last_payment != null && subscription.days_since_last_payment >= 14) {
      warnings.push(`[${userEmail}] 사용자는 결제일 기준 14일이 지난 사용자입니다.`);
    }
    // 조건 2: 플랜 크레딧의 15% 이상 사용
    if (subscription.plan_credits > 0 && subscription.credit_used_ratio >= 15) {
      warnings.push(`[${userEmail}] 사용자는 충전 크레딧의 15% 이상 사용한 사용자입니다.`);
    }
    if (warnings.length > 0) {
      alert(`⚠️ 구독 취소 주의 사항\n\n${warnings.join("\n\n")}`);
    }

    setCancelTarget(subscription);
    setCancelReason("");
    setCancelConfirmOpen(true);
  };

  /* 모달에서 실제 취소 API 호출 */
  const handleConfirmCancel = async () => {
    if (!cancelTarget || !detailData) return;
    const reason = cancelReason.trim();
    if (!reason) {
      alert("취소 사유를 입력해주세요.");
      return;
    }
    if (reason.length > 30) {
      alert("취소 사유는 30글자 이내로 입력해주세요.");
      return;
    }

    setCancelLoading(true);
    try {
      const userId = detailData.user.user_id;
      const res = await cancelAdminSubscription(userId, cancelTarget.subscription_id, reason);
      const restored = res?.data?.restored_plan || "Free";
      alert(`구독이 취소되었습니다.\n복원된 플랜: ${restored}`);

      setCancelConfirmOpen(false);
      setCancelTarget(null);

      /* 상세 모달 새로고침 */
      const detail = await getAdminSubscriptionDetail(userId);
      setDetailData(detail.data);

      /* 목록 새로고침 */
      setQueryVersion((v) => v + 1);
    } catch (err) {
      alert("구독 취소 중 오류가 발생했습니다: " + (err.message || "알 수 없는 오류"));
    } finally {
      setCancelLoading(false);
    }
  };

  return (
    <GarimPage bodyClass="" screenLabel="31 Admin Subscriptions">
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
          <div className="sec">서비스</div>
          <a href="/admin/users">
            <span className="material-icons">people</span>
            사용자
          </a>
          <a href="/admin/analytics">
            <span className="material-icons">analytics</span>
            분석
          </a>
          <a href="/admin/policy">
            <span className="material-icons">tune</span>
            정책 및 상품 관리
          </a>
          <a href="/admin/subscriptions" className="active">
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

        <main className="adm-main sb-main">
          <div className="sb-head">
            <div>
              <h1>구독 관리</h1>
              <p>현재 적용 플랜, 자동결제 상태, 예약 변경, 결제 실패 이력을 운영 화면에서 빠르게 조회합니다.</p>
            </div>
          </div>

          <div className="sb-metric-row">
            <div className="sb-metric">
              <div className="lbl">전체 사용자</div>
              <div className="num">{summary.total_users.toLocaleString()}</div>
              <div className="delta">조회 조건 기준 사용자 수</div>
            </div>
            <div className="sb-metric ok">
              <div className="lbl">유료 구독 사용자</div>
              <div className="num">{summary.paid_users.toLocaleString()}</div>
              <div className="delta">현재 유료 플랜 적용 대상</div>
            </div>
            <div className="sb-metric err">
              <div className="lbl">결제 실패 상태</div>
              <div className="num">{summary.billing_failed_users.toLocaleString()}</div>
              <div className="delta">실패 또는 billing key 없음</div>
            </div>
            <div className="sb-metric info">
              <div className="lbl">예약 변경 사용자</div>
              <div className="num">{summary.scheduled_change_users.toLocaleString()}</div>
              <div className="delta">다운그레이드 또는 Free 변경 예약</div>
            </div>
          </div>

          <div className="sb-card">
            <div className="sb-card-head">
              <div>
                <h2>구독 상태 목록</h2>
                <p>조회 전용 화면입니다. 강제 취소, 강제 변경 같은 관리 액션은 이번 화면에 포함하지 않았습니다.</p>
              </div>
            </div>

            <form className="sb-toolbar" onSubmit={handleSearch}>
              <div className="sb-toolbar-grid">
                <div className="sb-toolbar-tools sb-toolbar-tools--left">
                  <select
                    className="sb-limit-select"
                    value={limit}
                    onChange={(e) => {
                      setLimit(Number(e.target.value));
                      setPage(1);
                    }}
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={50}>50</option>
                  </select>
                  <span className="sb-limit-label">개씩 보기</span>
                </div>

                <div className="sb-filter-group sb-primary-slot-plan">
                  <label>현재 플랜</label>
                  <select value={planCode} onChange={(e) => setPlanCode(e.target.value)}>
                    <option value="">현재 플랜: 전체</option>
                    <option value="free">Free</option>
                    <option value="pro">Pro</option>
                    <option value="studio">Studio</option>
                  </select>
                </div>

                <div className="sb-filter-group sb-primary-slot-failed">
                  <label>결제 실패</label>
                  <select value={billingFailed} onChange={(e) => setBillingFailed(e.target.value)}>
                    <option value="">결제 실패: 전체</option>
                    <option value="true">실패만</option>
                    <option value="false">정상만</option>
                  </select>
                </div>

                <div className="sb-filter-group sb-primary-slot-scheduled-change">
                  <label>예약 변경</label>
                  <select value={scheduledChange} onChange={(e) => setScheduledChange(e.target.value)}>
                    <option value="">예약 변경: 전체</option>
                    <option value="true">예약 있음</option>
                    <option value="false">예약 없음</option>
                  </select>
                </div>

                <button
                  type="button"
                  className={`sb-advanced-toggle ${showAdvancedFilters ? "active" : ""}`}
                  onClick={() => setShowAdvancedFilters((value) => !value)}
                >
                  <span className="material-icons">
                    {showAdvancedFilters ? "expand_less" : "tune"}
                  </span>
                  고급 필터
                </button>

                <div className="sb-filter-group sb-search-group">
                  <label>검색</label>
                  <div className="sb-search-input-wrap">
                    <select value={searchKey} onChange={(e) => setSearchKey(e.target.value)}>
                      <option value="email">이메일</option>
                      <option value="user_id">사용자 ID</option>
                      <option value="all">전체 검색</option>
                    </select>
                    <input
                      type="search"
                      value={searchValue}
                      onChange={(e) => setSearchValue(e.target.value)}
                      placeholder="사용자 검색"
                    />
                  </div>
                </div>

                <div className="sb-toolbar-actions">
                  <button type="submit" className="mui-btn mui-btn--contained sb-btn-search">
                    <span className="material-icons">search</span>
                    조회
                  </button>
                  <button type="button" className="mui-btn mui-btn--outlined" onClick={handleReset}>
                    초기화
                  </button>
                </div>

                {showAdvancedFilters && (
                  <>
                    <div className="sb-filter-group sb-advanced-slot-plan">
                      <label>구독 상태</label>
                      <select value={subscriptionStatus} onChange={(e) => setSubscriptionStatus(e.target.value)}>
                        <option value="">구독 상태: 전체</option>
                        <option value="free">Free</option>
                        <option value="active">활성</option>
                      </select>
                    </div>

                    <div className="sb-filter-group sb-advanced-slot-billing">
                      <label>자동결제</label>
                      <select value={autoRenew} onChange={(e) => setAutoRenew(e.target.value)}>
                        <option value="">자동결제: 전체</option>
                        <option value="true">Y</option>
                        <option value="false">N</option>
                      </select>
                    </div>

                    <div className="sb-filter-group sb-advanced-slot-scheduled">
                      <label>취소 예약</label>
                      <select value={cancelScheduled} onChange={(e) => setCancelScheduled(e.target.value)}>
                        <option value="">취소 예약: 전체</option>
                        <option value="true">예약 있음</option>
                        <option value="false">예약 없음</option>
                      </select>
                    </div>
                  </>
                )}
              </div>
            </form>

            <div className="sb-data-table">
              <div className="sb-data-row sb-data-head">
                <span>사용자</span>
                <span>현재 플랜</span>
                <span>구독 상태</span>
                <span>자동결제</span>
                <span>다음 결제일</span>
                <span>결제 상태</span>
                <span>예약 변경</span>
                <span>관리</span>
              </div>

              {isLoading && <div className="sb-empty">불러오는 중입니다.</div>}
              {!isLoading && error && <div className="sb-empty sb-empty-error">{error}</div>}
              {!isLoading && !error && rows.length === 0 && (
                <div className="sb-empty">조건에 맞는 사용자가 없습니다.</div>
              )}

              {!isLoading && !error && rows.map((row) => (
                <div className="sb-data-row" key={row.user_id}>
                  <span className="sb-user-cell">
                    <strong>{row.email}</strong>
                    <small className="mono">{row.user_id}</small>
                  </span>

                  <span className="sb-plan-cell">
                    <span className={getPlanTone(row.current_plan_code)}>
                      {row.current_plan_name}
                    </span>
                    {row.carried_over_subscription && (
                      <small className="sb-subtext">
                        이월: {row.carried_over_subscription.plan_name} {row.carried_over_subscription.carried_over_days}일
                      </small>
                    )}
                  </span>

                  <span className="sb-state-cell">
                    <span className="mui-chip">{mapStatusLabel(row.current_subscription?.status)}</span>
                    <small className="sb-subtext">active {row.active_subscription_count}건</small>
                  </span>

                  <span>{boolLabel(row.current_subscription?.auto_renew)}</span>
                  <span className="mono">{formatDateTime(row.current_subscription?.next_billing_at)}</span>

                  <span className="sb-status-cell">
                    <span className={`mui-chip ${statusChipClass(row.current_subscription?.billing_status)}`}>
                      {mapStatusLabel(row.current_subscription?.billing_status)}
                    </span>
                    {row.latest_billing_attempt?.failure_reason && (
                      <small className="sb-subtext">{row.latest_billing_attempt.failure_reason}</small>
                    )}
                  </span>

                  <span className="sb-scheduled-cell">
                    {row.scheduled_plan_change ? (
                      <>
                        <span className={`mui-chip ${statusChipClass(row.scheduled_plan_change.change_type)}`}>
                          {mapStatusLabel(row.scheduled_plan_change.change_type)}
                        </span>
                        <small className="sb-subtext">
                          {row.scheduled_plan_change.to_plan_name || "-"} · {formatDateTime(row.scheduled_plan_change.effective_at)}
                        </small>
                      </>
                    ) : (
                      <span className="sb-dash">-</span>
                    )}
                  </span>

                  <span className="sb-action-cell">
                    <button
                      type="button"
                      className="mui-btn mui-btn--outlined mui-btn--sm"
                      onClick={() => handleOpenDetail(row.user_id)}
                    >
                      상세
                    </button>
                  </span>
                </div>
              ))}
            </div>

            <div className="sb-pagination">
              <span className="meta">{pageMeta}</span>
              <div className="sb-pagination-actions">
                <button
                  type="button"
                  className="mui-btn mui-btn--outlined mui-btn--sm"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => value - 1)}
                >
                  이전
                </button>
                <button
                  type="button"
                  className="mui-btn mui-btn--outlined mui-btn--sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((value) => value + 1)}
                >
                  다음
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>

      {detailOpen && (
        <div className="sb-modal-backdrop" onClick={() => setDetailOpen(false)}>
          <div className="sb-modal" onClick={(event) => event.stopPropagation()}>
            <div className="sb-modal-head">
              <div>
                <h2>구독 상세</h2>
                <p>{detailData?.user?.email || "사용자 구독 상세"}</p>
              </div>
              <button
                type="button"
                className="sb-icon-btn"
                onClick={() => setDetailOpen(false)}
                aria-label="닫기"
              >
                <span className="material-icons">close</span>
              </button>
            </div>

            {detailLoading && <div className="sb-empty">상세 정보를 불러오는 중입니다.</div>}
            {!detailLoading && detailError && <div className="sb-empty sb-empty-error">{detailError}</div>}

            {!detailLoading && !detailError && detailData && (
              <div className="sb-detail-body">
                <section className="sb-detail-summary">
                  <div className="sb-detail-summary-card">
                    <span className="sb-detail-label">현재 적용 플랜</span>
                    <strong>{detailData.current_applied_plan?.plan_name || "-"}</strong>
                    <small className="mono">{detailData.current_applied_plan?.subscription_id || "-"}</small>
                  </div>
                  <div className="sb-detail-summary-card">
                    <span className="sb-detail-label">다음 결제일</span>
                    <strong>{formatDateTime(detailData.current_applied_plan?.next_billing_at)}</strong>
                    <small>period end {formatDateTime(detailData.current_applied_plan?.current_period_end)}</small>
                  </div>
                  <div className="sb-detail-summary-card">
                    <span className="sb-detail-label">자동결제 / 취소예약</span>
                    <strong>{boolLabel(detailData.current_applied_plan?.auto_renew)} / {boolLabel(detailData.current_applied_plan?.cancel_at_period_end)}</strong>
                    <small>billing {mapStatusLabel(detailData.current_applied_plan?.billing_status)}</small>
                  </div>
                  <div className="sb-detail-summary-card">
                    <span className="sb-detail-label">이월 기간</span>
                    <strong>{detailData.current_applied_plan?.carried_over_days ?? 0}일</strong>
                    <small>superseded {detailData.current_applied_plan?.superseded_by_subscription_id || "-"}</small>
                  </div>
                </section>

                <section className="sb-detail-section">
                  <div className="sb-section-head">
                    <h3>활성 구독 목록</h3>
                    <p>현재 사용자에게 유효한 active subscription 목록입니다.</p>
                  </div>
                  <div className="sb-detail-table">
                    <div className="sb-detail-row sb-detail-head sb-detail-row-subscription">
                      <span>플랜</span>
                      <span>subscription_id</span>
                      <span>period end</span>
                      <span>자동결제</span>
                      <span>carryover</span>
                      <span>superseded_by</span>
                      <span>관리</span>
                    </div>
                    {detailData.active_subscriptions.length === 0 && (
                      <div className="sb-empty">활성 구독이 없습니다.</div>
                    )}
                    {detailData.active_subscriptions.map((subscription) => (
                      <div className="sb-detail-row sb-detail-row-subscription" key={subscription.subscription_id}>
                        <span>{subscription.plan_name}</span>
                        <span className="mono">{subscription.subscription_id}</span>
                        <span className="mono">{formatDateTime(subscription.current_period_end)}</span>
                        <span>{boolLabel(subscription.auto_renew)}</span>
                        <span>{subscription.carried_over_days || 0}일</span>
                        <span className="mono">{subscription.superseded_by_subscription_id || "-"}</span>
                        <span>
                          {/* Free 플랜은 취소 불가 */}
                          {subscription.plan_code !== "free" && (
                            <button
                              type="button"
                              className="sb-cancel-sub-btn"
                              onClick={() => handleCancelSubscriptionClick(subscription)}
                            >
                              <span className="material-icons">cancel</span>
                              구독 취소
                            </button>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="sb-detail-section">
                  <div className="sb-section-head">
                    <h3>결제 시도 이력</h3>
                    <p>자동결제 및 예약 다운그레이드 결제 시도 결과입니다.</p>
                  </div>
                  <div className="sb-detail-table">
                    <div className="sb-detail-row sb-detail-head sb-detail-row-attempt">
                      <span>시도 일시</span>
                      <span>유형</span>
                      <span>상태</span>
                      <span>금액</span>
                      <span>실패 사유</span>
                    </div>
                    {detailData.billing_attempts.length === 0 && (
                      <div className="sb-empty">결제 시도 이력이 없습니다.</div>
                    )}
                    {detailData.billing_attempts.map((attempt) => (
                      <div className="sb-detail-row sb-detail-row-attempt" key={attempt.attempt_id}>
                        <span className="mono">{formatDateTime(attempt.attempted_at)}</span>
                        <span>{mapStatusLabel(attempt.attempt_type)}</span>
                        <span>
                          <span className={`mui-chip ${statusChipClass(attempt.status)}`}>
                            {mapStatusLabel(attempt.status)}
                          </span>
                        </span>
                        <span>{formatMoney(attempt.amount)}원</span>
                        <span>{attempt.failure_reason || "-"}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="sb-detail-section">
                  <div className="sb-section-head">
                    <h3>플랜 변경 이력</h3>
                    <p>업그레이드, 다운그레이드 예약, Free 변경 예약 이력입니다.</p>
                  </div>
                  <div className="sb-detail-table">
                    <div className="sb-detail-row sb-detail-head sb-detail-row-change">
                      <span>생성 일시</span>
                      <span>유형</span>
                      <span>상태</span>
                      <span>from</span>
                      <span>to</span>
                      <span>적용 시점</span>
                    </div>
                    {detailData.plan_changes.length === 0 && (
                      <div className="sb-empty">플랜 변경 이력이 없습니다.</div>
                    )}
                    {detailData.plan_changes.map((change) => (
                      <div className="sb-detail-row sb-detail-row-change" key={change.plan_change_id}>
                        <span className="mono">{formatDateTime(change.created_at)}</span>
                        <span>{mapStatusLabel(change.change_type)}</span>
                        <span>
                          <span className={`mui-chip ${statusChipClass(change.status)}`}>
                            {mapStatusLabel(change.status)}
                          </span>
                        </span>
                        <span>{change.from_plan_name || "-"}</span>
                        <span>{change.to_plan_name || "-"}</span>
                        <span className="mono">{formatDateTime(change.effective_at)}</span>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </div>
        </div>
      )}

      {cancelConfirmOpen && cancelTarget && detailData && (
        <div className="sb-modal-backdrop" onClick={() => !cancelLoading && setCancelConfirmOpen(false)}>
          <div className="sb-modal sb-modal--narrow" onClick={(e) => e.stopPropagation()}>
            <div className="sb-modal-head">
              <div>
                <h2>구독 취소 확인</h2>
                <p>선택한 구독을 강제 취소합니다.</p>
              </div>
              <button
                type="button"
                className="sb-icon-btn"
                onClick={() => setCancelConfirmOpen(false)}
                disabled={cancelLoading}
              >
                <span className="material-icons">close</span>
              </button>
            </div>
            
            <div className="sb-detail-body sb-cancel-body">
              <div className="sb-cancel-target">
                <strong>사용자:</strong> {detailData.user.email} <br/>
                <strong>취소 플랜:</strong> {cancelTarget.plan_name}
              </div>
              <div className="sb-reason-field">
                <label className="sb-reason-label">
                  취소 사유 <span className="sb-required-mark">*</span>
                </label>
                <input
                  type="text"
                  placeholder="취소 사유를 30글자 이내로 요약해주세요"
                  maxLength={30}
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  autoFocus
                  className="sb-reason-input"
                />
                <span className="sb-reason-count">
                  {cancelReason.length}/30
                </span>
              </div>
            </div>

            <div className="sb-modal-foot">
              <button
                type="button"
                className="mui-btn mui-btn--outlined"
                onClick={() => setCancelConfirmOpen(false)}
                disabled={cancelLoading}
              >
                닫기
              </button>
              <button
                type="button"
                className="mui-btn mui-btn--contained mui-btn--error"
                onClick={handleConfirmCancel}
                disabled={cancelLoading || !cancelReason.trim()}
              >
                구독 취소
              </button>
            </div>
          </div>
        </div>
      )}
    </GarimPage>
  );
}
