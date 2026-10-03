# NET scientific browser demo

This browser journey exposes three synthetic estimation experiments through the
existing `ciw.sensor-fusion-ekf.v1` operation: metrology, thermal observation and
planar range tracking. The backend runs the installed Python instruments and
their exact GSIE/JSPT providers. It qualifies all three default experiments by
actual execution and explicit native replay before exposing them in its example
catalogue. A failed qualification keeps the affected operation unavailable.

The demonstration does not admit canonical state, acquire live devices, inspect
private industrial evidence or authorize machine actions. Its estimates and
covariances remain conditional on declared models and synthetic observations.

## Install a fresh environment

Use a native Git checkout containing the imported upstream histories, Git, and
**Python 3.12.14**. A source ZIP or shallow checkout that omits the original
provider commits is insufficient. The setup command reports a missing history
rather than downloading or replacing a scientific provider.

From the repository root:

```sh
python3.12 scripts/prepare_web_demo.py
.venv-demo/bin/python -I -m ciw.demo_server \
  --gsie-repo .demo-providers/gsie \
  --jspt-repo .demo-providers/jspt \
  --host 127.0.0.1 --port 4173
```

For the optional supervised preview, start the same installed Python service on
port 8765, then run the repository's fixed Node proxy on port 4173 (Node 22+):

```sh
.venv-demo/bin/python -I -m ciw.demo_server \
  --gsie-repo .demo-providers/gsie \
  --jspt-repo .demo-providers/jspt \
  --host 127.0.0.1 --port 8765
# In a second terminal, from the repository root:
npm run dev
```

The proxy forwards actual HTTP requests, session cookies and scientific results
to the fixed loopback backend. It does not simulate successful execution. Do not
run the direct port-4173 Python listener and the proxy on the same port at once.

Linux is the qualified execution target. On Windows, the installation script
uses `.venv-demo\Scripts\python.exe`; run the Linux container for qualified CPU,
memory, file-size and process-group limits. Native Windows/macOS execution has
not been qualified for those limits. `--python` selects a
specific interpreter; `--environment` and `--providers` select separate output
directories. The script refuses an existing non-venv directory, a mismatched
Python version or changed provider source bytes.

The script creates an isolated environment, installs exact package versions,
builds a wheel in a temporary staging directory, installs that wheel without an
editable source link, and runs `pip check`. Its installation is independent of
the current working directory. Bundled fixtures and browser assets ship in that
wheel. The preparation manifest is `.demo-providers/setup.json` and records the
source commit, installed module path, package versions and wheel SHA-256.

| Component | Pinned version or revision |
| --- | --- |
| Python | 3.12.14 |
| pip | 25.0.1 |
| setuptools | 84.0.0 |
| wheel | 0.48.0 |
| packaging | 26.3 |
| NumPy | 2.4.3 |
| websockets | 16.0 |
| GSIE | `5241eee6dab434533bdf0cf0e824bc43b4a79831` |
| JSPT | `d910f5a1d7f6dd5f2dd87dfca66990f714f97b18` |

Provider preparation uses the exact retained Git objects locally. It exports
each original commit into a separate minimal Git repository and verifies its
source tree and tracked file bytes. These runtime snapshots do not replace or
rewrite the full native histories retained by the monorepo. Scientific providers
are bound from trusted startup arguments; browser requests cannot supply code,
imports, provider paths or a replacement provider revision.

Package installation requires access to a package index unless an offline
wheelhouse is supplied. Prepare one for the target platform and interpreter:

```sh
python3.12 -m pip download --dest /tmp/net-demo-wheels \
  pip==25.0.1 setuptools==84.0.0 wheel==0.48.0 packaging==26.3 \
  numpy==2.4.3 websockets==16.0
python3.12 scripts/prepare_web_demo.py --wheelhouse /tmp/net-demo-wheels
```

Wheel versions are fixed. Platform wheels, package-index availability and Python
installation remain external dependencies; matching version pins alone do not
claim a byte-identical operating-system image.

## Browser journey

Open `http://127.0.0.1:4173` once startup qualification has completed. Choose an
example, read its state and sensor declaration, adjust the supported controls,
and execute it. Status distinguishes queued, running, completed, cancelled and
failed work. Expand the declaration and evidence panels for model definitions,
uncertainty, observations and provenance. Download the configuration to retain
the exact declared problem and the evidence bundle to retain the native
execution and its scientific identities.

Use Replay on a completed execution to launch a fresh provider execution against
that execution's retained input and runtime binding. A successful replay checks
exact canonical numerical reproduction and creates new execution, result and
verification occurrences. It uses the same pinned implementations;
`independent: false` remains explicit. Inspection and downloads do not rerun the
experiment. Replay establishes neither physical validity nor admission.

