/*
코드 설명:
Garim 공통 푸터 컴포넌트. 기본은 4열 브랜드/링크 그리드를 렌더하고,
minimal=true(인증 화면)일 때는 저작권·약관 링크만 담은 축약 푸터를 렌더한다.
*/
import { Link } from "react-router-dom";
import "../../css/components/GarimFooter.css";

export default function GarimFooter({ minimal = false }) {
  // 인증 화면용 축약 푸터
  if (minimal) {
    return (
      <footer className="gf gf--minimal">
        <div className="gf__bottom">
          <span>© 2026 Garim, Inc.</span>
          <span><Link to="/terms?tab=terms">이용약관</Link> · <Link to="/terms?tab=privacy">개인정보처리방침</Link></span>
        </div>
      </footer>
    );
  }

  return (
    <footer className="gf">
      <div className="gf__inner">
        <div className="gf__brand">
          <img src="/garim/logo.svg" alt="Garim" />
          <p>
            AI가 영상·이미지 속 개인정보를 자동으로 탐지하고<br />
            비식별화하여 안전한 데이터 활용을 돕는 플랫폼입니다.
          </p>
          <p className="gf__brand-sub">
            현재 베타 서비스 운영 중입니다.<br />
            문의 및 피드백은 고객 문의/신고 메뉴를 이용해 주세요.
          </p>
        </div>
        <div className="gf__col">
          <h4>서비스</h4>
          <Link to="/upload">파일 탐지</Link>
          <Link onClick={() => alert("준비중입니다. 커밍쑨!")}>SNS 점검(준비중)</Link>
          <Link to="/pricing">요금제</Link>
        </div>
        <div className="gf__col">
          <h4>지원</h4>
          <Link to="/faq">FAQ</Link>
          <Link to="/support">고객 문의 / 신고</Link>
          <Link to="/faq">처리 안내</Link>
        </div>
        <div className="gf__col">
          <h4>정책</h4>
          <Link to="/terms?tab=terms">이용약관</Link>
          <Link to="/terms?tab=privacy">개인정보처리방침</Link>
          <Link to="/learning-consent">AI 학습 동의</Link>
        </div>
      </div>
      <div className="gf__bottom">
        <span>© 2026 Garim, Inc. · garim.kr</span>
        <span>made in Seoul</span>
      </div>
    </footer>
  );
}
