/*
코드 설명:
백엔드 REST API 호출을 모은 클라이언트 모듈. 공통 fetch 래퍼(requestJson)가 쿠키 인증과 401 토큰 자동 갱신을
처리하고, 인증·결제·구독·업로드·분석·관리자·알림 등 도메인별 요청 함수를 제공한다.
*/
const DEFAULT_API_PORT = "8000";

export function getApiBaseUrl() {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (typeof window === "undefined") {
    return `http://localhost:${DEFAULT_API_PORT}`;
  }
  return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}`;
}

export function getOAuthStartUrl(provider, nextPath = "") {
  const params = new URLSearchParams();
  if (nextPath) params.set("next", nextPath);
  const query = params.toString();
  return `${getApiBaseUrl()}/auth/${provider}/start${query ? `?${query}` : ""}`;
}

export function getOAuthReregisterUrl(provider) {
  return `${getApiBaseUrl()}/auth/${provider}/start?reregister=true`;
}

export async function getAuthStatus() {
  return requestJson("/auth/status");
}

export async function getMyPaymentInfo() {
  return requestJson("/payment/me");
}

export async function getMyCreditBalance() {
  return requestJson("/payment/credits/me");
}

export async function requestPlanChange(payload) {
  return requestJson("/subscriptions/change-plan", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function resumeSubscription(subscriptionId) {
  return requestJson(`/subscriptions/${subscriptionId}/resume`, {
    method: "POST",
  });
}

export async function cancelScheduledPlanChange(planChangeId) {
  return requestJson(`/subscriptions/plan-changes/${planChangeId}/cancel`, {
    method: "POST",
  });
}

export async function getCurrentUser() {
  return requestJson("/auth/me");
}

export async function getConsents() {
  return requestJson("/auth/consents");
}

export async function saveConsents(isAgreed, version) {
  return requestJson("/auth/consents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_agreed: isAgreed, version }),
  });
}

export async function logout() {
  return requestJson("/auth/logout", { method: "POST" });
}

export async function getUserSettings() {
  return requestJson("/settings/me");
}

export async function getMyLoginHistories() {
  return requestJson("/settings/me/login-histories");
}

export async function deleteAccount() {
  return requestJson("/settings/me", { method: "DELETE" });
}

export async function updateUserSettings(settings) {
  return requestJson("/settings/me", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(settings),
  });
}

export async function getAdminUsers(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.limit) query.set("limit", params.limit);
  if (params.role) query.set("role", params.role);
  if (params.status) query.set("status", params.status);
  const qs = query.toString();
  return requestJson(`/admin/users${qs ? "?" + qs : ""}`);
}

export async function getAdminPolicySettings() {
  return requestJson("/admin/policy");
}

export async function getAdminAnalytics(days = 30) {
  return requestJson(`/admin/analytics?days=${days}`);
}

// 관리자 - 사용자 모니터링
export async function getMonitoringOverview() {
  return requestJson("/admin/monitoring/overview");
}

export async function getMonitoringActivities(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", params.limit);
  if (params.status) query.set("status", params.status);
  const qs = query.toString();
  return requestJson(`/admin/monitoring/activities${qs ? "?" + qs : ""}`);
}

export async function cancelMonitoringJob(jobId) {
  return requestJson(`/admin/monitoring/jobs/${jobId}/cancel`, { method: "POST" });
}

// 관리자 - 처리 큐
export async function getQueueOverview() {
  return requestJson("/admin/queue/overview");
}

// 관리자 - 컴플라이언스
export async function getComplianceOverview() {
  return requestJson("/admin/compliance/overview");
}

export async function searchCompliance(q, type = "job_id") {
  const qs = new URLSearchParams({ q, type }).toString();
  return requestJson(`/admin/compliance/search?${qs}`);
}

export async function getComplianceConsent(q) {
  const qs = new URLSearchParams({ q }).toString();
  return requestJson(`/admin/compliance/consent?${qs}`);
}

export async function getComplianceReports(params = {}) {
  const query = new URLSearchParams();
  if (params.page)  query.set("page",  params.page);
  if (params.limit) query.set("limit", params.limit);
  return requestJson(`/admin/compliance/reports?${query.toString()}`);
}

export async function getAdminSubscriptions(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.limit) query.set("limit", params.limit);
  if (params.q) query.set("q", params.q);
  if (params.search_key) query.set("search_key", params.search_key);
  if (params.plan_code) query.set("plan_code", params.plan_code);
  if (params.subscription_status) query.set("subscription_status", params.subscription_status);
  if (params.auto_renew !== undefined && params.auto_renew !== "") query.set("auto_renew", params.auto_renew);
  if (params.cancel_scheduled !== undefined && params.cancel_scheduled !== "") query.set("cancel_scheduled", params.cancel_scheduled);
  if (params.billing_failed !== undefined && params.billing_failed !== "") query.set("billing_failed", params.billing_failed);
  if (params.scheduled_change !== undefined && params.scheduled_change !== "") query.set("scheduled_change", params.scheduled_change);
  const qs = query.toString();
  return requestJson(`/admin/subscriptions${qs ? "?" + qs : ""}`);
}

export async function getAdminSubscriptionDetail(userId) {
  return requestJson(`/admin/subscriptions/${userId}`);
}

export async function cancelAdminSubscription(userId, subscriptionId, cancelReason) {
  return requestJson(`/admin/subscriptions/${userId}/${subscriptionId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cancel_reason: cancelReason }),
  });
}

