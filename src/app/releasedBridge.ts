import { BRIDGE_SCHEMA, bridgeMessage, parsePublicProjectionSpec, safeHttpUrl,
  validatePublicProjection, drawablePositions, ProjectionRefusal, type PublicProjection } from '../data/esmProjection';
import { mountReleasedViewer } from './releasedViewer';

const status = document.getElementById('status')!;
const viewport = document.getElementById('viewport')!;
const context = document.getElementById('context')!;
const params = new URLSearchParams(location.hash.slice(1));
let origin = '', channel = '';
try {
  const url = safeHttpUrl(params.get('parentOrigin') ?? '');
  if (url.pathname !== '/' || window.parent === window) throw new Error();
  origin = url.origin; channel = params.get('channel') ?? '';
  if (!/^[a-f0-9]{32}$/.test(channel)) throw new Error();
} catch { status.textContent = 'NOT CONNECTED · Open this read-only view from the Notation Systems explorer.'; }
if (origin && /^[a-f0-9]{32}$/.test(channel)) {
  let active: PublicProjection | null = null;
  let viewer: ReturnType<typeof mountReleasedViewer> | null = null;
  let revision = 0, disposed = false;
  const send = (type: string, payload: Record<string, unknown> = {}) =>
    window.parent.postMessage({ schema: BRIDGE_SCHEMA, channel, type, ...payload }, origin);
  const select = (recordId: string | null) => send('selected', { recordId, digest: active?.digest });
  const receive = async (event: MessageEvent) => {
    if (event.origin !== origin || event.source !== window.parent || disposed) return;
    const msg = event.data;
    if (bridgeMessage(msg, channel, 'load')) {
      const ticket = ++revision;
      try {
        const spec = parsePublicProjectionSpec(msg.spec);
        const next = await validatePublicProjection(msg.projection, { spec, digest: msg.digest as string });
        if (disposed || ticket !== revision) return;
        if (viewer) viewer.setProjection(next); else viewer = mountReleasedViewer(viewport, next, select);
        active = next;
        const drawn = drawablePositions(next).length;
        status.textContent = `FIXTURE ONLY · ${drawn} declared point markers · ${next.geometry.unplaced.length} records without geometry`;
        context.textContent = `Release ${next.spec.source.releaseId} | known at ${next.spec.selection.knownAt} | valid at ${next.spec.selection.validAt}\n${next.digest}\nGSV / Three.js point inspection. Source routing hint: ${next.engine}. Non-point shapes remain in the host inspector; no state, execution or admission is inferred.`;
        send('loaded', { digest: next.digest, pointCount: drawn });
      } catch (error) {
        if (disposed || ticket !== revision) return;
        const code = error instanceof ProjectionRefusal ? error.code : 'VIEW_UNAVAILABLE';
        status.textContent = `REFUSED · ${code}${active ? ' · Previous projection remains active' : ''}`;
        send('refused', { code, activeDigest: active?.digest ?? null });
      }
    } else if (bridgeMessage(msg, channel, 'select') && active && msg.digest === active.digest &&
      (msg.recordId === null || (typeof msg.recordId === 'string' && active.records.some(r => r.recordId === msg.recordId)))) {
      viewer?.setSelection(msg.recordId as string | null);
    }
  };
  const dispose = () => { disposed = true; revision++; window.removeEventListener('message', receive); viewer?.dispose(); };
  window.addEventListener('message', receive);
  window.addEventListener('pagehide', dispose, { once: true });
  status.textContent = 'WAITING · No dataset loaded';
  send('ready');
}
