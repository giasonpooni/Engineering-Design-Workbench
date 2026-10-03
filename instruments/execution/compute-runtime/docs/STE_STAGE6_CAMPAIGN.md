# Scientific Computation Runtime Stage 6 -- Campaign Scale, and the Third Backend

This is a retained implementation-stage record. `STE` in the record and its
identifiers refers to this runtime; stage measurements and runtime pins retain
their original scope. See [compatibility and historical records](README.md#compatibility-and-historical-records).
Two objectives, both built and run: a REAL multi-workload scientific
campaign through one EvidencePool and one OperationTrace; and RISC Zero
as the third independent `ProofBackend` implementer.

## The campaign (actual run, actual numbers)

Heat-diffusion parameter sweep (3 initial profiles x 3 grid sizes,
200 steps) + spec-A repeated 3x + one altered input + a proved subset
under SP1 and Nexus + 3 GROMACS trajectory points + a 5-point failure
campaign -- all through the UNCHANGED seam, driven by the thin
`execution/campaign.py` (`CampaignPoint` is a parameter bundle,
`CampaignReport` a bag of counters; neither is an identity or a store).

```text
specifications          : 16
executions (points)     : 26   (final run, incl. the RISC Zero point)
successes               : 21
failures                : 5   (unsupported / execution / verification /
                               downstream-rejection / malformed -- each
                               named by its real exception)
observations admitted   : 21
unique evidence ids     : 14      N=25 >= M=20 >= K=14
trace occurrences       : 26  (79 transitions)
occurrence states       : SUCCEEDED=21  FAILED=4  REJECTED=1
evidence fingerprint    : +42 semantic steps (identical re-admissions
                          move it not at all -- put_observation is a
                          content-keyed write; measured, not assumed)
proof artifacts         : 5, 3.23 MB total -- and for ONE spec, three
                          warrants side by side:
                          proof-ff3a5805...-sp1-heat.bin   (2778 kB)
                          proof-ff3a5805...-risc0-heat.bin  (225 kB)
                          proof-ff3a5805...-nexus-heat.bin   (75 kB)
campaign wall time      : 341 s
slowest points          : sp1 237-299s; risc0 64.5s; nexus 12-18s;
                          gromacs ~0.4s; native ~0.02s
```

**The scaling bottleneck is unambiguous: SP1 CPU core proving.** One
SP1 proof (299 s) cost more than the other 24 points combined (44 s).
Nexus proving is 20x cheaper on this workload; native execution and
evidence admission are noise (~ms); GROMACS externals are sub-second.
Orchestration, serialization, admission and storage are nowhere near
the bottleneck at this scale.

Campaign locks (tests): the central experiment (A,A,A,B -> 4
occurrences, 2 specs, 2 unique evidence ids in ONE pool); backend
substitution inside one shared pool (unproved + Nexus-proved -> one
observation id, proof artifact only in the proved world); the failure
campaign (interleaved with a success; only the success admits; states
separate FAILED from REJECTED; the verification failure is named
`EngineIdentityMismatch`).

One genuine defect found by running (and fixed): `proved_runner` named
proof files by specification only, so SP1's and Nexus's proofs of one
spec collided on a filename. Artifact names now carry the guest ELF
stem.

## RISC Zero, from source (fork `risc0-zero` @ 3bbcd44, risc0-zkvm 5.0.0)

- Guest: `riscv32im-risc0-zkvm-elf`, toolchain `r0.1.97.0` (risc0's
  rust fork; fetched by direct release download, linked as `risc0`).
- Build flags (from `risc0/build/src/lib.rs`): lower-atomic,
  `-Ttext=0x00200800`, `--fatal-warnings`, panic=abort, getrandom
  custom.
- IO: `env::read` (word-serde) in, `env::commit_slice` -> journal out.
  `read_frame` exists but is `#[stability::unstable]` -- the guest uses
  the stable surface.
- Verifier: EXTRACT-style like SP1 -- `Receipt::verify(image_id)` binds
  seal + journal digest + image id; the journal carries the statement
  (`ste.r0.kernel-io.v1` layout), so tamper rejections are attributable
  per dimension (vs Nexus's confirm-style `StatementMismatch`).
- Native program commitment: the ImageID, a pure function of the ELF --
  recorded beside our descriptor identity, never as it.
- Dev mode: `RISC0_DEV_MODE` produces FakeReceipts; the adapter REFUSES
  to construct if that variable is set at all.
- Environment finding: the fork's large circuit blobs (recursion zkr
  archives) are Git-LFS objects; the anonymous clone had pointer stubs
  and the proving build fails on them. Resolved by attaching the fork
  to the session and `git lfs pull` of exactly the needed objects.

**Reproducible builds: RISC Zero fit the stage-5 machinery with ZERO
structural extension** -- one `_BACKENDS` entry (flags/target/toolchain/
fork), one registered guest. Independent rebuild converges on the
registered identity (`risc0-heat` elf `692c15bd...`), and every prior
artifact identity was unchanged by the regeneration.

## RISC Zero: proven, measured

First receipt over the reproducible artifact (`risc0-heat.elf`,
`692c15bd...`, wrapped deterministically with the fork's v1compat
kernel; ImageID `65efe6a9...` reported beside our identity):
**63 s wall on 4 CPU cores, 225 kB receipt**, `risc0-cpu 5.0.0`. The
guest's in-circuit input and output commitments matched Python's
recomputation byte-for-byte on the first run -- the third substrate
compiling the same two `no_std` crates to the same function. Fresh-
process verification: `outcome verified`, full coverage.

Proving-cost ladder on the 50-step heat statement, measured:
Nexus stwo ~13-18 s / ~75 kB; RISC Zero ~63 s / 225 kB; SP1 core
~299 s / ~2.6 MB.

One orchestration defect caught by an existing lock while landing the
campaign driver: the first draft lived in `execution/` while importing
evidence machinery, and `test_execution_package_touches_no_evidence_
machinery` failed. The driver moved to the new `campaign/` orchestration
package (the same altitude as `scout.pipeline`); the execution
boundary stayed intact rather than being weakened.

## Boundaries re-affirmed at campaign scale

No evidence contamination (the campaign pool's observations carry no
occurrence, proof, or backend data); operation multiplicity fully
retained; no silent fallback from proof to unproved execution (a failed
verification is a FAILED dispatch, never a quieter success); GROMACS
remains explicitly outside computational verification -- its campaign
points are labeled external-unverified and nothing upgrades them.

## Morpho note (sharpened by the campaign, not implemented)

What a lowering compiler must emit, now concrete: (a) canonical input
bytes for a REGISTERED kernel descriptor, or (b) a full BuildRecipe for
a new kernel. The campaign exposed no missing field in either; the
sweep's "parameter -> input encoding" functions are exactly the shape a
lowering would generate.
