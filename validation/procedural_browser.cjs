#!/usr/bin/env node
'use strict';

// Actual installed-workbench browser qualification. Runtime doubles are used
// only for explicit graphics-failure branches; retained scientific records are
// produced by the installed NET executable and never rewritten by this script.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const { chromium } = require('playwright');

function argumentsFrom(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 2) {
    assert(['--net', '--output-dir', '--browser-executable'].includes(argv[i]), 'Unknown qualifier argument');
    assert(i + 1 < argv.length && !Object.hasOwn(result, argv[i]), 'Require one value per unique argument');
    result[argv[i]] = argv[i + 1];
  }
  assert(result['--net'] && path.isAbsolute(result['--net']), '--net must identify an absolute installed executable');
  assert(result['--output-dir'], '--output-dir is required');
  if (result['--browser-executable']) assert(path.isAbsolute(result['--browser-executable']), 'Browser executable must be absolute');
  return result;
}

function bounded(promise, milliseconds, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Timed out: ' + label)), milliseconds);
    Promise.resolve(promise).then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); });
  });
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function decodePng(bytes, width, height) {
  assert(bytes.length <= 1024 * 1024, 'Exported PNG exceeds its byte budget');
  assert.deepEqual(bytes.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const chunks = [];
  let offset = 8;
  while (offset < bytes.length) {
    assert(offset + 12 <= bytes.length, 'Truncated PNG chunk');
    const length = bytes.readUInt32BE(offset), end = offset + 12 + length;
    assert(end <= bytes.length, 'PNG chunk exceeds retained bytes');
    const kind = bytes.subarray(offset + 4, offset + 8);
    const payload = bytes.subarray(offset + 8, end - 4);
    assert.equal(crc32(Buffer.concat([kind, payload])), bytes.readUInt32BE(end - 4), 'PNG CRC differs');
    chunks.push([kind.toString('ascii'), payload]);
    offset = end;
  }
  assert.deepEqual(chunks.map(([kind]) => kind), ['IHDR', 'IDAT', 'IEND']);
  const header = chunks[0][1];
  assert.equal(header.length, 13);
  assert.equal(header.readUInt32BE(0), width); assert.equal(header.readUInt32BE(4), height);
  assert.deepEqual([...header.subarray(8)], [8, 6, 0, 0, 0]);
  assert.equal(chunks[2][1].length, 0);
  const stride = 1 + width * 4, expected = height * stride;
  const decoded = zlib.inflateSync(chunks[1][1], { maxOutputLength: expected + 1, info: true });
  assert.equal(decoded.engine.bytesWritten, chunks[1][1].length, 'PNG contains trailing compressed input');
  const filtered = decoded.buffer;
  assert.equal(filtered.length, expected, 'PNG inflated length differs');
  const rows = [];
  for (let row = 0; row < height; row += 1) {
    assert.equal(filtered[row * stride], 0, 'Require the declared zero-filter profile');
    rows.push(filtered.subarray(row * stride + 1, (row + 1) * stride));
  }
  return Buffer.concat(rows);
}

function decodeObj(bytes, mesh) {
  assert(bytes.length <= 8 * 1024 * 1024, 'OBJ exceeds its byte budget');
  const vertices = [], triangles = [];
  for (const line of bytes.toString('ascii').split('\n')) {
    if (!line || line.startsWith('#')) continue;
    const tokens = line.split(' ');
    assert.equal(tokens.length, 4, 'Unexpected OBJ record shape');
    if (tokens[0] === 'v') {
      const point = tokens.slice(1).map(Number); assert(point.every(Number.isFinite)); vertices.push(point);
    } else {
      assert.equal(tokens[0], 'f', 'Unexpected OBJ record type');
      assert(tokens.slice(1).every(token => /^[1-9][0-9]*$/.test(token)));
      triangles.push(tokens.slice(1).map(value => Number(value) - 1));
    }
  }
  assert.deepEqual(vertices, mesh.vertices, 'OBJ vertex round-trip differs');
  assert.deepEqual(triangles, mesh.triangles, 'OBJ connectivity round-trip differs');
}

async function awaitServer(child) {
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '';
    const timer = setTimeout(() => finish(new Error('NET graphics server did not advertise its origin: ' + stderr)), 30000);
    function finish(error, origin) {
      clearTimeout(timer); child.stdout.off('data', onData); child.off('error', onError); child.off('exit', onExit);
      if (error) reject(error); else resolve(origin);
    }
    function onData(data) {
      stdout += data.toString('utf8');
      const match = stdout.match(/NET procedural graphics: (http:\/\/127\.0\.0\.1:[0-9]+)\r?\n/);
      if (match) finish(null, match[1]);
    }
    function onError(error) { finish(error); }
    function onExit(code) { finish(new Error('NET graphics server exited ' + code + ': ' + stderr)); }
    child.stdout.on('data', onData); child.stderr.on('data', data => { stderr = (stderr + data.toString('utf8')).slice(-16384); });
    child.once('error', onError); child.once('exit', onExit);
  });
}

