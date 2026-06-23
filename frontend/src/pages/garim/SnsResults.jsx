import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/SnsResults.css";

import GarimPage from "../../components/garim/GarimPage";

export default function SnsResults() {
  useDocumentTitle("SNS 진단 결과 · Garim");

  return (
    <GarimPage bodyClass="page-app" screenLabel="12 SNS results">
      <div className="sr-page">
        <div className="sr-shell">
          <section className="sr-impact">
            <div>
              <span className="overline-k sns-overline">
                ⚠ SNS 셀프 점검 완료
              </span>
              <h1>
                내 인스타에서
                <span className="num">
                  9건
                </span>
                의 위험 게시물이 발견됐어요
              </h1>
              <div className="meta">
                최근 60개 게시물 분석 · 1분 18초 소요 · 마지막 스캔 방금 전
              </div>
            </div>
            <div className="ig-info">
              <div className="ig-avatar">
                <img src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=120&amp;q=60" alt="" />
              </div>
              <div className="ig-text">
                <strong>
                  @mynn_creator
                </strong>
                <small>
                  비즈니스 계정 · 1,247 팔로워
                </small>
              </div>
            </div>
          </section>
          <div className="sr-cats">
            <div className="sr-cat err">
              <div className="lbl">
                택배 송장·주소
              </div>
              <div className="num">
                3
              </div>
            </div>
            <div className="sr-cat err">
              <div className="lbl">
                차량 번호판
              </div>
              <div className="num">
                2
              </div>
            </div>
            <div className="sr-cat warn">
              <div className="lbl">
                지인 얼굴
              </div>
              <div className="num">
                3
              </div>
            </div>
            <div className="sr-cat info">
              <div className="lbl">
                위치 태그·EXIF
              </div>
              <div className="num">
                1
              </div>
            </div>
          </div>
          <div className="v2-placeholder">
            <span className="material-icons">
              trending_up
            </span>
            <div className="sns-flex1">
              <div className="t">
                위험도 추이 — 정기 스캔으로 시각화 (v2)
              </div>
              <div className="s">
                자동 스캔이 활성화되면 매주 위험도 추이 그래프를 볼 수 있습니다.
              </div>
            </div>
            <span className="mui-chip">
              v2 예정
            </span>
          </div>
          <div className="sr-grid">
            <div className="sr-main">
              <div className="sr-toolbar">
                <span className="label">
                  정렬:
                </span>
                <button className="mui-btn mui-btn--text mui-btn--sm">
                  위험도순 ↓
                </button>
                <span className="label sns-label-ml">
                  필터:
                </span>
                <span className="mui-chip mui-chip--primary mui-chip--md">
                  전체 9
                </span>
                <span className="mui-chip mui-chip--outlined mui-chip--md">
                  위험 5
                </span>
                <span className="mui-chip mui-chip--outlined mui-chip--md">
                  주의 4
                </span>
                <div className="sns-flex1">
                </div>
                <span className="caption-k">
                  9건 / 60개 게시물
                </span>
              </div>
              <div className="post-grid">
                <div className="post-card">
                  <div className="thumb">
                    <img src="https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=400&amp;q=60" alt="" />
                    <svg viewBox="0 0 400 400" preserveAspectRatio="none" className="sns-svg">
                      <rect x="80" y="120" width="240" height="160" fill="none" stroke="#d32f2f" strokeWidth="3" />
                    </svg>
                    <span className="mui-chip mui-chip--error risk-badge">
                      위험 8.4
                    </span>
                    <span className="date">
                      2026.04.12
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      새 책상 도착 ‼ 박스 그대로 풀어봤어요
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-error sns-chip">
                        송장
                      </span>
                      <span className="mui-chip mui-chip--soft-warning sns-chip">
                        주소
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
                <div className="post-card">
                  <div className="thumb">
                    <img src="https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=400&amp;q=60" alt="" />
                    <svg viewBox="0 0 400 400" preserveAspectRatio="none" className="sns-svg">
                      <rect x="180" y="100" width="80" height="80" fill="none" stroke="#ed6c02" strokeWidth="3" />
                      <rect x="80" y="180" width="80" height="80" fill="none" stroke="#ed6c02" strokeWidth="3" />
                    </svg>
                    <span className="mui-chip mui-chip--warning risk-badge">
                      주의 6.7
                    </span>
                    <span className="date">
                      2026.03.28
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      우리 가족 주말 피크닉 🌳
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-warning sns-chip">
                        얼굴 3명
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
                <div className="post-card">
                  <div className="thumb sns-thumb-video">
                    <span className="material-icons sns-video-ico">
                      directions_car
                    </span>
                    <span className="mui-chip mui-chip--error risk-badge">
                      위험 7.8
                    </span>
                    <span className="date">
                      2026.03.15
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      새 차 출고 기념 🚗 우리 동네에서
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-error sns-chip">
                        번호판
                      </span>
                      <span className="mui-chip mui-chip--soft-info sns-chip">
                        위치 태그
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
                <div className="post-card">
                  <div className="thumb">
                    <img src="https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=400&amp;q=60" alt="" />
                    <svg viewBox="0 0 400 400" preserveAspectRatio="none" className="sns-svg">
                      <rect x="100" y="160" width="200" height="80" fill="none" stroke="#d32f2f" strokeWidth="3" />
                    </svg>
                    <span className="mui-chip mui-chip--error risk-badge">
                      위험 8.2
                    </span>
                    <span className="date">
                      2026.02.21
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      주말 배달 도착! 컵라면 한 박스
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-error sns-chip">
                        송장
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
                <div className="post-card">
                  <div className="thumb">
                    <img src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&amp;q=60" alt="" />
                    <svg viewBox="0 0 400 400" preserveAspectRatio="none" className="sns-svg">
                      <rect x="160" y="80" width="100" height="100" fill="none" stroke="#ed6c02" strokeWidth="3" />
                    </svg>
                    <span className="mui-chip mui-chip--warning risk-badge">
                      주의 5.9
                    </span>
                    <span className="date">
                      2026.02.10
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      절친이랑 카페 데이트 ☕
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-warning sns-chip">
                        얼굴
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
                <div className="post-card">
                  <div className="thumb">
                    <img src="https://images.unsplash.com/photo-1521295121783-8a321d551ad2?w=400&amp;q=60" alt="" />
                    <svg viewBox="0 0 400 400" preserveAspectRatio="none" className="sns-svg">
                      <rect x="240" y="220" width="120" height="60" fill="none" stroke="#ed6c02" strokeWidth="3" />
                    </svg>
                    <span className="mui-chip mui-chip--warning risk-badge">
                      주의 6.4
                    </span>
                    <span className="date">
                      2026.01.30
                    </span>
                  </div>
                  <div className="body">
                    <div className="desc">
                      집 근처 산책로 발견! 너무 좋네요
                    </div>
                    <div className="tags">
                      <span className="mui-chip mui-chip--soft-warning sns-chip">
                        번호판
                      </span>
                    </div>
                    <a href="/replace-options" className="mui-btn mui-btn--contained mui-btn--sm mui-btn--block">
                      처리하기
                    </a>
                  </div>
                </div>
              </div>
              <div className="sns-card-foot">
                위험 게시물 6/9 표시 중 ·
                <a href="#" className="sns-link">
                  3건 더 보기
                </a>
                · 안전 게시물 51개는 숨겨져 있습니다
              </div>
            </div>
            <aside className="side">
              <div className="side-card guide-card">
                <h3>
                  처리 후 흐름 — 직접 해야 하는 일
                </h3>
                <p className="caption-k sns-sub">
                  Garim은 인스타에 자동 게시·삭제를 하지 않습니다 (B-2 권한 정책).
                </p>
                <div className="guide-step">
                  <span className="n">
                    1
                  </span>
                  <div>
                    <div className="t">
                      게시물 "처리하기" 클릭
                    </div>
                    <div className="s">
                      치환 옵션 → 미리보기 → 결과 다운로드
                    </div>
                  </div>
                </div>
                <div className="guide-step">
                  <span className="n">
                    2
                  </span>
                  <div>
                    <div className="t">
                      인스타에서 기존 게시물 삭제
                    </div>
                    <div className="s">
                      앱·웹에서 직접 삭제하세요
                    </div>
                  </div>
                </div>
                <div className="guide-step">
                  <span className="n">
                    3
                  </span>
                  <div>
                    <div className="t">
                      새 버전 업로드
                    </div>
                    <div className="s">
                      캡션·해시태그 그대로 유지 권장
                    </div>
                  </div>
                </div>
              </div>
              <div className="side-card">
                <h3>
                  연결 상태
                </h3>
                <div className="row sns-row-gap">
                  <span className="material-icons sns-ico-ok">
                    check_circle
                  </span>
                  <div>
                    <div className="body2-k sns-item-title">
                      @mynn_creator
                    </div>
                    <div className="caption-k sns-cap-11">
                      연결됨 · 토큰 만료 60일 후
                    </div>
                  </div>
                </div>
                <button className="mui-btn mui-btn--text mui-btn--sm sns-del-btn">
                  연결 해제 →
                </button>
              </div>
              <div className="side-card sns-card-dim">
                <h3>
                  정기 자동 스캔
                </h3>
                <div className="row sns-row-between">
                  <span className="body2-k">
                    매주 자동 점검
                  </span>
                  <span className="mui-chip">
                    v2
                  </span>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </GarimPage>
  );
}
