import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/Faq.css";

import GarimPage from "../../components/garim/GarimPage";

export default function Faq() {
  useDocumentTitle("도움말·FAQ · Garim");

  return (
    <GarimPage bodyClass="page-public" screenLabel="03 FAQ">
      <div className="faq-page">
        <div className="faq-head">
          <h1>
            무엇을 도와드릴까요?
          </h1>
          <div className="search-bar">
            <span className="material-icons">
              search
            </span>
            <input type="text" placeholder="키워드 검색 — 예: 한국어 음성, 환불, 자동 삭제" />
          </div>
        </div>
        <div className="faq-grid">
          <aside className="cat-side">
            <h3>
              카테고리
            </h3>
            <a href="#" className="active">
              <span className="material-icons faq-ico">
                apps
              </span>
              전체
              <span className="count">
                42
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                play_arrow
              </span>
              시작하기
              <span className="count">
                6
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                visibility
              </span>
              검출 기능
              <span className="count">
                8
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                visibility_off
              </span>
              치환 기능
              <span className="count">
                11
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                payment
              </span>
              결제·환불
              <span className="count">
                5
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                lock
              </span>
              데이터·보안
              <span className="count">
                7
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                share
              </span>
              SNS 연동
              <span className="count">
                3
              </span>
            </a>
            <a href="#">
              <span className="material-icons faq-ico">
                tune
              </span>
              입력 사양
              <span className="count">
                2
              </span>
            </a>
          </aside>
          <main className="faq-list">
            <h2>
              인기 질문 Top 5
            </h2>
            <div className="crumb">
              자주 본 순서대로 정렬
            </div>
            <details className="accordion" open="">
              <summary>
                <h4>
                  한국어 영상에서 자동 치환이 자연스럽지 않으면 어떻게 하나요?
                </h4>
                <span className="material-icons">
                  expand_more
                </span>
              </summary>
              <div className="answer">
                한국어 자연어 합성(STE)은 글자 수와 음운 환경에 민감합니다. Garim은 "처리 전 미리보기"(페이지 16)에서 결과를 먼저 확인할 수 있게 합니다. 자연스럽지 않다면 "옵션 수정"에서 다음을 시도해보세요:
                <br />
                <br />
                1)
                <strong>
                  사용자 지정
                </strong>
                입력 — 원본과 동일한 글자 수로 작성 (3자→3자 강제)
                <br />
                2)
                <strong>
                  마스킹
                </strong>
                으로 전환 — 블러 또는 모자이크
                <br />
                3)
                <strong>
                  건너뛰기
                </strong>
                — 일부만 안전한 경우 해당 항목 처리 제외
              </div>
              <div className="feedback">
                <span className="caption-k">
                  도움이 되었나요?
                </span>
                <button>
                  <span className="material-icons faq-ico">
                    thumb_up
                  </span>
                  도움됨
                </button>
                <button>
                  <span className="material-icons faq-ico">
                    thumb_down
                  </span>
                  아니요
                </button>
              </div>
            </details>
            <details className="accordion">
              <summary>
                <h4>
                  처리한 영상은 얼마나 보관되나요?
                </h4>
                <span className="material-icons">
                  expand_more
                </span>
              </summary>
              <div className="answer">
                원본은 처리 완료 후 12시간 내 자동 삭제됩니다. 결과 영상은 플랜별로 Free 7일, 1회권 30일, Pro 90일 후 삭제됩니다. 마이페이지에서 언제든 수동 삭제도 가능합니다 (B-1 자동 삭제 정책).
              </div>
            </details>
            <details className="accordion">
              <summary>
                <h4>
                  음성 속 이름·전화번호도 검출되나요?
                </h4>
                <span className="material-icons">
                  expand_more
                </span>
              </summary>
              <div className="answer">
                네. Whisper로 한국어 음성을 텍스트로 변환한 후, KoELECTRA로 개인정보 패턴을 검출합니다. 음성 마스킹은 "삐 1000Hz" 또는 "묵음" 중 선택할 수 있습니다 (페이지 15).
              </div>
            </details>
            <details className="accordion">
              <summary>
                <h4>
                  Instagram에 자동으로 다시 올려주나요?
                </h4>
                <span className="material-icons">
                  expand_more
                </span>
              </summary>
              <div className="answer">
                아니요. Garim은 인스타에 직접 게시·삭제하지 않습니다 (B-2 권한 정책). 결과 영상을 다운로드한 후, 사용자가 직접 기존 게시물을 삭제하고 새 버전을 업로드하는 흐름입니다. SNS 진단 페이지(12)와 다운로드 페이지(18)에서 단계별 가이드를 제공합니다.
              </div>
            </details>
            <details className="accordion">
              <summary>
                <h4>
                  워터마크는 왜 들어가나요? 제거할 수 있나요?
                </h4>
                <span className="material-icons">
                  expand_more
                </span>
              </summary>
              <div className="answer">
                MVP1 단계의 모든 결과물에는 식별 워터마크가 자동 적용됩니다 (B-3 정책). 이는 위변조 의심 시 역추적 가능성을 확보하기 위함이며, 시각적 워터마크는 작게 우하단에 표시되고, 별도의 보이지 않는 워터마크가 함께 삽입됩니다. v1 정식 출시 후 1회권·Pro 이상에서 시각적 워터마크가 제거됩니다 (보이지 않는 워터마크는 유지).
              </div>
            </details>
            <div className="contact-card">
              <div className="faq-contact-ico">
                <span className="material-icons">
                  support_agent
                </span>
              </div>
              <div className="faq-contact-body">
                <h3>
                  원하는 답을 못 찾으셨나요?
                </h3>
                <p>
                  support@garim.kr 로 문의해주세요. 평균 4시간 이내 답변 드립니다.
                </p>
              </div>
              <Link to="/support" className="mui-btn mui-btn--contained">
                문의하기
              </Link>
            </div>
          </main>
        </div>
      </div>
    </GarimPage>
  );
}
