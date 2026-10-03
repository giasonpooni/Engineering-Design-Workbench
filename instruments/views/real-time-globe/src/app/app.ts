/**
 * The App: composition root of the digital twin client. Owns the
 * engine, layers, interaction, clock and selection state; implements
 * the AppApi facade that the UI instrument layer and demo controllers
 * consume. Rendering here is a projection of provider state — nothing
 * in this file (or below it) writes back into the data layer.
 */

import * as THREE from 'three';
import type {
  EntityId,
  Facility,
  Flow,
  Route,
  TemporalState,
} from '../data/contracts';
import { WorldStore, type SearchResult } from '../data/store';
import { SyntheticProvider } from '../data/synthetic/provider';
import { EventBus } from '../core/events';
import { SimClock } from '../core/time';
import { Engine } from '../core/engine';
import { CameraController } from '../core/cameraController';
import { Countries, type Country } from '../geo/countries';
import { generateEarthTextures } from '../geo/texture';
import { latLonToVec3, slerpSurface, vec3ToLatLon } from '../geo/projection';
import { Globe, sunDirectionAt } from '../earth/globe';
import { Atmosphere } from '../earth/atmosphere';
import { createStars } from '../earth/stars';
import { createGraticule } from '../earth/graticule';
import { LayerManager } from '../layers/layerManager';
import { RoutesLayer } from '../layers/routesLayer';
import { NodesLayer } from '../layers/nodesLayer';
import { FlowsLayer } from '../layers/flowsLayer';
import { LabelsLayer } from '../layers/labelsLayer';
import { SelectionInput, type Pick } from '../interaction/selection';
import { FollowTheLoad } from '../interaction/followTheLoad';
import { executeCommand, suggestCommands } from './commands';
import type {
  AppApi,
  AppEvents,
  CameraFacade,
  CommandResult,
  CountryInfo,
  LayerDef,
  LayerId,
  Suggestion,
  ViewPreset,
} from './api';

export class App implements AppApi {
  readonly events = new EventBus<AppEvents>();
  readonly store = new WorldStore();
  readonly clock = new SimClock();
  camera!: CameraFacade;

  private engine!: Engine;
  private cameraCtl!: CameraController;
  private countries!: Countries;
  private globe!: Globe;
  private atmosphere!: Atmosphere;
  private graticule!: THREE.LineSegments;
  private borders!: THREE.LineSegments;
  private layerMgr = new LayerManager();
  private routesLayer!: RoutesLayer;
  private nodesLayer!: NodesLayer;
  private flowsLayer!: FlowsLayer;
  private labelsLayer!: LabelsLayer;
  private anomalies!: THREE.Points;
  private anomaliesMat!: THREE.PointsMaterial;
  private depOverlay = new THREE.Group();
  private demo!: FollowTheLoad;

  private preset: ViewPreset = 'world';
  private selection: EntityId | null = null;
  /** Routes highlighted by the current selection (a route, or a flow's legs). */
  private selectedRouteIds = new Set<EntityId>();
  private hoverId: EntityId | null = null;
  private selectedCountry: Country | null = null;
  private countryOutline: THREE.Object3D | null = null;
  private activeEventIds = new Set<EntityId>();
  private lastTemporalRefresh = 0;
  private lastSimMs = 0;

  // ------------------------------------------------------------------ boot