The browser has an opaque `HttpOnly`, `SameSite=Strict` session cookie and a
CSRF token. Concurrent visitors have separate retained jobs and evidence. There
is no account system or private investigation import in this public synthetic
journey. Evidence should be downloaded before closing the session or restarting
the service.

| Control | Supported range | Meaning |
| --- | --- | --- |
| Initial temperature shift | −20 to +20 K; default 0 | Changes only the initial prior mean; metrology converts the shift to its normalized coordinate, and thermal shifts core/shell together. |
| Initial x-position shift | −2 to +2 m; default 0 | Range tracking changes the initial x coordinate only. |
| Prior covariance scale | 0.25 to 4; default 1 | Multiplies the full prior covariance. |
| Process covariance scale | 0.1 to 4; default 1 | Multiplies each full declared discrete process covariance. |
| Measurement covariance scale | 0.25 to 4; default 1 | Multiplies each full joint measurement covariance. |

Covariance scaling preserves correlation coefficients and cross entries; standard
deviations scale by the square root of the factor. Observations and sensor/model
maps remain fixed. Downloads retain the complete validated problem declaration,
including the new synthetic prior/noise declaration and original model evidence.

## Scientific interpretation

| Experiment | State and observation | Plot interpretation and limitation |
| --- | --- | --- |
| Metrology | Dimensionless `x=(T−300 K)/(100 K)`; a direct temperature reference and quadratic voltage proxy | Temperature and voltage have separate axes/panels. The nonlinear voltage map can be globally ambiguous. An informative prior and direct reference do not establish general identifiability. |
| Thermal observation | Core/shell temperatures in kelvins; affine discrete two-capacity RC dynamics and direct thermometers | Compare thermometers with the corresponding estimate. Declared interval covariances are not automatically rescaled from a continuous noise model. Parameters describe a synthetic fixture, not a qualified mold or polymer specimen. |
| Planar range tracking | Cartesian `[x,y,vx,vy]`; metric ranges to two declared anchors | Range observations belong in range space; they are not direct Cartesian positions. The range Jacobian is undefined at an anchor, so the model enforces its declared minimum-range exclusion. |

Uncertainty bands show marginal Gaussian standard deviations under the declared
model and local EKF approximation: `mean ± 2 sqrt(variance)`, approximately 95%
under that Gaussian approximation. They do not report an empirically measured
coverage rate. Predictive measurement bands use innovation covariance, including
the declared measurement noise; they differ from state uncertainty bands.
Cross-covariances remain in the downloadable evidence and declaration. Missing
observations are explicitly prediction-only periods and must not appear as
zero-valued samples or invented measurements.

Innovations compare observations with predicted measurements. True posterior
residuals compare observations with the nonlinear measurement map evaluated at
the posterior state; these can differ from the linearized correction residual.
NIS describes the declared innovation covariance and is a diagnostic, not a
certificate of calibrated uncertainty or an automatic outlier rejection gate.

Evidence, operation, execution, result and verification identities remain
separate. Successful mathematical regression and matching numerical replay are
distinct from experimental model validation, state admission and device control.
The existing linear Kalman, scalar-angle and coordinate-transport operations
retain their implementations and contracts. This three-example browser journey
does not imply that every registered NET instrument has been qualified for public
browser execution. See [the EKF scope](SENSOR_FUSION_EKF.md),
[linear fusion](SENSOR_FUSION.md) and [coordinate transport](SENSOR_FUSION_TRANSPORT.md).

## Execution limits and retention

The backend launches fixed Python worker operations in isolated processes with
restricted input schemas and bounded numerical dimensions. Arbitrary callbacks
and executable expressions are refused. Numerical subprocesses use pinned
provider source and recorded interpreter/dependency identity.

| Limit | Default |
| --- | --- |
| Global active jobs | 2 |
| Active jobs per visitor session | 1 |
| Queued jobs | 8 |
| Retained jobs / sessions | 64 / 128 |
| Global retained result bytes | 32 MiB |
| Completed jobs and idle session lifetime | 3,600 seconds |
| HTTP request body / declared source | 32 KiB / 256 KiB |
| Concurrent HTTP connections / socket inactivity timeout | 32 / 5 seconds |
| Worker combined output | 8 MiB |
| Worker wall / CPU limit | 45 seconds / 30 seconds |
| Worker address space / output file size | 2,048 MiB / 8 MiB |
| BLAS/OpenMP threads | 1 |

The three-example workload stays within existing source limits: at most 16 state
coordinates, sensor profiles, sensors per profile, ordered batches and active
measurement channels per batch. Invalid configurations are rejected before
execution. Provider refusals, deadlines, cancellation and exhausted concurrency
produce explicit failure/status responses rather than a synthetic successful
result. Startup qualification uses the same worker limits.

