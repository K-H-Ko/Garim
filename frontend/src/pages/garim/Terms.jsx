import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/Terms.css";
import GarimPage from "../../components/garim/GarimPage";

// ─── 탭 정의 ────────────────────────────────────────────────────
const TABS = [
  { id: "terms",    label: "이용약관" },
  { id: "privacy",  label: "개인정보처리방침" },
  { id: "marketing",label: "마케팅 정보 수신" },
  { id: "location", label: "위치기반 서비스" },
  { id: "ai",       label: "AI 학습 데이터 활용" },
];

// ─── 탭별 메타 정보 ──────────────────────────────────────────────
const TAB_META = {
  terms: {
    title: "서비스 이용약관 v1.0",
    date: "적용일자 2026년 5월 14일 · 최종 수정 2026년 5월 14일",
    toc: [
      { id: "t1",  label: "제1조 · 목적" },
      { id: "t2",  label: "제2조 · 용어의 정의" },
      { id: "t3",  label: "제3조 · 약관의 효력 및 변경" },
      { id: "t4",  label: "제4조 · 회원가입과 자격" },
      { id: "t5",  label: "제5조 · 서비스 내용" },
      { id: "t6",  label: "제6조 · 워터마크 정책" },
      { id: "t7",  label: "제7조 · 콘텐츠 제한" },
      { id: "t8",  label: "제8조 · 회원의 의무" },
      { id: "t9",  label: "제9조 · 데이터 보관·삭제" },
      { id: "t11", label: "제11조 · 면책" },
      { id: "t12", label: "제12조 · 분쟁 해결" },
    ],
  },
  privacy: {
    title: "개인정보처리방침 v1.0",
    date: "적용일자 2026년 5월 14일 · 최종 수정 2026년 5월 14일",
    toc: [
      { id: "p1",  label: "제1조 · 수집 항목 및 방법" },
      { id: "p2",  label: "제2조 · 수집 및 이용 목적" },
      { id: "p3",  label: "제3조 · 보관 기간 및 파기" },
      { id: "p4",  label: "제4조 · 제3자 제공" },
      { id: "p5",  label: "제5조 · 처리 위탁" },
      { id: "p6",  label: "제6조 · 정보주체의 권리" },
      { id: "p7",  label: "제7조 · 자동 수집 항목" },
      { id: "p8",  label: "제8조 · 보안 조치" },
      { id: "p9",  label: "제9조 · 개인정보보호책임자" },
    ],
  },
  marketing: {
    title: "마케팅 정보 수신 동의 v1.0",
    date: "적용일자 2026년 5월 14일 · 최종 수정 2026년 5월 14일",
    toc: [
      { id: "m1", label: "제1조 · 수신 동의 목적" },
      { id: "m2", label: "제2조 · 발송 채널 및 내용" },
      { id: "m3", label: "제3조 · 수집 항목" },
      { id: "m4", label: "제4조 · 보관 기간" },
      { id: "m5", label: "제5조 · 동의 철회" },
      { id: "m6", label: "제6조 · 미동의 불이익 없음" },
    ],
  },
  location: {
    title: "위치기반 서비스 이용약관 v1.0",
    date: "적용일자 2026년 5월 14일 · 최종 수정 2026년 5월 14일",
    toc: [
      { id: "l1", label: "제1조 · 목적" },
      { id: "l2", label: "제2조 · 위치 정보 수집 범위" },
      { id: "l3", label: "제3조 · 서비스 내용" },
      { id: "l4", label: "제4조 · 보관 및 이용 기간" },
      { id: "l5", label: "제5조 · 동의 철회" },
      { id: "l6", label: "제6조 · 손해배상 및 면책" },
    ],
  },
  ai: {
    title: "AI 학습 데이터 활용 동의 v1.0",
    date: "적용일자 2026년 5월 14일 · 최종 수정 2026년 5월 14일",
    toc: [
      { id: "a1", label: "제1조 · 목적 및 성격" },
      { id: "a2", label: "제2조 · 활용 데이터 범위" },
      { id: "a3", label: "제3조 · 비활용 데이터 명시" },
      { id: "a4", label: "제4조 · 익명화 처리" },
      { id: "a5", label: "제5조 · 제공 혜택" },
      { id: "a6", label: "제6조 · 동의 철회 및 효과" },
      { id: "a7", label: "제7조 · 데이터 보관 기간" },
    ],
  },
};

// ─── 탭별 본문 컴포넌트 ──────────────────────────────────────────

