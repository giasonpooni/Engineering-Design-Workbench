/**
 * Info panel — the right-side inspector. An intelligence instrument,
 * not a tooltip: dense, quiet, legible. Renders facilities, routes,
 * flows ("loads") and countries from the WorldStore projection, with
 * live values resolved at the sim clock's current time and an EVIDENCE
 * section on everything.
 */

import type { AppApi } from '../app/api';
import type {
  EntityId,
  Facility,
  Flow,
  Provenance,
  Route,
  RouteConstraint,
  TransportMode,
  WorldEvent,
} from '../data/contracts';
import { drawSparkline, fmt, fmtPct } from './sparkline';

const MODE_COLOR: Record<TransportMode, string> = {
  road: 'var(--mode-road)',
  rail: 'var(--mode-rail)',
  maritime: 'var(--mode-maritime)',
  air: 'var(--mode-air)',
};

const MODE_ORDER: TransportMode[] = ['road', 'rail', 'maritime', 'air'];

type Tone = 'ok' | 'warn' | 'alert' | 'dim';

function statusTone(status: string): Tone {
  switch (status) {
    case 'active':
    case 'moving':
    case 'delivered':
      return 'ok';
    case 'degraded':
    case 'delayed':
    case 'holding':
      return 'warn';
    case 'disrupted':
    case 'inactive':
      return 'alert';
    default:
      return 'dim';
  }
}

function caps(s: string): string {
  return s.replace(/_/g, ' ').toUpperCase();
}

