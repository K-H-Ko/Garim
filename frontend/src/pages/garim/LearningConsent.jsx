import { useEffect, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getUserSettings, updateUserSettings } from "../../utils/api";
import "../../css/garim-pages/LearningConsent.css";

import GarimPage from "../../components/garim/GarimPage";

// KST 기준 날짜+시간 포맷
function nowKST() {
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

export default function LearningConsent() {
  useDocumentTitle("학습 데이터 동의 · Garim");

  // 전체 설정값 (다른 필드 보존을 위해 전체 로드)
  const [settings, setSettings] = useState({
    email_notification: true,
    browser_notification: true,
    data_usage_consent: false,
  });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  // 이번 세션에서의 변경 이력 (초기 로드 시 현재 상태 1건 포함)
  const [changeLog, setChangeLog] = useState([]);

  useEffect(() => {
    getUserSettings()
      .then((result) => {
        const loaded_settings = {
          email_notification: Boolean(result.data?.email_notification),
          browser_notification: Boolean(result.data?.browser_notification),
          data_usage_consent: Boolean(result.data?.data_usage_consent),
        };
        setSettings(loaded_settings);
        setLoaded(true);
        // 현재 상태를 이력 첫 항목으로 표시
        setChangeLog([
          {
            date: nowKST(),
            label: "현재 상태 확인",
            value: loaded_settings.data_usage_consent,
          },
        ]);
      })
      .catch(console.error);
  }, []);

  const consent = settings.data_usage_consent;

  const handleToggle = async () => {
    if (saving || !loaded) return;

    const prevSettings = settings;
    const nextConsent = !consent;
    const nextSettings = { ...settings, data_usage_consent: nextConsent };

    // 낙관적 업데이트 (즉시 UI 반영)
    setSettings(nextSettings);
    setSaving(true);

    try {
      const result = await updateUserSettings(nextSettings);
      const saved = {
        email_notification: Boolean(result.data?.email_notification),
        browser_notification: Boolean(result.data?.browser_notification),
        data_usage_consent: Boolean(result.data?.data_usage_consent),
      };
      setSettings(saved);
      // 변경 이력 앞에 추가
      setChangeLog((prev) => [
        {
          date: nowKST(),
          label: saved.data_usage_consent ? "동의 ON 으로 변경" : "동의 OFF 로 변경",
          value: saved.data_usage_consent,
        },
        ...prev,
      ]);
    } catch (err) {
      console.error(err);
      setSettings(prevSettings); // 실패 시 롤백
    } finally {
      setSaving(false);
    }
  };

  return (
    <GarimPage bodyClass="page-app" screenLabel="23 Learning consent">
      <div className="lc-page">
        <a href="/settings#data" className="lc-back">
          <span className="material-icons">
            arrow_back
          </span>
          설정으로 돌아가기
        </a>
        <h1>AI 학습 데이터 활용 동의</h1>
        <p className="sub">
          내 처리 데이터를 모델 개선에 활용할지 결정하세요. 언제든 변경할 수 있습니다 (B-1 동의 분리 원칙).
        </p>

        {/* 메인 토글 카드 — 클릭 시 Settings와 동일한 API 호출 */}
        <div className="toggle-card">
          <button
            type="button"
            className={`big-switch${consent ? " on" : ""}${saving ? " big-switch--saving" : ""}`}
            onClick={handleToggle}
            disabled={saving || !loaded}
            aria-label="AI 학습 데이터 활용 동의 토글"
          >
            <div className="knob">
              <span className="material-icons">
                {consent ? "check" : "close"}
              </span>
            </div>
          </button>
          <div className="lc-toggle-info">
            <div className="title">AI 학습 데이터 활용</div>
            <div className={`state${consent ? " on" : ""}`}>
              {!loaded ? (
                "불러오는 중..."
              ) : consent ? (
                <>현재 <strong>활성화</strong>되어 있습니다 — 내 데이터가 학습에 활용됩니다.</>
              ) : (
                <>현재 <strong>비활성화</strong>되어 있습니다 — 내 데이터는 학습에 사용되지 않습니다.</>
              )}
            </div>
          </div>
        </div>

        <div className="info-cards">
          <div className="info-card on">
            <h3>
              <span className="material-icons">check_circle</span>
              동의 시 — 활성화하면
            </h3>
            <ul>
              <li>내 처리 데이터(메타데이터·미리보기 평가)가 한국어 모델 개선에 활용됩니다</li>
              <li>월 처리량 <strong>10% 환원 크레딧</strong> 제공 (v1 정식 출시 후)</li>
              <li>원본 파일·결과 영상은 학습에 사용되지 않습니다 (메타데이터·평가만)</li>
              <li>익명화 후 처리됩니다</li>
            </ul>
          </div>
          <div className="info-card off">
            <h3>
              <span className="material-icons">shield</span>
              비동의 시 — 비활성 상태
            </h3>
            <ul>
              <li>내 데이터는 절대 모델 학습에 사용되지 않습니다</li>
              <li>처리 메타데이터는 워터마크 역추적용으로만 90일 보관</li>
              <li>환원 크레딧 없음</li>
              <li>서비스 이용에는 차이 없습니다</li>
            </ul>
          </div>
        </div>

        <div className="credit-card">
          <div className="icon-box">
            <span className="material-icons">redeem</span>
          </div>
          <div>
            <h3>환원 크레딧 — v1 정식 출시 후</h3>
            <p>
              학습 동의 활성 사용자는 매월 처리량의 10%가 추가 적립됩니다. Pro 플랜(월 50회) 기준 +5회 = 월 55회.
            </p>
          </div>
        </div>

        {/* 변경 이력 — 이번 세션 기준 동적 표시 */}
        <div className="changelog">
          <h3>변경 이력</h3>
          {changeLog.map((entry, i) => (
            <div key={i} className="change-row">
              <span className="date">{entry.date}</span>
              <span className="lc-log-text">
                {entry.label} ·{" "}
                <strong className={`lc-log-state${entry.value ? " lc-log-state--on" : ""}`}>
                  {entry.value ? "ON" : "OFF"}
                </strong>
              </span>
            </div>
          ))}
        </div>

        <div className="legal-note">
          <strong>중요 안내</strong>
          <br />
          동의 ON → OFF로 변경하더라도, 이미 학습된 모델의 가중치에서 사용자별 기여 분을 기술적으로 분리하는 것은 어렵습니다.
          OFF 변경 시점부터 향후 학습에서만 제외됩니다. 자세한 내용은{" "}
          <a href="/terms" className="lc-terms-link">AI 학습 데이터 활용 약관</a>을 확인하세요.
        </div>
      </div>
    </GarimPage>
  );
}
