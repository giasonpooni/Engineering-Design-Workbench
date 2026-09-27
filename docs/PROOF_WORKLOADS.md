# F2 checker preparation and explicit proof obligations

This increment implements the finite-F2 direction in [the Julia/SP1 contract](JULIA_SP1.md).
It does not register a new proved workbench operation, change the existing heat
ELF or pins, or create another evidence/admission system.

## Delivered and still pending

| Layer | Implemented | Qualification boundary |
| --- | --- | --- |
| Python exact reference | Canonical complex validation, dense-row F2 elimination, ordinary Betti numbers, candidate comparison and binary input/output | Exact calculation and preparation, not an SP1 proof |
| SCR Rust checker | Independent boundary reconstruction and bitset-column elimination; bounded binary CLI | Native compilation and differential tests passed; registered guest qualification remains pending |
| SCR SP1 guest source | Candidate guest using the existing `ste.sp1.kernel-io.v1` convention | Unregistered; no accepted ELF, reproducible recipe or genuine F2 proof yet |
| Proof obligations | Explicit predicate label, program/input/expected-output commitments, expected guest binding and unproved context | A statement of what must be checked; no verifier invocation |
| Composition planning | Exact-byte handoff validation for a bounded declared DAG | Not recursive aggregation or authentication of child proofs |
| Privacy/build trust | Public input/output disclosure and unproved context are explicit | No privacy guarantee or host build attestation |

The Python reference and SCR implementation are deliberately independent. Julia
candidate generation remains a separate, unfinished provider connection. This
checker does not establish that Julia ran or that a complex represents a measured
physical surface.

## Run a preparation

From an installed checkout:

```sh
python -m ciw.proof_f2 examples/f2-checker/source.json > preparation.json
```

The triangle-boundary fixture has ordinary F2 Betti vector `[1, 1]`. Preparation
retains the exact source bytes and constructs the binary guest input, expected
output and SCR-compatible specification/input/output commitments. It uses the
existing `_commit` identity function. It emits `prepared_not_proved`, pending
guest registration, and no cryptographic, physical or admission authority.

The source's JSON representation is retained as evidence. Its whitespace, source
label, provenance and other surrounding metadata are not automatically proved by
the guest. The actual mathematical input and candidate are the committed binary
bytes. The program descriptor is a host binding until a reviewed guest build and
registry entry bind it to the compiled implementation.

## Exact finite predicate

Accept exactly when the candidate equals the recomputed ordinary simplicial
homology Betti vector over F2. Inputs must contain all nonempty faces explicitly,
with simplices sorted by cardinality then lexicographically and vertices strictly
increasing within each simplex. Vertex IDs are the full set `0..vertex_count-1`.
The checker rejects, rather than repairs, missing faces, duplicate simplices,
wrong ordering, malformed dimensions or unsupported conventions.

Bounds are 1..64 vertices, 1..256 listed simplices, and dimension at most three.
The empty face is implicit. Empty complexes, reduced homology, integral torsion
and arbitrary matrix complexes are outside this profile. These software bounds
are not measured SP1 proving capacity.

The reference constructs `D_k`, checks `D_k D_(k+1) = 0`, and computes
`beta_k = n_k - rank(D_k) - rank(D_(k+1))`, with `D_0 = 0` and the top outgoing map
zero. No floating-point tolerance is involved. Direct independent recomputation
needs no auxiliary rank certificate in this first checker.

### Binary format

All integer words are unsigned little-endian. Input has a conservative maximum
size of 2325 bytes and must be consumed completely:

```text
"NSF2" | version:u8=1 | field:u8=2 | ordinary:u8=0 | bounds-profile:u8=1
vertex_count:u16 | simplex_count:u16
for each simplex: vertex_count:u8 | vertex_ids:u16[]
candidate_length:u8 | candidate_betti:u16[]
```

The candidate length equals the highest simplex dimension plus one. A successful
output is `"NSF2O1"`, dimension-count u8, then three u16 vectors: simplex counts,
`rank(D_k)` starting with zero, and Betti numbers. A native refusal writes no
successful stdout result. Rust fault codes are 2 malformed, 3 bounds, 4 canonical
ordering, 5 missing face, 6 inconsistent chain, 7 candidate mismatch, 8 policy.

