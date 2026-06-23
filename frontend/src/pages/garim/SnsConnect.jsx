import { Link } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/SnsConnect.css";

import GarimPage from "../../components/garim/GarimPage";

export default function SnsConnect() {
  useDocumentTitle("SNS 연결 준비중 · Garim");

  return (
    <GarimPage bodyClass="page-app" screenLabel="11 SNS connect">
      <div className="sns-page">
        <div className="sns-shell">
          <div className="sns-head">
            <span className="mui-chip mui-chip--secondary mui-chip--md">SNS 점검 준비중</span>
            <h1>
              SNS 자동 연결 기능은
              <br />
              아직 제공하지 않습니다
            </h1>
            <p className="sub">
              현재 MVP에서는 업로드한 파일을 기준으로 개인정보 노출 여부를 먼저 점검합니다. SNS 계정 연결 기능은
              이후 정책과 보안 검토가 끝난 뒤 별도 기능으로 제공할 예정입니다.
            </p>
          </div>

          <section className="sns-status-card" aria-labelledby="sns-status-title">
            <div className="sns-status-icon">
              <span className="material-icons" aria-hidden="true">
                shield
              </span>
            </div>
            <div>
              <h2 id="sns-status-title">계정 연결 없음</h2>
              <p>
                이 화면에서는 외부 SNS 로그인, 계정 권한 요청, 토큰 저장을 수행하지 않습니다. 파일 업로드 방식으로
                먼저 서비스를 확인해 주세요.
              </p>
            </div>
          </section>

          <div className="sns-info-grid">
            <div className="sns-info-card">
              <span className="material-icons" aria-hidden="true">
                upload_file
              </span>
              <h3>현재 지원</h3>
              <p>동영상 또는 이미지 파일을 직접 업로드해 개인정보 탐지 흐름을 테스트합니다.</p>
            </div>
            <div className="sns-info-card">
              <span className="material-icons" aria-hidden="true">
                lock
              </span>
              <h3>보류 중</h3>
              <p>SNS 계정 연결은 백엔드 인증 정책과 권한 범위를 확정한 뒤 진행합니다.</p>
            </div>
          </div>

          <div className="sns-actions">
            <Link to="/upload" className="mui-btn mui-btn--contained">
              업로드로 이동 →
            </Link>
            <Link to="/" className="mui-btn mui-btn--text">
              홈으로
            </Link>
          </div>
        </div>
      </div>
    </GarimPage>
  );
}
