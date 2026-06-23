import { useState, useEffect, useCallback, useRef } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/AdminMonitoring.css";

import GarimPage from "../../components/garim/GarimPage";
import {
  getMonitoringOverview,
  getMonitoringActivities,
  cancelMonitoringJob,
} from "../../utils/api";

// analysis_jobs 상태 → 화면 표시 메타(라벨/색상/칩 클래스)
const STATUS_META = {
  processing: { label: "처리 중", dot: "#1976d2", chip: "mui-chip--soft-primary" },
  queued:     { label: "대기 중", dot: "#ed6c02", chip: "mui-chip--soft-warning" },
  done:       { label: "완료",   dot: "#2e7d32", chip: "mui-chip--soft-success" },
  error:      { label: "오류",   dot: "#d32f2f", chip: "mui-chip--soft-error" },
  idle:       { label: "유휴",   dot: "#bdbdbd", chip: "" },
};

// 10초 간격 자동 갱신
const REFRESH_INTERVAL_MS = 10000;

export default function AdminMonitoring() {
  useDocumentTitle("사용자 모니터링 · Garim Admin");

  const [overview,   setOverview]   = useState(null);
  const [activities, setActivities] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState(null);
  const [canceling,  setCanceling]  = useState(false);

  // 선택 상태를 비동기 콜백 내부에서 참조하기 위한 ref
  const selectedIdRef = useRef(null);
  selectedIdRef.current = selectedId;

  // 데이터 로딩 (overview + activities 동시 호출)
  const fetchData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const [ovRes, actRes] = await Promise.all([
        getMonitoringOverview(),
        getMonitoringActivities({ limit: 50 }),
      ]);
      if (ovRes) setOverview(ovRes.data);
      if (actRes) {
        const list = actRes.data.activities || [];
        setActivities(list);
        // 선택된 사용자가 없거나 목록에서 사라졌으면 첫 행 선택
        const stillExists = list.some((a) => a.id === selectedIdRef.current);
        if (!stillExists && list.length > 0) {
          setSelectedId(list[0].id);
        }
      }
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  // 최초 로딩 + 주기적 폴링
  useEffect(() => {
    fetchData(true);
    const timer = setInterval(() => fetchData(false), REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchData]);

  const selected = activities.find((u) => u.id === selectedId);

  // 실시간 활동 헤더 칩에 표시할 상태별 카운트
  const statusCount = activities.reduce(
    (acc, a) => {
      acc[a.status] = (acc[a.status] || 0) + 1;
      return acc;
    },
    {}
  );

  // 처리 중 작업 플랜 분포 문자열 (예: "Free 24 · Pro 9")
  const planBreakdownText =
    overview && overview.plan_breakdown && Object.keys(overview.plan_breakdown).length > 0
      ? Object.entries(overview.plan_breakdown).map(([k, v]) => `${k} ${v}`).join(" · ")
      : "—";

  // 평균 대기 시간 표시
  const avgWaitText = overview ? `평균 대기 ${overview.avg_wait_seconds}초` : "—";

  // 작업 취소 핸들러
  const handleCancelJob = async () => {
    if (!selected || selected.job_file === "—") return;
    if (!["processing", "queued"].includes(selected.status)) return;
    if (!window.confirm(`${selected.email} 사용자의 작업을 취소하시겠습니까?`)) return;
    setCanceling(true);
    try {
      await cancelMonitoringJob(selected.job_id);
      await fetchData(false);
    } catch (e) {
      alert("작업 취소 실패: " + e.message);
    } finally {
      setCanceling(false);
    }
  };

  return (
    <GarimPage bodyClass="" screenLabel="25 Admin monitor">
      <div className="adm-shell">
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring" className="active">
            <span className="material-icons">monitor_heart</span>
            사용자 모니터링
          </a>
          <a href="/admin/queue">
            <span className="material-icons">queue</span>
            처리 큐
          </a>
          <a href="/admin/compliance">
            <span className="material-icons">verified_user</span>
            컴플라이언스
          </a>
          <div className="sec">시스템</div>
          <a href="/admin/users">
            <span className="material-icons">people</span>
            사용자
          </a>
          <a href="/admin/analytics">
            <span className="material-icons">analytics</span>
            분석
          </a>
          <a href="/admin/policy">
            <span className="material-icons">tune</span>
            정책 및 상품 관리
          </a>
          <a href="/admin/subscriptions">
            <span className="material-icons">subscriptions</span>
            구독 관리
          </a>
          <a href="/admin/payments">
            <span className="material-icons">payments</span>
            사용자 결제 확인
          </a>
          <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
        <main className="adm-main">
          <div className="adm-head">
            <h1>사용자 모니터링</h1>
            <span className="live-badge">
              <span className="live-dot" />
              LIVE
            </span>
            <span className="meta">실시간 활동 중인 사용자 · 10초 갱신</span>
            <div className="mon-toolbar-right">
              <button className="mui-btn mui-btn--outlined mui-btn--sm" onClick={() => fetchData(true)}>
                <span className="material-icons mon-ico-sm">refresh</span>
                새로고침
              </button>
            </div>
          </div>

          <div className="metric-row">
            <div className="metric">
              <div className="lbl">현재 접속자</div>
              <div className="num">{overview ? overview.current_online : "—"}</div>
              <div className="delta">
                {overview
                  ? `${overview.online_delta >= 0 ? "↑" : "↓"} ${Math.abs(overview.online_delta)} (1시간 전 대비)`
                  : ""}
              </div>
            </div>
            <div className="metric">
              <div className="lbl">처리 중</div>
              <div className="num">{overview ? overview.processing : "—"}</div>
              <div className="delta">{planBreakdownText}</div>
            </div>
            <div className="metric warn">
              <div className="lbl">대기 중</div>
              <div className="num">{overview ? overview.queued : "—"}</div>
              <div className="delta">{avgWaitText}</div>
            </div>
            <div className="metric">
              <div className="lbl">금일 완료</div>
              <div className="num">{overview ? overview.today_completed : "—"}</div>
              <div className="delta">
                {overview ? `오류 ${overview.today_error}건 (${overview.error_rate}%)` : ""}
              </div>
            </div>
          </div>

          <div className="adm-grid">
            <div className="adm-card">
              <div className="head">
                <h3>실시간 사용자 활동</h3>
                <span className="mui-chip mui-chip--soft-primary">처리 중 {statusCount.processing || 0}</span>
                <span className="mui-chip mui-chip--soft-warning">대기 {statusCount.queued || 0}</span>
                <span className="mui-chip mui-chip--soft-error">오류 {statusCount.error || 0}</span>
              </div>
              <div className="mon-row tbl-head">
                <span />
                <span>사용자</span>
                <span>플랜</span>
                <span>현재 작업</span>
                <span>진행률</span>
                <span>경과</span>
                <span>마지막 활동</span>
                <span />
              </div>

              {loading && (
                <div className="mon-state">
                  불러오는 중…
                </div>
              )}
              {!loading && error && (
                <div className="mon-state mon-state--error">
                  {error}
                </div>
              )}
              {!loading && !error && activities.length === 0 && (
                <div className="mon-state mon-state--empty">
                  최근 24시간 내 활동 중인 사용자가 없습니다.
                </div>
              )}

              {!loading && !error && activities.map((u) => {
                const sm = STATUS_META[u.status] || STATUS_META.idle;
                const isPro = u.plan && u.plan !== "Free";
                return (
                  <div
                    key={u.id}
                    className={`mon-row${selectedId === u.id ? " selected" : ""}`}
                  >
                    <span
                      className="status-dot"
                      style={{ background: sm.dot }}
                      title={sm.label}
                    />
                    <span>
                      <div className="mon-email">
                        {/* @ 이후 도메인을 줄바꿈 허용 — 이메일이 길어도 열 넘침 방지 */}
                        {u.email.includes("@")
                          ? <>{u.email.split("@")[0]}<wbr />@{u.email.split("@")[1]}</>
                          : u.email}
                      </div>
                      <div className="mon-uid">{u.id.slice(0, 8)}</div>
                    </span>
                    <span>
                      <span className={`mui-chip ${isPro ? "mui-chip--soft-warning" : ""}`}>
                        {u.plan}
                      </span>
                    </span>
                    <span>
                      {u.job_file !== "—" ? (
                        <>
                          <div className="mon-filename">{u.job_file}</div>
                          <div className="mon-type">{u.job_type}</div>
                        </>
                      ) : (
                        <span className="mon-dash">—</span>
                      )}
                    </span>
                    <span>
                      {u.status !== "idle" && u.job_file !== "—" ? (
                        <div className="mon-progress-wrap">
                          <div className="mon-progress-bar">
                            <div
                              style={{
                                width: `${u.progress}%`,
                                background: u.status === "error" ? "#d32f2f" : u.status === "done" ? "#2e7d32" : "#1976d2",
                              }}
                            />
                          </div>
                          <span className="mon-pct">{u.progress}%</span>
                        </div>
                      ) : (
                        <span className="mon-dash">—</span>
                      )}
                    </span>
                    <span className="mon-elapsed">{u.elapsed}</span>
                    <span>
                      <span className={`mui-chip ${sm.chip} mon-status-chip`}>
                        {sm.label}
                      </span>
                      <div className="mon-lastseen">{u.last_seen}</div>
                    </span>
                    <span>
                      <button
                        className={`mon-view-btn${selectedId === u.id ? " active" : ""}`}
                        onClick={() => setSelectedId(u.id)}
                      >
                        확인
                      </button>
                    </span>
                  </div>
                );
              })}

              {!loading && !error && activities.length > 0 && (
                <div className="mon-footer">
                  활동 사용자 {activities.length}명 표시 중
                </div>
              )}
            </div>

            {selected && (
              <aside className="adm-card">
                <div className="head">
                  <h3>{selected.email}</h3>
                  <span className={`mui-chip ${(STATUS_META[selected.status] || STATUS_META.idle).chip} mon-chip-sm`}>
                    {(STATUS_META[selected.status] || STATUS_META.idle).label}
                  </span>
                </div>
                <div className="detail-body">
                  <section className="detail-section">
                    <h4>사용자 정보</h4>
                    <div className="detail-row"><span>UID</span><span className="mono">{selected.id.slice(0, 8)}</span></div>
                    <div className="detail-row"><span>플랜</span><span>{selected.plan}</span></div>
                    <div className="detail-row"><span>가입일</span><span className="mono">{selected.joined}</span></div>
                    <div className="detail-row"><span>IP</span><span className="mono">{selected.ip}</span></div>
                    <div className="detail-row"><span>브라우저</span><span>{selected.ua}</span></div>
                    <div className="detail-row"><span>세션 시작</span><span className="mono">{selected.session_start}</span></div>
                  </section>

                  <section className="detail-section">
                    <h4>작업 현황</h4>
                    {selected.job_file !== "—" ? (
                      <>
                        <div className="detail-row"><span>파일</span><span className="mono mon-break">{selected.job_file}</span></div>
                        <div className="detail-row"><span>유형</span><span>{selected.job_type}</span></div>
                        <div className="detail-row"><span>진행률</span>
                          <span className="mon-progress-inline">
                            <div className="detail-progress">
                              <div style={{
                                width: `${selected.progress}%`,
                                background: selected.status === "error" ? "#d32f2f" : selected.status === "done" ? "#2e7d32" : "#1976d2",
                              }} />
                            </div>
                            {selected.progress}%
                          </span>
                        </div>
                        <div className="detail-row"><span>경과 시간</span><span className="mono">{selected.elapsed}</span></div>
                      </>
                    ) : (
                      <div className="mon-no-job">현재 처리 중인 작업 없음</div>
                    )}
                    <div className="detail-row"><span>오늘 처리</span><span>{selected.today_jobs}건</span></div>
                    <div className="detail-row"><span>누적 처리</span><span>{selected.total_jobs}건</span></div>
                  </section>

                  <section className="detail-section">
                    <h4>최근 활동</h4>
                    <div className="activity-log">
                      {/* recent_events 배열: 세션시작 + 최근 작업 이력 최대 5개 */}
                      {(selected.recent_events && selected.recent_events.length > 0)
                        ? selected.recent_events.map((ev, i) => (
                          <div key={i}>
                            <span className="ts">{ev.ts}</span>
                            <span style={{
                              color: ev.status === "completed" ? "#2e7d32"
                                   : ev.status === "failed"    ? "#d32f2f"
                                   : ev.status === "cancelled" ? "#9e9e9e"
                                   : undefined,
                            }}>{ev.label}</span>
                          </div>
                        ))
                        : (
                          <>
                            <div><span className="ts">{selected.session_start}</span> 세션 시작</div>
                            {selected.job_file !== "—" && (
                              <>
                                <div><span className="ts">{selected.last_seen}</span> 작업 파일 ({selected.job_type})</div>
                                {selected.status === "done"       && <div><span className="ts">{selected.last_seen}</span> <span className="mon-evt-done">처리 완료</span></div>}
                                {selected.status === "error"      && <div><span className="ts">{selected.last_seen}</span> <span className="mon-evt-error">오류 발생</span></div>}
                                {selected.status === "processing" && <div><span className="ts">{selected.last_seen}</span> 처리 중 ({selected.progress}%)</div>}
                                {selected.status === "queued"     && <div><span className="ts">{selected.last_seen}</span> 큐 대기 중</div>}
                              </>
                            )}
                          </>
                        )
                      }
                    </div>
                  </section>

                  <section className="detail-section">
                    <h4>관리 액션</h4>
                    <div className="detail-actions">
                      <button
                        className="mui-btn mui-btn--outlined mui-btn--sm mon-action-btn"
                        disabled={canceling || selected.job_file === "—" || !["processing", "queued"].includes(selected.status)}
                        onClick={handleCancelJob}
                      >
                        <span className="material-icons mon-ico-15">cancel</span>
                        {canceling ? "취소 중…" : "작업 취소"}
                      </button>
                    </div>
                  </section>
                </div>
              </aside>
            )}
          </div>
        </main>
      </div>
    </GarimPage>
  );
}
