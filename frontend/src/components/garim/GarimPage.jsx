/*
코드 설명:
모든 Garim 페이지의 공통 래퍼. 라우트 메타(layout/current)에 따라 본문 클래스와 헤더 레이아웃을 정하고,
GarimHeader와 GarimFooter로 페이지 콘텐츠를 감싼다.
*/
import GarimFooter from "./GarimFooter";
import GarimHeader from "./GarimHeader";
import { useGarimRoute } from "../../hooks/useGarimRoute";
import { getDefaultBodyClass, getHeaderLayout } from "../../utils/garimLayout";

export default function GarimPage({
  children,
  bodyClass,
  screenLabel,
}) {
  const route = useGarimRoute();
  const layout = route?.layout ?? "public";
  const current = route?.current ?? "";
  const headerLayout = getHeaderLayout(layout, current);

  return (
    <div className={bodyClass ?? getDefaultBodyClass(layout)} data-screen-label={screenLabel ?? route?.name ?? ""}>
      <GarimHeader layout={headerLayout} current={current} />
      {children}
      <GarimFooter minimal={layout === "auth"} />
    </div>
  );
}
