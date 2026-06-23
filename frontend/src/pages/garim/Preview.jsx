import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getAnalysisJob, getDetailFileUrl, getDownloadUrl, resetSelections, triggerMaskPreview, deleteMaskPreview, deleteMaskPreviewKeepalive, triggerMaskFinal } from "../../utils/api";
import "../../css/garim-pages/Preview.css";

import GarimPage from "../../components/garim/GarimPage";
import ComparisonSlider from "../../components/garim/ComparisonSlider";

// 처리 중인 상태값 집합
const ACTIVE = new Set(["queued", "processing", "retrying"]);

export default function Preview() {
  useDocumentTitle("마스킹 미리보기 · Garim");

  const location = useLocation();
  const navigate = useNavigate();

  // 상세 페이지에서 전달받은 state
  const {
    jobId,
    fileType = "image",     // "image" | "video"
    pii_id: piiId,        // 영상 개별 PII 미리보기 시 필요
    clip_start: clipStart,  // 영상 클립 시작 시각(초)
    clip_end: clipEnd,    // 영상 클립 종료 시각(초)
  } = location.state || {};

  const [phase, setPhase] = useState("polling");  // polling | done | error
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    if (jobId) {
      localStorage.setItem(`job_stage_${jobId}`, "/preview");
    }
  }, [jobId]);

  // 가림바에 넘길 두 URL
  const [originalUrl, setOriginalUrl] = useState(null);
  const [maskedUrl, setMaskedUrl] = useState(null);

  const pollRef = useRef(null);

  // ── 마스킹 미리보기 job 생성 + 폴링 ──────────────────────────────
  useEffect(() => {
    if (!jobId) {
      setTimeout(() => {
        setError("jobId가 없습니다. 상세 페이지로 돌아가 다시 시도해주세요.");
        setPhase("error");
      }, 0);
      return;
    }

    const mId = location.state?.maskJobId;

    const startPolling = (targetMaskJobId) => {
      const poll = () => {
        getAnalysisJob(targetMaskJobId)
          .then((job) => {
            setProgress(job.total_progress || 0);

            if (ACTIVE.has(job.status)) {
              pollRef.current = setTimeout(poll, 2500);
            } else if (job.status === "completed") {
              // 원본: detail-file API (영상+pii_id 시 마스킹 클립과 동일한 6초 구간 클립으로 서빙)
              // 마스킹: download API (processed_files에 등록된 결과 파일)
              const origPiiId = fileType === "video" ? piiId : null;
              setOriginalUrl(getDetailFileUrl(jobId, fileType, origPiiId));
              setMaskedUrl(getDownloadUrl(targetMaskJobId));
              setPhase("done");
            } else {
              setError(`미리보기 생성 실패: 상태=${job.status}`);
              setPhase("error");
            }
          })
          .catch((e) => {
            setError(String(e));
            setPhase("error");
          });
      };
      poll();
    };

    if (mId) {
      startPolling(mId);
    } else {
      // 영상 개별 PII 클립 미리보기 시 body에 pii_id, clip_start, clip_end 전달
      const previewBody = (fileType === "video" && piiId)
        ? { pii_id: piiId, clip_start: clipStart, clip_end: clipEnd }
        : {};

      triggerMaskPreview(jobId, previewBody)
        .then((data) => {
          navigate(".", { replace: true, state: { ...location.state, maskJobId: data.mask_job_id } });
          startPolling(data.mask_job_id);
        })
        .catch((e) => {
          setError(String(e));
          setPhase("error");
        });
    }

    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [jobId]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── 브라우저 뒤로가기, 탭 닫기, 페이지 이탈 시 자동 삭제 ──
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (jobId) {
        deleteMaskPreviewKeepalive(jobId);
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      if (jobId) {
        deleteMaskPreview(jobId).catch(() => { });
      }
    };
  }, [jobId]);

  // ── 처리진행 버튼 (이미지만) ────────────────────────────────────
  const goResult = async () => {
    if (jobId) {
      try {
        await deleteMaskPreview(jobId);
      } catch (_) {
        // 무시
      }
      try {
        const data = await triggerMaskFinal(jobId);
        navigate("/result", { state: { jobId, fileType, maskJobId: data.mask_job_id } });
      } catch (e) {
        alert("마스킹 작업 시작에 실패했습니다: " + e.message);
      }
    }
  };

  // ── 뒤로가기 — is_user_selected 전체 리셋 후 이전 페이지로 이동 ──
  const handleGoBack = async () => {
    if (jobId) {
      try {
        await deleteMaskPreview(jobId);
      } catch (_) {
        // 무시
      }
      try {
        await resetSelections(jobId);
      } catch (_) {
        // 리셋 실패해도 뒤로가기는 진행
      }
    }
    navigate("/replace-options", { state: { jobId, fileType } });
  };


  // ── 렌더링 ──────────────────────────────────────────────────────
  return (
    <GarimPage bodyClass="page-app" screenLabel="Preview">
      <div className="pv-page">

        {/* ── 상단 툴바 ── */}
        <div className="pv-toolbar">
          <button
            className="gh__icon pv-back-btn"
            onClick={handleGoBack}
          >
            <span className="material-icons">arrow_back</span>
          </button>
          <h1>
            {fileType === "video" ? "마스킹 미리보기 (6초 클립)" : "마스킹 미리보기"}
          </h1>

          {/* 상태 뱃지 */}
          {phase === "polling" && (
            <span className="mui-chip mui-chip--soft-warning mui-chip--md">
              미리보기 생성 중…
            </span>
          )}
          {phase === "done" && (
            <span className="mui-chip mui-chip--soft-success mui-chip--md">
              {fileType === "video" ? "클립 준비 완료" : "미리보기 준비 완료"}
            </span>
          )}
        </div>

        {/* ── 본문: 가림바 슬라이더 영역 ── */}
        <div className="pv-grid">
          <div className="pv-left">

            {/* 에러 */}
            {phase === "error" && (
              <div className="pv-error-box">
                <span className="material-icons pv-error-icon">error_outline</span>
                <p className="pv-error-text">{error}</p>
              </div>
            )}

            {/* 로딩 애니메이션 */}
            {phase === "polling" && (
              <div className="pv-loading">
                <div className="masking-anim-wrap">
                  <div className="masking-anim">
                    <div className="doc-line"></div>
                    <div className="doc-line"></div>
                    <div className="doc-line short"></div>
                    <div className="scanner"></div>
                  </div>
                </div>
                <div className="pv-loading-text">
                  <h3>개인정보 마스킹 미리보기 생성 중...</h3>
                  <p>안전하게 개인정보를 가리고 있습니다</p>
                </div>
                <div className="pv-progress-bar-container">
                  <div className="pv-progress-bar" style={{ width: `${progress}%` }}></div>
                </div>
                <div className="pv-progress-text">{progress}% 완료</div>
              </div>
            )}

            {/* 가림바 비교 슬라이더 */}
            {phase === "done" && (
              <>
                <ComparisonSlider
                  mode={fileType}
                  originalSrc={originalUrl}
                  maskedSrc={maskedUrl}
                />
                <div className="pv-mode">
                  ← 가림바를 드래그하여 원본과 마스킹 결과를 비교하세요 →
                </div>
              </>
            )}
          </div>

          {/* ── 우측 패널 ── */}
          <aside className="pv-right">
            <div className="head">
              <h2>미리보기 확인</h2>
              <div className="sub">
                {phase === "polling"
                  ? "미리보기 생성이 완료되면 가림바로 원본과 비교할 수 있습니다."
                  : "가림바를 좌우로 드래그하여 원본과 마스킹 결과를 비교하세요."}
              </div>
            </div>

            <div className="wmk-note pv-wmk-note">
              <div className="watermark-note">
                <strong>워터마크 안내</strong><br />
                미리보기는 검토용으로 워터마크가 표시됩니다.
                최종 결과물(다운로드)에는 워터마크가 보이지 않습니다.
              </div>
            </div>

            {/* 영상 미리보기: 안내 문구 */}
            {fileType === "video" && (
              <div className="pv-info-box">
                <strong className="pv-info-title">영상 미리보기 안내</strong><br />
                선택한 개인정보(PII) 구간의 6초 클립을 미리보기로 제공합니다.<br />
                처리 진행은 상세 페이지의 "처리진행" 버튼을 이용하세요.
              </div>
            )}

            <div className="pv-bottom-bar">
              <span className="info pv-bottom-info">
                {phase === "polling" && "미리보기 생성 중…"}
                {phase === "error" && "미리보기 생성에 실패했습니다."}
              </span>
              <button
                className="mui-btn mui-btn--outlined"
                onClick={handleGoBack}
              >
                ← 뒤로가기
              </button>
            </div>

            {/* 이미지만: 처리진행 버튼 (영상은 상세 페이지에서 처리진행) */}
            {fileType === "image" && (
              <div className="pv-action-btn-wrap">
                <button
                  className={`mui-btn mui-btn--contained mui-btn--lg pv-action-btn${phase !== "done" ? " disabled" : ""}`}
                  onClick={goResult}
                  disabled={phase !== "done"}
                >
                  <span className="material-icons pv-play-icon">play_arrow</span>
                  처리 진행
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    </GarimPage>
  );
}
