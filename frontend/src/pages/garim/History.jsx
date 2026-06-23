import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getHistoryList, getDownloadUrl, deleteAnalysisJob, getApiBaseUrl } from "../../utils/api";
import "../../css/garim-pages/History.css";

import GarimPage from "../../components/garim/GarimPage";

function formatBytes(bytes, decimals = 1) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

export default function History() {
  useDocumentTitle("처리 이력 · Garim");
  const navigate = useNavigate();

  const [historyData, setHistoryData] = useState({ items: [], total: 0, page: 1, size: 10 });
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState("desc"); // 'desc' | 'asc'

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await getHistoryList(currentPage, 10, searchQuery, sortOrder);
      setHistoryData(data);
    } catch (e) {
      console.error("History data load failed:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentPage, searchQuery, sortOrder]);

  const totalPages = Math.max(1, Math.ceil((historyData.total || 0) / 10));

  async function handleDelete(jobId) {
    if (!jobId) return;
    if (!window.confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deleteAnalysisJob(jobId);
      await loadData();
    } catch (e) {
      alert("삭제 중 오류가 발생했습니다: " + e.message);
    }
  }

  async function handleDeleteAll() {
    if (!historyData.items || historyData.items.length === 0) return;
    if (!window.confirm(`${currentPage}페이지 목록 전체 삭제하시겠습니까?`)) return;
    
    try {
      await Promise.all(
        historyData.items.map(job => job.job_id ? deleteAnalysisJob(job.job_id) : Promise.resolve())
      );
      await loadData();
    } catch (e) {
      alert("전체 삭제 중 일부 오류가 발생했습니다: " + e.message);
      await loadData();
    }
  }

  return (
    <GarimPage bodyClass="page-app" screenLabel="20 History">
      <div className="hist-page">
        <div className="hist-head">
          <h1>처리 이력</h1>
          <span className="caption-k">총 {historyData.total}건</span>
          <div className="hist-nav-btns">
            <button onClick={() => navigate("/dashboard")} className="mui-btn mui-btn--outlined">
              <span className="material-icons hist-ico-sm">arrow_back</span>
              대시보드
            </button>
            <Link to="/upload" className="mui-btn mui-btn--contained">
              <span className="material-icons hist-ico-sm">add</span>
              새 검출
            </Link>
          </div>
        </div>
        
        <div className="hist-toolbar">
          <div className="search-mini">
            <span className="material-icons">search</span>
            <input 
              placeholder="파일명, 날짜로 검색(예시:우편물3, 26.6.12, 26/6/12)" 
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setSearchQuery(searchInput);
                  setCurrentPage(1);
                }
              }}
            />
          </div>
          <div className="filter-bar">
            {/* 전체 N건 칩 삭제됨 */}
          </div>
          <div className="hist-toolbar-right">
            <button 
              className="mui-btn mui-btn--outlined mui-btn--sm"
              onClick={() => {
                setSortOrder(prev => prev === "desc" ? "asc" : "desc");
                setCurrentPage(1);
              }}
            >
              정렬: {sortOrder === "desc" ? "최신순 ↓" : "오래된순 ↑"}
            </button>
            {historyData.items.length > 0 && (
              <button 
                className="mui-btn mui-btn--outlined mui-btn--sm hist-del-all"
                onClick={handleDeleteAll}
              >
                전체 삭제
              </button>
            )}
          </div>
        </div>

        <div className="hist-list" style={{ opacity: loading ? 0.6 : 1, transition: "opacity 0.2s ease-in-out" }}>
          <div className="hist-row head">
            <span></span>
            <span>파일</span>
            <span>처리 일시</span>
            <span className="hist-col-pad">만료 일시</span>
            <span>처리/검출</span>
            <span>상태</span>
            <span>액션</span>
          </div>

          {loading && historyData.items.length === 0 ? (
            <div className="hist-empty">
              데이터를 불러오는 중...
            </div>
          ) : historyData.items.length === 0 ? (
            <div className="hist-empty">
              처리 이력이 없습니다.
            </div>
          ) : (
            historyData.items.map((job) => {
              const isVideo = job.media_type === "video";
              const isAudio = job.media_type === "audio";
              const isImage = job.media_type === "image";
              const iconName = isVideo ? "movie" : isAudio ? "graphic_eq" : "image";
              const dateObj = job.created_at ? new Date(job.created_at) : new Date();

              return (
                <div className="hist-row" key={job.job_id}>
                  <div className="thumb hist-thumb">
                    {job.thumbnail_url ? (
                      <img src={`${getApiBaseUrl()}${job.thumbnail_url}`} alt="thumbnail" />
                    ) : (
                      <span className="material-icons hist-thumb-ico">{iconName}</span>
                    )}
                  </div>
                  <div>
                    <div className="name">{job.filename}</div>
                    <div className="sub">
                      {job.media_type?.toUpperCase()} · {formatBytes(job.file_size)}
                    </div>
                  </div>
                  <div className="date">
                    {dateObj.toLocaleDateString()}
                    <br />
                    <span className="caption-k hist-cap-time">
                      {dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="date hist-col-pad">
                    {(() => {
                      const expireDate = job.expires_at ? new Date(job.expires_at) : new Date(dateObj.getTime() + 7 * 24 * 60 * 60 * 1000);
                      return (
                        <>
                          <span className="hist-expire-date">{expireDate.toLocaleDateString()}</span>
                          <br />
                          <span className="caption-k hist-expire-time">
                            {expireDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </>
                      );
                    })()}
                  </div>
                  <div className="detected">
                    {job.replaced}
                    <small> / {job.detected}</small>
                  </div>
                  <div className="hist-status-cell">
                    {job.status === "completed" ? (
                      job.detected > 0 && job.replaced < job.detected ? (
                        <span className="mui-chip mui-chip--soft-warning hist-chip-partial">
                          일부완료
                        </span>
                      ) : (
                        <span className="mui-chip mui-chip--soft-success">완료</span>
                      )
                    ) : (
                      <span className={`mui-chip ${job.status === "failed" ? "mui-chip--soft-error" : "mui-chip--soft-info"}`}>
                        {job.status === "failed" ? "실패" : `진행 중 · ${job.progress}%`}
                      </span>
                    )}
                  </div>
                  <div className="actions-group">
                    {job.status === "completed" ? (
                      <>
                        <a href={getDownloadUrl(job.job_id)} title="다운로드" className="mui-btn mui-btn--text mui-btn--sm btn-download-green hist-act-icon-btn">
                          <span className="material-icons hist-ico-sm">download</span>
                        </a>
                        <Link to="/replace-options" state={{ jobId: job.job_id, fromDashboard: true }} className="mui-btn mui-btn--outlined mui-btn--sm hist-act-detail">
                          상세
                        </Link>
                      </>
                    ) : (
                      <Link to={job.job_type === "analysis" || job.job_type === "stt_analysis" ? "/analysis-progress" : "/replace-options"} state={{ jobId: job.job_id }} title="상세 보기" className="mui-btn mui-btn--text mui-btn--sm hist-act-icon-btn">
                        <span className="material-icons hist-ico-md">arrow_forward</span>
                      </Link>
                    )}
                    <button 
                      className="delete-btn" 
                      title="삭제"
                      onClick={() => handleDelete(job.job_id)}
                      disabled={!job.job_id}
                    >
                      <span className="material-icons hist-ico-sm">delete</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {!loading && totalPages > 1 && (
          <div className="pagination">
            <button 
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              ‹
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
              <button 
                key={pageNum}
                className={currentPage === pageNum ? "active" : ""}
                onClick={() => setCurrentPage(pageNum)}
              >
                {pageNum}
              </button>
            ))}
            <button 
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
            >
              ›
            </button>
          </div>
        )}
      </div>
    </GarimPage>
  );
}
