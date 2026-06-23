import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { loadTossPayments } from "@tosspayments/payment-sdk";

import GarimPage from "../../components/garim/GarimPage";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { createPaymentTempOrder } from "../../utils/api";
import "../../css/garim-pages/Payment.css";

const clientKey = import.meta.env.VITE_TOSS_CLIENT_KEY;

const PLAN_PAYMENT = {
  pro: {
    label: "PRO",
    defaultCredits: 50,
    defaultAmount: 19800,
  },
  studio: {
    label: "STUDIO",
    defaultCredits: 500,
    defaultAmount: 49500,
  },
  credit_100: {
    label: "100 Credits",
    defaultCredits: 100,
    defaultAmount: 5000,
  },
  credit_500: {
    label: "500 Credits",
    defaultCredits: 500,
    defaultAmount: 20000,
  },
};
function numberFromQuery(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatPrice(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

export default function Payment() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 새 URL 파라미터: productType, productCode (구 plan 파라미터 fallback 지원)
  const productType = (searchParams.get("productType") || "subscription").toLowerCase();
  const productCode = (searchParams.get("productCode") || searchParams.get("plan") || "pro").toLowerCase();
  const isEmbed = searchParams.get("embed") === "1";

  const basePlan = PLAN_PAYMENT[productCode] || PLAN_PAYMENT.pro;
  const credits = numberFromQuery(
    searchParams.get("credits"),
    basePlan.defaultCredits,
  );
  const amount = numberFromQuery(
    searchParams.get("price"),
    basePlan.defaultAmount,
  );

  const isCredit = productType === "credit";
  const plan = {
    label: basePlan.label,
    itemName: isCredit ? `${basePlan.label} 충전` : `${basePlan.label} 플랜`,
    description: `크레딧 ${formatPrice(credits)}개`,
    amount,
  };

  useDocumentTitle("결제 · Garim");

  const handlePayment = async () => {
    if (isSubmitting) return;
    if (!clientKey) {
      alert("Toss Payments 클라이언트 키가 설정되지 않았습니다.");
      return;
    }

    setIsSubmitting(true);
    try {
      const tempOrder = await createPaymentTempOrder({
        product_type: productType,
        product_code: productCode,
        amount: plan.amount,
      });

      sessionStorage.setItem("lastOrderId", tempOrder.orderId);

      const tossPayments = await loadTossPayments(clientKey);
      await tossPayments.requestPayment("CARD", {
        amount: tempOrder.amount,
        orderId: tempOrder.orderId,
        orderName: `Garim ${tempOrder.orderName}`,
        customerName: "Garim 사용자",
        successUrl: `${window.location.origin}/payment/success`,
        failUrl: `${window.location.origin}/payment/fail`,
      });
    } catch (err) {
      console.error(err);
      alert(err.message || "결제창 실행에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const content = (
    <div className={`pay-page${isEmbed ? " pay-page--embed" : ""}`}>
      <div className="pay-shell">
        <div className="pay-head">
          <h1>결제</h1>
        </div>

        <div className="summary">
          <div className="row">
            <span>
              {plan.itemName} ({plan.description})
            </span>
            <span className="v">{formatPrice(plan.amount)}원</span>
          </div>

          <div className="row total">
            <span>합계</span>
            <span className="v">{formatPrice(plan.amount)}원</span>
          </div>
        </div>

        <div className="pay-disabled">
          <div className="pay-visual" aria-hidden="true">
            <span className="material-icons pay-visual__card">credit_card</span>
            <span className="material-icons pay-visual__shield">
              verified_user
            </span>
          </div>

          <h2>테스트 결제</h2>

          <p className="pay-guide">
            결제 버튼을 누르면 백엔드 임시 주문 생성 후 Toss 결제창이 열립니다.
          </p>

          <div className="pay-btn-group">
            <button
              type="button"
              onClick={() => navigate("/pricing")}
              className="mui-btn mui-btn--outlined mui-btn--lg pay-submit"
              disabled={isSubmitting}
            >
              취소하기
            </button>
            <button
              type="button"
              onClick={handlePayment}
              className="mui-btn mui-btn--contained mui-btn--lg pay-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? "주문 생성 중" : "결제하기"}
              <span className="material-icons">arrow_forward</span>
            </button>
          </div>
        </div>

        <div className="trust-strip">
          <span className="trust">
            <span className="material-icons">lock</span>
            SSL 256bit
          </span>

          <span className="trust">
            <span className="material-icons">verified</span>
            PCI DSS Level 1
          </span>
        </div>
      </div>
    </div>
  );

  if (isEmbed) {
    return content;
  }

  return (
    <GarimPage bodyClass="page-app page-payment" screenLabel="14 Payment">
      {content}
    </GarimPage>
  );
}
