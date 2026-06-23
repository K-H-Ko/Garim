/*
코드 설명:
전달받은 title로 브라우저 문서 제목(document.title)을 설정하는 훅.
*/
import { useEffect } from "react";

export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
