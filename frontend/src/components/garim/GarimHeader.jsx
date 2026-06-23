/*
코드 설명:
Garim 공통 헤더 컴포넌트. layout(public/app/landing/auth/admin)에 따라 네비게이션·사용자 정보·
알림 드롭다운·테마 토글을 조합해 렌더하고, 로그인 상태와 사용자 플랜/크레딧을 표시한다.
*/
import { Link } from "react-router-dom";
import { useRef, useState, useEffect } from "react";

import "../../css/components/GarimHeader.css";
import { useAuthStatus } from "../../hooks/useAuthStatus";
import { useNotifications, relativeTime } from "../../context/NotificationContext";
import { useTheme } from "../../context/ThemeContext";
import { getCurrentUser, getMyPaymentInfo, getMyCreditBalance } from "../../utils/api";

// 라이트/다크 테마 토글 버튼 — 모든 헤더 레이아웃에서 공통 사용.
// 현재 테마에 따라 해/달 아이콘을 보여주고, 클릭 시 전역 테마를 전환한다.
function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      className="gh__icon"
      type="button"
      onClick={toggleTheme}
      title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
      aria-label={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
    >
      <span className="material-icons">{isDark ? "light_mode" : "dark_mode"}</span>
    </button>
  );
}

const publicNav = [
  { id: "detect", label: "탐지", to: "/upload" },
  { id: "sns", label: "SNS 점검(준비중)", onClick: () => alert("준비중입니다. 커밍쑨!") },
  { id: "pricing", label: "요금제", to: "/pricing" },
  { id: "help", label: "도움말", to: "/faq" },
];

function buildLoginUrl(nextPath) {
  return nextPath ? `/login?next=${encodeURIComponent(nextPath)}` : "/login";
}

