# Executable agent production workcells

A workcell is an operator-granted unit of **candidate source -> contained build ->
fixed observations/checks -> conditional packaging**, not another NET, agent
framework, game engine, evidence store or source-to-source language compiler.

This increment explicitly joins the existing Foundry packet/inventory/scope
helpers from PR72 at `296457e2bb21cdd412025f1b946db0abf9648606` with the original
MCP/server/source-selection modules from PR60 at
`009144f6f951d5999df07294965db221d0817b05`. The original eleven-tool scientific
MCP host remains available. Its transport additionally accepts a host-specific
tool catalog/instructions. Session, graph runner, production dependencies,
acceptance/refusal semantics and original tests remain unchanged.

The DSP, GIS and other active branches are not silently merged or replaced.
Generated multilingual instrument interfaces remain a separate complementary
capability; this cell's first compiler recipe is Python/GDScript/Godot.

## First working recipe: compile an asset and a mechanic

The installed `godot-prop.v1` recipe consumes exactly three source files:

| File | Authority |
|---|---|
| `compiler.py` | Candidate-editable small mesh compiler; executed inside the cell. |
| `motion.gd` | Candidate-editable movement rule; compiled/loaded and tested by Godot. |
| `spec.json` | Operator-locked geometric brief; not an agent write target. |

The example in `examples/workcells/godot-prop` is original demonstration content:
a small moving-platform test prop, **not a reconstruction or modification of1792**.
The model derives a binary mesh resource (`prop.res`) and scene (`main.scn`),
checks the candidate mechanic against fixed input/output and120-tick trajectories,
then produces `slice.pck` only after all required conditions pass. A fresh Godot
process loads the PCK's resources and checks the packaged scene. The package can
be opened with the corresponding Godot engine; Space/Enter toggles the platform.
It is a bounded interactive test slice, not a complete game or platform export.
GDScript is compiled by Godot on loading; this is not an AOT machine-code claim.

The compiler is itself an agent-editable source artifact. Thus agents can improve
a bounded asset compiler and have its *generated asset* tested before downstream
assembly is allowed. Promoting that compiler to a new trusted image/recipe is a
separate operator-reviewed revision, never a self-awarded privilege.

## The threshold is an executable condition

The original production controller runs three jobs, sequentially:

```text
build asset/scene -> fixed asset checks
                  -> fresh-container mechanic/scene tests
                  -> fixed correctness/integration checks
                  -> package, ONLY if already granted
                  -> fresh packaged-resource smoke process
```

Every required check must pass. There is no weighted percentage allowing a failed
critical condition to be averaged away. Failed or indeterminate jobs block their
descendants. Rejected candidates remain retained. A compiled mesh alone does not
qualify its mechanics. An LLM's assessment never substitutes for these checks.

The same model/client may reason, author a candidate, inspect the diagnostics,
correct its source and submit again. It cannot replace the source brief, checks,
image, host command, budgets or publication authority. A passing stage unlocks
**existing authority**, not the ability to invent wider permissions.

A new compiler/runtime, whole-game packaging recipe or new tools are separate
candidate workloads with their own explicit inputs/tests. This first recipe does
not yet expose arbitrary Blender projects, C++/Rust builds or1792 release builds.

## Agent connection: existing MCP stdio, four workcell tools

| Tool | Behavior |
|---|---|
| `net_cell_describe` | Return the fixed packet/context, available rights and remaining budget. |
| `net_cell_submit` | Check and freeze permitted complete source replacements; no execution. |
| `net_cell_build` | Invoke the original production controller; conditional assembly follows fixed checks. |
| `net_cell_inspect` | Recompute checks against retained evidence without any engine/container launch. |

No tool accepts shell commands, filesystem roots, executable/image selections,
new check thresholds, agent spawning, Git writes, merge or release requests.
Changes use exact granted filenames, not globs or paths selected by the model.
Unknown/oversized fields refuse. MCP context is task data, not privileged
instructions. Source diffs and runnable artifacts are distinct deliverables.

This is provider-neutral: an open-source coding host or reasoning agent that
supports the qualified MCP stdio profile can use it. The qualification uses an
independent official MCP Python SDK1.26.0 client negotiating2025-11-25. It does
not invoke a model, configure a user's account or measure autonomous throughput.
Newer protocol versions/hosts require compatibility testing, not assumed support.

## Container boundary

The operator builds the tool image *before* agent execution and grants its exact
local image ID. The execution path never pulls images, installs packages, passes
model/API credentials, exposes a Docker socket to candidate code, or mounts a
live repository. Only a fresh immutable source/artifact snapshot is bind-mounted,
read-only. Work happens in bounded tmpfs; output crosses as size-checked, hashed
bytes, not an extracted untrusted archive or writable host directory.

