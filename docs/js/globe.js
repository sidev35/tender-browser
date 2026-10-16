// Region picker: a globe button in the controls opens an interactive Earth.
// Pick a region on the globe (or in the list) and it zooms in, showing that
// region's countries; pick a country and it becomes the active filter chip.
//
// Only India and Australia have tender data today. Choosing any country calls
// onChange(country): the dashboard then shows that country's tenders, or its
// "no tenders yet" page when there are none. The globe itself loads lazily from a
// CDN (d3-geo + world-atlas); if that fails the lists still work.

const D3_GEO = 'https://cdn.jsdelivr.net/npm/d3-geo@3.1.1/+esm';
const TOPOJSON = 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/+esm';
const WORLD = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';

const LIVE = new Set(['India', 'Australia']);

// Region -> countries, by the names used in the world-atlas data.
const REGIONS = {
  asia: { name: 'Asia', color: '#fb923c', view: { lon: 90, lat: 30, zoom: 1.9 }, blurb: 'South, East & Central Asia', countries: ['India', 'China', 'Japan', 'South Korea', 'North Korea', 'Taiwan', 'Mongolia', 'Pakistan', 'Bangladesh', 'Sri Lanka', 'Nepal', 'Bhutan', 'Afghanistan', 'Kazakhstan', 'Uzbekistan', 'Turkmenistan', 'Kyrgyzstan', 'Tajikistan', 'Myanmar', 'Thailand', 'Vietnam', 'Laos', 'Cambodia', 'Malaysia', 'Brunei', 'Indonesia', 'Philippines', 'Timor-Leste', 'Armenia', 'Azerbaijan', 'Georgia'] },
  middleeast: { name: 'Middle East', color: '#f472b6', view: { lon: 46, lat: 28, zoom: 3.1 }, blurb: 'Gulf, Levant & Iran', countries: ['Saudi Arabia', 'United Arab Emirates', 'Qatar', 'Kuwait', 'Oman', 'Yemen', 'Iraq', 'Iran', 'Syria', 'Jordan', 'Lebanon', 'Israel', 'Palestine', 'Turkey', 'Cyprus', 'N. Cyprus'] },
  africa: { name: 'Africa', color: '#facc15', view: { lon: 20, lat: 2, zoom: 1.7 }, blurb: 'North, West, East & Southern Africa', countries: ['South Africa', 'Egypt', 'Nigeria', 'Kenya', 'Ethiopia', 'Tanzania', 'Uganda', 'Ghana', 'Morocco', 'Algeria', 'Tunisia', 'Libya', 'Sudan', 'S. Sudan', 'Somalia', 'Somaliland', 'Eritrea', 'Djibouti', 'Rwanda', 'Burundi', 'Dem. Rep. Congo', 'Congo', 'Angola', 'Zambia', 'Zimbabwe', 'Mozambique', 'Malawi', 'Botswana', 'Namibia', 'Lesotho', 'eSwatini', 'Madagascar', 'Cameroon', 'Central African Rep.', 'Chad', 'Niger', 'Mali', 'Burkina Faso', 'Senegal', 'Gambia', 'Guinea', 'Guinea-Bissau', 'Sierra Leone', 'Liberia', "Côte d'Ivoire", 'Togo', 'Benin', 'Mauritania', 'W. Sahara', 'Gabon', 'Eq. Guinea'] },
  europe: { name: 'Europe', color: '#60a5fa', view: { lon: 18, lat: 52, zoom: 2.6 }, blurb: 'EU, UK, Nordics & beyond', countries: ['United Kingdom', 'Ireland', 'France', 'Germany', 'Austria', 'Switzerland', 'Italy', 'Spain', 'Portugal', 'Netherlands', 'Belgium', 'Luxembourg', 'Denmark', 'Norway', 'Sweden', 'Finland', 'Iceland', 'Poland', 'Czechia', 'Slovakia', 'Hungary', 'Romania', 'Bulgaria', 'Greece', 'Albania', 'Macedonia', 'Serbia', 'Montenegro', 'Kosovo', 'Bosnia and Herz.', 'Croatia', 'Slovenia', 'Ukraine', 'Belarus', 'Moldova', 'Lithuania', 'Latvia', 'Estonia', 'Russia'] },
  namerica: { name: 'North America', color: '#34d399', view: { lon: -100, lat: 42, zoom: 1.8 }, blurb: 'USA, Canada, Mexico & Caribbean', countries: ['United States of America', 'Canada', 'Mexico', 'Greenland', 'Guatemala', 'Belize', 'Honduras', 'El Salvador', 'Nicaragua', 'Costa Rica', 'Panama', 'Cuba', 'Jamaica', 'Haiti', 'Dominican Rep.', 'Bahamas', 'Puerto Rico', 'Trinidad and Tobago'] },
  samerica: { name: 'South America', color: '#a78bfa', view: { lon: -60, lat: -18, zoom: 2.0 }, blurb: 'Andes, Amazon & Patagonia', countries: ['Brazil', 'Argentina', 'Chile', 'Peru', 'Colombia', 'Venezuela', 'Ecuador', 'Bolivia', 'Paraguay', 'Uruguay', 'Guyana', 'Suriname', 'Falkland Is.'] },
  oceania: { name: 'Oceania', color: '#22d3ee', view: { lon: 150, lat: -24, zoom: 2.3 }, blurb: 'Australia, NZ & the Pacific', countries: ['Australia', 'New Zealand', 'Papua New Guinea', 'Fiji', 'Solomon Is.', 'Vanuatu', 'New Caledonia'] },
};
const REGION_OF = {};
for (const [key, r] of Object.entries(REGIONS)) for (const c of r.countries) REGION_OF[c] = key;