// 알림 드롭다운 컴포넌트 (헤더 종 모양 클릭 시 펼쳐지는 풍선)
function NotificationDropdown({ notifications, onClose }) {
  return (
    <div className="gh__notif-dropdown">
      <div className="gh__notif-header">
        <span>알림</span>
        <button className="gh__notif-close" onClick={onClose} type="button">
          <span className="material-icons">close</span>
        </button>
      </div>
      {notifications.length === 0 ? (
        <div className="gh__notif-empty">새로운 알림이 없습니다.</div>
      ) : (
        <ul className="gh__notif-list">
          {notifications.slice(0, 10).map((n) => (
            <li key={n.id} className={`gh__notif-item gh__notif-item--${n.type}`}>
              <span className="material-icons gh__notif-icon">
                {n.type === "admin_report" ? "report_problem" :
                  n.type === "analysis_complete" ? "analytics" :
                    n.type === "mask_complete" ? "check_circle" : "notifications"}
              </span>
              <div className="gh__notif-body">
                <p className="gh__notif-msg">
                  {n.title && <strong className="gh__notif-title">{n.title}</strong>}
                  {n.msg}
                </p>
                <span className="gh__notif-time">{relativeTime(n.createdAt)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function GarimHeader({ layout = "public", current = "" }) {
  const isAuthed = useAuthStatus();
  // 알림 컨텍스트는 조건 없이 호출(React 훅 규칙 준수). 미인증 시 Provider가 빈 상태를 반환한다.
  const { unreadCount, markAllRead, notifications } = useNotifications();

  // 드롭다운 열림/닫힘 상태
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const wrapRef = useRef(null);

  // 헤더 중앙 사용자 정보 (이메일, 플랜, 크레딧, 역할)
  const [headerUserInfo, setHeaderUserInfo] = useState({ email: "", plan: "Free", credit: 0, role: "user" });

  useEffect(() => {
    if (isAuthed) {
      Promise.all([
        getCurrentUser().catch(() => ({ authenticated: false, user: { email: "", role: "user" } })),
        getMyPaymentInfo().catch(() => ({ plan_name: "Free" })),
        getMyCreditBalance().catch(() => ({ balance: 0 }))
      ]).then(([userRes, paymentRes, creditRes]) => {
        const u = userRes?.user || userRes || {};
        setHeaderUserInfo({
          email: u.email || u.provider_email || u.name || "사용자",
          plan: paymentRes?.plan_name || "Free",
          credit: creditRes?.balance || 0,
          role: u.role || "user"
        });
      });
    }
  }, [isAuthed]);

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    if (!dropdownOpen) return;
    const handleOutside = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [dropdownOpen]);

  // 종 버튼 클릭: 열 때 읽음 처리, 토글
  const handleBellClick = () => {
    if (!dropdownOpen) markAllRead();
    setDropdownOpen((prev) => !prev);
  };

  // 종 + 드롭다운 묶음 렌더 (컴포넌트가 아닌 렌더 함수 — 매 렌더 재생성으로 인한 상태 초기화 방지)
  const renderBell = () => {
    // 관리자 알림(admin_report)이 있으면 배지 강조색 적용
    const hasAdminNotif = notifications.some(n => n.type === "admin_report");

    return (
      <span className="gh__icon-wrap" ref={wrapRef}>
        <button
          className="gh__icon"
          title="알림"
          type="button"
          onClick={handleBellClick}
          aria-expanded={dropdownOpen}
        >
          <span className="material-icons">notifications</span>
        </button>
        {unreadCount > 0 && (
          <span className={`gh__badge${hasAdminNotif ? " gh__badge--admin" : ""}`}>
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
        {dropdownOpen && (
          <NotificationDropdown
            notifications={notifications}
            onClose={() => setDropdownOpen(false)}
          />
        )}
      </span>
    );
  };

  if (layout === "admin") {
    return (
      <header className="gh gh--admin">
        <Link to="/" className="gh__logo">
          <img
            src="/garim/logo.svg"
            alt="Garim"
          />
        </Link>
        <a href="/admin/monitoring" className="overline-k gh__admin-link">
          ADMIN
        </a>
        <div className="spacer" />
        <div className="gh__right">

          <ThemeToggle />
          {renderBell()}
          <div className="gh__avatar gh__avatar--admin">
            A
          </div>
        </div>
      </header>
    );
  }

  if (layout === "auth") {
    return (
      <header className="gh gh--minimal">
        <Link to="/" className="gh__logo">
          <img src="/garim/logo.svg" alt="Garim" />
        </Link>
        {/* 로고 왼쪽 고정, 테마 토글 오른쪽으로 밀기 */}
        <div className="spacer" />
        <ThemeToggle />
      </header>
    );
  }

  return (
    <header
      className={`gh ${layout === "app" ? "gh--app" : ""} ${layout === "landing" || current === "landing" ? "gh--landing" : ""
        }`}
    >
      <Link to="/" className="gh__logo">
        <img src="/garim/logo.svg" alt="Garim" />
      </Link>
      <nav className="gh__nav">
        {publicNav.map((item) => {
          if (item.onClick) {
            return (
              <a
                key={item.id}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  item.onClick();
                }}
                className={current === item.id ? "active" : ""}
              >
                {item.label}
              </a>
            );
          }
          return (
            <Link
              key={item.id}
              to={
                item.id === "detect" && !isAuthed
                  ? buildLoginUrl(item.to)
                  : item.to
              }
              className={current === item.id ? "active" : ""}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      {isAuthed && (
        <div className="gh__user-info">
          <div className="gh__user-cols">
            {/* 로그인 계정 컬럼 */}
            <div className="gh__user-col">
              <span className="gh__user-label">로그인 계정</span>
              <span className="gh__user-account">
                <span className="gh__online-dot" />
                {headerUserInfo.email || "—"}
              </span>
            </div>
            {/* 플랜 컬럼 */}
            <div className="gh__user-col">
              <span className="gh__user-label">플랜</span>
              <span className="gh__user-plan">{headerUserInfo.plan}</span>
            </div>
            {/* 보유 크레딧 컬럼 */}
            <div className="gh__user-col">
              <span className="gh__user-label">보유 크레딧</span>
              <span className="gh__user-credit">
                {headerUserInfo.credit}
                <span className="gh__user-credit-unit">개</span>
              </span>
            </div>
          </div>
        </div>
      )}
      <div className="gh__right">
        <ThemeToggle />
        {isAuthed ? (
          <>
            {/* TODO: 임시 버튼 — 어드민 링크 확정 후 제거 */}
            {headerUserInfo.role === "admin" && (
              <Link
                to="/admin/monitoring"
                className="mui-btn mui-btn--outlined mui-btn--sm gh__admin-btn"
              >
                관리자 페이지로 이동
              </Link>
            )}
            {renderBell()}
            <Link
              to="/settings"
              className="gh__icon"
              title="프로필/환경 설정"
              aria-label="프로필/환경 설정"
            >
              <span className="material-icons">settings</span>
            </Link>
            <Link to="/dashboard" className="gh__avatar" title="대시보드">
              M
            </Link>
          </>
        ) : (
          <>
            <Link to="/login" className="mui-btn mui-btn--text">
              로그인
            </Link>
            <Link
              to={isAuthed ? "/upload" : buildLoginUrl("/upload")}
              className="mui-btn mui-btn--contained mui-btn--sm"
            >
              무료 시작
            </Link>
          </>
        )}
      </div>
    </header>
  );
}
