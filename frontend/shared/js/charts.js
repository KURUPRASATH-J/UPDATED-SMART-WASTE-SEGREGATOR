/**
 * charts.js — Lightweight Canvas Chart Library for Smart Waste Segregator
 * Zero external dependencies. Pure ES6 module with animated, themed charts.
 * 
 * @module charts
 */

/** Default colour palette used across all chart types */
const DEFAULT_COLORS = ['#00d4ff', '#00ff99', '#ff6b35', '#9932ff', '#ff4444'];

/** Default shared options applied to every chart unless overridden */
const DEFAULT_OPTIONS = {
  textColor: '#e0e0e0',
  gridColor: 'rgba(255,255,255,0.08)',
  fontFamily: '"Segoe UI", Roboto, sans-serif',
  animationDuration: 1000,
  backgroundColor: 'transparent',
  padding: { top: 30, right: 30, bottom: 50, left: 60 }
};

/* ───────────────────────────── helpers ───────────────────────────── */

/**
 * Resolve a canvas element from an ID string or an HTMLCanvasElement.
 * @param {string|HTMLCanvasElement} canvasId
 * @returns {{ canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D }}
 */
function resolveCanvas(canvasId) {
  const canvas = typeof canvasId === 'string'
    ? document.getElementById(canvasId)
    : canvasId;
  if (!canvas || !(canvas instanceof HTMLCanvasElement)) {
    throw new Error(`charts.js: Canvas "${canvasId}" not found`);
  }
  const ctx = canvas.getContext('2d');

  // Make the canvas crisp on HiDPI screens
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  // Store CSS dimensions for drawing
  canvas._cssW = rect.width;
  canvas._cssH = rect.height;

  return { canvas, ctx };
}

/**
 * Merge user options over defaults (shallow).
 * @param {Object} userOpts
 * @returns {Object}
 */
function mergeOpts(userOpts = {}) {
  return {
    ...DEFAULT_OPTIONS,
    ...userOpts,
    padding: { ...DEFAULT_OPTIONS.padding, ...(userOpts.padding || {}) }
  };
}

/** Easing: ease-out cubic */
function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

/** Clamp a value between min and max */
function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

/* ─────────────────────── 1. LINE CHART ─────────────────────── */

/**
 * Create a smooth, animated line chart with gradient fill, grid, axis labels
 * and hover tooltips.
 *
 * @param {string|HTMLCanvasElement} canvasId - Canvas element or its ID.
 * @param {{ labels: string[], datasets: { label: string, data: number[], color?: string }[] }} data
 * @param {Object} [options] - Overrides for DEFAULT_OPTIONS.
 * @returns {{ destroy: Function, update: Function }}
 */
