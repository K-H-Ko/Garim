/*
코드 설명:
상세보기 진입 시 크레딧 차감을 안내하는 확인 모달. sourceType(image=2, video=3)에 따라 비용을 계산하고,
크레딧 부족(isInsufficient) 시에는 요금제 이동 안내로 전환한다.
*/
import { useEffect } from "react";
import "../../css/components/CreditConfirmModal.css";

export default function CreditConfirmModal({ open, sourceType, isInsufficient, onConfirm, onCancel, onGoToPricing }) {
  // 소스 타입별 크레딧 비용/라벨
  const creditCost = sourceType === "video" ? 3 : 2;
  const typeLabel = sourceType === "video" ? "영상" : "이미지";

  // Esc 키로 닫기
  useEffect(() => {
    if (!open) return;
    function handleKey(e) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  // 비활성 상태면 렌더링 생략
  if (!open) return null;

  return (
    <div className="credit-modal-overlay" onClick={onCancel} role="dialog" aria-modal="true">
      <div
        className="credit-modal"
        onClick={(e) => e.stopPropagation()} // 내부 클릭 시 닫힘 방지
      >
        {/* 아이콘 */}
        <div className={`credit-modal__icon${isInsufficient ? " credit-modal__icon--danger" : ""}`}>
          <span className="material-icons">
            {isInsufficient ? "error_outline" : "toll"}
          </span>
        </div>

        {/* 제목 */}
        <h2 className="credit-modal__title">
          {isInsufficient ? "크레딧이 부족합니다" : "상세보기 크레딧 안내"}
        </h2>

        {/* 설명 */}
        <p className="credit-modal__desc">
          {typeLabel} 파일의 상세보기 이용 시<br />
          <strong className="credit-modal__cost">{creditCost}크레딧</strong>이 필요합니다.
        </p>

        {/* 크레딧 배지 */}
        {isInsufficient ? (
          <div className="credit-modal__badge credit-modal__badge--danger">
            <span className="material-icons">warning</span>
            <span>현재 보유 크레딧이 부족합니다</span>
          </div>
        ) : (
          <div className="credit-modal__badge">
            <span className="material-icons">stars</span>
            <span>{creditCost} 크레딧 차감</span>
          </div>
        )}

        {/* 안내 문구 */}
        <p className="credit-modal__note">
          {isInsufficient
            ? "요금제 페이지로 이동하여 크레딧을 충전하시겠습니까?"
            : <>세부 탐지 결과 확인 및 가리기 작업을 진행할 수 있습니다.</>}
        </p>

        {/* 버튼 영역 */}
        <div className="credit-modal__actions">
          <button
            type="button"
            className="mui-btn mui-btn--outlined"
            onClick={onCancel}
          >
            취소
          </button>
          {isInsufficient ? (
            <button
              type="button"
              className="mui-btn mui-btn--contained credit-modal__btn--danger"
              onClick={onGoToPricing}
            >
              <span className="material-icons">shopping_cart</span>
              요금제 페이지로 이동
            </button>
          ) : (
            <button
              type="button"
              className="mui-btn mui-btn--contained"
              onClick={onConfirm}
            >
              <span className="material-icons">search</span>
              확인 · 상세보기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
