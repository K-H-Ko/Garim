/*
코드 설명:
원본/마스킹 이미지·영상을 좌우로 겹쳐 드래그로 비교하는 가림바 슬라이더 컴포넌트.
영상 모드에서는 원본 재생에 맞춰 마스킹 영상을 시점 동기화한다.
*/
import { useEffect, useRef, useState } from "react";
import "../../css/components/ComparisonSlider.css";

/**
 * 가림바 비교 슬라이더 — 이미지/영상 공통
 *
 * props:
 *   mode        "image" | "video"  — 렌더링 방식 결정
 *   originalSrc  원본 파일 URL
 *   maskedSrc    마스킹 결과 파일 URL
 */
export default function ComparisonSlider({ mode = "image", originalSrc, maskedSrc }) {
  const [pct, setPct] = useState(50);       // 가림바 위치 (0~100%)
  const containerRef = useRef(null);
  const origVideoRef = useRef(null);
  const maskVideoRef = useRef(null);
  const dragging = useRef(false);

  // ── 드래그 핸들러 ────────────────────────────────────────────────
  const startDrag = (e) => {
    e.preventDefault();
    dragging.current = true;
  };

  const onMove = (clientX) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const newPct = Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100));
    setPct(newPct);
  };

  const stopDrag = () => { dragging.current = false; };

  // 마우스 이벤트
  const handleMouseMove = (e) => onMove(e.clientX);
  // 터치 이벤트 (모바일 대응)
  const handleTouchMove = (e) => { if (e.touches[0]) onMove(e.touches[0].clientX); };

  // ── 영상 동기화 — 원본 timeupdate 시 마스킹 영상도 같은 시점으로 동기화 ────
  const handleTimeUpdate = () => {
    const orig = origVideoRef.current;
    const mask = maskVideoRef.current;
    if (!orig || !mask) return;
    // 0.3초 이상 차이나면 맞춤 (매 프레임 강제 동기는 끊김 유발)
    if (Math.abs(orig.currentTime - mask.currentTime) > 0.3) {
      mask.currentTime = orig.currentTime;
    }
  };

  // 원본 영상 재생 시 마스킹도 재생
  const handlePlay = () => { maskVideoRef.current?.play().catch(() => { }); };
  const handlePause = () => { maskVideoRef.current?.pause(); };

  // 원본 URL 변경 시 슬라이더 위치 초기화
  useEffect(() => {
    let timer = setTimeout(() => setPct(50), 0);
    return () => clearTimeout(timer);
  }, [originalSrc]);

  return (
    <div
      ref={containerRef}
      className="cs-container"
      onMouseMove={handleMouseMove}
      onMouseUp={stopDrag}
      onMouseLeave={stopDrag}
      onTouchMove={handleTouchMove}
      onTouchEnd={stopDrag}
    >
      {/* ── 원본 레이어 (하단, 전체 표시) ── */}
      <div className="cs-layer cs-original">
        {mode === "image" ? (
          <img src={originalSrc} alt="원본" draggable={false} />
        ) : (
          <video
            ref={origVideoRef}
            src={originalSrc}
            controls
            onTimeUpdate={handleTimeUpdate}
            onPlay={handlePlay}
            onPause={handlePause}
          />
        )}
      </div>

      {/* ── 마스킹 레이어 (상단, clip-path로 오른쪽만 보임) ── */}
      <div
        className="cs-layer cs-masked"
        style={{ clipPath: `inset(0 0 ${mode === "video" ? "60px" : "0"} ${pct}%)` }}
      >
        {mode === "image" ? (
          <img src={maskedSrc} alt="마스킹" draggable={false} />
        ) : (
          <video
            ref={maskVideoRef}
            src={maskedSrc}
            muted
            /* 마스킹 영상 포인터 이벤트는 CSS(.cs-masked video)에서 차단 */
          />
        )}
      </div>

      {/* ── 가림바 핸들 ── */}
      <div
        className="cs-handle"
        style={{ left: `${pct}%` }}
        onMouseDown={startDrag}
        onTouchStart={startDrag}
      >
        <div className="cs-grip">
          <span className="material-icons">drag_indicator</span>
        </div>
      </div>

      {/* ── 라벨 배지 ── */}
      <span className="cs-badge cs-badge--before">원본</span>
      <span className="cs-badge cs-badge--after">마스킹</span>
    </div>
  );
}
