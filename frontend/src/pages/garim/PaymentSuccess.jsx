/*
코드 설명:
Toss 결제 성공 리다이렉트를 받아 백엔드 승인(confirm)을 1회 처리하고, 중복 승인을 방지하며 결제 결과를 보여주는 페이지.
*/
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import GarimPage from "../../components/garim/GarimPage";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { confirmPayment } from "../../utils/api";
import "../../css/garim-pages/PaymentSuccess.css";

function getProcessedOrders() {
  try {
    return JSON.parse(sessionStorage.getItem("processedPaymentOrders") || "[]");
  } catch {
    return [];
  }
}

function addProcessedOrder(orderId) {
  const orders = getProcessedOrders();
  if (orders.includes(orderId)) return;
  sessionStorage.setItem("processedPaymentOrders", JSON.stringify([...orders, orderId]));
}

function getStoredPaymentResult(orderId) {
  try {
    const stored = sessionStorage.getItem(`paymentResult:${orderId}`);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function storePaymentResult(orderId, data) {
  try {
    sessionStorage.setItem(`paymentResult:${orderId}`, JSON.stringify(data));
  } catch {
    // Backend idempotency is the source of truth, so storage failure is non-fatal.
  }
}

export default function PaymentSuccess() {
  useDocumentTitle("결제 성공 · Garim");
  const [searchParams] = useSearchParams();
  const didConfirmRef = useRef(false);
  const [status, setStatus] = useState("confirming");
  const [message, setMessage] = useState("결제 승인 처리 중입니다.");
  const [result, setResult] = useState(null);

  const paymentKey = searchParams.get("paymentKey") || "";
  const orderId = searchParams.get("orderId") || "";
  const requestedAmount = Number(searchParams.get("amount") || 0);
  const displayAmount = Number(result?.amount || requestedAmount || 0);

  useEffect(() => {
    async function runConfirm() {
      if (didConfirmRef.current) return;
      didConfirmRef.current = true;

      if (!paymentKey || !orderId || !requestedAmount) {
        setStatus("error");
        setMessage("결제 승인에 필요한 파라미터가 부족합니다.");
        return;
      }

      const processedOrders = getProcessedOrders();
      if (processedOrders.includes(orderId)) {
        setResult(getStoredPaymentResult(orderId));
        setStatus("success");
        setMessage("이미 처리된 결제입니다.");
        return;
      }

      try {
        const data = await confirmPayment({
          paymentKey,
          orderId,
          amount: requestedAmount,
        });
        addProcessedOrder(orderId);
        storePaymentResult(orderId, data);
        setResult(data);
        setStatus("success");
        setMessage(data.idempotent ? "이미 승인 완료된 결제입니다." : "결제 승인이 완료되었습니다.");
      } catch (error) {
        console.error("Failed to confirm payment", error);
        setStatus("error");
        setMessage(error.message || "결제 승인 처리에 실패했습니다.");
      }
    }

    runConfirm();
  }, [orderId, paymentKey, requestedAmount]);

  return (
    <GarimPage bodyClass="page-app page-payment-success" screenLabel="Payment Success">
      <main className="payment-success-main">
        <div className="payment-success-content">
          <div
            className={`mui-alert payment-success-alert ${status === "error" ? "mui-alert--error" : "mui-alert--success"}`}
          >
            {message}
          </div>

          <div className="pay-shell">
            <div className="pay-head">
              <h1>결제 성공</h1>
            </div>

            <div className="summary">
              <div className="row">
                <span>주문명</span>
                <span className="v">{result?.orderName || "Garim 결제"}</span>
              </div>
              <div className="row">
                <span>주문번호</span>
                <span className="v payment-success-orderid">
                  {orderId || "-"}
                </span>
              </div>
              {result?.method && (
                <div className="row">
                  <span>결제 수단</span>
                  <span className="v">{result.method}</span>
                </div>
              )}
              <div className="row total">
                <span>결제 금액</span>
                <span className="v">{displayAmount ? `${displayAmount.toLocaleString("ko-KR")}원` : "-"}</span>
              </div>
            </div>
          </div>
        </div>
      </main>
    </GarimPage>
  );
}