// 이용약관
function TermsContent() {
  return (
    <>
      <div className="callout warning">
        <strong>법무 검토 전 초안</strong> · 본 약관은 사전 공개용 초안으로, 변호사 법무 검토 후 정식 게시됩니다. 회사 정보(상호·대표자·주소·연락처)는 정식 등기 후 갱신됩니다.
      </div>

      <h2 id="t1">제1조 (목적)</h2>
      <p>본 약관은 <strong>[회사명]</strong>(이하 "회사")가 제공하는 AI 기반 멀티모달 개인정보 도싱 방지 및 데이터 치환 서비스 "Garim"(이하 "서비스")의 이용과 관련하여, 회사와 회원 간의 권리·의무 및 책임사항을 규정함을 목적으로 합니다.</p>

      <h2 id="t2">제2조 (용어의 정의)</h2>
      <p>본 약관에서 사용하는 용어의 정의는 다음과 같습니다.</p>
      <ul>
        <li><strong>"서비스"</strong> — 회사가 운영하는 garim.kr 도메인 및 그 하위 도메인에서 제공하는 모든 기능을 의미합니다.</li>
        <li><strong>"회원"</strong> — 본 약관에 동의하고 회사에 이메일을 제공하여 가입한 자를 의미합니다.</li>
        <li><strong>"개인정보"</strong> — 영상·이미지·음성에 포함되어 개인을 식별할 수 있는 정보(얼굴·이름·전화번호·주소·차량번호·송장 정보·신분증 등)를 의미합니다.</li>
        <li><strong>"검출"</strong> — 업로드된 콘텐츠에서 개인정보의 존재·위치·시점을 자동으로 식별하는 행위를 의미합니다.</li>
        <li><strong>"치환"</strong> — 검출된 개인정보를 회원이 선택한 방식(자동 생성·사용자 지정·마스킹·건너뛰기)으로 가공하여 결과물을 생성하는 행위를 의미합니다.</li>
        <li><strong>"STE"</strong>(Scene Text Editing) — 영상·이미지의 텍스트를 원본의 폰트·색상·왜곡을 보존한 채 새 텍스트로 합성하는 기술을 의미합니다.</li>
        <li><strong>"워터마크"</strong> — 변조 악용을 방지하기 위해 결과물에 삽입되는 디지털 표식을 의미합니다.</li>
        <li><strong>"크레딧"</strong> — 서비스 처리 기능을 이용하기 위한 내부 포인트 단위를 의미합니다.</li>
      </ul>

      <h2 id="t3">제3조 (약관의 효력 및 변경)</h2>
      <p>① 본 약관은 회원이 가입 시 동의함으로써 효력이 발생합니다.</p>
      <p>② 회사는 관련 법령에 위배되지 않는 범위에서 본 약관을 개정할 수 있으며, 개정 시 적용일자 <strong>7일 전</strong>부터 서비스 내 공지사항 및 회원의 이메일을 통해 통지합니다. 회원에게 불리한 변경의 경우 <strong>30일 전</strong>부터 통지합니다.</p>
      <p>③ 회원이 개정 약관에 동의하지 않을 경우, 적용일자 이전에 회원 탈퇴를 통해 서비스 이용을 중단할 수 있습니다. 적용일자 이후 서비스를 계속 이용하는 경우 개정 약관에 동의한 것으로 간주됩니다.</p>

      <h2 id="t4">제4조 (회원가입과 자격)</h2>
      <h3>1. 가입 자격</h3>
      <p>회원가입은 <strong>만 14세 이상</strong>의 개인 또는 법인을 대상으로 합니다. 만 14세 미만은 가입할 수 없으며, 회사는 가입 시 본인 확인을 요구할 수 있습니다.</p>
      <h3>2. 가입 방식</h3>
      <p>본 서비스는 사용자 편의와 보안을 위해 <strong>OAuth 2.0 기반의 간편 가입</strong>만을 지원합니다.</p>
      <ul>
        <li><strong>간편 가입</strong> — 카카오, 네이버, 구글 계정으로 로그인 시 자동 가입 (첫 로그인 시 필수 약관 동의)</li>
      </ul>
      <h3>3. 최소 수집 원칙</h3>
      <p>회사는 서비스 제공에 필요한 최소한의 정보만 수집합니다. <strong>실명·전화번호·주소·생년월일·주민등록번호는 수집하지 않습니다.</strong></p>
      <h3>4. 가입 거절·해지</h3>
      <ul>
        <li>타인의 이메일·정보로 가입한 경우</li>
        <li>만 14세 미만이거나 허위 정보를 제공한 경우</li>
        <li>이전에 본 약관 위반으로 회원 자격을 상실한 이력이 있는 경우</li>
        <li>기타 회사가 정한 가입 요건을 충족하지 못한 경우</li>
      </ul>

      <h2 id="t5">제5조 (서비스 내용)</h2>
      <ul>
        <li>영상·이미지·음성의 개인정보 자동 검출 (무료)</li>
        <li>검출 항목의 자연스러운 지움 처리 (자동 OCR·사용자 지정·인페인팅)</li>
        <li>전체·구간 다운로드</li>
        <li>모든 결과물에 변조 방지 워터마크 자동 적용</li>
        <li>크레딧 기반 유료 플랜 (Free / Pro / Business)</li>
      </ul>

      <h2 id="t6">제6조 (워터마크 정책)</h2>
      <p>회사는 변조 악용 방지를 위해 모든 치환 결과물에 워터마크를 자동 적용합니다. 회원은 워터마크 적용을 거부하거나 제거할 수 없습니다.</p>
      <div className="callout">
        <strong>1) 비식별 워터마크 (모든 결과물에 영구 적용)</strong><br />
        사람 눈에 보이지 않는 디지털 서명으로, 콘텐츠 품질에 영향을 주지 않습니다. 위변조 의심 신고 시 회사는 본 워터마크로 처리 이력을 역추적할 수 있으며, 해시 값은 영구 보존됩니다.<br /><br />
        <strong>2) 가시 워터마크 (미리보기 전용)</strong><br />
        처리 전 미리보기 화면에서만 표시됩니다. 최종 결과물에는 적용되지 않습니다.
      </div>

      <h2 id="t7">제7조 (콘텐츠 제한)</h2>
      <p>위·변조 악용 위험이 큰 다음 콘텐츠의 처리를 거부합니다. 업로드 시점에 자동 감지되어 차단됩니다.</p>
      <table>
        <thead><tr><th>거부 카테고리</th><th>예시</th></tr></thead>
        <tbody>
          <tr><td>정부 공문서</td><td>주민등록증·운전면허·여권·등기부등본·인감증명</td></tr>
          <tr><td>의료 기록</td><td>처방전·진료 확인서·검사 결과지</td></tr>
          <tr><td>금융 공식 문서</td><td>은행 잔고 증명·재직 증명서·소득 증명</td></tr>
          <tr><td>법원 문서</td><td>판결문·소장·공증서</td></tr>
        </tbody>
      </table>

      <h2 id="t8">제8조 (회원의 권리와 의무)</h2>
      <p>① 업로드된 파일의 저작권은 회원에게 있습니다. 회사는 회원의 별도 선택적 동의(AI 학습 데이터 활용 동의) 없이는 업로드된 원본 및 결과물을 AI 모델 학습에 사용하지 않습니다.</p>
      <p>② 회원은 다음 행위를 하여서는 안 됩니다.</p>
      <ul>
        <li>타인의 콘텐츠를 권한 없이 업로드·처리하는 행위</li>
        <li>제7조의 거부 콘텐츠를 우회·변형하여 업로드하는 행위</li>
        <li>처리 결과물의 워터마크를 제거·왜곡하려는 시도</li>
        <li>서비스를 이용하여 타인을 사칭하거나 위·변조 콘텐츠를 제작·유포하는 행위</li>
        <li>자동화 도구·봇을 이용한 비정상적 트래픽 발생 (어뷰징)</li>
        <li>서비스의 보안 취약점을 악용하거나 시스템에 무단 접근하는 행위</li>
      </ul>

      <h2 id="t9">제9조 (데이터 보관·삭제)</h2>
      <p>회사는 <strong>B-1 자동 삭제 원칙</strong>에 따라 회원의 데이터를 처리합니다.</p>
      <table>
        <thead><tr><th>데이터 종류</th><th>보관 기간</th><th>비고</th></tr></thead>
        <tbody>
          <tr><td>업로드 원본 파일</td><td><strong>12시간</strong></td><td>모든 회원 공통</td></tr>
          <tr><td>치환 결과 파일</td><td><strong>24시간</strong></td><td>다운로드 후 자동 삭제</td></tr>
          <tr><td>미리보기 파일</td><td>1시간</td><td>가시 워터마크 적용</td></tr>
          <tr><td>처리 메타데이터</td><td>30일</td><td>원본 영상 미포함</td></tr>
          <tr><td>처리 이력 로그</td><td>90일</td><td>분쟁 입증·통계용</td></tr>
          <tr><td>회원 가입 정보</td><td>탈퇴 시까지</td><td>탈퇴 후 7일 유예 → 영구 삭제</td></tr>
          <tr><td>약관 동의 이력</td><td>탈퇴 후 5년</td><td>법무·감사 보존</td></tr>
          <tr><td>워터마크 해시</td><td><strong>영구 보존</strong></td><td>변조 악용 방지</td></tr>
        </tbody>
      </table>

      <h2 id="t11">제11조 (면책 조항)</h2>
      <ul>
        <li>AI 검출 및 치환 결과는 100% 정확도를 보장하지 않습니다. 최종 결과물 외부 게시 전 본인이 확인할 책임이 있습니다.</li>
        <li>천재지변·전쟁·정전·통신 장애 등 불가항력으로 인한 서비스 중단</li>
        <li>회원의 귀책 사유로 인한 서비스 이용 장애</li>
        <li>외부 서비스(카카오·결제 PG 등)의 정책 변경 또는 장애로 인한 영향</li>
      </ul>
      <p>회사의 손해배상 책임은 회원이 직전 1년간 지불한 이용료를 초과하지 않습니다. 단, 회사의 고의 또는 중과실로 인한 손해는 예외입니다.</p>

      <h2 id="t12">제12조 (분쟁 해결·준거법)</h2>
      <p>① 본 약관은 대한민국 법령에 따라 해석·적용됩니다.</p>
      <p>② 분쟁 발생 시 회사와 회원은 신의 성실의 원칙에 따라 우선 협의 해결합니다.</p>
      <p>③ 협의가 이루어지지 않을 경우, 관할 법원은 <strong>[회사 본점 소재지 관할 법원]</strong>으로 합니다.</p>

      <div className="callout success">
        <strong>부칙</strong> · 본 약관은 2026년 5월 14일부터 시행합니다.
      </div>
    </>
  );
}