export async function updateAdminPolicySettings(policies) {
  return requestJson("/admin/policy", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ policies }),
  });
}

function buildAdminPlanQuery(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.limit) query.set("limit", params.limit);
  if (params.q) query.set("q", params.q);
  if (params.status) query.set("status", params.status);
  if (params.include_deleted !== undefined) {
    query.set("include_deleted", params.include_deleted ? "true" : "false");
  }

  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export async function getAdminPlans(params = {}) {
  return requestJson(`/admin/plans${buildAdminPlanQuery(params)}`);
}

export async function createAdminPlan(plan) {
  return requestJson("/admin/plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
}

export async function updateAdminPlan(planId, plan) {
  return requestJson(`/admin/plans/${planId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
}

export async function deleteAdminPlan(planId) {
  return requestJson(`/admin/plans/${planId}`, { method: "DELETE" });
}

export async function getAdminCreditPlans(params = {}) {
  return requestJson(`/admin/credit-plans${buildAdminPlanQuery(params)}`);
}

export async function createAdminCreditPlan(plan) {
  return requestJson("/admin/credit-plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
}

export async function updateAdminCreditPlan(creditPlanId, plan) {
  return requestJson(`/admin/credit-plans/${creditPlanId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
}

export async function deleteAdminCreditPlan(creditPlanId) {
  return requestJson(`/admin/credit-plans/${creditPlanId}`, {
    method: "DELETE",
  });
}

export async function createPaymentTempOrder(order) {
  return requestJson("/payment/temp-order", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(order),
  });
}

export async function confirmPayment(payment) {
  return requestJson("/payment/confirm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payment),
  });
}

export async function initUpload(meta) {
  return requestJson("/uploads/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(meta),
  });
}

export async function uploadChunk(
  uploadId,
  chunkIndex,
  blob,
  chunkHash = null,
) {
  const formData = new FormData();
  formData.append("file", blob);

  const headers = {};
  if (chunkHash) headers["X-Chunk-Hash"] = chunkHash;

  const response = await fetch(
    `${getApiBaseUrl()}/uploads/${uploadId}/chunks/${chunkIndex}`,
    {
      method: "POST",
      credentials: "include",
      headers,
      body: formData,
    },
  );

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      body.message || `chunk ${chunkIndex} 업로드에 실패했습니다.`,
    );
  }

  return body;
}

export async function completeUpload(uploadId) {
  return requestJson(`/uploads/${uploadId}/complete`, { method: "POST" });
}

export async function createAnalysisJob(uploadId) {
  return requestJson("/analysis/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId }),
  });
}

