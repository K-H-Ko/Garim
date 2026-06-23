import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getAdminReports, getAdminReportDetail, updateAdminReportStatus, deleteAdminReport, getApiBaseUrl } from "../../utils/api";
import GarimHeader from "../../components/garim/GarimHeader";
import "../../css/garim-pages/AdminReports.css";

// 탭 정의 (report_type)
const TABS = [
  { id: "all",        label: "전체" },
  { id: "general",    label: "일반 문의" },
  { id: "billing",    label: "결제/구독" },
  { id: "account",    label: "계정/로그인" },
  { id: "bug_report", label: "오탐지 신고" },
  { id: "illegal",    label: "불법/위반" },
  { id: "other",      label: "기타" },
];

export default function AdminReports() {
  useDocumentTitle("문의 내역 관리 · Garim Admin");

  // 상태 관리
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const size = 10;
  
  // 뷰 모드: "list" 또는 "detail"
  const [viewMode, setViewMode] = useState("list");
  
  // 데이터 상태
  const [reports, setReports] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  
  // 상세 데이터 상태
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 첨부파일 미리보기 상태
  const [selectedMediaUrl, setSelectedMediaUrl] = useState(null);
  const [selectedMediaIsVideo, setSelectedMediaIsVideo] = useState(false);
  const [selectedJsonContent, setSelectedJsonContent] = useState(null);

  // JSON 검색 상태
  const [jsonSearchTerm, setJsonSearchTerm] = useState("");
  const [jsonSearchIndex, setJsonSearchIndex] = useState(0);

  // 리스트 로딩
  const fetchReports = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminReports(activeTab, page, size);
      if (res.success) {
        setReports(res.items || []);
        setTotal(res.total || 0);
        setTotalPages(res.totalPages || 1);
      }
    } catch (err) {
      console.error("Failed to fetch reports", err);
      alert("문의 내역을 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [activeTab, page, size]);

  useEffect(() => {
    if (viewMode === "list") {
      fetchReports();
    }
  }, [fetchReports, viewMode]);

  // 탭 변경
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setPage(1);
    setViewMode("list");
  };

  // 상세 보기 클릭
  const handleReportClick = async (reportId) => {
    setDetailLoading(true);
    setViewMode("detail");
    try {
      const res = await getAdminReportDetail(reportId);
      if (res.success) {
        setDetailData(res.report);
      }
    } catch (err) {
      console.error("Failed to fetch report detail", err);
      alert("문의 상세를 불러오는데 실패했습니다.");
      setViewMode("list");
    } finally {
      setDetailLoading(false);
    }
  };

  // 목록으로 돌아가기 (페이지, 탭 상태는 useState로 유지됨)
  const handleBackToList = () => {
    setViewMode("list");
    setDetailData(null);
    setSelectedMediaUrl(null);
    setSelectedMediaIsVideo(false);
    setSelectedJsonContent(null);
    setJsonSearchTerm("");
    setJsonSearchIndex(0);
  };

  // 첨부파일 클릭 핸들러
  const handleFileClick = async (e, file) => {
    e.preventDefault();
    const fullUrl = `${getApiBaseUrl()}${file.url}`;
    const isJson = file.filename.toLowerCase().endsWith('.json');
    const isVideo = file.filename.toLowerCase().endsWith('.mp4') || file.filename.toLowerCase().endsWith('.webm');
    
    if (isJson) {
      try {
        // 인증정보 포함 (admin 권한 필요) - getAdminReportDetail 등에서 사용하는 쿠키 방식이므로 별도 header 불필요
        const res = await fetch(fullUrl, {credentials: "include"});
        if (!res.ok) throw new Error("Failed to fetch JSON");
        const data = await res.json();
        setSelectedJsonContent(JSON.stringify(data, null, 2));
      } catch (err) {
        console.error(err);
        alert("JSON 데이터를 불러오는데 실패했습니다.");
      }
    } else {
      setSelectedMediaUrl(fullUrl);
      setSelectedMediaIsVideo(isVideo);
    }
  };

  // JSON 검색 핸들러
  const handleSearchChange = (e) => {
    setJsonSearchTerm(e.target.value);
    setJsonSearchIndex(0);
  };

  const getHighlightedJson = () => {
    if (!selectedJsonContent) return { elements: null, matchCount: 0 };
    if (!jsonSearchTerm) return { elements: selectedJsonContent, matchCount: 0 };
    
    // 특수문자 이스케이프
    const escapedTerm = jsonSearchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedTerm})`, 'gi');
    const parts = selectedJsonContent.split(regex);
    const matchCount = Math.floor(parts.length / 2);
    
    let matchIdx = 0;
    const elements = parts.map((part, i) => {
      if (i % 2 === 1) { // 캡처된 그룹 (매치된 문자열)
        const isCurrent = matchIdx === jsonSearchIndex;
        const el = <mark key={i} id={isCurrent ? "current-json-match" : undefined} style={{ background: isCurrent ? "#ff9800" : "#fff59d", color: "#000", borderRadius: "2px", padding: "0 2px" }}>{part}</mark>;
        matchIdx++;
        return el;
      }
      return part;
    });
    
    return { elements, matchCount };
  };

  const highlighted = getHighlightedJson();
  const matchCount = highlighted.matchCount;

  const handleNextMatch = () => {
    if (matchCount > 0) {
      setJsonSearchIndex((prev) => (prev + 1) % matchCount);
    }
  };

  const handlePrevMatch = () => {
    if (matchCount > 0) {
      setJsonSearchIndex((prev) => (prev - 1 + matchCount) % matchCount);
    }
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (e.shiftKey) {
        handlePrevMatch();
      } else {
        handleNextMatch();
      }
    }
  };

  // 현재 매치된 항목으로 자동 스크롤
  useEffect(() => {
    if (jsonSearchTerm && matchCount > 0) {
      const el = document.getElementById("current-json-match");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [jsonSearchIndex, jsonSearchTerm, matchCount]);

  // 상태 변경
  const handleStatusChange = async (newStatus) => {
    if (!detailData) return;
    try {
      const res = await updateAdminReportStatus(detailData.id, newStatus);
      if (res.success) {
        setDetailData({ ...detailData, status: newStatus });
        alert("상태가 업데이트되었습니다.");
      }
    } catch (err) {
      console.error("Failed to update status", err);
      alert("상태 업데이트에 실패했습니다.");
    }
  };

  // 문의내역 삭제
  const handleDelete = async (e, reportId) => {
    e.stopPropagation(); // 행 클릭 이벤트(상세보기) 방지
    if (!window.confirm("해당 문의내역을 삭제하시겠습니까?")) return;

    try {
      const res = await deleteAdminReport(reportId);
      if (res.success) {
        alert("성공적으로 삭제되었습니다.");
        // 리스트에서 삭제된 항목 제거
        setReports(prev => prev.filter(r => r.id !== reportId));
        setTotal(prev => prev - 1);
        if (viewMode === "detail" && detailData && detailData.id === reportId) {
          handleBackToList();
        }
      }
    } catch (err) {
      console.error("Failed to delete report", err);
      alert("삭제 중 오류가 발생했습니다.");
    }
  };

  return (
    <div className="admin-layout">
      <GarimHeader layout="admin" />
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
          <a href="/admin/reports" className="active">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>
        <main className="adm-main">
          <div className="adm-head">
            <h1>문의 내역</h1>
            <span className="meta">사용자가 남긴 신고 및 고객 문의를 처리합니다.</span>
          </div>

          <div className="arp-pad-20">
            {/* 탭 헤더 */}
            <div className="terms-tabs" style={{ marginBottom: "20px", borderBottom: "1px solid rgba(255,255,255,0.1)", display: "flex", gap: "10px" }}>
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={`btn ${activeTab === tab.id ? "active" : ""}`}
                  onClick={() => handleTabChange(tab.id)}
                  style={{
                    background: activeTab === tab.id ? "#1976d2" : "transparent",
                    color: activeTab === tab.id ? "#fff" : "rgba(255,255,255,0.6)",
                    border: "none",
                    padding: "10px 20px",
                    cursor: "pointer",
                    borderBottom: activeTab === tab.id ? "2px solid #fff" : "2px solid transparent",
                    borderRadius: "4px 4px 0 0"
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {viewMode === "list" && (
              <div className="report-list-view">
                {loading ? (
                  <div className="arp-loading">데이터를 불러오는 중입니다...</div>
                ) : reports.length === 0 ? (
                  <div className="arp-empty">해당 조건의 문의 내역이 없습니다.</div>
                ) : (
                  <>
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>유형</th>
                          <th>제목</th>
                          <th>작성자</th>
                          <th>작성일</th>
                          <th>상태</th>
                          <th>관리</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reports.map((r) => (
                          <tr key={r.id} onClick={() => handleReportClick(r.id)} className="arp-row-click">
                            <td className="arp-td-id">{r.id.substring(0,8)}</td>
                            <td>
                              <span className="mui-chip mui-chip--sm mui-chip--outlined">
                                {TABS.find(t => t.id === r.type)?.label || r.type}
                              </span>
                            </td>
                            <td>{r.title}</td>
                            <td>{r.userId ? r.userId.substring(0,8) : "비회원"}</td>
                            <td>{new Date(r.createdAt).toLocaleString()}</td>
                            <td>
                              <span className={`mui-chip mui-chip--sm ${r.status === 'completed' ? 'mui-chip--success' : r.status === 'in_progress' ? 'mui-chip--primary' : 'mui-chip--warning'}`}>
                                {r.status === 'completed' ? '완료' : r.status === 'in_progress' ? '처리중' : '대기중'}
                              </span>
                            </td>
                            <td>
                              <button
                                className="mui-btn mui-btn--sm mui-btn--outlined arp-del-btn"
                                onClick={(e) => handleDelete(e, r.id)}
                              >
                                삭제
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {/* Pagination */}
                    {totalPages > 1 && (
                      <div className="admin-pagination arp-pagination-row">
                        <button 
                          className="mui-btn mui-btn--outlined mui-btn--sm" 
                          disabled={page === 1}
                          onClick={() => setPage(p => p - 1)}
                        >
                          이전
                        </button>
                        {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                          <button
                            key={p}
                            className={`mui-btn mui-btn--sm ${page === p ? "mui-btn--contained" : "mui-btn--text"}`}
                            onClick={() => setPage(p)}
                          >
                            {p}
                          </button>
                        ))}
                        <button 
                          className="mui-btn mui-btn--outlined mui-btn--sm"
                          disabled={page === totalPages}
                          onClick={() => setPage(p => p + 1)}
                        >
                          다음
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {viewMode === "detail" && (
              <div className="report-detail-view">
                {detailLoading || !detailData ? (
                  <div className="arp-loading">상세 정보를 불러오는 중입니다...</div>
                ) : (
                  <div className="report-detail-content">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "20px", paddingBottom: "15px", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                      <div>
                        <div className="arp-mb-8">
                          <span className="mui-chip mui-chip--sm mui-chip--outlined arp-chip-mr">
                            {TABS.find(t => t.id === detailData.type)?.label || detailData.type}
                          </span>
                          <span className="arp-meta-date">
                            {new Date(detailData.createdAt).toLocaleString()}
                          </span>
                        </div>
                        <h2 className="arp-detail-title">{detailData.title}</h2>
                        <div className="arp-author">
                          작성자: {detailData.userId || "비회원"}
                        </div>
                      </div>
                      <button className="mui-btn mui-btn--outlined" onClick={handleBackToList}>
                        목록으로
                      </button>
                    </div>

                    <div style={{ 
                      background: "rgba(0,0,0,0.2)", 
                      padding: "20px", 
                      borderRadius: "8px", 
                      minHeight: "150px", 
                      marginBottom: "30px",
                      whiteSpace: "pre-wrap",
                      lineHeight: "1.6"
                    }}>
                      {detailData.description}
                    </div>

                    {/* 오탐지 신고 관련 파일 첨부 */}
                    {detailData.targetJobId && detailData.files && detailData.files.length > 0 && (
                      <div className="arp-mb-30">
                        <h3 className="arp-attach-title">첨부 파일 (관련 작업 ID: {detailData.targetJobId.substring(0,8)})</h3>
                        <div className="arp-attach-list">
                          {[...detailData.files].sort((a, b) => {
                            const aIsJson = a.filename.toLowerCase().endsWith('.json');
                            const bIsJson = b.filename.toLowerCase().endsWith('.json');
                            if (aIsJson && !bIsJson) return 1;
                            if (!aIsJson && bIsJson) return -1;
                            return 0;
                          }).map((file, idx) => (
                            <button 
                              key={idx} 
                              onClick={(e) => handleFileClick(e, file)}
                              className="mui-btn mui-btn--outlined mui-btn--sm"
                              className="mui-btn mui-btn--outlined mui-btn--sm arp-attach-btn"
                            >
                              <span className="material-icons arp-ico-18">
                                {file.filename.toLowerCase().endsWith('.json') ? 'data_object' : 'image'}
                              </span>
                              {file.filename}
                            </button>
                          ))}
                        </div>
                        <p className="arp-attach-note">
                          * 위 파일들은 신고 접수 시점에 안전하게 복사되어 보존된 원본(상세보기) 및 결과 데이터입니다.
                        </p>
                      </div>
                    )}

                    {/* 상태 처리 */}
                    <div style={{ 
                      padding: "20px", 
                      background: "rgba(25, 118, 210, 0.1)", 
                      border: "1px solid rgba(25, 118, 210, 0.3)",
                      borderRadius: "8px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between"
                    }}>
                      <div>
                        <span className="arp-status-label">처리 상태 관리</span>
                        <div className="arp-status-btns">
                          {['received', 'in_progress', 'completed'].map(status => (
                            <button
                              key={status}
                              onClick={() => handleStatusChange(status)}
                              className={`mui-btn mui-btn--sm ${detailData.status === status ? 'mui-btn--contained' : 'mui-btn--outlined'}`}
                            >
                              {status === 'received' ? '대기중' : status === 'in_progress' ? '처리중' : '처리완료'}
                            </button>
                          ))}
                        </div>
                      </div>
                      <button
                        className="mui-btn mui-btn--sm mui-btn--outlined arp-del-btn"
                        onClick={(e) => handleDelete(e, detailData.id)}
                      >
                        삭제
                      </button>
                    </div>

                    {/* 첨부파일 미리보기 영역 */}
                    {(selectedMediaUrl || selectedJsonContent) && (
                      <div style={{ 
                        marginTop: "20px", 
                        display: "flex", 
                        gap: "20px", 
                        height: "500px" 
                      }}>
                        {/* 미디어 미리보기 (빨간 박스 영역) */}
                        <div style={{ 
                          flex: 1, 
                          border: "2px solid #ef5350", 
                          borderRadius: "8px", 
                          background: "#000",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          overflow: "hidden"
                        }}>
                          {!selectedMediaUrl ? (
                            <span className="arp-media-empty">이미지/영상을 선택하세요</span>
                          ) : selectedMediaIsVideo ? (
                            <video src={selectedMediaUrl} controls autoPlay muted className="arp-media" />
                          ) : (
                            <img src={selectedMediaUrl} alt="preview" className="arp-media" />
                          )}
                        </div>

                        {/* JSON 코드 뷰어 (파란 박스 영역) */}
                        <div style={{ 
                          flex: 1, 
                          border: "2px solid #29b6f6", 
                          borderRadius: "8px", 
                          background: "#1e1e1e",
                          overflow: "hidden",
                          display: "flex",
                          flexDirection: "column",
                          position: "relative"
                        }}>
                          {!selectedJsonContent ? (
                            <div className="arp-json-empty">
                              JSON 파일을 선택하세요
                            </div>
                          ) : (
                            <>
                              {/* 찾기 (Ctrl+F 기능) 헤더 */}
                              <div style={{
                                padding: "8px 12px",
                                background: "#252526",
                                borderBottom: "1px solid #333",
                                display: "flex",
                                alignItems: "center",
                                gap: "10px"
                              }}>
                                <input
                                  type="text"
                                  placeholder="JSON 내에서 찾기... (Enter로 다음)"
                                  value={jsonSearchTerm}
                                  onChange={handleSearchChange}
                                  onKeyDown={handleSearchKeyDown}
                                  style={{
                                    background: "#3c3c3c",
                                    border: "1px solid #007fd4",
                                    color: "#ccc",
                                    padding: "4px 8px",
                                    borderRadius: "2px",
                                    outline: "none",
                                    fontSize: "13px",
                                    flex: 1
                                  }}
                                />
                                {jsonSearchTerm && (
                                  <span className="arp-match-count">
                                    {matchCount > 0 ? `${jsonSearchIndex + 1} / ${matchCount}` : "0 / 0"}
                                  </span>
                                )}
                                <button
                                  onClick={handlePrevMatch}
                                  className="arp-nav-btn"
                                  title="이전 (Shift+Enter)"
                                >
                                  <span className="material-icons arp-ico-16">keyboard_arrow_up</span>
                                </button>
                                <button
                                  onClick={handleNextMatch}
                                  className="arp-nav-btn"
                                  title="다음 (Enter)"
                                >
                                  <span className="material-icons arp-ico-16">keyboard_arrow_down</span>
                                </button>
                              </div>

                              <pre style={{ 
                                margin: 0, 
                                padding: "16px", 
                                color: "#d4d4d4", 
                                fontSize: "13px", 
                                lineHeight: "1.5",
                                fontFamily: "monospace",
                                overflow: "auto",
                                flex: 1
                              }}>
                                {jsonSearchTerm ? highlighted.elements : selectedJsonContent}
                              </pre>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
