import { useCallback, useEffect, useRef, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getComplianceOverview,
  searchCompliance,
  getComplianceConsent,
  getComplianceReports,
} from "../../utils/api";
import "../../css/garim-pages/AdminCompliance.css";
import GarimPage from "../../components/garim/GarimPage";

// 준수율 → pill 클래스
function pillClass(rate) {
  if (rate >= 99) return "compliance-pill ok";
  if (rate >= 95) return "compliance-pill warn";
  return "compliance-pill err";
}

// abuse_reports status → 한글 + pill 클래스
function reportStatus(s) {
  if (s === "resolved")   return { label: "완료",   cls: "compliance-pill ok"  };
  if (s === "rejected")   return { label: "불가",   cls: "compliance-pill warn" };
  if (s === "in_review")  return { label: "검토 중", cls: "compliance-pill warn" };
  return                         { label: "접수",   cls: "compliance-pill" };
}

// report_type → chip 클래스
function reportChipClass(rtype) {
  if (rtype === "court_order")   return "mui-chip mui-chip--soft-warning";
  if (rtype === "investigation") return "mui-chip mui-chip--soft-danger";
  return "mui-chip mui-chip--soft-info"; // forgery, takedown 등
}

// deletion log 결과 → 색상
function logColor(result) {
  if (result === "success") return "#2e7d32";
  if (result === "failed")  return "#d32f2f";
  return "#ed6c02"; // partial
}

// deletion log target_type → 한글
function logTarget(tt) {
  if (!tt) return "데이터";
  if (tt.includes("upload"))   return "원본 파일";
  if (tt.includes("processed") || tt.includes("result")) return "결과 파일";
  if (tt.includes("meta") || tt.includes("job"))  return "메타데이터";
  if (tt.includes("artifact")) return "처리 산출물";
  return tt;
}

// ── 탭 목록
const TABS = [
  { key: "auto",    icon: "auto_delete",   label: "자동 삭제 모니터" },
  { key: "search",  icon: "search",         label: "처리 이력 검색"   },
  { key: "consent", icon: "checklist",      label: "약관 동의 이력"   },
  { key: "report",  icon: "gavel",          label: "신고·수사 응답"   },
];

const SEARCH_TYPES = [
  { value: "job_id",    label: "처리 ID로" },
  { value: "user_id",   label: "사용자 ID / 이메일로" },
  { value: "watermark", label: "워터마크 해시로" },
];

// 10분 폴링 (overview 탭만, 실시간성 낮아도 OK)
const POLL_MS = 600_000;

