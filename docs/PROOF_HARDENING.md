# Proof hardening and next proof workloads

This is an extension of the existing [registered heat proof](PROVED_HEAT.md)
and [Julia/SP1 contract](JULIA_SP1.md), not a second execution or evidence system.

## Implemented in this increment

The proof adapter now captures its subject before binding or invoking a verifier.
A caller changing its bundle during verification cannot retarget the resulting
report. Replay likewise captures the requested original occurrence. Provider
responses and runtime metadata are detached before retention; mutating a cached
response or memory measurement after return cannot rewrite an identified bundle
or verification report. Changes to the submitted source, retained statement or
runtime binding during the verifier call refuse rather than publish success.

These are host-side statement/lifecycle fixes, not changes to SP1 cryptography.
The registered guest, source pins, arithmetic, proof format, result schemas and
historical trust labels are unchanged. A Python snapshot is not isolation from a
malicious process with arbitrary access to host memory or credentials.

The real installed-wheel gate additionally requires:

- `test_native_proof_rejects_rebound_input`: keep the original proof bytes, change
  the input statement, consistently recompute the surrounding record commitments,
  reach the actual verifier and require rejection.
- `test_native_proof_rejects_rebound_output`: perform the corresponding attack on
  the claimed output, then require that the original still verifies.

The fixtures deliberately pass offline structural validation. Otherwise a test
could appear to check SP1 while only detecting an obsolete JSON digest. The gate
still requires the existing genuine proof, fresh replay, corrupted-proof rejection
and verification-only checks. Missing or skipped negative tests fail gate
accounting. No synthetic fixture may substitute for the native acceptance gate.

## Audit evidence and limitations

Baseline: main `4cafa0e1c4193acbc6c8ad62c007c19aba796bc4`. The original proof
module matched Git blob `8b954256f8c84d64a11ea9302b77f35cf6bd6a43`.
Source was taken from the checksum-verified CI wheel for merged #29, artifact
`10938570758`, run `36339548254`; repository tests were separately read and their
original blob identities checked.

The 19 new proof-isolation/statement-fixture cases produced **11 failures and
eight passes** against the unchanged proof adapter. The patched adapter passed
all 19 and all 101 unchanged proof-unit cases: **120 passed, no skips**.
Eight additional tests exercise the gate's required-test and skip accounting.

The complete focused proof suite, with this patch alone over the unmodified
main session implementation, passed **135 tests and skipped five native-SP1
tests**. With the separately reconciled runtime audit it passed **271 tests and
skipped the same five**. These are not additive totals of distinct tests.

Local environment: Linux, Python 3.13.5, NumPy 2.3.5, pytest 9.0.2, websockets
16.0. It differs from the project's pinned Python/NumPy CI matrix. No native
SCR engine, SP1 host or registered ELF was available for local proving. The five
skips are therefore unperformed cryptographic gates, not successful checks.
No full upstream cryptographic audit, physical validation or performance claim
is made. The new negative gate must run on the genuine pinned backend before
it is reported as qualified.

## Development sequence: stronger claims, not broader labels

### 1. Close the existing real-proof qualification

Provision scoped, reviewed access to the exact private providers without making
untrusted PR code secret-bearing. Run the existing build recipe and installed
proof gate, including all five required native tests. Retain the source/ELF
bindings, original and replay proof bytes, verification-only report, rejection
results, timings and explicitly scoped memory observations. Do not weaken pins,
count skips as passes or replace the backend with a mock to close this gate.

A later release should independently reproduce verifier builds and review
upstream security advisories before updating approved pins. The current host
binary bindings remain operator assertions, not cryptographic build attestations.
A proof verifies a program statement, not an arbitrary host's text saying it did.

### 2. Add one small certificate-checking guest

Extend the registered SCR guest/provider boundary rather than try to execute an
entire Julia or C++ solver inside a zkVM. A solver may produce an untrusted
candidate and a witness; a small deterministic checker evaluates a precisely
specified predicate. SP1 then attests execution of that checker on committed
inputs. Checker correctness must be established separately by specification,
independent references and adversarial tests.

A suitable next workload is the already-planned finite F2 topology calculation:
validate the complex/matrix representation, dimensions and binary coefficients;
check the boundary-composition identity; compute or certify ranks; and report
only the finite algebraic claim actually checked. Triangle boundary versus filled
triangle, vertex relabelling, disconnected components and malformed complexes
provide initial fixtures. Invalid inputs must not become a zero-rank success.
Bounds and arithmetic belong in the guest specification and its tests.

An alternative later workload is exact rational constraint feasibility. Do not
label feasibility as optimality; optimality requires the additional justified
certificate and assumptions. Likewise, a numerical residual threshold is not
an error enclosure unless the required mathematical error argument is supplied.

### 3. Make proof obligations explicit at operation boundaries

For each future profile, specify the predicate, applicable domain, arithmetic,
encoding, approved guest/verifier identity and public input/output commitments.
Distinguish what is enforced inside the proved program from host metadata about
units, source provenance, calibration, tolerance policy or release permission.
Hashing metadata beside a proof does not make the guest enforce that metadata.

Extend existing operation/result/verification records compatibly. Preserve
separate evidence, execution and verification occurrences. Cryptographic validity,
scientific applicability, physical validation and ESM admission remain separate.

### 4. Compose proofs only after individual obligations are qualified

A future aggregation guest must verify the approved child keys and their public
statements, then check the actual dependency relations: selected output bytes
become the next input under an explicit map. Reject missing, substituted,
misordered or duplicated dependencies where the declared graph forbids them.
A manifest containing proof hashes is not a proof of composition.

SP1 supports verification of compressed proofs inside a guest using the child
verifying key and public-values digest. Its documentation also notes aggregation
overhead; benchmark it against independent verification rather than assuming a
speedup. This is upstream capability, not implemented Notations aggregation.
See [SP1 proof aggregation](https://docs.succinct.xyz/docs/sp1/writing-programs/proof-aggregation).

### 5. Treat privacy and deployment trust as separate qualification

The retained heat bundle contains its source and outputs. It is not a private
computation interface. Upstream distinguishes non-zero-knowledge individual STARK
proofs from its zero-knowledge Groth16/PLONK wrappers, which bring additional
assumptions. A future privacy profile must declare exactly what is disclosed and
qualify its chosen proof type and deployment; a `zkVM` label is insufficient.
See [SP1 security model](https://docs.succinct.xyz/docs/sp1/security/security-model).

Keep proof generation outside deadline-critical device control unless that
specific deployment is qualified. Neither an execution proof nor a cache hit
authorizes equipment operation or establishes a new physical observation.

## Acceptance rule for every extension

A proof capability is delivered only when its exact claim, approved implementation,
positive and negative tests, genuine verification evidence and limitations are
retained together. Reuse the existing source, operation, execution, result and
verification identities; do not fork the investigation or admission substrate.
