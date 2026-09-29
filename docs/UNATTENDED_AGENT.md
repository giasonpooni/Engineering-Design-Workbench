# One unattended coding/vision worker through the existing MCP workcell

This optional layer advances PR76's session-authored trial to an actual model
endpoint. It does not replace WorkcellHost, DockerCell, the Session, production
DAG, source permissions, PNG checker, acceptance policy or old experiment reader.
The first provider is **an explicitly selected, already provisioned local Ollama
server**. Existing coding hosts can still use the original MCP tools directly.
No OpenAI/Anthropic subscription, API key, service or paid endpoint is inferred.

## Execution

The finite controller runs the unchanged baseline, obtains actual daylight and
evening PNGs over the existing MCP interface, and sends the operator-selected
source context, fixed acceptance, current diagnostics and those images to the
pinned model. The model can propose up to four exact unique-substring edits in
already granted files, or stop. The host converts validated edits into full
candidate replacements for the original scope checker, builds them, obtains new
images and returns that feedback on the next bounded model call.

No model text is evaluated or imported by the supervisor. There is no shell
operation, fuzzy patch application, arbitrary external MCP server, agent spawning,
model-selected endpoint/tool image or self-issued acceptance/release grant.
An earlier failed candidate's source can be corrected; a duplicate/unchanged
candidate does not consume a new native build or inflate distinct revision yield.
A stop after a technical pass is an operator option, not artistic approval.

The provider is an independent computation host, not a child of the asset build
container. Source/PNG data leaves the workcell only through the explicit local
inference connection. Build containers retain their no-network/read-only/nonroot
constraints. The model server, daemon and local host remain operator-trusted.
MCP and a loopback URL alone do not sandbox an unrestricted external agent.

## Provider and accounting contract

A strict `ciw.local-model-profile.v1` pins an HTTP endpoint with a literal
127.0.0.1 or ::1 address and explicit port, model name, full model digest and
server version. `/api/version`, `/api/tags` and `/api/show` are checked before
and after inference. Cloud model declarations, redirects, credentials in URLs,
remote hostnames, missing models/capabilities and identity drift refuse. The
client never pulls models, inherits HTTP proxy credentials or retries a call.

`/api/chat` is non-streamed, with a bounded JSON action schema and explicit
`num_ctx`/`num_predict`. Context bytes are bounded and never silently omitted by
NET. This is not independent proof of a server's tokenizer, context truncation,
weights, backend or execution fidelity. Endpoint/model identities and usage are
server declarations, not cryptographic inference attestations. Configure the
server with `OLLAMA_NO_CLOUD=1`; enforce inference egress in its deployment too.

Every call reserves the configured full context plus maximum output BEFORE
request dispatch. A subsequent call starts only if the remaining token budget
and optional operator rate-card estimate can cover that reservation. Successful
usage is taken only from the server's `prompt_eval_count`/`eval_count` fields,
never from generated prose. Counts are strict nonnegative integers, not booleans.
A provider overrun is retained as a breach and stops further work.

An optional decimal rate card produces **an estimate**, never an invoice or the
full hardware/energy/hosting cost. With no rate card, estimated dollars are null.
Billed dollars, active human time and accepted output per human hour remain null
unless a future independently supplied measurement path establishes them.
Inference duration, workcell stage duration and broader experiment wall time
remain separate. Provisioning/CI queue/human setup are excluded from the runner's
experiment timer; do not report its seconds as the total production cost.

Timeouts, malformed responses, truncated generation, identity drift and missing
usage halt without applying source or trying another endpoint. Unknown usage
keeps its reservation and is reported incomplete, not zero. Closing the HTTP
connection does **not prove remote inference has stopped**; the operator owns
server cancellation/cleanup. No crash-resume, background daemon or exactly-once
billing guarantee is claimed. Re-execution needs a new explicit output directory.

## Operator setup

Provision a local Ollama installation/model separately. Pin the actual version
and digest reported by that installation; no default model is secretly selected.
The live CI profile provisions Ollama0.12.7 and qwen3-vl:2b-instruct, then switches to a
read-only model volume on a Docker internal network with cloud disabled. A bounded
host-loopback socat relay connects to its fixed inspected private address because
Docker does not publish ports on an internal-only gateway. The model never gains
a second external network. Relay binary/version and isolation metadata are retained. It
records the resolved image/model identities before the agent runs. This is a
scoped integration test, not a recommendation or a new default dependency.
The explicit instruct variant avoids relying on `think:false` to disable a
separately trained thinking model; no fallback changes the model during a run.