// 개인정보처리방침
function PrivacyContent() {
  return (
    <>
      <div className="callout warning">
        <strong>법무 검토 전 초안</strong> · 본 방침은 사전 공개용 초안입니다. 개인정보보호책임자(CPO) 정보는 법인 등기 후 갱신됩니다.
      </div>

      <h2 id="p1">제1조 (수집하는 개인정보 항목 및 수집 방법)</h2>
      <h3>1. 수집 항목</h3>
      <table>
        <thead><tr><th>구분</th><th>항목</th><th>수집 시점</th></tr></thead>
        <tbody>
          <tr><td>필수</td><td>이메일 주소, OAuth 제공자 식별자(sub)</td><td>첫 로그인 시 자동 수신</td></tr>
          <tr><td>선택</td><td>프로필 닉네임(OAuth 제공 시)</td><td>첫 로그인 시 자동 수신</td></tr>
          <tr><td>결제</td><td>결제 승인번호, 카드사 정보(마스킹), Billing Key(암호화)</td><td>자동결제 등록 시</td></tr>
          <tr><td>자동 수집</td><td>접속 IP, 브라우저 종류, 서비스 이용 로그, 쿠키·세션 정보</td><td>서비스 이용 중 자동 수집</td></tr>
        </tbody>
      </table>
      <div className="callout">
        <strong>최소 수집 원칙</strong> · 실명, 전화번호, 상세 주소, 생년월일, 주민등록번호 등 민감한 개인정보는 일절 수집하지 않습니다.
      </div>
      <h3>2. 수집 방법</h3>
      <ul>
        <li>카카오·네이버·구글 OAuth 2.0 인증을 통해 동의 범위 내 정보만 수신</li>
        <li>서비스 이용 중 자동 생성되는 접속 로그 수집</li>
        <li>결제 시 Toss Payments PG를 통해 암호화 전달</li>
      </ul>

      <h2 id="p2">제2조 (개인정보의 수집 및 이용 목적)</h2>
      <table>
        <thead><tr><th>이용 목적</th><th>관련 항목</th></tr></thead>
        <tbody>
          <tr><td>회원 식별 및 본인 확인</td><td>이메일, OAuth 식별자</td></tr>
          <tr><td>서비스 제공 (AI 마스킹·검출·치환)</td><td>이메일, 서비스 이용 로그</td></tr>
          <tr><td>결제 처리 및 크레딧 관리</td><td>결제 정보, Billing Key</td></tr>
          <tr><td>고객 지원 및 공지 전달</td><td>이메일</td></tr>
          <tr><td>부정 이용 방지 및 보안</td><td>접속 IP, 이용 로그</td></tr>
          <tr><td>서비스 개선 및 통계 분석</td><td>익명화된 이용 로그</td></tr>
        </tbody>
      </table>

      <h2 id="p3">제3조 (개인정보의 보관 기간 및 파기)</h2>
      <h3>1. 보관 기간</h3>
      <table>
        <thead><tr><th>항목</th><th>보관 기간</th><th>근거</th></tr></thead>
        <tbody>
          <tr><td>회원 가입 정보</td><td>탈퇴 시까지 (유예 7일 후 파기)</td><td>서비스 제공</td></tr>
          <tr><td>결제 정보</td><td>5년</td><td>전자상거래법</td></tr>
          <tr><td>약관 동의 이력</td><td>5년</td><td>정보통신망법</td></tr>
          <tr><td>접속 로그·IP</td><td>3개월</td><td>통신비밀보호법</td></tr>
          <tr><td>업로드 원본 파일</td><td>최대 12시간 후 자동 삭제</td><td>B-1 원칙</td></tr>
          <tr><td>처리 결과 파일</td><td>최대 24시간 후 자동 삭제</td><td>B-1 원칙</td></tr>
          <tr><td>워터마크 해시</td><td>영구 보존</td><td>변조 방지·역추적</td></tr>
        </tbody>
      </table>
      <h3>2. 파기 방법</h3>
      <p>전자 파일 형태의 개인정보는 복구 불가능한 방법으로 영구 삭제합니다. 서버 삭제 시 덮어쓰기(overwrite) 방식으로 완전 파기합니다.</p>

      <h2 id="p4">제4조 (개인정보의 제3자 제공)</h2>
      <p>회사는 원칙적으로 이용자의 개인정보를 제3자에게 제공하지 않습니다. 다만, 다음의 경우는 예외로 합니다.</p>
      <ul>
        <li>이용자가 사전에 동의한 경우</li>
        <li>법령에 의하여 수사·조사 목적으로 법원·수사기관으로부터 적법한 절차에 따른 요청이 있는 경우</li>
        <li>위변조 의심 신고 발생 시 수사 기관에 워터마크 해시 및 처리 로그를 제공하는 경우</li>
      </ul>

      <h2 id="p5">제5조 (개인정보 처리 위탁)</h2>
      <table>
        <thead><tr><th>수탁 업체</th><th>위탁 업무</th><th>보관 기간</th></tr></thead>
        <tbody>
          <tr><td>Toss Payments</td><td>결제 처리 및 Billing Key 관리</td><td>계약 종료 시 즉시 파기</td></tr>
          <tr><td>Amazon Web Services (AWS)</td><td>서버 인프라 운영 및 데이터 저장</td><td>계약 종료 시 즉시 파기</td></tr>
          <tr><td>Google Cloud Platform</td><td>대용량 AI 처리 임시 연산</td><td>처리 완료 즉시 파기</td></tr>
          <tr><td>Kakao / Naver / Google</td><td>OAuth 인증 처리</td><td>인증 완료 후 해당 업체 정책 따름</td></tr>
        </tbody>
      </table>

      <h2 id="p6">제6조 (정보주체의 권리·의무 및 행사 방법)</h2>
      <p>정보주체(회원)는 언제든지 다음의 권리를 행사할 수 있습니다.</p>
      <ul>
        <li><strong>열람 요구</strong> — 본인의 개인정보 처리 현황 확인</li>
        <li><strong>정정·삭제 요구</strong> — 잘못된 개인정보 정정 또는 삭제 요청</li>
        <li><strong>처리 정지 요구</strong> — 개인정보 처리 일시 정지 요청</li>
        <li><strong>동의 철회</strong> — 언제든지 서비스 탈퇴를 통해 수집 동의 철회 가능</li>
      </ul>
      <p>권리 행사는 서비스 내 <strong>설정 → 계정</strong> 메뉴 또는 개인정보보호책임자 이메일로 요청할 수 있습니다. 회사는 요청 후 <strong>10일 이내</strong>에 처리 결과를 통보합니다.</p>

      <h2 id="p7">제7조 (자동으로 수집되는 개인정보 (쿠키·세션))</h2>
      <p>서비스는 로그인 유지 및 보안을 위해 <strong>HTTP-Only Secure 쿠키</strong>를 사용합니다.</p>
      <ul>
        <li><strong>Access Token 쿠키</strong> — 인증된 API 요청을 위한 단기 토큰 (만료: 1시간)</li>
        <li><strong>Refresh Token 쿠키</strong> — Access Token 자동 갱신용 (만료: 7일)</li>
      </ul>
      <p>브라우저 설정에서 쿠키를 비활성화하면 로그인 기능을 이용할 수 없습니다. 쿠키는 제3자 추적·광고에 사용되지 않습니다.</p>

      <h2 id="p8">제8조 (개인정보 보호를 위한 기술적·관리적 조치)</h2>
      <ul>
        <li>데이터 전송 시 TLS 1.2 이상 암호화 통신</li>
        <li>Billing Key 등 민감 데이터 AES-256 암호화 저장</li>
        <li>접근 권한 최소화 원칙 적용 (Role-Based Access Control)</li>
        <li>정기 보안 취약점 점검 및 침입 탐지 시스템 운영</li>
        <li>내부 직원 개인정보 교육 실시</li>
      </ul>

      <h2 id="p9">제9조 (개인정보보호책임자)</h2>
      <table>
        <thead><tr><th>구분</th><th>내용</th></tr></thead>
        <tbody>
          <tr><td>개인정보보호책임자</td><td>[담당자명] (법인 등기 후 갱신)</td></tr>
          <tr><td>연락처</td><td>privacy@garim.kr</td></tr>
          <tr><td>처리 기간</td><td>요청 접수 후 10일 이내</td></tr>
        </tbody>
      </table>
      <p>개인정보 침해로 인한 신고·상담은 아래 기관을 이용할 수 있습니다.</p>
      <ul>
        <li>개인정보보호위원회 : <strong>privacy.go.kr</strong> / 국번 없이 182</li>
        <li>경찰청 사이버범죄 신고시스템 : <strong>ecrm.cyber.go.kr</strong></li>
      </ul>

      <div className="callout success">
        <strong>부칙</strong> · 본 방침은 2026년 5월 14일부터 시행합니다.
      </div>
    </>
  );
}

