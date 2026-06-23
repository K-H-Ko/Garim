import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getOAuthStartUrl, getOAuthReregisterUrl } from "../../utils/api";
import "../../css/garim-pages/Login.css";
import "../../css/garim-pages/TermsConsentModal.css";

import GarimPage from "../../components/garim/GarimPage";
import TermsText from "../../components/garim/TermsText";

const socialButtons = [
  {
    provider: "kakao",
    label: "카카오 OAuth로 로그인",
    className: "login-social login-social--kakao",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="#3C1E1E"
          d="M12 3C6.5 3 2 6.6 2 11c0 2.9 1.9 5.5 4.8 6.9-.2.7-.7 2.6-.8 3-.1.5.2.5.4.4l3.5-2.4c.7.1 1.4.2 2.1.2 5.5 0 10-3.6 10-8.1S17.5 3 12 3z"
        />
      </svg>
    ),
  },
  {
    provider: "naver",
    label: "네이버 OAuth로 로그인",
    className: "login-social login-social--naver",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="currentColor" d="M4 4h5.1l5.8 8.4V4H20v16h-5.1L9.1 11.6V20H4V4z" />
      </svg>
    ),
  },
  {
    provider: "google",
    label: "구글 OAuth로 로그인",
    className: "login-social login-social--google",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#4285F4" d="M21.8 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5.5c-.2 1.2-.9 2.3-2 3v2.4h3.2c1.9-1.7 3.1-4.2 3.1-7.1z" />
        <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.7-2.6l-3.2-2.4c-.9.6-2 .9-3.5.9-2.6 0-4.8-1.8-5.6-4.1H3.1v2.5C4.8 19.7 8.2 22 12 22z" />
        <path fill="#FBBC05" d="M6.4 13.8c-.2-.6-.3-1.2-.3-1.8s.1-1.2.3-1.8V7.7H3.1C2.4 9 2 10.4 2 12s.4 3 1.1 4.3l3.3-2.5z" />
        <path fill="#EA4335" d="M12 6.1c1.5 0 2.8.5 3.8 1.5l2.8-2.8C17 3.1 14.7 2 12 2 8.2 2 4.8 4.3 3.1 7.7l3.3 2.5c.8-2.3 3-4.1 5.6-4.1z" />
      </svg>
    ),
  },
];

export default function Login() {
  useDocumentTitle("로그인 · Garim");
  const [searchParams] = useSearchParams();
  const isReregister = searchParams.get("reregister") === "true";
  const reregisterProvider = searchParams.get("provider") || "";
  const nextPath = searchParams.get("next") || "";

  // 약관 팝업 열림/닫힘 상태
  const [termsOpen, setTermsOpen] = useState(false);

  const startOAuth = (provider) => {
    window.location.assign(getOAuthStartUrl(provider, nextPath));
  };

  const startReregister = () => {
    window.location.assign(getOAuthReregisterUrl(reregisterProvider));
  };

  if (isReregister) {
    return (
      <GarimPage bodyClass="page-auth" screenLabel="06 Login">
        <main className="auth-main">
          <div className="auth-card">
            <h1>계정 재가입</h1>
            <p className="sub">
              이전에 탈퇴한 계정입니다. 재가입하시려면 개인정보 제공에 다시
              동의해 주세요.
            </p>
            <button
              type="button"
              className="mui-btn mui-btn--contained mui-btn--block login-reregister-btn"
              onClick={startReregister}
            >
              동의하고 재가입하기
            </button>
            <div className="login-terms-action login-terms-action--gap">
              <Link className="mui-btn mui-btn--outlined mui-btn--block" to="/login">
                돌아가기
              </Link>
            </div>
          </div>
        </main>
      </GarimPage>
    );
  }

  return (
    <GarimPage bodyClass="page-auth" screenLabel="06 Login">
      <main className="auth-main">
        <div className="auth-card">
          <h1>OAuth 계정으로 시작</h1>
          <p className="sub">사용할 OAuth 계정을 선택해 로그인해 주세요.</p>

          <div className="social-stack">
            {socialButtons.map((button) => (
              <button
                key={button.provider}
                type="button"
                className={button.className}
                onClick={() => startOAuth(button.provider)}
              >
                {button.icon}
                <span>{button.label}</span>
              </button>
            ))}
          </div>
          <div className="login-terms-action">
            {/* /terms 페이지 이동 대신 팝업으로 약관 표시 */}
            <button
              type="button"
              className="mui-btn mui-btn--outlined mui-btn--block"
              onClick={() => setTermsOpen(true)}
            >
              이용약관 확인
            </button>
          </div>
        </div>
      </main>

      {/* 이용약관 팝업 — TermsConsentModal과 동일한 스타일 재사용 */}
      {termsOpen && (
        <div className="consent-modal-overlay" onClick={() => setTermsOpen(false)}>
          <div className="consent-modal" onClick={(e) => e.stopPropagation()}>
            <div className="consent-detail-view">
              <TermsText />
              <button
                type="button"
                className="mui-btn mui-btn--contained mui-btn--block"
                onClick={() => setTermsOpen(false)}
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </GarimPage>
  );
}
