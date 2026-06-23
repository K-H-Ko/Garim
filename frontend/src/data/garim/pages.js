/*
코드 설명:
전체 페이지 라우트 정의 테이블. 각 항목은 경로·컴포넌트·레이아웃·현재 메뉴 키를 담으며 App.jsx의 라우팅에 쓰인다.
*/
import Landing from "../../pages/garim/Landing";
import Pricing from "../../pages/garim/Pricing";
import Faq from "../../pages/garim/Faq";
import Terms from "../../pages/garim/Terms";
import Signup from "../../pages/garim/Signup";
import Login from "../../pages/garim/Login";
import Support from "../../pages/garim/Support";
import PasswordReset from "../../pages/garim/PasswordReset";
import Upload from "../../pages/garim/Upload";
import AnalysisProgress from "../../pages/garim/AnalysisProgress";
import AnalysisReport from "../../pages/garim/AnalysisReport";
import SnsConnect from "../../pages/garim/SnsConnect";
import SnsResults from "../../pages/garim/SnsResults";
import Payment from "../../pages/garim/Payment";
import PaymentSuccess from "../../pages/garim/PaymentSuccess";
import PaymentFail from "../../pages/garim/PaymentFail";
import ReplaceOptions from "../../pages/garim/ReplaceOptions";
import Preview from "../../pages/garim/Preview";
import ResultPage from "../../pages/garim/ResultPage";
import Dashboard from "../../pages/garim/Dashboard";
import History from "../../pages/garim/History";
import Billing from "../../pages/garim/Billing";
import Settings from "../../pages/garim/Settings";
import LearningConsent from "../../pages/garim/LearningConsent";
import AdminMonitoring from "../../pages/garim/AdminMonitoring";
import AdminQueue from "../../pages/garim/AdminQueue";
import AdminCompliance from "../../pages/garim/AdminCompliance";
import AdminUsers from "../../pages/garim/AdminUsers";
import AdminAnalytics from "../../pages/garim/AdminAnalytics";
import AdminPolicy from "../../pages/garim/AdminPolicy";
import AdminSubscriptions from "../../pages/garim/AdminSubscriptions";
import AdminPaymentCheck from "../../pages/garim/AdminPaymentCheck";
import AdminReports from "../../pages/garim/AdminReports";

export const garimPages = [
  { path: "/", name: "Landing", component: Landing, file: "01-landing.html", layout: "public", current: "landing" },
  { path: "/pricing", name: "Pricing", component: Pricing, file: "02-pricing.html", layout: "public", current: "pricing" },
  { path: "/faq", name: "Faq", component: Faq, file: "03-faq.html", layout: "public", current: "help" },
  { path: "/terms", name: "Terms", component: Terms, file: "04-terms.html", layout: "public", current: "help" },
  { path: "/signup", name: "Signup", component: Signup, file: "05-signup.html", layout: "auth", current: "" },
  { path: "/login", name: "Login", component: Login, file: "06-login.html", layout: "auth", current: "" },
  { path: "/support", name: "Support", component: Support, file: "06-support.html", layout: "public", current: "help" },
  { path: "/password-reset", name: "PasswordReset", component: PasswordReset, file: "07-password-reset.html", layout: "auth", current: "" },
  { path: "/upload", name: "Upload", component: Upload, file: "08-upload.html", layout: "app", current: "detect" },
  { path: "/analysis-progress", name: "AnalysisProgress", component: AnalysisProgress, file: "09-analysis-progress.html", layout: "app", current: "detect" },
  { path: "/analysis-report", name: "AnalysisReport", component: AnalysisReport, file: "10-analysis-report.html", layout: "app", current: "detect" },
  { path: "/sns-connect", name: "SnsConnect", component: SnsConnect, file: "11-sns-connect.html", layout: "app", current: "sns" },
  { path: "/sns-results", name: "SnsResults", component: SnsResults, file: "12-sns-results.html", layout: "app", current: "sns" },
  { path: "/payment", name: "Payment", component: Payment, file: "14-payment.html", layout: "app", current: "pricing" },
  { path: "/payment/success", name: "PaymentSuccess", component: PaymentSuccess, file: "14-payment-success.html", layout: "app", current: "pricing" },
  { path: "/payment/fail", name: "PaymentFail", component: PaymentFail, file: "14-payment-fail.html", layout: "app", current: "pricing" },
  { path: "/replace-options", name: "ReplaceOptions", component: ReplaceOptions, file: "15-replace-options.html", layout: "app", current: "detect" },
  { path: "/preview", name: "Preview", component: Preview, file: "16-preview.html", layout: "app", current: "detect" },
  { path: "/result", name: "ResultPage", component: ResultPage, file: "17-result.html", layout: "app", current: "detect" },
  { path: "/dashboard", name: "Dashboard", component: Dashboard, file: "19-dashboard.html", layout: "app", current: "dashboard" },
  { path: "/history", name: "History", component: History, file: "20-history.html", layout: "app", current: "history" },
  { path: "/billing", name: "Billing", component: Billing, file: "21-billing.html", layout: "app", current: "billing" },
  { path: "/settings", name: "Settings", component: Settings, file: "22-settings.html", layout: "app", current: "settings" },
  { path: "/learning-consent", name: "LearningConsent", component: LearningConsent, file: "23-learning-consent.html", layout: "app", current: "settings" },
  { path: "/admin/monitoring", name: "AdminMonitoring", component: AdminMonitoring, file: "25-admin-monitoring.html", layout: "admin", current: "monitoring" },
  { path: "/admin/queue", name: "AdminQueue", component: AdminQueue, file: "26-admin-queue.html", layout: "admin", current: "queue" },
  { path: "/admin/compliance", name: "AdminCompliance", component: AdminCompliance, file: "27-admin-compliance.html", layout: "admin", current: "compliance" },
  { path: "/admin/users", name: "AdminUsers", component: AdminUsers, file: "28-admin-users.html", layout: "admin", current: "users" },
  { path: "/admin/analytics", name: "AdminAnalytics", component: AdminAnalytics, file: "29-admin-analytics.html", layout: "admin", current: "analytics" },
  { path: "/admin/policy", name: "AdminPolicy", component: AdminPolicy, file: "30-admin-policy.html", layout: "admin", current: "policy" },
  { path: "/admin/subscriptions", name: "AdminSubscriptions", component: AdminSubscriptions, file: "31-admin-subscriptions.html", layout: "admin", current: "subscriptions" },
  { path: "/admin/payments", name: "AdminPaymentCheck", component: AdminPaymentCheck, file: "32-admin-payments.html", layout: "admin", current: "payments" },
  { path: "/admin/reports", name: "AdminReports", component: AdminReports, file: "33-admin-reports.html", layout: "admin", current: "reports" },
];
