import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { cancelAnalysisJob, getAnalysisJob, deleteAnalysisUpload, getApiBaseUrl } from "../../utils/api";
import { useNavigate } from "react-router-dom";
import "../../css/garim-pages/AnalysisProgress.css";

import GarimPage from "../../components/garim/GarimPage";

const POLL_INTERVAL_MS = 1000;
const ACTIVE_STATUSES = new Set(["queued", "processing", "retrying", "cancelling"]);

const STAGES = [
  { key: "upload_completed", label: "업로드 완료", detail: "원본 파일 병합과 무결성 확인 완료" },
  { key: "queued", label: "대기열 등록", detail: "분석 작업이 처리 순서를 기다리는 중" },
  { key: "visual_detection", label: "시각 탐지", detail: "얼굴, 번호판, 주소 등 프레임 기반 개인정보 탐지" },
  { key: "audio_detection", label: "음성 탐지", detail: "STT와 텍스트 분석 기반 개인정보 탐지" },
  { key: "report_generation", label: "리포트 생성", detail: "탐지 결과 통합 및 위험도 산출" },
  { key: "completed", label: "완료", detail: "결과 확인 준비 완료" },
];

function formatBytes(size) {
  if (!size) return "";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  return `${(size / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return "계산 중";
  if (seconds <= 0) return "곧 완료";
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return min > 0 ? `${min}분 ${sec}초` : `${sec}초`;
}

function clampPercent(value) {
  const n = Number(value || 0);
  return Math.max(0, Math.min(100, Math.round(n)));
}

function statusLabel(status) {
  const labels = {
    queued: "대기 중",
    processing: "분석 중",
    retrying: "재시도 중",
    completed: "완료",
    failed: "실패",
    cancelling: "취소 요청됨",
    cancelled: "취소됨",
  };
  return labels[status] || "상태 확인 중";
}

// 최근 로그 패널에 표시할 stage_name 한국어 레이블
const STAGE_NAME_KO = {
  upload_completed: "업로드 완료",
  queued:           "대기열 등록",
  ocr:              "텍스트 탐지 중",
  ocr_done:         "텍스트 탐지 완료",
  stt_wait:         "음성 분석 대기",
  audio_extract:    "음성 추출 중",
  stt:              "음성-텍스트 변환",
  pii_detect:       "개인정보 탐지",
  merge:            "결과 통합",
  detail_view:      "상세 분석",
  register:         "결과 등록",
  completed:        "완료",
};

function stageNameKo(name) {
  return STAGE_NAME_KO[name] || name;
}

function stageIndex(currentStage, status) {
  if (status === "completed") return STAGES.length - 1;

  // 백엔드의 세부 진행 단계(stage_name)를 프론트엔드의 큰 5단계(STAGES)에 매핑
  const stageMap = {
    "upload_completed": "upload_completed",
    "queued": "queued",
    "ocr": "visual_detection",
    "ocr_done": "visual_detection",
    "stt_wait": "audio_detection",
    "audio_extract": "audio_detection",
    "stt": "audio_detection",
    "pii_detect": "audio_detection",
    "merge": "report_generation",
    "detail_view": "report_generation",
    "register": "report_generation",
    "completed": "completed"
  };
  
  const mappedKey = stageMap[currentStage] || currentStage;
  const index = STAGES.findIndex((stage) => stage.key === mappedKey);
  return index >= 0 ? index : 1; // 기본값은 대기열 등록(index 1)
}

export default function AnalysisProgress() {
  useDocumentTitle("분석 진행 - Garim");
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialState = location.state || {};
  const jobId = initialState.jobId || searchParams.get("jobId");

  const [job, setJob] = useState(null);
  const [error, setError] = useState(jobId ? "" : "분석 작업 ID가 없습니다.");
  const [loading, setLoading] = useState(Boolean(jobId));
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    if (jobId) {
      localStorage.setItem(`job_stage_${jobId}`, "/analysis-progress");
    }
  }, [jobId]);

  const jobStatus = job?.status;
  const isActive = job ? ACTIVE_STATUSES.has(jobStatus) : Boolean(jobId);
  const totalProgress = clampPercent(job?.total_progress);
  const currentStageIndex = stageIndex(job?.current_stage, job?.status);
  
  const [localEta, setLocalEta] = useState(null);
  const [nowTick, setNowTick] = useState(Date.now());

  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (jobStatus === "completed") {
      setLocalEta(0);
      return;
    }
    if (job?.eta_seconds !== undefined && job.eta_seconds !== null) {
      setLocalEta({
        base: job.eta_seconds,
        updatedAt: Date.now()
      });
    } else {
      setLocalEta(null);
    }
  }, [job?.eta_seconds, job?.total_progress, jobStatus]);

  const displayEta = useMemo(() => {
    if (localEta === 0) return 0;
    if (!localEta) return null;
    const elapsedSec = Math.floor((nowTick - localEta.updatedAt) / 1000);
    return Math.max(0, localEta.base - elapsedSec);
  }, [localEta, nowTick]);

  const fileMeta = useMemo(() => {
    const parts = [];
    const name = initialState.fileName || job?.filename;
    const size = initialState.fileSize || job?.file_size;
    const type = initialState.contentType || (job?.media_type ? `${job.media_type}/unknown` : undefined);
    
    if (name) parts.push(name);
    if (size) parts.push(formatBytes(size));
    if (type) parts.push(type.split("/")[0].toUpperCase());
    return parts.join(" · ");
  }, [initialState.contentType, initialState.fileName, initialState.fileSize, job?.filename, job?.file_size, job?.media_type]);

  useEffect(() => {
    if (!jobId) return undefined;

    let cancelled = false;
    const shouldPoll = !jobStatus || ACTIVE_STATUSES.has(jobStatus);

    async function loadJob() {
      try {
        const nextJob = await getAnalysisJob(jobId);
        if (!cancelled) {
          setJob(nextJob);
          setError("");
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      }
    }

    loadJob();
    if (!shouldPoll) {
      return () => {
        cancelled = true;
      };
    }

    const timer = window.setInterval(() => {
      if (!cancelled) loadJob();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobId, jobStatus]);

  async function handleCancel() {
    if (canceling || !job || !ACTIVE_STATUSES.has(job.status)) return;
    
    // Use upload_id to delete the whole upload if available
    const targetUploadId = job.upload_id;
    if (!targetUploadId && !jobId) return;

    const filename = initialState.fileName || job?.filename || "진행 중인";
    if (!window.confirm(`${filename} 작업을 취소하시겠습니까?`)) return;

    setCanceling(true);
    try {
      if (targetUploadId) {
        await deleteAnalysisUpload(targetUploadId);
      } else {
        await cancelAnalysisJob(jobId);
      }
      setError("");
      navigate("/upload"); // Navigate to upload page
    } catch (err) {
      setError(err.message);
      setCanceling(false);
    }
  }

  const heading =
    error && !job ? "분석 상태를 불러올 수 없습니다" :
    loading ? "분석 상태 확인 중" :
    job?.status === "completed" ? "분석이 완료되었습니다" :
    job?.status === "failed" ? "분석에 실패했습니다" :
    job?.status === "cancelled" ? "분석이 취소되었습니다" :
    "분석이 진행 중입니다";

  const statusMessage = job?.message || (loading ? "서버에서 최신 진행률을 가져오고 있습니다." : error);

  return (
    <GarimPage bodyClass="page-app" screenLabel="09 Analysis progress">
      <div className="ana-page">
        <div className="ana-grid">
          <div className="ana-main">
            <div className="ana-head">
              <div className="thumb ap-thumb">
                {initialState.thumbnailUrl ? (
                  initialState.contentType?.startsWith("video/") ? (
                    <video src={`${initialState.thumbnailUrl}#t=0.1`} preload="metadata" className="ap-thumb-media" />
                  ) : (
                    <img src={initialState.thumbnailUrl} alt="thumbnail" className="ap-thumb-media" />
                  )
                ) : job?.thumbnail_url ? (
                  <img src={`${getApiBaseUrl()}${job.thumbnail_url}`} alt="thumbnail" className="ap-thumb-media" />
                ) : (
                  <span className="material-icons ap-thumb-ico">manage_search</span>
                )}
                {isActive && <div className="pulse ap-pulse" />}
              </div>
              <div className="ap-job-info">
                <h1>{heading}</h1>
                <div className="meta">
                  {fileMeta || `Job ${jobId || "unknown"}`}
                </div>
                <div className="ap-tag-row">
                  <span className="mui-chip mui-chip--soft-info">{statusLabel(job?.status)}</span>
                  <span className="mui-chip mui-chip--soft-info">{job?.job_type || "analysis"}</span>
                  {job?.current_stage && (
                    <span className="mui-chip mui-chip--soft-info">{stageNameKo(job.current_stage)}</span>
                  )}
                </div>
              </div>
            </div>

            {error && (
              <div className="mui-alert mui-alert--error ap-alert-mb">
                <span className="material-icons">error</span>
                <div className="mui-alert__body">{error}</div>
              </div>
            )}

            <div className="stepper-wrap">
              {(() => {
                const stageStatus = STAGES.map((stage, index) => {
                  let done = false;
                  let active = false;
                  let progressValue = 0;
                  let stepMessage = stage.detail;

                  const isImage = !(initialState.contentType?.startsWith("video/") || job?.media_type === "video");

                  if (stage.key === "visual_detection") {
                    done = currentStageIndex > index || job?.status === "completed";
                    active = currentStageIndex === index && !["failed", "cancelled", "completed"].includes(job?.status);
                    if (active) {
                      progressValue = clampPercent(job?.stage_progress);
                      stepMessage = statusMessage || stage.detail;
                    } else if (done) stepMessage = "시각 탐지 완료";
                  } else if (stage.key === "audio_detection") {
                    if (isImage) {
                      done = currentStageIndex >= index || job?.status === "completed";
                      active = false;
                      progressValue = 100;
                      stepMessage = "이미지 (음성 없음)";
                    } else if (job?.stt_job) {
                      done = job.stt_job.status === "completed" || currentStageIndex > index || job?.status === "completed";
                      active = job.stt_job.status === "processing" || (currentStageIndex === index && !done);
                      if (active) {
                        progressValue = clampPercent(job.stt_job.total_progress);
                        stepMessage = "음성 분석 중... " + progressValue + "%";
                      } else if (done) stepMessage = "음성 탐지 완료";
                    } else {
                      done = currentStageIndex > index || job?.status === "completed";
                      active = currentStageIndex === index && !["failed", "cancelled", "completed"].includes(job?.status);
                      if (active) {
                        progressValue = clampPercent(job?.stage_progress);
                        stepMessage = statusMessage || stage.detail;
                      } else if (done) stepMessage = "음성 탐지 완료";
                    }
                  } else {
                    // For upload_completed, queued, report_generation, and completed
                    done = currentStageIndex > index || job?.status === "completed";
                    active = currentStageIndex === index && !["failed", "cancelled", "completed"].includes(job?.status);
                    if (active) {
                      progressValue = clampPercent(job?.stage_progress);
                      stepMessage = statusMessage || stage.detail;
                    } else if (done) {
                      stepMessage = "완료";
                    }
                  }
                  
                  return { ...stage, done, active, progressValue, stepMessage };
                });

                const STAGE_ICONS = {
                  upload_completed: "cloud_done",
                  queued: "hourglass_empty",
                  visual_detection: "visibility",
                  audio_detection: "graphic_eq",
                  report_generation: "analytics",
                  completed: "check_circle"
                };

                const renderFlowNode = (st) => {
                  const cn = `fc-node ${st.active ? 'active' : ''} ${st.done ? 'done' : ''}`;
                  return (
                    <div className={cn} key={st.key}>
                      <div className="fc-node-content-row">
                        <div className="fc-node-icon">
                          <span className="material-icons">{STAGE_ICONS[st.key] || "lens"}</span>
                        </div>
                        <div className="fc-node-text-wrap">
                          <div className="fc-node-title">{st.label}</div>
                          <div className="fc-node-sub">{st.stepMessage}</div>
                        </div>
                      </div>
                      {st.active && (
                        <div className="fc-node-progress">
                          <div className="fc-node-progress-bar" style={{ width: `${st.progressValue}%` }} />
                        </div>
                      )}
                    </div>
                  );
                };
                
                const lineState = (targetSt) => targetSt.done ? 'done' : targetSt.active ? 'active' : '';

                return (
                  <div className="flow-chart">
                    {renderFlowNode(stageStatus[0])}
                    <div className={`fc-v-line ${lineState(stageStatus[1])}`} />
                    
                    {renderFlowNode(stageStatus[1])}

                    <div className="fc-split-container">
                      <div className={`fc-v-line ${lineState(stageStatus[2]) || lineState(stageStatus[3])}`} />
                      <div className="fc-h-bar split-bar">
                        <div className={`fc-h-half left ${lineState(stageStatus[2])}`} />
                        <div className={`fc-h-half right ${lineState(stageStatus[3])}`} />
                      </div>
                    </div>

                    <div className="fc-columns">
                      <div className="fc-col">
                        <div className={`fc-v-line ${lineState(stageStatus[2])}`} />
                        {renderFlowNode(stageStatus[2])}
                        <div className={`fc-v-line ${stageStatus[4].active ? 'active' : stageStatus[4].done ? 'done' : ''}`} />
                      </div>
                      <div className="fc-col">
                        <div className={`fc-v-line ${lineState(stageStatus[3])}`} />
                        {renderFlowNode(stageStatus[3])}
                        <div className={`fc-v-line ${stageStatus[4].active ? 'active' : stageStatus[4].done ? 'done' : ''}`} />
                      </div>
                    </div>

                    <div className="fc-split-container">
                      <div className="fc-h-bar merge-bar">
                        <div className={`fc-h-half left ${stageStatus[4].done ? 'done' : stageStatus[4].active ? 'active' : ''}`} />
                        <div className={`fc-h-half right ${stageStatus[4].done ? 'done' : stageStatus[4].active ? 'active' : ''}`} />
                      </div>
                      <div className={`fc-v-line ${lineState(stageStatus[4])}`} />
                    </div>

                    {renderFlowNode(stageStatus[4])}
                    <div className={`fc-v-line ${lineState(stageStatus[5])}`} />
                    
                    {renderFlowNode(stageStatus[5])}
                  </div>
                );
              })()}
            </div>

            <div className="progress-summary">
              <span className="caption-k ap-cap-13">전체 진행</span>
              <div className="progress">
                <div className="progress__bar" style={{ width: `${(() => {
                  if (job?.status === "completed") return 100;
                  const ocrProg = job?.total_progress || 0;
                  const sttProg = job?.stt_job ? job.stt_job.total_progress : null;
                  let combined = ocrProg;
                  if (sttProg !== null) {
                    combined = Math.round((ocrProg + sttProg) / 2);
                  }
                  return clampPercent(combined);
                })()}%` }} />
              </div>
              <span className="pct">{(() => {
                if (job?.status === "completed") return 100;
                const ocrProg = job?.total_progress || 0;
                const sttProg = job?.stt_job ? job.stt_job.total_progress : null;
                let combined = ocrProg;
                if (sttProg !== null) {
                  combined = Math.round((ocrProg + sttProg) / 2);
                }
                return clampPercent(combined);
              })()}%</span>
            </div>

            <div className="caption-k ap-eta">
              예상 남은 시간 <strong className="ap-eta-val">{formatEta(displayEta)}</strong>
              {job?.queue_position ? ` · 대기 순번 ${job.queue_position}` : ""}
            </div>

            <div className="actions">
              <Link to="/dashboard" className="mui-btn mui-btn--outlined">
                백그라운드 처리
              </Link>
              <button
                className="mui-btn mui-btn--text ap-cancel"
                type="button"
                disabled={!job || !ACTIVE_STATUSES.has(job.status) || canceling}
                onClick={handleCancel}
              >
                {canceling ? "취소 요청 중" : "취소"}
              </button>
              <div className="ap-spacer" />
              <Link
                to={job?.status === "completed" ? `/analysis-report` : "#"}
                className="mui-btn mui-btn--contained"
                style={job?.status !== "completed" ? { pointerEvents: "none", opacity: 0.4 } : {}}
                state={{ jobId }}
              >
                결과 보기
              </Link>
            </div>
          </div>

          <aside>
            <div className="sidebar-card">
              <h3>작업 위치</h3>
              <div className="info-row">
                <span className="k">상태</span>
                <span className="v">{statusLabel(job?.status)}</span>
              </div>
              <div className="info-row">
                <span className="k">대기 순번</span>
                <span className="v">{job?.queue_position ?? "-"}</span>
              </div>
              <div className="info-row">
                <span className="k">단계 진행</span>
                <span className="v">{clampPercent(job?.stage_progress)}%</span>
              </div>
              <div className="info-row">
                <span className="k">Job ID</span>
                <span className="v">{jobId || "-"}</span>
              </div>
            </div>

            <div className="sidebar-card">
              <h3>최근 로그</h3>
              <div className="models-list">
                {(job?.stage_logs || []).slice(0, 5).map((log, index) => (
                  <span className="mui-chip mui-chip--md mui-chip--outlined" key={`${log.stage_name}-${index}`}>
                    {stageNameKo(log.stage_name)} · {log.total_progress}%
                  </span>
                ))}
                {(!job?.stage_logs || job.stage_logs.length === 0) && (
                  <span className="mui-chip mui-chip--md mui-chip--outlined">로그 대기 중</span>
                )}
              </div>
            </div>

            <div className="sidebar-card ap-notice-card">
              <h3 className="ap-notice-title">알림</h3>
              <div className="ap-notice-body">
                페이지를 벗어나도 서버 작업은 계속됩니다. 완료 후 대시보드와 기록 화면에서 결과를 다시 확인할 수 있습니다.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </GarimPage>
  );
}
