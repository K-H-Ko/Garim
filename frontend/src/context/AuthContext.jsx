/*
코드 설명:
앱 진입 시 /auth/status를 1회 조회해 인증 상태와 사용자 정보를 보관하고 하위에 공급하는 Provider.
화면마다 개별로 인증을 조회하던 중복 호출을 단일 호출로 통합한다.
*/
import { useEffect, useState } from "react";
import { AuthContext } from "./authContext";
import { getAuthStatus } from "../utils/api";

export function AuthProvider({ children }) {
  const [state, setState] = useState({ isAuthenticated: false, user: null, loading: true });

  useEffect(() => {
    let isMounted = true;

    getAuthStatus()
      .then((status) => {
        if (!isMounted) return;
        setState({
          isAuthenticated: Boolean(status?.authenticated),
          user: status?.user ?? null,
          loading: false,
        });
      })
      .catch(() => {
        if (isMounted) setState({ isAuthenticated: false, user: null, loading: false });
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}
