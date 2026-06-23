import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { useAuthUser } from "../../hooks/useAuthStatus";
import { getDashboardData, deleteAnalysisUpload, getApiBaseUrl, getDownloadUrl } from "../../utils/api";
import { useNotifications, relativeTime } from "../../context/NotificationContext";
import "../../css/garim-pages/Dashboard.css";

import GarimPage from "../../components/garim/GarimPage";

export default function Dashboard() {
  useDocumentTitle("마이 대시보드 · Garim");
  const { user } = useAuthUser();
  const displayEmail = user?.email || user?.provider_email || user?.name || "사용자";

  const { notifications } = useNotifications() || { notifications: [] };

  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer = null;

    async function loadData() {
      try {
        const data = await getDashboardData();
        if (!cancelled) setDashboardData(data);

        // If there are active jobs, poll every 3 seconds
        if (!cancelled && data?.active_jobs?.length > 0) {
          timer = setTimeout(loadData, 3000);
        }
      } catch (e) {
        console.error("Dashboard data load failed:", e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadData();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  async function handleDeleteUpload(uploadId, filename = "해당") {
    if (!window.confirm(`${filename} 작업을 취소하시겠습니까?`)) return;
    try {
      await deleteAnalysisUpload(uploadId);
      // Immediately refresh dashboard
      const data = await getDashboardData();
      setDashboardData(data);
    } catch (e) {
      alert("삭제 중 오류가 발생했습니다: " + e.message);
    }
  }

  async function handleDeleteAllActiveJobs() {
    if (!dashboardData?.active_jobs || dashboardData.active_jobs.length === 0) return;
    if (!window.confirm("진행 중인 모든 작업이 취소됩니다. 목록에서 삭제하시겠습니까?")) return;

    try {
      await Promise.all(
        dashboardData.active_jobs.map(job => job.upload_id ? deleteAnalysisUpload(job.upload_id) : Promise.resolve())
      );
      // Immediately refresh dashboard
      const data = await getDashboardData();
      setDashboardData(data);
    } catch (e) {
      alert("전체 취소 중 일부 오류가 발생했습니다: " + e.message);
    }
  }

  const getJobDetailLink = (job) => {
    if (job.job_type === "mask_final") {
      return "/replace-options";
    }
    if (job.status === "review_pending") {
      const jobId = job.job_id;
      const savedStage = localStorage.getItem(`job_stage_${jobId}`);
      return savedStage || "/analysis-progress";
    }
    return "/analysis-progress";
  };
  return (
    <GarimPage bodyClass="page-app" screenLabel="19 Dashboard">
      <div className="dash-page">
        <div className="dash-hero">
          <div>
            <h1>
              안녕하세요, {displayEmail}님 👋
            </h1>
            <p>
              지난주 검출한 영상은 안전하게 가려졌어요. 오늘은 어떤 영상을 점검해볼까요?
            </p>
          </div>
          <div className="cta-stack">
            <a onClick={() => alert("준비중입니다. 커밍쑨!")} className="mui-btn mui-btn--outlined mui-btn--lg">
              <span className="material-icons db-ico-20">
                share
              </span>
              인스타 점검(준비중)
            </a>
            <Link to="/upload" className="mui-btn mui-btn--contained mui-btn--lg">
              <span className="material-icons db-ico-20">
                cloud_upload
              </span>
              새 검출 시작
            </Link>
          </div>
        </div>
        <div className="stat-row">
          <div className="stat">
            <span className="ico">
              <span className="material-icons">visibility</span>
            </span>
            <div className="lbl">누적 검출</div>
            <div className="num">
              {dashboardData?.stats?.total_detections ?? 0}
              <small className="db-unit">건</small>
            </div>
            <div className="delta">누적 발견 수</div>
          </div>
          <div className="stat">
            <span className="ico">
              <span className="material-icons db-ico-purple">visibility_off</span>
            </span>
            <div className="lbl">치환 완료</div>
            <div className="num">
              {dashboardData?.stats?.total_replacements ?? 0}
              <small className="db-unit">건</small>
            </div>
            <div className="delta">누적 치환 수</div>
          </div>
          <div className="stat">
            <span className="ico">
              <span className="material-icons db-ico-danger">shield</span>
            </span>
            <div className="lbl">처리 완료 파일</div>
            <div className="num">
              {dashboardData?.stats?.completed_jobs ?? 0}
              <small className="db-unit">건</small>
            </div>
            <div className="delta">전체 {dashboardData?.stats?.completed_jobs ?? 0}건 완료</div>
          </div>
          <div className="stat">
            <span className="ico">
              <span className="material-icons db-ico-green">savings</span>
            </span>
            <div className="lbl">남은 무료 크레딧</div>
            <div className="num">
              <div className="db-credit-col">
                <div>
                  {dashboardData?.stats?.free_balance ?? 0}
                  <small className="db-unit"> 개</small>
                </div>
                <div className="db-credit-sub">
                  사용량: {dashboardData?.stats?.used_free_limit ?? 0}개, 익월 무료충전: {dashboardData?.stats?.expected_ai_refund ?? 0}개
                </div>
              </div>
            </div>
            <div className="delta db-delta-row">
              유료크레딧 결제일 기준(월 1회 충전)
              <span className="material-icons db-help-ico" title="AI 활용동의 일자 기준 1달간 유료 크레딧 누적 사용량 의 10% 무료 크래딧 충전">error_outline</span>
            </div>
          </div>
        </div>
        <div className="dash-grid">
          <div>
            <div className="card-block">
              <h2>
                진행 중인 작업
                <span className="mui-chip mui-chip--soft-info">
                  {dashboardData?.active_jobs?.length ?? 0}
                </span>
                <span className="spacer"></span>
                {dashboardData?.active_jobs?.length > 0 && (
                  <button
                    className="mui-btn mui-btn--outlined mui-btn--sm db-del-all"
                    onClick={handleDeleteAllActiveJobs}
                  >
                    전체 취소
                  </button>
                )}
              </h2>
              {loading ? (
                <div className="db-empty">데이터를 불러오는 중...</div>
              ) : dashboardData?.active_jobs?.length > 0 ? (
                dashboardData.active_jobs.map((job) => (
                  <div className="progress-row" key={job.job_id}>
                    <div className="thumb db-thumb">
                      {job.thumbnail_url ? (
                        <img src={`${getApiBaseUrl()}${job.thumbnail_url}`} alt="thumbnail" className="db-thumb-img" />
                      ) : (
                        <span className="material-icons db-thumb-ico">
                          {job.media_type === "video" ? "movie" : job.media_type === "audio" ? "graphic_eq" : "image"}
                        </span>
                      )}
                    </div>
                    <div className="body">
                      <div className="name">{job.filename}</div>
                      <div className="meta">
                        {job.status === "review_pending" ? "마스킹 대기 중" : job.status === "queued" ? "대기 중" : job.status === "failed" ? "처리 실패" : "진행 중"}
                        {job.status !== "review_pending" && job.status !== "failed" && ` · ${job.progress}%`}
                      </div>
                      <div className="progress">
                        <div className="progress__bar" style={{ width: `${job.status === "review_pending" || job.status === "failed" ? 100 : job.progress}%`, background: job.status === "failed" ? "var(--error)" : undefined }}></div>
                      </div>
                    </div>
                    <div className="actions-group">
                      <Link to={getJobDetailLink(job)} state={{ jobId: job.job_id }} className="mui-btn mui-btn--text mui-btn--sm">
                        상세 →
                      </Link>
                      <button
                        className="delete-btn"
                        title="작업 삭제"
                        onClick={() => handleDeleteUpload(job.upload_id, job.filename)}
                        disabled={!job.upload_id}
                      >
                        <span className="material-icons db-ico-18">delete</span>
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ padding: "24px", textAlign: "center", color: "var(--fg-3)" }}>진행 중인 작업이 없습니다.</div>
              )}
            </div>
            <div className="card-block">
              <h2>
                최근 처리 이력
                <span className="spacer"></span>
                <Link to="/history">전체 보기 →</Link>
              </h2>
              {loading ? (
                <div className="db-empty">데이터를 불러오는 중...</div>
              ) : dashboardData?.recent_jobs?.length > 0 ? (
                dashboardData.recent_jobs.map((job) => (
                  <div className="hist-row db-hist-row" key={job.job_id}>
                    <div className="db-hist-left">
                      <div className="thumb db-thumb-fs">
                        {job.thumbnail_url ? (
                          <img src={`${getApiBaseUrl()}${job.thumbnail_url}`} alt="thumbnail" className="db-thumb-img" />
                        ) : (
                          <span className="material-icons db-thumb-ico">
                            {job.media_type === "video" ? "movie" : job.media_type === "audio" ? "graphic_eq" : "image"}
                          </span>
                        )}
                      </div>
                      {job.status === "completed" ? (
                        job.detected > 0 && job.replaced < job.detected ? (
                          <span className="mui-chip mui-chip--soft-warning db-chip-partial">
                            일부완료
                          </span>
                        ) : (
                          <span className="mui-chip mui-chip--soft-success db-chip-shrink">완료</span>
                        )
                      ) : (
                        <span className="mui-chip mui-chip--soft-error db-chip-shrink">실패</span>
                      )}
                      <div className="body db-hist-body">
                        <div className="name db-hist-name">{job.filename}</div>
                        <div className="meta db-hist-meta">
                          · {new Date(job.created_at).toLocaleDateString()} · {job.status === "completed" ? (job.detected > 0 && job.replaced < job.detected ? "일부 완료" : "처리 완료") : "실패"} · {job.replaced}건 처리
                        </div>
                      </div>
                    </div>
                    <div className="right db-hist-right">
                      {job.status === "completed" && job.job_type === "mask_final" && (
                        <a href={getDownloadUrl(job.job_id)} title="다운로드" className="mui-btn mui-btn--text mui-btn--sm btn-download-green db-act-icon">
                          <span className="material-icons db-ico-18">download</span>
                        </a>
                      )}
                      {job.status === "completed" && (
                        <Link to={getJobDetailLink(job)} state={{ jobId: job.job_id, fromDashboard: true }} className="mui-btn mui-btn--outlined mui-btn--sm db-act-detail">
                          상세
                        </Link>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ padding: "24px", textAlign: "center", color: "var(--fg-3)" }}>최근 처리 이력이 없습니다.</div>
              )}
            </div>
          </div>
          <aside>
            <div className="card-block sns-widget">
              <h2>
                SNS 셀프 점검
              </h2>
              <div className="big-num db-big-num">
                준비중
              </div>
              {/* 
              <div className="big-num">
                9
                <small style={{ fontSize: "18px", color: "var(--fg-2)" }}>
                  건
                </small>
              </div>
              <p className="desc">
                최근 스캔에서 위험 게시물 9건이 발견됐어요. 1주일 전 점검 결과입니다.
              </p>
              <a href="/sns-results" className="mui-btn mui-btn--contained mui-btn--block" style={{ background: "#9747ff" }}>
                결과 다시 보기 →
              </a>
              */}
            </div>
            <div className="card-block">
              <h2>알림</h2>
              {notifications.length > 0 ? (
                notifications.slice(0, 2).map((notif) => (
                  <div
                    key={notif.id}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "8px",
                      padding: "10px 0",
                      borderBottom: "1px solid var(--mui-divider)",
                    }}
                  >
                    <span
                      className="material-icons"
                      style={{
                        fontSize: "18px",
                        marginTop: "1px",
                        color: notif.type === "analysis_complete" ? "#9747ff" : "#2e7d32",
                      }}
                    >
                      {notif.type === "analysis_complete" ? "analytics" : "check_circle"}
                    </span>
                    <div>
                      <div className="db-noti-body">
                        {notif.msg}
                      </div>
                      <div className="db-noti-time">
                        {relativeTime(notif.createdAt)}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="db-noti-empty">
                  새로운 알림이 없습니다.
                </div>
              )}
            </div>
            <div className="card-block tip-card">
              <h3>
                💡 팁 — Pro 플랜 전환
              </h3>
              <p>
                지난 30일간 무료 한도(월 5회)에 가까웠어요. v1 정식 출시 시 Pro 플랜으로 월 50회까지 처리할 수 있어요.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </GarimPage>
  );
}
