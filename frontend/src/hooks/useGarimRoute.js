/*
코드 설명:
현재 라우트 메타 정보를 GarimRouteContext에서 꺼내 쓰는 훅.
*/
import { useContext } from "react";

import { GarimRouteContext } from "../context/garimRouteContext";

export function useGarimRoute() {
  return useContext(GarimRouteContext);
}
