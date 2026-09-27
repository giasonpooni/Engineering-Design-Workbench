# Learn and use the same instrument

PDT's optional learning surface teaches through the existing operation API.
The initial closed exercise is **oscillator-rms**: inspect synthetic
displacement, interpret its RMS amplitude, retain a computation, reopen it,
cross-check it independently and rerun it as a new occurrence.

This extends [model exploration](MODEL_EXPLORATION.md). It introduces no new
scientific operation, provider, proof engine or workspace format.

## Terminal walkthrough

After installing the workbench, no LLM, external provider, Julia runtime,
network connection or device is required for this lesson:

```text
ciw math
ciw math history oscillator-rms
ciw math learn oscillator-rms --level concrete
ciw math learn oscillator-rms --level formal
ciw math explore oscillator-rms --view derive
ciw math explore oscillator-rms --view bridge
ciw math work oscillator-rms --output-dir results/lesson-1
```

The last command prints the actual retained result ID. Substitute it for
RESULT_ID below; this placeholder is not an identifier to send literally.

```text
ciw math inspect results/lesson-1/workspace.json --result-id RESULT_ID
ciw math verify results/lesson-1/workspace.json --result-id RESULT_ID
ciw math replay results/lesson-1/workspace.json --result-id RESULT_ID --output-dir results/lesson-2
```

Choose a new output directory for each computation. Existing directories are
refused. The ordinary workspace can also be opened through the existing
terminal and Godot session interface. There is no separate lesson file format.

Read commands support `--json`; abstraction levels are concrete, structural,
formal and computational. These change the explanation, not the operation,
parameters, tolerances or authority.

## One grammar, with explicit scope

| Stage | This lesson |
| --- | --- |
| State | Finite displacement samples in metres, with retained time/frame declarations |
| Structure | A uniformly sampled vector and a half-open selection interval |
| Change | Square, average and take the nonnegative square root |
| Compute | Existing `statistics.v1` through `operation.execute` |
| Check | Separate Decimal RMS comparison; unchanged scientific verification status |

The problem-led prologue asks why a signed average can hide variation.
Alternating electrical signals offer one application context
([OpenStax, AC sources](https://openstax.org/books/university-physics-volume-2/pages/15-1-ac-sources)).
The lesson text and exercises are original; no textbook text or figures are
bundled. A sourced historical chronology remains curriculum work.

For N equally weighted samples, RMS = ||q||_2 / sqrt(N). Sign reversal and
permutation preserve this scalar; they do not preserve all signal meaning.
Time ordering, sign and phase cannot be reconstructed from RMS. This is an
invariance of the summary map, not a conservation law for oscillator dynamics.

The quantity is displacement amplitude, not energy or measurement uncertainty.
A different sampling measure needs an explicit weighting rule. A finite
numerical check is distinct from a derivation, formal proof and physical
validation.

## Retention and authority

- `work` uses the shared runner's operation/execution/result envelopes and
  saves a normal version-2 workspace, including refusals without a result.
- `inspect` delegates validation to the existing workspace reopen path.
  Restored copies go to temporary storage; it does not execute an operation,
  generate new source data or overwrite retained files.
- `verify` computes only a numerical RMS diagnostic. It uses 80-digit
  Decimal arithmetic with exact conversion of each retained binary64 sample.
  The criterion is absolute error <= 1e-12 * max(1 m, abs(reference RMS)).
  That is a declared comparison tolerance, not a rigorous rounding bound.
  This diagnostic is printed; it is not a registered verification record.
- `replay` uses the retained source, parameters and effective selection through
  the same operation. If parameters omit channel or interval, the separately
  retained selection supplies them; fresh session defaults cannot replace them.
  Replay creates new execution/result IDs. It compares the full statistics payload and
  the runtime declarations by exact equality. A match of the built-in runtime's
  provider/version declaration is not proof of an identical dependency closure.
  The original workspace remains unchanged.
- Both comparison commands return exit code 3 on mismatch; a provider refusal
  returns 2. Successful calculations retain `verification_status=not_verified`.
  Nothing admits a scientific state or authorizes equipment.

An intentionally resealed but incorrect RMS can be structurally inspectable
and still fail the numerical check. Tests exercise this distinction.

## Six books: the follow-up curriculum

| Book | Purpose | Current status |
| --- | --- | --- |
| I — Why | Source the problems and historical development of capabilities | Problem-led RMS prologue; broader history pending |
| II — Grammar | State, structure, change, computation and scoped truth claims | Applied to one lesson |
| III — Build | Reconstruct concepts from explicit assumptions | Finite RMS derivation |
| IV — Compute | Separate meaning, representation, algorithm, execution and checks | Retained operation, independent diagnostic and replay |
| V — Atlas | Navigate relations among supported concepts | Sample vector -> quadratic form -> norm |
| VI — Frontier | Identify when a representation or method is insufficient | Sampling and information-loss questions; broader research paths pending |

This is an organizing pedagogy, not a claim that all mathematics has been
formally reduced to one complete language. A shared display vocabulary must
preserve each field's premises and its supported algorithms.

The supplied language examples (`state`, general `derive`, `prove`,
arbitrary `solve`) remain proposed syntax. This increment does not evaluate
free-form mathematical strings, invent proof results, generate courses or
infer learner competence. The `explore --view derive` command presents the
reviewed finite derivation above.

Next, connect a second lesson to an already qualified model operation, with
tests for its assumptions and a counterexample. Add explicit, user-editable
prerequisite/progress records before any adaptive curriculum. Broader atlas
and proof work should follow demonstrated lesson needs, under the
[development policy](DEVELOPMENT.md).

## Validation

```text
python -m pytest -q tests/test_learning.py tests/test_model_education.py tests/test_operation_runner.py
```

The installed-wheel acceptance script also runs the lesson, inspection,
numerical comparison and replay outside the checkout. Provider pins, session
admission, core envelopes and numerical kernels are unchanged.