export function createLineChart(canvasId, data, options = {}) {
  const opts = mergeOpts(options);
  const { canvas, ctx } = resolveCanvas(canvasId);
  const W = canvas._cssW;
  const H = canvas._cssH;
  const { top: pt, right: pr, bottom: pb, left: pl } = opts.padding;
  const plotW = W - pl - pr;
  const plotH = H - pt - pb;

  // Normalise datasets
  const datasets = (data.datasets || []).map((ds, i) => ({
    ...ds,
    color: ds.color || DEFAULT_COLORS[i % DEFAULT_COLORS.length]
  }));
  const labels = data.labels || [];
  const allValues = datasets.flatMap(ds => ds.data);
  const dataMin = Math.min(0, ...allValues);
  const dataMax = Math.max(...allValues) * 1.1 || 1;

  let animProg = 0;
  let rafId = null;
  let tooltipInfo = null; // { x, y, label, values }

  /* ---- mapping helpers ---- */
  const xOf = i => pl + (i / Math.max(labels.length - 1, 1)) * plotW;
  const yOf = v => pt + plotH - ((v - dataMin) / (dataMax - dataMin)) * plotH;

  /* ---- draw one frame ---- */
  function draw(progress) {
    ctx.clearRect(0, 0, W, H);

    // Background
    if (opts.backgroundColor !== 'transparent') {
      ctx.fillStyle = opts.backgroundColor;
      ctx.fillRect(0, 0, W, H);
    }

    // Grid lines & Y-axis labels
    const gridSteps = 5;
    ctx.strokeStyle = opts.gridColor;
    ctx.lineWidth = 0.5;
    ctx.fillStyle = opts.textColor;
    ctx.font = `11px ${opts.fontFamily}`;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= gridSteps; i++) {
      const val = dataMin + (dataMax - dataMin) * (i / gridSteps);
      const y = yOf(val);
      ctx.beginPath();
      ctx.moveTo(pl, y);
      ctx.lineTo(W - pr, y);
      ctx.stroke();
      ctx.fillText(Math.round(val), pl - 8, y);
    }

    // X-axis labels
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    labels.forEach((lbl, i) => {
      ctx.fillText(lbl, xOf(i), H - pb + 10);
    });

    // Datasets
    datasets.forEach(ds => {
      const pts = ds.data.map((v, i) => ({ x: xOf(i), y: yOf(v * progress) }));
      if (pts.length < 2) return;

      // Gradient fill
      const grad = ctx.createLinearGradient(0, pt, 0, pt + plotH);
      grad.addColorStop(0, ds.color + '55');
      grad.addColorStop(1, ds.color + '00');

      // Bezier smooth path
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 0; i < pts.length - 1; i++) {
        const cpx = (pts[i].x + pts[i + 1].x) / 2;
        ctx.bezierCurveTo(cpx, pts[i].y, cpx, pts[i + 1].y, pts[i + 1].x, pts[i + 1].y);
      }

      // Fill under curve
      ctx.lineTo(pts[pts.length - 1].x, pt + plotH);
      ctx.lineTo(pts[0].x, pt + plotH);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // Line
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 0; i < pts.length - 1; i++) {
        const cpx = (pts[i].x + pts[i + 1].x) / 2;
        ctx.bezierCurveTo(cpx, pts[i].y, cpx, pts[i + 1].y, pts[i + 1].x, pts[i + 1].y);
      }
      ctx.strokeStyle = ds.color;
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Data dots
      pts.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = ds.color;
        ctx.fill();
        ctx.strokeStyle = '#111';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
    });

    // Tooltip
    if (tooltipInfo && progress >= 1) {
      drawTooltip(ctx, tooltipInfo.x, tooltipInfo.y, tooltipInfo.text, opts);
    }
  }

  /* ---- animation loop ---- */
  const start = performance.now();
  function tick(now) {
    animProg = clamp((now - start) / opts.animationDuration, 0, 1);
    draw(easeOutCubic(animProg));
    if (animProg < 1) {
      rafId = requestAnimationFrame(tick);
    }
  }
  rafId = requestAnimationFrame(tick);

  /* ---- hover tooltip ---- */
  function onMouseMove(e) {
    if (animProg < 1) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let closest = null;
    let minDist = 20; // px threshold
    labels.forEach((lbl, i) => {
      const px = xOf(i);
      const d = Math.abs(mx - px);
      if (d < minDist) {
        minDist = d;
        const values = datasets.map(ds => `${ds.label}: ${ds.data[i]}`).join('\n');
        closest = { x: px, y: my, text: `${lbl}\n${values}` };
      }
    });
    tooltipInfo = closest;
    draw(1);
  }

  function onMouseLeave() {
    tooltipInfo = null;
    if (animProg >= 1) draw(1);
  }

  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseleave', onMouseLeave);

  /* ---- resize observer ---- */
  const ro = new ResizeObserver(() => {
    const { ctx: newCtx } = resolveCanvas(canvas);
    Object.assign(canvas, { _ctx: newCtx });
    if (animProg >= 1) draw(1);
  });
  ro.observe(canvas);

  return {
    /** Remove all listeners and cancel animations */
    destroy() {
      cancelAnimationFrame(rafId);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      ro.disconnect();
    },
    /** Redraw with new data */
    update(newData) {
      Object.assign(data, newData);
      animProg = 0;
      const s2 = performance.now();
      function t2(now) {
        animProg = clamp((now - s2) / opts.animationDuration, 0, 1);
        draw(easeOutCubic(animProg));
        if (animProg < 1) rafId = requestAnimationFrame(t2);
      }
      rafId = requestAnimationFrame(t2);
    }
  };
}

/* ─────────────────────── 2. BAR CHART ──────────────────────── */

