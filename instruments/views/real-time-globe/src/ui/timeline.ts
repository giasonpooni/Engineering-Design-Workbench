/**
 * Timeline — bottom-center temporal control strip: play/pause, speed,
 * UTC readout, regime chip, NOW jump, and a scrubber with the played
 * range, the dataset-now tick, world-event markers, and a draggable
 * playhead. Reads the clock lazily — the app configures it.
 */

import type { AppApi } from '../app/api';
import type { TemporalRegime, WorldEvent } from '../data/contracts';

const SPEEDS: [label: string, simSecondsPerSecond: number][] = [
  ['1H/S', 3600],
  ['6H/S', 21600],
  ['24H/S', 86400],
];

export function createTimeline(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pi-timeline';

  // ---------------------------------------------------------------- row 1

  const row1 = document.createElement('div');
  row1.className = 'pi-tl-row1';

  const playBtn = document.createElement('button');
  playBtn.type = 'button';
  playBtn.className = 'pi-tl-play';
  playBtn.title = 'Play / pause (space)';

  const setPlayGlyph = (playing: boolean): void => {
    playBtn.textContent = playing ? '❚❚' : '▸';
  };
  setPlayGlyph(false);

  playBtn.addEventListener('click', () => {
    api.clock.setPlaying(!api.clock.playing);
  });

  const speeds = document.createElement('div');
  speeds.className = 'pi-tl-speeds';
  const speedBtns: [HTMLButtonElement, number][] = [];
  for (const [label, v] of SPEEDS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'pi-tl-speed';
    b.textContent = label;
    b.title = `${label.toLowerCase()} sim speed`;
    b.addEventListener('click', () => api.clock.setSpeed(v));
    speeds.append(b);
    speedBtns.push([b, v]);
  }
  const setActiveSpeed = (speed: number): void => {
    for (const [b, v] of speedBtns) b.classList.toggle('active', v === speed);
  };
  setActiveSpeed(api.clock.speed);

  const readout = document.createElement('div');
  readout.className = 'pi-tl-readout';
  readout.textContent = 'UTC ——';

  const regimeChip = document.createElement('div');
  regimeChip.className = 'pi-tl-regime regime-current';
  regimeChip.textContent = 'CURRENT';

  const setRegime = (regime: TemporalRegime): void => {
    regimeChip.classList.remove('regime-historical', 'regime-current', 'regime-forecast');
    regimeChip.classList.add(`regime-${regime === 'scenario' ? 'forecast' : regime}`);
    regimeChip.textContent = regime.toUpperCase();
  };

  const nowBtn = document.createElement('button');
  nowBtn.type = 'button';
  nowBtn.className = 'pi-tl-nowbtn';
  nowBtn.textContent = 'NOW';
  nowBtn.title = 'Jump to dataset now';
  nowBtn.addEventListener('click', () => api.clock.jumpToNow());

  row1.append(playBtn, speeds, readout, regimeChip, nowBtn);

  // ---------------------------------------------------------------- row 2 — scrubber

  const scrub = document.createElement('div');
  scrub.className = 'pi-tl-scrub';

  const track = document.createElement('div');
  track.className = 'pi-tl-track';

  const played = document.createElement('div');
  played.className = 'pi-tl-played';

  const nowTick = document.createElement('div');
  nowTick.className = 'pi-tl-nowtick';

  const markers = document.createElement('div');

  const playhead = document.createElement('div');
  playhead.className = 'pi-tl-playhead';

  track.append(played, nowTick, markers, playhead);
  scrub.append(track);

  el.append(row1, scrub);

  // ---------------------------------------------------------------- markers

  let markersRangeKey = '';

  const frac = (ms: number, startMs: number, endMs: number): number =>
    endMs === startMs ? 0 : Math.min(1, Math.max(0, (ms - startMs) / (endMs - startMs)));

  const ensureMarkers = (): void => {
    const { startMs, endMs, nowMs } = api.clock.range;
    if (!(endMs > startMs)) return;
    const key = `${startMs}:${endMs}:${nowMs}`;
    if (key === markersRangeKey) return;
    markersRangeKey = key;

    nowTick.style.left = `${frac(nowMs, startMs, endMs) * 100}%`;

    markers.replaceChildren();
    let events: WorldEvent[] = [];
    try {
      events = api.store.snapshot?.events ?? [];
    } catch {
      events = [];
    }
    for (const evt of events) {
      const startFrac = frac(Date.parse(evt.start), startMs, endMs);
      const m = document.createElement('div');
      m.className = 'pi-tl-evt';
      if (evt.severity > 0.6) m.classList.add('pi-evt-alert');
      m.style.left = `${startFrac * 100}%`;
      const endLabel = evt.end ? ` → ${evt.end.slice(0, 10)}` : '';
      m.title = `${evt.name}\n${evt.start.slice(0, 10)}${endLabel}`;
      m.addEventListener('pointerdown', (e) => {
        e.stopPropagation();
        api.clock.setFraction(startFrac);
      });
      markers.append(m);
    }
  };

  // attempt once at mount (store/clock may already be configured)
  try {
    ensureMarkers();
  } catch {
    /* provider not ready yet — retried on first 'time' event */
  }

  // ---------------------------------------------------------------- scrubbing

  let dragging = false;
  const scrubTo = (e: PointerEvent): void => {
    const rect = track.getBoundingClientRect();
    if (rect.width <= 0) return;
    api.clock.setFraction((e.clientX - rect.left) / rect.width);
  };
  scrub.addEventListener('pointerdown', (e) => {
    dragging = true;
    scrub.setPointerCapture(e.pointerId);
    scrubTo(e);
  });
  scrub.addEventListener('pointermove', (e) => {
    if (dragging) scrubTo(e);
  });
  const endDrag = (): void => {
    dragging = false;
  };
  scrub.addEventListener('pointerup', endDrag);
  scrub.addEventListener('pointercancel', endDrag);

  // ---------------------------------------------------------------- clock wiring

  const renderTime = (ts: { t: string; regime: 'historical' | 'current' | 'forecast' | 'scenario' }) => {
    ensureMarkers();
    const f = api.clock.fraction;
    playhead.style.left = `${f * 100}%`;
    played.style.width = `${f * 100}%`;
    readout.textContent = `UTC ${ts.t.slice(0, 16).replace('T', ' ')}`;
    setRegime(ts.regime);
  };
  api.events.on('time', renderTime);
  // the clock is configured before the HUD mounts — render current state now
  renderTime(api.clock.state());

  api.clock.events.on('playstate', ({ playing, speed }) => {
    setPlayGlyph(playing);
    setActiveSpeed(speed);
  });

  // space toggles play unless typing in an input
  window.addEventListener('keydown', (e) => {
    if (e.code !== 'Space') return;
    const ae = document.activeElement as HTMLElement | null;
    if (
      ae &&
      (ae.tagName === 'INPUT' ||
        ae.tagName === 'TEXTAREA' ||
        ae.tagName === 'SELECT' ||
        ae.isContentEditable)
    )
      return;
    e.preventDefault();
    api.clock.setPlaying(!api.clock.playing);
  });

  return { el };
}