Prepare the existing title workcell as documented in `TITLE_WORKCELLS.md`.
The runner copies its exact capsule into a new investigation and only narrows its
write/candidate/run grants. It does not edit the supplied profile or game checkout.
The first unattended CLI supports the installed title recipe; no universal game
or programming-language worker is claimed.

Example `model.json` (replace model/digest/version with real selected values):

```json
{
  "schema": "ciw.local-model-profile.v1",
  "endpoint": "http://127.0.0.1:11434",
  "model": "qwen3-vl:2b-instruct",
  "model_digest": "sha256:REPLACE_WITH_FULL_LOCAL_MODEL_DIGEST",
  "server_version": "0.12.7",
  "num_ctx": 16384,
  "num_predict": 768,
  "max_calls": 2,
  "max_total_tokens": 36000,
  "timeout_s": 600,
  "vision": true,
  "pricing": null
}
```

Example task:

```json
{
  "schema": "ciw.unattended-task.v1",
  "goal": "Inspect the images. Improve one material contrast without adding geometry. Inspect the result and stop.",
  "editable_paths": ["workshops/workshop_world.gd"],
  "context_paths": ["workshops/workshop_world.gd", "presentation/workshop_kit.gd"],
  "max_revisions": 1,
  "stop_after_accept": false
}
```

With the existing workcell profile and the exact SHA256 of each operator document:

```sh
python -m pip install -e '.[dev]' mcp==1.26.0
python -m ciw.agent_unattended run \
  --workcell-profile /absolute/path/profile.json --workcell-profile-sha256 sha256:EXACT_HASH \
  --model-profile /absolute/path/model.json --model-profile-sha256 sha256:EXACT_HASH \
  --task /absolute/path/task.json --task-sha256 sha256:EXACT_HASH \
  --output-dir results/unattended-001
python -m ciw.agent_unattended inspect results/unattended-001
```

Only the runner command needs the optional MCP client dependency; the original
terminal's default dependency set and module behavior are unchanged. No model
weights or inference daemon are installed by importing this code.

## Retention and verification

Model request intents are retained before dispatch. HTTP requests/responses are
bounded hashed objects; MCP responses reuse the existing chunked SDK transcript
format. Images are original PNGs with identity checked against their MCP result.
Source proposals, rejected builds and original workcell histories remain retained.
The inspector freezes bounded ordinary files once, recomputes usage/reservations,
checks transmitted proposal-to-candidate identity and invokes the original
provider-free workcell gates. It starts no model, container or engine. Hashes
check content integrity, not producer authenticity or physical truth.

The automated live qualification must show real model responses, positive
reported input/output token counts and a re-auditable baseline. **It must not
require that the model's creative proposal passes.** Model refusal, malformed
edits or a technically rejected candidate are outcomes to retain, not invitations
to substitute a canned answer. Unit HTTP/model/cell fixtures remain explicitly
labelled non-LLM/non-native evidence. Validity of the measurement is separate
from creative success and independent artistic review.

## Primary interface references

- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/tags
- https://docs.ollama.com/capabilities/structured-outputs
- https://docs.ollama.com/faq
- https://github.com/ollama/ollama/releases/tag/v0.12.7

Qualification scope and counts are determined by actual workflow reports, not
by the presence of this guide. Real-title high-fidelity art, physical-GPU frame
rate, console release, human review and repeated-task productivity distributions
remain separate requirements.

### Initial deployment correction

The first completed hosted attempt passed726 source tests and installed the
selected1.9GB vision model, but failed before inference when a localhost-published
port was not created for the internal-only Docker network. The retained model log
showed the server was listening. The corrected provisioning explicitly relays
one host-loopback port to the inspected internal model address. Candidate scope,
model, numerical/visual gates and inference budgets are unchanged. The relay is
operator infrastructure, not an agent-selected proxy or a new public listener.
Reference: https://docs.docker.com/engine/network/port-publishing/

### Model resource and receipt qualification

The next hosted attempt reached the actual pinned model, but its declared
weights/KV/compute requirement was7.9GiB at the selected16384-token context. The
4GiB model-container limit killed the native runner. NET retained the one request
with unknown usage and no candidate, did not retry it, and did not impute zero
cost. A new explicit operator deployment raises only the model-container cap to
10GiB; the source task, token/context limits and512MiB asset-build cells are
unchanged. This is a bounded CPU integration profile, not a memory/performance
recommendation for every model or machine.

Four additional audit regressions reject Boolean receipt indexes/reservation
counts, floating-point substitutions for reported integer token counts, and
negative observation durations. Those initially reproduced false acceptances in
the new reader; exact typed checks now reject them. The model inference and
original game acceptance algorithms are unchanged.
