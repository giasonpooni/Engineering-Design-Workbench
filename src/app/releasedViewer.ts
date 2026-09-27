/** ESM record projection view. Uses the existing engine and geographic convention.
 * Records are not relabelled as facilities or supplied with invented operational state.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Engine } from '../core/engine';
import { createGraticule } from '../earth/graticule';
import { latLonToVec3 } from '../geo/projection';
import { drawablePositions, type PublicProjection } from '../data/esmProjection';

export function mountReleasedViewer(container: HTMLElement, initial: PublicProjection,
  onSelection: (recordId: string | null) => void) {
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
  canvas.setAttribute('aria-label', 'Read-only geographic record points; use the host table for keyboard selection');
  container.append(canvas);
  let engine: Engine;
  try { engine = new Engine(canvas, container); } catch (error) { canvas.remove(); throw error; }
  const controls = new OrbitControls(engine.camera, canvas);
  controls.enableDamping = true; controls.enablePan = false; controls.minDistance = 1.15; controls.maxDistance = 8;
  const globeGeometry = new THREE.SphereGeometry(1, 64, 32);
  const globeMaterial = new THREE.MeshBasicMaterial({ color: 0x101d2e });
  const globe = new THREE.Mesh(globeGeometry, globeMaterial);
  const grid = createGraticule(1.002);
  (grid.material as THREE.LineBasicMaterial).opacity = 0.4;
  engine.scene.add(globe, grid);
  const pointGeometry = new THREE.SphereGeometry(0.009, 10, 8);
  const normal = new THREE.MeshBasicMaterial({ color: 0x73cce3 });
  const highlight = new THREE.MeshBasicMaterial({ color: 0xffcf76 });
  let group = new THREE.Group(); engine.scene.add(group);
  let projection = initial, selected: string | null = null, disposed = false;
  const markers = new Map<THREE.Object3D, string>();
  const frameOff = engine.onFrame(() => controls.update());
  function setProjection(next: PublicProjection) {
    if (disposed) return;
    const nextGroup = new THREE.Group(), nextMarkers = new Map<THREE.Object3D, string>();
    for (const pos of drawablePositions(next)) {
      const marker = new THREE.Mesh(pointGeometry, normal);
      latLonToVec3(pos.point.latitude, pos.point.longitude, 1.012, marker.position);
      nextGroup.add(marker); nextMarkers.set(marker, pos.recordId);
    }
    engine.scene.remove(group); group.clear(); group = nextGroup; engine.scene.add(group);
    markers.clear(); nextMarkers.forEach((id, obj) => markers.set(obj, id));
    projection = next;
    if (!next.records.some(r => r.recordId === selected)) selected = null;
    setSelection(selected);
  }
  function setSelection(recordId: string | null) {
    if (disposed) return;
    if (recordId !== null && !projection.records.some(r => r.recordId === recordId)) throw new Error('Unknown record selection');
    selected = recordId;
    let focused = false;
    for (const [marker, id] of markers) {
      (marker as THREE.Mesh).material = id === selected ? highlight : normal;
      if (!focused && id === selected) {
        engine.camera.position.copy(marker.position).normalize().multiplyScalar(3.2);
        controls.target.set(0, 0, 0); controls.update(); focused = true;
      }
    }
  }
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let down: { x: number; y: number } | null = null;
  const pointerDown = (event: PointerEvent) => { down = { x: event.clientX, y: event.clientY }; };
  const pointerUp = (event: PointerEvent) => {
    if (!down || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 4) { down = null; return; }
    down = null;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    engine.camera.updateMatrixWorld(); engine.scene.updateMatrixWorld(true);
    ray.setFromCamera(pointer, engine.camera);
    // The opaque globe participates in picking: far-side points cannot win.
    const hit = ray.intersectObjects([globe, ...markers.keys()], false)[0];
    const id = hit ? markers.get(hit.object) ?? null : null;
    setSelection(id); onSelection(id);
  };
  const cancel = () => { down = null; };
  canvas.addEventListener('pointerdown', pointerDown); canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointercancel', cancel);
  setProjection(initial); engine.start();
  return {
    setProjection, setSelection, resize: () => engine.resize(),
    dispose() {
      if (disposed) return; disposed = true;
      canvas.removeEventListener('pointerdown', pointerDown); canvas.removeEventListener('pointerup', pointerUp);
      canvas.removeEventListener('pointercancel', cancel);
      frameOff(); controls.dispose(); group.clear(); markers.clear();
      pointGeometry.dispose(); normal.dispose(); highlight.dispose(); globeGeometry.dispose(); globeMaterial.dispose();
      grid.geometry.dispose(); (grid.material as THREE.Material).dispose();
      engine.scene.clear(); engine.dispose(); canvas.remove();
    },
  };
}
