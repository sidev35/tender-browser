// Visual effects that follow the pointer or the scroll: a soft glow under the
// cursor, a spotlight and slight 3D tilt on cards and stat tiles, click
// ripples, magnetic header buttons, and a scroll-progress bar. Purely cosmetic:
// nothing here changes layout, and all of it stays off for visitors who ask
// for reduced motion or who use touch.

const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const hasMouse = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

export function initEffects() {
  setupScrollProgress();
  if (calm) return;
  setupRipples();
  setupSparkBurst();
  setupParticles();
  setupTitleScramble();
  setupTypingPlaceholder();
  setupScrollParallax();
  if (!hasMouse) return;
  setupCursorGlow();
  setupCursorDot();
  setupSpotlightAndTilt();
  setupMagnetic();
}


// A small accent dot that follows the pointer. The native cursor stays: this
// is only decoration.
function setupCursorDot() {
  const dot = document.createElement('div');
  dot.className = 'cursor-dot';
  document.body.appendChild(dot);
  document.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    dot.style.transform = `translate(${e.clientX}px, ${e.clientY}px) translate(-50%, -50%)`;
    dot.classList.add('on');
    document.documentElement.classList.add('no-cursor');
  }, { passive: true });
  document.addEventListener('pointerleave', () => dot.classList.remove('on'));
}

// A drifting network of accent-coloured nodes behind the page. Nodes link up
// when close and are nudged away from the pointer. Pauses with the tab.
function setupParticles() {
  const cv = document.createElement('canvas');
  cv.className = 'fx-canvas';
  document.body.prepend(cv);
  const ctx = cv.getContext('2d');
  let w = 0, h = 0, dpr = 1, accent = '#38bdf8', parts = [];
  const mouse = { x: -999, y: -999 };
  const readAccent = () => { accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || accent; };
  const resize = () => {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    w = window.innerWidth; h = window.innerHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(70, (w * h) / 22000));
    parts = Array.from({ length: n }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.28, vy: (Math.random() - 0.5) * 0.28, r: 1 + Math.random() * 1.6,
    }));
  };
  window.addEventListener('resize', resize);
  window.addEventListener('pointermove', (e) => { mouse.x = e.clientX; mouse.y = e.clientY; }, { passive: true });
  new MutationObserver(readAccent).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  const LINK = 130;
  const frame = () => {
    if (document.hidden) return;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = accent; ctx.strokeStyle = accent;
    for (const p of parts) {
      const dx = p.x - mouse.x, dy = p.y - mouse.y, d2 = dx * dx + dy * dy;
      if (d2 < 150 * 150 && d2 > 1) { const f = (1 - Math.sqrt(d2) / 150) * 0.9; p.vx += (dx / Math.sqrt(d2)) * f * 0.08; p.vy += (dy / Math.sqrt(d2)) * f * 0.08; }
      p.vx *= 0.99; p.vy *= 0.99;
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = w + 10; else if (p.x > w + 10) p.x = -10;
      if (p.y < -10) p.y = h + 10; else if (p.y > h + 10) p.y = -10;
    }
    for (let i = 0; i < parts.length; i++) {
      const a = parts[i];
      for (let j = i + 1; j < parts.length; j++) {
        const b = parts[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 < LINK * LINK) { ctx.globalAlpha = (1 - Math.sqrt(d2) / LINK) * 0.22; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      }
      ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
    }
    requestAnimationFrame(frame);
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) requestAnimationFrame(frame); });
  readAccent(); resize(); requestAnimationFrame(frame);
}

// A burst of little sparks from the click point on pills and header buttons.
function setupSparkBurst() {
  document.addEventListener('pointerdown', (e) => {
    const el = e.target.closest && e.target.closest('.pill, .icon-btn, .stat.clickable, .to-top');
    if (!el) return;
    for (let i = 0; i < 9; i++) {
      const s = document.createElement('span');
      const ang = (Math.PI * 2 * i) / 9 + Math.random() * 0.5, dist = 26 + Math.random() * 28;
      s.className = 'spark';
      s.style.cssText = `left:${e.clientX}px;top:${e.clientY}px;--dx:${(Math.cos(ang) * dist).toFixed(1)}px;--dy:${(Math.sin(ang) * dist).toFixed(1)}px`;
      document.body.appendChild(s);
      s.addEventListener('animationend', () => s.remove());
    }
  });
}

// The page title decodes from random letters once on load.
function setupTitleScramble() {
  const h = document.querySelector('.brand h1');
  if (!h) return;
  const text = h.textContent, glyphs = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789';
  h.style.minWidth = h.offsetWidth + 'px';
  let frame = 0;
  const tick = () => {
    frame++;
    h.textContent = [...text].map((c, i) => (c === ' ' || i < frame / 2 ? c : glyphs[(Math.random() * glyphs.length) | 0])).join('');
    if (frame / 2 < text.length) setTimeout(tick, 35); else h.textContent = text;
  };
  setTimeout(tick, 350);
}