/**
 * Create an animated bar chart with rounded corners and hover highlighting.
 *
 * @param {string|HTMLCanvasElement} canvasId
 * @param {{ labels: string[], datasets: { label: string, data: number[], color?: string }[] }} data
 * @param {Object} [options]
 * @returns {{ destroy: Function, update: Function }}
 */
export function createBarChart(canvasId, data, options = {}) {
  const opts = mergeOpts(options);
  const { canvas, ctx } = resolveCanvas(canvasId);
  const W = canvas._cssW;
  const H = canvas._cssH;
  const { top: pt, right: pr, bottom: pb, left: pl } = opts.padding;
  const plotW = W - pl - pr;
  const plotH = H - pt - pb;

  const datasets = (data.datasets || []).map((ds, i) => ({
    ...ds,
    color: ds.color || DEFAULT_COLORS[i % DEFAULT_COLORS.length]
  }));
  const labels = data.labels || [];
  const numSets = datasets.length || 1;
  const allValues = datasets.flatMap(ds => ds.data);
  const dataMax = Math.max(...allValues) * 1.15 || 1;

  const barGroupW = plotW / labels.length;
  const barW = Math.min(barGroupW * 0.6 / numSets, 50);
  const barGap = 4;

  let animProg = 0;
  let rafId = null;
  let hoverIdx = -1;

  function yOf(v) {
    return pt + plotH - (v / dataMax) * plotH;
  }

  /** Draw a rectangle with rounded top corners */
  function roundedBar(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    ctx.beginPath();
    ctx.moveTo(x, y + h);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h);
    ctx.closePath();
  }

  function draw(progress) {
    ctx.clearRect(0, 0, W, H);

    if (opts.backgroundColor !== 'transparent') {
      ctx.fillStyle = opts.backgroundColor;
      ctx.fillRect(0, 0, W, H);
    }

    // Grid & Y-axis
    const gridSteps = 5;
    ctx.strokeStyle = opts.gridColor;
    ctx.lineWidth = 0.5;
    ctx.fillStyle = opts.textColor;
    ctx.font = `11px ${opts.fontFamily}`;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= gridSteps; i++) {
      const val = (dataMax * i) / gridSteps;
      const y = yOf(val);
      ctx.beginPath();
      ctx.moveTo(pl, y);
      ctx.lineTo(W - pr, y);
      ctx.stroke();
      ctx.fillText(Math.round(val), pl - 8, y);
    }

    // X-axis labels
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    labels.forEach((lbl, i) => {
      const cx = pl + barGroupW * i + barGroupW / 2;
      ctx.fillStyle = opts.textColor;
      ctx.fillText(lbl, cx, H - pb + 10);
    });

    // Bars
    labels.forEach((lbl, li) => {
      const groupX = pl + barGroupW * li + (barGroupW - (barW * numSets + barGap * (numSets - 1))) / 2;
      datasets.forEach((ds, di) => {
        const val = ds.data[li] || 0;
        const barH = (val / dataMax) * plotH * progress;
        const x = groupX + di * (barW + barGap);
        const y = pt + plotH - barH;

        // Hover highlight
        const isHover = (li === hoverIdx);
        ctx.globalAlpha = isHover ? 1.0 : 0.85;

        roundedBar(x, y, barW, barH, 5);
        ctx.fillStyle = ds.color;
        ctx.fill();

        // Value on top
        if (progress > 0.9) {
          ctx.globalAlpha = 1;
          ctx.fillStyle = opts.textColor;
          ctx.font = `bold 11px ${opts.fontFamily}`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(val, x + barW / 2, y - 4);
        }
      });
    });
    ctx.globalAlpha = 1;
  }

  // Animate
  const start = performance.now();
  function tick(now) {
    animProg = clamp((now - start) / opts.animationDuration, 0, 1);
    draw(easeOutCubic(animProg));
    if (animProg < 1) rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);

  // Hover
  function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const idx = Math.floor((mx - pl) / barGroupW);
    hoverIdx = (idx >= 0 && idx < labels.length) ? idx : -1;
    if (animProg >= 1) draw(1);
  }

  function onMouseLeave() {
    hoverIdx = -1;
    if (animProg >= 1) draw(1);
  }

  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseleave', onMouseLeave);

  const ro = new ResizeObserver(() => {
    resolveCanvas(canvas);
    if (animProg >= 1) draw(1);
  });
  ro.observe(canvas);

  return {
    destroy() {
      cancelAnimationFrame(rafId);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      ro.disconnect();
    },
    update(newData) {
      Object.assign(data, newData);
      animProg = 0;
      const s2 = performance.now();
      function t2(now) {
        animProg = clamp((now - s2) / opts.animationDuration, 0, 1);
        draw(easeOutCubic(animProg));
        if (animProg < 1) rafId = requestAnimationFrame(t2);
      }
      rafId = requestAnimationFrame(t2);
    }
  };
}

