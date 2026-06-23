import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { getApiBaseUrl, getJobDetections, getJobResult, saveSelections, triggerMaskFinal, submitAbuseReport } from "../../utils/api";
import "../../css/garim-pages/ReplaceOptions.css";

import GarimPage from "../../components/garim/GarimPage";

// ── 시간 포맷 (초 → MM:SS)
function formatTime(sec) {
  if (sec === null || sec === undefined) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ── PII 타입별 색상 — pipeline_detail_view.py _PII_COLORS를 BGR→RGB 변환한 값
// BGR(B,G,R) → RGB(R,G,B): r=bgr[2], g=bgr[1], b=bgr[0]
const PII_COLORS = {
  "주민등록번호": "#ff3232", "외국인등록번호": "#ff3232", // BGR(50,50,255)
  "전화번호": "#32ff32",                               // BGR(50,255,50)
  "주소": "#3296ff",                               // BGR(255,150,50)
  "카드번호": "#ff9632",                               // BGR(50,150,255)
  "계좌번호": "#ffff32",                               // BGR(50,255,255)
  "이메일": "#9632ff",                               // BGR(255,50,150)
};
const PII_DEFAULT_COLOR = "#ff64ff";

// ── 위험도별 색상 (재생바 마커용)
const SEVERITY_COLORS = {
  high: "#d32f2f",
  medium: "#ed6c02",
  low: "#0288d1",
};

function getPiiColor(label) {
  return PII_COLORS[label] || PII_DEFAULT_COLOR;
}

// ── 같은 label이 여러 개일 때 "전화번호1", "전화번호2" 순번 부여
function buildLabelMap(detections) {
  const count = {};
  const idx = {};
  detections.forEach((d) => { count[d.label] = (count[d.label] || 0) + 1; });
  return (d) => {
    if (count[d.label] <= 1) return d.label;
    idx[d.label] = (idx[d.label] || 0) + 1;
    return `${d.label}${idx[d.label]}`;
  };
}

// ── 상세보기 파일 URL (쿠키 인증 포함, img src로 직접 사용 가능)
function detailFileUrl(jobId, fileType) {
  return `${getApiBaseUrl()}/analysis/jobs/${jobId}/detail-file?file_type=${fileType}`;
}

// ══════════════════════════════════════════════════════
// 이미지 뷰어 — _상세보기.jpg + SVG bbox 오버레이 + 우측 체크박스 목록
// ══════════════════════════════════════════════════════
function ImageDetailView({ jobId, detections, selected, onToggle, onSelectAll, setShowReportModal }) {
  const [naturalSize, setNaturalSize] = useState(null); // { w, h } 원본 이미지 크기
  const [hoveredId, setHoveredId] = useState(null); // 우측 카드 hover 중인 detection_id

  const selectedCount = Object.values(selected).filter(Boolean).length;
  const total = detections.length;
  const getLabel = buildLabelMap(detections); // 순번 라벨 함수 (한 번 생성)

  // SVG에 그릴 수 있는 detection — polygon 또는 bbox가 있는 것
  const hasOverlay = detections.filter(
    (d) => (d.polygons && d.polygons.length > 0) || (d.bbox?.x != null && d.bbox?.w != null)
  );

  return (
    <div className="opt-grid">
      {/* 좌측: 상세보기 이미지 + SVG 오버레이 */}
      <div className="opt-left opt-left--image">
        <div className="image-viewer-wrap">
          {/* 이미지 + SVG를 같은 aspect ratio로 겹침 */}
          <div className="detail-image-container">
            <img
              src={detailFileUrl(jobId, "image")}
              alt="상세보기 이미지"
              className="detail-image"
              onLoad={(e) => setNaturalSize({ w: e.target.naturalWidth, h: e.target.naturalHeight })}
              onError={(e) => { e.target.style.display = "none"; }}
            />
            {/* SVG 오버레이 — viewBox=원본크기, preserveAspectRatio=none으로 이미지와 1:1 매핑
                polygon 데이터 있으면 회전 <polygon>, 없으면 axis-aligned <rect> 폴백 */}
            {naturalSize && hasOverlay.length > 0 && (
              <svg
                className="detail-image-svg"
                viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
                preserveAspectRatio="none"
              >
                {hasOverlay.map((d) => {
                  const isSelected = selected[d.detection_id] ?? false;
                  const isHovered = hoveredId === d.detection_id;
                  const color = getPiiColor(d.label);
                  const fillColor = isSelected ? `${color}40` : "transparent";
                  const stroke = isHovered ? "#ffffff" : isSelected ? color : "transparent";
                  const strokeW = isHovered ? 3 : isSelected ? 2 : 0;
                  const sharedProps = {
                    key: d.detection_id,
                    fill: fillColor,
                    stroke,
                    strokeWidth: strokeW,
                    pointerEvents: "all",
                    style: { cursor: "pointer", transition: "fill 120ms, stroke 120ms" },
                    onClick: () => onToggle(d.detection_id),
                  };

                  // polygons 있으면 각 polygon마다 <polygon> 요소 — 각도/형태 완벽 매핑
                  if (d.polygons && d.polygons.length > 0) {
                    return (
                      <g key={d.detection_id}>
                        {d.polygons.map((poly, pi) => {
                          // poly: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                          const pts = poly.map(([px, py]) => `${px},${py}`).join(" ");
                          return (
                            <polygon
                              key={`${d.detection_id}_p${pi}`}
                              points={pts}
                              fill={fillColor}
                              stroke={stroke}
                              strokeWidth={strokeW}
                              pointerEvents="all"
                              className="opt-svg-layer"
                              onClick={() => onToggle(d.detection_id)}
                            />
                          );
                        })}
                      </g>
                    );
                  }

                  // polygon 없을 때 axis-aligned rect 폴백
                  const { x, y, w, h } = d.bbox;
                  return (
                    <rect
                      {...sharedProps}
                      x={x} y={y} width={w} height={h}
                    />
                  );
                })}
              </svg>
            )}
          </div>
          {/* 이미지 없을 때 대체 안내 */}
          <div className="detail-image-fallback">
            <span className="material-icons opt-no-image-icon">image_not_supported</span>
            <div className="ro-loading-text">상세보기 이미지 준비 중...</div>
          </div>
        </div>
      </div>

      {/* 우측: 선택 패널 */}
      <aside className="opt-right">
        <div className="head">
          <h2>{total}건의 탐지 항목</h2>
          <div className="sub">마스킹할 항목을 선택하세요. 미선택 항목은 원본 유지됩니다.</div>
        </div>
        <div className="bulk">
          <span className="label">일괄 선택:</span>
          <button className="active" onClick={() => onSelectAll(true)}>전체 선택</button>
          <button onClick={() => onSelectAll(false)}>전체 해제</button>
        </div>
        <div className="opt-list">
          {detections.length === 0 ? (
            <div className="opt-empty-box">
              탐지된 개인정보가 없습니다.
            </div>
          ) : (
            detections.map((d) => {
              const isSelected = selected[d.detection_id] ?? false;
              const color = getPiiColor(d.label);
              const displayName = getLabel(d);        // "전화번호1", "주소2" 등
              return (
                <div
                  key={d.detection_id}
                  className={`opt-card${isSelected ? " selected" : ""}${d.is_masked ? " masked" : ""}`}
                  onClick={() => !d.is_masked && onToggle(d.detection_id)}
                  onMouseEnter={() => setHoveredId(d.detection_id)}
                  onMouseLeave={() => setHoveredId(null)}
                  style={{
                    opacity: d.is_masked ? 0.6 : 1,
                    cursor: d.is_masked ? "not-allowed" : "pointer",
                  }}
                >
                  <div className="opt-card__head">
                    {/* PII 타입 색상 도트 — 이미지 박스 색상과 동일 */}
                    <div className="pii-color-dot" style={{ background: color }} />
                    <div className="info">
                      <div className="opt-card__title">
                        {/* 선택 시 체크 아이콘 */}
                        {isSelected && (
                          <span className="material-icons" style={{ fontSize: 14, color, verticalAlign: "middle", marginRight: 4 }}>
                            check_circle
                          </span>
                        )}
                        {displayName}
                        {d.is_masked && <span className="ro-masked-note">(이미 처리 완료되었습니다)</span>}
                      </div>
                      <div className="opt-card__time" style={{ color }}>이미지</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={d.is_masked ? true : isSelected}
                      disabled={d.is_masked}
                      onChange={() => onToggle(d.detection_id)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ width: 18, height: 18, cursor: d.is_masked ? "not-allowed" : "pointer", accentColor: color }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
        {/* 선택 요약 */}
        <div className="opt-selection-info ro-sel-info">
          <div>
            선택 <strong className="opt-selection-count">{selectedCount}건</strong> / 전체 {total}건
          </div>
          <button
            type="button"
            className="mui-btn mui-btn--text mui-btn--sm ro-report-btn"
            onClick={() => setShowReportModal(true)}
          >
            <span className="material-icons ro-report-ico">warning</span>
            <span className="ro-report-text">AI 오탐지 / 미탐지 신고</span>
          </button>
        </div>
      </aside>
    </div>
  );
}

// ══════════════════════════════════════════════════════
// 영상 뷰어 — _상세보기.mp4 재생 + 재생바 마커 + 체크박스 목록
// ══════════════════════════════════════════════════════
function VideoDetailView({ jobId, detections, timelineMarkers, selected, onToggle, onSelectAll, navigate, setShowReportModal }) {
  const videoRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);

  // 시각 PII / 음성 PII 분리
  const visualDetections = detections.filter((d) => d.detection_type !== "voice_pii");
  const audioDetections = detections.filter((d) => d.detection_type === "voice_pii");
  const total = detections.length;
  const selectedCount = Object.values(selected).filter(Boolean).length;
  const getLabel = buildLabelMap(detections);

  // 재생/정지 토글
  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); setIsPlaying(true); }
    else { v.pause(); setIsPlaying(false); }
  };

  // 재생바 클릭 → 시간 이동
  const handleProgressClick = (e) => {
    if (!duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    if (videoRef.current) videoRef.current.currentTime = pct * duration;
  };

  // 확인 버튼 → 해당 시점으로 이동 후 일시정지 (재생은 사용자가 직접)
  const seekTo = (sec) => {
    if (videoRef.current) {
      videoRef.current.currentTime = sec;
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  // 음량 변경
  const handleVolumeChange = (e) => {
    const v = parseFloat(e.target.value);
    setVolume(v);
    setIsMuted(v === 0);
    if (videoRef.current) { videoRef.current.volume = v; videoRef.current.muted = v === 0; }
  };

  // 음소거 토글
  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    const next = !isMuted;
    setIsMuted(next);
    v.muted = next;
    if (!next && volume === 0) { setVolume(0.5); v.volume = 0.5; }
  };

  // 미리보기 버튼 → Preview 페이지 이동 (탐지 시점 앞뒤 3초 클립 전달)
  const goToPreview = (d) => {
    const startSec = d.start_time_sec ?? 0;
    const endSec = d.end_time_sec ?? startSec;
    navigate("/preview", {
      state: {
        jobId,
        pii_id: d.pii_id || d.detection_id,
        clip_start: Math.max(0, startSec - 3),
        clip_end: endSec + 3,
        fileType: "video",
      },
    });
  };

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  // 탐지 카드 공통 렌더러
  const renderDetectionCard = (d, color) => {
    const isMasked = d.is_masked;
    const isSelected = selected[d.detection_id] ?? false;
    const startSec = d.start_time_sec;
    const displayName = getLabel(d);
    const isAudio = d.detection_type === "voice_pii";
    return (
      <div
        key={d.detection_id}
        className={`opt-card${isSelected ? " selected" : ""}${isMasked ? " masked" : ""}`}
        onClick={() => !isMasked && onToggle(d.detection_id)}
        style={{
          ...(isAudio ? { borderLeft: `3px solid ${color}` } : {}),
          opacity: isMasked ? 0.6 : 1,
          cursor: isMasked ? "not-allowed" : "pointer",
        }}
      >
        <div className="opt-card__head">
          <div className="pii-color-dot" style={{ background: color }} />
          <div className="info">
            <div className="opt-card__title">
              {isMasked ? (
                <span className="material-icons ro-mask-ico-muted">
                  lock
                </span>
              ) : isSelected ? (
                <span className="material-icons" style={{ fontSize: 14, color, verticalAlign: "middle", marginRight: 4 }}>
                  check_circle
                </span>
              ) : null}
              {isAudio ? "🔊 " : "👁 "}
              {displayName}
              {d.detected_text ? ` — ${d.detected_text.slice(0, 20)}${d.detected_text.length > 20 ? "…" : ""}` : ""}
              {isMasked && <span className="ro-masked-note">(이미 처리 완료되었습니다)</span>}
            </div>
            <div className="opt-card__time" style={{ color }}>
              {startSec != null ? formatTime(startSec) : "—"}
            </div>
          </div>
          <div className="opt-time-wrap">
            {/* 확인 버튼 — 해당 탐지 시점으로 영상 재생 위치 이동 */}
            <button
              type="button"
              className="mui-btn mui-btn--outlined mui-btn--sm opt-tag-btn active"
              onClick={(e) => { e.stopPropagation(); seekTo(d.start_time_sec ?? 0); }}
              title="해당 시점으로 이동"
            >
              <span className="material-icons opt-tag-icon">my_location</span>
              확인
            </button>
            {/* 미리보기 버튼 — Preview 페이지로 이동 (탐지 시점 앞뒤 3초 클립) */}
            <button
              type="button"
              className="mui-btn mui-btn--outlined mui-btn--sm opt-tag-btn"
              onClick={(e) => { e.stopPropagation(); !isMasked && goToPreview(d); }}
              title={isMasked ? "마스킹 완료된 항목은 미리보기할 수 없습니다." : "탐지 구간 미리보기"}
              disabled={isMasked}
            >
              <span className="material-icons opt-tag-icon">visibility</span>
              미리보기
            </button>
            <input
              type="checkbox"
              checked={isMasked ? true : isSelected}
              disabled={isMasked}
              onChange={() => onToggle(d.detection_id)}
              onClick={(e) => e.stopPropagation()}
              style={{ width: 18, height: 18, cursor: isMasked ? "not-allowed" : "pointer", accentColor: color }}
            />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="opt-grid">
      {/* 좌측: 상세보기 영상 플레이어 */}
      <div className="opt-left">
        <div className="player-wrap">
          <div className="player-box">
            {videoError ? (
              <div className="opt-video-off">
                <span className="material-icons opt-video-off-icon">videocam_off</span>
                <span className="opt-video-off-title">상세보기 영상을 불러올 수 없습니다.</span>
                <span className="ro-retry-note">분석 파이프라인 완료 후 재시도하세요.</span>
              </div>
            ) : (
              <video
                ref={videoRef}
                src={detailFileUrl(jobId, "video")}
                className="detail-video opt-pointer"
                crossOrigin="use-credentials"
                onClick={togglePlay}
                onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
                onLoadedMetadata={(e) => setDuration(e.target.duration)}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onError={() => setVideoError(true)}
              />
            )}
          </div>
        </div>

        {/* 재생 컨트롤 */}
        <div className="player-ctrls">
          <button onClick={togglePlay} title={isPlaying ? "일시정지" : "재생"}>
            <span className="material-icons">{isPlaying ? "pause" : "play_arrow"}</span>
          </button>
          <span className="time">{formatTime(currentTime)} / {formatTime(duration)}</span>

          {/* 재생바 + PII 마커 — 선택 여부에 따라 마커 강조 */}
          <div className="timeline opt-pointer" onClick={handleProgressClick}>
            <div className="timeline__fill" style={{ width: `${progressPct}%` }} />
            {timelineMarkers.map((marker, idx) => {
              const isSelected = selected[marker.id] ?? false;
              const color = marker.source === "audio"
                ? "#7c4dff"
                : (SEVERITY_COLORS[marker.severity] || "#1976d2");
              return (
                <div
                  key={idx}
                  className="timeline__marker"
                  style={{
                    left: `${marker.left_pct}%`,
                    background: color,
                    // 체크 선택 시 마커 크게 + 테두리 강조
                    width: isSelected ? "16px" : "10px",
                    height: isSelected ? "16px" : "10px",
                    top: isSelected ? "-5px" : "-2px",
                    border: isSelected ? "3px solid #fff" : "2px solid rgba(255,255,255,0.7)",
                    boxShadow: isSelected ? `0 0 8px ${color}` : "none",
                    opacity: isSelected ? 1 : 0.7,
                    zIndex: isSelected ? 3 : 2,
                  }}
                  title={`[${marker.source === "audio" ? "음성" : "시각"}] ${marker.pii_type} · ${formatTime(marker.start_sec)}`}
                  onClick={(e) => { e.stopPropagation(); seekTo(marker.start_sec); }}
                />
              );
            })}
          </div>

          {/* 음량 컨트롤 — 뮤트 버튼 + 슬라이더 */}
          <div className="opt-volume-wrap">
            <button onClick={toggleMute} title={isMuted ? "음소거 해제" : "음소거"} className="opt-mute-btn">
              <span className="material-icons opt-mute-icon">
                {isMuted || volume === 0 ? "volume_off" : volume < 0.5 ? "volume_down" : "volume_up"}
              </span>
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={isMuted ? 0 : volume}
              onChange={handleVolumeChange}
              title={`음량 ${Math.round((isMuted ? 0 : volume) * 100)}%`}
              className="ro-range-input"
            />
          </div>

          <button onClick={() => videoRef.current?.requestFullscreen()} title="전체화면">
            <span className="material-icons">fullscreen</span>
          </button>
        </div>

        {/* 마커 범례 */}
        {timelineMarkers.length > 0 && (
          <div className="marker-legend">
            <span className="legend-item"><span className="legend-dot ro-dot--danger" />시각 위험</span>
            <span className="legend-item"><span className="legend-dot ro-dot--warn" />시각 주의</span>
            <span className="legend-item"><span className="legend-dot ro-dot--info" />시각 참고</span>
            <span className="legend-item"><span className="legend-dot ro-dot--voice" />음성 주의</span>
          </div>
        )}
      </div>

      {/* 우측: 선택 패널 */}
      <aside className="opt-right">
        <div className="head">
          <h2>{total}건의 탐지 항목</h2>
          <div className="sub">마스킹 항목 선택 후 "처리진행"을 눌러주세요.</div>
        </div>
        <div className="bulk">
          <span className="label">일괄 선택:</span>
          <button className="active" onClick={() => onSelectAll(true)}>전체 선택</button>
          <button onClick={() => onSelectAll(false)}>전체 해제</button>
        </div>

        <div className="opt-list">
          {detections.length === 0 ? (
            <div className="opt-empty-box">탐지된 개인정보가 없습니다.</div>
          ) : (
            <>
              {/* 시각 PII 목록 */}
              {visualDetections.length > 0 && (
                <>
                  <div className="opt-cat-title">
                    시각 PII ({visualDetections.length}건)
                  </div>
                  {visualDetections.map((d) => renderDetectionCard(d, getPiiColor(d.label)))}
                </>
              )}

              {/* 음성 PII 목록 — 박스 표기 불가, 재생바 포인트로만 위치 확인 */}
              {audioDetections.length > 0 && (
                <>
                  <div style={{ padding: "8px 4px 4px", fontSize: 11, fontWeight: 600, color: "#7c4dff", textTransform: "uppercase", letterSpacing: "0.5px", marginTop: visualDetections.length > 0 ? 8 : 0 }}>
                    음성 PII ({audioDetections.length}건)
                  </div>
                  <div className="opt-cat-desc">
                    영상 박스 표기 불가 · 재생바 보라색 포인트로 구간 확인 · 선택 시 포인트 강조
                  </div>
                  {audioDetections.map((d) => renderDetectionCard(d, "#7c4dff"))}
                </>
              )}
            </>
          )}
        </div>

        <div className="opt-selection-info ro-sel-info">
          <div>
            선택 <strong className="opt-selection-count">{selectedCount}건</strong> / 전체 {total}건
          </div>
          <button
            type="button"
            className="mui-btn mui-btn--text mui-btn--sm ro-report-btn"
            onClick={() => setShowReportModal(true)}
          >
            <span className="material-icons ro-report-ico">warning</span>
            <span className="ro-report-text">AI 오탐지 / 미탐지 신고</span>
          </button>
        </div>
      </aside>
    </div>
  );
}

// ══════════════════════════════════════════════════════
// 메인 페이지
// ══════════════════════════════════════════════════════
export default function ReplaceOptions() {
  useDocumentTitle("상세보기 · Garim");
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const jobId = location.state?.jobId || searchParams.get("jobId");
  // 대시보드/히스토리 "상세" 버튼으로 진입했는지 여부 (구간다운로드 버튼 표시 조건)
  const fromDashboard = location.state?.fromDashboard === true;

  // AnalysisReport에서 전달된 summary (source_type 포함)
  const passedSummary = location.state?.summary || {};
  const [summary, setSummary] = useState(passedSummary);
  const [detections, setDetections] = useState([]);
  const [timelineMarkers, setTimelineMarkers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // 신고 모달 상태
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportDesc, setReportDesc] = useState("");
  const [reportLoading, setReportLoading] = useState(false);

  useEffect(() => {
    if (jobId) {
      localStorage.setItem(`job_stage_${jobId}`, "/replace-options");
    }
  }, [jobId]);

  // detection_id → 선택 여부 맵 (기본: 전체 선택)
  const [selected, setSelected] = useState({});

  useEffect(() => {
    if (!jobId) { setLoading(false); return; }
    getJobDetections(jobId)
      .then((data) => {
        const dets = data.detections || [];
        setDetections(dets);
        setTimelineMarkers(data.timeline_markers || []);
        if (!passedSummary.source_type) setSummary(data.summary || {});
        // 기본 전체 선택 (단, 이미 마스킹 완료된 항목은 제외)
        const init = {};
        dets.forEach((d) => { init[d.detection_id] = d.is_masked ? false : (d.is_selected ?? true); });
        setSelected(init);
      })
      .finally(() => setLoading(false));
  }, [jobId]);

  async function handleReportSubmit() {
    if (!reportDesc.trim()) {
      alert("신고 내용을 입력해주세요.");
      return;
    }
    setReportLoading(true);
    try {
      await submitAbuseReport({
        report_type: "bug_report",
        title: `[오탐지/미탐지 신고] Job ID: ${jobId}`,
        description: reportDesc,
        target_job_id: jobId
      });
      alert("신고가 정상적으로 접수되었습니다. 감사합니다.");
      setShowReportModal(false);
      setReportDesc("");
    } catch (err) {
      alert(err.message || "신고 접수 중 오류가 발생했습니다.");
    } finally {
      setReportLoading(false);
    }
  }

  const toggleSelection = useCallback((detection_id) => {
    setSelected((prev) => ({ ...prev, [detection_id]: !prev[detection_id] }));
  }, []);

  const onSelectAll = useCallback((val) => {
    setSelected((prev) => {
      const next = { ...prev };
      detections.forEach((d) => {
        if (!d.is_masked) {
          next[d.detection_id] = val;
        }
      });
      return next;
    });
  }, [detections]);

  const handleSaveAndNext = useCallback(async (dest) => {
    if (!jobId) return;
    setSaving(true);
    try {
      const selectionList = Object.entries(selected).map(([detection_id, is_selected]) => ({
        detection_id,
        is_selected,
      }));
      await saveSelections(jobId, selectionList);
      // fileType을 명시적으로 전달 (결과/미리보기 페이지에서 분기용)
      const ft = (summary.source_type || passedSummary?.source_type || "image") === "video" ? "video" : "image";
      if (dest === "/result") {
        try {
          const data = await triggerMaskFinal(jobId);
          navigate(dest, { state: { jobId, summary, fileType: ft, maskJobId: data.mask_job_id } });
        } catch (e) {
          alert("마스킹 작업 시작에 실패했습니다: " + e.message);
        }
      } else {
        navigate(dest, { state: { jobId, summary, fileType: ft } });
      }
    } finally {
      setSaving(false);
    }
  }, [jobId, selected, summary, passedSummary, navigate]);

  const sourceType = summary.source_type || passedSummary.source_type || "image";
  const isVideo = sourceType === "video";
  const selectedCount = Object.values(selected).filter(Boolean).length;
  const total = detections.length;

  if (loading) {
    return (
      <GarimPage bodyClass="page-app" screenLabel="15 Detail view">
        <div className="opt-page opt-page-center">
          <div className="caption-k ro-loading-cap">탐지 결과를 불러오는 중…</div>
        </div>
      </GarimPage>
    );
  }

  if (!jobId) {
    return (
      <GarimPage bodyClass="page-app" screenLabel="15 Detail view">
        <div className="opt-page opt-page-error">
          <div className="ro-no-job">분석 작업 ID가 없습니다.</div>
          <Link to="/upload" className="mui-btn mui-btn--outlined">새 파일 업로드</Link>
        </div>
      </GarimPage>
    );
  }

  return (
    <GarimPage bodyClass="page-app" screenLabel="15 Detail view">
      {/* AI 오탐지 신고 모달 */}
      {showReportModal && (
        <div className="credit-modal-overlay">
          <div className="credit-modal">
            <div className="credit-modal__icon ro-report-modal-icon">
              <span className="material-icons ro-report-modal-ico">warning</span>
            </div>
            <h2 className="credit-modal__title">AI 오탐지/미탐지 신고</h2>
            <p className="credit-modal__desc ro-report-desc">
              AI가 개인정보를 놓쳤거나 잘못 가렸나요?<br />
              어떤 부분이 잘못되었는지 알려주시면 AI 개선에 큰 도움이 됩니다.
            </p>
            <textarea
              value={reportDesc}
              onChange={(e) => setReportDesc(e.target.value)}
              placeholder="예: 오른쪽 하단의 사람 얼굴이 마스킹되지 않았습니다."
              className="ro-report-textarea"
            />
            <div className="credit-modal__actions ro-report-actions">
              <button className="mui-btn mui-btn--outlined" onClick={() => setShowReportModal(false)}>취소</button>
              <button className="mui-btn mui-btn--contained mui-btn--error" onClick={handleReportSubmit} disabled={!reportDesc.trim() || reportLoading}>
                {reportLoading ? "제출 중..." : "신고 접수"}
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="opt-page">
        {/* 툴바 */}
        <div className="opt-toolbar">
          <Link to="/analysis-report" state={{ jobId }} className="gh__icon opt-back-icon">
            <span className="material-icons">arrow_back</span>
          </Link>
          <div className="opt-flex-1">
            <h1>상세보기 · {isVideo ? "영상" : "이미지"}</h1>
          </div>
          <span className="meta">{total}건 탐지</span>
        </div>

        {/* 이미지/영상 분기 뷰 */}
        {isVideo ? (
          <VideoDetailView
            jobId={jobId}
            detections={detections}
            timelineMarkers={timelineMarkers}
            selected={selected}
            onToggle={toggleSelection}
            onSelectAll={onSelectAll}
            navigate={navigate}
            onPreview={() => navigate("/preview", { state: { jobId, summary } })}
            setShowReportModal={setShowReportModal}
          />
        ) : (
          <ImageDetailView
            jobId={jobId}
            detections={detections}
            selected={selected}
            onToggle={toggleSelection}
            onSelectAll={onSelectAll}
            setShowReportModal={setShowReportModal}
          />
        )}

        <div className="opt-footer">
          <div className="est ro-est-hidden">
            선택된 항목 <strong>{selectedCount}건</strong> / 전체 {total}건
          </div>
          {summary?.job_type === "mask_final" ? (
            <div className="ro-est-row">
              <Link to="/dashboard" className="mui-btn mui-btn--text">대시보드 이동</Link>
              {/* 대시보드/히스토리에서 상세 버튼으로 진입한 경우에만 구간다운로드 이동 버튼 표시 */}
              {fromDashboard && (
                <button
                  type="button"
                  className="mui-btn mui-btn--outlined"
                  onClick={() => navigate("/result", {
                    state: {
                      jobId,
                      fileType: sourceType === "video" ? "video" : "image",
                      fromCropDownload: true,
                    },
                  })}
                >
                  <span className="material-icons ro-crop-ico">crop</span>
                  구간다운로드 이동
                </button>
              )}
            </div>
          ) : (
            <Link to="/analysis-report" state={{ jobId }} className="mui-btn mui-btn--text">이전으로</Link>
          )}
          <button
            type="button"
            className="mui-btn mui-btn--contained mui-btn--lg"
            onClick={() => handleSaveAndNext(isVideo ? "/result" : "/preview")}
            disabled={saving || selectedCount === 0}
          >
            <span className="material-icons opt-mute-icon">
              {isVideo ? "play_circle" : "visibility"}
            </span>
            {saving ? "저장 중…" : isVideo ? "처리진행" : "미리보기 생성"}
          </button>
        </div>
      </div>
    </GarimPage>
  );
}
