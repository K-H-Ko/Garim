import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useAuthStatus } from "../../hooks/useAuthStatus";
import "../../css/garim-pages/Landing.css";

import GarimPage from "../../components/garim/GarimPage";
import ComparisonSlider from "../../components/garim/ComparisonSlider";

// 랜딩 데모용 비교 이미지 (탐지 전 원본 / 마스킹 처리 결과)
const DEMO = {
  card: {
    original: "https://i.imgur.com/0HCFwMh.png", // 카드 탐지(원본)
    masked: "https://i.imgur.com/jFTMERt.png",   // 카드 처리(마스킹)
  },
  mail: {
    original: "https://i.imgur.com/WVAmYrC.png", // 우편 탐지(원본)
    masked: "https://i.imgur.com/H7n7E2C.png",   // 우편 처리(마스킹)
  },
};

export default function Landing() {
  useDocumentTitle("Garim — 영상 속 개인정보, 자연스럽게 가립니다");
  const isAuthed = useAuthStatus();
  const startHref = isAuthed
    ? "/upload"
    : `/login?next=${encodeURIComponent("/upload")}`;

  return (
    <GarimPage bodyClass="page-public" screenLabel="01 Landing">
      <section className="hero">
        <span className="mui-chip mui-chip--secondary mui-chip--md hero__chip">
          🛡 데이터 도싱 방지 · 한국 특화
        </span>
        <h1>
          영상 속 개인정보,
          <br />
          <span className="accent">
            자연스럽게
          </span>
          가립니다.
        </h1>
        <p className="lead">
          택배송장·우편물·신분증/카드·음성 등 <br />AI가 빠르게 찾아내고, 자연스럽게 가려줍니다
        </p>
        <div className="hero__cta">
          <a href={startHref} className="mui-btn mui-btn--contained mui-btn--lg">
            무료로 시작하기 →
          </a>
          <a href="/pricing" className="mui-btn mui-btn--outlined mui-btn--lg">
            요금제 보기
          </a>
        </div>
        <p className="pc-optimized-notice">
          ※ 가림(GARIM) 서비스는 현재 <b>PC(데스크탑) 환경에 최적화</b> 되어 있습니다.
        </p>
      </section>
      {/* ── 가림바 비교 데모 — 좌: 카드 / 우: 우편(택배 송장) ── */}
      <section className="section">
        <h2>
          <span className="accent">직접</span> 확인해보세요
        </h2>
        <p className="lead">
          가림바를 좌우로 움직여, 탐지된 개인정보가 어떻게 가려지는지 비교해보세요.
        </p>
        <div className="demo-compare-grid">
          <div className="demo-compare-item">
            <h3 className="demo-compare-title">영상 처리 (캡처 이미지로 제공)</h3>
            <ComparisonSlider
              mode="image"
              originalSrc={DEMO.card.original}
              maskedSrc={DEMO.card.masked}
            />
          </div>
          <div className="demo-compare-item">
            <h3 className="demo-compare-title">이미지 처리</h3>
            <ComparisonSlider
              mode="image"
              originalSrc={DEMO.mail.original}
              maskedSrc={DEMO.mail.masked}
            />
          </div>
        </div>
      </section>
      <section className="section section--alt">
        <h2>
          지금 일어나고 있는 일
        </h2>
        <p className="lead">
          SNS에 무심코 올린 영상 한 컷이 신상 도싱·스토킹의 단서가 됩니다.
        </p>
        <div className="stat-grid landing-stats">
          <div className="stat-card">
            <div className="num">
              23.1
              <small className="landing-stat-unit">
                %
              </small>
            </div>
            <div className="lbl">
              2024년 스토킹 신고 증가율
              <br />
              (경찰청 자료)
            </div>
          </div>
          <div className="stat-card">
            <div className="num">
              <span className="accent">
                2,345
              </span>
            </div>
            <div className="lbl">
              이번 주 Garim이 처리한 영상 평균
              <br />
              발견 개인정보 (영상당 평균 6.4건)
            </div>
          </div>
          <div className="stat-card">
            <div className="num">
              87
              <small className="landing-stat-unit">
                %
              </small>
            </div>
            <div className="lbl">
              한국어 영상에서 기존 자동 모자이크
              <br />
              도구가 놓치는 정보 비율
            </div>
          </div>
        </div>
        <div className="problem-cards">
          <div className="problem-card">
            <span className="material-icons">
              local_shipping
            </span>
            <h4>
              택배 송장
            </h4>
            <p>
              이름·주소·전화번호가 한 장에 — <bR />도싱의 1순위 단서
            </p>
          </div>
          <div className="problem-card">
            <span className="material-icons">
              directions_car
            </span>
            <h4>
              차량 번호판
            </h4>
            <p>
              무심코 촬영된 아파트 주차장에서 <br />차량 번호판 노출
            </p>
          </div>
          <div className="problem-card">
            <span className="material-icons">
              credit_card
            </span>
            <h4>
              신분증 / 금융카드
            </h4>
            <p>
              나도 모르게 촬영된 신분증 / 금융카드 <br />정보 노출
            </p>
          </div>
          <div className="problem-card">
            <span className="material-icons">
              record_voice_over
            </span>
            <h4>
              음성 속 주소 / 전화번호
            </h4>
            <p>
              "경기도 양주시~ / 공일공 일이삼사~" 등 <br />음성 노출
            </p>
          </div>
        </div>
      </section>
      <section className="section">
        <h2>
          <span className="accent">
            세 가지가 다릅니다
          </span>
        </h2>
        <p className="lead">
          단순 모자이크가 아닙니다. 한국 환경에 맞춘 검출과, 자연스러운 제거 효과.
        </p>
        <div className="feature-grid">
          <div className="feature-card">
            <div className="feature-card__ico">
              <span className="material-icons">
                visibility
              </span>
            </div>
            <h3>
              검출은 영원히 무료
            </h3>
            <p>
              내 영상에 어떤 개인정보가 있는지 보는 데에는 비용이 들지 않습니다. 결제는 가릴 때만.
            </p>
            <span className="mui-chip mui-chip--soft-success landing-feat-chip">
              무료 탐지
            </span>
          </div>
          <div className="feature-card">
            <div className="feature-card__ico feature-card__ico--secondary">
              <span className="material-icons">
                translate
              </span>
            </div>
            <h3>
              OCR 최적화
            </h3>
            <p>
              택배사 송장 양식·국내 번호판·한국어 호칭·EXIF GPS까지. 글로벌 도구가 놓치는 87%를 포착합니다.
            </p>
            <span className="mui-chip mui-chip--soft-info landing-feat-chip">
              한국어 특화 OCR 모델
            </span>
          </div>
          <div className="feature-card">
            <div className="feature-card__ico feature-card__ico--success">
              <span className="material-icons">
                layers
              </span>
            </div>
            <h3>
              영상 · 이미지 · 음성
            </h3>
            <p>
              한 번의 업로드로 시각·청각 모두 점검. 영상은 프레임마다, 음성은 1초 단위로 분석하여, 도싱 위험있는 개인정보를 찾아 지워드립니다.
            </p>
            <span className="mui-chip mui-chip--soft-warning landing-feat-chip">
              OpenCV + LaMa + Whisper
            </span>
          </div>
        </div>
      </section>
      <section className="section section--alt">
        <h2>
          사용 흐름
        </h2>
        <p className="lead">
          파일을 올리고, 결과를 보고, 가립니다. 그게 전부입니다.
        </p>
        <div className="steps">
          <div className="step">
            <div className="step__num">
              1
            </div>
            <h4>
              업로드
            </h4>
            <p>
              영상·이미지·음성 파일을 드래그
              <br />
              1080p / 2GB / 30분까지 지원.
            </p>
          </div>
          <div className="step">
            <div className="step__num step__num--secondary">
              2
            </div>
            <h4>
              검출 (무료)
            </h4>
            <p>
              위험 항목 리포트.
              <br />
              시점·위치·위험도 확인.
            </p>
          </div>
          <div className="step">
            <div className="step__num step__num--success">
              3
            </div>
            <h4>
              치환
            </h4>
            <p>
              자동/사용자 지정/마스킹 중 선택.
              <br />
              워터마크 없는 결과 다운로드.
            </p>
          </div>
        </div>
      </section>
      <section className="closing-cta">
        <h2>
          지금 내 영상 / 이미지에
        </h2>
        <p>
          무엇이 노출돼 있는지, 한 번 확인해보세요.
        </p>
        <div className="closing-cta__actions">
          <a href={startHref} className="mui-btn mui-btn--contained mui-btn--lg">
            무료로 시작하기 →
          </a>
          <a href="/pricing" className="mui-btn mui-btn--outlined mui-btn--lg">
            요금제 보기
          </a>
        </div>
        <p className="pc-optimized-notice alt">
          ※ 가림(GARIM) 서비스는 현재 <b>PC(데스크탑) 환경에 최적화</b> 되어 있습니다.
        </p>
      </section>
    </GarimPage>
  );
}
