import { Link } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/PasswordReset.css";

import GarimPage from "../../components/garim/GarimPage";

export default function PasswordReset() {
  useDocumentTitle("OAuth 로그인 · Garim");

  return (
    <GarimPage bodyClass="page-auth" screenLabel="07 Password reset">
      <main className="auth-main">
        <div className="auth-card">
          <h1>비밀번호 없이 로그인</h1>
          <p className="sub">OAuth-only 구조에서는 Garim 비밀번호를 저장하거나 재설정하지 않습니다.</p>
          <Link className="mui-btn mui-btn--contained mui-btn--lg mui-btn--block" to="/login">
            OAuth 로그인
          </Link>
        </div>
      </main>
    </GarimPage>
  );
}