/* ────────────────────── 3. DOUGHNUT CHART ──────────────────── */

/**
 * Create an animated doughnut chart with center text and a legend.
 *
 * @param {string|HTMLCanvasElement} canvasId
 * @param {{ labels: string[], data: number[], colors?: string[] }} data
 * @param {Object} [options] - Extra options: `centerLabel`, `innerRadiusRatio`.
 * @returns {{ destroy: Function, update: Function }}
 */
export function createDoughnutChart(canvasId, data, options = {}) {
  const opts = mergeOpts(options);
  const centerLabel = opts.centerLabel || 'Total';
  const innerRatio = opts.innerRadiusRatio || 0.62;
  const { canvas, ctx } = resolveCanvas(canvasId);
  const W = canvas._cssW;
  const H = canvas._cssH;

  const colors = data.colors || DEFAULT_COLORS;
  const labels = data.labels || [];
  const values = data.data || [];
  const total = values.reduce((a, b) => a + b, 0) || 1;

  const cx = W * 0.45;
  const cy = H / 2;
  const outerR = Math.min(cx - 20, cy - 20);
  const innerR = outerR * innerRatio;

  let animProg = 0;
  let rafId = null;
  let hoverIndex = -1;

  function draw(progress) {
    ctx.clearRect(0, 0, W, H);

    if (opts.backgroundColor !== 'transparent') {
      ctx.fillStyle = opts.backgroundColor;
      ctx.fillRect(0, 0, W, H);
    }

    const totalAngle = Math.PI * 2 * progress;
    let startAngle = -Math.PI / 2;

    values.forEach((val, i) => {
      const slice = (val / total) * totalAngle;
      const isHover = (i === hoverIndex);
      const r = isHover ? outerR + 6 : outerR;

      ctx.beginPath();
      ctx.arc(cx, cy, r, startAngle, startAngle + slice);
      ctx.arc(cx, cy, innerR, startAngle + slice, startAngle, true);
      ctx.closePath();
      ctx.fillStyle = colors[i % colors.length];
      ctx.globalAlpha = isHover ? 1 : 0.88;
      ctx.fill();
      ctx.globalAlpha = 1;

      startAngle += slice;
    });

    // Center text
    if (progress > 0.5) {
      ctx.fillStyle = opts.textColor;
      ctx.font = `bold 26px ${opts.fontFamily}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(Math.round(total * progress), cx, cy - 6);
      ctx.font = `12px ${opts.fontFamily}`;
      ctx.fillStyle = opts.textColor + 'aa';
      ctx.fillText(centerLabel, cx, cy + 18);
    }

    // Legend on the right
    const legendX = cx + outerR + 30;
    let legendY = cy - (values.length * 24) / 2;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    labels.forEach((lbl, i) => {
      ctx.fillStyle = colors[i % colors.length];
      ctx.fillRect(legendX, legendY - 6, 12, 12);
      ctx.fillStyle = opts.textColor;
      ctx.font = `12px ${opts.fontFamily}`;
      const pct = ((values[i] / total) * 100).toFixed(1);
      ctx.fillText(`${lbl} (${pct}%)`, legendX + 18, legendY);
      legendY += 24;
    });
  }

  const start = performance.now();
  function tick(now) {
    animProg = clamp((now - start) / opts.animationDuration, 0, 1);
    draw(easeOutCubic(animProg));
    if (animProg < 1) rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);

  // Hover detection
  function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left - cx;
    const my = e.clientY - rect.top - cy;
    const dist = Math.sqrt(mx * mx + my * my);

    if (dist < innerR || dist > outerR + 10) {
      hoverIndex = -1;
    } else {
      let angle = Math.atan2(my, mx) + Math.PI / 2;
      if (angle < 0) angle += Math.PI * 2;
      let cumAngle = 0;
      hoverIndex = -1;
      for (let i = 0; i < values.length; i++) {
        cumAngle += (values[i] / total) * Math.PI * 2;
        if (angle <= cumAngle) {
          hoverIndex = i;
          break;
        }
      }
    }
    if (animProg >= 1) draw(1);
  }

  function onMouseLeave() {
    hoverIndex = -1;
    if (animProg >= 1) draw(1);
  }

  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseleave', onMouseLeave);

  const ro = new ResizeObserver(() => {
    resolveCanvas(canvas);
    if (animProg >= 1) draw(1);
  });
  ro.observe(canvas);

  return {
    destroy() {
      cancelAnimationFrame(rafId);
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      ro.disconnect();
    },
    update(newData) {
      Object.assign(data, newData);
      animProg = 0;
      const s2 = performance.now();
      function t2(now) {
        animProg = clamp((now - s2) / opts.animationDuration, 0, 1);
        draw(easeOutCubic(animProg));
        if (animProg < 1) rafId = requestAnimationFrame(t2);
      }
      rafId = requestAnimationFrame(t2);
    }
  };
}

/* ──────────────────────── 4. GAUGE CHART ───────────────────── */

/**
 * Create a 180° gauge meter with animated needle and green→yellow→red gradient.
 *
 * @param {string|HTMLCanvasElement} canvasId
 * @param {number} value - Current value (0-100 by default).
 * @param {Object} [options] - Extra options: `min`, `max`, `label`, `unit`.
 * @returns {{ destroy: Function, setValue: Function }}
 */
export function createGaugeChart(canvasId, value, options = {}) {
  const opts = mergeOpts(options);
  const min = opts.min ?? 0;
  const max = opts.max ?? 100;
  const label = opts.label || '';
  const unit = opts.unit || '%';
  const { canvas, ctx } = resolveCanvas(canvasId);
  const W = canvas._cssW;
  const H = canvas._cssH;

  const cx = W / 2;
  const cy = H * 0.72;
  const radius = Math.min(cx - 20, cy - 10);

  let currentValue = 0;
  let targetValue = clamp(value, min, max);
  let animProg = 0;
  let rafId = null;

  /** Map a value to an angle on the 180° arc (π to 0, left to right) */
  function valueToAngle(v) {
    const ratio = (v - min) / (max - min);
    return Math.PI * (1 - ratio);
  }

  function draw(progress) {
    ctx.clearRect(0, 0, W, H);

    if (opts.backgroundColor !== 'transparent') {
      ctx.fillStyle = opts.backgroundColor;
      ctx.fillRect(0, 0, W, H);
    }

    // Background arc
    ctx.beginPath();
    ctx.arc(cx, cy, radius, Math.PI, 0);
    ctx.lineWidth = 22;
    ctx.strokeStyle = opts.gridColor;
    ctx.stroke();

    // Gradient arc (green → yellow → red)
    const arcGrad = ctx.createLinearGradient(cx - radius, cy, cx + radius, cy);
    arcGrad.addColorStop(0, '#00ff99');
    arcGrad.addColorStop(0.5, '#ffd700');
    arcGrad.addColorStop(1, '#ff4444');

    const displayVal = min + (targetValue - min) * progress;
    const endAngle = valueToAngle(displayVal);

    ctx.beginPath();
    ctx.arc(cx, cy, radius, Math.PI, Math.PI - (Math.PI - endAngle) * 1, false);
    ctx.lineWidth = 22;
    ctx.lineCap = 'round';
    ctx.strokeStyle = arcGrad;
    ctx.stroke();
    ctx.lineCap = 'butt';

    // Tick marks
    for (let i = 0; i <= 10; i++) {
      const angle = Math.PI - (Math.PI * i) / 10;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const isMajor = i % 2 === 0;
      const len = isMajor ? 14 : 8;
      ctx.beginPath();
      ctx.moveTo(cx + cos * (radius - 16), cy - sin * (radius - 16));
      ctx.lineTo(cx + cos * (radius - 16 - len), cy - sin * (radius - 16 - len));
      ctx.strokeStyle = opts.textColor + '88';
      ctx.lineWidth = isMajor ? 2 : 1;
      ctx.stroke();

      if (isMajor) {
        const tickVal = Math.round(min + (max - min) * (i / 10));
        ctx.fillStyle = opts.textColor + 'aa';
        ctx.font = `10px ${opts.fontFamily}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(tickVal, cx + cos * (radius - 46), cy - sin * (radius - 46));
      }
    }

    // Needle
    const needleAngle = valueToAngle(displayVal);
    const needleLen = radius - 30;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-needleAngle);
    // Shadow
    ctx.shadowColor = 'rgba(0,0,0,0.3)';
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.moveTo(0, -3);
    ctx.lineTo(needleLen, 0);
    ctx.lineTo(0, 3);
    ctx.closePath();
    ctx.fillStyle = '#ff6b35';
    ctx.fill();
    ctx.shadowBlur = 0;
    // Center dot
    ctx.beginPath();
    ctx.arc(0, 0, 7, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.restore();

    // Center value
    ctx.fillStyle = opts.textColor;
    ctx.font = `bold 32px ${opts.fontFamily}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`${Math.round(displayVal)}${unit}`, cx, cy + 12);

    // Label
    if (label) {
      ctx.font = `13px ${opts.fontFamily}`;
      ctx.fillStyle = opts.textColor + 'bb';
      ctx.fillText(label, cx, cy + 48);
    }

    // Min / Max labels
    ctx.font = `11px ${opts.fontFamily}`;
    ctx.fillStyle = opts.textColor + '99';
    ctx.textAlign = 'center';
    ctx.fillText(`${min}`, cx - radius + 10, cy + 14);
    ctx.fillText(`${max}`, cx + radius - 10, cy + 14);
  }

  const startTime = performance.now();
  function tick(now) {
    animProg = clamp((now - startTime) / opts.animationDuration, 0, 1);
    draw(easeOutCubic(animProg));
    if (animProg < 1) rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);

  const ro = new ResizeObserver(() => {
    resolveCanvas(canvas);
    if (animProg >= 1) draw(1);
  });
  ro.observe(canvas);

  return {
    destroy() {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    },
    /** Animate to a new value */
    setValue(newValue) {
      currentValue = targetValue;
      targetValue = clamp(newValue, min, max);
      animProg = 0;
      const s2 = performance.now();
      function t2(now) {
        animProg = clamp((now - s2) / opts.animationDuration, 0, 1);
        const prog = easeOutCubic(animProg);
        const interpValue = currentValue + (targetValue - currentValue) * prog;
        // draw expects a 0-1 progress that multiplies (targetValue - min), so
        // we call a helper that draws the exact interpolated value at progress=1
        drawExact(interpValue);
        if (animProg < 1) rafId = requestAnimationFrame(t2);
      }
      /** Draw with an exact value (progress already baked in) */
      function drawExact(val) {
        const saved = targetValue;
        targetValue = val;
        draw(1);
        targetValue = saved;
      }
      rafId = requestAnimationFrame(t2);
    }
  };
}

/* ────────────────── shared tooltip renderer ────────────────── */

/**
 * Draw a floating tooltip box near (x, y).
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} x
 * @param {number} y
 * @param {string} text - Newline-separated lines.
 * @param {Object} opts
 */
function drawTooltip(ctx, x, y, text, opts) {
  const lines = text.split('\n');
  const lineH = 16;
  const padX = 12;
  const padY = 8;
  ctx.font = `12px ${opts.fontFamily}`;
  const maxW = Math.max(...lines.map(l => ctx.measureText(l).width));
  const boxW = maxW + padX * 2;
  const boxH = lines.length * lineH + padY * 2;
  let bx = x - boxW / 2;
  let by = y - boxH - 12;
  if (by < 0) by = y + 12;

  // Background
  ctx.fillStyle = 'rgba(17,17,17,0.92)';
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  roundRect(ctx, bx, by, boxW, boxH, 6);
  ctx.fill();
  ctx.stroke();

  // Text
  ctx.fillStyle = '#fff';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  lines.forEach((line, i) => {
    ctx.fillText(line, bx + padX, by + padY + i * lineH);
  });
}

/** Draw a rounded rectangle path */
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}
