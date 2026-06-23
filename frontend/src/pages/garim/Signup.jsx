import { Navigate } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/Signup.css";

export default function Signup() {
  useDocumentTitle("OAuth 시작 · Garim");

  return <Navigate to="/login" replace />;
}
