/** Shared WebGL render engine with an optional container-sized lifecycle. */
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
export type FrameCallback = (dt: number, elapsed: number) => void;
export class Engine {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene: THREE.Scene;
  readonly camera: THREE.PerspectiveCamera;
  readonly canvas: HTMLCanvasElement;
  private composer: EffectComposer;
  private bloom: UnrealBloomPass;
  private output: OutputPass;
  private renderPass: RenderPass;
  private callbacks = new Set<FrameCallback>();
  private clock = new THREE.Clock();
  private running = false;
  private disposed = false;
  private animation: number | null = null;
  private viewport?: HTMLElement;
  private observer?: ResizeObserver;
  private frames = 0;
  private fpsAccum = 0;
  fps = 60;
  private handleResize = () => this.resize();
  private handleVisibility = () => {
    if (document.hidden) this.clock.stop();
    else if (this.running) this.clock.start();
  };
  /** Omitting viewport preserves the existing standalone window-sized app. */
  constructor(canvas: HTMLCanvasElement, viewport?: HTMLElement) {
    this.canvas = canvas; this.viewport = viewport;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance', alpha: false });
    this.renderer.setClearColor(0x020409, 1);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 120);
    this.camera.position.set(0, 0.6, 4.4);
    this.renderPass = new RenderPass(this.scene, this.camera);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.55, 0.75, 0.82);
    this.output = new OutputPass();
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(this.renderPass); this.composer.addPass(this.bloom); this.composer.addPass(this.output);
    this.resize();
    window.addEventListener('resize', this.handleResize);
    document.addEventListener('visibilitychange', this.handleVisibility);
    if (viewport && typeof ResizeObserver !== 'undefined') {
      this.observer = new ResizeObserver(this.handleResize); this.observer.observe(viewport);
    }
  }
  resize(): void {
    if (this.disposed) return;
    const rect = this.viewport?.getBoundingClientRect();
    const w = Math.max(1, rect ? rect.width : window.innerWidth);
    const h = Math.max(1, rect ? rect.height : window.innerHeight);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.renderer.setPixelRatio(dpr); this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(dpr); this.composer.setSize(w, h);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  onFrame(cb: FrameCallback): () => void {
    if (this.disposed) throw new Error('Engine is disposed');
    this.callbacks.add(cb); return () => { this.callbacks.delete(cb); };
  }
  start(): void {
    if (this.disposed) throw new Error('Engine is disposed');
    if (this.running) return;
    this.running = true; this.clock.start();
    const loop = () => {
      if (!this.running) return;
      this.animation = requestAnimationFrame(loop);
      if (document.hidden) return;
      const dt = Math.min(this.clock.getDelta(), 0.1), elapsed = this.clock.elapsedTime;
      for (const cb of this.callbacks) cb(dt, elapsed);
      this.composer.render(); this.fpsAccum += dt; this.frames++;
      if (this.fpsAccum >= 0.5) { this.fps = this.frames / this.fpsAccum; this.frames = 0; this.fpsAccum = 0; }
    };
    this.animation = requestAnimationFrame(loop);
  }
  stop(): void {
    this.running = false; this.clock.stop();
    if (this.animation !== null) cancelAnimationFrame(this.animation);
    this.animation = null;
  }
  /** Scene objects remain caller-owned; dispose their geometry/materials first. */
  dispose(): void {
    if (this.disposed) return;
    this.stop(); this.disposed = true; this.callbacks.clear();
    this.observer?.disconnect();
    window.removeEventListener('resize', this.handleResize);
    document.removeEventListener('visibilitychange', this.handleVisibility);
    this.bloom.dispose(); this.output.dispose(); this.renderPass.dispose();
    this.composer.dispose(); this.renderer.dispose();
  }
}