export function createInfoPanel(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pi-panel pi-hidden';

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'pi-close';
  close.textContent = '×';
  close.title = 'Close';
  close.addEventListener('click', () => {
    if (country) api.selectCountry(null);
    else api.select(null, 'ui');
  });

  const content = document.createElement('div');
  el.append(close, content);

  let selectedId: EntityId | null = null;
  let country: { code: string; name: string } | null = null;
  const expandedCats = new Set<string>();

  // ---------------------------------------------------------------- builders

  function div(cls: string, text?: string): HTMLElement {
    const d = document.createElement('div');
    d.className = cls;
    if (text !== undefined) d.textContent = text;
    return d;
  }

  function header(kindLabel: string, name: string, opts?: { modeColor?: string }): HTMLElement {
    const head = div('pi-head');
    const kind = div('pi-kind');
    if (opts?.modeColor) {
      const dot = kindLabel.indexOf('·');
      if (dot >= 0) {
        kind.append(document.createTextNode(kindLabel.slice(0, dot + 1) + ' '));
        const mode = document.createElement('span');
        mode.className = 'pi-kind-mode';
        mode.style.color = opts.modeColor;
        mode.textContent = kindLabel.slice(dot + 1).trim();
        kind.append(mode);
      } else {
        kind.textContent = kindLabel;
        kind.style.color = opts.modeColor;
      }
    } else {
      kind.textContent = kindLabel;
    }
    head.append(kind, div('pi-name', name));
    return head;
  }

  function statusChip(status: string): HTMLElement {
    const tone = statusTone(status);
    const line = div('pi-statusline');
    line.append(
      div(`pi-status-dot pi-bg-${tone}`),
      div(`pi-status-text pi-tone-${tone}`, status.toUpperCase())
    );
    return line;
  }

  function section(title: string, ...children: (HTMLElement | null)[]): HTMLElement {
    const s = div('pi-section');
    s.append(div('pi-sec-title', title));
    for (const c of children) if (c) s.append(c);
    return s;
  }

  function kv(
    label: string,
    value: string,
    opts?: { focusId?: EntityId; tone?: Tone }
  ): HTMLElement {
    const row = div('pi-kv');
    const v = div('pi-kv-v', value);
    if (opts?.tone) v.classList.add(`pi-tone-${opts.tone}`);
    row.append(div('pi-kv-k', label), v);
    if (opts?.focusId) {
      const id = opts.focusId;
      row.classList.add('pi-click');
      row.addEventListener('click', () => api.focus(id));
    }
    return row;
  }

  function meter(label: string, frac: number, color: string): HTMLElement {
    const m = div('pi-meter');
    const head = div('pi-meter-head');
    head.append(div('pi-meter-label', label), div('pi-meter-value', fmtPct(frac)));
    const track = div('pi-meter-track');
    const fill = div('pi-meter-fill');
    fill.style.width = `${Math.min(100, Math.max(0, frac * 100))}%`;
    fill.style.background = color;
    track.append(fill);
    m.append(head, track);
    return m;
  }

  function entityRow(
    text: string,
    opts?: { focusId?: EntityId; sub?: string; dotColor?: string }
  ): HTMLElement {
    const row = div('pi-row');
    if (opts?.dotColor) {
      const dot = div('pi-dot');
      dot.style.background = opts.dotColor;
      row.append(dot);
    }
    row.append(div('pi-row-main', text));
    if (opts?.sub) row.append(div('pi-row-sub', opts.sub));
    if (opts?.focusId) {
      const id = opts.focusId;
      row.classList.add('pi-click');
      row.addEventListener('click', () => api.focus(id));
    }
    return row;
  }

  function sevBar(severity: number): HTMLElement {
    const bar = div('pi-sev');
    const fill = div('pi-sev-fill');
    fill.style.width = `${Math.min(100, Math.max(0, severity * 100))}%`;
    fill.style.background = severity > 0.6 ? 'var(--alert)' : 'var(--warn)';
    bar.append(fill);
    return bar;
  }

  function eventRow(evt: WorldEvent): HTMLElement {
    const wrap = div('pi-con');
    const head = div('pi-con-head');
    head.append(div('pi-con-type', caps(evt.category)), div('pi-con-desc', evt.name));
    wrap.append(head, sevBar(evt.severity));
    wrap.title = evt.description;
    return wrap;
  }

  function empty(text: string): HTMLElement {
    return div('pi-empty', text);
  }

  function rangeDays(): number {
    const r = api.clock.range;
    return Math.max(1, Math.round((r.endMs - r.startMs) / 86400000));
  }

  function sparkSection(title: string, entityId: EntityId, color?: string): HTMLElement | null {
    const { startMs, endMs, nowMs } = api.clock.range;
    if (!(endMs > startMs)) return null;
    const canvas = document.createElement('canvas');
    canvas.className = 'pi-spark';
    const N = 56;
    const points: { t: number; v: number }[] = [];
    for (let i = 0; i < N; i++) {
      const t = startMs + (i / (N - 1)) * (endMs - startMs);
      const st = api.store.stateAt(entityId, new Date(t).toISOString());
      points.push({ t, v: st.utilization });
    }
    const markerT = api.clock.simMillis;
    // canvas needs layout for clientWidth — draw on next frame
    requestAnimationFrame(() =>
      drawSparkline(canvas, points, { min: 0, max: 1, markerT, nowT: nowMs, color })
    );
    return section(title, canvas);
  }

  function evidence(
    prov: Provenance | undefined,
    extraRows?: [string, string][]
  ): HTMLElement {
    const rows: (HTMLElement | null)[] = [];
    if (prov) {
      const chipWrap = div('pi-kv');
      chipWrap.append(div('pi-kv-k', 'SOURCE'));
      const chip = document.createElement('span');
      chip.className = 'pi-chip';
      if (String(prov.source).startsWith('synthetic')) chip.classList.add('pi-chip-warn');
      chip.textContent = String(prov.source).toUpperCase();
      const holder = div('pi-kv-v');
      holder.append(chip);
      chipWrap.append(holder);
      rows.push(chipWrap);
      rows.push(kv('KNOWN AT', prov.knownAt.slice(0, 10)));
      if (prov.confidence !== undefined) rows.push(kv('CONFIDENCE', fmtPct(prov.confidence)));
    }
    for (const [k, v] of extraRows ?? []) rows.push(kv(k, v));
    return section('EVIDENCE', ...rows);
  }

  // ---------------------------------------------------------------- facility

  function renderFacility(f: Facility): void {
    const simT = api.clock.simTime;
    const s = api.store.stateAt(f.id, simT);

    const head = header(caps(f.kind), f.name);
    head.append(statusChip(s.status));
    content.append(head);

    // STATUS
    content.append(
      section(
        'STATUS',
        kv('STATUS', s.status.toUpperCase(), { tone: statusTone(s.status) }),
        meter('UTILIZATION', s.utilization, 'var(--accent)'),
        meter('CONGESTION', s.congestion, 'var(--warn)')
      )
    );

    // CAPACITY
    const x = f as Facility & {
      iata?: string;
      berths?: number;
      drafts?: number;
      portType?: string;
      areaSqm?: number;
      cargoTonnesPerYear?: number;
      intermodal?: boolean;
    };
    const capRows: (HTMLElement | null)[] = [];
    if (f.capacity) capRows.push(kv('CAPACITY', `${fmt(f.capacity.value)} ${f.capacity.unit}`));
    if (x.iata) capRows.push(kv('IATA', x.iata));
    if (x.berths !== undefined) capRows.push(kv('BERTHS', fmt(x.berths)));
    if (x.drafts !== undefined) capRows.push(kv('DRAFT', `${fmt(x.drafts, 1)} M`));
    if (x.portType) capRows.push(kv('TYPE', x.portType.toUpperCase()));
    if (x.areaSqm !== undefined) capRows.push(kv('AREA', `${fmt(x.areaSqm)} M²`));
    if (x.cargoTonnesPerYear !== undefined)
      capRows.push(kv('CARGO', `${fmt(x.cargoTonnesPerYear)} T/YR`));
    if (x.intermodal !== undefined) capRows.push(kv('INTERMODAL', x.intermodal ? 'YES' : 'NO'));
    if (f.operator) capRows.push(kv('OPERATOR', f.operator.toUpperCase()));
    if (capRows.length) content.append(section('CAPACITY', ...capRows));

    // CONNECTED TRANSPORT — grouped by mode
    const routes = api.store.routesOfNode(f.id);
    if (routes.length) {
      const holder = document.createElement('div');
      for (const mode of MODE_ORDER) {
        const inMode = routes.filter((r) => r.mode === mode);
        if (!inMode.length) continue;
        const label = div('pi-group-label');
        const dot = div('pi-dot');
        dot.style.background = MODE_COLOR[mode];
        label.append(dot, document.createTextNode(mode.toUpperCase()));
        holder.append(label);
        for (const r of inMode) {
          const otherId = r.originId === f.id ? r.destinationId : r.originId;
          const otherName = api.store.node(otherId)?.name ?? otherId;
          holder.append(
            entityRow(`→ ${otherName}`, {
              focusId: r.id,
              sub: `${fmt(r.distanceKm)} KM`,
            })
          );
        }
      }
      content.append(section('CONNECTED TRANSPORT', holder));
    }

    // ACTIVE FLOWS
    const flows = api.store.flowsTouchingNode(f.id);
    content.append(
      section(
        'ACTIVE FLOWS',
        ...(flows.length
          ? flows.map((fl) =>
              entityRow(fl.name, {
                focusId: fl.id,
                sub: api.store.commodity(fl.commodityId)?.name.toUpperCase() ?? '',
              })
            )
          : [empty('NO ACTIVE FLOWS')])
      )
    );

    // ACTIVE EVENTS
    const evts = s.activeEventIds
      .map((id) => api.store.snapshot.events.find((e) => e.id === id))
      .filter((e): e is WorldEvent => !!e);
    if (evts.length) content.append(section('ACTIVE EVENTS', ...evts.map(eventRow)));

    content.append(sparkSection(`UTILIZATION ${rangeDays()}D`, f.id) ?? empty(''));
    content.append(evidence(f.provenance));
  }

  // ---------------------------------------------------------------- route

  function renderRoute(r: Route): void {
    const simT = api.clock.simTime;
    const s = api.store.stateAt(r.id, simT);
    const modeColor = MODE_COLOR[r.mode];

    const head = header(`ROUTE · ${r.mode.toUpperCase()}`, r.name, { modeColor });
    const origin = api.store.node(r.originId);
    const dest = api.store.node(r.destinationId);
    const od = div('pi-od');
    const oEnd = div('pi-od-end', origin?.name ?? r.originId);
    oEnd.addEventListener('click', () => api.focus(r.originId));
    const dEnd = div('pi-od-end', dest?.name ?? r.destinationId);
    dEnd.addEventListener('click', () => api.focus(r.destinationId));
    od.append(oEnd, div('pi-od-arrow', '→'), dEnd);
    head.append(od, statusChip(s.status));
    content.append(head);

    content.append(
      section(
        'ROUTE',
        kv('DISTANCE', `${fmt(r.distanceKm)} KM`),
        kv('MODE', r.mode.toUpperCase()),
        kv('STATUS', s.status.toUpperCase(), { tone: statusTone(s.status) })
      )
    );

    // TRANSIT — the promise / evidence split
    const transitRows: (HTMLElement | null)[] = [
      kv('PROMISED', `${fmt(r.estimatedDurationHours)} H`),
    ];
    const range = api.store.snapshot.timeRange;
    // Scrubbing selects the knowledge cutoff. The event window stays explicit;
    // no observation at or after the selected cursor is included.
    const dev = simT === range.start || Date.parse(simT) <= Date.parse(range.start) ? undefined : api.store
      .deviationsFor(r.id, { knownAt: simT, from: range.start, to: simT })
      .find((d) => d.assertion.metric === 'transit_hours');
    if (dev?.status === 'ready' && dev.deviation && dev.meanObserved !== null) {
      transitRows.push(kv('OBSERVED μ', `${fmt(dev.meanObserved, 1)} ${dev.comparison.unit}`));
      const pct = dev.deviation.ratio === null ? null : (dev.deviation.ratio - 1) * 100;
      const over = pct !== null && pct > 5;
      transitRows.push(
        kv(
          'DEVIATION',
          pct === null ? 'UNDEFINED RATIO — ZERO ASSERTION' : `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% · records=${dev.observations.length}`,
          { tone: pct === null ? 'dim' : over ? 'warn' : 'ok' }
        )
      );
      transitRows.push(kv('INDEPENDENCE', 'NOT ESTABLISHED'));
      transitRows.push(kv('EXCLUDED RECORDS', String(dev.excluded.length)));
    } else if (dev) {
      transitRows.push(kv('COMPARISON', dev.reason ?? 'UNAVAILABLE', { tone: 'dim' }));
    }
    content.append(section('TRANSIT', ...transitRows));

    // CAPACITY + live utilization
    content.append(
      section(
        'CAPACITY',
        kv('RATED', `${fmt(r.capacity.value)} ${r.capacity.unit}`),
        meter('LIVE UTILIZATION', s.utilization, modeColor)
      )
    );

    // CONSTRAINTS
    if (r.constraints.length) {
      content.append(
        section('CONSTRAINTS', ...r.constraints.map((c) => constraintRow(c)))
      );
    }

    // FLOWS ON ROUTE
    const flows = api.store.flowsThroughRoute(r.id);
    content.append(
      section(
        'FLOWS ON ROUTE',
        ...(flows.length
          ? flows.map((fl) =>
              entityRow(fl.name, {
                focusId: fl.id,
                sub: api.store.commodity(fl.commodityId)?.name.toUpperCase() ?? '',
              })
            )
          : [empty('NO FLOWS ROUTED')])
      )
    );

    content.append(sparkSection('HISTORY', r.id, modeColor) ?? empty(''));
    content.append(evidence(r.provenance));
  }

  function constraintRow(c: RouteConstraint): HTMLElement {
    const wrap = div('pi-con');
    const head = div('pi-con-head');
    head.append(div('pi-con-type', caps(c.type)), div('pi-con-desc', c.description));
    wrap.append(head, sevBar(c.severity));
    if (c.type === 'chokepoint') {
      const target =
        api.store.node(c.id) ??
        api.store.snapshot.nodes.find(
          (n) =>
            n.kind === 'chokepoint' &&
            c.description.toLowerCase().includes(n.name.toLowerCase())
        );
      if (target) {
        wrap.classList.add('pi-click');
        wrap.addEventListener('click', () => api.focus(target.id));
      }
    }
    return wrap;
  }

  // ---------------------------------------------------------------- flow

  function renderFlow(fl: Flow): void {
    const head = header('LOAD', fl.name);
    head.append(statusChip(fl.status));
    content.append(head);

    const commodity = api.store.commodity(fl.commodityId);
    const origin = api.store.node(fl.originId);
    const dest = api.store.node(fl.destinationId);
    const modes = new Set(fl.segments.map((sg) => sg.mode));
    const modeLabel =
      modes.size > 1 ? 'MULTIMODAL' : (fl.segments[0]?.mode ?? 'unknown').toUpperCase();

    content.append(
      section(
        'LOAD',
        kv('COMMODITY', (commodity?.name ?? fl.commodityId).toUpperCase()),
        kv('ORIGIN', origin?.name ?? fl.originId, { focusId: fl.originId }),
        kv('DESTINATION', dest?.name ?? fl.destinationId, { focusId: fl.destinationId }),
        kv('MODE', modeLabel),
        kv('INTENSITY', fmtPct(fl.intensity)),
        kv('STATUS', fl.status.toUpperCase(), { tone: statusTone(fl.status) })
      )
    );

    // ROUTE CHAIN
    const steps: HTMLElement[] = [];
    let totalKm = 0;
    let totalH = 0;
    const ordered = [...fl.segments].sort((a, b) => a.sequence - b.sequence);
    for (const seg of ordered) {
      const route = api.store.route(seg.routeId);
      if (route) {
        totalKm += route.distanceKm;
        totalH += route.estimatedDurationHours;
      }
      const step = div('pi-step');
      step.style.borderLeftColor = MODE_COLOR[seg.mode];
      const mode = div('pi-step-mode', seg.mode.toUpperCase());
      mode.style.color = MODE_COLOR[seg.mode];
      const fromName = api.store.node(seg.fromNodeId)?.name ?? seg.fromNodeId;
      const toName = api.store.node(seg.toNodeId)?.name ?? seg.toNodeId;
      step.append(mode, div('pi-step-od', `${fromName} → ${toName}`));
      if (route) step.append(div('pi-step-dist', `${fmt(route.distanceKm)} KM`));
      step.addEventListener('click', () => api.focus(seg.routeId));
      steps.push(step);
    }
    content.append(
      section(
        'ROUTE CHAIN',
        ...steps,
        kv('TOTAL DISTANCE', `${fmt(totalKm)} KM`),
        kv('EST TRANSIT', `${fmt(totalH)} H`)
      )
    );

    content.append(evidence(fl.provenance));
  }

  // ---------------------------------------------------------------- country

  const CATEGORIES: [string, string[]][] = [
    ['PORTS', ['port']],
    ['AIRPORTS', ['airport']],
    ['TERMINALS', ['rail_terminal', 'trucking_hub', 'border_crossing']],
    ['WAREHOUSES', ['warehouse', 'distribution_center']],
    [
      'INDUSTRIAL',
      [
        'factory',
        'industrial_park',
        'manufacturing_cluster',
        'refinery',
        'smelter',
        'chemical_plant',
        'steel_mill',
        'processing_facility',
        'mine',
        'oil_field',
        'gas_field',
        'agricultural_region',
        'consumption_center',
      ],
    ],
  ];

  function renderCountry(code: string, name: string): void {
    const info = api.countryInfo(code);
    const head = header('COUNTRY', name);
    content.append(head);

    if (!info) {
      content.append(section('DATA', empty('NO CORPUS COVERAGE')));
      content.append(
        evidence(undefined, [
          ['GEOMETRY', 'Natural Earth via world-atlas'],
          ['STATS', 'derived from synthetic demo corpus'],
        ])
      );
      return;
    }

    // TRANSPORT — route counts per mode
    const transportRows: HTMLElement[] = [];
    for (const mode of MODE_ORDER) {
      const n = info.byMode[mode] ?? 0;
      if (!n) continue;
      transportRows.push(
        entityRow(mode.toUpperCase(), { dotColor: MODE_COLOR[mode], sub: `${n} ROUTES` })
      );
    }
    content.append(
      section(
        'TRANSPORT',
        ...(transportRows.length ? transportRows : [empty('NO ROUTES TOUCHING')])
      )
    );

    // INFRASTRUCTURE — expandable categories
    const infraKids: HTMLElement[] = [];
    for (const [label, kinds] of CATEGORIES) {
      const nodes = info.nodes.filter((n) => kinds.includes(n.kind));
      if (!nodes.length) continue;
      const catKey = `${code}:${label}`;
      const cat = div('pi-cat');
      const headBtn = document.createElement('button');
      headBtn.type = 'button';
      headBtn.className = 'pi-cat-head';
      const caret = div('pi-cat-caret', expandedCats.has(catKey) ? '▾' : '▸');
      headBtn.append(caret, document.createTextNode(label), div('pi-cat-count', fmt(nodes.length)));
      const bodyEl = div('pi-cat-body');
      bodyEl.hidden = !expandedCats.has(catKey);
      const shown = nodes.slice(0, 8);
      for (const n of shown) {
        bodyEl.append(entityRow(n.name, { focusId: n.id, sub: caps(n.kind) }));
      }
      if (nodes.length > 8) bodyEl.append(div('pi-more', `+${nodes.length - 8} more`));
      headBtn.addEventListener('click', () => {
        if (expandedCats.has(catKey)) expandedCats.delete(catKey);
        else expandedCats.add(catKey);
        bodyEl.hidden = !expandedCats.has(catKey);
        caret.textContent = expandedCats.has(catKey) ? '▾' : '▸';
      });
      cat.append(headBtn, bodyEl);
      infraKids.push(cat);
    }
    content.append(
      section(
        'INFRASTRUCTURE',
        ...(infraKids.length ? infraKids : [empty('NO MAPPED FACILITIES')])
      )
    );

    // ACTIVE FLOWS touching the country
    const nodeIds = new Set(info.nodes.map((n) => n.id));
    const flows = api.store.snapshot.flows.filter(
      (fl) => nodeIds.has(fl.originId) || nodeIds.has(fl.destinationId)
    );
    content.append(
      section(
        'ACTIVE FLOWS',
        ...(flows.length
          ? flows.map((fl) =>
              entityRow(fl.name, {
                focusId: fl.id,
                sub: api.store.commodity(fl.commodityId)?.name.toUpperCase() ?? '',
              })
            )
          : [empty('NO FLOWS TOUCHING')])
      )
    );

    // ACTIVE EVENTS in-country
    const inCountry = new Set<string>([
      ...info.nodes.map((n) => n.id),
      ...info.routes.map((r) => r.id),
    ]);
    const evts = api.store
      .activeEvents(api.clock.simTime)
      .filter((e) => e.affects.some((id) => inCountry.has(id)));
    if (evts.length) content.append(section('ACTIVE EVENTS', ...evts.map(eventRow)));

    content.append(
      evidence(undefined, [
        ['GEOMETRY', 'Natural Earth via world-atlas'],
        ['STATS', 'derived from synthetic demo corpus'],
      ])
    );
  }

  // ---------------------------------------------------------------- render

  function render(): void {
    if (!selectedId && !country) {
      el.classList.add('pi-hidden');
      return;
    }
    const scroll = el.scrollTop;
    content.replaceChildren();

    if (country) {
      renderCountry(country.code, country.name);
    } else if (selectedId) {
      const ent = api.store.entity(selectedId);
      if (!ent) {
        el.classList.add('pi-hidden');
        return;
      }
      if ('segments' in ent) renderFlow(ent);
      else if (ent.kind === 'route') renderRoute(ent as Route);
      else renderFacility(ent as Facility);
    }

    el.classList.remove('pi-hidden');
    el.scrollTop = scroll;
  }

  // ---------------------------------------------------------------- wiring

  api.events.on('select', ({ id }) => {
    selectedId = id;
    if (id) country = null;
    render();
  });

  api.events.on('countrySelect', ({ code, name }) => {
    country = code ? { code, name: name ?? code } : null;
    if (code) selectedId = null;
    render();
  });

  // re-render dynamic values while time moves, throttled to ~2 Hz with a
  // trailing render so the final state after a scrub burst always lands
  let lastTimeRender = 0;
  let trailing: number | undefined;
  api.events.on('time', () => {
    if (!selectedId && !country) return;
    const now = performance.now();
    if (now - lastTimeRender < 500) {
      if (trailing === undefined) {
        trailing = window.setTimeout(() => {
          trailing = undefined;
          lastTimeRender = performance.now();
          render();
        }, 520);
      }
      return;
    }
    lastTimeRender = now;
    render();
  });

  return { el };
}
