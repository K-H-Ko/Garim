/*
코드 설명:
필수 약관(이용약관·개인정보) 동의 모달. 전체/개별 동의 체크와 약관 상세보기(TermsText/PrivacyText)
전환을 제공하며, 두 약관 모두 동의해야 onConsentSuccess가 호출된다.
*/
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "../../css/garim-pages/TermsConsentModal.css";
import TermsText from "./TermsText";
import PrivacyText from "./PrivacyText";

export default function TermsConsentModal({ onConsentSuccess }) {
  const navigate = useNavigate();
  const [termsAgreed, setTermsAgreed] = useState(false);
  const [privacyAgreed, setPrivacyAgreed] = useState(false);
  const [detailView, setDetailView] = useState(null); // 'terms' | 'privacy' | null

  const handleAgreeAll = (e) => {
    const checked = e.target.checked;
    setTermsAgreed(checked);
    setPrivacyAgreed(checked);
  };

  const handleSubmit = () => {
    if (termsAgreed && privacyAgreed) {
      onConsentSuccess();
    } else {
      alert("필수 약관에 모두 동의해 주세요.");
    }
  };

  const handleCancel = () => {
    navigate("/");
  };

  return (
    <div className="consent-modal-overlay">
      <div className="consent-modal">
        {detailView === 'terms' && (
          <div className="consent-detail-view">
            <TermsText />
            <button className="mui-btn mui-btn--contained mui-btn--block" onClick={() => setDetailView(null)}>닫기</button>
          </div>
        )}

        {detailView === 'privacy' && (
          <div className="consent-detail-view">
            <PrivacyText />
            <button className="mui-btn mui-btn--contained mui-btn--block" onClick={() => setDetailView(null)}>닫기</button>
          </div>
        )}

        {!detailView && (
          <>
            <h2>Garim 서비스 이용 안내</h2>
        <p className="consent-subtitle">안전한 서비스 이용을 위해 다음 4가지 핵심 사항을 꼭 확인해 주세요.</p>
        
        <div className="consent-summary-box">
          <ol>
            <li><strong>AI의 한계:</strong> AI 마스킹은 100% 완벽하지 않을 수 있으므로, 최종 업로드 전 본인이 직접 결과를 확인해야 합니다.</li>
            <li><strong>워터마크 삽입:</strong> 위변조 악용을 막기 위해 모든 결과물에는 눈에 보이지 않는 비식별 워터마크가 영구 삽입됩니다.</li>
            <li><strong>금지된 콘텐츠:</strong> 정부 공문서(신분증 등), 금융/의료/법원 문서의 조작 목적으로 사용을 엄격히 금지합니다.</li>
            <li><strong>데이터 처리 방식:</strong> 원본과 결과물은 일정 시간 후 우리 서버 및 외부 처리 환경에서 자동 영구 삭제됩니다.</li>
          </ol>
        </div>

        <div className="consent-checkboxes">
          <label className="checkbox-label agree-all">
            <input 
              type="checkbox" 
              checked={termsAgreed && privacyAgreed} 
              onChange={handleAgreeAll}
            />
            <span><strong>전체 동의합니다.</strong></span>
          </label>
          <hr />
          <label className="checkbox-label">
            <input 
              type="checkbox" 
              checked={termsAgreed} 
              onChange={(e) => setTermsAgreed(e.target.checked)}
            />
            <span>[필수] 서비스 이용약관 전문 동의 <button type="button" className="text-link-btn" onClick={(e) => { e.stopPropagation(); setDetailView('terms'); }}>(자세히 보기)</button></span>
          </label>
          <label className="checkbox-label">
            <input 
              type="checkbox" 
              checked={privacyAgreed} 
              onChange={(e) => setPrivacyAgreed(e.target.checked)}
            />
            <span>[필수] 개인정보 수집 및 이용 동의 <button type="button" className="text-link-btn" onClick={(e) => { e.stopPropagation(); setDetailView('privacy'); }}>(자세히 보기)</button></span>
          </label>
        </div>

        <div className="consent-actions">
          <button className="mui-btn mui-btn--outlined" onClick={handleCancel}>취소(돌아가기)</button>
          <button 
            className="mui-btn mui-btn--contained mui-btn--primary" 
            onClick={handleSubmit}
            disabled={!(termsAgreed && privacyAgreed)}
          >
            동의하고 시작하기
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  );
}