const SHORT = { 'United States of America': 'United States', 'Dem. Rep. Congo': 'DR Congo', 'Central African Rep.': 'Central African Republic', 'Dominican Rep.': 'Dominican Republic', 'Eq. Guinea': 'Equatorial Guinea', 'Bosnia and Herz.': 'Bosnia & Herzegovina', 'Macedonia': 'North Macedonia', 'S. Sudan': 'South Sudan', 'W. Sahara': 'Western Sahara', 'Solomon Is.': 'Solomon Islands', 'Falkland Is.': 'Falkland Islands', 'N. Cyprus': 'Northern Cyprus', 'eSwatini': 'Eswatini' };
const label = (c) => SHORT[c] || c;

// Globe colours for the dark (night) and light (day) themes.
const NIGHT = { halo: 'rgba(56,189,248,.32)', sea: ['#1d4f7a', '#0f2f52', '#071a33'], grat: 'rgba(125,211,252,.10)', land: '#27405e', edge: 'rgba(7,26,51,.55)', edgeHi: 'rgba(7,26,51,.85)', mark: '255,255,255', shade: 'rgba(2,8,20,.55)', rim: 'rgba(125,211,252,.55)' };
const LIGHT = { halo: 'rgba(56,189,248,.38)', sea: ['#d7eefc', '#a9d8f4', '#78bce6'], grat: 'rgba(20,90,150,.14)', land: '#c9d8e6', edge: 'rgba(255,255,255,.75)', edgeHi: 'rgba(255,255,255,.95)', mark: '11,100,160', shade: 'rgba(30,90,150,.28)', rim: 'rgba(30,130,200,.55)' };

const ICON_GLOBE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9.2"/><path d="M2.8 12h18.4"/><path d="M4.4 7.2h15.2M4.4 16.8h15.2" opacity=".55"/><ellipse class="meridian" cx="12" cy="12" rx="4.4" ry="9.2"/></svg>';
const ICON_BACK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>';
const ICON_X = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

