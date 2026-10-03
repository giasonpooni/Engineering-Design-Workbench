/**
 * Status bar — bottom-left mono readout of renderer vitals plus the
 * synthetic-data disclaimer chip. Throttled to ~4Hz.
 */

import type { AppApi, AppEvents } from '../app/api';

const THROTTLE_MS = 250;

function fmt(n: number): string {
  return Math.round(n).toLocaleString('en-US');
}

export function createStatusBar(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pe-statusbar';

  const seg = (): HTMLSpanElement => {
    const s = document.createElement('span');
    s.className = 'pe-sb-seg';
    el.appendChild(s);
    return s;
  };

  const fpsSeg = seg();
  const altSeg = seg();
  const nodesSeg = seg();
  const routesSeg = seg();
  const particlesSeg = seg();

  const chip = document.createElement('span');
  chip.className = 'pe-sb-chip';
  chip.textContent = 'SYNTHETIC / DEMO DATA';
  el.appendChild(chip);

  const syncDisclaimer = (): void => {
    try {
      chip.title = api.store.snapshot.meta.disclaimer;
    } catch {
      /* snapshot not loaded yet */
    }
  };
  syncDisclaimer();

  const render = (s: AppEvents['status']): void => {
    fpsSeg.innerHTML = `FPS <b>${fmt(s.fps)}</b>`;
    altSeg.innerHTML = `ALT <b>${fmt(s.altitudeKm)} KM</b>`;
    nodesSeg.innerHTML = `NODES <b>${fmt(s.visibleNodes)}</b>`;
    routesSeg.innerHTML = `ROUTES <b>${fmt(s.visibleRoutes)}</b>`;
    particlesSeg.innerHTML = `PARTICLES <b>${fmt(s.particles)}</b>`;
  };

  render({ fps: 0, altitudeKm: 0, visibleNodes: 0, visibleRoutes: 0, particles: 0 });

  let lastRender = 0;
  let pending: AppEvents['status'] | null = null;
  let timer = 0;

  api.events.on('status', (s) => {
    if (!chip.title) syncDisclaimer();
    const now = performance.now();
    if (now - lastRender >= THROTTLE_MS) {
      lastRender = now;
      render(s);
    } else {
      pending = s;
      if (!timer) {
        timer = window.setTimeout(() => {
          timer = 0;
          if (pending) {
            lastRender = performance.now();
            render(pending);
            pending = null;
          }
        }, THROTTLE_MS - (now - lastRender));
      }
    }
  });

  return { el };
}
