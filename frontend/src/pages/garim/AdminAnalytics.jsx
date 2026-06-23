import { useState, useEffect } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/AdminAnalytics.css";

import GarimPage from "../../components/garim/GarimPage";
import { getAdminAnalytics } from "../../utils/api";

export default function AdminAnalytics() {
  useDocumentTitle("분석 · Garim Admin");

  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      setLoading(true);
      try {
        const res = await getAdminAnalytics(days);
        if (res.data) {
          setData(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch analytics:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, [days]);

  const handleCsvExport = () => {
    if (!data) return;
    
    let csvContent = "\uFEFF"; // BOM for Excel

    // 1. 요약 지표
    csvContent += "=== 핵심 요약 지표 ===\n";
    csvContent += `처리 건수,"${data.metrics.jobs.value} (전 기간 대비 ${data.metrics.jobs.delta}%)"\n`;
    csvContent += `신규 가입,"${data.metrics.users.value} (전 기간 대비 ${data.metrics.users.delta}%)"\n`;
    csvContent += `평균 처리 시간,"${data.metrics.duration.value}s (전 기간 대비 ${data.metrics.duration.delta}s)"\n`;
    csvContent += `처리 성공률,"${data.metrics.success_rate.value}% (전 기간 대비 ${data.metrics.success_rate.delta}%)"\n\n`;

    // 2. 제공자별 가입 비율
    csvContent += "=== 제공자별 가입 비율 ===\n";
    csvContent += "제공자,가입 수,비율\n";
    data.providers.forEach(p => {
      csvContent += `"${p.provider}","${p.count}","${p.pct}%"\n`;
    });
    csvContent += "\n";

    // 3. 요금제별 사용 현황
    csvContent += "=== 요금제별 사용 현황 ===\n";
    csvContent += "요금제,사용자 수,처리 건수,평균 파일 크기,비율\n";
    data.plans.forEach(p => {
      csvContent += `"${p.plan}","${p.users}","${p.jobs}","${p.avgSize}","${p.pct}%"\n`;
    });
    csvContent += "\n";

    // 4. 처리 실패 유형
    csvContent += "=== 처리 실패 유형 ===\n";
    csvContent += "오류 유형,건수,비율\n";
    data.errors.forEach(e => {
      csvContent += `"${e.type}","${e.count}","${e.pct}%"\n`;
    });
    csvContent += "\n";

    // 5. 일별 처리 건수
    csvContent += "=== 일별 처리 건수 ===\n";
    csvContent += "날짜,처리 건수\n";
    data.daily_jobs.forEach(d => {
      csvContent += `"${d.date}","${d.count}"\n`;
    });

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `analytics_report_${days}days.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const renderDelta = (delta, unit = "%") => {
    if (delta > 0) return `↑ ${delta}${unit} vs 전 기간`;
    if (delta < 0) return `↓ ${Math.abs(delta)}${unit} vs 전 기간`;
    return `- 0${unit} vs 전 기간`;
  };

  return (
    <GarimPage bodyClass="" screenLabel="29 Admin analytics">
      <div className="adm-shell">
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring">
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
          <a href="/admin/analytics" className="active">
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
            <h1>분석</h1>
            <span className="meta">서비스 지표 · 최근 {days}일</span>
            <div className="an-toolbar-right">
              <select className="an-period-sel" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                <option value={7}>최근 7일</option>
                <option value={30}>최근 30일</option>
                <option value={90}>최근 90일</option>
              </select>
              <button className="mui-btn mui-btn--outlined mui-btn--sm" onClick={handleCsvExport} disabled={loading || !data}>
                <span className="material-icons an-export-ico">file_download</span>
                CSV Export
              </button>
            </div>
          </div>

          {loading || !data ? (
            <div className="an-loading">데이터를 불러오는 중입니다...</div>
          ) : (
            <>
              <div className="metric-row">
                <div className="metric">
                  <div className="lbl">처리 건수</div>
                  <div className="num">{data.metrics.jobs.value.toLocaleString()}</div>
                  <div className="delta">{renderDelta(data.metrics.jobs.delta)}</div>
                </div>
                <div className="metric">
                  <div className="lbl">신규 가입</div>
                  <div className="num">{data.metrics.users.value.toLocaleString()}</div>
                  <div className="delta">{renderDelta(data.metrics.users.delta)}</div>
                </div>
                <div className="metric warn">
                  <div className="lbl">평균 처리 시간</div>
                  <div className="num">{data.metrics.duration.value}s</div>
                  <div className="delta">{renderDelta(data.metrics.duration.delta, "s")}</div>
                </div>
                <div className="metric">
                  <div className="lbl">처리 성공률</div>
                  <div className="num">{data.metrics.success_rate.value}%</div>
                  <div className="delta">{renderDelta(data.metrics.success_rate.delta)}</div>
                </div>
              </div>

              <div className="an-grid">
                <div className="adm-card">
                  <div className="head">
                    <h3>일별 처리 건수</h3>
                    <span className="meta">최근 {days}일</span>
                  </div>
                  <div className="body an-chart-placeholder an-chart-scroll">
                    <div className="an-plan-row tbl-head">
                      <span>날짜</span>
                      <span>처리 건수</span>
                    </div>
                    {data.daily_jobs.map((d) => (
                      <div className="an-plan-row an-plan-row--bordered" key={d.date}>
                        <span>{d.date}</span>
                        <span>{d.count.toLocaleString()}</span>
                      </div>
                    ))}
                    {data.daily_jobs.length === 0 && <div className="an-empty">데이터 없음</div>}
                  </div>
                </div>
                <div className="adm-card">
                  <div className="head">
                    <h3>제공자별 가입 비율</h3>
                  </div>
                  <div className="body an-chart-placeholder an-chart-scroll">
                    <div className="an-plan-row tbl-head">
                      <span>제공자</span>
                      <span>가입 수</span>
                      <span>비율</span>
                    </div>
                    {data.providers.map((p) => (
                      <div className="an-plan-row an-plan-row--bordered" key={p.provider}>
                        <span>{p.provider}</span>
                        <span>{p.count.toLocaleString()}</span>
                        <span>{p.pct}%</span>
                      </div>
                    ))}
                    {data.providers.length === 0 && <div className="an-empty">데이터 없음</div>}
                  </div>
                </div>
              </div>

              <div className="adm-card adm-card--mt">
                <div className="head">
                  <h3>요금제별 사용 현황</h3>
                </div>
                <div className="body">
                  <div className="an-plan-row tbl-head">
                    <span>요금제</span>
                    <span>사용자 수</span>
                    <span>처리 건수</span>
                    <span>평균 파일 크기</span>
                    <span>비율</span>
                  </div>
                  {data.plans.map((r) => (
                    <div className="an-plan-row" key={r.plan}>
                      <span><span className="mui-chip">{r.plan}</span></span>
                      <span>{r.users}</span>
                      <span>{r.jobs}</span>
                      <span>{r.avgSize}</span>
                      <span>{r.pct}</span>
                    </div>
                  ))}
                  {data.plans.length === 0 && <div className="an-empty">데이터 없음</div>}
                </div>
              </div>

              <div className="adm-card adm-card--mt">
                <div className="head">
                  <h3>처리 실패 유형</h3>
                </div>
                <div className="body">
                  <div className="an-err-row tbl-head">
                    <span>오류 유형</span>
                    <span>건수</span>
                    <span>비율</span>
                  </div>
                  {data.errors.map((r) => (
                    <div className="an-err-row" key={r.type}>
                      <span>{r.type}</span>
                      <span>{r.count}</span>
                      <span>{r.pct}</span>
                    </div>
                  ))}
                  {data.errors.length === 0 && <div className="an-empty">데이터 없음</div>}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </GarimPage>
  );
}
