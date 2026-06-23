import { useEffect, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  cancelScheduledPlanChange,
  getMyPaymentInfo,
  requestPlanChange,
  resumeSubscription,
} from "../../utils/api";
import "../../css/garim-pages/Billing.css";

import GarimPage from "../../components/garim/GarimPage";

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatPrice(value) {
  return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
}

export default function Billing() {
  useDocumentTitle("결제·구독 관리 · Garim");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionLoading, setActionLoading] = useState("");

  async function loadBillingInfo() {
    setLoading(true);
    setError("");
    try {
      const result = await getMyPaymentInfo();
      setData(result);
    } catch (err) {
      setError(err.message || "구독 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBillingInfo();
  }, []);

  async function handleCancelToFree() {
    if (!data?.current_plan?.plan_code || data.current_plan.plan_code === "free") return;
    setActionLoading("cancel");
    setActionMessage("");
    try {
      await requestPlanChange({ to_plan_id: "free" });
      await loadBillingInfo();
      setActionMessage("구독 취소 예약이 등록되었습니다.");
    } catch (err) {
      setActionMessage(err.message || "구독 취소 예약에 실패했습니다.");
    } finally {
      setActionLoading("");
    }
  }

  async function handleResume() {
    const subscriptionId = data?.current_subscription?.subscription_id;
    if (!subscriptionId) return;
    setActionLoading("resume");
    setActionMessage("");
    try {
      await resumeSubscription(subscriptionId);
      await loadBillingInfo();
      setActionMessage("구독 취소 예약이 철회되었습니다.");
    } catch (err) {
      setActionMessage(err.message || "구독 취소 철회에 실패했습니다.");
    } finally {
      setActionLoading("");
    }
  }

  async function handleCancelPlanChange() {
    const planChangeId = data?.scheduled_plan_change?.plan_change_id;
    if (!planChangeId) return;
    setActionLoading("plan-change");
    setActionMessage("");
    try {
      await cancelScheduledPlanChange(planChangeId);
      await loadBillingInfo();
      setActionMessage("다운그레이드 예약이 취소되었습니다.");
    } catch (err) {
      setActionMessage(err.message || "다운그레이드 예약 취소에 실패했습니다.");
    } finally {
      setActionLoading("");
    }
  }

  const currentPlan = data?.current_plan;
  const currentSubscription = data?.current_subscription;
  const scheduledPlanChange = data?.scheduled_plan_change;
  const carriedOver = data?.carried_over_subscription;
  const isCancelScheduled = scheduledPlanChange?.change_type === "cancel_to_free";
  const isDowngradeScheduled = scheduledPlanChange?.change_type === "downgrade";

  return (
    <GarimPage bodyClass="page-app" screenLabel="21 Billing">
      <div className="billing-page">
        <div className="billing-page__header">
          <div>
            <h1>결제·구독 관리</h1>
            <p>현재 플랜, 다음 결제일, 예약된 변경 상태를 한 화면에서 확인합니다.</p>
          </div>
          <button
            type="button"
            className="mui-btn mui-btn--outlined"
            onClick={loadBillingInfo}
            disabled={loading}
          >
            새로고침
          </button>
        </div>

        {error ? <div className="billing-banner billing-banner--error">{error}</div> : null}
        {actionMessage ? <div className="billing-banner billing-banner--info">{actionMessage}</div> : null}

        {loading ? (
          <div className="billing-surface billing-surface--empty">구독 정보를 불러오는 중입니다.</div>
        ) : (
          <>
            <section className="billing-grid">
              <div className="billing-surface billing-hero">
                <div className="billing-hero__meta">
                  <span className="mui-chip mui-chip--primary mui-chip--md">현재 플랜</span>
                  <h2>{currentPlan?.plan_name || "Free"}</h2>
                  <p>{currentPlan?.plan_code?.toUpperCase() || "FREE"}</p>
                </div>
                <div className="billing-hero__price">
                  {formatPrice(currentPlan?.price_amount)}
                  <small>원</small>
                </div>
              </div>

              <div className="billing-surface billing-facts">
                <div className="billing-fact">
                  <span>현재 플랜 만료</span>
                  <strong>{formatDateTime(currentSubscription?.current_period_end)}</strong>
                </div>
                <div className="billing-fact">
                  <span>다음 결제일</span>
                  <strong>{formatDateTime(currentSubscription?.next_billing_at)}</strong>
                </div>
                <div className="billing-fact">
                  <span>자동결제</span>
                  <strong>{currentSubscription?.auto_renew ? "사용" : "중지"}</strong>
                </div>
                <div className="billing-fact">
                  <span>취소 예약</span>
                  <strong>{currentSubscription?.cancel_at_period_end ? "예약됨" : "없음"}</strong>
                </div>
              </div>
            </section>

            {carriedOver ? (
              <section className="billing-surface billing-message">
                <h3>업그레이드 후 이월된 하위 플랜</h3>
                <p>
                  {carriedOver.plan_name} 잔여 기간 {carriedOver.carried_over_days}일이 현재 플랜 종료 이후까지
                  이어집니다. 종료 시점은 {formatDateTime(carriedOver.current_period_end)}입니다.
                </p>
              </section>
            ) : null}

            {isDowngradeScheduled ? (
              <section className="billing-surface billing-message">
                <h3>다운그레이드 예약</h3>
                <p>
                  {currentPlan?.plan_name}는 {formatDateTime(currentSubscription?.current_period_end)}까지 유지되고,
                  이후 {scheduledPlanChange?.to_plan_name} 플랜으로 변경됩니다.
                </p>
                <div className="billing-actions">
                  <button
                    type="button"
                    className="mui-btn mui-btn--outlined"
                    onClick={handleCancelPlanChange}
                    disabled={actionLoading === "plan-change"}
                  >
                    다운그레이드 예약 취소
                  </button>
                </div>
              </section>
            ) : null}

            {isCancelScheduled ? (
              <section className="billing-surface billing-message">
                <h3>구독 취소 예약</h3>
                <p>
                  {formatDateTime(currentSubscription?.current_period_end)}까지 {currentPlan?.plan_name} 플랜을 사용할
                  수 있습니다. 이후 유효한 다른 구독이 없으면 Free 플랜으로 전환됩니다.
                </p>
                <div className="billing-actions">
                  <button
                    type="button"
                    className="mui-btn mui-btn--contained"
                    onClick={handleResume}
                    disabled={actionLoading === "resume"}
                  >
                    취소 철회
                  </button>
                </div>
              </section>
            ) : null}

            <section className="billing-surface">
              <div className="billing-section__header">
                <div>
                  <h3>구독 상태</h3>
                  <p>현재 적용 중인 구독의 핵심 상태값입니다.</p>
                </div>
                {!isCancelScheduled && currentPlan?.plan_code !== "free" ? (
                  <button
                    type="button"
                    className="mui-btn mui-btn--outlined"
                    onClick={handleCancelToFree}
                    disabled={actionLoading === "cancel"}
                  >
                    구독 취소
                  </button>
                ) : null}
              </div>
              <dl className="billing-definition">
                <div>
                  <dt>current_period_start</dt>
                  <dd>{formatDateTime(currentSubscription?.current_period_start)}</dd>
                </div>
                <div>
                  <dt>current_period_end</dt>
                  <dd>{formatDateTime(currentSubscription?.current_period_end)}</dd>
                </div>
                <div>
                  <dt>next_billing_at</dt>
                  <dd>{formatDateTime(currentSubscription?.next_billing_at)}</dd>
                </div>
                <div>
                  <dt>billing_status</dt>
                  <dd>{currentSubscription?.billing_status || "-"}</dd>
                </div>
              </dl>
            </section>

            <section className="billing-surface">
              <div className="billing-section__header">
                <div>
                  <h3>결제 이력</h3>
                  <p>최근 승인된 결제와 전체 이력을 확인합니다.</p>
                </div>
              </div>
              {data?.payment_history?.length ? (
                <div className="billing-history">
                  {data.payment_history.map((item) => (
                    <div key={item.orderId} className="billing-history__row">
                      <div>
                        <strong>{item.orderName}</strong>
                        <span>{formatDateTime(item.approvedAt)}</span>
                      </div>
                      <div>
                        <strong>{formatPrice(item.amount)}원</strong>
                        <span>{item.method}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="billing-surface--empty">표시할 결제 이력이 없습니다.</div>
              )}
            </section>
          </>
        )}
      </div>
    </GarimPage>
  );
}
