import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

const expectedPages = [
  "Landing",
  "Pricing",
  "Faq",
  "Terms",
  "Signup",
  "Login",
  "PasswordReset",
  "Upload",
  "AnalysisProgress",
  "AnalysisReport",
  "SnsConnect",
  "SnsResults",
  "PaymentGate",
  "Payment",
  "ReplaceOptions",
  "Preview",
  "Processing",
  "Download",
  "Dashboard",
  "History",
  "Billing",
  "Settings",
  "LearningConsent",
  "FaceWhitelist",
  "AdminMonitoring",
  "AdminQueue",
  "AdminCompliance",
];

const expectedRoutes = [
  "/",
  "/pricing",
  "/faq",
  "/terms",
  "/signup",
  "/login",
  "/password-reset",
  "/upload",
  "/analysis-progress",
  "/analysis-report",
  "/sns-connect",
  "/sns-results",
  "/payment-gate",
  "/payment",
  "/replace-options",
  "/preview",
  "/processing",
  "/download",
  "/dashboard",
  "/history",
  "/billing",
  "/settings",
  "/learning-consent",
  "/face-whitelist",
  "/admin/monitoring",
  "/admin/queue",
  "/admin/compliance",
];

const pageDir = path.join(root, "src", "pages", "garim");
const routeFile = path.join(root, "src", "data", "garim", "pages.js");
const appFile = path.join(root, "src", "App.jsx");
const garimPageFile = path.join(root, "src", "components", "garim", "GarimPage.jsx");
const packageFile = path.join(root, "package.json");
const apiFile = path.join(root, "src", "utils", "api.js");
const expectedStructureFiles = [
  path.join(root, "src", "hooks", "useDocumentTitle.js"),
  path.join(root, "src", "hooks", "useGarimRoute.js"),
  path.join(root, "src", "context", "GarimRouteContext.jsx"),
  path.join(root, "src", "context", "garimRouteContext.js"),
  path.join(root, "src", "utils", "garimLayout.js"),
  apiFile,
];

const missingStructureFiles = expectedStructureFiles.filter((file) => !fs.existsSync(file));

if (missingStructureFiles.length > 0) {
  throw new Error(`Missing Garim structure files: ${missingStructureFiles.join(", ")}`);
}

const packageSource = fs.readFileSync(packageFile, "utf8");
if (packageSource.includes("--port 5173")) {
  throw new Error("frontend dev:lan script still uses port 5173.");
}

const apiSource = fs.readFileSync(apiFile, "utf8");
for (const apiExport of ["uploadFile", "getAuthStatus", "getCurrentUser", "refreshAuthSession", "logout"]) {
  if (!apiSource.includes(`function ${apiExport}`)) {
    throw new Error(`Missing API helper: ${apiExport}`);
  }
}

if (!apiSource.includes("function getOAuthStartUrl")) {
  throw new Error("Missing OAuth start URL helper.");
}

if (!apiSource.includes('credentials: "include"')) {
  throw new Error("Auth API helpers must include HttpOnly cookies.");
}

if (apiSource.includes("getMetaOAuthStartUrl") || apiSource.includes("/auth/instagram")) {
  throw new Error("Instagram OAuth API helper should not be present.");
}

const missingPages = expectedPages.filter(
  (name) => !fs.existsSync(path.join(pageDir, `${name}.jsx`)),
);

if (missingPages.length > 0) {
  throw new Error(`Missing Garim page components: ${missingPages.join(", ")}`);
}

const routeSource = fs.readFileSync(routeFile, "utf8");
const missingRoutes = expectedRoutes.filter(
  (route) => !routeSource.includes(`path: "${route}"`),
);

if (missingRoutes.length > 0) {
  throw new Error(`Missing Garim routes: ${missingRoutes.join(", ")}`);
}

const appSource = fs.readFileSync(appFile, "utf8");
if (!appSource.includes("garimPages")) {
  throw new Error("App.jsx does not register Garim route metadata.");
}

if (!appSource.includes("GarimRouteProvider")) {
  throw new Error("App.jsx does not provide Garim route metadata through context.");
}

const garimPageSource = fs.readFileSync(garimPageFile, "utf8");
if (garimPageSource.includes("dangerouslySetInnerHTML")) {
  throw new Error("GarimPage still renders page bodies from HTML strings.");
}

if (!garimPageSource.includes("useGarimRoute")) {
  throw new Error("GarimPage does not read layout metadata from Garim route context.");
}

const nonJsxPages = expectedPages.filter((name) => {
  const source = fs.readFileSync(path.join(pageDir, `${name}.jsx`), "utf8");
  return source.includes("<GarimPage page={page}") || source.includes('"body":');
});

if (nonJsxPages.length > 0) {
  throw new Error(`Garim pages still use page body strings: ${nonJsxPages.join(", ")}`);
}

const pagesWithInlineStyleTags = expectedPages.filter((name) => {
  const source = fs.readFileSync(path.join(pageDir, `${name}.jsx`), "utf8");
  return source.includes("<style>{`");
});

if (pagesWithInlineStyleTags.length > 0) {
  throw new Error(
    `Garim pages still contain inline style tags: ${pagesWithInlineStyleTags.join(", ")}`,
  );
}

const missingCssFiles = expectedPages.filter(
  (name) => !fs.existsSync(path.join(root, "src", "css", "garim-pages", `${name}.css`)),
);

if (missingCssFiles.length > 0) {
  throw new Error(`Missing per-page CSS files: ${missingCssFiles.join(", ")}`);
}

const pagesWithoutTitleHook = expectedPages.filter((name) => {
  const source = fs.readFileSync(path.join(pageDir, `${name}.jsx`), "utf8");
  return !source.includes("useDocumentTitle(");
});

if (pagesWithoutTitleHook.length > 0) {
  throw new Error(`Garim pages still manage document title inline: ${pagesWithoutTitleHook.join(", ")}`);
}

const loginSource = fs.readFileSync(path.join(pageDir, "Login.jsx"), "utf8");
const requiredLoginLabels = ["카카오 OAuth로 로그인", "네이버 OAuth로 로그인", "구글 OAuth로 로그인"];
const missingLoginLabels = requiredLoginLabels.filter(
  (label) => !loginSource.includes(label),
);

if (missingLoginLabels.length > 0) {
  throw new Error(`Missing social login buttons: ${missingLoginLabels.join(", ")}`);
}

for (const provider of ["kakao", "naver", "google"]) {
  if (!loginSource.includes(`provider: "${provider}"`)) {
    throw new Error(`Missing social login provider wiring: ${provider}`);
  }
}

if (!loginSource.includes("window.location.assign")) {
  throw new Error("Login buttons do not start OAuth redirects.");
}

for (const removedField of ['type=\\"email\\"', 'type=\\"password\\"', "30일 동안 로그인 유지"]) {
  if (loginSource.includes(removedField)) {
    throw new Error(`Login page still contains removed credential UI: ${removedField}`);
  }
}

console.log(`Garim smoke test passed: ${expectedPages.length} pages registered.`);
