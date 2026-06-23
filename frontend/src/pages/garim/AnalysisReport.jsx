import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getJobDetections, getJobResult, getMyCreditBalance, chargeDetailAccess } from "../../utils/api";
import "../../css/garim-pages/AnalysisReport.css";

import GarimPage from "../../components/garim/GarimPage";
import CreditConfirmModal from "../../components/garim/CreditConfirmModal";

// UUID 접두사 제거 → 원본 파일명만 반환 (예: "abc123_택배송장1.jpg" → "택배송장1.jpg")
function stripUuidPrefix(sourceName) {
  if (!sourceName) return "";
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_/i;
  return sourceName.replace(uuidPattern, "");
}

// 위험도 점수 0~10 → 게이지 바늘 좌표
function riskGaugePath(score) {
  const clamped = Math.max(0, Math.min(10, score || 0));
  const angle = (clamped / 10) * 160 - 80;
  const rad = (angle * Math.PI) / 180;
  const cx = 100, cy = 100, r = 80;
  const x = cx + r * Math.sin(rad);
  const y = cy - r * Math.cos(rad);
  return { x: Math.round(x), y: Math.round(y) };
}

export default function AnalysisReport() {
  useDocumentTitle("분석 리포트 · Garim");
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const jobId = location.state?.jobId || searchParams.get("jobId");

  const [summary, setSummary] = useState({});
  const [resultPaths, setResultPaths] = useState({});
  const [loading, setLoading] = useState(Boolean(jobId));
  const [error, setError] = useState(jobId ? "" : "분석 작업 ID가 없습니다.");
  // 크레딧 확인 팝업 표시 여부
  const [showCreditModal, setShowCreditModal] = useState(false);
  const [creditBalance, setCreditBalance] = useState(0);



  useEffect(() => {
    if (jobId) {
      localStorage.setItem(`job_stage_${jobId}`, "/analysis-report");
    }
  }, [jobId]);

  useEffect(() => {
    getMyCreditBalance().then(res => {
      setCreditBalance(res.balance || 0);
    }).catch(err => console.error("크레딧 조회 실패", err));
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    Promise.all([getJobDetections(jobId), getJobResult(jobId)])
      .then(([detectData, resultData]) => {
        if (cancelled) return;
        setSummary(detectData.summary || {});
        setResultPaths(resultData || {});
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [jobId]);

  const riskCounts = summary.risk_level_counts || {};
  const total = summary.total_pii_count || 0;
  const riskScore = summary.risk_score || 0;
  const gaugePoint = riskGaugePath(riskScore);

  // 원본 파일명 (UUID 제거)
  const rawSourceName = summary.source_name
    || resultPaths.result_json_path?.split(/[\\/]/).pop()?.replace("_result.json", "")
    || "";
  const displayName = stripUuidPrefix(rawSourceName) || "업로드된 파일";

  if (loading) {
    return (
      <GarimPage bodyClass="page-app" screenLabel="10 Analysis report">
        <div className="report-page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh" }}>
          <div className="caption-k" style={{ color: "var(--fg-3)" }}>탐지 결과를 불러오는 중…</div>
        </div>
      </GarimPage>
    );
  }

  if (error) {
    return (
      <GarimPage bodyClass="page-app" screenLabel="10 Analysis report">
        <div className="report-page" style={{ padding: "48px", textAlign: "center" }}>
          <div style={{ color: "var(--error)", marginBottom: "16px" }}>{error}</div>
          <Link to="/upload" className="mui-btn mui-btn--outlined">새 파일 업로드</Link>
        </div>
      </GarimPage>
    );
  }

  const requiredCredit = summary.source_type === "video" ? 3 : 2;
  const isInsufficient = creditBalance < requiredCredit;

  // 상세보기 확인 → /replace-options 이동
  async function handleDetailConfirm() {
    setShowCreditModal(false);
    try {
      setLoading(true);
      const res = await chargeDetailAccess(jobId, summary.source_type);
      setCreditBalance(res.remaining_credits);
      navigate("/replace-options", { state: { jobId, summary } });
    } catch (err) {
      if (err.message && err.message.includes("크레딧이 부족")) {
        alert("크레딧이 부족합니다. 요금제 구매 페이지로 이동합니다.");
        navigate("/pricing");
      } else {
        alert(err.message || "상세보기 접근 중 오류가 발생했습니다.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleGoToPricing() {
    setShowCreditModal(false);
    navigate("/pricing");
  }



  return (
    <GarimPage bodyClass="page-app" screenLabel="10 Analysis report">
      {/* 크레딧 확인 팝업 */}
      <CreditConfirmModal
        open={showCreditModal}
        sourceType={summary.source_type}
        isInsufficient={isInsufficient}
        onConfirm={handleDetailConfirm}
        onCancel={() => setShowCreditModal(false)}
        onGoToPricing={handleGoToPricing}
      />

      <div className="report-page">
        <div className="report-shell">

          {/* ── 요약 임팩트 섹션 ── */}
          <section className={`impact ${total === 0 ? "safe" : ""}`}>
            <div className="lead">
              {/* 파란 부분: 파일명.확장자만 표시 */}
              <div className="overline-k">
                {total === 0 ? "✓" : "⚠"} 분석 완료 · {displayName}
              </div>
              <h1>
                <span className="file-name-highlight">{displayName}</span> 파일에서
                <span className="num" style={{ color: total === 0 ? "#2e7d32" : undefined }}> {total}건</span>의
                개인정보 탐지가 되었습니다.
              </h1>
              <p className="sub">
                {total === 0 ? (
                  "발견된 민감한 개인정보가 없으므로 별도의 마스킹 처리 없이 안전하게 활용하실 수 있습니다."
                ) : (
                  "탐지된 개인정보를 확인하고 안전하게 처리하세요. 상세보기를 통해 각 항목을 직접 선택하고 가릴 수 있습니다."
                )}
              </p>
              <div style={{ display: "flex", gap: "8px", marginTop: "16px", flexWrap: "wrap" }}>
                {(riskCounts["위험"] > 0) && (
                  <span className="mui-chip mui-chip--soft-error">위험 {riskCounts["위험"]}건</span>
                )}
                {(riskCounts["주의"] > 0) && (
                  <span className="mui-chip mui-chip--soft-warning">주의 {riskCounts["주의"]}건</span>
                )}
                {(riskCounts["참고"] > 0) && (
                  <span className="mui-chip mui-chip--soft-info">참고 {riskCounts["참고"]}건</span>
                )}
                {total === 0 && (
                  <span className="mui-chip mui-chip--soft-info">탐지된 개인정보 없음</span>
                )}
              </div>
            </div>

            {/* 위험도 게이지 */}
            <div className="risk-gauge">
              <svg viewBox="0 0 200 120">
                <defs>
                  <linearGradient id="gg" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#2e7d32" />
                    <stop offset="40%" stopColor="#ed6c02" />
                    <stop offset="100%" stopColor="#d32f2f" />
                  </linearGradient>
                </defs>
                <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="#e0e0e0" strokeWidth="14" strokeLinecap="round" />
                <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gg)" strokeWidth="14" strokeLinecap="round" />
                <circle cx={gaugePoint.x} cy={gaugePoint.y} r="6" fill={total === 0 ? "#2e7d32" : "#d32f2f"} />
              </svg>
              <div className="score">
                {riskScore.toFixed(1)}
                <small>/10</small>
              </div>
              <div className="lbl">위험도</div>
            </div>
          </section>

          {/* ── 사이드바 영역 ── */}
          <div className="main-grid" style={{ gridTemplateColumns: "1fr 280px" }}>
            {/* 경고 및 요약 영역 (좌측) */}
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              {/* 탐지 결과 요약 카드 */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                  <div style={{
                    background: "var(--surface-2)",
                    borderRadius: "12px",
                    padding: "24px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "16px",
                    boxShadow: "var(--mui-elev-1)"
                  }}>
                    <div style={{ fontSize: "15px", fontWeight: 600, color: "var(--fg-1)" }}>
                      탐지된 개인정보 요약
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-around", marginTop: "8px" }}>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "32px", fontWeight: 700, color: "var(--primary)" }}>{summary.visual_pii_count ?? total}</div>
                        <div style={{ fontSize: "12px", color: "var(--fg-3)", marginTop: "4px" }}>시각 PII</div>
                      </div>
                      {(summary.audio_pii_count > 0) && (
                        <div style={{ textAlign: "center" }}>
                          <div style={{ fontSize: "32px", fontWeight: 700, color: "#7c4dff" }}>{summary.audio_pii_count}</div>
                          <div style={{ fontSize: "12px", color: "var(--fg-3)", marginTop: "4px" }}>음성 PII</div>
                        </div>
                      )}
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: "32px", fontWeight: 700, color: "#d32f2f" }}>{total}</div>
                        <div style={{ fontSize: "12px", color: "var(--fg-3)", marginTop: "4px" }}>총 건수</div>
                      </div>
                    </div>
                  </div>
                  
                  {/* 액션 유도 카드 */}
                  {total === 0 ? (
                    <div style={{
                      background: "linear-gradient(135deg, var(--surface-1) 0%, rgba(46, 125, 50, 0.08) 100%)",
                      border: "1px solid rgba(46, 125, 50, 0.2)",
                      borderRadius: "12px",
                      padding: "24px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "center",
                      gap: "12px",
                      boxShadow: "var(--mui-elev-1)"
                    }}>
                       <div style={{ fontSize: "15px", fontWeight: 600, color: "var(--fg-1)", display: "flex", alignItems: "center", gap: "6px" }}>
                         <span className="material-icons" style={{ color: "#2e7d32", fontSize: "20px" }}>check_circle</span>
                         안전하게 배포하세요
                       </div>
                       <p style={{ margin: 0, fontSize: "13px", color: "var(--fg-2)", lineHeight: 1.6 }}>
                         이 파일은 탐지된 개인정보가 없습니다. 안심하고 다른 곳에 공유하셔도 좋습니다.
                       </p>
                    </div>
                  ) : (
                    <div style={{
                      background: "linear-gradient(135deg, var(--surface-1) 0%, rgba(33, 150, 243, 0.08) 100%)",
                      border: "1px solid rgba(33, 150, 243, 0.2)",
                      borderRadius: "12px",
                      padding: "24px",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "center",
                      gap: "12px",
                      boxShadow: "var(--mui-elev-1)"
                    }}>
                       <div style={{ fontSize: "15px", fontWeight: 600, color: "var(--fg-1)", display: "flex", alignItems: "center", gap: "6px" }}>
                         <span className="material-icons" style={{ color: "#2196f3", fontSize: "20px" }}>visibility</span>
                         안전한 배포를 원하시나요?
                       </div>
                       <p style={{ margin: 0, fontSize: "13px", color: "var(--fg-2)", lineHeight: 1.6 }}>
                         상세보기를 통해 AI가 찾아낸 {total}건의 항목을 눈으로 직접 확인하고, 안전하게 가려보세요.
                       </p>
                    </div>
                  )}
              </div>

              {/* 경고 시뮬레이션 카드 */}
              {total === 0 ? (
                <div style={{
                  background: "linear-gradient(145deg, rgba(46,125,50,0.05) 0%, rgba(46,125,50,0.12) 100%)",
                  border: "1px solid rgba(46,125,50,0.25)",
                  borderRadius: "12px",
                  padding: "28px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "16px",
                  position: "relative",
                  overflow: "hidden",
                  boxShadow: "var(--mui-elev-1)"
                }}>
                  <div style={{
                    position: "absolute", top: 0, right: 0, width: "150px", height: "150px",
                    background: "radial-gradient(circle, rgba(46,125,50,0.2) 0%, transparent 70%)",
                    transform: "translate(30%, -30%)",
                    pointerEvents: "none"
                  }}></div>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span className="material-icons" style={{ color: "#2e7d32" }}>verified_user</span>
                    <span style={{ fontSize: "18px", fontWeight: 700, color: "var(--fg-1)" }}>
                      탐지된 개인정보 없음
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: "14px", color: "var(--fg-2)", lineHeight: 1.6 }}>
                    현재 파일에서 민감한 개인정보가 <strong style={{ color: "#2e7d32" }}>0건</strong> 발견되었습니다.<br/>
                    이 파일은 개인정보 유출 위험이 없으며, 안전하게 공유하거나 배포할 수 있습니다.
                  </p>
                  <div style={{
                    background: "var(--bg-2)",
                    border: "1px solid var(--mui-border)",
                    borderRadius: "8px",
                    padding: "16px",
                    fontFamily: "monospace",
                    fontSize: "13px",
                    color: "var(--fg-1)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    marginTop: "8px",
                    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.05)"
                  }}>
                    <div style={{ color: "#2e7d32", fontWeight: 600 }}>[✓] SECURITY SCAN REPORT</div>
                    <div style={{ color: "var(--fg-2)" }}>&gt; Analyzing file: {displayName}</div>
                    <div style={{ color: "var(--fg-2)" }}>&gt; Found 0 visual/voice identifiers...</div>
                    <div style={{ color: "#2e7d32" }}>&gt; SUCCESS: No sensitive data detected.</div>
                    <div style={{ 
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      marginTop: "8px", borderTop: "1px dashed var(--mui-divider)", paddingTop: "12px" 
                    }}>
                      <span>Status: <span style={{ color: "#2e7d32", fontWeight: "bold" }}>SAFE(안전함)</span></span>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{
                  background: "linear-gradient(145deg, rgba(211,47,47,0.05) 0%, rgba(211,47,47,0.12) 100%)",
                  border: "1px solid rgba(211,47,47,0.25)",
                  borderRadius: "12px",
                  padding: "28px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "16px",
                  position: "relative",
                  overflow: "hidden",
                  boxShadow: "var(--mui-elev-1)"
                }}>
                  {/* 경고등 효과 */}
                  <div style={{
                    position: "absolute", top: 0, right: 0, width: "150px", height: "150px",
                    background: "radial-gradient(circle, rgba(211,47,47,0.2) 0%, transparent 70%)",
                    transform: "translate(30%, -30%)",
                    pointerEvents: "none"
                  }}></div>

                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span className="material-icons" style={{ color: "#d32f2f" }}>gpp_bad</span>
                    <span style={{ fontSize: "18px", fontWeight: 700, color: "var(--fg-1)" }}>
                      개인정보 노출 및 유출 위험 감지!
                    </span>
                  </div>
                  
                  <p style={{ margin: 0, fontSize: "14px", color: "var(--fg-2)", lineHeight: 1.6 }}>
                    현재 파일에는 <strong style={{ color: "#d32f2f" }}>{total}건</strong>의 민감한 정보가 그대로 노출되어 있습니다.<br/>
                    이대로 외부에 공유되거나 전송될 경우, <strong>무단 도용 및 보이스피싱 타겟팅</strong> 등 심각한 피해를 초래할 수 있으며 
                    관련 법령에 의해 처벌받을 수 있습니다.
                  </p>
                  
                  <div style={{
                    background: "var(--bg-2)",
                    border: "1px solid var(--mui-border)",
                    borderRadius: "8px",
                    padding: "16px",
                    fontFamily: "monospace",
                    fontSize: "13px",
                    color: "var(--fg-1)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    marginTop: "8px",
                    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.05)"
                  }}>
                    <div style={{ color: "#d32f2f", fontWeight: 600 }}>[!] SECURITY SCAN REPORT</div>
                    <div style={{ color: "var(--fg-2)" }}>&gt; Analyzing file: {displayName}</div>
                    {((summary.visual_pii_count ?? total) > 0 || total === 0) && (
                      <div style={{ color: "var(--fg-2)" }}>&gt; Found {summary.visual_pii_count ?? total} visual identifiers...</div>
                    )}
                    {(summary.audio_pii_count > 0) && (
                      <div style={{ color: "var(--fg-2)" }}>&gt; Found {summary.audio_pii_count} voice identifiers...</div>
                    )}
                    <div style={{ color: "#ed6c02" }}>&gt; WARNING: Sensitive data is completely exposed.</div>
                    <div style={{ 
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      marginTop: "8px", borderTop: "1px dashed var(--mui-divider)", paddingTop: "12px" 
                    }}>
                      <span>Status: <span style={{ color: "#d32f2f", fontWeight: "bold", animation: "pulse 1.5s infinite" }}>UNPROTECTED(보호되지 않음)</span></span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 우측 사이드바 */}
            <aside className="side">
              <div className="side-card">
                <h3>유형별 분포</h3>
                <div className="donut">
                  <svg viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="40" fill="none" stroke="#e0e0e0" strokeWidth="14" />
                    {(riskCounts["위험"] > 0) && (
                      <circle cx="50" cy="50" r="40" fill="none" stroke="#d32f2f" strokeWidth="14"
                        strokeDasharray={`${(riskCounts["위험"] / total) * 251} 251`}
                        strokeDashoffset="0" transform="rotate(-90 50 50)" />
                    )}
                    {(riskCounts["주의"] > 0) && (
                      <circle cx="50" cy="50" r="40" fill="none" stroke="#ed6c02" strokeWidth="14"
                        strokeDasharray={`${(riskCounts["주의"] / total) * 251} 251`}
                        strokeDashoffset={`-${(riskCounts["위험"] / total) * 251 || 0}`}
                        transform="rotate(-90 50 50)" />
                    )}
                    {(riskCounts["참고"] > 0) && (
                      <circle cx="50" cy="50" r="40" fill="none" stroke="#0288d1" strokeWidth="14"
                        strokeDasharray={`${(riskCounts["참고"] / total) * 251} 251`}
                        strokeDashoffset={`-${((riskCounts["위험"] + riskCounts["주의"]) / total) * 251 || 0}`}
                        transform="rotate(-90 50 50)" />
                    )}
                    {total === 0 && (
                      <circle cx="50" cy="50" r="40" fill="none" stroke="#e0e0e0" strokeWidth="14" />
                    )}
                    <text x="50" y="48" textAnchor="middle" fontFamily="Pretendard" fontSize="14" fontWeight="500" fill="var(--fg-1)" style={{ fill: "var(--fg-1)" }}>
                      {total}
                    </text>
                    <text x="50" y="62" textAnchor="middle" fontFamily="Pretendard" fontSize="7" fill="var(--fg-3)" style={{ fill: "var(--fg-3)" }}>건</text>
                  </svg>
                  <div className="donut__legend">
                    {(riskCounts["위험"] > 0) && (
                      <div className="lg-row">
                        <span className="dot" style={{ background: "#d32f2f" }}></span>
                        위험 {riskCounts["위험"]}건 ({Math.round((riskCounts["위험"] / total) * 100)}%)
                      </div>
                    )}
                    {(riskCounts["주의"] > 0) && (
                      <div className="lg-row">
                        <span className="dot" style={{ background: "#ed6c02" }}></span>
                        주의 {riskCounts["주의"]}건 ({Math.round((riskCounts["주의"] / total) * 100)}%)
                      </div>
                    )}
                    {(riskCounts["참고"] > 0) && (
                      <div className="lg-row">
                        <span className="dot" style={{ background: "#0288d1" }}></span>
                        참고 {riskCounts["참고"]}건 ({Math.round((riskCounts["참고"] / total) * 100)}%)
                      </div>
                    )}
                    {total === 0 && (
                      <div className="lg-row" style={{ color: "var(--fg-3)" }}>탐지된 항목 없음</div>
                    )}
                  </div>
                </div>
              </div>

              <div className="side-card" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--fg-1)" }}>
                  다음 단계
                </div>
                <div className="caption-k" style={{ fontSize: "12px", color: "var(--fg-2)" }}>
                  {total === 0 ? "개인정보 탐지 내역 없음" : `탐지된 ${total}건 모두 안전하게 가리기`}
                </div>
                <button
                  type="button"
                  className="mui-btn mui-btn--contained mui-btn--lg"
                  onClick={() => {
                    if (total === 0) {
                      alert("개인정보 탐지된 부분이 없습니다. 안전한 파일입니다.");
                      return;
                    }
                    if (summary.is_paid) {
                      navigate("/replace-options", { state: { jobId, summary } });
                    } else {
                      setShowCreditModal(true);
                    }
                  }}
                  style={{ width: "100%", display: "flex", justifyContent: "center", borderRadius: "8px" }}
                >
                  <span className="material-icons" style={{ fontSize: "20px", marginRight: "6px" }}>search</span>
                  상세보기
                </button>
                <Link to="/upload" className="mui-btn mui-btn--outlined" style={{ width: "100%", display: "flex", justifyContent: "center", borderRadius: "8px" }}>
                  다른 파일 검사
                </Link>
              </div>
            </aside>
          </div>

        </div>
      </div>
    </GarimPage>
  );
}
