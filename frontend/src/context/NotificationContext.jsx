/**
 * 알림 전역 상태 관리 — notification_events 테이블 폴링 기반.
 * 백엔드에서 job 완료(analysis_complete, mask_complete) 및 관리자 알림(admin_report)을
 * DB에 기록하므로, 클라이언트는 5초 간격으로 GET /notifications 를 폴링하여 동기화한다.
 */
import { createContext, useContext, useEffect, useState, useRef } from "react";
import { getNotifications, markAllNotificationsRead } from "../utils/api";
import { useAuthStatus } from "../hooks/useAuthStatus";

const NotificationContext = createContext();

// 상대 시간 표시 유틸 (예: "방금 전", "3분 전", "2시간 전")
export function relativeTime(date) {
  const diff = Date.now() - new Date(date).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "방금 전";
  if (min < 60) return `${min}분 전`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전`;
  return `${Math.floor(hr / 24)}일 전`;
}

export function NotificationProvider({ children }) {
  const isAuthed = useAuthStatus();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // 이미 로드된 DB 알림 ID 추적 (중복 추가 방지)
  const loadedIds = useRef(new Set());
  const initialLoadRef = useRef(true);

  useEffect(() => {
    if (!isAuthed) return;

    // 브라우저 알림 권한 요청
    if (typeof window !== "undefined" && "Notification" in window) {
      if (Notification.permission === "default") {
        Notification.requestPermission().catch(() => {});
      }
    }

    const pollNotifications = async () => {
      try {
        const data = await getNotifications();
        if (!data?.success) return;

        const newItems = [];
        for (const n of data.notifications) {
          if (loadedIds.current.has(n.id)) continue;
          loadedIds.current.add(n.id);
          newItems.push({
            id: n.id,
            type: n.type,
            title: n.title,
            msg: n.msg,
            target_type: n.target_type,
            target_id: n.target_id,
            createdAt: new Date(n.createdAt),
            isDbNotification: true,
          });
        }

        if (newItems.length === 0) return;

        // 첫 로드 시 UI에는 추가하되 팝업·브라우저 알림은 띄우지 않음
        if (initialLoadRef.current) {
          initialLoadRef.current = false;
          setNotifications(newItems.sort((a, b) => b.createdAt - a.createdAt));
          setUnreadCount(newItems.length);
          return;
        }

        initialLoadRef.current = false;

        setNotifications((prev) =>
          [...newItems, ...prev]
            .sort((a, b) => b.createdAt - a.createdAt)
            .slice(0, 50)
        );
        setUnreadCount((c) => c + newItems.length);

        // 브라우저 네이티브 알림
        if (
          typeof window !== "undefined" &&
          "Notification" in window &&
          Notification.permission === "granted"
        ) {
          for (const n of newItems) {
            new Notification(n.title || "Garim 알림", {
              body: n.msg,
              icon: "/garim/logo.svg",
            });
          }
        }
      } catch (err) {
        console.error("알림 폴링 실패:", err);
      }
    };

    pollNotifications();
    const timer = setInterval(pollNotifications, 5000);
    return () => clearInterval(timer);
  }, [isAuthed]);

  const markAllRead = async () => {
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch (e) {
      console.error("Failed to mark notifications read", e);
    }
  };

  return (
    <NotificationContext.Provider
      value={{ notifications, unreadCount, markAllRead, clearUnread: markAllRead }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  return useContext(NotificationContext);
}
