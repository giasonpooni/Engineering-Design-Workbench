/** Actual Chromium checks over the built embed. Test fixture is authored, not an ESM export. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';
import { fixture } from '../tests/helpers/public-projection.mjs';
const viewerOrigin = 'http://127.0.0.1:5173';
const channel = '1234567890abcdef1234567890abcdef';
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '5173', '--strictPort'], { stdio: 'inherit' });
let browser;
const host = createServer((req, res) => {
  const origin = `http://127.0.0.1:${host.address().port}`;
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(`<html><body><script>window.messages=[];addEventListener('message',e=>{if(e.origin===${JSON.stringify(viewerOrigin)})window.messages.push(e.data)});window.bridgeSend=m=>document.querySelector('iframe').contentWindow.postMessage(m,${JSON.stringify(viewerOrigin)});</script><iframe title="GSV integration test" sandbox="allow-scripts allow-same-origin" style="width:90vw;height:500px" src="${viewerOrigin}/embed.html#parentOrigin=${encodeURIComponent(origin)}&channel=${channel}"></iframe></body></html>`);
});
try {
  await new Promise(resolve => host.listen(0, '127.0.0.1', resolve));
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try { if ((await fetch(`${viewerOrigin}/embed.html`)).ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok(ready, 'Built viewer did not start');
  browser = await chromium.launch({ headless: true, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${host.address().port}`);
  await page.waitForFunction(() => window.messages.some(m => m.type === 'ready'));
  const p = await fixture();
  const send = message => page.evaluate(m => window.bridgeSend(m), { schema: 'notation.gsv-inspection.v1', channel, ...message });
  await send({ type: 'load', projection: p, spec: p.spec, digest: p.digest });
  await page.waitForFunction(digest => window.messages.some(m => m.type === 'loaded' && m.digest === digest), p.digest);
  const frame = page.frames().find(f => f.url().startsWith(viewerOrigin)); assert.ok(frame);
  assert.match(await frame.locator('#status').innerText(), /FIXTURE ONLY/);
  assert.equal(await frame.locator('canvas').count(), 1);
  const rect = await frame.locator('canvas').boundingBox(); assert.ok(rect.width > 500 && rect.height > 150);
  await send({ type: 'select', recordId: 'fixture:one', digest: p.digest });
  await mkdir('artifacts', { recursive: true }); await page.screenshot({ path: 'artifacts/released-embed.png', fullPage: true });
  const altered = structuredClone(p); altered.records[0].value = 500;
  await send({ type: 'load', projection: altered, spec: p.spec, digest: p.digest });
  await page.waitForFunction(digest => window.messages.some(m => m.type === 'refused' && m.activeDigest === digest), p.digest);
  assert.match(await frame.locator('#status').innerText(), /Previous projection remains active/);
  await send({ type: 'load', projection: p, spec: p.spec, digest: p.digest });
  await page.waitForFunction(() => window.messages.filter(m => m.type === 'loaded').length === 2);
  assert.equal(await frame.locator('canvas').count(), 1, 'Replacement must reuse the mounted renderer');
  await page.setViewportSize({ width: 800, height: 700 });
  await page.waitForTimeout(150);
  const resized = await frame.locator('canvas').boundingBox(); assert.ok(resized.width < rect.width);
  // Navigate the same frame away and back; no stale handshake can accept new data.
  await page.locator('iframe').evaluate(el => { el.src = 'about:blank'; });
  await page.waitForTimeout(100);
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('Chromium embed: handshake, rendering, selection input, digest refusal, replacement, resize and frame teardown passed.');
} finally { await browser?.close(); host.closeAllConnections(); await new Promise(resolve => host.close(resolve)); vite.kill('SIGTERM'); }