The initial Linux/amd64 Docker profile requests and inspects before starting:
network=none, read-only root, UID/GID65534, all Linux capabilities dropped,
no-new-privileges,1CPU quota,512MiB memory+swap ceiling,64PIDs,64MiB work scratch,
8MiB temporary scratch, bounded file descriptors/files and disabled daemon logs.
Each stage has a45-second outer deadline; contained commands have20-second limits.
The controller reaps its unique container even after an attached-process timeout.
No default unrestricted-local-process fallback exists.

Docker's daemon/image and the host are trusted. This is **not VM isolation**, a
kernel-escape proof, complete supply-chain attestation or crash-resumable leasing.
The stdio MCP host runs with the launching user's privileges. An agent with an
independent unrestricted host shell could bypass an MCP-only scope; deploy the
supervisor under separately controlled privileges and do not grant that agent
host/Docker access. The four tool interfaces are not an OS security boundary.
Untrusted external MCP servers are not dynamically imported by this workcell.

The recipe scripts are read-only image inputs; independent host checks compare
raw outcomes, not worker PASS flags. These finite tests detect their specified
failures; they do not prove arbitrary malicious code correct. Geometry bounds and
mechanic tests are not aesthetic quality, collision-system coverage, historical
verification, controller feel, GPU profiling, rights clearance or release approval.

## Budgets, retained output and reuse

Slots default to8 immutable candidates and8 intentional production runs; the
operator can select1..16 of each. Each run reserves at most3 operation nodes.
All stages remain sequential under one supervisor. Source replacements are bounded
at64KiB per file and128KiB total; artifacts512KiB each/2MiB total. This is not a
large binary-asset depot. The original packet helpers preserve their stricter
path, symlink, original-test and source-snapshot constraints.

The same attempt/request reuses its response in that host process. A new attempt
is an intentional fresh execution. There is no cross-restart exactly-once claim;
startup requires a new output directory. Ambiguous interrupted attempts do not
silently rerun. Parallel independent cells are possible as separate deployments,
not an implemented distributed scheduler or an exponential speedup measurement.

Sources, scope checks and run declarations are frozen. Build/test outcomes use
original Session operation/execution/result records. A successful capture of a
compiler error remains a **failed build**, not an accepted artifact. The final
PCK is exported only from the accepted package result. The reader freezes a bounded copy once, recomputes original acceptance and
checks any exported PCK against its retained bytes. It does not reread the
original files after validation to construct its summary.
No ordinary result acquires a formal verification ID, ESM admission or release
permission. Model-token/cost/human-hour fields are null until measured.

## Operator setup

First build the image in an isolated provisioning environment. The Dockerfile
requires an explicit BASE digest and a verified Godot4.5.1 Linux binary named
`godot` in its context. The dedicated workflow demonstrates this process, records
the resolved base digest and final image ID, and verifies the unchanged official
Godot ZIP SHA256 `02ec53d1cc7dbb9cc6355393c61b9ab43d1244751a124f10248a4802830788cd`.
Package installation during image provisioning is not part of an agent execution;
the finished image is the runtime pin. No byte-reproducible-image claim is made.

Then install this integration branch and explicitly configure a work slot:

```sh
python -m pip install -e '.[dev]'
net workcell configure --source-root examples/workcells/godot-prop \
  --docker /usr/bin/docker --image-id sha256:EXACT_LOCAL_IMAGE_ID \
  --allow-package --output-dir results/cell-profile
```

`configure` declares the source/image and writes `profile.json`; it does not start
a container. Omit `--allow-package` to permit only compilation/testing.

Register with an MCP-compatible host using its local stdio server configuration:

```json
{
  "mcpServers": {
    "net-workcell": {
      "command": "/absolute/path/to/python",
      "args": ["-I", "-m", "ciw.workcell_cli", "serve", "--profile", "/absolute/path/results/cell-profile/profile.json"]
    }
  }
}
```

This generic configuration needs adaptation to the selected host's supported
format. One server instance uses a fresh profile output directory. No background
worker is installed just by committing these files.

For a non-MCP deterministic invocation, supply a JSON object of candidate source
replacements (an empty object builds the frozen baseline):

```sh
net workcell run --profile results/cell-profile/profile.json --changes candidate.json
net workcell inspect results/cell-profile/cell/runs/build
```

The exact package is `results/cell-profile/cell/runs/build/slice.pck` on success.
Run it using Godot4.5.1 `--main-pack /absolute/path/slice.pck`.

## Qualification sources

`tests/test_workcell.py` explicitly models container responses for contract and
orchestration tests. It is not native isolation evidence. The dedicated
`scripts/check_workcell.py` uses the real MCP client, server subprocess, Docker
and Godot to test baseline, failed mechanic, correction, failed mesh compiler,
actual isolation probes and timeout cleanup. The original MCP campaign is rerun
separately so the extension cannot replace or quietly break the old tools.

Primary references:
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/SECURITY.md
- https://docs.docker.com/engine/containers/run/
- https://docs.docker.com/engine/containers/resource_constraints/
- https://docs.godotengine.org/en/4.5/classes/class_pckpacker.html