  async boot(canvas: HTMLCanvasElement, hud: HTMLElement): Promise<void> {
    const progress = (pct: number, msg: string) => {
      const fill = document.getElementById('boot-fill');
      const status = document.getElementById('boot-status');
      if (fill) fill.style.width = `${pct}%`;
      if (status) status.textContent = msg;
    };

    progress(8, 'LOADING SYNTHETIC CORPUS');
    const snapshot = await this.store.init(new SyntheticProvider());

    progress(24, 'LOADING WORLD TOPOLOGY');
    const [countries, textures] = await Promise.all([
      Countries.load('data/countries-110m.json'),
      generateEarthTextures('data/land-50m.json', snapshot.cityLights),
    ]);
    this.countries = countries;

    progress(52, 'BUILDING PLANET');
    this.engine = new Engine(canvas);
    const scene = this.engine.scene;
    this.globe = new Globe(textures);
    this.atmosphere = new Atmosphere();
    scene.add(this.globe.mesh, this.atmosphere.mesh, createStars());
    this.graticule = createGraticule();
    this.graticule.visible = false;
    scene.add(this.graticule);
    this.borders = countries.buildBorders();
    scene.add(this.borders);

    progress(70, 'PROJECTING NETWORK');
    this.routesLayer = new RoutesLayer(snapshot.routes);
    scene.add(this.routesLayer.group);
    this.nodesLayer = new NodesLayer(snapshot.nodes);
    scene.add(this.nodesLayer.points);
    const routeIx = new Map(snapshot.routes.map((r) => [r.id, r]));
    this.flowsLayer = new FlowsLayer(snapshot.flows, routeIx, this.routesLayer);
    scene.add(this.flowsLayer.group);
    this.labelsLayer = new LabelsLayer(hud);
    scene.add(this.depOverlay);
    this.buildAnomalies();
    scene.add(this.anomalies);

    progress(84, 'CALIBRATING INSTRUMENTS');
    this.cameraCtl = new CameraController(this.engine.camera, canvas);
    this.camera = this.buildCameraFacade();
    this.registerLayers();
    this.wireSelection(canvas);
    this.demo = new FollowTheLoad(this);
    // a drag or wheel during the demo hands control back to the user
    // instead of letting the script fight them for the camera
    this.cameraCtl.onInteract = () => {
      if (this.demo.active) {
        this.demo.stop();
        this.events.emit('toast', {
          title: 'DEMO EXITED',
          body: 'Camera control returned.',
          tone: 'info',
        });
      }
    };

    // temporal spine
    this.clock.configure(
      snapshot.timeRange.start,
      snapshot.timeRange.end,
      snapshot.timeRange.now
    );
    this.lastSimMs = this.clock.simMillis;
    this.clock.events.on('change', (t) => this.onTimeChange(t));
    this.updateSun(this.clock.simMillis);
    this.refreshTemporalStates(true);

    // frame loop
    this.engine.onFrame((dt) => {
      this.clock.tick(dt);
      this.cameraCtl.update(dt);
      const alt = this.cameraCtl.altitudeRadii();
      this.routesLayer.setAltitude(alt);
      this.nodesLayer.setAltitude(alt);
      this.routesLayer.update(dt);
      this.nodesLayer.update(dt);
      this.flowsLayer.update(dt);
      this.labelsLayer.update(this.engine.camera, this.nodesLayer, alt);
      this.pulseAnomalies(dt);
    });
    this.engine.start();

    // status heartbeat
    setInterval(() => {
      this.events.emit('status', {
        fps: Math.round(this.engine.fps),
        altitudeKm: this.cameraCtl.altitudeRadii() * 6371,
        visibleNodes: this.nodesLayer.visibleCount,
        visibleRoutes: this.routesLayer.visibleCount,
        particles: this.flowsLayer.visible ? this.flowsLayer.particleCount : 0,
      });
    }, 500);

    progress(100, 'ONLINE');
    // cinematic arrival: pull in from deep space toward the Atlantic seam
    setTimeout(() => {
      const boot = document.getElementById('boot');
      boot?.classList.add('done');
      // hard-remove after the fade so nothing depends on CSS transitions
      setTimeout(() => boot?.remove(), 900);
      this.cameraCtl.flyToLatLon(28, -42, { distance: 2.75, durationMs: 3200 });
      this.cameraCtl.setAutoRotate(true);
    }, 250);
  }

  // ------------------------------------------------------------- rendering aux