export async function getAnalysisJob(jobId) {
  return requestJson(`/analysis/jobs/${jobId}`);
}

export async function cancelAnalysisJob(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/cancel`, { method: "POST" });
}

// ── 파이프라인 연동 신규 API 함수 ──

/** 탐지 결과 목록 + timeline_markers + 요약 통계 */
export async function getJobDetections(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/detections`);
}

/** 상세보기 진입 시 크레딧 차감 요청 */
export async function chargeDetailAccess(jobId, fileType) {
  return requestJson(`/analysis/jobs/${jobId}/detail-access`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_type: fileType }),
  });
}

/** result.json / 상세보기 / tracks artifact 경로 */
export async function getJobResult(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/result`);
}

/** 사용자 선택 저장 — selections: [{ detection_id, is_selected }] */
export async function saveSelections(jobId, selections) {
  return requestJson(`/analysis/jobs/${jobId}/selections`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections }),
  });
}

/** 마스킹 선택 전체 초기화 — 미리보기에서 뒤로가기 시 모든 is_user_selected를 False로 리셋 */
export async function resetSelections(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/selections`, { method: "DELETE" });
}

/** 마스킹 미리보기 job 생성
 *  이미지: body 없이 호출
 *  영상 개별 PII 6초 클립: body = { pii_id, clip_start, clip_end } 전달
 */
export async function triggerMaskPreview(jobId, body = {}) {
  return requestJson(`/analysis/jobs/${jobId}/mask-preview`, {
    method: "POST",
    headers: Object.keys(body).length ? { "Content-Type": "application/json" } : {},
    body: Object.keys(body).length ? JSON.stringify(body) : undefined,
  });
}

/** 마스킹 미리보기 결과물(파일/DB) 삭제 (뒤로가기 또는 처리진행 시 호출) */
export async function deleteMaskPreview(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/mask-preview`, { method: "DELETE" });
}

/** 탭 종료나 새로고침 시 백그라운드에서 안전하게 삭제 요청을 보내기 위함 */
export function deleteMaskPreviewKeepalive(jobId) {
  fetch(`${getApiBaseUrl()}/analysis/jobs/${jobId}/mask-preview`, {
    method: "DELETE",
    keepalive: true,
    credentials: "include",
  }).catch(() => {});
}

/** 처리 완료 파일 다운로드 URL (브라우저 src / a href 용) */
export function getDownloadUrl(jobId) {
  return `${getApiBaseUrl()}/analysis/jobs/${jobId}/download`;
}

/** 영상 구간 다운로드 URL — 백엔드 ffmpeg로 잘라 MP4 반환 */
export function getTrimUrl(jobId, startSec, endSec) {
  return `${getApiBaseUrl()}/analysis/jobs/${jobId}/trim?start=${startSec}&end=${endSec}`;
}

/** 마스킹 본처리 job 생성 (선택된 PII 전체 처리) */
export async function triggerMaskFinal(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/mask-final`, { method: "POST" });
}

/** 최종 결과물 파일 정보 조회 (다운로드 URL 포함) */
export async function getResultFile(jobId) {
  return requestJson(`/analysis/jobs/${jobId}/result-file`);
}

/** 상세보기 파일 URL 반환 (브라우저에서 직접 src로 사용)
 *  file_type: "image" | "video"
 *  piiId    : 영상 개별 PII 미리보기 시 전달 → 해당 PII 탐지구간 6초 클립으로 서빙(마스킹 클립과 시간축 일치)
 *  credentials 쿠키가 필요하므로 <img src> 대신 fetch → blob URL 방식 사용 가능
 */
export function getDetailFileUrl(jobId, fileType = "image", piiId = null) {
  const base = `${getApiBaseUrl()}/analysis/jobs/${jobId}/detail-file?file_type=${fileType}`;
  return piiId ? `${base}&pii_id=${encodeURIComponent(piiId)}` : base;
}

