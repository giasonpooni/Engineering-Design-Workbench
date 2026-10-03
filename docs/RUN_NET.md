# Run NET with the installed public tools

This path uses the existing Terminal package, Session, operation registry and
verification contracts. It connects local analysis, impact, Legibility and
atmospheric handoffs without installing optional native providers or modifying
their execution pins.

## Install and inspect dependencies

From the repository root, use Python 3.11 or newer:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install ".[legibility]"
ciw doctor --profile core
ciw doctor --profile legibility
```

On Linux/macOS, create the environment with `python3 -m venv .venv` and activate
it with `source .venv/bin/activate`, then use the same installation and doctor
commands. Activation is optional: invoke the environment's Python directly with
`-m ciw` or `-m ciw.net` in place of `ciw` or `net`.

The `legibility` extra supplies the pinned cryptography dependency used for
Ed25519 signing and signature verification. The doctor reads installed
distribution metadata and reports expected and observed versions. It neither
imports cryptography nor executes a provider. `preflight_passed` means those
local checks passed; qualification remains `not_performed`.

Inspect the existing catalogs:

```text
ciw capabilities list
net providers --json
net --help
```

The capability index describes selected implemented surfaces. The provider
catalog describes explicitly registered operations. Neither listing binds a
new provider, establishes scientific validity or authorizes execution. The
21 imported instruments retain their own packages and runtime requirements;
the root wheel contains `ciw`, not all of those packages.

## Check the installed operator path

From the checkout, with the installed environment active:

```text
python -I scripts/check_operator_installed.py --output-dir ../net-operator-first-run
```

The check launches installed CLI modules with Python isolation from a separate
working directory outside the checkout. It retains synthetic oscillator analysis, a verified modal
plate impact, a read-only Legibility import, a signed specimen demonstration,
and a dry atmospheric column with impact/fluid/render handoffs. It also checks
a wrong-version refusal and that inspection/verification leave prior bundles
unchanged. Its output directory must be new; choose another name to retain a
second run. Read the resulting `report.json` for the exact checks and
installed package provenance.

This establishes the exercised command lifecycle and declared numerical and
representation checks. The specimen trust anchor is a demonstration key, not
an authenticated organizational issuer. Handoffs preserve source and
verification identities; they do not execute their receiving providers.

## Run an individual workflow

Use new output directories for each retained investigation:

```text
ciw demo --output recordings/demo.json
ciw analyze stats --recording recordings/demo.json --channel q --start 2 --end 8 --output-dir results/stats
ciw inspect results/stats/workspace.json

net impact plate example --output plate-request.json
net impact plate run plate-request.json --output-dir results/plate
net impact plate verify results/plate
ciw legibility import-impact results/plate/workspace.json --object-id notations:specimen:plate-001 --version 1 --label "Plate specimen" --output-dir results/plate-review

ciw legibility demo --output-dir results/legibility-demo
ciw legibility verify results/legibility-demo --trust results/legibility-demo/demo-trust.json --expected-object-id notations:specimen:demo-coupon-001 --expected-version 1

net atmosphere example --output atmosphere-request.json
net atmosphere run atmosphere-request.json --output-dir results/atmosphere
net atmosphere verify results/atmosphere
net atmosphere handoff results/atmosphere --provider fluid --sample-index 5 --output fluid-handoff.json
```

Open the Legibility directory's `review.html` for the offline review. Its JSON
and source artifacts remain the authoritative representation inputs; HTML
integrity is separately unassessed. The impact import currently accepts its
documented Session-v2 contract and refuses correction-journal v4 workspaces
whose dependency eligibility has not been qualified by that adapter.

## Select additional tools explicitly

The [instrument catalogue](INSTRUMENTS.md), [integration coverage](INTEGRATION_COVERAGE.md)
and [superrepo guide](MONOREPO.md) distinguish installed commands, provider
bindings and isolated module gates. From a Git checkout:

```text
python scripts/superrepo.py list --json
python scripts/superrepo.py audit
```

Audit reads source histories, licenses and declared execution bindings. It does
not provision or run providers. Use each instrument's documented installation,
binding and qualification command before selecting it for an investigation.
Private-provider credentials, external engines and physical measurement
equipment are separate requirements. Missing access must remain a reported
blocker, not a simulated successful check.

For a synchronized local session and optional Godot viewport, follow the
[existing quickstart](quickstart.md#shared-terminal-and-viewport). For signed
operator artifacts and independently established trust, follow the
[Legibility guide](LEGIBILITY.md#supply-a-real-source-and-signing-key).
