/*
코드 설명:
로그인 인증 상태(isAuthenticated/user/loading)를 앱 전역에 전달하는 Context 객체 정의 (Provider는 AuthContext.jsx).
*/
import { createContext } from "react";

export const AuthContext = createContext({
  isAuthenticated: false,
  user: null,
  loading: true,
});