// 마케팅 정보수신 동의
function MarketingContent() {
  return (
    <>
      <div className="callout">
        본 동의는 <strong>선택 사항</strong>입니다. 동의하지 않아도 Garim 서비스의 모든 기본 기능을 이용할 수 있습니다.
      </div>

      <h2 id="m1">제1조 (수신 동의의 목적)</h2>
      <p>Garim 서비스(이하 "회사")는 회원에게 서비스 혜택, 업데이트 소식, 이벤트 및 프로모션 정보를 제공하기 위해 마케팅 정보 수신 동의를 받습니다. 동의 여부는 서비스 <strong>설정 → 알림</strong> 메뉴에서 언제든지 변경할 수 있습니다.</p>

      <h2 id="m2">제2조 (발송 채널 및 정보 내용)</h2>
      <table>
        <thead><tr><th>채널</th><th>발송 내용</th><th>발송 주기</th></tr></thead>
        <tbody>
          <tr><td>이메일</td><td>신규 기능 안내, 요금제 변경 공지, 이벤트·프로모션</td><td>월 1~2회 이내</td></tr>
          <tr><td>서비스 내 알림</td><td>처리 완료, 크레딧 적립, 구독 갱신 안내</td><td>이벤트 발생 시</td></tr>
        </tbody>
      </table>
      <ul>
        <li>서비스의 정상 운영을 위한 <strong>필수 공지(이용약관 변경, 결제 알림 등)는 미동의 시에도 발송</strong>됩니다.</li>
        <li>광고성 정보에는 제목 앞에 <strong>[광고]</strong> 표시를 하여 발송합니다.</li>
      </ul>

      <h2 id="m3">제3조 (수집하는 개인정보 항목)</h2>
      <ul>
        <li><strong>이메일 주소</strong> — 마케팅 정보 발송 목적으로만 사용</li>
        <li>마케팅 목적으로 추가적인 개인정보를 수집하지 않습니다.</li>
      </ul>

      <h2 id="m4">제4조 (보관 기간)</h2>
      <p>마케팅 수신 동의 이력은 동의 철회 후 또는 회원 탈퇴 후 <strong>5년간</strong> 보관됩니다(정보통신망법 제50조 제5항). 이후 즉시 파기합니다.</p>

      <h2 id="m5">제5조 (동의 철회 방법)</h2>
      <p>다음 방법 중 하나로 언제든지 철회할 수 있습니다.</p>
      <ul>
        <li>서비스 내 <strong>설정 → 알림 → 이메일 알림</strong> 에서 OFF 전환</li>
        <li>수신한 마케팅 이메일 하단의 <strong>"수신 거부"</strong> 링크 클릭</li>
        <li>개인정보보호책임자 이메일(privacy@garim.kr)로 철회 요청</li>
      </ul>
      <p>철회 요청은 <strong>영업일 기준 3일 이내</strong>에 처리됩니다.</p>

      <h2 id="m6">제6조 (미동의 시 불이익 없음)</h2>
      <p>마케팅 정보 수신에 동의하지 않아도 Garim의 AI 마스킹, 크레딧 결제, 다운로드 등 <strong>모든 핵심 기능을 동일하게 이용</strong>할 수 있습니다. 다만, 신규 기능 출시나 이벤트 혜택 정보를 빠르게 받아볼 수 없을 수 있습니다.</p>

      <div className="callout success">
        <strong>부칙</strong> · 본 동의는 2026년 5월 14일부터 시행합니다.
      </div>
    </>
  );
}

