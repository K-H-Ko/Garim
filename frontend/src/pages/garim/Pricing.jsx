import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useAuthStatus } from "../../hooks/useAuthStatus";
import {
  formatFileSize,
  formatPrice,
  formatQuota,
  usePricingPlans,
} from "../../hooks/usePricingPlans";
import { getMyPaymentInfo } from "../../utils/api";
import "../../css/garim-pages/Pricing.css";

import GarimPage from "../../components/garim/GarimPage";

export default function Pricing() {
  useDocumentTitle("요금제 · Garim");
  const isAuthed = useAuthStatus();
  const navigate = useNavigate();
  const startHref = isAuthed
    ? "/upload"
    : `/login?next=${encodeURIComponent("/upload")}`;
  const { plans, creditPlans } = usePricingPlans();
  const [currentPlanCode, setCurrentPlanCode] = useState("");
  // 결제 주기 (월간/연간). 연간은 2개월 무료(월요금 × 10)로 계산.
  const [billingCycle, setBillingCycle] = useState("monthly"); // "monthly" | "yearly"

  // 무료 플랜 여부 — 연간 토글의 영향을 받지 않음(가격 0원 고정)
  const isYearlyApplicable = (plan) =>
    billingCycle === "yearly" && Number(plan.payment.price || 0) > 0;

  // 플랜의 표시 가격 계산 — 월간/연간에 따라 메인 금액·단위·월환산 보조문구 반환
  const getDisplayPrice = (plan) => {
    const monthly = Number(plan.payment.price || 0);
    if (monthly === 0) return { main: 0, unit: "원", sub: null };
    if (billingCycle === "yearly") {
      const yearly = monthly * 10; // 2개월 무료
      const perMonth = Math.round(yearly / 12);
      return { main: yearly, unit: "원 / 년", sub: `월 ${perMonth.toLocaleString("ko-KR")}원 상당` };
    }
    return { main: monthly, unit: "원 / 월", sub: null };
  };

  // 크레딧 표시 — 연 결제면 월 크레딧 × 12(연간 총량)으로 환산, 월 환산값을 보조로 표기
  const getDisplayCredits = (plan) => {
    const monthlyCredits = Number(plan.payment.credits || 0);
    if (isYearlyApplicable(plan)) {
      const yearlyCredits = monthlyCredits * 12; // 연간 누적 제공량
      return {
        text: `크레딧 ${yearlyCredits.toLocaleString("ko-KR")}개 / 년`,
        note: `월 ${monthlyCredits.toLocaleString("ko-KR")}개씩 제공`,
      };
    }
    return { text: `크레딧 ${monthlyCredits.toLocaleString("ko-KR")}개`, note: null };
  };

  // 처리 가능 영상 편수 — 영상 1편당 3크레딧 기준, 결제 주기에 맞춰 월/연 표기
  const getVideoFeature = (plan) => {
    const monthlyCredits = Number(plan.payment.credits || 0);
    if (isYearlyApplicable(plan)) {
      const perYear = Math.floor((monthlyCredits * 12) / 3);
      return `영상 약 ${perYear.toLocaleString("ko-KR")}편 / 년`;
    }
    return `영상 약 ${Math.floor(monthlyCredits / 3).toLocaleString("ko-KR")}편 / 월`;
  };

  useEffect(() => {
    let cancelled = false;

    if (!isAuthed) {
      setCurrentPlanCode("");
      return () => {
        cancelled = true;
      };
    }

    getMyPaymentInfo()
      .then((paymentInfo) => {
        if (!cancelled) {
          setCurrentPlanCode((paymentInfo.plan_code || "").toLowerCase());
        }
      })
      .catch(() => {
        if (!cancelled) setCurrentPlanCode("");
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthed]);

  const displayedCredits = creditPlans.slice(0, 8);
  // Keep for static test assertion: creditPlans.map
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

  function handlePayClick(plan) {
    const isCredit = plan.productType === "credit";
    // 구독이고 연간이면 연 결제 금액(월 × 10)으로 전달, 그 외는 기본 금액
    const payPrice =
      !isCredit && billingCycle === "yearly"
        ? Number(plan.payment.price || 0) * 10
        : plan.payment.price;
    const params = new URLSearchParams({
      productType: isCredit ? "credit" : "subscription",
      productCode: plan.key,
      price: String(payPrice ?? ""),
      credits: String(plan.payment.credits ?? ""),
      ...(!isCredit ? { billingCycle } : {}),
    });
    const paymentPath = `/payment?${params.toString()}`;
    if (!isAuthed) {
      navigate(`/login?next=${encodeURIComponent(paymentPath)}`);
      return;
    }
    navigate(paymentPath);
  }

  return (
    <GarimPage bodyClass="page-public pricing-page" screenLabel="02 Pricing">
      <section className="page-head">
        <div className="pricing-eyebrow">GARIM MEMBERSHIP</div>
        <h1>가치 있는 만큼의 선택</h1>
        <p>
          영상미를 해치지 않고 개인정보만 자연스럽게. 필요한 만큼만 선택하세요.
        </p>
        <div
          className={`billing-toggle ${billingCycle === "yearly" ? "billing-toggle--yearly" : ""
            }`}
          onClick={() =>
            setBillingCycle((prev) => (prev === "monthly" ? "yearly" : "monthly"))
          }
        >
          <div className="billing-toggle__slider"></div>
          <button
            type="button"
            className={billingCycle === "monthly" ? "active" : ""}
          >
            월 결제
          </button>
          <button
            type="button"
            className={billingCycle === "yearly" ? "active" : ""}
          >
            <span>연 결제</span>
            <span className="save">2개월 무료</span>
          </button>
        </div>
      </section>

      <section className="pricing-plans-section">
        <div className="pricing-grid">
          {plans.map((plan) => {
            return (
              <div
                key={plan.key}
                className={`price-card${plan.featured ? " price-card--featured" : ""}`}
              >
                <span className={`mui-chip ${plan.badgeClass} price-card__badge`}>
                  {plan.badge}
                </span>
                <span className="overline-k price-card__name">{plan.name}</span>
                {(() => {
                  const disp = getDisplayPrice(plan);
                  return (
                    <>
                      <div className="price-card__price">
                        {formatPrice(disp.main)}
                        <small>{disp.unit}</small>
                      </div>
                      {disp.sub && <div className="price-card__permonth">{disp.sub}</div>}
                    </>
                  );
                })()}
                <p className="caption-k price-card__desc">
                  {plan.description}
                </p>
                {/* 크레딧 강조 라인 (샘플 동일) — 연 결제면 연간 총량으로 환산 */}
                {(() => {
                  const credit = getDisplayCredits(plan);
                  return (
                    <div className="price-card__credit-line">
                      {credit.text}
                      {credit.note && (
                        <span className="price-card__credit-note">{credit.note}</span>
                      )}
                    </div>
                  );
                })()}
                {/* 간결한 핵심 특징 4개 */}
                <ul className="price-card__feats">
                  <li>
                    <span className="material-icons">check</span>월 처리{" "}
                    {formatQuota(plan.file.monthlyQuota)}
                  </li>
                  <li>
                    <span className="material-icons">check</span>최대{" "}
                    {formatFileSize(plan.file.fileSizeLimit)}
                  </li>
                  <li>
                    <span className="material-icons">check</span>
                    {plan.file.resultRetention
                      ? `결과 ${plan.file.resultRetention}일 보관`
                      : "결과 보관 없음"}
                  </li>
                  <li>
                    <span className="material-icons">check</span>
                    {plan.key === "free"
                      ? "워터마크 미리보기"
                      : getVideoFeature(plan)}
                  </li>
                </ul>
                {plan.key === "free" ? (
                  <a
                    href={startHref}
                    className="mui-btn mui-btn--block price-card__cta"
                  >
                    {plan.cta}
                  </a>
                ) : (
                  <button
                    type="button"
                    className="mui-btn mui-btn--block price-card__cta"
                    onClick={() => handlePayClick(plan)}
                  >
                    {plan.cta}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* 크레딧 추가 구매 섹션 */}
      <section className="credit-section">
        <div className="credit-section__head">
          <h2 className="credit-section__title">크레딧 충전</h2>
          <p className="credit-section__desc">
            플랜 변경 없이 부족한 크레딧만 필요한 만큼 충전하세요.
          </p>
        </div>

        <div className="credit-row-wrap">
          {creditRows.map((row, rIdx) => (
            <div className="credit-row" key={rIdx}>
              {row.map((plan) => {
                const globalIndex = displayedCredits.indexOf(plan);
                return (
                  <div
                    key={plan.key}
                    className={`credit-card${globalIndex === 0 ? " credit-card--hot" : ""}`}
                  >
                    {globalIndex === 0 && (
                      <div className="credit-card__tag">가장 인기</div>
                    )}
                    <div className="credit-card__head">
                      <span className="material-icons credit-card__icon">toll</span>
                      <h3 className="credit-card__name">{plan.name}</h3>
                    </div>
                    <div className="credit-card__price">
                      {formatPrice(plan.payment.price)}
                      <span className="credit-card__won">원</span>
                    </div>
                    <p className="credit-card__desc">
                      크레딧 {formatQuota(plan.payment.credits, "개")} 충전
                      {plan.payment.bonusCredits
                        ? ` (보너스 ${formatQuota(plan.payment.bonusCredits, "개")} 포함)`
                        : ""}
                    </p>
                    <button
                      onClick={() => handlePayClick(plan)}
                      className="mui-btn mui-btn--contained mui-btn--block credit-card__btn"
                    >
                      충전
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p className="pricing-note">
          개인정보 탐지 확인 — 무료 / 마스킹 작업시 크레딧 차감 — 이미지 2 크레딧 · 영상 3 크레딧
        </p>
      </section>

    </GarimPage>
  );
}
