"use strict";
(() => {
  const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;
  const MAX_PARAMETERS = 8;
  const MAX_RENDER_TRIANGLES = 65536;
  const SCHEMAS = { "ciw.procedural-request.v1": "implicit", "ciw.procedural-surface-request.v1": "surface", "ciw.procedural-texture-request.v1": "texture" };
  const RESERVED = new Set(["x", "y", "z", "sin", "cos", "abs", "sqrt", "min", "max"]);
  const byId = (id) => document.getElementById(id);
  const nodes = {};
  ["example", "expression", "parameters", "parameter-add", "parameter-name", "parameter-value", "parameter-min", "parameter-max", "bounds", "resolution", "isovalue", "field-tolerance", "require-closed", "base-color", "roughness", "metallic", "roughness-value", "metallic-value", "preview", "retain", "live-preview", "authoring-status", "domain-summary", "viewport", "viewport-title", "viewport-empty", "viewport-error", "artifact-mode", "mesh-stat", "wireframe", "reset-view", "error", "verification-status", "metrics", "check-list", "lineage-intro", "identities", "display-definition", "export-obj", "export-manifest", "export-json", "history", "refresh-history", "replay", "use-definition", "history-status"].forEach((id) => { nodes[id] = byId(id); });
  ["contrast-toggle", "representation", "representation-chip", "definition-intro", "scalar-definition", "vector-definition", "expression-0", "expression-1", "expression-2", "channel-label-0", "channel-label-1", "channel-label-2", "expression-help", "resolution-label", "resolution-second", "resolution-2", "resolution-label-2", "isosurface-control", "isosurface-help", "geometry-verification", "texture-verification", "periodic-controls", "periodic-u", "periodic-v", "surface-color-control", "appearance-help", "texture-raster", "viewport-instructions", "wireframe-control", "cpu-raster-control", "cpu-raster", "gpu-status", "scope-note", "export-png", "shader-source-panel", "shader-source", "shader-diagnostics"].forEach((id) => { nodes[id] = byId(id); });
  ["verification-tolerance-label", "axis-key"].forEach((id) => { nodes[id] = byId(id); });
  const state = { examples: [], request: null, parameterInputs: Object.create(null), boundsInputs: [], revision: 0, previewController: null, previewTimer: null, busy: false, displayed: null, viewportArtifact: null, selectedRunId: null, history: [], ready: false };
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const finite = (number) => typeof number === "number" && Number.isFinite(number);
  const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const kindOf = (request) => object(request) && Object.prototype.hasOwnProperty.call(SCHEMAS, request.schema) ? SCHEMAS[request.schema] : null;
  const format = (value) => finite(value) ? (Number.isInteger(value) ? String(value) : (Math.abs(value) < 0.0001 || Math.abs(value) >= 100000 ? value.toExponential(3) : Number(value.toPrecision(5)).toString())) : String(value);
  const humanize = (name) => String(name).replace(/_/g, " ");
  const make = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const clear = (node) => node.replaceChildren();
  function showError(message) { nodes.error.textContent = message; nodes.error.hidden = false; }
  function clearError() { nodes.error.textContent = ""; nodes.error.hidden = true; }
  function authoringStatus(message) { nodes["authoring-status"].textContent = message; }
  function changeChip(node, text, flavor = "") { node.textContent = text; node.className = "chip" + (flavor ? " " + flavor : ""); }
  async function boundedBody(response) {
    const declared = response.headers.get("Content-Length");
    if (declared && Number(declared) > MAX_RESPONSE_BYTES) throw new Error("The server response exceeds the bounded artifact size.");
    if (response.body && response.body.getReader) {
      const reader = response.body.getReader(); const chunks = []; let total = 0;
      try { while (true) { const part = await reader.read(); if (part.done) break; total += part.value.byteLength; if (total > MAX_RESPONSE_BYTES) { await reader.cancel(); throw new Error("The server response exceeds the bounded artifact size."); } chunks.push(part.value); } }
      finally { reader.releaseLock(); }
      const bytes = new Uint8Array(total); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return bytes;
    }
    const bytes = new Uint8Array(await response.arrayBuffer()); if (bytes.byteLength > MAX_RESPONSE_BYTES) throw new Error("The server response exceeds the bounded artifact size."); return bytes;
  }
  async function api(path, options = {}) {
    const headers = { Accept: "application/json" };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { method: options.body === undefined ? "GET" : "POST", headers, credentials: "same-origin", cache: "no-store", signal: options.signal, body: options.body === undefined ? undefined : JSON.stringify(options.body) });
    if (!(response.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json")) throw new Error("The local instrument returned an unexpected response type.");
    const text = new TextDecoder("utf-8", { fatal: true }).decode(await boundedBody(response));
    let value; try { value = JSON.parse(text); } catch (_) { throw new Error("The local instrument returned invalid JSON."); }
    if (!object(value)) throw new Error("The local instrument returned an invalid response object.");
    if (!response.ok || value.status === "REFUSE") { const error = new Error(typeof value.reason === "string" ? value.reason : "The instrument refused this request. Check the definition, domain, and declared parameter bounds."); error.httpStatus = response.status; throw error; }
    return value;
  }
  function checkRequest(request) {
    const kind = kindOf(request);
    if (!kind || !object(request.definition) || !object(request.definition.parameters) || !object(request.domain) || !Array.isArray(request.domain.bounds) || request.domain.bounds.length !== (kind === "implicit" ? 3 : 2) || !object(request.appearance) || !object(request.verification)) throw new Error("The instrument returned an unsupported definition contract.");
    if ((kind === "implicit" && typeof request.definition.expression !== "string") || (kind !== "implicit" && (!Array.isArray(request.definition.expressions) || request.definition.expressions.length !== 3 || !request.definition.expressions.every((expression) => typeof expression === "string")))) throw new Error("The instrument returned invalid notation channels.");
    if (Object.keys(request.definition.parameters).length > MAX_PARAMETERS) throw new Error("The definition exceeds the parameter limit.");
    for (const [name, item] of Object.entries(request.definition.parameters)) if (!/^[A-Za-z_][A-Za-z0-9_]{0,31}$/.test(name) || !object(item) || !finite(item.value) || !finite(item.minimum) || !finite(item.maximum) || item.minimum > item.value || item.value > item.maximum) throw new Error("The definition contains an invalid parameter declaration.");
    for (const pair of request.domain.bounds) if (!Array.isArray(pair) || pair.length !== 2 || !finite(pair[0]) || !finite(pair[1]) || pair[0] >= pair[1]) throw new Error("The definition contains invalid domain bounds.");
    if (kind === "implicit" && (!Number.isInteger(request.domain.resolution) || request.domain.resolution < 8 || request.domain.resolution > 24 || !object(request.surface) || request.surface.convention !== "negative_inside" || request.surface.isovalue !== 0)) throw new Error("The definition contains an unsupported implicit extraction contract.");
    if (kind !== "implicit" && (!Array.isArray(request.domain.resolution) || request.domain.resolution.length !== 2 || !request.domain.resolution.every((n) => Number.isInteger(n) && n >= (kind === "surface" ? 8 : 16) && n <= (kind === "surface" ? 48 : 256)))) throw new Error("The definition contains an unsupported UV resolution contract.");
    if (kind === "surface" && (!Array.isArray(request.domain.periodic) || request.domain.periodic.length !== 2 || !request.domain.periodic.every((value) => typeof value === "boolean"))) throw new Error("The definition contains invalid UV periodicity declarations.");
    if (request.domain.units !== (kind === "texture" ? "normalized_coordinates" : "normalized_length") || request.domain.frame !== (kind === "texture" ? "procedural.texture_uv.v1" : "procedural.local_xyz.v1")) throw new Error("The definition changes the supported coordinate contract.");
    if (!finite(request.appearance.roughness) || !finite(request.appearance.metallic) || (kind !== "texture" && (!Array.isArray(request.appearance.base_color) || request.appearance.base_color.length !== 3 || !request.appearance.base_color.every((n) => finite(n) && n >= 0 && n <= 1) || !finite(request.verification.field_tolerance) || typeof request.verification.require_closed !== "boolean")) || (kind === "texture" && request.verification.byte_exact !== true)) throw new Error("The definition contains invalid appearance or verification controls.");
  }
  function validateArtifact(artifact, report) {
    if (!object(artifact) || !object(artifact.appearance) || !object(report) || !Array.isArray(report.checks) || !object(report.metrics)) throw new Error("The instrument returned an incomplete artifact or check report.");
    if (!["PASS", "FAIL"].includes(report.status) || !report.checks.every((check) => object(check) && typeof check.name === "string" && typeof check.status === "string")) throw new Error("The returned check report is invalid.");
    if (artifact.schema === "ciw.procedural-texture.v1") {
      const image = artifact.image;
      if (!object(image) || !Number.isInteger(image.width) || !Number.isInteger(image.height) || image.width < 16 || image.width > 256 || image.height < 16 || image.height > 256 || typeof image.png_base64 !== "string" || image.png_base64.length > MAX_RESPONSE_BYTES || typeof image.rgba_base64 !== "string" || image.rgba_base64.length > 350000 || !object(artifact.shader) || artifact.shader.language !== "glsl_es_1.00" || typeof artifact.shader.vertex_source !== "string" || typeof artifact.shader.fragment_source !== "string" || artifact.shader.vertex_source.length > 65536 || artifact.shader.fragment_source.length > 65536) throw new Error("The returned texture exceeds the bounded raster or shader contract.");
      return;
    }
    if (!["ciw.procedural-mesh.v1", "ciw.procedural-surface-mesh.v1"].includes(artifact.schema) || !object(artifact.mesh)) throw new Error("The instrument returned an unsupported graphics artifact.");
    const mesh = artifact.mesh;
    if (!Array.isArray(mesh.vertices) || !Array.isArray(mesh.triangles) || mesh.triangles.length > MAX_RENDER_TRIANGLES || mesh.vertices.length > 40000 || mesh.units !== "normalized_length" || mesh.frame !== "procedural.local_xyz.v1") throw new Error("The returned mesh exceeds or changes the supported viewport contract.");
    if (!mesh.vertices.every((v) => Array.isArray(v) && v.length === 3 && v.every(finite)) || !mesh.triangles.every((triangle) => Array.isArray(triangle) && triangle.length === 3 && triangle.every((index) => Number.isInteger(index) && index >= 0 && index < mesh.vertices.length))) throw new Error("The returned mesh has invalid coordinates or connectivity.");
    const appearance = artifact.appearance;
    if (!Array.isArray(appearance.base_color) || appearance.base_color.length !== 3 || !appearance.base_color.every((n) => finite(n) && n >= 0 && n <= 1) || !finite(appearance.roughness) || appearance.roughness < 0.05 || appearance.roughness > 1 || !finite(appearance.metallic) || appearance.metallic < 0 || appearance.metallic > 1) throw new Error("The returned appearance is outside the supported visual contract.");
  }
  function numberValue(input, name) { if (input.value.trim() === "") throw new Error(name + " needs a numeric value."); const value = Number(input.value); if (!finite(value)) throw new Error(name + " needs a finite number."); return value; }
  function readRequest() {
    if (!state.request) throw new Error("Choose a starting definition first.");
    const request = copy(state.request);
    const kind = kindOf(request);
    if (kind === "implicit") { request.definition.expression = nodes.expression.value.trim(); if (!request.definition.expression) throw new Error("Enter a field expression before previewing."); }
    else { request.definition.expressions = [0, 1, 2].map((index) => nodes["expression-" + index].value.trim()); if (request.definition.expressions.some((expression) => !expression)) throw new Error("Every coordinate or RGB channel needs an expression."); }
    for (const [name, item] of Object.entries(state.parameterInputs)) {
      const value = numberValue(item.number, "Parameter " + name); const declaration = request.definition.parameters[name];
      if (value < declaration.minimum || value > declaration.maximum) throw new Error("Parameter " + name + " must stay inside its declared bounds.");
      declaration.value = value;
    }
    const resolution = numberValue(nodes.resolution, "Resolution"), resolution2 = kind === "implicit" ? null : numberValue(nodes["resolution-2"], "Second resolution"); const lower = kind === "texture" ? 16 : 8, upper = kind === "texture" ? 256 : kind === "surface" ? 48 : 24;
    if (!Number.isInteger(resolution) || resolution < lower || resolution > upper || (kind !== "implicit" && (!Number.isInteger(resolution2) || resolution2 < lower || resolution2 > upper))) throw new Error("Resolution must contain integers from " + lower + " to " + upper + ".");
    request.domain.resolution = kind === "implicit" ? resolution : [resolution, resolution2];
    request.domain.bounds = state.boundsInputs.map((pair, axis) => { const name = (kind === "implicit" ? "xyz" : "uv")[axis]; const lo = numberValue(pair[0], "Lower " + name + " bound"), hi = numberValue(pair[1], "Upper " + name + " bound"); if (lo < -10 || hi > 10 || hi - lo < 0.1) throw new Error("Each domain bound must lie within −10 to 10 and span at least 0.1."); return [lo, hi]; });
    if (kind === "surface") request.domain.periodic = [nodes["periodic-u"].checked, nodes["periodic-v"].checked];
    if (kind !== "texture") {
      request.verification.field_tolerance = numberValue(nodes["field-tolerance"], "Field residual tolerance");
      if (request.verification.field_tolerance < 0.001 || request.verification.field_tolerance > 2) throw new Error("Field residual tolerance must be from 0.001 to 2.");
      request.verification.require_closed = nodes["require-closed"].checked;
      const hex = nodes["base-color"].value; if (hex !== colorHex(request.appearance.base_color)) request.appearance.base_color = [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255);
    }
    if (kind !== "texture") { request.appearance.roughness = numberValue(nodes.roughness, "Roughness"); request.appearance.metallic = numberValue(nodes.metallic, "Metallic"); }
    return request;
  }
  function colorHex(rgb) { return "#" + rgb.map((n) => Math.round(n * 255).toString(16).padStart(2, "0")).join(""); }
  function loadDefinition(request) {
    checkRequest(request); state.request = copy(request); state.revision += 1; cancelPreview();
    const kind = kindOf(request); configureEditor(kind); nodes.representation.value = kind;
    if (kind === "implicit") { nodes.expression.value = request.definition.expression; nodes.resolution.value = request.domain.resolution; }
    else { request.definition.expressions.forEach((expression, index) => { nodes["expression-" + index].value = expression; }); nodes.resolution.value = request.domain.resolution[0]; nodes["resolution-2"].value = request.domain.resolution[1]; }
    if (kind !== "texture") { nodes["field-tolerance"].value = request.verification.field_tolerance; nodes["require-closed"].checked = request.verification.require_closed; nodes["base-color"].value = colorHex(request.appearance.base_color); }
    if (kind === "surface") { nodes["periodic-u"].checked = request.domain.periodic[0]; nodes["periodic-v"].checked = request.domain.periodic[1]; }
    nodes.roughness.value = request.appearance.roughness; nodes.metallic.value = request.appearance.metallic; updateAppearanceOutputs();
    drawParameterControls(); drawBounds(); updateDomainLabel(); syncControls();
  }
  function configureEditor(kind) {
    nodes["verification-tolerance-label"].textContent = kind === "surface" ? "Position residual tolerance" : "Field residual tolerance";
    nodes["scalar-definition"].hidden = kind !== "implicit"; nodes["vector-definition"].hidden = kind === "implicit";
    nodes["resolution-second"].hidden = kind === "implicit"; nodes["isosurface-control"].hidden = kind !== "implicit"; nodes["isosurface-help"].hidden = kind !== "implicit"; nodes["geometry-verification"].hidden = kind === "texture"; nodes["texture-verification"].hidden = kind !== "texture"; nodes["periodic-controls"].hidden = kind !== "surface"; nodes["surface-color-control"].hidden = kind === "texture";
    nodes["surface-color-control"].parentElement.classList.toggle("texture-controls", kind === "texture");
    changeChip(nodes["representation-chip"], kind === "implicit" ? "Implicit field" : kind === "surface" ? "Parametric surface" : "RGB notation");
    nodes["definition-intro"].textContent = kind === "implicit" ? "Define a scalar field. Extract its declared isosurface on a bounded grid, inspect the checks, and retain a reproducible run." : kind === "surface" ? "Define Cartesian coordinates as functions of u and v. Sample a declared UV grid, check its mesh and seams, and retain the result." : "Define red, green, and blue as functions of u and v. Bake a checked CPU raster and compile its generated display shader in this browser.";
    [0, 1, 2].forEach((index) => { nodes["channel-label-" + index].textContent = (kind === "texture" ? ["Red", "Green", "Blue"] : ["X", "Y", "Z"])[index] + "(u, v)"; });
    nodes["expression-help"].textContent = "Use explicit multiplication (*). Functions: sin, cos, abs, sqrt, min, max. Powers use ** with integer exponents 0–6. " + (kind === "implicit" ? "Coordinates: x, y, z." : "Coordinates: u, v; declare other symbols as parameters.");
    nodes["resolution-label"].textContent = kind === "implicit" ? "Grid resolution" : kind === "surface" ? "U intervals" : "Width (pixels)"; nodes["resolution-label-2"].textContent = kind === "surface" ? "V intervals" : "Height (pixels)";
    for (const input of [nodes.resolution, nodes["resolution-2"]]) { input.min = kind === "texture" ? 16 : 8; input.max = kind === "texture" ? 256 : kind === "surface" ? 48 : 24; }
    nodes["appearance-help"].textContent = kind === "texture" ? "RGB denotes unqualified display color. Roughness and metallic remain declared visual concepts; this generated RGB shader does not use them. No optical or physical material model is supplied." : "Appearance controls an approximate display shader. It supplies no composition, strength, or physical material model.";
    drawExamples(nodes.example.value);
  }
  function drawExamples(selected) {
    clear(nodes.example); const kind = kindOf(state.request);
    for (const example of state.examples.filter((item) => kindOf(item.request) === kind)) { const option = make("option", "", example.label); option.value = example.id; nodes.example.append(option); }
    if (Array.from(nodes.example.options).some((option) => option.value === selected)) nodes.example.value = selected;
  }
  function drawParameterControls() {
    clear(nodes.parameters); state.parameterInputs = Object.create(null);
    for (const [name, declaration] of Object.entries(state.request.definition.parameters)) {
      const row = make("div", "parameter-row"); const label = make("label", "", name); const identity = "declared-parameter-" + name;
      label.htmlFor = identity; label.append(make("span", "", format(declaration.minimum) + " … " + format(declaration.maximum)));
      const slider = make("input"); slider.type = "range"; slider.id = identity; slider.min = declaration.minimum; slider.max = declaration.maximum; slider.step = "any"; slider.value = declaration.value; slider.setAttribute("aria-label", name + " slider"); slider.disabled = declaration.minimum === declaration.maximum;
      const number = make("input"); number.type = "number"; number.min = declaration.minimum; number.max = declaration.maximum; number.step = "any"; number.value = declaration.value; number.setAttribute("aria-label", name + " value");
      const remove = make("button", "remove", "×"); remove.type = "button"; remove.title = "Remove parameter " + name; remove.setAttribute("aria-label", "Remove parameter " + name);
      slider.addEventListener("input", () => { number.value = slider.value; edited(); }); number.addEventListener("input", () => { if (number.value !== "" && Number.isFinite(Number(number.value))) slider.value = number.value; edited(); });
      remove.addEventListener("click", () => { if (state.busy) return; try { state.request = readRequest(); } catch (_) { /* Keep other declared values when a draft field is incomplete. */ } delete state.request.definition.parameters[name]; drawParameterControls(); edited(); });
      row.append(label, slider, number, remove); nodes.parameters.append(row); state.parameterInputs[name] = { slider, number, remove };
    }
    if (!Object.keys(state.parameterInputs).length) nodes.parameters.append(make("p", "help", "No parameters are declared. Add one to expose a bounded control."));
  }
  function drawBounds() {
    clear(nodes.bounds); state.boundsInputs = [];
    state.request.domain.bounds.forEach((pair, axis) => {
      const axisName = (kindOf(state.request) === "implicit" ? "xyz" : "uv")[axis]; const row = make("div", "bound-row"); row.append(make("span", "", axisName)); const inputs = [];
      pair.forEach((value, index) => { const label = make("label", "", index ? "Maximum" : "Minimum"); const input = make("input"); input.type = "number"; input.step = "any"; input.min = -10; input.max = 10; input.value = value; input.setAttribute("aria-label", axisName + " " + (index ? "maximum" : "minimum")); input.addEventListener("input", () => { updateDomainLabel(); edited(); }); label.append(input); row.append(label); inputs.push(input); });
      nodes.bounds.append(row); state.boundsInputs.push(inputs);
    });
  }
  function updateDomainLabel() { nodes["domain-summary"].textContent = state.request && kindOf(state.request) === "texture" ? "Normalized texture UV" : "Normalized length · " + (state.request && kindOf(state.request) === "surface" ? "UV sampling" : "local XYZ"); }
  function updateAppearanceOutputs() { nodes["roughness-value"].value = Number(nodes.roughness.value).toFixed(2); nodes["metallic-value"].value = Number(nodes.metallic.value).toFixed(2); }
  function cancelPreview() { if (state.previewController) state.previewController.abort(); state.previewController = null; if (state.previewTimer !== null) clearTimeout(state.previewTimer); state.previewTimer = null; nodes.preview.textContent = "Preview"; }
  function edited() {
    if (state.busy || !state.ready) return; state.revision += 1; cancelPreview(); clearError();
    if (state.displayed) { changeChip(nodes["artifact-mode"], "Previous artifact", "preview"); authoringStatus("Definition changed. The displayed artifact belongs to the previous inputs."); }
    else authoringStatus("Definition changed. Preview to inspect its sampled surface.");
    if (nodes["live-preview"].checked) state.previewTimer = setTimeout(() => { state.previewTimer = null; preview(); }, 420);
    syncControls();
  }
  function syncControls() {
    const disabled = !state.ready || state.busy;
    [nodes.representation, nodes.example, nodes.expression, nodes["expression-0"], nodes["expression-1"], nodes["expression-2"], nodes.resolution, nodes["resolution-2"], nodes["periodic-u"], nodes["periodic-v"], nodes["field-tolerance"], nodes["require-closed"], nodes["base-color"], nodes.roughness, nodes.metallic, nodes["parameter-add"], nodes["parameter-name"], nodes["parameter-value"], nodes["parameter-min"], nodes["parameter-max"]].forEach((node) => { node.disabled = disabled; });
    if (state.request && kindOf(state.request) === "texture") { nodes.roughness.disabled = true; nodes.metallic.disabled = true; }
    for (const [name, item] of Object.entries(state.parameterInputs)) for (const [type, input] of Object.entries(item)) input.disabled = disabled || (type === "slider" && state.request.definition.parameters[name].minimum === state.request.definition.parameters[name].maximum);
    for (const pair of state.boundsInputs) for (const input of pair) input.disabled = disabled;
    nodes.preview.disabled = disabled; nodes.retain.disabled = disabled;
    const retained = state.displayed && state.displayed.id && state.displayed.summary && state.displayed.summary.verification_status === "PASS";
    [nodes["export-obj"], nodes["export-png"], nodes["export-manifest"], nodes["export-json"]].forEach((node) => { node.disabled = state.busy || !retained; });
    nodes["export-obj"].disabled = state.busy || !retained || !state.displayed.artifact || state.displayed.artifact.schema === "ciw.procedural-texture.v1";
    nodes["export-png"].disabled = state.busy || !retained || !state.displayed.artifact || state.displayed.artifact.schema !== "ciw.procedural-texture.v1";
    nodes.replay.disabled = state.busy || !state.selectedRunId || !retained; nodes["use-definition"].disabled = state.busy || !state.displayed || !state.displayed.id || !state.displayed.request;
    nodes["refresh-history"].disabled = state.busy;
    for (const button of nodes.history.querySelectorAll("button")) button.disabled = state.busy;
  }
  function display(result, mode, request) {
    if (mode !== "preview" && object(result.summary) && result.summary.verification_status === "not_verified") { displayRefusal(result, request); return; }
    validateArtifact(result.artifact, result.report);
    if (result.request) checkRequest(result.request);
    if (mode !== "preview" && (typeof result.id !== "string" || !/^[a-zA-Z0-9_.-]{1,128}$/.test(result.id) || !object(result.summary) || !["PASS", "FAIL"].includes(result.summary.verification_status) || result.summary.verification_status !== result.report.status)) throw new Error("The instrument returned an invalid retained-run identity or verification status.");
    const texture = result.artifact.schema === "ciw.procedural-texture.v1";
    if (texture) renderer.setTexture(result.artifact.image, result.artifact.shader); else renderer.setMesh(result.artifact.mesh, result.artifact.appearance);
    nodes["shader-source-panel"].hidden = !texture; if (texture) nodes["shader-source"].textContent = "// Vertex source\n" + result.artifact.shader.vertex_source + "\n// Fragment source\n" + result.artifact.shader.fragment_source;
    state.viewportArtifact = result.artifact;
    state.displayed = { ...result, request: copy(result.request || request), revision: state.revision, mode };
    state.selectedRunId = mode === "preview" ? null : result.id;
    nodes["viewport-empty"].hidden = true;
    changeChip(nodes["artifact-mode"], mode === "preview" ? "Transient preview" : mode === "replay" ? "Retained replay" : "Retained artifact", mode === "preview" ? "preview" : "retained");
    nodes["viewport-title"].textContent = texture ? (mode === "preview" ? "Texture and shader preview" : "Retained texture") : mode === "preview" ? "Geometry preview" : "Retained geometry";
    nodes["mesh-stat"].textContent = texture ? result.artifact.image.width + " × " + result.artifact.image.height + " CPU pixels · RGBA8" : result.artifact.mesh.vertices.length.toLocaleString() + " vertices · " + result.artifact.mesh.triangles.length.toLocaleString() + " triangles";
    configureViewport(texture);
    renderReport(result.report, result.summary); renderLineage(state.displayed); renderHistory(); syncControls();
  }
  function displayRefusal(result, request) {
    if (typeof result.id !== "string" || !/^[a-zA-Z0-9_.-]{1,128}$/.test(result.id) || result.summary.status !== "REFUSE" || result.report !== null || !Array.isArray(result.summary.executions)) throw new Error("The instrument returned an invalid retained refusal.");
    checkRequest(result.request || request);
    state.displayed = { ...result, request: copy(result.request || request), revision: state.revision, mode: "refusal" }; state.selectedRunId = result.id;
    changeChip(nodes["artifact-mode"], "Retained refusal", "fail"); changeChip(nodes["verification-status"], "Not verified", "fail"); nodes["viewport-title"].textContent = "Refused execution";
    if (state.viewportArtifact) { nodes["mesh-stat"].textContent = state.viewportArtifact.schema === "ciw.procedural-texture.v1" ? "Previous texture · " + state.viewportArtifact.image.width + " × " + state.viewportArtifact.image.height + " pixels" : "Previous geometry · " + state.viewportArtifact.mesh.vertices.length.toLocaleString() + " vertices · " + state.viewportArtifact.mesh.triangles.length.toLocaleString() + " triangles"; }
    else nodes["mesh-stat"].textContent = "No verified artifact from this run";
    clear(nodes.metrics); clear(nodes["check-list"]); nodes["check-list"].append(make("p", "help", "This execution was retained as a refusal. It has no completed numerical verification and cannot be exported or replayed. Any surface still visible belongs to the previous artifact."));
    const messages = result.summary.executions.filter((entry) => object(entry) && object(entry.refusal) && typeof entry.refusal.message === "string").map((entry) => entry.refusal.message);
    showError("Retained refusal: " + (messages.length ? messages.join(" · ") : "The declared computation did not produce a qualified artifact.")); renderLineage(state.displayed); renderHistory(); syncControls();
  }
  function configureViewport(texture) {
    nodes["axis-key"].hidden = texture;
    nodes["wireframe-control"].hidden = texture; nodes["reset-view"].hidden = texture; nodes["cpu-raster-control"].hidden = !texture; nodes["export-png"].hidden = !texture; nodes["export-obj"].hidden = texture;
    nodes["viewport-instructions"].textContent = texture ? "GPU field preview · Switch to declared CPU samples" : "Drag to orbit · Scroll to zoom";
    nodes["scope-note"].textContent = texture ? "CPU pixels: declared RGBA8 center sampling · Display RGB is unqualified · GPU pixel equality and optical material properties are not established" : "Sampled geometry · Normalized length · Continuous fidelity is not established · Self intersections are not checked";
    nodes.viewport.setAttribute("aria-label", texture ? "Generated procedural RGB shader preview. CPU raster control shows the retained pixel samples." : "Interactive mesh viewport. Drag to orbit. Scroll to zoom. Arrow keys orbit, plus and minus zoom, Home resets.");
  }
  const METRICS = [["vertex_count", "Vertices"], ["triangle_count", "Triangles"], ["boundary_edge_count", "Boundary edges"], ["component_count", "Components"], ["max_field_residual", "Field residual"], ["minimum_triangle_quality", "Min. triangle quality"]];
  function renderReport(report, summary) {
    clear(nodes.metrics); clear(nodes["check-list"]);
    const status = summary ? summary.verification_status : report.status;
    if (!["PASS", "FAIL"].includes(status)) throw new Error("The instrument returned an unsupported verification status.");
    changeChip(nodes["verification-status"], status === "PASS" ? "Checks passed" : "Checks failed", status.toLowerCase());
    const metrics = state.displayed && state.displayed.artifact && state.displayed.artifact.schema === "ciw.procedural-texture.v1" ? [["width", "Width"], ["height", "Height"], ["pixel_count", "CPU pixels"], ["max_channel_byte_error", "CPU channel byte error"], ["png_bytes", "PNG bytes"]] : METRICS.map(([key, label]) => [key, key === "max_field_residual" && state.displayed && kindOf(state.displayed.request) === "surface" ? "Position residual" : label]);
    for (const [key, label] of metrics) { if (!finite(report.metrics[key])) continue; const metric = make("dl", "metric"); metric.append(make("dt", "", label), make("dd", "", format(report.metrics[key]))); nodes.metrics.append(metric); }
    for (const check of report.checks) {
      const flavor = check.status === "PASS" ? "pass" : check.status === "FAIL" ? "fail" : ""; const row = make("div", "check-row " + flavor);
      const title = ["Observed: " + format(check.value), "Declared tolerance: " + format(check.tolerance)].join(" · "); row.title = title;
      row.append(make("span", "check-dot"), make("span", "check-name", humanize(check.name)), make("span", "check-status", check.status)); nodes["check-list"].append(row);
    }
    if (report.metrics.boundary_edge_count > 0) nodes["check-list"].append(make("p", "help", "This surface has open boundaries. Closedness is enforced only when the request requires it."));
    if (status === "FAIL") nodes["check-list"].append(make("p", "help", "The artifact is inspectable, but it failed its declared checks and is not eligible for accepted export. Adjust the definition, resolution, or declared requirements and run again."));
  }
  function renderLineage(result) {
    clear(nodes.identities);
    const fields = result.id ? [["Retained run", result.id], ["Evidence", result.summary.evidence_id], ["Result", result.summary.result_id], ["Execution", result.summary.execution_id], ["Verification", result.summary.verification_id], ["Verification execution", result.summary.verification_execution_id], ["Mesh digest", result.summary.mesh_digest], ["CPU image digest", result.summary.image_digest], ["PNG digest", result.summary.png_digest]] : [["Transient artifact digest", result.artifact.record_digest]];
    if (result.id && Array.isArray(result.summary.executions)) for (const execution of result.summary.executions) if (object(execution) && typeof execution.operation_id === "string") fields.push([execution.execution_id === result.summary.verification_execution_id ? "Verification operation" : "Generator operation", execution.operation_id]);
    for (const [name, value] of fields) if (typeof value === "string") { nodes.identities.append(make("dt", "", name), make("dd", "", value)); }
    nodes["lineage-intro"].textContent = result.mode === "refusal" ? "This retained refusal has source evidence and attempted execution records. No completed verification identity is invented. The viewport may retain the previous artifact for comparison." : result.id ? "Evidence, result, execution, and verification identities remain separate. Stored checks and fresh replay do not establish continuous, physical, or manufacturing validity." : "This preview is transient. It has no retained evidence, execution, or verification identity. Retain a run to capture its inputs and checks.";
    if (result.mode === "refusal") for (const execution of result.summary.executions) if (typeof execution.execution_id === "string") nodes.identities.append(make("dt", "", "Attempted execution"), make("dd", "", execution.execution_id));
    const kind = kindOf(result.request);
    nodes["display-definition"].textContent = result.request ? (kind === "implicit" ? result.request.definition.expression : result.request.definition.expressions.map((expression, index) => (kind === "texture" ? ["R", "G", "B"] : ["X", "Y", "Z"])[index] + " = " + expression).join("\n")) + "\n\n" + Object.entries(result.request.definition.parameters).map(([name, item]) => name + " = " + format(item.value) + "  [" + format(item.minimum) + ", " + format(item.maximum) + "]").join("\n") + "\n\nSampling: " + result.request.domain.resolution + (kind === "implicit" ? " · Isovalue: 0" : " · UV bounds: " + result.request.domain.bounds.map((pair) => pair.map(format).join(" … ")).join(" / ")) : "Definition unavailable in this response.";
    if (result.replay) { const message = make("p", "help", typeof result.replay.status === "string" ? "Fresh replay: " + result.replay.status + ". Inspect its retained verification identity above." : "Fresh replay completed; its new execution and verification identities are retained above."); nodes.identities.append(message); }
  }
  async function preview(retry = 0) {
    if (state.busy || !state.ready) return; cancelPreview(); clearError(); let request;
    try { request = readRequest(); } catch (error) { showError(error.message); authoringStatus("The draft needs a correction before extraction."); return; }
    const revision = state.revision; const controller = new AbortController(); state.previewController = controller;
    authoringStatus("Extracting a transient preview…"); nodes.preview.textContent = "Previewing…";
    try { const result = await api("/api/preview", { body: { request }, signal: controller.signal }); if (revision !== state.revision || controller.signal.aborted || state.busy) return; if (result.status !== "preview" || result.transient !== true || result.id !== undefined) throw new Error("The preview response does not satisfy the transient execution contract."); display(result, "preview", request); authoringStatus("Transient preview complete. Retain a run to capture this definition and its checks."); }
    catch (error) { if (error.name !== "AbortError" && revision === state.revision) { if (error.httpStatus === 429 && retry < 4 && !state.busy) { authoringStatus("Waiting for the previous extraction to finish…"); state.previewTimer = setTimeout(() => { state.previewTimer = null; if (revision === state.revision && !state.busy) preview(retry + 1); }, 650); } else { showError(error.message); authoringStatus("Preview failed. The previous artifact remains visible."); } } }
    finally { if (state.previewController === controller) { state.previewController = null; nodes.preview.textContent = "Preview"; } }
  }
  async function retain() {
    if (state.busy || !state.ready) return; let request; try { request = readRequest(); } catch (error) { showError(error.message); return; }
    cancelPreview(); state.busy = true; nodes.preview.textContent = "Preview"; clearError(); syncControls(); authoringStatus("Executing and retaining the declared definition…"); nodes.retain.textContent = "Retaining…";
    try { const result = await submitWhenIdle("/api/run", { request }); display(result, "retained", request); authoringStatus(result.summary.verification_status === "PASS" ? "Run retained. Its numerical checks passed; fresh verification gates each export." : result.summary.verification_status === "not_verified" ? "The refused execution was retained. Correct its definition before running again." : "Run retained for inspection. Its checks failed; accepted export is unavailable."); await refreshHistory(); }
    catch (error) { showError(error.message); authoringStatus("The retained run did not finish in this view. Refresh history before retrying if the connection was interrupted."); }
    finally { state.busy = false; nodes.retain.textContent = "Retain run"; syncControls(); }
  }
  function renderHistory() {
    clear(nodes.history); if (!state.history.length) { nodes.history.append(make("li", "history-empty", "No retained runs yet.")); return; }
    for (const run of state.history) {
      const li = make("li"); const button = make("button", "history-item" + (state.selectedRunId === run.id ? " selected" : "")); button.type = "button"; button.disabled = state.busy; button.setAttribute("aria-pressed", state.selectedRunId === run.id ? "true" : "false");
      const heading = make("span", "history-title", run.summary.verification_status === "not_verified" ? "Refused execution" : run.summary.artifact_kind === "texture" ? "Texture run" : "Geometry run"); const status = run.summary.verification_status; heading.append(make("span", "chip " + (status === "PASS" ? "pass" : "fail"), status === "not_verified" ? "REFUSE" : status)); button.append(heading, make("span", "history-id", run.id));
      if (object(run.summary.metrics) && finite(run.summary.metrics.triangle_count)) button.append(make("span", "history-metric", format(run.summary.metrics.triangle_count) + " triangles"));
      if (object(run.summary.metrics) && finite(run.summary.metrics.width) && finite(run.summary.metrics.height)) button.append(make("span", "history-metric", format(run.summary.metrics.width) + " × " + format(run.summary.metrics.height) + " pixels"));
      button.addEventListener("click", () => openRun(run.id)); li.append(button); nodes.history.append(li);
    }
  }
  async function refreshHistory() {
    try { const result = await api("/api/history"); if (!Array.isArray(result.runs) || !result.runs.every((run) => object(run) && typeof run.id === "string" && /^[a-zA-Z0-9_.-]{1,128}$/.test(run.id) && object(run.summary) && ["PASS", "FAIL", "not_verified"].includes(run.summary.verification_status))) throw new Error("The instrument returned an invalid run history."); state.history = result.runs; renderHistory(); nodes["history-status"].textContent = state.history.length + " retained " + (state.history.length === 1 ? "run" : "runs") + "."; }
    catch (error) { nodes["history-status"].textContent = "History could not be loaded: " + error.message; }
  }
  async function openRun(id) {
    if (state.busy) return; cancelPreview(); state.busy = true; nodes.preview.textContent = "Preview"; clearError(); syncControls(); nodes["history-status"].textContent = "Opening retained artifact…";
    try { const result = await api("/api/runs/" + encodeURIComponent(id)); if (result.id !== id) throw new Error("The returned artifact belongs to a different retained run."); display(result, "retained", result.request); nodes["history-status"].textContent = result.summary.verification_status === "not_verified" ? "Retained refusal selected. Use its definition to restore and correct the editor." : "Retained artifact selected. Use its definition to restore the editor."; authoringStatus(result.summary.verification_status === "not_verified" ? "This is a retained refusal. Any visible surface belongs to the previous artifact; the editor remains your current draft." : "The viewport shows a retained artifact. The editor remains your current draft."); }
    catch (error) { showError(error.message); nodes["history-status"].textContent = "The selected run could not be inspected."; }
    finally { state.busy = false; syncControls(); }
  }
  async function replay() {
    if (state.busy || !state.selectedRunId) return; const id = state.selectedRunId; cancelPreview(); state.busy = true; nodes.preview.textContent = "Preview"; clearError(); syncControls(); nodes["history-status"].textContent = "Replaying the retained definition with fresh numerical checks…";
    try { const result = await submitWhenIdle("/api/runs/" + encodeURIComponent(id) + "/replay", {}); display(result, "replay", result.request); nodes["history-status"].textContent = "Fresh replay retained with a new execution and verification identity."; authoringStatus("The viewport shows the freshly replayed artifact. The editor remains your current draft."); await refreshHistory(); }
    catch (error) { showError(error.message); nodes["history-status"].textContent = "Replay failed. The previous artifact remains selected."; }
    finally { state.busy = false; syncControls(); }
  }
  async function submitWhenIdle(path, body) {
    for (let attempt = 0; ; attempt += 1) {
      try { return await api(path, { body }); }
      catch (error) { if (error.httpStatus !== 429 || attempt >= 9) throw error; authoringStatus("Waiting for the local instrument to finish its current operation…"); await new Promise((resolve) => setTimeout(resolve, 650)); }
    }
  }
  async function exportRun(formatName) {
    if (!state.displayed || !state.displayed.id || state.displayed.summary.verification_status !== "PASS" || state.busy) return;
    const id = state.displayed.id; state.busy = true; cancelPreview(); syncControls(); clearError(); nodes["history-status"].textContent = "Checking the retained artifact before export…";
    try {
      const response = await fetch("/api/runs/" + encodeURIComponent(id) + "/export?format=" + encodeURIComponent(formatName), { credentials: "same-origin", cache: "no-store", headers: { Accept: formatName === "obj" ? "text/plain, model/obj" : formatName === "png" ? "image/png" : "application/json" } });
      const bytes = await boundedBody(response);
      if (!response.ok) { let message; try { message = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch (_) { throw new Error("Fresh export verification refused this artifact."); } throw new Error(object(message) && typeof message.reason === "string" ? message.reason : "Fresh export verification refused this artifact."); }
      const type = (response.headers.get("Content-Type") || "").toLowerCase(); if ((!["obj", "png"].includes(formatName) && !type.startsWith("application/json")) || (formatName === "obj" && !type.startsWith("text/plain") && !type.startsWith("model/obj")) || (formatName === "png" && !type.startsWith("image/png"))) throw new Error("The export has an unexpected response type.");
      const blob = new Blob([bytes], { type }); const url = URL.createObjectURL(blob); const anchor = make("a"); anchor.href = url; anchor.download = "net-artifact-" + id + (formatName === "obj" ? ".obj" : formatName === "png" ? ".png" : formatName === "manifest" ? "-manifest.json" : ".json"); document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      nodes["history-status"].textContent = ["obj", "png"].includes(formatName) ? "Checked " + formatName.toUpperCase() + " exported. Export the manifest too to retain its identity and scope alongside the artifact." : "Checked export complete. The artifact's retained identities remain distinct from fresh export verification.";
    } catch (error) { showError(error.message); nodes["history-status"].textContent = "Export failed. The artifact remains available for inspection."; }
    finally { state.busy = false; syncControls(); }
  }

  class MeshViewport {
    constructor(canvas) {
      this.canvas = canvas; this.gl = null; this.mode = "mesh"; this.textureProgram = null; this.yaw = -0.55; this.pitch = 0.25; this.distance = 3.5; this.boundingRadius = 1; this.vertexCount = 0; this.edgeCount = 0; this.appearance = { base_color: [0.3, 0.7, 0.75], roughness: 0.45, metallic: 0 }; this.drag = null; this.frame = null;
      try { this.gl = canvas.getContext("webgl", { alpha: true, antialias: true, preserveDrawingBuffer: false }); if (!this.gl) throw new Error("WebGL is unavailable in this browser. Enable a supported graphics context to view the surface. You can still retain, inspect, replay, and export checked geometry."); this.initialize(); }
      catch (error) { this.gl = null; nodes["viewport-error"].textContent = error.message; nodes["viewport-error"].hidden = false; nodes["viewport-empty"].hidden = true; nodes["gpu-status"].dataset.status = "unavailable"; nodes["gpu-status"].textContent = "GPU display unavailable · Numerical checks remain independent"; }
      canvas.addEventListener("webglcontextlost", (event) => { event.preventDefault(); this.gl = null; nodes["viewport-error"].textContent = "The browser lost its WebGL context. Reload to restore rendering. Retained artifacts remain available through history and export."; nodes["viewport-error"].hidden = false; nodes["gpu-status"].dataset.status = "unavailable"; nodes["gpu-status"].textContent = "GPU display unavailable · Numerical checks remain independent"; if (this.mode === "texture") { nodes["cpu-raster"].checked = true; this.showCpuRaster(); } });
      canvas.addEventListener("pointerdown", (event) => { if (!this.gl || this.mode === "texture" || event.button !== 0) return; this.drag = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId); canvas.classList.add("dragging"); });
      canvas.addEventListener("pointermove", (event) => { if (!this.drag) return; this.yaw += (event.clientX - this.drag[0]) * 0.008; this.pitch = Math.max(-1.5, Math.min(1.5, this.pitch + (event.clientY - this.drag[1]) * 0.008)); this.drag = [event.clientX, event.clientY]; this.schedule(); });
      const end = () => { this.drag = null; canvas.classList.remove("dragging"); }; canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end); canvas.addEventListener("lostpointercapture", end);
      canvas.addEventListener("wheel", (event) => { if (!this.gl || this.mode === "texture") return; event.preventDefault(); this.distance = Math.max(1.65, Math.min(8, this.distance * Math.exp(Math.max(-100, Math.min(100, event.deltaY)) * 0.001))); this.schedule(); }, { passive: false });
      canvas.addEventListener("keydown", (event) => { if (!this.gl || this.mode === "texture") return; let used = true; if (event.key === "ArrowLeft") this.yaw -= 0.1; else if (event.key === "ArrowRight") this.yaw += 0.1; else if (event.key === "ArrowUp") this.pitch = Math.max(-1.5, this.pitch - 0.1); else if (event.key === "ArrowDown") this.pitch = Math.min(1.5, this.pitch + 0.1); else if (event.key === "+" || event.key === "=") this.distance = Math.max(1.65, this.distance * 0.9); else if (event.key === "-") this.distance = Math.min(8, this.distance * 1.1); else if (event.key === "Home") this.reset(); else used = false; if (used) { event.preventDefault(); this.schedule(); } });
      if (typeof ResizeObserver !== "undefined") this.resizeObserver = new ResizeObserver(() => this.schedule()); if (this.resizeObserver) this.resizeObserver.observe(canvas); else window.addEventListener("resize", () => this.schedule());
    }
    initialize() {
      const gl = this.gl;
      const vertexSource = `attribute vec3 a_position; attribute vec3 a_normal; uniform mat4 u_projection; uniform mat4 u_view; varying vec3 v_position; varying vec3 v_normal; void main(){vec4 p=u_view*vec4(a_position,1.0);v_position=p.xyz;v_normal=mat3(u_view)*a_normal;gl_Position=u_projection*p;}`;
      const fragmentSource = `precision mediump float; varying vec3 v_position; varying vec3 v_normal; uniform vec3 u_color; uniform float u_roughness; uniform float u_metallic; uniform float u_edges; void main(){if(u_edges>0.5){gl_FragColor=vec4(0.075,0.12,0.145,1.0);return;}vec3 n=normalize(v_normal);if(!gl_FrontFacing)n=-n;vec3 l=normalize(vec3(-0.5,0.9,1.0));vec3 v=normalize(-v_position);vec3 h=normalize(l+v);float diffuse=max(dot(n,l),0.0);float fill=max(dot(n,normalize(vec3(0.8,-0.2,0.5))),0.0);float power=mix(100.0,6.0,u_roughness);float spec=pow(max(dot(n,h),0.0),power)*(1.0-u_roughness*0.7);vec3 reflection=mix(vec3(0.35),u_color,u_metallic);vec3 color=u_color*(0.24+diffuse*0.66+fill*0.18)*(1.0-u_metallic*0.25)+reflection*spec*0.55;color=pow(max(color,vec3(0.0)),vec3(0.4545));gl_FragColor=vec4(color,1.0);}`;
      const compile = (type, source) => { const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader); if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) { gl.deleteShader(shader); throw new Error("The packaged display shader could not compile in this browser. Geometry checks and retained exports remain available."); } return shader; };
      const vertex = compile(gl.VERTEX_SHADER, vertexSource), fragment = compile(gl.FRAGMENT_SHADER, fragmentSource); this.program = gl.createProgram(); gl.attachShader(this.program, vertex); gl.attachShader(this.program, fragment); gl.linkProgram(this.program); gl.deleteShader(vertex); gl.deleteShader(fragment);
      if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error("The packaged WebGL shader could not link. Geometry checks and retained exports remain available.");
      this.locations = { position: gl.getAttribLocation(this.program, "a_position"), normal: gl.getAttribLocation(this.program, "a_normal"), projection: gl.getUniformLocation(this.program, "u_projection"), view: gl.getUniformLocation(this.program, "u_view"), color: gl.getUniformLocation(this.program, "u_color"), roughness: gl.getUniformLocation(this.program, "u_roughness"), metallic: gl.getUniformLocation(this.program, "u_metallic"), edges: gl.getUniformLocation(this.program, "u_edges") };
      this.buffer = gl.createBuffer(); this.edgeBuffer = gl.createBuffer(); gl.enable(gl.DEPTH_TEST); gl.disable(gl.CULL_FACE); this.schedule();
    }
    setMesh(mesh, appearance) {
      this.mode = "mesh"; nodes["texture-raster"].hidden = true; this.canvas.hidden = false; this.appearance = copy(appearance); if (!this.gl) return;
      nodes["viewport-error"].hidden = true; nodes["gpu-status"].dataset.status = "mesh"; nodes["gpu-status"].textContent = "Packaged visual shader compiled · Approximate diffuse and specular appearance";
      const mins = [Infinity, Infinity, Infinity], maxs = [-Infinity, -Infinity, -Infinity]; for (const v of mesh.vertices) for (let axis = 0; axis < 3; axis += 1) { mins[axis] = Math.min(mins[axis], v[axis]); maxs[axis] = Math.max(maxs[axis], v[axis]); }
      const center = mins.map((n, i) => (n + maxs[i]) / 2); const span = Math.max(...maxs.map((n, i) => n - mins[i])); const scale = finite(span) && span > 0 ? 1.8 / span : 1;
      const coords = mesh.vertices.map((v) => v.map((n, i) => (n - center[i]) * scale)); this.boundingRadius = coords.reduce((radius, vertex) => Math.max(radius, Math.hypot(...vertex)), 0); this.distance = this.cameraFit(); const values = new Float32Array(mesh.triangles.length * 18); const edges = new Float32Array(mesh.triangles.length * 36); let position = 0, edgePosition = 0;
      for (const triangle of mesh.triangles) { const a = coords[triangle[0]], b = coords[triangle[1]], c = coords[triangle[2]]; const u = b.map((n, i) => n - a[i]), v = c.map((n, i) => n - a[i]); let normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; const length = Math.hypot(...normal); normal = length ? normal.map((n) => n / length) : [0, 1, 0]; for (const p of [a, b, c]) { values.set(p, position); values.set(normal, position + 3); position += 6; } for (const p of [a, b, b, c, c, a]) { edges.set(p, edgePosition); edges.set(normal, edgePosition + 3); edgePosition += 6; } }
      this.vertexCount = mesh.triangles.length * 3; this.edgeCount = mesh.triangles.length * 6; const gl = this.gl; gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer); gl.bufferData(gl.ARRAY_BUFFER, values, gl.STATIC_DRAW); gl.bindBuffer(gl.ARRAY_BUFFER, this.edgeBuffer); gl.bufferData(gl.ARRAY_BUFFER, edges, gl.STATIC_DRAW); this.schedule();
    }
    setTexture(image, shader) {
      const raw = atob(image.rgba_base64); if (raw.length !== image.width * image.height * 4) throw new Error("The CPU raster does not match its bounded dimensions."); this.textureSize = [image.width, image.height]; this.textureDisplayReady = false;
      const rgba = new Uint8ClampedArray(raw.length); for (let index = 0; index < raw.length; index += 1) rgba[index] = raw.charCodeAt(index);
      const cpuCanvas = document.createElement("canvas"); cpuCanvas.width = image.width; cpuCanvas.height = image.height; const cpu = cpuCanvas.getContext("2d"); if (!cpu) throw new Error("The browser cannot display the bounded CPU raster."); cpu.putImageData(new ImageData(rgba, image.width, image.height), 0, 0);
      // Never decode a retained PNG in the viewer. This URL is newly encoded
      // from exact-size RGBA, so an altered PNG header cannot allocate pixels.
      nodes["texture-raster"].src = cpuCanvas.toDataURL("image/png"); this.mode = "texture"; this.drag = null; this.canvas.classList.remove("dragging"); nodes["cpu-raster"].checked = false;
      if (!this.gl) { nodes["cpu-raster"].checked = true; nodes["cpu-raster"].disabled = true; this.showCpuRaster(); nodes["gpu-status"].dataset.status = "unavailable"; nodes["gpu-status"].textContent = "GPU display unavailable; bounded CPU raster shown"; nodes["shader-diagnostics"].textContent = "WebGL is unavailable. The displayed raster contains the declared CPU bytes; GPU compilation and pixel agreement remain unestablished."; return; }
      const gl = this.gl; let vertex = null, fragment = null, program = null;
      try {
        const compile = (type, source) => { const compiled = gl.createShader(type); gl.shaderSource(compiled, source); gl.compileShader(compiled); if (!gl.getShaderParameter(compiled, gl.COMPILE_STATUS)) { const diagnostic = (gl.getShaderInfoLog(compiled) || "Shader compilation failed").slice(0, 4096); gl.deleteShader(compiled); throw new Error(diagnostic); } return compiled; };
        vertex = compile(gl.VERTEX_SHADER, shader.vertex_source); fragment = compile(gl.FRAGMENT_SHADER, shader.fragment_source); program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program); if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error((gl.getProgramInfoLog(program) || "Shader linking failed").slice(0, 4096));
        if (this.textureProgram) gl.deleteProgram(this.textureProgram); this.textureProgram = program; program = null;
        this.textureLocations = { position: gl.getAttribLocation(this.textureProgram, "a_position"), uv: gl.getAttribLocation(this.textureProgram, "a_uv") }; if (this.textureLocations.position < 0) throw new Error("The generated shader has no position attribute.");
        if (!this.textureBuffer) this.textureBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, this.textureBuffer);
        // PNG/CPU row zero is the low-v row. Give the top display edge v=0;
        // conventional bottom-v=0 UVs would silently flip asymmetric fields.
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 0, 1, 1, -1, 1, 1, -1, 1, 0, 0, -1, 1, 0, 0, 1, -1, 1, 1, 1, 1, 1, 0]), gl.STATIC_DRAW);
        this.textureDisplayReady = true; nodes["cpu-raster"].disabled = false; nodes["viewport-error"].hidden = true; nodes["gpu-status"].dataset.status = "compiled"; nodes["gpu-status"].textContent = "Generated shader compiled in this browser"; nodes["shader-diagnostics"].textContent = "Generated GLSL compiled and linked in this browser. CPU row zero and the top display edge both use the lower v bound. CPU pixels sample centers with binary64 arithmetic; GLSL samples continuously with GPU float precision. This display check does not establish pixel equality, optical properties, or retained hardware identity.";
      } catch (error) { if (program) gl.deleteProgram(program); nodes["cpu-raster"].checked = true; nodes["cpu-raster"].disabled = true; nodes["viewport-error"].textContent = "GPU compilation failed. The bounded CPU raster is shown; retained CPU verification remains separate. " + error.message; nodes["viewport-error"].hidden = false; nodes["gpu-status"].dataset.status = "failed"; nodes["gpu-status"].textContent = "GPU compilation failed; bounded CPU raster shown"; nodes["shader-diagnostics"].textContent = error.message; }
      finally { if (vertex) gl.deleteShader(vertex); if (fragment) gl.deleteShader(fragment); }
      this.showCpuRaster(); this.schedule();
    }
    showCpuRaster() { const show = this.mode === "texture" && nodes["cpu-raster"].checked; nodes["texture-raster"].hidden = !show; this.canvas.hidden = show; if (!show) this.schedule(); }
    cameraFit() { const aspect = Math.max(0.1, (this.canvas.clientWidth || 1) / (this.canvas.clientHeight || 1)); const angle = Math.min(Math.PI / 8, Math.atan(Math.tan(Math.PI / 8) * aspect)); return Math.max(1.65, this.boundingRadius * 1.12 / Math.sin(angle)); }
    reset() { this.yaw = -0.55; this.pitch = 0.25; this.distance = this.cameraFit(); this.schedule(); }
    schedule() { if (!this.gl || this.frame !== null) return; this.frame = requestAnimationFrame(() => { this.frame = null; this.render(); }); }
    render() {
      if (!this.gl) return; const gl = this.gl, width = Math.max(1, this.canvas.clientWidth), height = Math.max(1, this.canvas.clientHeight), ratio = Math.min(window.devicePixelRatio || 1, 2); const w = Math.round(width * ratio), h = Math.round(height * ratio);
      if (this.canvas.hidden) return; if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; } gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      if (this.mode === "texture") { if (!this.textureProgram || !this.textureDisplayReady) return; const aspect = this.textureSize[0] / this.textureSize[1], drawWidth = Math.min(w, Math.round(h * aspect)), drawHeight = Math.min(h, Math.round(w / aspect)); gl.viewport(Math.floor((w - drawWidth) / 2), Math.floor((h - drawHeight) / 2), drawWidth, drawHeight); gl.useProgram(this.textureProgram); gl.disable(gl.DEPTH_TEST); gl.bindBuffer(gl.ARRAY_BUFFER, this.textureBuffer); for (let location = 0; location < gl.getParameter(gl.MAX_VERTEX_ATTRIBS); location += 1) gl.disableVertexAttribArray(location); gl.enableVertexAttribArray(this.textureLocations.position); gl.vertexAttribPointer(this.textureLocations.position, 2, gl.FLOAT, false, 16, 0); if (this.textureLocations.uv >= 0) { gl.enableVertexAttribArray(this.textureLocations.uv); gl.vertexAttribPointer(this.textureLocations.uv, 2, gl.FLOAT, false, 16, 8); } gl.drawArrays(gl.TRIANGLES, 0, 6); gl.enable(gl.DEPTH_TEST); return; }
      if (!this.vertexCount) return;
      const f = 1 / Math.tan(Math.PI / 8), near = 0.05, far = 30; const projection = new Float32Array([f / (w / h), 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]);
      const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch); const view = new Float32Array([cy, sp * sy, -cp * sy, 0, 0, cp, sp, 0, sy, -sp * cy, cp * cy, 0, 0, 0, -this.distance, 1]);
      gl.useProgram(this.program); gl.uniformMatrix4fv(this.locations.projection, false, projection); gl.uniformMatrix4fv(this.locations.view, false, view); gl.uniform3fv(this.locations.color, this.appearance.base_color); gl.uniform1f(this.locations.roughness, this.appearance.roughness); gl.uniform1f(this.locations.metallic, this.appearance.metallic); gl.uniform1f(this.locations.edges, 0);
      const bind = (buffer) => { gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.enableVertexAttribArray(this.locations.position); gl.enableVertexAttribArray(this.locations.normal); gl.vertexAttribPointer(this.locations.position, 3, gl.FLOAT, false, 24, 0); gl.vertexAttribPointer(this.locations.normal, 3, gl.FLOAT, false, 24, 12); };
      bind(this.buffer); gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(1, 1); gl.drawArrays(gl.TRIANGLES, 0, this.vertexCount); gl.disable(gl.POLYGON_OFFSET_FILL); if (nodes.wireframe.checked) { gl.uniform1f(this.locations.edges, 1); bind(this.edgeBuffer); gl.drawArrays(gl.LINES, 0, this.edgeCount); }
    }
  }
  const renderer = new MeshViewport(nodes.viewport);
  nodes.representation.addEventListener("change", () => { if (state.busy) return; const example = state.examples.find((item) => kindOf(item.request) === nodes.representation.value); if (!example) { showError("This instrument does not expose an example for that representation."); nodes.representation.value = kindOf(state.request); return; } try { loadDefinition(example.request); nodes.example.value = example.id; clearError(); authoringStatus("Representation loaded. Preview remains transient until you retain a run."); if (nodes["live-preview"].checked) preview(); } catch (error) { showError(error.message); } });
  nodes.example.addEventListener("change", () => { const item = state.examples.find((example) => example.id === nodes.example.value); if (!item || state.busy) return; try { loadDefinition(item.request); clearError(); authoringStatus("Example loaded. Preview extracts a transient sampled surface."); if (nodes["live-preview"].checked) preview(); } catch (error) { showError(error.message); } });
  nodes.expression.addEventListener("input", edited); [nodes["expression-0"], nodes["expression-1"], nodes["expression-2"], nodes.resolution, nodes["resolution-2"], nodes["periodic-u"], nodes["periodic-v"], nodes["field-tolerance"], nodes["require-closed"]].forEach((node) => node.addEventListener("input", edited));
  [nodes["base-color"], nodes.roughness, nodes.metallic].forEach((node) => node.addEventListener("input", () => { updateAppearanceOutputs(); edited(); }));
  nodes["parameter-add"].addEventListener("click", () => {
    if (!state.request || state.busy) return; clearError();
    try { const name = nodes["parameter-name"].value.trim(); if (!/^[A-Za-z_][A-Za-z0-9_]{0,31}$/.test(name) || RESERVED.has(name) || (kindOf(state.request) !== "implicit" && ["u", "v"].includes(name))) throw new Error("Use an ASCII parameter name beginning with a letter or underscore. Coordinates and built-in function names are reserved."); if (Object.prototype.hasOwnProperty.call(state.request.definition.parameters, name)) throw new Error("That parameter is already declared."); if (Object.keys(state.request.definition.parameters).length >= MAX_PARAMETERS) throw new Error("A definition supports at most eight declared parameters."); const value = numberValue(nodes["parameter-value"], "Parameter value"), minimum = numberValue(nodes["parameter-min"], "Parameter minimum"), maximum = numberValue(nodes["parameter-max"], "Parameter maximum"); if (minimum > maximum || value < minimum || value > maximum || minimum < -1000000 || maximum > 1000000) throw new Error("The parameter needs ordered bounds inside −1,000,000 to 1,000,000 that include its value. Equal bounds declare a constant."); state.request = readRequest(); Object.defineProperty(state.request.definition.parameters, name, { value: { value, minimum, maximum }, enumerable: true, configurable: true, writable: true }); drawParameterControls(); nodes["parameter-name"].value = ""; edited(); }
    catch (error) { showError(error.message); }
  });
  nodes["live-preview"].addEventListener("change", () => { if (!nodes["live-preview"].checked) cancelPreview(); else edited(); }); nodes.preview.addEventListener("click", () => preview()); nodes.retain.addEventListener("click", retain); nodes["refresh-history"].addEventListener("click", refreshHistory); nodes.replay.addEventListener("click", replay);
  nodes["use-definition"].addEventListener("click", () => { if (state.busy || !state.displayed || !state.displayed.request) return; try { loadDefinition(state.displayed.request); nodes.example.value = ""; clearError(); authoringStatus("The selected run's definition is restored in the editor. Preview or retain to execute it."); } catch (error) { showError(error.message); } });
  nodes["export-obj"].addEventListener("click", () => exportRun("obj")); nodes["export-png"].addEventListener("click", () => exportRun("png")); nodes["export-manifest"].addEventListener("click", () => exportRun("manifest")); nodes["export-json"].addEventListener("click", () => exportRun("json")); nodes["reset-view"].addEventListener("click", () => renderer.reset()); nodes.wireframe.addEventListener("change", () => renderer.schedule()); nodes["cpu-raster"].addEventListener("change", () => renderer.showCpuRaster());
  nodes["contrast-toggle"].addEventListener("click", () => { const enabled = !document.body.classList.contains("high-contrast"); document.body.classList.toggle("high-contrast", enabled); nodes["contrast-toggle"].setAttribute("aria-pressed", String(enabled)); });
  async function initialize() {
    try { const result = await api("/api/examples"); if (!Array.isArray(result.examples) || !result.examples.length || !result.examples.every((example) => object(example) && typeof example.id === "string" && typeof example.label === "string" && object(example.request))) throw new Error("The instrument returned no valid starting definitions."); for (const example of result.examples) checkRequest(example.request); state.examples = result.examples; clear(nodes.example); for (const example of state.examples) { const option = make("option", "", example.label); option.value = example.id; nodes.example.append(option); } state.ready = true; loadDefinition(state.examples[0].request); authoringStatus("Ready. The viewport is a sampled geometry preview; retained runs keep their definitions and checks."); await refreshHistory(); if (nodes["live-preview"].checked) preview(); }
    catch (error) { showError(error.message); authoringStatus("The local instrument is unavailable. Start the workbench server and reload this page."); }
    finally { syncControls(); }
  }
  initialize();
})();
