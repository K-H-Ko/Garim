import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getAnalysisJob, getDownloadUrl, getResultFile, getTrimUrl } from "../../utils/api";
import "../../css/garim-pages/Preview.css";
import "../../css/garim-pages/ResultPage.css";

import GarimPage from "../../components/garim/GarimPage";

const ACTIVE = new Set(["queued", "processing", "retrying"]);

/* mm:ss 문자열 → 초(float) 변환 */
function timeToSec(str) {
  if (!str) return NaN;
  const parts = str.split(":").map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 1) return parts[0];
  return NaN;
}

/* 초 → mm:ss 문자열 */
function secToTime(sec) {
  if (!isFinite(sec)) return "?:??";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function ResultPage() {
  useDocumentTitle("처리 결과 · Garim");

  const location = useLocation();
  const { jobId, fileType = "image" } = location.state || {};
  // 상세보기 페이지의 "구간다운로드 이동" 버튼으로 진입한 경우 — 이미 처리 완료된 파일 직접 로드
  const fromCropDownload = location.state?.fromCropDownload === true;

  /* ── 기본 상태 ─────────────────────────────────────────────────── */
  const [phase, setPhase] = useState("polling"); // polling | done | error
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  const [fileUrl, setFileUrl] = useState(null);
  const [fileName, setFileName] = useState("");
  const [expiresAt, setExpiresAt] = useState(null);

  const pollRef = useRef(null);

  /* ── 구간 다운로드 공통 상태 ─────────────────────────────────── */
  const [showRangeDownload, setShowRangeDownload] = useState(false);

  /* ── 이미지 크롭 상태 ─────────────────────────────────────────── */
  const cropCanvasRef = useRef(null);
  const imgRef = useRef(null);
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const dragMode = useRef("new");       // "new" | "nw" | "ne" | "sw" | "se"
  const anchorPoint = useRef({ x: 0, y: 0 }); // resize 시 반대쪽 고정 모서리
  const selectedRectRef = useRef(null);        // document 핸들러에서 최신 rect 접근용
  const docMoveHandler = useRef(null);         // document mousemove 참조 (제거에 필요)
  const docUpHandler = useRef(null);         // document mouseup  참조 (제거에 필요)
  const [selectedRect, setSelectedRect] = useState(null); // canvas 좌표(= 실제 이미지 좌표)

  /* selectedRect 변경 → ref 동기화 (document 핸들러에서 최신값 읽기 위함) */
  useEffect(() => { selectedRectRef.current = selectedRect; }, [selectedRect]);

  /* 컴포넌트 언마운트 시 document 이벤트 잔여 정리 */
  useEffect(() => {
    return () => {
      if (docMoveHandler.current) document.removeEventListener("mousemove", docMoveHandler.current);
      if (docUpHandler.current) document.removeEventListener("mouseup", docUpHandler.current);
    };
  }, []);

  /* fromCropDownload 이미지 blob URL 참조 — 언마운트 시 메모리 해제 */
  const blobUrlRef = useRef(null);
  useEffect(() => {
    return () => {
      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
    };
  }, []);

  /* ── 영상 구간 상태 ───────────────────────────────────────────── */
  const videoRef = useRef(null);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [isTrimLoading, setIsTrimLoading] = useState(false); // 서버 처리 중
  const [rangeError, setRangeError] = useState("");

  /* ── 폴링 ─────────────────────────────────────────────────────── */
  useEffect(() => {
    if (!jobId) {
      setError("jobId가 없습니다. 상세 페이지로 돌아가 다시 시도해주세요.");
      setPhase("error");
      return;
    }

    // 구간다운로드 이동 경로: 이미 완료된 작업 → 폴링 없이 파일 로드
    if (fromCropDownload) {
      const downloadUrl = getDownloadUrl(jobId);
      let cancelled = false;

      const run = async () => {
        // 파일명·만료일 정보 로드
        try {
          const info = await getResultFile(jobId);
          if (!cancelled) {
            setFileName(info.original_filename || "result");
            setExpiresAt(info.expires_at || null);
          }
        } catch { /* 정보 없어도 파일 표시는 계속 진행 */ }

        if (cancelled) return;

        if (fileType !== "video") {
          // 이미지: download_handler가 쿠키 인증을 요구하므로
          // crossOrigin="anonymous"(쿠키 미전송)로는 401 반환 → blob URL로 우회
          try {
            const res = await fetch(downloadUrl, { credentials: "include" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            // Content-Disposition 헤더에서 서버가 지정한 파일명 추출
            const disp = res.headers.get("Content-Disposition") || "";
            const match = disp.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
            const serverFileName = match ? decodeURIComponent(match[1].trim()) : null;
            const blob = await res.blob();
            if (!cancelled) {
              const blobUrl = URL.createObjectURL(blob);
              blobUrlRef.current = blobUrl;
              setFileUrl(blobUrl); // same-origin blob URL → canvas taint 없음
              // 서버 파일명 우선, 없으면 getResultFile에서 받은 파일명 유지
              if (serverFileName) setFileName(serverFileName);
            }
          } catch {
            // blob 변환 실패 시 직접 URL fallback
            if (!cancelled) setFileUrl(downloadUrl);
          }
        } else {
          // 영상: <video> 태그는 crossOrigin 없이 same-site 쿠키 자동 전송
          if (!cancelled) setFileUrl(downloadUrl);
        }

        if (!cancelled) setPhase("done");
      };

      run();
      return () => { cancelled = true; };
    }

    const mId = location.state?.maskJobId;
    const startPolling = (targetId) => {
      const poll = () => {
        getAnalysisJob(targetId)
          .then((job) => {
            setProgress(job.total_progress || 0);
            if (ACTIVE.has(job.status)) {
              pollRef.current = setTimeout(poll, 2500);
            } else if (job.status === "completed") {
              return getResultFile(targetId)
                .then((info) => {
                  setFileUrl(getDownloadUrl(targetId));
                  setFileName(info.original_filename || "result");
                  setExpiresAt(info.expires_at || null);
                  setPhase("done");
                })
                .catch(() => {
                  setFileUrl(getDownloadUrl(targetId));
                  setPhase("done");
                });
            } else {
              setError(`마스킹 처리 실패: 상태=${job.status}`);
              setPhase("error");
            }
          })
          .catch((e) => { setError(String(e)); setPhase("error"); });
      };
      poll();
    };

    if (mId) {
      startPolling(mId);
    } else {
      setError("마스킹 작업 ID(maskJobId)가 제공되지 않았습니다. 이전 페이지에서 '처리진행' 버튼을 눌러 접근해주세요.");
      setPhase("error");
    }
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* 구간 패널이 열릴 때 canvas 크기 초기화 (이미지가 이미 로드된 경우 대비) */
  useEffect(() => {
    if (!showRangeDownload || fileType === "video") return;
    const img = imgRef.current;
    const canvas = cropCanvasRef.current;
    if (img && canvas && img.naturalWidth > 0) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
  }, [showRangeDownload, fileType]);


  /* ── 만료일 포맷 ──────────────────────────────────────────────── */
  const formatExpiry = (isoStr) => {
    if (!isoStr) return "해당 없음";
    try {
      return new Date(isoStr).toLocaleDateString("ko-KR", {
        year: "numeric", month: "long", day: "numeric",
      });
    } catch { return isoStr; }
  };

  /* ── 전체 다운로드 ────────────────────────────────────────────── */
  const handleDownload = () => {
    if (!fileUrl) return;
    const a = document.createElement("a");
    a.href = fileUrl;
    a.download = fileName || "garim_result";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  /* ────────────────────────────────────────────────────────────────
     이미지 크롭 — Canvas 이벤트
  ──────────────────────────────────────────────────────────────── */

  /* 이미지 로드 완료 → canvas 크기를 실제 이미지 해상도로 설정 */
  const handleImgLoad = () => {
    const img = imgRef.current;
    const canvas = cropCanvasRef.current;
    if (img && canvas) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }
  };

  /* 마우스 이벤트 좌표 → canvas 내부 좌표(= 실제 이미지 픽셀) 변환 */
  const toCanvasCoords = (e) => {
    const canvas = cropCanvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const r = canvas.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * (canvas.width / r.width),
      y: (e.clientY - r.top) * (canvas.height / r.height),
    };
  };

  /* 이미지 경계 밖으로 나가지 않도록 클램프한 canvas 좌표 반환 */
  const toCanvasCoordsClamped = (e) => {
    const canvas = cropCanvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const r = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, (e.clientX - r.left) * (canvas.width / r.width))),
      y: Math.max(0, Math.min(canvas.height, (e.clientY - r.top) * (canvas.height / r.height))),
    };
  };

  /* 모서리 핸들 클릭 감지 반경 (display 12px → canvas 내부 px 변환) */
  const getHandleRadius = () => {
    const canvas = cropCanvasRef.current;
    if (!canvas) return 20;
    const r = canvas.getBoundingClientRect();
    return 12 * (canvas.width / r.width);
  };

  /* 마우스 위치가 어느 모서리 핸들 위인지 반환 ("nw"|"ne"|"sw"|"se"|null) */
  const getCornerHit = (pos) => {
    const rect = selectedRectRef.current;
    if (!rect) return null;
    const r = getHandleRadius();
    const corners = {
      nw: [rect.x, rect.y],
      ne: [rect.x + rect.w, rect.y],
      sw: [rect.x, rect.y + rect.h],
      se: [rect.x + rect.w, rect.y + rect.h],
    };
    for (const [name, [cx, cy]] of Object.entries(corners)) {
      if (Math.abs(pos.x - cx) <= r && Math.abs(pos.y - cy) <= r) return name;
    }
    return null;
  };

  /* 모서리 이름 → resize 커서 */
  const CORNER_CURSORS = { nw: "nw-resize", ne: "ne-resize", sw: "sw-resize", se: "se-resize" };

  /* 드래그 중인 모서리의 반대쪽 고정 모서리 좌표 반환 */
  const getOppositeAnchor = (corner, rect) => {
    if (corner === "nw") return { x: rect.x + rect.w, y: rect.y + rect.h };
    if (corner === "ne") return { x: rect.x, y: rect.y + rect.h };
    if (corner === "sw") return { x: rect.x + rect.w, y: rect.y };
    if (corner === "se") return { x: rect.x, y: rect.y };
    return { x: 0, y: 0 };
  };

  /* 두 점으로 rect 객체 생성 */
  const makeRect = (a, b) => ({
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(b.x - a.x),
    h: Math.abs(b.y - a.y),
  });

  /* 선택 영역을 canvas에 그리기 (어두운 오버레이 + 점선 박스 + 모서리 핸들) */
  const drawSelection = (rect) => {
    const canvas = cropCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!rect || rect.w < 1 || rect.h < 1) return;

    // 배경 어둡게
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    // 선택 영역만 밝게 클리어
    ctx.clearRect(rect.x, rect.y, rect.w, rect.h);
    // 점선 테두리
    ctx.strokeStyle = "#1976d2";
    ctx.lineWidth = Math.max(1, canvas.width / 400); // 해상도 비례
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    // 모서리 핸들 (실선)
    const hs = Math.max(4, canvas.width / 200);
    ctx.setLineDash([]);
    ctx.fillStyle = "#1976d2";
    [
      [rect.x, rect.y],
      [rect.x + rect.w, rect.y],
      [rect.x, rect.y + rect.h],
      [rect.x + rect.w, rect.y + rect.h],
    ].forEach(([cx, cy]) => ctx.fillRect(cx - hs, cy - hs, hs * 2, hs * 2));
  };

  const handleCanvasMouseDown = (e) => {
    e.preventDefault();
    const pos = toCanvasCoords(e);
    const corner = getCornerHit(pos);

    if (corner && selectedRectRef.current) {
      /* 모서리 핸들 드래그 → resize 모드 */
      dragMode.current = corner;
      anchorPoint.current = getOppositeAnchor(corner, selectedRectRef.current);
    } else {
      /* 새 선택 영역 그리기 */
      dragMode.current = "new";
      dragStart.current = pos;
      setSelectedRect(null);
      selectedRectRef.current = null;
      const canvas = cropCanvasRef.current;
      if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    }

    isDragging.current = true;

    /* document 레벨에 등록: 마우스가 canvas 밖으로 나가도 드래그 유지 */
    docMoveHandler.current = (ev) => {
      const cur = toCanvasCoordsClamped(ev);
      if (dragMode.current === "new") {
        drawSelection(makeRect(dragStart.current, cur));
      } else {
        drawSelection(makeRect(anchorPoint.current, cur));
      }
    };

    docUpHandler.current = (ev) => {
      isDragging.current = false;
      document.removeEventListener("mousemove", docMoveHandler.current);
      document.removeEventListener("mouseup", docUpHandler.current);

      const cur = toCanvasCoordsClamped(ev);
      const rect = dragMode.current === "new"
        ? makeRect(dragStart.current, cur)
        : makeRect(anchorPoint.current, cur);

      if (rect.w < 5 || rect.h < 5) {
        if (dragMode.current === "new") {
          /* 너무 작은 드래그 → 선택 초기화 */
          const canvas = cropCanvasRef.current;
          if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
          setSelectedRect(null);
          selectedRectRef.current = null;
        } else {
          /* resize가 너무 작아지면 이전 상태 복원 */
          drawSelection(selectedRectRef.current);
        }
        return;
      }
      setSelectedRect(rect);
      selectedRectRef.current = rect;
      drawSelection(rect);
    };

    document.addEventListener("mousemove", docMoveHandler.current);
    document.addEventListener("mouseup", docUpHandler.current);
  };

  /* canvas 위에서 마우스 이동 — 드래그 중이 아닐 때 커서 모양만 변경 */
  const handleCanvasMouseMove = (e) => {
    if (isDragging.current) return;
    const pos = toCanvasCoords(e);
    const corner = getCornerHit(pos);
    const canvas = cropCanvasRef.current;
    if (canvas) canvas.style.cursor = corner ? CORNER_CURSORS[corner] : "crosshair";
  };

  /* 선택 영역 초기화 */
  const handleCropReset = () => {
    const canvas = cropCanvasRef.current;
    if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    setSelectedRect(null);
  };

  /* 크롭 영역 PNG 다운로드 — img 요소를 직접 canvas에 그려 추가 fetch 없이 처리 */
  const handleCropDownload = () => {
    if (!selectedRect) return;
    const img = imgRef.current;
    if (!img || !img.complete || img.naturalWidth === 0) {
      alert("이미지가 아직 로드되지 않았습니다. 잠시 후 다시 시도해주세요.");
      return;
    }
    try {
      const off = document.createElement("canvas");
      off.width = Math.round(selectedRect.w);
      off.height = Math.round(selectedRect.h);
      off.getContext("2d").drawImage(
        img,
        selectedRect.x, selectedRect.y, selectedRect.w, selectedRect.h,
        0, 0, off.width, off.height,
      );
      off.toBlob((pngBlob) => {
        if (!pngBlob) { alert("PNG 생성에 실패했습니다. 다시 시도해주세요."); return; }
        const a = document.createElement("a");
        a.href = URL.createObjectURL(pngBlob);
        a.download = `garim_crop_${Date.now()}.png`;
        a.click();
      }, "image/png");
    } catch (err) {
      /* crossOrigin="use-credentials"로 로드된 이미지여야 canvas에서 SecurityError 없이 사용 가능 */
      alert("크롭 다운로드 중 오류가 발생했습니다: " + err.message);
    }
  };

  /* ────────────────────────────────────────────────────────────────
     영상 시간 구간 다운로드 — 백엔드 ffmpeg → MP4
  ──────────────────────────────────────────────────────────────── */

  /* 영상 구간 다운로드 — 백엔드 ffmpeg로 MP4 생성 후 다운로드 */
  const handleVideoRangeDownload = async () => {
    const startSec = timeToSec(rangeStart);
    const endSec = timeToSec(rangeEnd);

    // 유효성 검사
    if (isNaN(startSec) || isNaN(endSec)) {
      setRangeError("시작/종료 시간을 올바르게 입력해주세요. (예: 0:10)");
      return;
    }
    if (startSec >= endSec) {
      setRangeError("종료 시간은 시작 시간보다 커야 합니다.");
      return;
    }
    const video = videoRef.current;
    if (video && isFinite(video.duration) && endSec > video.duration + 0.5) {
      setRangeError(`종료 시간이 영상 길이(${secToTime(video.duration)})를 초과합니다.`);
      return;
    }

    setRangeError("");
    setIsTrimLoading(true);
    try {
      // 백엔드에서 ffmpeg로 구간 추출 → MP4 반환
      // fromCropDownload 경로: maskJobId 대신 jobId(= mask_final job id)를 사용
      const trimJobId = fromCropDownload ? jobId : location.state?.maskJobId;
      const trimUrl = getTrimUrl(trimJobId, startSec, endSec);
      const res = await fetch(trimUrl, { credentials: "include" });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message || `서버 오류 (${res.status})`);
      }

      // 응답 Blob을 파일로 저장
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      // Content-Disposition 헤더에서 파일명 추출, 없으면 기본값
      const disp = res.headers.get("content-disposition") || "";
      const match = disp.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i);
      a.href = url;
      a.download = match ? decodeURIComponent(match[1]) : `garim_trim_${secToTime(startSec)}-${secToTime(endSec)}.mp4`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setRangeError("구간 다운로드 실패: " + (err?.message || String(err)));
    } finally {
      setIsTrimLoading(false);
    }
  };

  /* ── 구간 다운로드 토글 ───────────────────────────────────────── */
  const toggleRangeDownload = () => {
    setShowRangeDownload(v => !v);
    handleCropReset();
    setRangeError("");
  };

  /* ════════════════════════════════════════════════════════════════
     렌더
  ════════════════════════════════════════════════════════════════ */
  return (
    <GarimPage bodyClass="page-app" screenLabel="Result">
      <div className="pv-page">

        {/* ── 상단 툴바 ── */}
        <div className="pv-toolbar">
          <h1>마스킹 처리 결과</h1>
          {phase === "polling" && (
            <span className="mui-chip mui-chip--soft-warning mui-chip--md">처리 중…</span>
          )}
          {phase === "done" && (
            <span className="mui-chip mui-chip--soft-success mui-chip--md">처리 완료</span>
          )}
        </div>

        {/* ── 본문 ── */}
        <div className="pv-grid">
          <div className="pv-left">

            {/* 에러 */}
            {phase === "error" && (
              <div className="rp-error">
                <span className="material-icons rp-error-ico">error_outline</span>
                <p className="rp-error-msg">{error}</p>
              </div>
            )}

            {/* 처리 중 로딩 */}
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
                  <h3>마스킹 처리 중입니다. 잠시 기다려주세요...</h3>
                  <p>선택하신 부분을 안전하게 처리하고 있습니다.</p>
                </div>
                <div className="pv-progress-bar-container">
                  <div className="pv-progress-bar" style={{ width: `${progress}%` }}></div>
                </div>
                <div className="pv-progress-text">{progress}% 완료</div>
              </div>
            )}

            {/* 완료 — 미리보기 */}
            {phase === "done" && fileUrl && (
              <div className="rp-preview-wrap">
                {fileType === "video" ? (
                  /* 영상 미리보기 */
                  <video
                    ref={videoRef}
                    src={fileUrl}
                    controls
                    className="rp-preview-video"
                  />
                ) : (
                  /* 이미지 미리보기 + 크롭 canvas 오버레이 */
                  <div className="rp-crop-wrapper">
                    <img
                      ref={imgRef}
                      src={fileUrl}
                      alt="마스킹 결과"
                      crossOrigin="use-credentials"
                      onLoad={handleImgLoad}
                      className="rp-preview-img"
                    />
                    {/* 구간 다운로드 활성 시에만 canvas 표시 */}
                    {showRangeDownload && (
                      <canvas
                        ref={cropCanvasRef}
                        className="rp-crop-canvas"
                        onMouseDown={handleCanvasMouseDown}
                        onMouseMove={handleCanvasMouseMove}
                      />
                    )}
                  </div>
                )}
                <p className="rp-preview-caption">
                  마스킹 처리가 완료되었습니다. 다운로드 버튼을 눌러 저장하세요.
                </p>
              </div>
            )}
          </div>

          {/* ── 우측 패널 ── */}
          <aside className="pv-right">
            <div className="head">
              <h2>처리 완료</h2>
              <div className="sub">
                {phase === "polling"
                  ? "마스킹 처리가 완료되면 결과 파일을 다운로드할 수 있습니다."
                  : "마스킹이 완료된 파일입니다. 다운로드 후 안전하게 사용하세요."}
              </div>
            </div>

            {/* 파일 보관 정보 */}
            {phase === "done" && (
              <div className="rp-info-block">
                <div className="rp-info-title">파일 보관 정보</div>
                <div>파일명: <strong className="rp-info-val">{fileName || "-"}</strong></div>
                <div>
                  보관 만료일:{" "}
                  <strong className={`rp-expire${expiresAt ? "" : " rp-expire--off"}`}>
                    {formatExpiry(expiresAt)}
                  </strong>
                </div>
                {!expiresAt && (
                  <p className="rp-info-note">
                    Free 요금제는 파일 보관이 제공되지 않습니다.<br />
                    지금 바로 다운로드 하세요.
                  </p>
                )}
              </div>
            )}

            {/* 워터마크 안내 */}
            {phase === "done" && (
              <div className="rp-info-block">
                <strong className="rp-info-val">워터마크 안내</strong><br />
                최종 결과물에는 워터마크가 보이지 않습니다. <br />안심하고 사용하세요.
              </div>
            )}

            {/* ── 버튼 영역 ── */}
            <div className="rp-btn-area">
              {phase === "done" && (
                <>
                  {/* 전체 다운로드 */}
                  <button
                    className="mui-btn mui-btn--contained mui-btn--lg rp-btn-full"
                    onClick={handleDownload}
                  >
                    <span className="material-icons rp-dl-ico">download</span>
                    전체 다운로드
                  </button>

                  {/* 구간 다운로드 토글 버튼 */}
                  <button
                    className={`mui-btn mui-btn--outlined mui-btn--lg rp-btn-full${showRangeDownload ? " rp-range-toggle--active" : ""}`}
                    onClick={toggleRangeDownload}
                  >
                    <span className="material-icons rp-dl-ico">
                      {showRangeDownload ? "close" : "crop"}
                    </span>
                    {showRangeDownload ? "구간 다운로드 닫기" : "구간 다운로드"}
                  </button>

                  {/* 구간 다운로드 패널 */}
                  {showRangeDownload && (
                    <div className="rp-range-panel">
                      {fileType === "video" ? (
                        /* ── 영상: 시간 구간 ── */
                        <>
                          <div className="rp-range-label">
                            <span className="material-icons rp-range-label-ico">schedule</span>
                            시간 구간 선택
                          </div>
                          <div className="rp-time-inputs">
                            <div className="rp-time-field">
                              <label>시작</label>
                              <input
                                type="text"
                                placeholder="0:00"
                                value={rangeStart}
                                onChange={e => setRangeStart(e.target.value)}
                                disabled={isTrimLoading}
                              />
                            </div>
                            <span className="rp-time-sep">~</span>
                            <div className="rp-time-field">
                              <label>종료</label>
                              <input
                                type="text"
                                placeholder="0:10"
                                value={rangeEnd}
                                onChange={e => setRangeEnd(e.target.value)}
                                disabled={isTrimLoading}
                              />
                            </div>
                          </div>
                          {rangeError && <div className="rp-range-error">{rangeError}</div>}
                          <p className="rp-range-hint">mm:ss 형식으로 입력 (예: 0:30 / 1:45)</p>

                          <button
                            className="mui-btn mui-btn--contained rp-btn-full"
                            onClick={handleVideoRangeDownload}
                            disabled={isTrimLoading}
                          >
                            <span className="material-icons rp-range-btn-ico">
                              {isTrimLoading ? "hourglass_top" : "videocam"}
                            </span>
                            {isTrimLoading ? "변환 중..." : "구간 다운로드"}
                          </button>
                          <p className="rp-range-note">※ MP4 포맷으로 저장됩니다 (서버 변환)</p>
                        </>
                      ) : (
                        /* ── 이미지: 크롭 영역 ── */
                        <>
                          <div className="rp-range-label">
                            <span className="material-icons rp-range-label-ico">crop</span>
                            영역 선택
                          </div>
                          <p className="rp-range-hint">
                            왼쪽 이미지 위에서 마우스를 드래그하여 원하는 영역을 선택하세요.
                          </p>
                          <div className="rp-crop-btns">
                            <button
                              className="mui-btn mui-btn--contained rp-crop-go"
                              onClick={handleCropDownload}
                              disabled={!selectedRect}
                            >
                              <span className="material-icons rp-range-btn-ico">crop</span>
                              영역 다운로드
                            </button>
                            <button
                              className="mui-btn mui-btn--outlined"
                              onClick={handleCropReset}
                              disabled={!selectedRect}
                            >
                              초기화
                            </button>
                          </div>
                          {selectedRect && (
                            <p className="rp-range-hint rp-range-hint--done">
                              영역 선택 완료 — PNG로 저장됩니다
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </>
              )}

              <Link to="/upload" className="mui-btn mui-btn--outlined rp-btn-full rp-newfile-btn">
                <span className="material-icons rp-newfile-ico">add_circle_outline</span>
                다른 파일 체크
              </Link>
            </div>
          </aside>
        </div>
      </div>
    </GarimPage>
  );
}
