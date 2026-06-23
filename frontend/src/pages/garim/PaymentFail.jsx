/*
코드 설명:
결제 취소·실패 시 표시되는 안내 페이지.
*/
import "../../css/garim-pages/PaymentFail.css";

export default function PaymentFail() {
  return (
    <div className="payment-fail">
      <h1>결제 실패</h1>
      <p>결제가 취소되었거나 실패했습니다.</p>
    </div>
  );
}
