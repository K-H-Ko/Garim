/*
코드 설명:
AuthContext에서 인증 상태를 꺼내 쓰는 훅. useAuthStatus는 인증 여부(boolean)만,
useAuthUser는 인증 여부와 사용자 정보를 반환한다. 실제 조회는 AuthProvider가 1회 수행한다.
*/
import { useContext } from "react";

import { AuthContext } from "../context/authContext";

export function useAuthStatus() {
  return useContext(AuthContext).isAuthenticated;
}

export function useAuthUser() {
  const { isAuthenticated, user } = useContext(AuthContext);
  return { isAuthenticated, user };
}