export default function AdminCompliance() {
  useDocumentTitle("컴플라이언스 로그·감사 · Garim Admin");

  const [activeTab, setActiveTab] = useState("auto");

  // ── auto 탭
  const [overview, setOverview] = useState(null);
  const timerRef = useRef(null);

  const loadOverview = useCallback(async () => {
    try {
      const res = await getComplianceOverview();
      setOverview(res?.data ?? res);
    } catch (_) {}
  }, []);

  useEffect(() => {
    loadOverview();
    timerRef.current = setInterval(loadOverview, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, [loadOverview]);

  // ── search 탭
  const [searchQ,    setSearchQ]    = useState("");
  const [searchType, setSearchType] = useState("job_id");
  const [searchRes,  setSearchRes]  = useState(null);
  const [searching,  setSearching]  = useState(false);

  const doSearch = async (q = searchQ) => {
    setSearching(true);
    try {
      const res = await searchCompliance(q.trim(), searchType);
      setSearchRes(res?.data ?? res);
    } finally {
      setSearching(false);
    }
  };

  // search 탭 진입 또는 searchType 변경 시 기본 최근 50건 로드
  useEffect(() => {
    if (activeTab === "search" && !searchRes) {
      doSearch("");
    }
  }, [activeTab, searchRes]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── consent 탭
  const [consentQ,   setConsentQ]   = useState("");
  const [consentRes, setConsentRes] = useState(null);
  const [consenting, setConsenting] = useState(false);

  const doConsent = async (q = consentQ) => {
    setConsenting(true);
    try {
      const res = await getComplianceConsent(q.trim());
      setConsentRes(res?.data ?? res);
    } finally {
      setConsenting(false);
    }
  };

  // consent 탭 진입 시 기본 최근 50건 로드
  useEffect(() => {
    if (activeTab === "consent" && !consentRes) {
      doConsent("");
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── report 탭
  const [reports, setReports] = useState(null);

  useEffect(() => {
    if (activeTab === "report" && !reports) {
      getComplianceReports({ limit: 30 })
        .then(res => setReports(res?.data ?? res))
        .catch(() => {});
    }
  }, [activeTab, reports]);

  // ── 추출
  const policyRows = overview?.policy_status ?? [];
  const upcoming   = overview?.upcoming      ?? {};
  const logs       = overview?.recent_logs   ?? [];
  const upcomingTotal = upcoming.total ?? 0;
  const uploadsDue = upcoming.uploads_due ?? 0;
  const pfDue      = upcoming.pf_due      ?? 0;

  // 도넛 차트 계산 (circumference = 2π×40 ≈ 251)
  const CIRC = 251;
  const uFrac = upcomingTotal ? Math.round((uploadsDue / upcomingTotal) * CIRC) : 0;
  const pFrac = upcomingTotal ? Math.round((pfDue      / upcomingTotal) * CIRC) : 0;

  return (
    <GarimPage bodyClass="" screenLabel="27 Admin compliance">
      <div className="adm-shell">
        {/* ── 사이드바 ── */}
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring"><span className="material-icons">monitor_heart</span>사용자 모니터링</a>
          <a href="/admin/queue"><span className="material-icons">queue</span>처리 큐</a>
          <a href="/admin/compliance" className="active"><span className="material-icons">verified_user</span>컴플라이언스</a>
          <div className="sec">시스템</div>
          <a href="/admin/users"><span className="material-icons">people</span>사용자</a>
          <a href="/admin/analytics"><span className="material-icons">analytics</span>분석</a>
          <a href="/admin/policy"><span className="material-icons">tune</span>정책 및 상품 관리</a>
          <a href="/admin/subscriptions"><span className="material-icons">subscriptions</span>구독 관리</a>
          <a href="/admin/payments"><span className="material-icons">payments</span>사용자 결제 확인</a>
          <a href="/admin/reports"><span className="material-icons">report_problem</span>문의 내역</a>
        </aside>

        {/* ── 메인 ── */}
        <main className="adm-main">
          {/* 헤더 */}
          <div className="adm-head">
            <h1>컴플라이언스 로그·감사</h1>
            <span className="caption-k">
              B-1 자동 삭제 · B-3 워터마크 역추적 · 약관 동의 이력 · 외부 요청 응답
            </span>
          </div>

          {/* 탭 바 */}
          <div className="tabs-bar">
            {TABS.map(t => (
              <button
                key={t.key}
                className={`tab-btn${activeTab === t.key ? " active" : ""}`}
                onClick={() => setActiveTab(t.key)}
              >
                <span className="material-icons">{t.icon}</span>
                {t.label}
              </button>
            ))}
          </div>

          {/* ══════════════ 탭 1: 자동 삭제 모니터 ══════════════ */}
          {activeTab === "auto" && (
            <>
              <div className="compliance-row">
                {/* 정책 현황 테이블 */}
                <div className="adm-card">
                  <div className="head">
                    <h3>데이터 종류별 보존·삭제 정책 (B-1)</h3>
                  </div>
                  <div className="policy-row tbl-head">
                    <span>데이터 종류</span>
                    <span>보존 정책</span>
                    <span>현재 잔존</span>
                    <span>준수율</span>
                  </div>
                  {policyRows.length === 0 ? (
                    <div style={{ padding: "20px 16px", textAlign: "center",
                      color: "var(--fg-2)", font: "400 12px var(--font-sans)" }}>
                      데이터 로딩 중…
                    </div>
                  ) : policyRows.map((row, i) => {
                    const isLast = i === policyRows.length - 1;
                    const rate   = row.compliance_rate ?? 100;
                    return (
                      <div className="policy-row" key={row.label}
                        style={isLast ? { borderBottom: "none" } : {}}>
                        <div>
                          <div className="data-type">{row.label}</div>
                          <div className="caption-k" style={{ fontSize: 11 }}>{row.sub}</div>
                        </div>
                        <div className="policy">{row.policy}</div>
                        <div>{row.count_label ?? `${(row.count ?? 0).toLocaleString()}개`}</div>
                        <div>
                          <span className={pillClass(rate)}>
                            {rate >= 99 && (
                              <span className="material-icons" style={{ fontSize: 14 }}>check</span>
                            )}
                            {rate < 99 && (
                              <span className="material-icons" style={{ fontSize: 14 }}>warning</span>
                            )}
                            {rate === 100 ? "100.0%" : `${rate.toFixed(1)}%`}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* 24h 삭제 예정 도넛 */}
                <div className="adm-card" style={{ display: "flex", flexDirection: "column" }}>
                  <div className="head">
                    <h3>24시간 내 삭제 예정 데이터</h3>
                  </div>
                  <div className="body" style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <div className="donut-mini">
                      <svg viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" fill="none" stroke="#e0e0e0" strokeWidth="14" />
                        {upcomingTotal > 0 && (
                          <>
                            <circle cx="50" cy="50" r="40" fill="none" stroke="#ed6c02"
                              strokeWidth="14"
                              strokeDasharray={`${uFrac} ${CIRC}`}
                              transform="rotate(-90 50 50)" />
                            <circle cx="50" cy="50" r="40" fill="none" stroke="#9747ff"
                              strokeWidth="14"
                              strokeDasharray={`${pFrac} ${CIRC}`}
                              strokeDashoffset={-uFrac}
                              transform="rotate(-90 50 50)" />
                          </>
                        )}
                        <text x="50" y="48" textAnchor="middle"
                          fontFamily="Pretendard" fontSize="15" fontWeight="500"
                          className="donut-text-main">
                          {upcomingTotal.toLocaleString()}
                        </text>
                        <text x="50" y="62" textAnchor="middle"
                          fontFamily="Pretendard" fontSize="8"
                          className="donut-text-sub">건</text>
                      </svg>
                      <div className="legend">
                        <div className="row">
                          <span className="dot" style={{ background: "#ed6c02" }} />
                          원본 (12h) — {uploadsDue.toLocaleString()}개
                        </div>
                        <div className="row">
                          <span className="dot" style={{ background: "#9747ff" }} />
                          결과 파일 — {pfDue.toLocaleString()}개
                        </div>
                      </div>
                    </div>
                    </div>
                    <div style={{ marginTop: "auto" }}>
                      <hr style={{ margin: "16px 0", border: "none", borderTop: "1px dashed var(--mui-divider)" }} />
                      <div style={{ font: "400 12px/1.5 var(--font-sans)", color: "var(--fg-2)", paddingLeft: "2px" }}>
                        자동 삭제 잡은 매 시간 정각에 실행됩니다.
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 최근 삭제 로그 */}
              <div className="adm-card">
                <div className="head">
                  <h3>최근 자동 삭제 로그</h3>
                  <span className="caption-k">최근 24시간</span>
                </div>
                {logs.length === 0 ? (
                  <div style={{ padding: "16px 18px", color: "var(--fg-2)",
                    font: "400 12px var(--font-sans)" }}>
                    최근 24시간 내 삭제 기록이 없습니다.
                  </div>
                ) : (
                  <div style={{ 
                    padding: "8px 18px", 
                    font: "400 12px/1.8 var(--font-sans)",
                    fontFamily: "var(--font-mono)", 
                    color: "var(--fg-2)",
                    maxHeight: "330px",
                    overflowY: "auto"
                  }}>
                    {logs.map((log, i) => (
                      <div key={i}>
                        <span style={{ color: "var(--fg-3)" }}>{log.ts}</span>
                        {" "}[{log.actor_type === "system" ? "auto-delete" : "user-delete"}]{" "}
                        {logTarget(log.target_type)} 삭제
                        {log.delete_reason ? ` (${log.delete_reason})` : ""}
                        {log.error_message ? (
                          <span style={{ color: "#d32f2f" }}> — {log.error_message}</span>
                        ) : (
                          <span style={{ color: logColor(log.result) }}>
                            {" "}{log.result === "success" ? "✓" : log.result === "failed" ? "✗" : "△"}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ══════════════ 탭 2: 처리 이력 검색 ══════════════ */}
          {activeTab === "search" && (
            <>
              <div className="search-block">
                <h3>처리 이력 검색</h3>
                <div className="search-tabs">
                  {SEARCH_TYPES.map(st => (
                    <button
                      key={st.value}
                      className={searchType === st.value ? "active" : ""}
                      onClick={() => { setSearchType(st.value); setSearchRes(null); setSearchQ(""); }}
                    >
                      {st.label}
                    </button>
                  ))}
                </div>
                <div className="search-row">
                  <input
                    value={searchQ}
                    onChange={e => setSearchQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && doSearch(searchQ)}
                    placeholder={
                      searchType === "job_id"    ? "작업 ID (UUID 일부) 입력" :
                      searchType === "user_id"   ? "이메일 또는 사용자 ID 입력" :
                      "워터마크 해시 입력 (wm_...)"
                    }
                  />
                  <button className="mui-btn mui-btn--contained" onClick={() => doSearch(searchQ)}
                    disabled={searching}>
                    {searching ? "검색 중…" : "검색"}
                  </button>
                </div>
                <div className="caption-k" style={{ fontSize: 11, marginTop: 8 }}>
                  모든 검색은 감사 로그에 기록됩니다.
                </div>
              </div>

              {searchRes && (
                <>
                  {searchRes.results?.length === 0 ? (
                    <div style={{ padding: "24px", textAlign: "center",
                      color: "var(--fg-2)", font: "400 13px var(--font-sans)" }}>
                      검색 결과가 없습니다.
                    </div>
                  ) : searchRes.is_default ? (
                    /* ── 기본 최근 N건: 게시판 테이블 형식 ── */
                    <div className="adm-card">
                      <div className="head">
                        <h3>최근 처리 이력 {searchRes.total ?? 0}건</h3>
                        <span className="caption-k" style={{ fontSize: 11 }}>
                          검색어를 입력하면 특정 이력을 조회할 수 있습니다
                        </span>
                      </div>
                      <div className="policy-row tbl-head"
                        style={{ gridTemplateColumns: "90px 180px 120px 90px 80px 80px 70px" }}>
                        <span>처리 ID</span>
                        <span>이메일</span>
                        <span>파일명</span>
                        <span>처리 시점</span>
                        <span>파일 크기</span>
                        <span>길이 / 해상도</span>
                        <span>검출</span>
                      </div>
                      {searchRes.results.map((r, i) => {
                        const isLast = i === searchRes.results.length - 1;
                        const parts = [
                          r.duration !== "—" ? r.duration : null,
                          r.resolution !== "—" ? r.resolution : null,
                        ].filter(Boolean);
                        const mediaInfo = parts.length > 0 ? parts.join(" / ") : "—";
                        return (
                          <div key={r.job_id} className="policy-row"
                            style={{
                              gridTemplateColumns: "90px 180px 120px 90px 80px 80px 70px",
                              borderBottom: isLast ? "none" : undefined,
                            }}>
                            <span className="policy">{r.short_id}</span>
                            <span className="policy" style={{ overflow: "hidden",
                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {r.email}
                            </span>
                            <span className="caption-k" style={{ overflow: "hidden",
                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {r.filename}
                            </span>
                            <span className="policy" style={{ fontSize: 11 }}>
                              {r.created_at.slice(0, 16)}
                            </span>
                            <span className="caption-k">{r.file_size}</span>
                            <span className="policy">{mediaInfo}</span>
                            <span>
                              <span className={r.detection_count > 0
                                ? "compliance-pill warn" : "compliance-pill ok"}>
                                {r.detection_count}건
                              </span>
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    /* ── 특정 검색 결과: 상세 카드 형식 ── */
                    searchRes.results?.map((r, i) => (
                    r.type === "job" ? (
                      <div className="result-grid" key={r.job_id}>
                        <div className="meta-card">
                          <h3>처리 이력 메타데이터</h3>
                          {[
                            ["처리 ID",     r.short_id],
                            ["사용자 이메일", r.email],
                            ["처리 상태",    r.status],
                            ["처리 시점",    r.created_at],
                            ["완료 시점",    r.completed_at],
                            ["파일 유형",    r.content_type],
                            ["파일 크기",    r.file_size],
                            ["영상 길이",    r.duration],
                            ["해상도",       r.resolution],
                            ["검출 건수",    String(r.detection_count)],
                          ].map(([k, v]) => (
                            <div className="meta-row" key={k}>
                              <span className="k">{k}</span>
                              <span className="v">{v}</span>
                            </div>
                          ))}
                        </div>
                        <div className="meta-card">
                          <h3>파일 정보</h3>
                          <div className="meta-row">
                            <span className="k">원본 파일명</span>
                            <span className="v">{r.filename}</span>
                          </div>
                          <div className="meta-row">
                            <span className="k">미디어 유형</span>
                            <span className="v">{r.media_type}</span>
                          </div>
                          <div className="deleted-note">
                            <span className="material-icons">visibility_off</span>
                            <div>
                              <strong>원본·결과 파일은 정책에 따라 자동 삭제됩니다.</strong><br />
                              메타데이터만 워터마크 역추적용으로 90일 보존됩니다 (B-1 정책).
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="adm-card" key={r.report_id} style={{ marginBottom: 12 }}>
                        <div className="head">
                          <h3>신고 이력 — {r.watermark_hash}</h3>
                          <span className={pillClass(r.status === "resolved" ? 100 : 80)}>
                            {r.status}
                          </span>
                        </div>
                        <div style={{ padding: "12px 16px", font: "400 13px var(--font-sans)" }}>
                          <div><strong>{r.type_label}</strong> · {r.created_at}</div>
                          <div style={{ marginTop: 6, color: "var(--fg-2)" }}>{r.description || "상세 내용 없음"}</div>
                        </div>
                      </div>
                    )
                  ))
                  )}
                </>
              )}
            </>
          )}

          {/* ══════════════ 탭 3: 약관 동의 이력 ══════════════ */}
          {activeTab === "consent" && (
            <>
              <div className="search-block">
                <h3>약관 동의 이력 조회</h3>
                <div className="search-row">
                  <input
                    value={consentQ}
                    onChange={e => setConsentQ(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && doConsent(consentQ)}
                    placeholder="이메일 또는 사용자 ID 입력"
                  />
                  <button className="mui-btn mui-btn--contained" onClick={() => doConsent(consentQ)}
                    disabled={consenting}>
                    {consenting ? "조회 중…" : "검색"}
                  </button>
                </div>
              </div>

              {consentRes && (
                <div className="adm-card">
                  {consentRes.error ? (
                    <div className="head">
                      <h3 style={{ color: "#d32f2f" }}>{consentRes.error}</h3>
                    </div>
                  ) : (
                    <>
                      <div className="head">
                        <h3>
                          {consentRes.is_default
                            ? `최근 동의 이력 ${consentRes.consents?.length ?? 0}건`
                            : `${consentRes.user?.email} · 동의 이력`}
                        </h3>
                        {!consentRes.is_default && consentRes.user?.joined_at && (
                          <span className="caption-k" style={{ fontSize: 11 }}>
                            가입: {consentRes.user.joined_at}
                          </span>
                        )}
                      </div>
                      <div style={{ padding: "8px 18px", font: "400 13px/1.8 var(--font-sans)" }}>
                        {consentRes.consents?.length === 0 ? (
                          <div style={{ color: "var(--fg-2)" }}>동의 이력이 없습니다.</div>
                        ) : consentRes.consents?.map((c, i) => (
                          <div key={i} style={{
                            display: "flex", gap: 16, padding: "10px 0",
                            borderBottom: i < consentRes.consents.length - 1
                              ? "1px solid var(--mui-divider)" : "none"
                          }}>
                            <span style={{
                              fontFamily: "var(--font-mono)", fontSize: 12,
                              color: "var(--fg-2)", minWidth: 160
                            }}>
                              {c.created_at}
                            </span>
                            {/* 기본 50건 목록일 때 이메일도 표시 */}
                            {consentRes.is_default && (
                              <span style={{
                                fontFamily: "var(--font-mono)", fontSize: 12,
                                color: "var(--fg-2)", minWidth: 200
                              }}>
                                {c.email}
                              </span>
                            )}
                            <span style={{ flex: 1 }}>
                              <strong>{c.type_label}</strong>
                              {" → "}
                              <span style={{ color: c.is_agreed ? "#2e7d32" : "#d32f2f" }}>
                                {c.is_agreed ? "동의" : "거부"}
                              </span>
                              {c.version && ` (약관 ${c.version})`}
                              {c.source && (
                                <span style={{ color: "var(--fg-2)", fontSize: 11 }}>
                                  {" · "}{c.source}
                                </span>
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </>
          )}

          {/* ══════════════ 탭 4: 신고·수사 응답 ══════════════ */}
          {activeTab === "report" && (
            <>
              <div className="adm-card" style={{ marginBottom: 16 }}>
                <div className="head">
                  <h3>응답 이력 — 최근 30건</h3>
                  <span className="caption-k">
                    법원 명령·수사 협조·위변조 신고 등
                  </span>
                </div>

                <div className="policy-row tbl-head"
                  style={{ gridTemplateColumns: "130px 130px 1fr 100px 80px" }}>
                  <span>접수 일시</span>
                  <span>유형</span>
                  <span>내용</span>
                  <span>워터마크</span>
                  <span>상태</span>
                </div>

                {!reports ? (
                  <div style={{ padding: "20px 16px", textAlign: "center",
                    color: "var(--fg-2)", font: "400 12px var(--font-sans)" }}>
                    로딩 중…
                  </div>
                ) : reports.data?.length === 0 ? (
                  <div style={{ padding: "20px 16px", textAlign: "center",
                    color: "var(--fg-2)", font: "400 12px var(--font-sans)" }}>
                    신고 이력이 없습니다.
                  </div>
                ) : reports.data?.map((r, i) => {
                  const st = reportStatus(r.status);
                  const isLast = i === reports.data.length - 1;
                  return (
                    <div key={r.report_id} className="policy-row"
                      style={{
                        gridTemplateColumns: "130px 130px 1fr 100px 80px",
                        borderBottom: isLast ? "none" : undefined
                      }}>
                      <span className="caption-k" style={{ fontFamily: "var(--font-mono)" }}>
                        {r.created_at}
                      </span>
                      <span>
                        <span className={`${reportChipClass(r.report_type)} mui-chip`}
                          style={{ height: 20, fontSize: 11 }}>
                          {r.type_label}
                        </span>
                      </span>
                      <span className="caption-k" style={{ overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.description || "내용 없음"}
                      </span>
                      <span className="caption-k" style={{ fontFamily: "var(--font-mono)",
                        fontSize: 11 }}>
                        {r.watermark_hash !== "—"
                          ? `${r.watermark_hash.slice(0, 10)}…`
                          : "—"}
                      </span>
                      <span>
                        <span className={st.cls}>{st.label}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </main>
      </div>
    </GarimPage>
  );
}
