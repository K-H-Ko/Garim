/*
코드 설명:
라우트 메타(route)를 GarimRouteContext로 하위에 공급하는 Provider 컴포넌트.
*/
import { GarimRouteContext } from "./garimRouteContext";

export function GarimRouteProvider({ children, route }) {
  return (
    <GarimRouteContext.Provider value={route}>
      {children}
    </GarimRouteContext.Provider>
  );
}