The candidate guest retains the existing SCR public-values layout: convention,
input commitment, completion/fault marker, and either output commitment plus
exit zero or fault exit code. Profile, field, convention and candidate all enter
the consumed input; the guest does not accept an arbitrary host policy as proved.

## Obligations and composition plans

`ciw.proof_obligations.obligation` prepares a `ciw.proof-obligation.v1` record.
It allows only empty native configuration because the existing public-values
convention does not separately prove arbitrary native configuration. Mathematical
settings must be guest input or fixed program semantics. Units, calibration,
source provenance and release policy belong in explicitly `unproved_context`
unless a qualified guest actually checks their meaning.

An expected guest SHA is a binding requirement, not evidence of registration or
proof validity. `obligation_only_not_verified` and `input_output_public` cannot be
relabelled through the validator, even by recomputing the surrounding digest.
Existing execution, result and verification occurrences remain separate.

`compose_exact(nodes, edges, roots)` checks at most 64 nodes and 128 edges. Nodes
must be in a declared topological order; each dependent whole input has one
producer; roots are exactly the external inputs. Edges currently support only
`identity-bytes.v1`: the upstream expected output bytes must equal the downstream
input bytes. Missing/duplicate edges, ambiguous producers, cycles, misordering
and undeclared conversions refuse.

The result is `plan_only_not_verified`, with cryptographic verification, recursive
aggregation and state admission all `not_performed`. It does not accept proof
bytes or verifier verdicts. A genuine aggregation guest must later verify approved
child keys and public statements as well as these dependency relations. A valid
graph or collection of hashes cannot stand in for that work.

## Tests actually performed

```sh
python -m pytest -q tests/test_proof_f2.py tests/test_proof_obligations.py
# To run, rather than skip, the independent native differential case:
CIW_F2_CHECKER=/trusted/path/f2-check python -m pytest -q tests/test_proof_f2.py tests/test_proof_obligations.py
```

With the CI-built Rust executable bound: **70 Python tests passed, no skips**.
SCR native CI separately passed **seven Rust tests**, then built a static Linux
binary. The differential case compares exact output bytes for 186 valid inputs
and requires refusal of 186 corresponding wrong candidate vectors, plus malformed
and truncated encodings. It includes 126 exhaustive complete-vertex complexes on
one to four vertices, 48 seeded random complexes, and 12 named/boundary fixtures.
Euler characteristic and graph connectivity provide additional reference checks.
The 255/256-simplex fixtures exercise higher bitset words and exact count bounds.
The six-vertex projective-plane fixture gives `[1, 1, 1]` over F2 and detects
accidental rational-coefficient substitution.

SCR checker commit: `14f4548eff0e0266975502acae589fbad810bfd5`; native CI run
`36344264616`, artifact `10939218788`. The downloaded artifact checksum and every
recorded core-source/binary checksum were verified before the local differential
run. Local Python is 3.13.5 with NumPy 2.3.5, not the pinned terminal CI matrix;
Rust CI used 1.94.0. No genuine F2/SP1 proof or cryptographic rejection was run.

## Remaining acceptance gates

1. Close the existing heat proof gate on a suitable runner without changing pins,
   lowering resource guards, using mocks or counting unavailable tests as passes.
2. Build the candidate F2 guest reproducibly with the reviewed compiler/backend;
   retain an actual lockfile, recipe and ELF identity. Review before registration.
3. Run genuine positive and negative F2 proofs, including changed complex,
   candidate, field/convention, guest and corrupted/truncated proof; verify the
   untouched original afterward. Measure cycles, memory, proof size and timing.
4. Bind the qualified checker to existing SCR/CIW operation/result/verification
   records; keep the optional Julia producer independently identified.
5. Only then implement and qualify recursive verification of child proofs and
   handoffs. Separately evaluate privacy wrappers and reproducible host builds.

The retained input/output profile is deliberately not private. Upstream SP1
[security documentation](https://docs.succinct.xyz/docs/sp1/security/security-model)
distinguishes individual STARK proofs from its zero-knowledge wrappers. Its
[aggregation documentation](https://docs.succinct.xyz/docs/sp1/writing-programs/proof-aggregation)
describes recursive verification; neither capability is qualified merely by
preparing these records. No new hardware or admission permission is introduced.
