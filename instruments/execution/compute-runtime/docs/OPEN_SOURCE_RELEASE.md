# The open-source releases

This repository publishes **two** distributions under Apache-2.0, and
they are two because the repository contains two programs. Measured
across every file in both, the twin compiler (`core`, `morpho`,
`backends`, `runtime`, `adapters`, `renderer`) and the evidence platform
(`evidence`, `scout`, ...) have **zero imports in either direction**, and
no production code outside the twin compiler imports it at all -- not
here, and not in either sibling repository (DAQ: 0, SCL: 0, against 335
imports of the evidence platform). One name over two programs would be
one distribution claiming to be two things.

| distribution | what it is | deriver |
|---|---|---|
| `provenance-pool` | the evidence model: an append-only pool with a strict admission gate | `release/provenance_pool/build.py` |
| `canonical-state` | the state model: one immutable versioned truth, every view a projection that cannot write back | `release/canonical_state/build.py` |

`canonical-state` is deliberately **not** presented as a scientific or
numerical tool, because measurement says it is not one: the shipped
packages import no numeric module at all, and `backends/simulation` and
`backends/neural` say in their own docstrings that they are interface
shapes only. See `docs/CANONICAL_STATE_RELEASE.md` for that release's
own account, including the two defects its deriver found.

---

# `provenance-pool`

This says what ships, why it is derived rather than copied, and what it
refuses.

```bash
python3 release/provenance_pool/build.py --check      # verify
python3 release/provenance_pool/build.py --out DIR    # emit
```

## What ships

| package | LOC role |
|---|---|
| `evidence` | pool, admission gate, content-addressed identity, four classes, quarantine, trust graph |
| `scout` | acquisition pipeline, adapters, extraction, content gates |
| `retrieval` | query and context assembly |
| `materials` | experiment design and active learning |
| `experiment` | session and policy layer |
| `operations` | the second ledger — an append-only trace of what the process did |

**61 modules, 9,426 lines, 48 test files, zero dependencies.**

Those four numbers are checked against the repository by
`tests/test_docs_match_measurement.py`. The suite's *result* — 557 tests
passing in the derived tree at the time of writing — is deliberately not
pinned there: it is a fact about a run, and a test asserting it would
fail for being run somewhere else, which is not drift.

## Why a deriver and not a directory of copied source

The obvious move is to copy the packages into `release/` and commit them.
That would put two byte-identical copies of nine thousand lines in one
repository, and the moment one was edited the other would be silently
wrong with nothing recomputing the difference.

This project has a name for that. **A mirror is not a source**, and
byte-identity is exactly what makes a mirror dangerous. The rule was
found at file scale — an emitted register re-read as its own input, 26
invariants becoming 77 — and again at repository scale, where eleven
third-party repositories sat under this organisation's own GitHub org
with the URL agreeing with the claim.

Committing a second copy of `evidence/` here would be that defect a
third time, introduced deliberately, by the party that wrote the rule.

So the release is a **projection**. The packages in this repository are
the source; the distribution is derived on demand and never committed.
The only things stored under `release/` are the parts that exist *only*
in the release: licence, notices, packaging, README, CI.

## What it refuses, and why each refusal exists

| refusal | why |
|---|---|
| a module importing outside the shipped set | a release that cannot import itself on a clean machine is not a release |
| a machine path anywhere in the emitted tree | it resolves to nothing for a user, and a stranger would find it first |
| an empty test selection | a suite that selected nothing reports success having verified nothing |
| a suite that fails **in the derived tree** | passing here is not evidence about there |
| a file that does not parse | it would fail at import for whoever installed it |
| a missing declared package | a projection of a surface that moved is a projection of something else |

Imports are measured by **parsing, not grepping**. A source grep tests
spelling; a parse tests what the module does.

## Two defects the deriver found on its first runs

**An annotation-only import.** `experiment/step.py` annotated a
parameter with `operations.trace` under `if TYPE_CHECKING:`. That import
never executes — which is precisely why importing all 54 modules
succeeded and proved nothing — but `mypy` and `typing.get_type_hints()`
would both have broken for anyone who installed the package. It is why
`operations` ships, and why the import check deliberately reads
`TYPE_CHECKING` blocks.

**Verifying the tree is what dirtied it.** `copytree` correctly refuses
to carry `__pycache__` across, and then the verification step ran pytest
*inside* the emitted tree and wrote fresh bytecode there, after the copy
that had been careful about it. The build log said everything passed and
was telling the truth — about a directory that also held six
`__pycache__` folders. Found by looking at the emitted tree rather than
at the log.

Both are the same shape: **a check that cannot fail where the defect
lives.** An import test cannot see an import that never executes, and a
build log cannot see what was written after it was believed done.

## Licence provenance

`LICENSE` is verbatim Apache-2.0, **sourced rather than transcribed**.
Three independent copies in unrelated repositories agree byte for byte
(`sha256:cfc7749b…`), which is stronger evidence of an uncorrupted text
than any single source. The appendix placeholder is left intact — the
licence ships verbatim and the copyright lives in `NOTICE`, which is
Apache's own guidance.

A licence is a legal document; a typo in one is not a cosmetic defect.

## What is deliberately not shipped

Listed **with a reason each**, in `build.py::DELIBERATELY_OUTSIDE`, so a
later reader can tell *left out deliberately* from *forgotten* — the
same courtesy the core identity surface extends to what it does not
hash. Summarised: the twin-compiler track (a separate project sharing
this repository), anything requiring an external toolchain to run,
`architecture/` (cross-repo tooling that measures only this
organisation), and `api/` (a plane contract whose tenancy and auth
concepts do not exist in this tree).

## Locks

`tests/test_release_provenance_pool.py` — 19 locks, every refusal driven
over **both** answers. `scripts/mutate_release_checks.py` — 17/17 mutants
killed by their named test.
