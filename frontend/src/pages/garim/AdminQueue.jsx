import { useCallback, useEffect, useRef, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getQueueOverview } from "../../utils/api";
import "../../css/garim-pages/AdminQueue.css";

import GarimPage from "../../components/garim/GarimPage";

// 경과 초 → 'm:ss' 또는 'Nh' 형식
function fmtElapsed(sec) {
  if (!sec && sec !== 0) return "—";
  const s = Math.max(0, Math.round(Number(sec)));
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, "0")}`;
  }
  return `${Math.floor(s / 3600)}h`;
}

// 평균 대기 초 → '분:초' 또는 '초' 표시
function fmtWait(sec) {
  if (!sec) return "0";
  const s = Math.round(sec);
  if (s < 60) return String(s);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// 플랜명 → MUI chip 클래스
function planChip(plan) {
  if (!plan) return "mui-chip";
  const lower = plan.toLowerCase();
  if (lower === "pro")    return "mui-chip mui-chip--soft-warning";
  if (lower === "studio") return "mui-chip mui-chip--secondary";
  return "mui-chip"; // Free
}

// 24h 시간별 데이터 → SVG path 문자열 생성 (영역 채우기용)
function hourlyToPath(data, w = 600, h = 140, fillClose = false) {
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => {
    const x = Math.round((i / (data.length - 1)) * w);
    const y = Math.round(h - (v / max) * (h - 10));
    return `${x},${y}`;
  });
  const line = pts.join(" L");
  if (fillClose) return `M${line} L${w},${h} L0,${h} Z`;
  return `M${line}`;
}

// 워커 상태 색상
function workerColor(sec) {
  if (sec < 30)  return "#2e7d32"; // 정상 (초록)
  if (sec < 120) return "#ed6c02"; // 경고 (주황)
  return "#d32f2f";                // 이상 (빨강)
}

// ─────────────────────────────────────────────
// 상수: 10초 폴링 간격
const POLL_MS = 10_000;

export default function AdminQueue() {
  useDocumentTitle("처리 큐 관리 · Garim Admin");

  const [data, setData]     = useState(null);  // 전체 응답 캐시
  const [error, setError]   = useState(null);
  const [lastAt, setLastAt] = useState(null);
  const timerRef            = useRef(null);

  const load = useCallback(async () => {
    try {
      const res = await getQueueOverview();
      setData(res?.data ?? res);
      setError(null);
      setLastAt(new Date());
    } catch (e) {
      setError(e?.message || "데이터를 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, [load]);

  // 데이터 추출 (null-safe)
  const metrics  = data?.metrics  ?? {};
  const jobs     = data?.jobs     ?? [];
  const workers  = data?.workers  ?? [];
  const hourly   = data?.hourly_throughput ?? Array(24).fill(0);

  const totalQueue    = metrics.total_queue    ?? 0;
  const queued        = metrics.queued         ?? 0;
  const processing    = metrics.processing     ?? 0;
  const avgWait       = metrics.avg_wait_seconds ?? 0;
  const throughput    = metrics.throughput_last_hour ?? 0;
  const errorRate     = metrics.error_rate     ?? 0;
  const activeWorkers = metrics.active_workers ?? 0;
  const planCounts    = metrics.plan_counts    ?? {};

  // 24h 완료 합계
  const total24h = hourly.reduce((a, b) => a + b, 0);

  // SVG path
  const areaPath = hourlyToPath(hourly, 600, 140, true);
  const linePath = hourlyToPath(hourly, 600, 140, false);

  // 시간 레이블 (폴링 시각)
  const timeLbl = lastAt
    ? lastAt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";

  // 플랜칩 카운트 (Free / Pro / Studio 순)
  const freeCnt   = planCounts["Free"]   ?? planCounts["free"]   ?? 0;
  const proCnt    = planCounts["Pro"]    ?? planCounts["pro"]    ?? 0;
  const studioCnt = planCounts["Studio"] ?? planCounts["studio"] ?? 0;

  return (
    <GarimPage bodyClass="" screenLabel="26 Admin queue">
      <div className="adm-shell">
        {/* ── 사이드바 ── */}
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring">
            <span className="material-icons">monitor_heart</span>
            사용자 모니터링
          </a>
          <a href="/admin/queue" className="active">
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

        {/* ── 메인 ── */}
        <main className="adm-main">
          {/* 헤더 */}
          <div className="adm-head">
            <h1>처리 큐 관리</h1>
            <span className="live-badge">
              <span className="live-dot" />
              LIVE
            </span>
            <span className="adm-head-meta">
              실시간 DB 연동 · 10초 갱신 · 마지막: {timeLbl}
            </span>
            {error && (
              <span className="aq-error">
                ⚠ {error}
              </span>
            )}
          </div>

          {/* ── 메트릭 카드 ── */}
          <div className="metric-row">
            <div className="metric">
              <div className="lbl">현재 큐</div>
              <div className="num">{totalQueue}</div>
              <div className="delta">대기 {queued} · 처리 {processing}</div>
            </div>
            <div className={`metric ${avgWait > 60 ? "warn" : ""}`}>
              <div className="lbl">평균 대기</div>
              <div className="num">
                {fmtWait(avgWait)}
                <small className="aq-unit">
                  {avgWait < 60 ? "초" : "분"}
                </small>
              </div>
              <div className="delta">SLA 60초 이내</div>
            </div>
            <div className="metric">
              <div className="lbl">시간당 완료</div>
              <div className="num">{throughput}</div>
              <div className="delta">최근 1시간</div>
            </div>
            <div className={`metric ${errorRate >= 5 ? "danger" : errorRate >= 3 ? "warn" : ""}`}>
              <div className="lbl">실패율</div>
              <div className="num">
                {errorRate.toFixed(1)}
                <small className="aq-unit">%</small>
              </div>
              <div className="delta">
                {errorRate < 3 ? "정상 (목표 <3%)" : "주의 필요"}
              </div>
            </div>
            <div className="metric">
              <div className="lbl">활성 워커</div>
              <div className="num">{activeWorkers}</div>
              <div className="delta">
                {activeWorkers === 0 ? "heartbeat 없음" : "5분 내 heartbeat"}
              </div>
            </div>
            <div className="metric">
              <div className="lbl">24h 완료</div>
              <div className="num">{total24h.toLocaleString()}</div>
              <div className="delta">최근 24시간 완료 건</div>
            </div>
          </div>

          {/* ── 차트 영역 ── */}
          <div className="charts">
            {/* 24h 시간별 처리량 */}
            <div className="chart-card">
              <h3>
                시간별 처리량 (24h)
                <span className="spacer" />
                <span className="caption-k aq-cap-11">
                  완료 {total24h.toLocaleString()}건
                </span>
              </h3>
              <div className="chart-area">
                <svg viewBox="0 0 600 160" preserveAspectRatio="none"
                  className="aq-chart-svg">
                  <defs>
                    <linearGradient id="ch1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="rgba(25,118,210,0.3)" />
                      <stop offset="100%" stopColor="rgba(25,118,210,0)" />
                    </linearGradient>
                  </defs>
                  <g stroke="#e0e0e0" strokeWidth="1">
                    <line x1="0" y1="40"  x2="600" y2="40" />
                    <line x1="0" y1="80"  x2="600" y2="80" />
                    <line x1="0" y1="120" x2="600" y2="120" />
                  </g>
                  {total24h > 0 && (
                    <>
                      <path d={areaPath} fill="url(#ch1)" />
                      <path d={linePath} fill="none" stroke="#1976d2" strokeWidth="2" />
                    </>
                  )}
                  <g fontFamily="Pretendard" fontSize="10" fill="#9e9e9e">
                    <text x="0"   y="155">00:00</text>
                    <text x="200" y="155">08:00</text>
                    <text x="400" y="155">16:00</text>
                    <text x="565" y="155">23:00</text>
                  </g>
                </svg>
              </div>
            </div>

            {/* 큐 상태 현황 (바 차트) */}
            <div className="chart-card">
              <h3>큐 현황</h3>
              <div className="chart-area aq-queue-chart">
                {[
                  { label: "처리 중", value: processing, color: "#1976d2", total: totalQueue || 1 },
                  { label: "대기 중", value: queued,     color: "#9747ff", total: totalQueue || 1 },
                ].map(({ label, value, color, total }) => (
                  <div key={label}>
                    <div className="aq-bar-label">
                      <span>{label}</span>
                      <span className="aq-bar-value">
                        {value}건
                      </span>
                    </div>
                    <div className="aq-bar-track">
                      <div style={{
                        width: `${Math.min(100, Math.round(value / total * 100))}%`,
                        height: "100%", background: color, borderRadius: 4,
                        transition: "width 0.4s",
                      }} />
                    </div>
                  </div>
                ))}
                <div className="aq-chip-row">
                  {freeCnt > 0   && <span className="mui-chip mui-chip--md">Free {freeCnt}</span>}
                  {proCnt > 0    && <span className="mui-chip mui-chip--soft-warning mui-chip--md">Pro {proCnt}</span>}
                  {studioCnt > 0 && <span className="mui-chip mui-chip--secondary mui-chip--md">Studio {studioCnt}</span>}
                  {totalQueue === 0 && (
                    <span className="aq-empty-text">
                      현재 대기 없음
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* ── 하단: 작업 목록 + 워커 상태 ── */}
          <div className="lower">
            {/* 현재 처리 중 작업 목록 */}
            <div className="adm-card">
              <div className="head">
                <h3>현재 처리 중 / 대기 작업 — {jobs.length}건</h3>
                {freeCnt > 0   && <span className="mui-chip mui-chip--soft-info">Free {freeCnt}</span>}
                {proCnt > 0    && <span className="mui-chip mui-chip--soft-warning">Pro {proCnt}</span>}
                {studioCnt > 0 && <span className="mui-chip mui-chip--secondary">Studio {studioCnt}</span>}
              </div>

              {/* 테이블 헤더 */}
              <div className="job-row tbl-head">
                <span>작업 ID</span>
                <span>사용자 / 파일</span>
                <span>플랜</span>
                <span>진행률</span>
                <span>경과</span>
                <span />
              </div>

              {jobs.length === 0 ? (
                <div className="aq-empty">
                  처리 중인 작업이 없습니다.
                </div>
              ) : (
                jobs.map((job) => (
                  <div className="job-row" key={job.job_id}>
                    {/* 작업 ID */}
                    <span className="jid">{job.short_id}</span>
                    {/* 파일 정보 */}
                    <div className="file">
                      <div className="aq-job-email">
                        {job.email}
                      </div>
                      {job.filename !== "—" ? job.filename : "—"}
                      {job.detection_count > 0 && (
                        <small>{job.detection_count}건 탐지</small>
                      )}
                    </div>
                    {/* 플랜 */}
                    <span>
                      <span className={`${planChip(job.plan)} mui-chip--md`}>
                        {job.plan || "Free"}
                      </span>
                    </span>
                    {/* 진행률 */}
                    <div>
                      <div className="progress-mini">
                        <div style={{
                          width: `${job.progress}%`,
                          background: job.status === "queued" ? "#9e9e9e" : undefined,
                        }} />
                      </div>
                      <span className="caption-k aq-cap-11">
                        {job.status === "queued"
                          ? `대기 중${job.queue_position != null ? ` (${job.queue_position}번)` : ""}`
                          : `${job.progress}%`}
                      </span>
                    </div>
                    {/* 경과 */}
                    <span className="caption-k">{job.elapsed}</span>
                    {/* 메뉴 버튼 */}
                    <button className="mui-btn mui-btn--text mui-btn--sm">⋯</button>
                  </div>
                ))
              )}
            </div>

            {/* GPU 워커 상태 */}
            <div className="adm-card">
              <div className="head">
                <h3>활성 워커 상태</h3>
                <span className="caption-k aq-cap-11">
                  {activeWorkers}개 활성 (최근 5분 heartbeat)
                </span>
              </div>

              {workers.length === 0 ? (
                <div className="gpu-grid aq-gpu-empty-wrap">
                  <div className="aq-gpu-empty">
                    <span className="material-icons aq-gpu-empty-ico">cloud_off</span>
                    최근 5분 내 heartbeat가 없습니다.
                    <div className="aq-gpu-empty-sub">
                      워커가 연결되면 자동으로 표시됩니다.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="gpu-grid">
                  {workers.map((w) => {
                    const isAlert = w.last_beat_seconds >= 120;
                    const isWarn  = w.last_beat_seconds >= 30 && !isAlert;
                    return (
                      <div className={`gpu-card${isAlert ? " alert" : ""}`} key={w.worker_id}>
                        <h4>
                          <span className="material-icons"
                            style={{ fontSize: 14, color: workerColor(w.last_beat_seconds) }}>
                            {isAlert ? "warning" : "memory"}
                          </span>
                          {w.worker_id} · {w.worker_type}
                        </h4>
                        <div className={`util${isAlert ? " err" : isWarn ? " warn" : ""}`}>
                          {w.progress}
                          <small className="aq-unit">%</small>
                        </div>
                        <div className="util-bar">
                          <div style={{
                            width: `${w.progress}%`,
                            background: isAlert ? "#d32f2f" : isWarn ? "#ed6c02" : undefined,
                          }} />
                        </div>
                        <div className="stat-row aq-stat-row">
                          <span style={{ color: isAlert ? "#d32f2f" : undefined }}>
                            {w.stage || "—"}
                          </span>
                          <span style={{ color: isAlert ? "#d32f2f" : "var(--fg-2)" }}>
                            {w.last_beat_seconds < 60
                              ? `${w.last_beat_seconds}초 전`
                              : `${Math.floor(w.last_beat_seconds / 60)}분 전`}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </GarimPage>
  );
}
