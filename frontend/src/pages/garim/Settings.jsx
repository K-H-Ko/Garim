import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useAuthUser } from "../../hooks/useAuthStatus";
import {
  getUserSettings,
  logout as requestLogout,
  updateUserSettings,
  deleteAccount,
  getMyPaymentInfo, // 백엔드 결제 조회 API 함수 임포트
  getMyLoginHistories, // 최근 로그인 이력 API 함수 임포트
} from "../../utils/api";
import "../../css/garim-pages/Settings.css";

import GarimPage from "../../components/garim/GarimPage";

const DEFAULT_SETTINGS = {
  email_notification: true,
  browser_notification: true,
  data_usage_consent: true,
};

// --- 한국 시간(KST) 변환 유틸리티 함수 ---
function formatToKST(dateString, isDateOnly = false) {
  if (!dateString) return "-";

  // 백엔드에서 온 데이터에 타임존 표시(Z나 +)가 없다면 UTC로 간주하여 'Z'를 붙여줍니다.
  let safeString = dateString;
  if (!safeString.includes("Z") && !safeString.includes("+")) {
    safeString += "Z";
  }

  const date = new Date(safeString);

  if (isDateOnly) {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

// --- User-Agent 파싱 유틸리티 함수 ---
function parseUserAgent(uaString) {
  if (!uaString) return "Unknown Device";
  let browser = "Unknown Browser";
  let os = "Unknown OS";

  // Browser (순서 중요: Whale, Edge 등이 Chrome보다 먼저 와야 함)
  if (uaString.includes("Whale")) browser = "Whale";
  else if (uaString.includes("Edg")) browser = "Edge";
  else if (uaString.includes("Chrome")) browser = "Chrome";
  else if (uaString.includes("Safari") && !uaString.includes("Chrome")) browser = "Safari";
  else if (uaString.includes("Firefox")) browser = "Firefox";

  // OS
  if (uaString.includes("Windows NT 10.0")) os = "Windows 10/11";
  else if (uaString.includes("Windows")) os = "Windows";
  else if (uaString.includes("Mac OS X")) os = "macOS";
  else if (uaString.includes("Linux")) os = "Linux";
  else if (uaString.includes("Android")) os = "Android";
  else if (uaString.includes("iOS") || uaString.includes("iPhone") || uaString.includes("iPad")) os = "iOS";

  return `${browser} / ${os}`;
}
// ----------------------------------------

export default function Settings() {
  useDocumentTitle("프로필·환경 설정 · Garim");
  const navigate = useNavigate();
  const { user } = useAuthUser();
  const [activeSection, setActiveSection] = useState("profile");
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [savingField, setSavingField] = useState("");
  const userEmail = user?.email || "";

  // 유료 결제 내역 및 모달 상태
  const [paymentHistory, setPaymentHistory] = useState([]);
  const [planInfo, setPlanInfo] = useState({ name: "무료 플랜", date: null });
  const [isPremium, setIsPremium] = useState(false);
  const [selectedReceipt, setSelectedReceipt] = useState(null);

  // 로그인 이력 상태
  const [loginHistories, setLoginHistories] = useState([]);

  useEffect(() => {
    const syncActiveSection = () => {
      setActiveSection(window.location.hash.replace("#", "") || "profile");
    };

    syncActiveSection();
    window.addEventListener("hashchange", syncActiveSection);
    return () => window.removeEventListener("hashchange", syncActiveSection);
  }, []);

  useEffect(() => {
    let isMounted = true;

    // 설정 정보 가져오기
    getUserSettings()
      .then((result) => {
        if (!isMounted) return;
        setSettings({
          email_notification: Boolean(result.data?.email_notification),
          browser_notification: Boolean(result.data?.browser_notification),
          data_usage_consent: Boolean(result.data?.data_usage_consent),
        });
      })
      .catch((error) => {
        console.error("Failed to load user settings", error);
      });

    // 백엔드 API로부터 플랜 및 결제 내역 리스트 조회
    getMyPaymentInfo()
      .then((data) => {
        if (!isMounted) return;
        if (data) {
          setIsPremium(data.is_premium);
          setPlanInfo({
            name: data.plan_name || "무료 플랜",
            date: data.plan_date,
          });
          setPaymentHistory(data.payment_history || []);
        }
      })
      .catch((error) => console.error("결제 정보 로드 실패", error));

    // 최근 로그인 이력 조회
    getMyLoginHistories()
      .then((res) => {
        if (!isMounted) return;
        if (res.data) {
          setLoginHistories(res.data);
        }
      })
      .catch((error) => console.error("로그인 이력 로드 실패", error));

    return () => {
      isMounted = false;
    };
  }, []);

  const getNavClassName = (section) =>
    activeSection === section ? "active" : "";

  const handleNavClick = (e, section) => {
    e.preventDefault();
    setActiveSection(section);
    document
      .getElementById(section)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleLogout = async () => {
    if (isLoggingOut) return;
    try {
      setIsLoggingOut(true);
      await requestLogout();
      navigate("/", { replace: true });
    } catch (error) {
      console.error("Logout failed", error);
      setIsLoggingOut(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (isDeletingAccount) return;
    try {
      setIsDeletingAccount(true);
      await deleteAccount();
      navigate("/", { replace: true });
    } catch (error) {
      console.error("Account deletion failed", error);
      setIsDeletingAccount(false);
    }
  };

  const openDeleteModal = () => {
    setDeleteConfirmText("");
    setShowDeleteModal(true);
  };

  const closeDeleteModal = () => {
    setShowDeleteModal(false);
    setDeleteConfirmText("");
  };

  const handleToggleSetting = async (field) => {
    if (savingField) return;
    const nextSettings = { ...settings, [field]: !settings[field] };
    const previousSettings = settings;
    setSettings(nextSettings);
    setSavingField(field);
    try {
      const result = await updateUserSettings(nextSettings);
      setSettings({
        email_notification: Boolean(result.data?.email_notification),
        browser_notification: Boolean(result.data?.browser_notification),
        data_usage_consent: Boolean(result.data?.data_usage_consent),
      });
    } catch (error) {
      console.error("Failed to update user settings", error);
      setSettings(previousSettings);
    } finally {
      setSavingField("");
    }
  };

  const renderSwitch = (field, label) => (
    <button
      type="button"
      className={`switch ${settings[field] ? "on" : ""}`}
      role="switch"
      aria-checked={settings[field]}
      aria-label={label}
      disabled={savingField === field}
      onClick={() => handleToggleSetting(field)}
    >
      <span className="knob"></span>
    </button>
  );

  return (
    <GarimPage bodyClass="" screenLabel="22 Settings">
      <div className="set-page">
        <aside className="set-nav">
          <h2>설정</h2>
          <a
            href="#profile"
            className={getNavClassName("profile")}
            onClick={(e) => handleNavClick(e, "profile")}
          >
            <span className="material-icons">person</span>
            프로필
          </a>
          <a
            href="#plan"
            className={getNavClassName("plan")}
            onClick={(e) => handleNavClick(e, "plan")}
          >
            <span className="material-icons">card_membership</span>
            플랜
          </a>
          <a
            href="#notif"
            className={getNavClassName("notif")}
            onClick={(e) => handleNavClick(e, "notif")}
          >
            <span className="material-icons">notifications</span>
            알림
          </a>
          <a
            href="#security"
            className={getNavClassName("security")}
            onClick={(e) => handleNavClick(e, "security")}
          >
            <span className="material-icons">lock</span>
            보안
          </a>
          <a
            href="#data"
            className={getNavClassName("data")}
            onClick={(e) => handleNavClick(e, "data")}
          >
            <span className="material-icons">storage</span>
            데이터
          </a>
          <a href="/terms">
            <span className="material-icons">description</span>
            약관
          </a>
          <a
            href="#danger"
            className={`set-nav-danger ${getNavClassName("danger")}`}
            onClick={(e) => handleNavClick(e, "danger")}
          >
            <span className="material-icons set-ico-danger">
              warning
            </span>
            위험 영역
          </a>
        </aside>
        <main className="set-main">
          <h1>프로필·환경 설정</h1>
          <div className="set-section" id="profile">
            <div className="set-section-head">
              <h3>프로필</h3>
              <button
                className="mui-btn mui-btn--outlined mui-btn--sm"
                type="button"
                onClick={handleLogout}
                disabled={isLoggingOut}
              >
                {isLoggingOut ? "로그아웃 중" : "로그아웃"}
              </button>
            </div>
            <p className="sub">실명·전화번호는 받지 않습니다.</p>
            <div className="set-field">
              <label>이메일</label>
              <input value={userEmail} readOnly />
            </div>
          </div>

          <div className="set-section" id="plan">
            <h3>플랜</h3>
            <p className="sub">
              현재 이용 중인 요금제와 결제 내역을 확인합니다.
            </p>

            {/* 현재 이용 중인 플랜 박스 */}
            <div
              style={{
                marginTop: "24px",
                padding: "16px",
                border: "1px solid var(--mui-divider)",
                borderRadius: "8px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <strong
                    style={{
                      fontSize: "16px",
                      color: isPremium ? "#1976d2" : "inherit",
                    }}
                  >
                    {/* 크레딧 글자 필터링 부분 */}
                    {planInfo.name.includes("크레딧")
                      ? paymentHistory.find(
                        (pay) => !pay.orderName.includes("크레딧"),
                      )?.orderName || "무료 플랜"
                      : planInfo.name}
                  </strong>
                  <span
                    style={{
                      marginLeft: "8px",
                      fontSize: "13px",
                      color: "var(--fg-2)",
                    }}
                  >
                    사용 중
                  </span>

                  {planInfo.date && (
                    <div
                      style={{
                        fontSize: "13px",
                        color: "var(--fg-3)",
                        marginTop: "6px",
                      }}
                    >
                      구독 시작일: {formatToKST(planInfo.date, true)}
                    </div>
                  )}
                </div>
                <div className="set-row-12">
                  {isPremium ? (
                    <>
                      <span className="mui-chip mui-chip--soft-success">
                        Active
                      </span>
                      <a
                        href="/billing"
                        className="mui-btn mui-btn--outlined mui-btn--sm"
                      >
                        구독 관리
                      </a>
                    </>
                  ) : (
                    <a
                      href="/pricing"
                      className="mui-btn mui-btn--contained mui-btn--sm"
                    >
                      업그레이드
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* 결제 내역 박스 */}
            <div className="set-mt-32">
              <h4 className="set-subhead">
                결제 내역
              </h4>
              <div
                style={{
                  border: "1px solid var(--mui-divider)",
                  borderRadius: "8px",
                  padding: "0 16px",
                }}
              >
                {paymentHistory.length > 0 ? (
                  paymentHistory.map((pay, index) => (
                    <div
                      key={pay.orderId}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "16px 0",
                        borderBottom:
                          index < paymentHistory.length - 1
                            ? "1px dashed var(--mui-divider)"
                            : "none",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          flex: 1,
                        }}
                      >
                        <div
                          style={{
                            minWidth: "120px",
                            fontWeight: "500",
                            fontSize: "14px",
                          }}
                        >
                          {pay.orderName}
                        </div>
                        <div
                          style={{
                            flex: 1,
                            borderBottom: "1px dotted #ccc",
                            margin: "0 16px",
                            transform: "translateY(4px)",
                          }}
                        ></div>
                        <div
                          style={{
                            color: "var(--fg-3)",
                            fontSize: "13px",
                            minWidth: "90px",
                            textAlign: "right",
                            marginRight: "16px",
                          }}
                        >
                          {formatToKST(pay.approvedAt, true)}
                        </div>
                      </div>
                      <button
                        className="mui-btn mui-btn--outlined mui-btn--sm"
                        onClick={() => setSelectedReceipt(pay)}
                      >
                        결제 영수증 확인
                      </button>
                    </div>
                  ))
                ) : (
                  <div
                    style={{
                      padding: "24px 0",
                      textAlign: "center",
                      color: "var(--fg-3)",
                      fontSize: "13px",
                    }}
                  >
                    결제 내역이 없습니다.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="set-section" id="notif">
            <h3>알림</h3>
            <p className="sub">
              처리 완료·자동 삭제 임박 등 알림 채널을 선택합니다.
            </p>
            <div className="row-toggle">
              <div className="text">
                <div className="t">처리 완료 이메일 </div>
                <div className="s">치환 완료·실패 시 이메일 발송 (미구현 개발중)</div>
              </div>
              {renderSwitch("email_notification", "처리 완료 이메일")}
            </div>
            <div className="row-toggle">
              <div className="text">
                <div className="t">처리 완료 브라우저 푸시</div>
                <div className="s">웹 브라우저 푸시 알림 (권한 허용 시)</div>
              </div>
              {renderSwitch("browser_notification", "처리 완료 브라우저 푸시")}
            </div>
          </div>

          <div className="set-section" id="security">
            <h3>보안</h3>
            <p className="sub">로그인 이력 관리</p>
            <div className="set-mt-24">
              <label className="set-login-label">
                최근 로그인 (최근 5건만 표시)
              </label>
              <div className="login-list">
                {loginHistories.length > 0 ? (
                  loginHistories.map((history, idx) => (
                    <div className="row" key={history.id}>
                      <span className="set-flex1">
                        {formatToKST(history.logged_in_at, false)} · {history.provider} / {parseUserAgent(history.user_agent)}
                      </span>
                      {idx === 0 && (
                        <span className="mui-chip mui-chip--soft-success set-chip-mr">
                          현재 세션
                        </span>
                      )}
                      <span className="ip">{history.ip_address}</span>
                    </div>
                  ))
                ) : (
                  <div className="row">
                    <span className="set-flex1-muted">로그인 이력이 없습니다.</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="set-section" id="data">
            <h3>데이터</h3>
            <p className="sub">처리 데이터 활용·자동 삭제·내려받기 설정.</p>
            <div className="row-toggle">
              <div className="text">
                <div className="t set-title-row">
                  AI 학습 데이터 활용 동의
                  <a
                    href="/learning-consent"
                    className="mui-btn mui-btn--outlined mui-btn--sm set-detail-link"
                  >
                    자세히
                  </a>
                </div>
              </div>
              {renderSwitch("data_usage_consent", "AI 학습 데이터 활용 동의")}
            </div>
            <div
              style={{
                marginTop: "16px",
                padding: "12px 16px",
                background: "rgba(25,118,210,0.04)",
                borderRadius: "4px",
                font: "400 12px/1.5 var(--font-sans)",
                color: "var(--fg-2)",
              }}
            >
              <strong className="set-policy-strong">자동 삭제 정책</strong>— 원본
              파일은 처리 후 12시간 / 결과 파일은 플랜별 (Free 7일·Pro 90일) /
              처리 메타데이터는 90일 (워터마크 역추적용).
            </div>
          </div>
          <div className="set-section" id="danger">
            <h3 className="set-danger-title">위험 영역</h3>
            <div className="danger">
              <h4>계정 삭제</h4>
              <p>
                계정과 모든 데이터가 영구히 삭제됩니다. 결제 이력은 법적 보관
                의무로 90일간 별도 보존됩니다.
              </p>
              <button
                className="mui-btn mui-btn--outlined set-danger-btn"
                onClick={openDeleteModal}
              >
                계정 삭제 신청 →
              </button>
            </div>
          </div>
        </main>
      </div>
      {showDeleteModal && (
        <div className="delete-modal-overlay" onClick={closeDeleteModal}>
          <div className="delete-modal" onClick={(e) => e.stopPropagation()}>
            <h3>계정 삭제</h3>
            <p>
              계정과 모든 데이터가 영구히 삭제됩니다. 결제 이력은 법적 보관
              의무로 90일간 별도 보존됩니다.
            </p>
            <p className="delete-modal-instruction">
              삭제를 진행하시려면 아래에 &lsquo;복구 안됨&rsquo; 이라는 메세지를
              작성해주세요.
            </p>
            <input
              className="delete-modal-input"
              type="text"
              placeholder="복구 안됨"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
            />
            <div className="delete-modal-actions">
              <button
                className="mui-btn mui-btn--outlined mui-btn--sm"
                onClick={closeDeleteModal}
              >
                취소
              </button>
              <button
                className="mui-btn mui-btn--sm delete-modal-confirm-btn"
                onClick={handleDeleteAccount}
                disabled={
                  deleteConfirmText !== "복구 안됨" || isDeletingAccount
                }
              >
                {isDeletingAccount ? "처리 중…" : "삭제"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 결제 영수증 모달 */}
      {selectedReceipt && (
        <div
          className="receipt-modal-overlay"
          onClick={() => setSelectedReceipt(null)}
        >
          <div className="receipt-modal" onClick={(e) => e.stopPropagation()}>
            <div className="receipt-modal-head">
              <span
                className="material-icons"
                style={{
                  color: "#2e7d32",
                  fontSize: "36px",
                  marginBottom: "8px",
                }}
              >
                check_circle
              </span>
              <h3>결제 승인이 완료되었습니다.</h3>
              <p className="success-text">결제 성공</p>
            </div>
            <div className="receipt-modal-body">
              <div className="row">
                <span className="lbl">결제 일시</span>
                <span className="val">
                  {formatToKST(selectedReceipt.approvedAt, false)}
                </span>
              </div>
              <div className="row">
                <span className="lbl">주문명</span>
                <span className="val set-val-bold">
                  {selectedReceipt.orderName}
                </span>
              </div>
              <div className="row">
                <span className="lbl">주문번호</span>
                <span className="val set-order-id">
                  {selectedReceipt.orderId}
                </span>
              </div>
              <div className="row">
                <span className="lbl">결제 수단</span>
                <span className="val">{selectedReceipt.method}</span>
              </div>
              <div className="row total">
                <span className="lbl">결제 금액</span>
                <span className="val price">
                  {Number(selectedReceipt.amount).toLocaleString()}원
                </span>
              </div>
            </div>
            <div className="receipt-modal-actions">
              <button
                className="mui-btn mui-btn--contained mui-btn--block set-w-full"
                onClick={() => setSelectedReceipt(null)}
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </GarimPage>
  );
}
