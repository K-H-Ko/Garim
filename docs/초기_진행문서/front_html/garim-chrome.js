/* Garim shared header/footer chrome.
   Each page calls renderHeader/renderFooter in its <script>. */

function gh(opts) {
  const o = Object.assign({ variant: 'public', current: '', authed: false, admin: false }, opts || {});

  if (o.admin) {
    return `
<header class="gh gh--admin">
  <div class="gh__logo"><img src="logo.svg" alt="Garim" style="filter:brightness(0) invert(1);"></div>
  <span class="overline-k" style="color:rgba(255,255,255,0.5);margin-left:12px;letter-spacing:1.5px;">ADMIN</span>
  <div class="spacer"></div>
  <div class="gh__right">
    <button class="gh__icon" title="알림" style="color:#fff;"><span class="material-icons">notifications</span></button>
    <div class="gh__avatar" style="background:#1976d2;">A</div>
  </div>
</header>`;
  }

  if (o.variant === 'minimal') {
    return `
<header class="gh gh--minimal">
  <a href="01-landing.html" class="gh__logo"><img src="logo.svg" alt="Garim"></a>
</header>`;
  }

  const nav = [
    ['detect', '검출하기', '08-upload.html'],
    ['sns', 'SNS 점검', '11-sns-connect.html'],
    ['pricing', '요금제', '02-pricing.html'],
    ['help', '도움말', '03-faq.html'],
  ].map(([id, label, href]) =>
    `<a href="${href}" class="${o.current === id ? 'active' : ''}">${label}</a>`
  ).join('');

  const right = o.authed ? `
    <button class="gh__icon" title="검색"><span class="material-icons">search</span></button>
    <span class="gh__icon-wrap">
      <button class="gh__icon" title="알림"><span class="material-icons">notifications</span></button>
      <span class="gh__badge">2</span>
    </span>
    <a href="19-dashboard.html" class="gh__avatar" title="마이페이지">M</a>
  ` : `
    <a href="06-login.html" class="mui-btn mui-btn--text">로그인</a>
    <a href="05-signup.html" class="mui-btn mui-btn--contained mui-btn--sm">무료로 시작</a>
  `;

  return `
<header class="gh ${o.variant === 'app' ? 'gh--app' : ''} ${o.variant === 'landing' ? 'gh--landing' : ''}">
  <a href="${o.authed ? '19-dashboard.html' : '01-landing.html'}" class="gh__logo"><img src="logo.svg" alt="Garim"></a>
  <nav class="gh__nav">${nav}</nav>
  <div class="gh__right">${right}</div>
</header>`;
}

function gf(opts) {
  const o = Object.assign({ minimal: false }, opts || {});
  if (o.minimal) {
    return `
<footer class="gf" style="padding:16px 32px;">
  <div class="gf__bottom" style="border:0;margin:0;">
    <span>© 2026 Garim, Inc.</span>
    <span><a href="04-terms.html">이용약관</a> · <a href="04-terms.html">개인정보처리방침</a></span>
  </div>
</footer>`;
  }
  return `
<footer class="gf">
  <div class="gf__inner">
    <div class="gf__brand">
      <img src="logo.svg" alt="Garim" style="height:24px;">
      <p>AI 기반 멀티모달 개인정보 도싱 방지 및 데이터 치환 엔진. 영상·이미지·음성 속 개인정보를 검출하고 자연스럽게 가립니다.</p>
    </div>
    <div class="gf__col">
      <h4>제품</h4>
      <a href="08-upload.html">파일 검출하기</a>
      <a href="11-sns-connect.html">SNS 점검</a>
      <a href="02-pricing.html">요금제</a>
    </div>
    <div class="gf__col">
      <h4>지원</h4>
      <a href="03-faq.html">FAQ·도움말</a>
      <a href="mailto:support@garim.kr">문의하기</a>
      <a href="03-faq.html">처리 사양 안내</a>
    </div>
    <div class="gf__col">
      <h4>법적 고지</h4>
      <a href="04-terms.html">이용약관</a>
      <a href="04-terms.html">개인정보처리방침</a>
      <a href="04-terms.html">AI 학습 데이터 정책</a>
    </div>
  </div>
  <div class="gf__bottom">
    <span>© 2026 Garim, Inc. · garim.kr</span>
    <span>made in Seoul</span>
  </div>
</footer>`;
}

window.gh = gh;
window.gf = gf;