// 위치기반 서비스
function LocationContent() {
  return (
    <>
      <div className="callout">
        <strong>현재 버전 안내</strong> · Garim v1 (현재 서비스)은 위치 정보를 수집하지 않습니다. 본 약관은 향후 위치 기반 기능(SNS 콘텐츠 지역 필터 등) 도입 시 적용될 사전 공개 약관입니다.
      </div>

      <h2 id="l1">제1조 (목적)</h2>
      <p>본 약관은 <strong>[회사명]</strong>(이하 "회사")이 제공하는 위치기반 서비스(이하 "위치 서비스")의 이용과 관련하여, 「위치정보의 보호 및 이용 등에 관한 법률」(이하 "위치정보법")에 따른 회사와 회원 간의 권리·의무 및 책임사항을 규정합니다.</p>

      <h2 id="l2">제2조 (위치 정보 수집 범위)</h2>
      <h3>현재 v1 서비스</h3>
      <p>현재 Garim 서비스는 위치 정보를 <strong>일절 수집하지 않습니다.</strong> 회원의 접속 IP는 보안 및 부정 이용 방지 목적으로만 수집되며, 위치 특정에는 활용되지 않습니다.</p>
      <h3>향후 v2 예정 기능 (SNS 점검)</h3>
      <p>준비 중인 SNS 점검 기능에서는 다음과 같은 위치 정보 수집이 예정됩니다.</p>
      <table>
        <thead><tr><th>수집 항목</th><th>수집 목적</th><th>수집 방법</th></tr></thead>
        <tbody>
          <tr><td>대략적 국가·지역 정보</td><td>SNS 콘텐츠 지역별 유출 현황 분석</td><td>회원 직접 입력 또는 브라우저 위치 API</td></tr>
        </tbody>
      </table>

      <h2 id="l3">제3조 (서비스 내용)</h2>
      <p>위치기반 서비스가 도입되면 다음 기능에 활용될 예정입니다.</p>
      <ul>
        <li>SNS 플랫폼에서 회원 콘텐츠의 지역별 유출 현황 모니터링</li>
        <li>지역별 위험도 분석 리포트 제공</li>
        <li>위치 기반 무단 유포 신고 자동화</li>
      </ul>
      <p>위 기능은 현재 <strong>개발 준비 중</strong>이며, 도입 시 별도 동의를 다시 받습니다.</p>

      <h2 id="l4">제4조 (보관 및 이용 기간)</h2>
      <ul>
        <li>위치 정보는 서비스 제공 목적 달성 즉시 파기합니다.</li>
        <li>보관이 필요한 경우 익명화 처리 후 통계 목적으로만 활용합니다.</li>
        <li>위치 정보를 제3자에게 제공하거나 공유하지 않습니다.</li>
      </ul>

      <h2 id="l5">제5조 (동의 철회)</h2>
      <p>위치기반 서비스 기능 도입 시, 회원은 다음 방법으로 동의를 철회할 수 있습니다.</p>
      <ul>
        <li>서비스 내 <strong>설정 → 개인정보</strong> 메뉴에서 위치 정보 수집 중단</li>
        <li>개인정보보호책임자(privacy@garim.kr)에 요청</li>
      </ul>

      <h2 id="l6">제6조 (손해배상 및 면책)</h2>
      <p>① 회사는 위치정보법 제15조·제26조에 따라 위치 정보 누출·변조로 인한 손해를 배상할 책임이 있습니다.</p>
      <p>② 다음의 경우 회사는 책임을 지지 않습니다.</p>
      <ul>
        <li>천재지변·불가항력으로 인해 위치기반 서비스를 제공할 수 없는 경우</li>
        <li>회원이 타인의 명의나 기기를 이용하여 발생한 손해</li>
        <li>회원의 위치 정보 부정확으로 인한 서비스 오류</li>
      </ul>

      <div className="callout success">
        <strong>부칙</strong> · 본 약관은 위치기반 서비스 도입 시점부터 시행됩니다. (예정: 2026년 하반기)
      </div>
    </>
  );
}

