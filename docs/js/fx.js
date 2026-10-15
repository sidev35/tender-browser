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
  if (!hasMouse) return;
  setupCursorGlow();
  setupSpotlightAndTilt();
  setupMagnetic();
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