export async function getUploadStatus(uploadId) {
  return requestJson(`/uploads/${uploadId}/status`);
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${getApiBaseUrl()}/uploads`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(body.message || "파일 업로드에 실패했습니다.");
  }

  return body;
}

let refreshPromise = null;

// 세션 만료 시 사유 알림 후 로그인 페이지로 이동
function handleSessionExpired(reason) {
  // 이미 로그인 페이지면 알림 없이 종료 (무한 루프 방지)
  if (window.location.pathname === "/login") return;

  alert(`[${reason}]\n\n해당 사유로 로그인을 다시 진행해주세요.`);
  window.location.href = "/login";
}

async function requestJson(path, options = {}, isRetry = false) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    credentials: "include",
    ...options,
  });
  const body = await response.json().catch(() => ({}));

  if (response.status === 401 && !isRetry) {
    // 1차 401: 액세스 토큰 만료 → 리프레시 토큰으로 갱신 시도
    if (!refreshPromise) {
      refreshPromise = fetch(`${getApiBaseUrl()}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      }).finally(() => {
        refreshPromise = null;
      });
    }

    try {
      const refreshRes = await refreshPromise;
      if (refreshRes && refreshRes.ok) {
        // 갱신 성공 → 원래 요청 재시도
        return requestJson(path, options, true);
      }
      // 리프레시도 실패 → 세션 완전 만료 (장시간 미사용 등)
      handleSessionExpired("장시간 미사용으로 로그인이 자동 해제되었습니다");
      return null;
    } catch {
      // 네트워크 오류 등으로 갱신 자체 실패
      handleSessionExpired("네트워크 오류로 로그인 세션을 확인할 수 없습니다");
      return null;
    }
  }

  if (response.status === 401 && isRetry) {
    // 갱신 후 재시도에서도 401 → 인증 정보 이상
    handleSessionExpired("로그인 인증 정보가 유효하지 않습니다");
    return null;
  }

  if (!response.ok) {
    throw new Error(body.message || body.detail || "API request failed.");
  }

  return body;
}

export async function getAdminPayments(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.limit) query.set("limit", params.limit);
  if (params.product_type) query.set("product_type", params.product_type);
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  if (params.search_key) query.set("search_key", params.search_key);
  if (params.date_from) query.set("date_from", params.date_from);
  if (params.date_to) query.set("date_to", params.date_to);
  const qs = query.toString();
  return requestJson(`/admin/payments${qs ? "?" + qs : ""}`);
}

export async function getAdminPaymentDetail(paymentId) {
  return requestJson(`/admin/payments/${paymentId}`);
}

export async function refundAdminPayment(paymentId, refundReason) {
  return requestJson(`/admin/payments/${paymentId}/refund`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refund_reason: refundReason }),
  });
}

export async function getDashboardData() {
  return requestJson(`/analysis/dashboard`);
}

export async function getHistoryList(page = 1, size = 10, search = "", sort = "desc") {
  const query = new URLSearchParams({ page, size });
  if (search) query.set("search", search);
  if (sort) query.set("sort", sort);
  return requestJson(`/analysis/history?${query.toString()}`);
}

export async function deleteAnalysisUpload(uploadId) {
  return requestJson(`/analysis/uploads/${uploadId}`, { method: "DELETE" });
}

export async function deleteAnalysisJob(jobId) {
  return requestJson(`/analysis/jobs/${jobId}`, { method: "DELETE" });
}

export async function submitAbuseReport(data) {
  return requestJson("/reports/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}
export async function getAdminReports(category = "all", page = 1, size = 20) {
  const query = new URLSearchParams({ category, page, size });
  return requestJson(`/reports/?${query.toString()}`);
}

export async function getAdminReportDetail(reportId) {
  return requestJson(`/reports/${reportId}`);
}

export async function updateAdminReportStatus(reportId, status) {
  return requestJson(`/reports/${reportId}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export async function deleteAdminReport(reportId) {
  return requestJson(`/reports/${reportId}`, { method: "DELETE" });
}


// -----------------------------------------------------
// 알림(Notifications)
// -----------------------------------------------------
export async function getNotifications() {
  return requestJson("/notifications/");
}

export async function markAllNotificationsRead() {
  return requestJson("/notifications/read-all", { method: "POST" });
}