  private buildAnomalies(): void {
    const c = document.createElement('canvas');
    c.width = c.height = 48;
    const ctx = c.getContext('2d')!;
    ctx.strokeStyle = 'rgba(255,93,110,0.9)';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(24, 24, 14, 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,93,110,0.35)';
    ctx.beginPath();
    ctx.arc(24, 24, 20, 0, Math.PI * 2);
    ctx.stroke();
    this.anomaliesMat = new THREE.PointsMaterial({
      size: 22,
      map: new THREE.CanvasTexture(c),
      transparent: true,
      sizeAttenuation: false,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.anomalies = new THREE.Points(new THREE.BufferGeometry(), this.anomaliesMat);
    this.anomalies.renderOrder = 8;
    this.anomalies.visible = false;
  }

  private rebuildAnomalies(): void {
    const positions: number[] = [];
    for (const ev of this.store.activeEvents(this.clock.simTime)) {
      for (const id of ev.affects) {
        const node = this.store.node(id);
        if (node) {
          const [lon, lat] = node.geometry.coordinates;
          const p = latLonToVec3(lat, lon, 1.01);
          positions.push(p.x, p.y, p.z);
          continue;
        }
        const vis = this.routesLayer.visuals.get(id);
        if (vis) {
          const mid = vis.path.points[Math.floor(vis.path.points.length / 2)];
          positions.push(mid.x * 1.008, mid.y * 1.008, mid.z * 1.008);
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    this.anomalies.geometry.dispose();
    this.anomalies.geometry = geo;
  }

  private anomalyPulse = 0;
  private pulseAnomalies(dt: number): void {
    if (!this.anomalies.visible) return;
    this.anomalyPulse += dt;
    this.anomaliesMat.opacity = 0.55 + 0.45 * Math.sin(this.anomalyPulse * 3.5);
  }

  private rebuildDependencyOverlay(): void {
    this.depOverlay.clear();
    if (!this.layerMgr.isVisible('intel.dependencies') || !this.selection) return;
    const node = this.store.node(this.selection);
    if (!node) return;
    const [lon0, lat0] = node.geometry.coordinates;
    const from = latLonToVec3(lat0, lon0, 1);
    const addArcs = (ids: EntityId[] | undefined, color: number) => {
      if (!ids?.length) return;
      const positions: number[] = [];
      for (const id of ids) {
        const other = this.store.node(id);
        if (!other) continue;
        const [lon1, lat1] = other.geometry.coordinates;
        const to = latLonToVec3(lat1, lon1, 1);
        const steps = 36;
        const v = new THREE.Vector3();
        const prev = new THREE.Vector3();
        for (let i = 0; i <= steps; i++) {
          const t = i / steps;
          slerpSurface(from, to, t, 1.012 + Math.sin(t * Math.PI) * 0.02, v);
          if (i > 0) positions.push(prev.x, prev.y, prev.z, v.x, v.y, v.z);
          prev.copy(v);
        }
      }
      if (!positions.length) return;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      const mat = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity: 0.5,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const lines = new THREE.LineSegments(geo, mat);
      lines.renderOrder = 8;
      this.depOverlay.add(lines);
    };
    addArcs(node.connectedSupplierIds, 0x8fa3b8);
    addArcs(node.connectedCustomerIds, 0x4da6ff);
  }

  // ------------------------------------------------------------------ layers

  private registerLayers(): void {
    const m = this.layerMgr;
    m.onChange = (layers) => this.events.emit('layersChange', { layers });

    m.register('world.countries', (v) => (this.borders.visible = v));
    m.register('world.terrain', (v) => (this.graticule.visible = v));
    m.register('world.nightlights', (v) => this.globe.setNightLights(v ? 1 : 0));
    m.register('world.cities', (v) => {
      this.labelsLayer.setEnabled(v);
      this.nodesLayer.setBucketVisible('world.cities', v);
    });
    for (const mode of ['road', 'rail', 'maritime', 'air'] as const) {
      m.register(`transport.${mode}` as LayerId, (v) =>
        this.routesLayer.setModeVisible(mode, v)
      );
    }
    for (const bucket of [
      'infra.ports',
      'infra.airports',
      'infra.rail_terminals',
      'infra.warehouses',
      'infra.industrial',
      'intel.bottlenecks',
    ] as const) {
      m.register(bucket as LayerId, (v) => this.nodesLayer.setBucketVisible(bucket, v));
    }
    m.register('economy.production', (v) => this.nodesLayer.setEmphasis('production', v));
    m.register('economy.demand', (v) => this.nodesLayer.setEmphasis('demand', v));
    m.register('economy.inventory', (v) => this.nodesLayer.setEmphasis('inventory', v));
    m.register('economy.flows', (v) => {
      this.flowsLayer.setVisible(v);
      this.events.emit('flowMode', { enabled: v });
    });
    m.register('intel.constraints', (v) => this.routesLayer.setConstraintsVisible(v));
    m.register('intel.anomalies', (v) => {
      this.anomalies.visible = v;
      if (v) this.rebuildAnomalies();
    });
    m.register('intel.dependencies', () => this.rebuildDependencyOverlay());
    m.register('intel.risk', (v) => this.routesLayer.setRiskMode(v));
  }

  // ------------------------------------------------------------------ time

  private onTimeChange(t: TemporalState): void {
    this.events.emit('time', t);
    this.updateSun(this.clock.simMillis);
    const now = performance.now();
    if (now - this.lastTemporalRefresh > 150) {
      this.lastTemporalRefresh = now;
      this.refreshTemporalStates(false);
    }
    this.lastSimMs = this.clock.simMillis;
  }

  private updateSun(simMillis: number): void {
    const dir = sunDirectionAt(simMillis);
    this.globe.setSunDirection(dir);
    this.atmosphere.setSunDirection(dir);
  }

  private refreshTemporalStates(initial: boolean): void {
    const t = this.clock.simTime;
    for (const route of this.store.snapshot.routes) {
      const s = this.store.stateAt(route.id, t);
      this.routesLayer.setTemporalState(route.id, s.utilization, s.congestion, s.status);
    }
    if (this.anomalies.visible) this.rebuildAnomalies();

    // event toasts: only on smooth advance (playback), not on scrub jumps
    const jump = Math.abs(this.clock.simMillis - this.lastSimMs);
    const smooth = jump < this.clock.speed * 3000;
    const current = new Set(this.store.activeEvents(t).map((e) => e.id));
    if (!initial && smooth) {
      for (const ev of this.store.activeEvents(t)) {
        if (!this.activeEventIds.has(ev.id)) {
          this.events.emit('toast', {
            title: ev.name.toUpperCase(),
            body: ev.description,
            tone: ev.severity > 0.6 ? 'alert' : 'warn',
          });
        }
      }
    }
    this.activeEventIds = current;
  }

  // ------------------------------------------------------------------ camera

  private buildCameraFacade(): CameraFacade {
    const ctl = this.cameraCtl;
    const routes = () => this.routesLayer;
    return {
      flyToLatLon: (lat, lon, opts) => ctl.flyToLatLon(lat, lon, opts),
      frameRoute: async (routeId, opts) => {
        const vis = routes().visuals.get(routeId);
        if (!vis) return;
        const pts = vis.path.points;
        const mid = pts[Math.floor(pts.length / 2)];
        const ll = vec3ToLatLon(mid);
        const extent = vis.path.totalAngle;
        const distance = THREE.MathUtils.clamp(1 + extent * 1.35, 1.14, 3.6);
        await ctl.flyToLatLon(ll.lat, ll.lon, {
          distance,
          durationMs: opts?.durationMs ?? 1900,
        });
      },
      followPath: (coords, opts) => ctl.followPath(coords, opts),
      cancel: () => ctl.cancel(),
      altitudeRadii: () => ctl.altitudeRadii(),
      setAutoRotate: (v) => ctl.setAutoRotate(v),
    };
  }

  // ------------------------------------------------------------- interaction

  private wireSelection(canvas: HTMLCanvasElement): void {
    const input = new SelectionInput(
      canvas,
      this.engine.camera,
      this.nodesLayer,
      this.routesLayer,
      this.globe.mesh,
      this.countries
    );
    input.onHover = (pick) => this.applyHover(pick);
    input.onClick = (pick) => {
      if (this.demo.active) return;
      if (!pick) {
        this.select(null, 'pick');
        this.selectCountry(null);
        return;
      }
      if (pick.type === 'country') {
        this.select(null, 'pick');
        this.selectCountryObj(pick.country);
      } else {
        this.selectCountry(null);
        this.select(pick.id, 'pick');
      }
    };
    input.onDoubleClick = (pick) => {
      if (this.demo.active || !pick || pick.type === 'country') return;
      this.focus(pick.id);
    };
  }

  private applyHover(pick: Pick): void {
    const id = pick && pick.type !== 'country' ? pick.id : null;
    if (id === this.hoverId) return;
    // restore old hover to its selection-aware baseline, never to bare 0
    if (this.hoverId && this.hoverId !== this.selection) {
      if (this.store.node(this.hoverId)) this.nodesLayer.setState(this.hoverId, 0);
      if (this.store.route(this.hoverId)) {
        this.routesLayer.setState(this.hoverId, this.selectedRouteIds.has(this.hoverId) ? 2 : 0);
      }
    }
    this.hoverId = id;
    if (id && id !== this.selection && !this.selectedRouteIds.has(id)) {
      if (this.store.node(id)) this.nodesLayer.setState(id, 1);
      if (this.store.route(id)) this.routesLayer.setState(id, 1);
    }
    document.body.style.cursor = id ? 'pointer' : 'default';
    this.events.emit('hover', { id });
  }

  // ------------------------------------------------------------------ AppApi

  getLayers(): LayerDef[] {
    return this.layerMgr.list();
  }

  setLayerVisible(id: LayerId, visible: boolean): void {
    this.layerMgr.setVisible(id, visible);
    if (id === 'intel.dependencies') this.rebuildDependencyOverlay();
  }

  setPreset(preset: ViewPreset): void {
    this.preset = preset;
    this.layerMgr.applyPreset(preset);
    this.routesLayer.setDimUndisturbed(this.layerMgr.presetDimsHealthy(preset));
    this.events.emit('preset', { preset });
    this.events.emit('flowMode', { enabled: this.getFlowMode() });
  }

  getPreset(): ViewPreset {
    return this.preset;
  }

  setFlowMode(enabled: boolean): void {
    this.layerMgr.setVisible('economy.flows', enabled);
  }

  getFlowMode(): boolean {
    return this.layerMgr.isVisible('economy.flows');
  }

  select(id: EntityId | null, source: AppEvents['select']['source'] = 'ui'): void {
    if (id && !this.store.entity(id)) id = null;
    this.selection = id;

    // reset highlight states
    const selectedRoutes = new Set<EntityId>();
    let selectedNode: EntityId | undefined;
    let selectedFlow: EntityId | null = null;
    if (id) {
      const flow = this.store.flow(id);
      if (flow) {
        selectedFlow = flow.id;
        for (const seg of flow.segments) selectedRoutes.add(seg.routeId);
      }
      if (this.store.route(id)) selectedRoutes.add(id);
      if (this.store.node(id)) selectedNode = id;
    }
    this.selectedRouteIds = selectedRoutes;
    this.routesLayer.clearStates(selectedRoutes);
    this.nodesLayer.clearStates(selectedNode);
    this.flowsLayer.setSelectedFlow(selectedFlow);
    this.labelsLayer.setSelected(selectedNode ?? null);
    this.rebuildDependencyOverlay();
    this.events.emit('select', { id, source });
  }

  getSelection(): EntityId | null {
    return this.selection;
  }

  /**
   * Countries outside the ISO alpha-2 table still get a stable code of
   * the form '#<numeric-id>' so selection, the inspector, and lookups
   * work for every polygon on the globe, not just corpus countries.
   */
  private countryCode(c: Country): string {
    return c.iso2 ?? `#${c.id}`;
  }

  private resolveCountry(code: string): Country | undefined {
    if (code.startsWith('#')) {
      const id = Number(code.slice(1));
      return this.countries.countries.find((c) => c.id === id);
    }
    return this.countries.byIso2(code);
  }

  getSelectedCountry(): { code: string; name: string } | null {
    if (!this.selectedCountry) return null;
    return { code: this.countryCode(this.selectedCountry), name: this.selectedCountry.name };
  }

  selectCountry(code: string | null): void {
    if (code === null) {
      this.selectCountryObj(null);
      return;
    }
    const c = this.resolveCountry(code);
    if (c) this.selectCountryObj(c, true);
  }

  private selectCountryObj(country: Country | null, fly = false): void {
    if (this.countryOutline) {
      this.engine.scene.remove(this.countryOutline);
      this.countryOutline = null;
    }
    this.selectedCountry = country;
    if (country) {
      this.countryOutline = this.countries.buildOutline(country);
      this.engine.scene.add(this.countryOutline);
      if (fly) {
        const c = this.countries.centroidOf(country);
        this.cameraCtl.flyToLatLon(c.lat, c.lon, { distance: 2.1, durationMs: 1600 });
      }
    }
    this.events.emit('countrySelect', {
      code: country ? this.countryCode(country) : null,
      name: country?.name ?? null,
    });
  }

  focus(id: EntityId): void {
    const node = this.store.node(id);
    if (node) {
      this.select(id, 'search');
      const [lon, lat] = node.geometry.coordinates;
      this.cameraCtl.flyToLatLon(lat, lon, {
        distance: 1.45 - node.importance * 0.18,
        durationMs: 1900,
      });
      return;
    }
    const route = this.store.route(id);
    if (route) {
      this.select(id, 'search');
      void this.camera.frameRoute(id);
      return;
    }
    const flow = this.store.flow(id);
    if (flow) {
      this.select(id, 'search');
      // frame the whole chain: vector-mean center + max angular extent
      const center = new THREE.Vector3();
      const pts: THREE.Vector3[] = [];
      for (const seg of flow.segments) {
        const vis = this.routesLayer.visuals.get(seg.routeId);
        if (!vis) continue;
        for (let i = 0; i < vis.path.points.length; i += 8) pts.push(vis.path.points[i]);
      }
      if (!pts.length) return;
      for (const p of pts) center.add(p);
      center.normalize();
      let extent = 0;
      for (const p of pts) extent = Math.max(extent, center.angleTo(p.clone().normalize()));
      const ll = vec3ToLatLon(center);
      this.cameraCtl.flyToLatLon(ll.lat, ll.lon, {
        distance: THREE.MathUtils.clamp(1 + extent * 2.4, 1.2, 4.2),
        durationMs: 2100,
      });
    }
  }

  countryInfo(code: string): CountryInfo | null {
    const country = this.resolveCountry(code);
    if (!country) return null;
    // corpus aggregates key off ISO-2; unmapped countries report empty
    // inventories rather than failing to open at all
    const iso2 = country.iso2 ?? '~none';
    const nodes = this.store.nodesInCountry(iso2);
    const routes = this.store.routesTouchingCountry(iso2);
    const nodeIds = new Set(nodes.map((n) => n.id));
    const flows = this.store.snapshot.flows.filter(
      (f) => nodeIds.has(f.originId) || nodeIds.has(f.destinationId)
    );
    const byMode: Record<string, number> = {};
    for (const r of routes) byMode[r.mode] = (byMode[r.mode] ?? 0) + 1;
    return { code, name: country.name, nodes, routes, flows, byMode };
  }

  runCommand(input: string): CommandResult {
    return executeCommand(this, input);
  }

  suggest(input: string): Suggestion[] {
    return suggestCommands(this, input);
  }

  search(q: string): SearchResult[] {
    return this.store.search(q);
  }

  startFollowTheLoad(): void {
    void this.demo.start();
  }

  stopFollowTheLoad(): void {
    this.demo.stop();
  }

  isDemoActive(): boolean {
    return this.demo.active;
  }
}

export type { Facility, Flow, Route };
