# Real IFC execution and transition experiment

This branch extends the executable ingress, preservation and industrial
transition branches. It connects an actual retained IFC occurrence to the
existing native CSE workload. NET retains the investigation; CSE owns IFC
lowering, its Gaussian world and ledger. Neither owns permission to admit an
industrial canonical state through this experiment.

The immediate experiment has two distinct outcomes. An original public IFC
artifact exercises the compatibility boundary. A bounded synthetic room
exercises the accepted scalar-conditioning path. Success on the synthetic room
does not establish compatibility of the public model.

## Actual public artifact

The source is buildingSMART's `wall-with-opening-and-window.ifc`, pinned to
Sample-Test-Files commit `e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7`:

- Original size: 12,492 bytes.
- SHA-256: `73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832`.
- Schema: IFC4; active length scale: 0.001 metres per source millimetre.
- License: CC BY 4.0; retain its source attribution with the fixture.

The native non-mutating audit inventories this original file. CSE's unchanged
scalar loader refuses it because the building storey lacks required
`ClearHeight`; missing quantities are not filled from assumptions. The audit
reports blocked lowering, with compilation and world verification unperformed.
The scalar refusal retains no invented prior, posterior or accepted ledger.
The complete original file remains evidence; the experiment does not silently
strip unsupported products or turn a subset into whole-model acceptance.
The negative chain can still bind the known logical object occurrence and an
explicitly unavailable quantity projection (`value=null`, `uncertainty=null`).
These NET projections are not native CSE worlds. Refuted mapping and preservation
preconditions force a `REFUSED` transition envelope; the missing quantity never
becomes a numeric state or an eligible admission.

## Accepted bounded fixture

The existing synthetic metre-unit room is a positive control, with an explicit
raw quantity target and a synthetic scalar observation. The independent
measurement-noise declaration is an applicability assumption, not evidence of
a surveyed frame or sensor calibration.

For the selected raw scalar, the verifier checks the Gaussian update separately
from CSE's execution. With prior mean $\mu$, prior variance $P$, observation $z$
and declared independent noise variance $R$:

$$K=\frac{P}{P+R},\qquad
\mu'=\mu+K(z-\mu),\qquad P'=\frac{PR}{P+R}.$$

The source occurrence, target GlobalId, quantity class, quantity name and active
project units must resolve without ambiguity. The bounded imported RAW means
and prior covariance are checked against source quantities and CSE's declared
prior policy; the posterior RAW block is checked against the conditioning law.
A local quantity-unit override, duplicate binding or incompatible quantity type
cannot be accepted merely because its label looks like a length. The complete
source-derived RAW slot inventory must match the returned RAW slots, including
their roles. Comparisons use relative tolerance `2e-10` with 32 float64 ULPs and
no absolute variance floor; a tiny variance cannot pass by being replaced with
a much larger value below a fixed tolerance. Checks cover RAW quantities in
this bounded profile; derived geometry, general IFC conformance and physical
truth require separate evidence.

## Identity and authority

Exact byte retention, operation, execution, mapped result and verifier identities
remain separate. The existing ingress and preservation contracts refer to the
retained execution evidence. The mapped BIM quantity is a candidate identity
bound to this IFC occurrence and GlobalId; this is not proof that two physical
assets in different systems are identical.

Any eligible transition stops at authority review. Canonical-state admission,
physical validity, construction acceptance and physical actuation remain
unperformed. A verified reproduction of a refused execution means the refusal
was reproduced, not that scalar conditioning succeeded. Record digests detect
content changes; they are not cryptographic attestations of who executed a
provider. Imported evidence retains that limitation.

The native provider is CSE commit
`4b74abda40bba3277de69bf61e9e09283ae2d5b3`. The existing adapter checks its source
tree and host-bound Python runtime. Dependency versions are retained; their
installed binaries are not independently authenticated by this experiment.

## Reproduce the two outcomes

Provision a clean CSE checkout at the exact revision above. From this NET checkout,
use a fresh declaration/output directory:

```sh
python -m pip install -e .
python examples/ifc-transition/make_sources.py results/ifc-declarations
python -m ciw.net interop execute-ifc examples/bim-quantity/room.ifc results/ifc-declarations/room-observation.json results/ifc-declarations/room-spec.json --cse /path/to/cse --output results/room-run.json
python -m ciw.net interop verify-ifc results/room-run.json --cse /path/to/cse
python -m ciw.net interop execute-ifc examples/ifc-transition/buildingSMART-wall-opening-window.ifc results/ifc-declarations/public-wall-observation.json results/ifc-declarations/public-wall-spec.json --cse /path/to/cse --output results/public-wall-run.json
python -m ciw.net interop verify-ifc results/public-wall-run.json --cse /path/to/cse
```

Both generated observations are synthetic. The public-model observation is an
explicit negative-path stimulus, not a measurement of the buildingSMART model.
`verify-ifc` without `--cse` checks retained bytes and reconstructs the records
without executing CSE; `--cse` additionally checks the currently provisioned
runtime against the retained binding. Output files are create-only. A successful
verification command checks a bundle's consistency and its bounded numerical
claims; read its native outcome and qualification to distinguish an accepted,
held or refused mapping.

`python scripts/check_real_ifc_transition.py --cse /path/to/cse --output-dir results/ifc-experiment`
retains both actual execution bundles, their verification summaries and one-run
phase timings. These timings are diagnostics, not a throughput/scaling benchmark.
The cross-platform workflow retains this evidence beside the tested source and
installable wheel.

The final installed-wheel development qualification and both retained execution
bundles are also committed under `validation/real-ifc-transition-v1`. Its report
records the uncommitted development source honestly; the retained module closure
identifies the executed implementation. The hosted workflow repeats the native
executions against its checked-out commit.

## Development order

P0/P1 are developed together because a real preservation claim requires an
executed mapping and a check against its retained result. Public-model acceptance
remains blocked by missing quantities. Extend CSE's declared derivation scope
and validate it against retained geometry before attempting that acceptance.

P2 will project these bound contracts and outcomes into the existing Board.
P3 will repeat this path with a second domain without changing the kernel's
identity or admission semantics. P4 will measure startup, mapping, transfer and
verification costs separately before choosing scaling changes. The priority
table is an implementation order, not a claim that these later gates passed.
