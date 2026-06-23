import { createContext, useContext, useEffect, useState, useCallback } from "react";

/* ============================================================
   ThemeContext — 전역 라이트/다크 테마 관리
   - <html> 태그에 data-theme="light" | "dark" 속성을 부여하면
     garim.css의 :root[data-theme="dark"] 변수 오버라이드가 적용된다.
   - 사용자가 고른 값은 localStorage('garim-theme')에 저장되어 새로고침/재방문 시 유지된다.
   - 요구사항: 최초 진입(저장값 없을 때)은 항상 라이트 모드.
   ============================================================ */

const STORAGE_KEY = "garim-theme";

const ThemeContext = createContext({
  theme: "light",
  toggleTheme: () => {},
  setTheme: () => {},
});

// 저장된 테마를 읽어온다. 없거나 잘못된 값이면 'light'로 기본 설정.
function readStoredTheme() {
  if (typeof window === "undefined") return "light";
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStoredTheme);

  // theme 값이 바뀔 때마다 <html data-theme="..."> 적용 + localStorage 저장
  useEffect(() => {
    const root = document.documentElement; // <html>
    root.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* 저장 실패는 무시 (시크릿 모드 등) */
    }
  }, [theme]);

  // 특정 테마로 직접 설정
  const setTheme = useCallback((next) => {
    setThemeState(next === "dark" ? "dark" : "light");
  }, []);

  // 라이트 ↔ 다크 토글 (헤더 버튼에서 사용)
  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// 컴포넌트에서 테마 상태/토글을 꺼내 쓰기 위한 훅
export function useTheme() {
  return useContext(ThemeContext);
}
