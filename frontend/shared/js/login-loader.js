/**
 * Smart Waste Segregator — full-screen loading overlay.
 * Pairs with ../css/login-loader.css. Mounts over the current page, drives a
 * forward-only progress bar from real network work, then hands off.
 *
 *   window.showLoginLoader({
 *     user,                 // {username, fullName, avatar} for the welcome line
 *     dest: '/dashboard.html',
 *     admin: false,         // accent + copy variant
 *     register: false,      // copy variant for the signup flow
 *     steps: [...],         // optional override of the default work plan
 *     minMs: 2000, maxMs: 8000,
 *     onDone: fn            // called just before navigation
 *   })
 *
 * Rules: progress never goes backwards; hard-capped so it always navigates;
 * the overlay is never removed by the page itself (navigation replaces it).
 */
(function () {
  'use strict';

  var ID = 'swlOverlay';
  var RING_R = 78;
  var CIRC = 2 * Math.PI * RING_R; // 490.09

  var PARTICLE_COLORS = ['#71dc68', '#2fc5db', '#41cddd', '#65de72', '#44d176', '#6fd779', '#37a968'];

  var reduceMotion = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;

  // ---------------------------------------------------------------- helpers
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    return n;
  }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

  function getJSON(url) {
    return fetch(url, { credentials: 'include', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; }); // never reject: prefetch is best-effort
  }

  // Build the SVG defs: gradients + glow filters.
  function buildDefs() {
    var defs = svg('defs');

    var g1 = svg('linearGradient', { id: 'swlArcGrad', gradientUnits: 'userSpaceOnUse', x1: 22, y1: 22, x2: 178, y2: 178 });
    [['0%', '#9df5ae'], ['22%', '#5ef0a8'], ['48%', '#3cefa2'],
     ['70%', '#2ce79c'], ['88%', '#33dd8c'], ['100%', '#159c5f']]
      .forEach(function (s) {
        var st = svg('stop', { offset: s[0], 'stop-color': s[1] });
        g1.appendChild(st);
      });
    defs.appendChild(g1);

    var gg = svg('linearGradient', { id: 'swlGlyphGrad', gradientUnits: 'userSpaceOnUse', x1: 60, y1: 55, x2: 145, y2: 150 });
    [['0%', '#7cf5b0'], ['55%', '#46e39a'], ['100%', '#2ecf7f']]
      .forEach(function (s) { gg.appendChild(svg('stop', { offset: s[0], 'stop-color': s[1] })); });
    defs.appendChild(gg);

    var lg = svg('linearGradient', { id: 'swlLeafGrad', gradientUnits: 'userSpaceOnUse', x1: 112, y1: 148, x2: 142, y2: 112 });
    [['0%', '#2ecf7f'], ['100%', '#9dffc4']]
      .forEach(function (s) { lg.appendChild(svg('stop', { offset: s[0], 'stop-color': s[1] })); });
    defs.appendChild(lg);

    var tg = svg('radialGradient', { id: 'swlTipGrad' });
    tg.appendChild(svg('stop', { offset: '0%', 'stop-color': '#ffffff', 'stop-opacity': '0.95' }));
    tg.appendChild(svg('stop', { offset: '55%', 'stop-color': '#9dffc4', 'stop-opacity': '0.45' }));
    tg.appendChild(svg('stop', { offset: '100%', 'stop-color': '#34f9de', 'stop-opacity': '0' }));
    defs.appendChild(tg);

    var f1 = svg('filter', { id: 'swlGlow', x: '-40%', y: '-40%', width: '180%', height: '180%' });
    f1.appendChild(svg('feGaussianBlur', { stdDeviation: '2.9', result: 'b' }));
    var m1 = svg('feMerge');
    /* blur is composited at reduced strength: the reference reads as a tight
       neon line with a restrained halo, not a wide bloom */
    var ct = svg('feComponentTransfer', { result: 'bd' });
    ct.appendChild(svg('feFuncA', { type: 'linear', slope: '0.85', intercept: '0' }));
    f1.appendChild(ct);
    m1.appendChild(svg('feMergeNode', { in: 'bd' }));
    m1.appendChild(svg('feMergeNode', { in: 'SourceGraphic' }));
    f1.appendChild(m1);
    defs.appendChild(f1);

    var f2 = svg('filter', { id: 'swlTipBlur', x: '-120%', y: '-120%', width: '340%', height: '340%' });
    f2.appendChild(svg('feGaussianBlur', { stdDeviation: '4' }));
    defs.appendChild(f2);

    return defs;
  }

  // Centre mark: three chasing arrows + leaf (paths computed for r=40, 120deg pitch).
  function buildGlyph() {
    var g = svg('g', { class: 'swl-glyph' });

    var halo = svg('circle', { class: 'swl-halo', cx: 100, cy: 100, r: 40, fill: 'none',
      stroke: '#46e39a', 'stroke-width': 2, opacity: 0.5 });
    g.appendChild(halo);

    var arrows = [
      { a: 'M 135.32 81.22 A 40 40 0 0 1 129.73 126.77',
        h: 'M 116.34 141.63 L 120.81 118.74 L 130.84 115.66 L 140.65 124.49 L 138.64 134.79 Z' },
      { a: 'M 98.60 139.98 A 40 40 0 0 1 61.96 112.36',
        h: 'M 55.78 93.34 L 73.37 108.65 L 71.02 118.88 L 58.46 122.96 L 50.55 116.07 Z' },
      { a: 'M 66.08 78.80 A 40 40 0 0 1 108.32 60.87',
        h: 'M 127.88 65.03 L 105.82 72.61 L 98.14 65.46 L 100.89 52.55 L 110.81 49.14 Z' }
    ];
    arrows.forEach(function (w) {
      g.appendChild(svg('path', { class: 'swl-arrow', d: w.a }));
      g.appendChild(svg('path', { class: 'swl-head', d: w.h }));
    });

    g.appendChild(svg('path', { class: 'swl-leaf', d: 'M 118 146 Q 136 112 140 132 Q 112 132 118 146 Z' }));
    g.appendChild(svg('path', { class: 'swl-leafrib', d: 'M 120 145 Q 125 137 137 128' }));

    return g;
  }

  function buildParticles(host) {
    var frag = document.createDocumentFragment();
    var n = reduceMotion ? 0 : 16;
    for (var i = 0; i < n; i++) {
      var leaf = i % 5 === 0;
      var p = el('i', leaf ? 'swl-p swl-p--leaf' : 'swl-p swl-p--dot');
      var size = leaf ? 18 + Math.random() * 16 : 5 + Math.random() * 8;
      if (leaf) { p.style.width = size + 'px'; p.style.height = size + 'px'; }
      else p.style.width = p.style.height = size.toFixed(1) + 'px';
      p.style.left = (4 + Math.random() * 92).toFixed(1) + '%';
      p.style.setProperty('--swl-c', PARTICLE_COLORS[i % PARTICLE_COLORS.length]);
      p.style.setProperty('--swl-o', (0.35 + Math.random() * 0.5).toFixed(2));
      p.style.setProperty('--swl-dx', ((Math.random() * 14 - 7)).toFixed(1) + 'vw');
      p.style.setProperty('--swl-rot', (Math.round(Math.random() * 2 ? 1 : -1) * (140 + Math.random() * 260)).toFixed(0) + 'deg');
      var dur = 9 + Math.random() * 12;
      p.style.animation = 'swl-float ' + dur.toFixed(1) + 's linear ' + (-Math.random() * dur).toFixed(1) + 's infinite';
      frag.appendChild(p);
    }
    host.appendChild(frag);
  }

  // ---------------------------------------------------------------- markup
  function build(cfg) {
    var ov = el('div', 'swl-overlay' + (cfg.admin ? ' swl-admin' : ''));
    ov.id = ID;
    ov.setAttribute('role', 'alert');
    ov.setAttribute('aria-busy', 'true');
    ov.setAttribute('aria-label', 'Signing you in, please wait');
    if (cfg.variant) ov.setAttribute('data-variant', cfg.variant);

    ov.appendChild(el('div', 'swl-bg'));
    var smoke = el('div', 'swl-smoke');
    smoke.appendChild(el('i')); smoke.appendChild(el('i')); smoke.appendChild(el('i'));
    ov.appendChild(smoke);
    if (cfg.useVideo) ov.appendChild(buildVideo());
    ov.appendChild(el('div', 'swl-particles'));
    ov.appendChild(el('div', 'swl-vignette'));

    var stage = el('div', 'swl-stage');

    // --- ring ---
    var wrap = el('div', 'swl-ringwrap');
    var s = svg('svg', { class: 'swl-ring', viewBox: '0 0 200 200', 'aria-hidden': 'true', focusable: 'false' });
    s.appendChild(buildDefs());
    var dial = svg('g', { class: 'swl-dial' });
    dial.appendChild(svg('circle', { class: 'swl-track', cx: 100, cy: 100, r: RING_R }));
    var arc = svg('circle', { class: 'swl-arc', cx: 100, cy: 100, r: RING_R });
    arc.style.strokeDasharray = '0 ' + CIRC;
    dial.appendChild(arc);
    var tipG = svg('g', { class: 'swl-tipwrap' });
    var tipHalo = svg('circle', { class: 'swl-tipglow', cx: 100, cy: 100 - RING_R, r: 13 });
    var tipDot = svg('circle', { class: 'swl-tip', cx: 100, cy: 100 - RING_R, r: 5 });
    tipG.appendChild(tipHalo); tipG.appendChild(tipDot);
    dial.appendChild(tipG);
    s.appendChild(dial);
    s.appendChild(buildGlyph());
    wrap.appendChild(s);
    stage.appendChild(wrap);

    // --- copy (fixed text; no user data interpolated as HTML) ---
    var title = el('h1', 'swl-title');
    title.appendChild(document.createTextNode('Smart '));
    var wspan = el('span');
    wspan.textContent = 'Waste';
    title.appendChild(wspan);
    title.appendChild(document.createTextNode(' Segregator'));
    stage.appendChild(title);

    stage.appendChild(el('p', 'swl-tag', 'Building a Cleaner, Greener Tomorrow'));

    // --- bar + percentage ---
    var brow = el('div', 'swl-barrow');
    var bar = el('div', 'swl-bar');
    var fill = el('i', 'swl-fill');
    bar.appendChild(fill);
    var pct = el('div', 'swl-pct');
    pct.textContent = '0%';
    pct.setAttribute('aria-hidden', 'true'); // text alternative lives on the bar
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-valuenow', '0');
    bar.setAttribute('aria-label', 'Loading progress');
    brow.appendChild(bar);
    brow.appendChild(pct);
    stage.appendChild(brow);

    // --- status (live region) ---
    var status = el('p', 'swl-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.textContent = cfg.initialStatus;
    stage.appendChild(status);

    var skip = el('button', 'swl-skip', 'Skip');
    skip.type = 'button';
    stage.appendChild(skip);

    ov.appendChild(stage);
    return { root: ov, arc: arc, tipG: tipG, fill: fill, pct: pct, status: status, bar: bar, skip: skip };
  }

  function buildVideo() {
    var v = el('video', 'swl-video');
    v.setAttribute('muted', '');
    v.setAttribute('playsinline', '');
    v.setAttribute('autoplay', '');
    v.setAttribute('loop', '');
    v.setAttribute('aria-hidden', 'true');
    v.setAttribute('poster', '/frontend/assets/images/loading-animation.png');
    v.muted = true;
    var src = document.createElement('source');
    src.src = '/frontend/assets/videos/login-loading.mp4';
    src.type = 'video/mp4';
    v.appendChild(src);
    v.addEventListener('loadeddata', function () { v.classList.add('swl-video-on'); });
    v.addEventListener('error', function () { v.classList.remove('swl-video-on'); });
    var pr = v.play();
    if (pr && pr.catch) pr.catch(function () {});
    return v;
  }

  // ---------------------------------------------------------------- mount
  var active = null;

  function show(cfg) {
    cfg = cfg || {};
    if (active) return active.api;

    cfg.minMs = cfg.minMs == null ? 2000 : cfg.minMs;
    cfg.maxMs = cfg.maxMs == null ? 8000 : cfg.maxMs;
    cfg.dest = cfg.dest || '/dashboard.html';
    if (cfg.admin) cfg.initialStatus = cfg.initialStatus || 'Loading admin portal...';
    if (cfg.register) cfg.initialStatus = cfg.initialStatus || 'Creating your account...';
    cfg.initialStatus = cfg.initialStatus || 'Signing you in...';

    var refs = build(cfg);
    active = refs;
    document.body.appendChild(refs.root);
    document.body.style.overflow = 'hidden';
    buildParticles(refs.root.querySelector('.swl-particles'));

    // Hide the underlying page content so nothing can show through.
    var host = document.querySelector('.login-box, .register-box, .auth-card, main');
    if (host) { host.setAttribute('aria-hidden', 'true'); host.style.visibility = 'hidden'; }

    requestAnimationFrame(function () {
      refs.root.classList.add('swl-in');
    });

    var api = drive(refs, cfg);
    refs.skip.addEventListener('click', function () { api.skip(); });
    return api;
  }

  // ---------------------------------------------------------------- progress
  function drive(refs, cfg) {
    var pctVal = 0;
    var done = false;
    var skipped = false;
    var t0 = performance.now();
    var timer = null;

    // Default work plan. Each step has a target %, a label, and real work.
    var steps = cfg.steps || [
      { to: 25, text: cfg.register ? 'Creating your account...' : 'Signing you in...', run: function () { return Promise.resolve(); } },
      { to: 60, text: cfg.admin ? 'Loading admin portal...' : 'Loading your dashboard...', run: function () {
          return Promise.all([getJSON('/api/dashboard/summary'), getJSON('/api/auth/me')]);
        } },
      { to: 90, text: 'Connecting to your bins...', run: function () { return getJSON('/api/bins'); } },
      { to: 96, text: 'Almost ready...', run: function () { return Promise.resolve(); } }
    ];

    function paint(p) {
      pctVal = Math.max(pctVal, clamp(p, 0, 100)); // forward-only
      var v = pctVal;
      refs.fill.style.width = v + '%';
      refs.pct.textContent = Math.round(v) + '%';
      refs.bar.setAttribute('aria-valuenow', String(Math.round(v)));
      refs.bar.setAttribute('aria-valuetext', Math.round(v) + '% — ' + refs.status.textContent);
      // ring arc + travelling tip
      refs.arc.style.strokeDasharray = (CIRC * v / 100) + ' ' + CIRC;
      var a = (v / 100) * 2 * Math.PI - Math.PI / 2;
      var tipR = RING_R;
      var tx = 100 + tipR * Math.cos(a);
      var ty = 100 + tipR * Math.sin(a);
      refs.tipG.setAttribute('transform', 'translate(' + (tx - 100).toFixed(2) + ' ' + (ty - 100).toFixed(2) + ')');
      refs.tipG.style.opacity = v > 1 ? '1' : '0';
    }

    function setStatus(text) {
      refs.status.textContent = text;
      refs.bar.setAttribute('aria-valuetext', Math.round(pctVal) + '% — ' + text);
    }

    function showWelcome(user) {
      refs.status.textContent = '';
      var wrap = el('span', 'swl-welcome');
      var name = (user && (user.fullName || user.username)) || '';
      var initial = name.trim().charAt(0).toUpperCase() || 'W';

      // Avatar: <img> with an onerror fallback to the initial-letter circle.
      var av = user && (user.avatar || user.avatarUrl);
      if (av) {
        var img = document.createElement('img');
        img.className = 'swl-avatar';
        img.alt = '';
        img.width = 30; img.height = 30;
        img.decoding = 'async';
        img.src = av;
        img.addEventListener('error', function () {
          if (img.parentNode) img.parentNode.replaceChild(makeInitial(initial), img);
        });
        wrap.appendChild(img);
      } else {
        wrap.appendChild(makeInitial(initial));
      }

      wrap.appendChild(document.createTextNode('Welcome back'));
      if (name) {
        var strong = el('span', 'swl-name');
        strong.textContent = name; // textContent: user input is never parsed as HTML
        wrap.appendChild(document.createTextNode(' '));
        wrap.appendChild(strong);
      }
      wrap.appendChild(document.createTextNode('!'));
      refs.status.appendChild(wrap);
      refs.bar.setAttribute('aria-valuetext', '100% — Welcome back' + (name ? ' ' + name : '') + '!');
    }

    function makeInitial(ch) {
      var s = el('span', 'swl-initial');
      s.setAttribute('aria-hidden', 'true');
      s.textContent = ch;
      return s;
    }

    function finish(force) {
      if (done) return;
      done = true;
      clearTimeout(timer);
      var elapsed = performance.now() - t0;
      var wait = Math.max(0, cfg.minMs - elapsed);

      var go = function () {
        if (!skipped || force) {
          paint(100);
          showWelcome(cfg.user);
        }
        setTimeout(function () {
          if (cfg.onDone) { try { cfg.onDone(); } catch (e) {} }
          window.location.replace(cfg.dest);
        }, 260);
      };
      if (wait) timer = setTimeout(go, wait); else go();
    }

    function runStep(i) {
      if (i >= steps.length) {
        paint(100);
        finish();
        return;
      }
      var s = steps[i];
      setStatus(s.text);
      var p = Promise.resolve();
      try { p = s.run() || Promise.resolve(); } catch (e) { p = Promise.resolve(); }
      p.then(function () {
        if (done) return;
        tweenTo(s.to, function () {
          if (i === steps.length - 1) { setStatus('Almost ready...'); paint(97); finish(); }
          else runStep(i + 1);
        });
      }).catch(function () {
        // A failed prefetch must never stall the flow.
        if (done) return;
        tweenTo(s.to, function () { runStep(i + 1); });
      });
    }

    // Smoothly ease to a target; never overshoots backwards.
    function tweenTo(target, cb) {
      target = clamp(target, pctVal, 100);
      var from = pctVal, span = target - from, dur = 420 + span * 14, t0l = performance.now();
      var prev = 0;
      function step(now) {
        if (done && pctVal >= 100) return;
        var t = clamp((now - t0l) / dur, 0, 1);
        var e = ease(t);
        paint(from + span * e);
        if (t < 1) { prev = requestAnimationFrame(step); }
        else if (cb) cb();
      }
      cancelAnimationFrame(prev);
      prev = requestAnimationFrame(step);
    }

    // Skip appears after 3s and jumps straight to the end.
    var skipReady = false;
    setTimeout(function () { if (!done) { skipReady = true; refs.skip.classList.add('swl-ready'); } }, 3000);

    // Hard cap: always navigate, whatever happened upstream.
    timer = setTimeout(function () {
      if (done) return;
      tweenTo(96, function () { finish(true); });
    }, cfg.maxMs);

    // Kick off after one paint so the arc animates from a visible 0.
    paint(0);
    requestAnimationFrame(function () { runStep(0); });

    return {
      skip: function () {
        if (!skipReady || done) return;
        skipped = true;
        tweenTo(100, function () { finish(true); });
      },
      destroy: function () {
        done = true;
        clearTimeout(timer);
        var n = document.getElementById(ID);
        if (n && n.parentNode) n.parentNode.removeChild(n);
        document.body.style.overflow = '';
        active = null;
      }
    };
  }

  // ---------------------------------------------------------------- page hooks
  // Back button / bfcache: if the page is restored after a real navigation,
  // drop a stale overlay instead of stranding the user behind it.
  window.addEventListener('pageshow', function (e) {
    if (e.persisted && active) {
      var n = document.getElementById(ID);
      if (n) { n.classList.add('swl-out'); }
      setTimeout(function () {
        var m = document.getElementById(ID);
        if (m && m.parentNode) m.parentNode.removeChild(m);
        document.body.style.overflow = '';
        var host = document.querySelector('.login-box, .register-box, .auth-card, main');
        if (host) { host.style.visibility = ''; host.removeAttribute('aria-hidden'); }
        active = null;
      }, 340);
    }
  });

  window.showLoginLoader = show;
})();