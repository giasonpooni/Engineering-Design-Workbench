# Computational microscope: select source, inspect meaning, compare evidence

**Code is one representation of a computational object.** NET connects a selected
source span to a declared operation, mathematics, relations, invariants and retained
experiments without acquiring the specialist repository's scientific authority.

This branch implements a bounded developer workflow, not just schema names:

```text
committed source -> symbol/span -> retained selection -> agent context / offline view
                                      |                      |
                              inert perturbation       candidate scope check
                                      |
                           existing CIW evidence comparison
```

## Try the real source workflow

From a checkout containing this branch, install the project and capture the
existing statistics provider. No selected code is imported or executed.

```sh
python -m pip install -e '.[dev]'
net object index --repo-root . --repository giasonpooni/Notations-Engineering-Terminal --revision HEAD --path src/ciw/adapters/oscillator.py --output results/object-index.json
net object capture --repo-root . --repository giasonpooni/Notations-Engineering-Terminal --revision HEAD --path src/ciw/adapters/oscillator.py --symbol compute_statistics --declaration examples/computational-objects/statistics.json --editable --output results/object-selection.json
net object context results/object-selection.json --output results/object-context.json
net object view results/object-selection.json --output results/object-inspector.html
```

Open `results/object-inspector.html`. The offline page provides source, declared
mathematics, unresolved syntactic calls, declared relations, invariants, evidence
references and the proposed edit envelope. It uses no scripts, server or network.
All output paths are create-only; use new paths for subsequent experiments.

For a method use its qualified name, such as `Integrator.step`. `--line 42`
selects the innermost definition covering that physical line. Decorators are
included. Duplicate qualified definitions require a line to disambiguate.

Rust, C++, Julia, WGSL, GDScript and TypeScript support exact, explicit line spans:
use `--language rust --span 10 25` instead of `--symbol`. This is **not** an AST,
LSP or type-resolution implementation for those languages. Python indexing uses
the host Python AST grammar; unsupported syntax is refused, not guessed.

## Source and identity boundaries

`capture` resolves the supplied local Git ref to a commit and reads its regular
file blob, not the working tree. Uncommitted changes are deliberately excluded.
Symlinks, submodules, missing files and files over 65,536 bytes are refused. Git
replacement objects, inherited Git-directory overrides, lazy fetching and network
transports are disabled for capture. No Git hooks or content filters are invoked.

The snapshot retains exact UTF-8 bytes, including line endings, a full-file SHA-256,
Git blob ID and commit. The repository label is operator-declared. Offline reopening
checks content and selection consistency; it does not authenticate the repository
owner, independently prove commit inclusion or trust a self-resealed document.
Use a trusted checkout and trusted retained artifact digests for provenance.

The original contracts remain:

| Contract | Role |
| --- | --- |
| `ciw.computational-object.v1` | Descriptive source, operation, mathematics and reference relations |
| `ciw.computational-selection.v1` | Object digest, requested views and proposed edit path |
| `ciw.context-package.v1` | Object and direct declared neighborhood; no execution authority |
| `ciw.perturbation-request.v1` | Data-only proposed variation, never a command |
| `ciw.computational-comparison.v1` | Legacy structurally aligned raw-number diagnostic only |

The new source snapshot and selection records retain enough source to recompute
the selected span and syntactic references. `ciw.source-context.v1` exports only
the selected excerpt plus declarations/references, not the entire file. Reopen it
against the retained capture with `validate_source_context`. References are not
recursively fetched; declared consumers are not a discovered call graph. Source
comments, docstrings and reference labels must be treated as untrusted agent input.

## Perturbation, edits and comparison

```sh
net object perturb results/object-selection.json --dimension parameter --change change.json --output results/variation.json
net object check-edit results/object-selection.json --candidate candidate.py --output results/edit-check.json
net object compare results/object-selection.json left-observations.json right-observations.json --atol 0.001 --rtol 0 --output results/comparison.json
```

`change.json` is ordinary data, for example `{"interval_s":{"from":[0,12],"to":[0,6]}}`.
It does not run a provider. Execution remains with the existing Session, registry,
`net run` and scientific workflows; selection does not dynamically bind source code.

`--editable` proposes a path, not permission. `check-edit` reads candidate file
bytes and requires the original prefix and suffix outside the selected line span
to remain identical. It does not apply a patch, compile it, assess semantic safety
or verify mathematical invariants. File-level v1 envelopes now have a usable,
stricter line-scope check without altering their wire shape.

The source comparison reuses **the existing** `control_checks.compare`. Inputs
are CIW observation lists or `ciw.observation-stream.v1`, not arbitrary flattened
JSON. It retains both inputs and their original execution/provenance identities,
and checks quantity, unit, frame, model/entity, clock, exact time grid and shape.
No interpolation, unit conversion, missing-value filling or covariance repair is
introduced. Right-hand evidence is the comparison reference. Exit codes are
0 = PASS, 2 = FAIL, 3 = INDETERMINATE, 1 = refused input or I/O failure.

`validate_source_comparison` rechecks both the native report and capture binding.
A comparison is still `not_verified`, with no verification occurrence or state
admission. Linking observations to a selected object is descriptive: it does not
prove that a particular source span produced those observations.

## Algebra, composition and topology

Domain, codomain, expression, units and assumptions are explicit declarations,
never extracted as mathematical truth from function names. Equivalent implementations
and compositions are proposed relations, not equivalence proofs. Existing numerical
comparisons can inspect retained outputs of alternative paths; they do not establish
categorical laws or universal commutativity.

The v1 topology/geometry/composition view labels remain extension points. No
persistent-homology engine, manifold inference, theorem prover, code-to-equation
translator, automatic dependency closure or cross-language semantic equivalence is
claimed here. Those providers can attach artifacts without replacing these records.

## Validation

```sh
python -m pytest -q tests/test_computational_objects.py tests/test_computational_source.py
```

The original five cases are retained. Additional cases exercise actual local Git,
decorators/nesting/ambiguous symbols, Unicode and CRLF bytes, explicit polyglot spans,
authority and digest tampering, duplicate JSON, out-of-span edits, source-code
non-execution, strict typed comparison and real existing Session executions.
`validation/source_selection_browser.py` exercises the actual offline page.

The parent Session, Workbench, operation registry, numerical kernels, runtime pins,
licenses and existing workflow gates are unchanged. This remains a stacked draft
extension of the NET control branch, not a main-branch release or deployment.
