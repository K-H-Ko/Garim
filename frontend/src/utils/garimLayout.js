/*
코드 설명:
라우트의 layout/current 값을 화면용 헤더 레이아웃과 본문 래퍼 클래스로 변환하는 유틸.
*/
export function getHeaderLayout(layout, current) {
  return layout === "public" && current === "landing" ? "landing" : layout;
}

export function getDefaultBodyClass(layout) {
  if (layout === "auth") return "page-auth";
  if (layout === "app") return "page-app";
  return "page-public";
}
