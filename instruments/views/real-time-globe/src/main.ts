/**
 * Entry point: boot the geographic state client, mount the instrument HUD, expose the
 * structured tool surface for future agent bindings.
 */

import './ui/theme.css';
import './ui/inspect.css';
import { App } from './app/app';
import { buildToolSurface } from './app/toolSurface';
import { createCommandBar } from './ui/commandBar';
import { createLayerPanel } from './ui/layerPanel';
import { createStatusBar } from './ui/statusBar';
import { createToasts } from './ui/toasts';
import { createInfoPanel } from './ui/infoPanel';
import { createTimeline } from './ui/timeline';

async function start(): Promise<void> {
  const canvas = document.getElementById('scene') as HTMLCanvasElement;
  const hud = document.getElementById('hud') as HTMLElement;

  const app = new App();
  try {
    await app.boot(canvas, hud);
  } catch (err) {
    const status = document.getElementById('boot-status');
    if (status) status.textContent = `BOOT FAILED — ${String(err)}`;
    throw err;
  }

  // instrument layer
  hud.appendChild(createCommandBar(app).el);
  hud.appendChild(createLayerPanel(app).el);
  hud.appendChild(createStatusBar(app).el);
  hud.appendChild(createToasts(app).el);
  hud.appendChild(createInfoPanel(app).el);
  hud.appendChild(createTimeline(app).el);

  // escape: exit demo, else clear selection — but never while typing
  // (the search box owns Escape for its own dropdown/blur)
  window.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const ae = document.activeElement as HTMLElement | null;
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.isContentEditable)) return;
    if (app.isDemoActive()) app.stopFollowTheLoad();
    else {
      app.select(null);
      app.selectCountry(null);
    }
  });

  // structured tool surface (GeoAgent pattern): the same operations the
  // command bar uses, exposed for a future agent/MCP binding.
  const tools = buildToolSurface(app);
  (window as unknown as Record<string, unknown>).payloadEarth = {
    api: app,
    tools,
    invokeTool: (name: string, args: Record<string, unknown> = {}) => {
      const tool = tools.find((t) => t.name === name);
      if (!tool) throw new Error(`unknown tool: ${name}`);
      return tool.invoke(args);
    },
  };

  app.events.emit('toast', {
    title: 'GEOSPATIAL STATE VISUALIZATION ONLINE',
    body: `${app.store.snapshot.meta.label} · ${app.store.snapshot.meta.disclaimer}`,
    tone: 'info',
  });
}

void start();