async function closeServer(child) {
  if (!child || !child.pid || child.exitCode !== null || child.signalCode !== null) return;
  const exited = once(child, 'exit'); child.kill();
  const timer = setTimeout(() => { if (child.exitCode === null) child.kill('SIGKILL'); }, 5000);
  try { await exited; } finally { clearTimeout(timer); }
}

async function main() {
  const args = argumentsFrom(process.argv.slice(2));
  assert.equal(require('playwright/package.json').version, '1.62.1', 'Qualifier requires pinned Playwright 1.62.1');
  const output = path.resolve(args['--output-dir']);
  await fs.mkdir(path.dirname(output), { recursive: true }); await fs.mkdir(output);
  const runs = path.join(output, 'runs'), downloads = path.join(output, 'downloads'); await fs.mkdir(downloads);
  const childEnvironment = { ...process.env, PYTHONDONTWRITEBYTECODE: '1' };
  delete childEnvironment.PYTHONPATH; delete childEnvironment.PYTHONHOME;
  let browser, server, activePage;
  const checks = [], errors = [], report = { schema: 'ciw.procedural-browser-qualification.v1', status: 'FAIL', checks,
    playwright: '1.62.1', node: process.version, platform: process.platform, net: args['--net'], gpu_scope: 'actual_shader_compilation_and_display_only',
    cpu_pixel_verification: 'independent_exported_RGBA8_and_PNG_binding', gpu_cpu_pixel_identity: 'not_established',
    physical_validation: 'not_established', state_admission: 'not_performed' };
  const check = (name, detail = {}) => checks.push({ name, status: 'PASS', ...detail });
  const phase = async name => { report.phase = name; await fs.writeFile(path.join(output, 'progress.json'), JSON.stringify(report, null, 2) + '\n'); };
  try {
    await phase('server_start');
    server = spawn(args['--net'], ['graphics', 'serve', '--output-dir', runs, '--port', '0'],
      { env: childEnvironment, cwd: output, stdio: ['ignore', 'pipe', 'pipe'] });
    const origin = await awaitServer(server);
    await phase('browser_launch');
    browser = await chromium.launch({ headless: true, timeout: 30000,
      ...(args['--browser-executable'] ? { executablePath: args['--browser-executable'] } : {}),
      args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    report.browser_version = browser.version();
    const context = await browser.newContext({ viewport: { width: 1480, height: 1080 }, acceptDownloads: true });
    const page = await context.newPage(); activePage = page; page.setDefaultTimeout(30000); page.setDefaultNavigationTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    async function ready(target = page) {
      await target.waitForFunction(() => !document.getElementById('retain').disabled, null, { timeout: 60000 });
    }
    async function preview(target = page) {
      const sent = target.waitForRequest(request => request.url() === origin + '/api/preview' && request.method() === 'POST');
      const received = target.waitForResponse(response => response.url() === origin + '/api/preview');
      await target.locator('#preview').click(); const response = await received;
      assert.equal(response.status(), 200, 'Transient preview HTTP status');
      await target.waitForFunction(() => document.getElementById('preview').textContent === 'Preview' && document.getElementById('artifact-mode').textContent === 'Transient preview', null, { timeout: 60000 });
      assert.equal(await target.locator('#verification-status').textContent(), 'Checks passed');
      // Capture the actual browser-submitted program. Scientific outputs are
      // independently inspected through the retained API and export parsers;
      // CDP may evict a consumed transient response body on older Chromium.
      return { request: (await sent).postDataJSON().request };
    }
    async function download(button, filename) {
      const pending = page.waitForEvent('download'); await page.locator(button).click();
      const item = await pending, destination = path.join(downloads, filename); await item.saveAs(destination); await ready();
      return fs.readFile(destination);
    }
    const fetchRun = async id => {
      const response = await page.request.get(origin + '/api/runs/' + id); assert.equal(response.status(), 200);
      return response.json();
    };
    const history = async () => {
      const response = await page.request.get(origin + '/api/history'); assert.equal(response.status(), 200); return response.json();
    };
    const newlyRetained = async before => {
      const after = await history(), added = after.runs.filter(item => !before.has(item.id));
      assert.equal(added.length, 1, 'One user action must retain exactly one new run'); return fetchRun(added[0].id);
    };
    await phase('initial_preview'); await page.goto(origin + '/'); await ready();
    await page.waitForFunction(() => document.getElementById('artifact-mode').textContent === 'Transient preview', null, { timeout: 60000 });
    assert.equal(await page.locator('#viewport-error').isVisible(), false);
    assert.equal(await page.locator('#export-obj').isEnabled(), false);
    report.gpu_observation = await page.evaluate(() => {
      const gl = document.getElementById('viewport').getContext('webgl'), debug = gl.getExtension('WEBGL_debug_renderer_info');
      const precision = gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT);
      return { renderer: gl.getParameter(gl.RENDERER), vendor: gl.getParameter(gl.VENDOR),
        unmasked_renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null,
        unmasked_vendor: debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : null,
        fragment_high_float: precision ? { range_min: precision.rangeMin, range_max: precision.rangeMax, precision: precision.precision } : null };
    });
    await page.locator('#live-preview').uncheck();
    check('installed_loopback_browser_started');
    const cases = [
      { representation: 'implicit', example: 'gyroid', parameter: 'k', value: '2.1' },
      { representation: 'surface', example: 'parametric', parameter: 'R', value: '0.7' },
      { representation: 'texture', example: 'texture', parameter: 'phase', value: '0.25' },
    ];
    const retained = [];
    for (const fixture of cases) {
      await phase(fixture.representation + '_author_and_preview');
      await page.locator('#representation').selectOption(fixture.representation);
      await page.locator('#example').selectOption(fixture.example);
      await page.getByRole('spinbutton', { name: fixture.parameter + ' value', exact: true }).fill(fixture.value);
      const transient = await preview(); assert.equal(transient.request.definition.parameters[fixture.parameter].value, Number(fixture.value));
      if (fixture.representation === 'texture') {
        await page.waitForFunction(() => document.getElementById('gpu-status').dataset.status === 'compiled', null, { timeout: 30000 });
        assert.equal(await page.locator('#texture-raster').isVisible(), false);
        check('actual_generated_texture_shader_compiled');
      }
      const before = new Set((await history()).runs.map(item => item.id));
      await phase(fixture.representation + '_retain_and_export');
      const submitted = page.waitForRequest(request => request.url() === origin + '/api/run' && request.method() === 'POST');
      const pending = page.waitForResponse(response => response.url() === origin + '/api/run'); await page.locator('#retain').click();
      const response = await pending; assert.equal(response.status(), 200, 'Retained run HTTP status'); await ready();
      assert.deepEqual((await submitted).postDataJSON().request, transient.request, 'Browser-submitted retained program differs from preview');
      const original = await newlyRetained(before);
      assert.deepEqual(original.request, transient.request, 'Retained program differs from displayed preview definition');
      assert.equal(original.summary.status, 'LOCAL'); assert.equal(original.report.status, 'PASS');
      assert.equal(original.summary.fresh_execution, false); assert.equal(original.summary.fresh_numerical_verification, false);
      for (const field of ['execution_id', 'result_id', 'verification_id', 'verification_execution_id']) assert.match(original.summary[field], /^[a-z]+-[0-9a-f]{32}$/);
      assert.equal(await page.locator('#artifact-mode').textContent(), 'Retained artifact');
      const json = JSON.parse((await download('#export-json', fixture.representation + '.json')).toString('utf8'));
      assert.deepEqual(json.request, original.request); assert.deepEqual(json.artifact, original.artifact);
      assert.equal(json.source_execution_id, original.summary.execution_id); assert.equal(json.verification_id, original.summary.verification_id);
      const binary = await download(fixture.representation === 'texture' ? '#export-png' : '#export-obj', fixture.representation + (fixture.representation === 'texture' ? '.png' : '.obj'));
      const manifest = JSON.parse((await download('#export-manifest', fixture.representation + '-manifest.json')).toString('utf8'));
      assert.equal(manifest.output_sha256, 'sha256:' + crypto.createHash('sha256').update(binary).digest('hex'));
      assert.equal(manifest.source_execution_id, original.summary.execution_id); assert.equal(manifest.verification_id, original.summary.verification_id);
      if (fixture.representation === 'texture') {
        const image = original.artifact.image;
        assert.deepEqual(decodePng(binary, image.width, image.height), Buffer.from(image.rgba_base64, 'base64'), 'Independent PNG/CPU byte binding differs');
      } else {
        decodeObj(binary, original.artifact.mesh); assert.equal(manifest.units, original.artifact.mesh.units); assert.equal(manifest.frame, original.artifact.mesh.frame);
      }
      const beforeReplay = new Set((await history()).runs.map(item => item.id));
      await phase(fixture.representation + '_replay_and_reopen');
      const replayPending = page.waitForResponse(item => item.url() === origin + '/api/runs/' + original.id + '/replay'); await page.locator('#replay').click();
      const replayResponse = await replayPending; assert.equal(replayResponse.status(), 200, 'Replay HTTP status'); await ready();
      const repeated = await newlyRetained(beforeReplay); assert.equal(repeated.summary.replay.status, 'PASS');
      assert.notEqual(original.id, repeated.id); assert.equal(original.summary.evidence_id, repeated.summary.evidence_id);
      assert.equal(original.summary.artifact_digest, repeated.summary.artifact_digest); assert.deepEqual(original.artifact, repeated.artifact);
      for (const field of ['execution_id', 'result_id', 'verification_id', 'verification_execution_id']) assert.notEqual(original.summary[field], repeated.summary[field]);
      await page.locator('.history-item').filter({ hasText: original.id }).click(); await ready();
      const reopened = await fetchRun(original.id); assert.deepEqual(reopened.artifact, original.artifact);
      await page.locator('#use-definition').click(); assert.equal(await page.getByRole('spinbutton', { name: fixture.parameter + ' value', exact: true }).inputValue(), fixture.value);
      await page.screenshot({ path: path.join(output, fixture.representation + '-desktop.png'), fullPage: true });
      retained.push(original); check(fixture.representation + '_edit_preview_retain_export_replay_reopen', { artifact_digest: original.summary.artifact_digest });
    }
    const historyResponse = await page.request.get(origin + '/api/history'); assert.equal(historyResponse.status(), 200);
    await phase('invalid_inputs_and_refusal');
    assert.equal((await historyResponse.json()).runs.length, 6); assert.equal(await page.locator('.history-item').count(), 6);
    const previousArtifact = await page.locator('#mesh-stat').textContent();
    await page.locator('#expression-0').fill('__import__("os")');
    const invalid = page.waitForResponse(response => response.url() === origin + '/api/preview'); await page.locator('#preview').click();
    assert.equal((await invalid).status(), 400); await ready(); assert.equal(await page.locator('#error').isVisible(), true);
    assert.equal(await page.locator('#mesh-stat').textContent(), previousArtifact); assert.equal(await page.locator('#artifact-mode').textContent(), 'Previous artifact');
    await page.locator('#example').selectOption('texture'); await page.locator('#resolution').fill('999'); await page.locator('#preview').click();
    assert.equal(await page.locator('#error').isVisible(), true); assert.match(await page.locator('#error').textContent(), /resolution|256|range|bounded/i);
    await page.locator('#example').selectOption('texture'); await preview(); check('invalid_notation_and_excess_resolution_refused_without_history_writes');
    await page.locator('#representation').selectOption('implicit'); await page.locator('#example').selectOption('sphere');
    await page.locator('.parameter-add > summary').click();
    for (const [name, value, minimum, maximum] of [['__proto__', '0.7', '0.7', '0.7'], ['pi', '3.14', '3', '4']]) {
      await page.locator('#parameter-name').fill(name); await page.locator('#parameter-value').fill(value);
      await page.locator('#parameter-min').fill(minimum); await page.locator('#parameter-max').fill(maximum); await page.locator('#parameter-add').click();
      assert.equal(await page.getByRole('spinbutton', { name: name + ' value', exact: true }).inputValue(), value);
    }
    assert.equal(await page.getByRole('slider', { name: '__proto__ slider', exact: true }).isEnabled(), false);
    await page.locator('#expression').fill('x*x+y*y+z*z-__proto__*__proto__'); const special = await preview();
    assert.equal(Object.hasOwn(special.request.definition.parameters, '__proto__'), true);
    assert.equal(special.request.definition.parameters.__proto__.value, 0.7); check('prototype_named_parameter_and_constant_bounds_preserved');
    await page.locator('#expression').fill('1');
    const beforeRefusal = new Set((await history()).runs.map(item => item.id));
    const refusalPending = page.waitForResponse(response => response.url() === origin + '/api/run'); await page.locator('#retain').click();
    const refusalResponse = await refusalPending; assert.equal(refusalResponse.status(), 200); await ready();
    const refusal = await newlyRetained(beforeRefusal);
    assert.equal(refusal.summary.status, 'REFUSE'); assert.equal(refusal.summary.verification_status, 'not_verified');
    assert.equal(refusal.summary.verification_id, null); assert.equal(refusal.artifact, null); assert.equal(refusal.report, null);
    assert.equal(await page.locator('#artifact-mode').textContent(), 'Retained refusal'); assert.equal(await page.locator('#replay').isEnabled(), false);
    assert.equal(await page.locator('#export-obj').isEnabled(), false); assert.match(await page.locator('#mesh-stat').textContent(), /^Previous /);
    await page.locator('.history-item').filter({ hasText: retained[0].id }).click(); await ready();
    assert.equal(await page.locator('#artifact-mode').textContent(), 'Retained artifact');
    await page.locator('.history-item').filter({ hasText: refusal.id }).click(); await ready();
    assert.equal(await page.locator('#artifact-mode').textContent(), 'Retained refusal'); check('numerical_refusal_retained_without_invented_verification_or_export');
    await phase('GPU_orientation');
    await page.evaluate(() => {
      const original = WebGLRenderingContext.prototype.drawArrays;
      window.__netGraphicsOrientationRestore = () => { WebGLRenderingContext.prototype.drawArrays = original; };
      window.__netGraphicsOrientationObservation = null;
      WebGLRenderingContext.prototype.drawArrays = function(mode, first, count) {
        const result = original.call(this, mode, first, count);
        if (mode === this.TRIANGLES && count === 6 && window.__netGraphicsOrientationObservation === null) {
          const [x, y, width, height] = this.getParameter(this.VIEWPORT);
          const sample = (u, v) => { const rgba = new Uint8Array(4); this.readPixels(x + Math.floor(width * u), y + Math.floor(height * v), 1, 1, this.RGBA, this.UNSIGNED_BYTE, rgba); return [...rgba]; };
          window.__netGraphicsOrientationObservation = { bottom_left: sample(0.25, 0.25), bottom_right: sample(0.75, 0.25), top_left: sample(0.25, 0.75), top_right: sample(0.75, 0.75), gl_error: this.getError() };
        }
        return result;
      };
    });
    try {
      await page.locator('#representation').selectOption('texture'); await page.locator('#example').selectOption('texture');
      for (const [index, expression] of ['u', 'v', '0'].entries()) await page.locator('#expression-' + index).fill(expression);
      await preview(); await page.waitForFunction(() => window.__netGraphicsOrientationObservation !== null);
      const pixels = await page.evaluate(() => window.__netGraphicsOrientationObservation);
      assert.equal(pixels.gl_error, 0, 'Gradient display raised a WebGL error');
      assert(pixels.bottom_right[0] > pixels.bottom_left[0] + 100, 'GPU U increases toward the wrong display edge');
      assert(pixels.bottom_left[1] > pixels.top_left[1] + 100, 'GPU V is flipped relative to declared CPU row zero');
      for (const name of ['bottom_left', 'bottom_right', 'top_left', 'top_right']) { assert.equal(pixels[name][2], 0); assert.equal(pixels[name][3], 255); }
      report.gpu_gradient_orientation = pixels; check('actual_GPU_gradient_UV_orientation', { claim: 'orientation_control_only_not_general_pixel_identity' });
    } finally { await page.evaluate(() => { if (window.__netGraphicsOrientationRestore) window.__netGraphicsOrientationRestore(); }); }
    const shaderFailure = await context.newPage(); activePage = shaderFailure; shaderFailure.setDefaultTimeout(30000); shaderFailure.on('pageerror', error => errors.push(error.message));
    await phase('shader_failure_fallback');
    await shaderFailure.route('**/api/preview', async route => {
      const response = await route.fetch(), data = await response.json();
      if (data.artifact && data.artifact.shader) data.artifact.shader.fragment_source += '\nINVALID_GLSL_TEST_ONLY';
      await route.fulfill({ response, json: data });
    });
    await shaderFailure.goto(origin + '/'); await ready(shaderFailure);
    await shaderFailure.waitForFunction(() => document.getElementById('artifact-mode').textContent === 'Transient preview', null, { timeout: 60000 });
    await shaderFailure.locator('#live-preview').uncheck();
    await shaderFailure.locator('#representation').selectOption('texture'); await shaderFailure.locator('#example').selectOption('texture'); await preview(shaderFailure);
    await shaderFailure.waitForFunction(() => document.getElementById('gpu-status').dataset.status === 'failed');
    assert.equal(await shaderFailure.locator('#texture-raster').isVisible(), true); assert.equal(await shaderFailure.locator('#retain').isEnabled(), true);
    await shaderFailure.screenshot({ path: path.join(output, 'shader-failure-cpu-fallback.png'), fullPage: true });
    check('generated_shader_compile_failure_preserves_CPU_fallback', { fault: 'transient_response_only' }); await shaderFailure.close();
    const noGpu = await context.newPage(); activePage = noGpu; noGpu.setDefaultTimeout(30000); noGpu.on('pageerror', error => errors.push(error.message));
    await phase('no_GPU_fallback');
    await noGpu.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(kind, ...args) { return kind === 'webgl' || kind === 'webgl2' ? null : original.call(this, kind, ...args); };
    });
    await noGpu.goto(origin + '/'); await ready(noGpu);
    await noGpu.waitForFunction(() => document.getElementById('artifact-mode').textContent === 'Transient preview', null, { timeout: 60000 });
    await noGpu.locator('#live-preview').uncheck();
    await noGpu.locator('#representation').selectOption('texture'); await noGpu.locator('#example').selectOption('texture'); await preview(noGpu);
    await noGpu.waitForFunction(() => document.getElementById('gpu-status').dataset.status === 'unavailable');
    assert.equal(await noGpu.locator('#texture-raster').isVisible(), true); assert.equal(await noGpu.locator('#retain').isEnabled(), true);
    check('no_WebGL_preserves_checked_CPU_texture_and_authoring'); await noGpu.close();
    activePage = page; await page.locator('.history-item').filter({ hasText: retained[2].id }).click(); await ready();
    await phase('contrast_mobile_and_reload');
    await page.locator('#contrast-toggle').click(); assert.equal(await page.locator('#contrast-toggle').getAttribute('aria-pressed'), 'true');
    await page.screenshot({ path: path.join(output, 'high-contrast-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 }); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: path.join(output, 'high-contrast-mobile.png'), fullPage: true }); check('high_contrast_and_390px_mobile_without_horizontal_overflow');
    await page.reload(); await ready(); await page.waitForFunction(() => document.querySelectorAll('.history-item').length === 7);
    await page.locator('.history-item').filter({ hasText: retained[1].id }).click(); await ready();
    assert.equal(await page.locator('#artifact-mode').textContent(), 'Retained artifact'); await page.locator('#use-definition').click();
    assert.equal(await page.locator('#representation').inputValue(), 'surface');
    assert.equal(await page.getByRole('spinbutton', { name: 'R value', exact: true }).inputValue(), '0.7');
    check('page_reload_reopens_all_retained_representations');
    assert.deepEqual(errors, [], 'Browser raised uncaught errors'); report.status = 'PASS'; report.browser_errors = errors;
  } catch (error) {
    report.reason = String(error.stack || error); report.browser_errors = errors;
    if (activePage && !activePage.isClosed()) {
      try {
        report.failure_DOM = await bounded(activePage.evaluate(() => Object.fromEntries(['artifact-mode', 'preview', 'retain', 'authoring-status', 'error', 'viewport-error', 'gpu-status', 'verification-status', 'representation', 'example'].map(id => {
          const node = document.getElementById(id); return [id, node ? { text: node.textContent.slice(0, 2048), value: node.value || null, disabled: node.disabled || false, hidden: node.hidden || false } : null];
        }))), 10000, 'failure DOM capture');
        await bounded(activePage.screenshot({ path: path.join(output, 'failure.png'), fullPage: true, timeout: 10000 }), 12000, 'failure screenshot');
      } catch (captureError) { report.failure_capture_error = String(captureError); }
    }
    throw error;
  } finally {
    try { await fs.writeFile(path.join(output, 'qualification.json'), JSON.stringify(report, null, 2) + '\n'); }
    finally { try { if (browser) await bounded(browser.close(), 10000, 'browser cleanup'); } finally { await closeServer(server); } }
  }
  console.log(JSON.stringify(report));
}

main().catch(error => { console.error(error.stack || String(error)); process.exitCode = 1; });