// AI 학습 데이터 활용 동의
function AILearningContent() {
  return (
    <>
      <div className="callout">
        본 동의는 <strong>선택 사항</strong>입니다. 동의하지 않아도 Garim의 모든 기능을 동일하게 이용할 수 있습니다. 동의 시 매월 처리량의 <strong>10% 환원 크레딧</strong>이 제공됩니다.
      </div>

      <h2 id="a1">제1조 (목적 및 성격)</h2>
      <p>본 동의는 Garim 서비스(이하 "회사")가 제공하는 AI 마스킹·검출 모델의 품질 향상을 위해, 회원의 처리 데이터를 학습에 활용하고자 하는 <strong>완전 선택적 동의</strong>입니다.</p>
      <p>이용약관 제8조에 명시된 바와 같이, 회사는 본 동의 없이는 회원의 어떠한 콘텐츠도 AI 학습에 사용하지 않습니다.</p>

      <h2 id="a2">제2조 (활용하는 데이터 범위)</h2>
      <p>동의 시 다음 데이터만 학습에 활용됩니다.</p>
      <table>
        <thead><tr><th>활용 데이터</th><th>내용</th></tr></thead>
        <tbody>
          <tr><td>처리 메타데이터</td><td>검출된 개인정보 종류, 위치 좌표, 처리 시점, 검출 신뢰도 점수</td></tr>
          <tr><td>미리보기 평가 결과</td><td>사용자가 미리보기에서 검출 결과를 수정·승인·거부한 피드백</td></tr>
          <tr><td>마스킹 품질 평가</td><td>치환 결과물에 대한 사용자 평가 (선택 시)</td></tr>
        </tbody>
      </table>

      <h2 id="a3">제3조 (절대 활용하지 않는 데이터)</h2>
      <div className="callout warning">
        아래 데이터는 동의 여부와 관계없이 AI 학습에 <strong>절대 사용되지 않습니다.</strong>
      </div>
      <ul>
        <li><strong>업로드 원본 파일</strong> — 영상·이미지·음성 파일 자체</li>
        <li><strong>처리 결과 파일</strong> — 마스킹·치환된 최종 결과물</li>
        <li><strong>이메일 주소</strong> — 개인 식별 정보 일체</li>
        <li><strong>결제 정보</strong> — 카드 정보, 결제 내역</li>
        <li><strong>원본 개인정보 내용</strong> — 검출된 텍스트의 실제 값 (이름·전화번호·주소 등)</li>
      </ul>

      <h2 id="a4">제4조 (익명화 처리)</h2>
      <p>활용되는 모든 데이터는 학습 사용 전 다음 절차를 거쳐 익명화됩니다.</p>
      <ul>
        <li>회원 식별자(user_id) 제거 후 비가역적 해시값으로 대체</li>
        <li>처리 메타데이터에서 개인 특정 가능 정보 제거</li>
        <li>위치 좌표는 픽셀 단위로 양자화하여 역추적 불가 처리</li>
        <li>통계적 노이즈 추가(Differential Privacy) 적용</li>
      </ul>

      <h2 id="a5">제5조 (제공 혜택 — v1 정식 출시 후 적용)</h2>
      <table>
        <thead><tr><th>플랜</th><th>월 기본 처리</th><th>환원 크레딧 (+10%)</th><th>실질 처리 가능</th></tr></thead>
        <tbody>
          <tr><td>Free</td><td>5회</td><td>+0.5회 (이월 적립)</td><td>누적 사용 가능</td></tr>
          <tr><td>Pro</td><td>50회</td><td>+5회</td><td>월 55회</td></tr>
          <tr><td>Business</td><td>200회</td><td>+20회</td><td>월 220회</td></tr>
        </tbody>
      </table>
      <p>환원 크레딧은 매월 1일 자동 적립되며, 미사용 크레딧은 최대 3개월간 이월됩니다. 동의 철회 시 다음 달부터 적립이 중단되며, 이미 적립된 크레딧은 유지됩니다.</p>

      <h2 id="a6">제6조 (동의 철회 및 효과)</h2>
      <p>동의는 서비스 <strong>설정 → 데이터 → AI 학습 데이터 활용</strong> 또는 <strong>설정 → 자세히 보기</strong>에서 언제든지 철회할 수 있습니다.</p>
      <div className="callout warning">
        <strong>철회 시 유의 사항</strong><br />
        동의 OFF로 변경한 시점부터 향후 학습에 데이터가 제외됩니다. 단, 이미 학습에 반영된 모델 가중치에서 기여분을 기술적으로 분리하는 것은 어렵습니다 (딥러닝 모델 특성). OFF 변경 시점부터의 새로운 데이터만 학습에서 제외됩니다.
      </div>
      <ul>
        <li>철회 즉시 새 처리 데이터 수집 중단</li>
        <li>다음 달 1일부터 환원 크레딧 적립 중단</li>
        <li>이미 적립된 크레딧은 유효 기간 내 사용 가능</li>
      </ul>

      <h2 id="a7">제7조 (학습 데이터 보관 기간)</h2>
      <table>
        <thead><tr><th>데이터 종류</th><th>보관 기간</th></tr></thead>
        <tbody>
          <tr><td>학습용 메타데이터 (익명화 후)</td><td>모델 폐기 시까지</td></tr>
          <tr><td>미리보기 평가 피드백 (익명화 후)</td><td>최대 3년</td></tr>
          <tr><td>동의 이력</td><td>탈퇴 후 5년 (법무 보존)</td></tr>
        </tbody>
      </table>

      <div className="callout success">
        <strong>부칙</strong> · 환원 크레딧 적립은 Garim v1 정식 출시 후부터 적용됩니다. 본 동의는 2026년 5월 14일부터 시행합니다.
      </div>
    </>
  );
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────────
export default function Terms() {
  useDocumentTitle("약관·개인정보처리방침 · Garim");

  // URL ?tab=privacy 같은 파라미터로 초기 탭 결정
  const [searchParams] = useSearchParams();
  const VALID_TABS = TABS.map((t) => t.id);
  const tabFromUrl = VALID_TABS.includes(searchParams.get("tab"))
    ? searchParams.get("tab")
    : "terms";

  // 현재 활성 탭
  const [activeTab, setActiveTab] = useState(tabFromUrl);

  // URL 파라미터가 바뀔 때마다 탭 동기화 + 스크롤 맨 위
  useEffect(() => {
    setActiveTab(tabFromUrl);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [tabFromUrl]);

  // 탭 클릭 시에도 스크롤 맨 위
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    window.scrollTo({ top: 0, behavior: "instant" });
  };

  const meta = TAB_META[activeTab];

  // 탭별 본문 렌더
  const renderContent = () => {
    switch (activeTab) {
      case "terms":    return <TermsContent />;
      case "privacy":  return <PrivacyContent />;
      case "marketing":return <MarketingContent />;
      case "location": return <LocationContent />;
      case "ai":       return <AILearningContent />;
      default:         return null;
    }
  };

  return (
    <GarimPage bodyClass="" screenLabel="04 Terms">
      <div className="terms-page">
        <div className="terms-head">
          <h1>법적 고지</h1>
        </div>

        {/* 탭 버튼 — 클릭 시 activeTab 전환 */}
        <div className="terms-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={activeTab === tab.id ? "active" : ""}
              onClick={() => handleTabChange(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="terms-grid">
          {/* 좌측 목차 — 탭에 따라 다르게 표시 */}
          <aside className="toc-side">
            <h3>목차</h3>
            {meta.toc.map((item, i) => (
              <a key={item.id} href={`#${item.id}`} className={i === 0 ? "active" : ""}>
                {item.label}
              </a>
            ))}
          </aside>

          {/* 우측 본문 */}
          <main className="terms-content">
            <div className="terms-meta">
              <div>
                <div className="overline">{meta.title}</div>
                <div className="meta-date">{meta.date}</div>
              </div>
              <div className="terms-actions">
                <button className="btn" onClick={() => window.print()}>
                  <span className="material-icons terms-tool-ico">print</span>인쇄
                </button>
                <button className="btn" onClick={() => window.print()}>
                  <span className="material-icons terms-tool-ico">picture_as_pdf</span>PDF
                </button>
              </div>
            </div>

            {renderContent()}
          </main>
        </div>
      </div>
    </GarimPage>
  );
}
