/**
 * Sparkline — tiny devicePixelRatio-aware canvas line chart for the
 * inspector's temporal sections, plus shared numeric formatters.
 * No axes, no chrome: a thin line, a soft area, a faint baseline,
 * an optional sim-cursor marker and a dotted 'now' divider.
 */

export interface SparkPoint {
  t: number; // ms
  v: number;
}

export interface SparkOpts {
  min?: number;
  max?: number;
  /** Sim cursor position (ms) — solid accent vertical. */
  markerT?: number;
  /** Dataset 'now' (ms) — dotted vertical. */
  nowT?: number;
  color?: string;
}

/** Resolve 'var(--token)' against :root so canvas can consume theme tokens. */
function resolveColor(c: string, fallback: string): string {
  if (!c) return fallback;
  if (c.startsWith('var(')) {
    const name = c.slice(4, -1).split(',')[0].trim();
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  return c;
}

export function drawSparkline(
  canvas: HTMLCanvasElement,
  points: { t: number; v: number }[],
  opts: { min?: number; max?: number; markerT?: number; color?: string; nowT?: number }
): void {
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const cssW = canvas.clientWidth || Number(canvas.getAttribute('width')) || 260;
  const cssH = canvas.clientHeight || Number(canvas.getAttribute('height')) || 44;
  const pxW = Math.max(1, Math.round(cssW * dpr));
  const pxH = Math.max(1, Math.round(cssH * dpr));
  if (canvas.width !== pxW) canvas.width = pxW;
  if (canvas.height !== pxH) canvas.height = pxH;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const color = resolveColor(opts.color ?? 'var(--accent)', '#4da6ff');
  const padTop = 3;
  const padBot = 3;
  const baseY = cssH - padBot;

  // faint baseline
  ctx.strokeStyle = 'rgba(120,160,200,0.16)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, baseY + 0.5);
  ctx.lineTo(cssW, baseY + 0.5);
  ctx.stroke();

  if (points.length >= 2) {
    let t0 = Infinity;
    let t1 = -Infinity;
    let vLo = Infinity;
    let vHi = -Infinity;
    for (const p of points) {
      if (p.t < t0) t0 = p.t;
      if (p.t > t1) t1 = p.t;
      if (p.v < vLo) vLo = p.v;
      if (p.v > vHi) vHi = p.v;
    }
    const min = opts.min ?? vLo;
    let max = opts.max ?? vHi;
    if (max <= min) max = min + 1;
    const tSpan = t1 - t0 || 1;
    const x = (t: number): number => ((t - t0) / tSpan) * cssW;
    const y = (v: number): number => {
      const f = Math.min(1, Math.max(0, (v - min) / (max - min)));
      return baseY - f * (baseY - padTop);
    };

    // soft area fill (8% alpha)
    ctx.beginPath();
    ctx.moveTo(x(points[0].t), baseY);
    for (const p of points) ctx.lineTo(x(p.t), y(p.v));
    ctx.lineTo(x(points[points.length - 1].t), baseY);
    ctx.closePath();
    ctx.globalAlpha = 0.08;
    ctx.fillStyle = color;
    ctx.fill();
    ctx.globalAlpha = 1;

    // thin line
    ctx.beginPath();
    ctx.moveTo(x(points[0].t), y(points[0].v));
    for (let i = 1; i < points.length; i++) ctx.lineTo(x(points[i].t), y(points[i].v));
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.25;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // dotted vertical at nowT (regime boundary)
    if (opts.nowT !== undefined && opts.nowT >= t0 && opts.nowT <= t1) {
      const nx = Math.round(x(opts.nowT)) + 0.5;
      ctx.save();
      ctx.setLineDash([2, 3]);
      ctx.strokeStyle = 'rgba(143,163,184,0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(nx, padTop);
      ctx.lineTo(nx, baseY);
      ctx.stroke();
      ctx.restore();
    }

    // solid accent marker at markerT (sim cursor)
    if (opts.markerT !== undefined && opts.markerT >= t0 && opts.markerT <= t1) {
      const mx = Math.round(x(opts.markerT)) + 0.5;
      ctx.strokeStyle = resolveColor('var(--accent)', '#4da6ff');
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(mx, padTop - 1);
      ctx.lineTo(mx, baseY);
      ctx.stroke();
    }
  }
}

/** Thousands-separated number, fixed fraction digits (default 0). */
export function fmt(n: number, digits?: number): string {
  const d = digits ?? 0;
  return n.toLocaleString('en-US', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

/** 0..1 → '62%'. */
export function fmtPct(v: number): string {
  return `${Math.round(v * 100)}%`;
}