// opts.country: the country the dashboard starts on; opts.onChange(country): called when one is picked.
// Returns { choose(country) } so other parts of the page (the empty state) can switch country too.
export function initGlobe({ country = 'India', onChange = () => {} } = {}) {
  const btn = document.getElementById('geoBtn');
  const chips = document.getElementById('geoChips');
  if (!btn || !chips) return null;

  btn.innerHTML = ICON_GLOBE;

  // The active filter: { country, region, live }.
  let active = { country, region: REGION_OF[country] || 'asia', live: LIVE.has(country) };

  function paintChips() {
    const r = REGIONS[active.region];
    chips.innerHTML = '';
    const chip = document.createElement('span');
    chip.className = 'geo-chip' + (active.live ? '' : ' preview');
    chip.style.setProperty('--rc', r.color);
    chip.innerHTML = `<i class="geo-dot"></i><span class="geo-chip-region">${r.name}</span><span class="geo-chip-sep">›</span><strong>${label(active.country)}</strong>${active.live ? '' : '<em>no tenders yet</em>'}`;
    const x = document.createElement('button');
    x.type = 'button'; x.className = 'geo-chip-x'; x.innerHTML = ICON_X;
    x.title = 'Clear the location filter'; x.setAttribute('aria-label', 'Clear the location filter');
    x.addEventListener('click', () => choose('India', true));
    chip.appendChild(x);
    chips.appendChild(chip);
  }

  function choose(country, silentClose) {
    active = { country, region: REGION_OF[country] || 'asia', live: LIVE.has(country) };
    paintChips();
    onChange(country);
    if (!silentClose) close();
  }

  paintChips();

  // --- Modal --------------------------------------------------------------
  const root = document.createElement('div');
  root.className = 'geo-modal';
  root.hidden = true;
  root.innerHTML = `
    <div class="geo-backdrop" data-close></div>
    <div class="geo-panel" role="dialog" aria-modal="true" aria-label="Choose a region">
      <button class="geo-close" type="button" data-close aria-label="Close">${ICON_X}</button>
      <div class="geo-stage">
        <canvas class="geo-canvas"></canvas>
        <div class="geo-loading"><span class="geo-spinner"></span>Loading the globe…</div>
        <div class="geo-hint"><span>Drag to spin</span><span>·</span><span>Click a region</span></div>
        <div class="geo-tag" hidden></div>
      </div>
      <div class="geo-side">
        <div class="geo-crumbs"><button class="geo-back" type="button" hidden>${ICON_BACK}<span>World</span></button><h2 class="geo-title">Explore regions</h2></div>
        <p class="geo-sub">Pick a region, then a country to filter tenders by location.</p>
        <input class="geo-search" type="search" placeholder="Search countries…" hidden>
        <div class="geo-list"></div>
      </div>
    </div>`;
  document.body.appendChild(root);

  const $ = (s) => root.querySelector(s);
  const canvas = $('.geo-canvas'), stage = $('.geo-stage'), loading = $('.geo-loading');
  const tag = $('.geo-tag'), list = $('.geo-list'), title = $('.geo-title'), sub = $('.geo-sub');
  const back = $('.geo-back'), search = $('.geo-search'), hint = $('.geo-hint');

  const view = { level: 'world', region: null, hoverRegion: null, hoverCountry: null };
  let globe = null; // set once d3 + the map data have loaded
  let open = false;

  // ----- Lists -----
  function renderList() {
    list.classList.remove('swap'); void list.offsetWidth; list.classList.add('swap');
    list.innerHTML = '';
    if (view.level === 'world') {
      title.textContent = 'Explore regions';
      sub.textContent = 'Pick a region, then a country to filter tenders by location.';
      back.hidden = true; search.hidden = true;
      Object.entries(REGIONS).forEach(([key, r], i) => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'geo-region'; b.style.setProperty('--rc', r.color); b.style.setProperty('--i', i);
        b.innerHTML = `<i class="geo-swatch"></i><span class="geo-region-txt"><strong>${r.name}</strong><small>${r.blurb}</small></span><span class="geo-count">${r.countries.length}</span>`;
        b.addEventListener('pointerenter', () => { view.hoverRegion = key; });
        b.addEventListener('pointerleave', () => { view.hoverRegion = null; });
        b.addEventListener('click', () => enterRegion(key));
        list.appendChild(b);
      });
    } else {
      const r = REGIONS[view.region];
      title.textContent = r.name;
      sub.textContent = `${r.countries.length} countries · pick one to add it as a filter.`;
      back.hidden = false; search.hidden = false; search.value = '';
      paintCountries('');
    }
  }

  function paintCountries(q) {
    const r = REGIONS[view.region];
    list.innerHTML = '';
    const names = [...r.countries].sort((a, b) => (LIVE.has(b) - LIVE.has(a)) || label(a).localeCompare(label(b)));
    const shown = names.filter((c) => label(c).toLowerCase().includes(q.trim().toLowerCase()));
    shown.forEach((c, i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'geo-country' + (active.country === c ? ' picked' : '');
      b.style.setProperty('--rc', r.color); b.style.setProperty('--i', i);
      b.innerHTML = `<i class="geo-swatch"></i><span>${label(c)}</span>${LIVE.has(c) ? '<em class="geo-live">Live data</em>' : '<em class="geo-soon">Soon</em>'}`;
      b.addEventListener('pointerenter', () => { view.hoverCountry = c; });
      b.addEventListener('pointerleave', () => { view.hoverCountry = null; });
      b.addEventListener('click', () => choose(c));
      list.appendChild(b);
    });
    if (!shown.length) list.innerHTML = '<p class="geo-none">No country matches.</p>';
  }
  search.addEventListener('input', () => paintCountries(search.value));

  function enterRegion(key) {
    view.level = 'region'; view.region = key; view.hoverRegion = null; view.hoverCountry = null;
    renderList();
    root.classList.add('zoomed');
    hint.hidden = true;
    if (globe) globe.flyTo(REGIONS[key].view);
  }
  function leaveRegion() {
    view.level = 'world'; view.region = null; view.hoverCountry = null;
    renderList();
    root.classList.remove('zoomed');
    hint.hidden = false;
    if (globe) globe.flyTo({ zoom: 1 });
  }
  back.addEventListener('click', leaveRegion);

  // ----- Open / close -----
  function openModal() {
    if (open) return;
    open = true;
    view.level = 'world'; view.region = null; view.hoverRegion = null; view.hoverCountry = null;
    root.classList.remove('zoomed'); hint.hidden = false;
    renderList();
    root.hidden = false;
    requestAnimationFrame(() => root.classList.add('on'));
    document.addEventListener('keydown', onKey);
    document.documentElement.classList.add('geo-open');
    ensureGlobe().then(() => { if (open && globe) globe.start(); });
  }
  function close() {
    if (!open) return;
    open = false;
    root.classList.remove('on');
    document.removeEventListener('keydown', onKey);
    document.documentElement.classList.remove('geo-open');
    if (globe) globe.stop();
    setTimeout(() => { if (!open) root.hidden = true; }, 320);
    btn.focus({ preventScroll: true });
  }
  function onKey(e) {
    if (e.key !== 'Escape') return;
    if (view.level === 'region') leaveRegion(); else close();
  }
  btn.addEventListener('click', openModal);
  root.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) close(); });

  // ----- The globe (lazy) -----
  let loadPromise = null;
  function ensureGlobe() {
    if (globe) return Promise.resolve();
    if (!loadPromise) {
      loadPromise = Promise.all([import(D3_GEO), import(TOPOJSON), fetch(WORLD).then((r) => r.json())])
        .then(([d3, topo, world]) => {
          globe = buildGlobe(d3, topo.feature(world, world.objects.countries).features);
          loading.hidden = true;
        })
        .catch((e) => {
          console.warn('Globe could not load; showing the lists only.', e);
          loading.innerHTML = 'The globe needs an internet connection.<br>You can still pick from the list.';
          loadPromise = null;
        });
    }
    return loadPromise;
  }

  function buildGlobe(d3, features) {
    const ctx = canvas.getContext('2d');
    const projection = d3.geoOrthographic().clipAngle(90).precision(0.4);
    const path = d3.geoPath(projection, ctx);
    const graticule = d3.geoGraticule10();
    const sphere = { type: 'Sphere' };
    const feats = features.map((f) => ({ f, name: f.properties.name, region: REGION_OF[f.properties.name] || null }));
    const liveCentroids = feats.filter((x) => LIVE.has(x.name)).map((x) => ({ name: x.name, c: d3.geoCentroid(x.f) }));
    const cam = { lon: 78, lat: 18, zoom: 1 };
    let W = 0, H = 0, R = 0, raf = 0, last = 0, t = 0, drag = null, tween = null, pointer = null, hover = null;

    function resize() {
      const r = stage.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(1, r.width); H = Math.max(1, r.height);
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      R = Math.min(W, H) / 2 - 14;
    }

    function place() {
      projection.translate([W / 2, H / 2]).scale(R * cam.zoom).rotate([-cam.lon, -cam.lat]);
    }

    function draw() {
      place();
      ctx.clearRect(0, 0, W, H);
      const S = projection.scale(), cx = W / 2, cy = H / 2;
      const P = document.documentElement.getAttribute('data-theme') === 'light' ? LIGHT : NIGHT;

      // Atmosphere halo
      const halo = ctx.createRadialGradient(cx, cy, S * 0.96, cx, cy, S * 1.18);
      halo.addColorStop(0, P.halo); halo.addColorStop(1, 'rgba(56,189,248,0)');
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(cx, cy, S * 1.18, 0, Math.PI * 2); ctx.fill();

      // Ocean
      const sea = ctx.createRadialGradient(cx - S * 0.35, cy - S * 0.4, S * 0.1, cx, cy, S);
      sea.addColorStop(0, P.sea[0]); sea.addColorStop(0.6, P.sea[1]); sea.addColorStop(1, P.sea[2]);
      ctx.beginPath(); path(sphere); ctx.fillStyle = sea; ctx.fill();

      // Graticule
      ctx.beginPath(); path(graticule); ctx.strokeStyle = P.grat; ctx.lineWidth = 0.6; ctx.stroke();

      // Land
      const zoomed = view.level === 'region';
      for (const x of feats) {
        const r = x.region ? REGIONS[x.region] : null;
        let fill = P.land, alpha = 1;
        if (r) {
          const inRegion = zoomed && x.region === view.region;
          const hot = (!zoomed && (view.hoverRegion === x.region || (hover && hover.region === x.region && hover.level === 'world'))) ||
                      (zoomed && inRegion && (view.hoverCountry === x.name || (hover && hover.name === x.name)));
          fill = r.color;
          alpha = zoomed ? (inRegion ? (hot ? 1 : 0.8) : 0.16) : (hot ? 1 : 0.62);
          if (zoomed && inRegion && active.country === x.name) alpha = 1;
        } else alpha = zoomed ? 0.4 : 0.8;
        ctx.beginPath(); path(x.f);
        ctx.globalAlpha = alpha; ctx.fillStyle = fill; ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = zoomed && r && x.region === view.region ? P.edgeHi : P.edge;
        ctx.lineWidth = zoomed && r && x.region === view.region ? 0.9 : 0.5; ctx.stroke();
      }

      // Pulsing markers on the countries that have live data
      for (const m of liveCentroids) {
        const p = projection(m.c);
        if (!p) continue;
        const [lon, lat] = m.c, dist = d3.geoDistance([lon, lat], [cam.lon, cam.lat]);
        if (dist > Math.PI / 2 - 0.05) continue;
        const pulse = (t / 1400 + (m.name === 'India' ? 0 : 0.5)) % 1;
        ctx.beginPath(); ctx.arc(p[0], p[1], 3 + pulse * 16, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${P.mark},${0.8 * (1 - pulse)})`; ctx.lineWidth = 1.5; ctx.stroke();
        ctx.beginPath(); ctx.arc(p[0], p[1], 3.2, 0, Math.PI * 2); ctx.fillStyle = `rgb(${P.mark})`; ctx.fill();
      }

      // Rim light + shading toward the edge
      const shade = ctx.createRadialGradient(cx - S * 0.3, cy - S * 0.35, S * 0.55, cx, cy, S);
      shade.addColorStop(0, 'rgba(0,0,0,0)'); shade.addColorStop(1, P.shade);
      ctx.beginPath(); path(sphere); ctx.fillStyle = shade; ctx.fill();
      ctx.beginPath(); path(sphere); ctx.strokeStyle = P.rim; ctx.lineWidth = 1.2; ctx.stroke();
    }

    function hit(px, py) {
      place();
      const S = projection.scale();
      if (Math.hypot(px - W / 2, py - H / 2) > S) return null;
      const p = projection.invert([px, py]);
      if (!p) return null;
      for (const x of feats) if (x.region && d3.geoContains(x.f, p)) return x;
      return null;
    }

    function updateHover() {
      if (!pointer || drag) { hover = null; tag.hidden = true; canvas.style.cursor = ''; return; }
      const h = hit(pointer.x, pointer.y);
      if (!h) { hover = null; tag.hidden = true; return; }
      hover = { name: h.name, region: h.region, level: view.level };
      const r = REGIONS[h.region];
      tag.hidden = false;
      tag.style.setProperty('--rc', r.color);
      tag.style.transform = `translate(${Math.min(W - 150, pointer.x + 14)}px, ${Math.max(8, pointer.y - 34)}px)`;
      tag.innerHTML = view.level === 'world' ? `<i class="geo-dot"></i>${r.name}` : `<i class="geo-dot"></i>${label(h.name)}${LIVE.has(h.name) ? ' <em>live</em>' : ''}`;
    }

    // Camera animation (shortest way round in longitude)
    function flyTo(to, ms = 1100) {
      const from = { lon: cam.lon, lat: cam.lat, zoom: cam.zoom };
      const goal = { lon: to.lon ?? cam.lon, lat: to.lat ?? cam.lat, zoom: to.zoom ?? cam.zoom };
      let dl = ((goal.lon - from.lon + 540) % 360) - 180;
      tween = { from, goal, dl, t0: performance.now(), ms };
    }
    const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

    function frame(now) {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(48, now - (last || now)); last = now; t += dt;
      if (tween) {
        const k = Math.min(1, (now - tween.t0) / tween.ms), e = ease(k);
        cam.lon = tween.from.lon + tween.dl * e;
        cam.lat = tween.from.lat + (tween.goal.lat - tween.from.lat) * e;
        cam.zoom = tween.from.zoom + (tween.goal.zoom - tween.from.zoom) * e;
        if (k >= 1) tween = null;
      } else if (view.level === 'world' && !drag && !hover && !view.hoverRegion) {
        cam.lon += dt * 0.011; // idle spin
      }
      if (cam.lon > 180) cam.lon -= 360; if (cam.lon < -180) cam.lon += 360;
      if (pointer && !drag) updateHover();
      draw();
    }

    // Pointer: drag to spin, click to pick
    canvas.addEventListener('pointerdown', (e) => {
      canvas.setPointerCapture(e.pointerId);
      const r = canvas.getBoundingClientRect();
      drag = { x: e.clientX, y: e.clientY, lon: cam.lon, lat: cam.lat, moved: false, ox: e.clientX - r.left, oy: e.clientY - r.top };
      tween = null; tag.hidden = true;
    });
    canvas.addEventListener('pointermove', (e) => {
      const r = canvas.getBoundingClientRect();
      pointer = { x: e.clientX - r.left, y: e.clientY - r.top };
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      if (drag.moved) {
        const k = 0.35 / cam.zoom;
        cam.lon = drag.lon - dx * k;
        cam.lat = Math.max(-80, Math.min(80, drag.lat + dy * k));
        canvas.style.cursor = 'grabbing';
      }
    });
    canvas.addEventListener('pointerup', (e) => {
      const d = drag; drag = null;
      canvas.style.cursor = '';
      if (!d || d.moved) return;
      const h = hit(d.ox, d.oy);
      if (!h) return;
      if (view.level === 'world') enterRegion(h.region);
      else if (h.region !== view.region) enterRegion(h.region);
      else choose(h.name);
    });
    canvas.addEventListener('pointerleave', () => { pointer = null; hover = null; tag.hidden = true; });
    canvas.addEventListener('wheel', (e) => {
      if (view.level !== 'world') return;
      e.preventDefault();
      cam.zoom = Math.max(0.8, Math.min(1.5, cam.zoom - e.deltaY * 0.0008));
    }, { passive: false });

    new ResizeObserver(() => { if (open) resize(); }).observe(stage);

    return {
      start() { resize(); cam.zoom = view.level === 'world' ? 1 : cam.zoom; last = 0; cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); },
      stop() { cancelAnimationFrame(raf); },
      flyTo,
    };
  }

  return { choose };
}