CPU, address-space and file-size resource limits are Linux-specific. Deadline,
output and schema checks are separate limits. Linux workers keep nested provider
processes in the outer worker's group so cancellation/deadline cleanup includes
the actual scientific subprocesses.

Retention is **ephemeral**, bounded and private to the visitor session. Server
restart removes in-memory jobs and sessions; idle/completed-job expiry also
removes retained work. Exhausted retention capacity refuses new work until
capacity is available. Downloads are the durable record available to a
visitor. No persistent industrial evidence store or guaranteed archival service
is introduced by this demo.

## Container and HTTPS deployment

The container build requires a standalone clone with a `.git` directory and the
repository's native object history. A linked worktree's `.git` pointer file is
not a container build input; create a full local clone first if needed with
`git clone --no-local /path/to/repository /tmp/net-demo-build`. Its
Dockerfile-specific ignore file admits only source/build metadata, the setup
script and necessary Git objects/refs; it excludes repository authentication
configuration and hooks. The build stage prepares the wheel and exact provider
snapshots. The final stage ships the installed environment and minimal provider
repositories; it does not ship the entire monorepo history or source worktree.

```sh
docker compose -f deploy/web-demo/compose.yaml up --build --detach --wait
docker compose -f deploy/web-demo/compose.yaml logs --tail 50 demo
curl http://127.0.0.1:4173/api/health
docker compose -f deploy/web-demo/compose.yaml stop
```

The container runs as UID/GID 10001 with a read-only root filesystem, bounded
temporary filesystem, dropped capabilities, `no-new-privileges`, 128 PIDs,
two CPUs and 3 GiB total memory. Its host listener binds to loopback. Worker
limits add a second boundary. There are no mounted live devices, credentials or
private evidence directories. Host-specific firewall/network policy is required
if the deployment must prohibit all outbound connections; the Compose file alone
does not establish an outbound network sandbox.

For public access, choose a Python-capable container host and configure an HTTPS
reverse proxy. `deploy/web-demo/Caddyfile` is an illustrative host-level Caddy
configuration. `demo.notations.io` is an example, not a deployment target already
selected or provisioned. Set both the actual origin used by the backend and the
actual domain used by the proxy:

```sh
export NET_DEMO_DOMAIN=demo.example.com
export NET_DEMO_ORIGIN=https://demo.example.com
export NET_DEMO_PORT=4173
docker compose -f deploy/web-demo/compose.yaml up --build --detach --wait
caddy validate --config deploy/web-demo/Caddyfile
caddy run --config deploy/web-demo/Caddyfile
```

DNS, domain ownership, server credentials, inbound ports 80/443 and the proxy's
certificate storage must be provisioned on the target host. Bind the public
origin explicitly so cross-origin browser operations remain constrained. The
minimal homepage can link “Launch Terminal” to that HTTPS origin once it is
deployed.

Sites Worker hosting cannot spawn CPython scientific subprocesses. It can host
a presentation/client surface, but serving a static client there does not
qualify scientific backend integration. This demo's real execution requires the
Python/container service and an explicit reachable backend deployment. Native
Git source publication and domain deployment have separate credentials and
status; a local commit or preview is not evidence that either has succeeded.

## Qualification evidence and operating checks

Earlier retained qualification at `4871b306` contains 214 passing fusion tests:
51 source-contract, 31 linear/angular workflow, 43 coordinate transport and 89
EKF tests, with no fusion skips. Its 19 retained source hashes matched the audited
baseline. Separate workbench regression evidence included 62 passes and 38 skips
for unprovisioned external calibration, identified-design, ESM and telemetry
integrations. These are scoped historical baseline claims; they are not the
browser demo's end-to-end qualification.

The [current qualification report](WEB_DEMO_QUALIFICATION.md) records installation,
native provider execution, exports, replay, invalid inputs, provider failures,
deadlines, cancellation, concurrent sessions and evidence integrity, with exact
test results and limitations. Browser desktop/mobile rendering and principal
interaction inspection remain **incomplete**: the cloud browser rejected the
preview URL. Source and accessibility-control review are not a substitute for
those browser checks. A preview does not establish production or industrial
readiness. A container tag
in a Dockerfile does not establish that its image was pulled or built; retain an
actual build/run result before claiming container qualification.

Run relevant regression tests from a clean checkout after changes; strict
import-source audits intentionally reject unrelated untracked source files.
Keep reproducible test outputs outside that checkout. A clean isolated worktree
is useful while other agents are changing the active source tree. Do not weaken
source audits to make a dirty development checkout pass.

On startup or upgrades, review the qualification log and `/api/health`; an
unqualified example should remain unavailable. On failed execution, retain the
actionable error and verify that no result is falsely shown as admitted state.
Before a restart, download any visitor evidence needed later. Existing NET and
provider licences, notices, imported source trees and history boundaries remain
in force.