// The search box types out example searches while it is idle and empty.
function setupTypingPlaceholder() {
  const box = document.getElementById('searchBox');
  if (!box) return;
  const base = box.placeholder;
  const phrases = ['EV charger tender…', 'Battery energy storage…', 'Power electronics…', 'Charging station RFP…', base];
  let p = 0, i = 0, dir = 1, timer = 0;
  const idle = () => document.activeElement !== box && !box.value;
  const step = () => {
    if (!idle()) { box.placeholder = base; timer = setTimeout(step, 1500); return; }
    const full = phrases[p];
    i += dir;
    box.placeholder = full.slice(0, i) + (i < full.length || dir < 0 ? '▍' : '');
    let delay = dir > 0 ? 70 : 35;
    if (dir > 0 && i >= full.length) { dir = -1; delay = 1600; }
    else if (dir < 0 && i <= 0) { dir = 1; p = (p + 1) % phrases.length; delay = 350; }
    timer = setTimeout(step, delay);
  };
  box.addEventListener('blur', () => { clearTimeout(timer); timer = setTimeout(step, 800); });
  timer = setTimeout(step, 2500);
}

// Gentle depth on scroll: the header drifts and fades a touch, the aurora lags.
function setupScrollParallax() {
  const root = document.documentElement;
  let raf = 0;
  window.addEventListener('scroll', () => {
    if (raf) return;
    raf = requestAnimationFrame(() => { root.style.setProperty('--scroll', String(window.scrollY)); raf = 0; });
  }, { passive: true });
}

function setupScrollProgress() {
  const bar = document.getElementById('scrollProgress');
  if (!bar) return;
  const update = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    bar.style.transform = `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`;
  };
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  update();
}

// A soft accent glow that trails the cursor, under the page content.
function setupCursorGlow() {
  const glow = document.getElementById('cursorGlow');
  if (!glow) return;
  let x = 0, y = 0, raf = 0;
  window.addEventListener('pointermove', (e) => {
    x = e.clientX; y = e.clientY;
    glow.classList.add('on');
    if (!raf) raf = requestAnimationFrame(() => { glow.style.transform = `translate(${x - 260}px, ${y - 260}px)`; raf = 0; });
  }, { passive: true });
  document.addEventListener('pointerleave', () => glow.classList.remove('on'));
}

// Cards and stat tiles: a spotlight under the cursor (--mx / --my) and, on
// cards, a slight tilt towards it (--rx / --ry, at most 3 degrees).
function setupSpotlightAndTilt() {
  let target = null, raf = 0, ev = null;
  const reset = (el) => { el.style.removeProperty('--rx'); el.style.removeProperty('--ry'); };
  const apply = () => {
    raf = 0;
    if (!ev) return;
    const el = ev.target.closest && ev.target.closest('.card.clickable, .stat');
    if (target && target !== el) reset(target);
    target = el;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = ev.clientX - r.left, py = ev.clientY - r.top;
    el.style.setProperty('--mx', px + 'px');
    el.style.setProperty('--my', py + 'px');
    if (el.classList.contains('card')) {
      el.style.setProperty('--ry', ((px / r.width - 0.5) * 3).toFixed(2) + 'deg');
      el.style.setProperty('--rx', ((0.5 - py / r.height) * 3).toFixed(2) + 'deg');
    }
  };
  document.addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    ev = e;
    if (!raf) raf = requestAnimationFrame(apply);
  }, { passive: true });
  document.addEventListener('pointerleave', () => { if (target) reset(target); target = null; });
}

// A ripple from the click point on pills and buttons.
function setupRipples() {
  document.addEventListener('pointerdown', (e) => {
    const el = e.target.closest && e.target.closest('.pill, .icon-btn, .card-action-btn, .new-toolbar button, .to-top');
    if (!el) return;
    const r = el.getBoundingClientRect();
    const size = Math.max(r.width, r.height) * 2;
    const dot = document.createElement('span');
    dot.className = 'ripple';
    dot.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - r.left - size / 2}px;top:${e.clientY - r.top - size / 2}px`;
    el.appendChild(dot);
    dot.addEventListener('animationend', () => dot.remove());
  });
}

// Header buttons lean a few pixels towards the cursor.
function setupMagnetic() {
  document.querySelectorAll('.top-actions .icon-btn').forEach((btn) => {
    btn.addEventListener('pointermove', (e) => {
      const r = btn.getBoundingClientRect();
      btn.style.setProperty('--tx', ((e.clientX - r.left - r.width / 2) * 0.22).toFixed(1) + 'px');
      btn.style.setProperty('--ty', ((e.clientY - r.top - r.height / 2) * 0.22).toFixed(1) + 'px');
    });
    btn.addEventListener('pointerleave', () => { btn.style.removeProperty('--tx'); btn.style.removeProperty('--ty'); });
  });
}

// Theme switch as a circle growing out of the toggle button (the View
// Transitions API; browsers without it just switch). `change` flips the theme.
export function switchThemeWithReveal(button, change) {
  if (calm || !document.startViewTransition) { change(); return; }
  const r = button.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  const t = document.startViewTransition(change);
  t.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: 650, easing: 'cubic-bezier(.2,.8,.2,1)', pseudoElement: '::view-transition-new(root)' },
    );
  }).catch(() => {});
}
