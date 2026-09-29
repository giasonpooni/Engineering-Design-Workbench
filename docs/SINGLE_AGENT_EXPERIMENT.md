# Single-agent visual revision through an existing workcell

This increment measures real externally authored model work instead of replaying
canned defects/corrections. It does not add another agent server, numerical
engine, game-state owner, acceptance policy, model API or privileged shell tool.

The first agent is the interactive coding/vision assistant in the initiating
conversation. Its source decisions are frozen under the title's licence and
executed by an unchanged workcell through the official MCP client. The runner
is a deterministic courier: it does not choose the source, write repairs or
require the candidate to succeed. The next decision belongs to the same actual
model session after it has received the actual result/previews.

This is a session-driven LLM trial with a CI/MCP relay, not a fully unattended
provider API loop. The assistant also authored the relay; therefore this is not
an independent/blinded benchmark. Model identity and viewed-input references are
explicit self-reports, not vendor-signed attestations. No model credentials are
required, inspected, transmitted into containers or configured by this change.

## Existing authorities

Use the exact PR75 workcell and PR39 title capsule. Candidate authoring remains
restricted to the existing two paths. The original `1792.smith.v1` policy,
source checks, Docker image binding, no-network/read-only execution, input and
artifact bounds, native reducer checks, camera/tick and packaging conditions
remain unchanged. The image is operator-provisioned, not selected by a model.
The original scientific and executable workcell tools remain intact.

One trial uses one baseline control and one frozen revision in a single slot;
max_candidates=max_runs=2. Native builds remain sequential. A new response is a
new explicit trial. There is no cross-restart exactly-once guarantee. No
source change can promote itself to a trusted tool, main merge or release.

## Reusable response boundary

`ciw.agent_experiment.read_revision` reads a content-pinned
`ciw.agent-revision.v1` document containing one declared agent, a bounded public
decision summary, prior-evidence references, and hashed source-file replacements.
It rejects unknown fields, non-granted paths, linked files, oversized inputs,
changed bytes and self-awarded billing/time/review claims. It never executes the
source. Prior-evidence references record the claimed input history; they do not
prove that a remote provider consumed an image.

`scripts/run_agent_workcell_experiment.py` freezes that response before dispatch,
records each MCP request before sending it, retains responses and native image
bytes, and measures the original outcomes. Rejections and holds remain recorded;
there is no assertion that an LLM must pass. A failed control stops the trial
rather than assigning blame to the candidate. A fatal relay error retains an
interruption marker and prior calls, not a successful summary.

`audit_attempt` rechecks the original workcell records from one private bounded
snapshot before deriving metrics. It never executes providers. The code does
not promote a mere hash, package header or model self-assessment to acceptance.

## Measurement meanings

| Field | Meaning |
|---|---|
| Unique changed candidates | Distinct source identities other than the baseline; repeated builds do not inflate it. |
| Technically accepted revisions | Distinct candidates whose original required package job passed. |
| Captured stage wall seconds | Original container-stage measurements, including their scoped overhead; not CPU/GPU time. |
| Experiment wall seconds | Profile/MCP/baseline/revision/preview/audit time; excludes model generation, runner provisioning and queue time. |
| Token/cost/human-time fields | Null because no provider billing or active human-time telemetry is available. |
| Independent art acceptance | Unreviewed/null; pixel differences and nonblank checks cannot establish it. |
| Merged revisions | Zero; this trial does not perform merges. |

Do not infer quality improvement from accepted source count, source-line count,
number of nodes, image difference or one successful package. Do not infer a
per-human-hour rate from elapsed CI seconds. Preserve source revision, image ID,
recipe policy hash and exact occurrence identities beside the observations.

## Run

After provisioning the existing operator image and installing this branch:

```sh
python scripts/run_agent_workcell_experiment.py \
  --title-root /absolute/path/1792/game \
  --source-profile /absolute/path/1792/tools/net/smith-workcell.profile.json \
  --profile-sha256 sha256:afe9f6ef3eec76126d0f56738c5ee762de6eaa8ea58b13dd5ba92b23ecd1ab8f \
  --docker /usr/bin/docker --image-id sha256:EXACT_LOCAL_IMAGE_ID \
  --response /absolute/path/1792/experiments/single-agent-smith/c01/decision.json \
  --response-sha256 sha256:EXACT_RESPONSE_DIGEST \
  --agent-id interactive-coding-vision-01 --output-dir results/agent-trial-01
```

Use a new destination. The optional official `mcp==1.26.0` client is an experiment
dependency, not a new mandatory NET runtime dependency. The dedicated workflow
records source/policy pins, builds the same tool image, runs source and installed
contracts, and retains all trial data irrespective of candidate acceptance.
The title-owned source response stays in the title repository, not NET.

The next artifact after execution is a clearly labelled visual review of actual
native output, followed by either a source revision or a stopping decision. A
future unattended provider/usage adapter needs explicit user-selected model,
endpoint, credential and spend policy; none is silently inferred here.
