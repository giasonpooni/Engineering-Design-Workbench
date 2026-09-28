# C++ and Godot consumers of the Julia-authored oscillator kernel

This extends [the qualified native export](OSCILLATOR_KERNEL_EXPORT.md). It adds
consumers, not another compiler backend or a second implementation of the model.
The original exporter, C library ABI, Python/Rust bindings, equations, Tsit5
provider, numerical tolerances and NET operation/session semantics are unchanged.

## Workflow

```text
Julia source -> existing export and complete native qualification
                         |
                  exact library bytes
                         |
             +-----------+-------------------+
             |                               |
     checked C++17 wrapper           Godot GDExtension
                                             |
                                    PackedFloat64Array RHS
                                             |
                                    Godot-owned RK4 test host
                                             |
                            recorded trajectory -> NET run.v1
```

The C++ wrapper calls `ciw_oscillator_rhs_v1`. The RefCounted Godot class
`CIWOscillatorKernel` exposes `bind_source(expected_sha256)` and
`rhs(state, parameters)`. State is `[q, v]`, parameters are `[gamma, omega]`,
and successful derivatives are `[dq, dv]`. Scalar state and buffers remain
binary64 even when the selected Godot build uses single-precision Vector types.

The Godot return dictionary contains `status` and `derivative`. Failure returns
an empty derivative, never a plausible zero result. Status 7 is wrapper-unbound
or source/ABI mismatch; C status codes 1-6 remain unchanged. A failed rebind
removes the prior binding. The host must trust and hash the binary before launch;
an embedded source string does not authenticate a native library.

The helper has no integrator, physics body, SceneTree control, NET session,
network service, dynamic executable discovery or hidden mutable numerical state.
The supplied headless GDScript host explicitly owns RK4 stepping. Do not also
advance the same state with a Godot rigid body. NET only receives the resulting
observations. The existing scientific Godot inspector is untouched.

## Qualification command

First run the unchanged complete parent gate. Its report must be `passed`,
including real Julia export, Python/Rust execution and retained Tsit5 comparison.
The new command checks the report digest, parent artifact bytes and selected
model-source identities before compiling anything:

```sh
python scripts/check_oscillator_consumers.py \
  --qualified-dir /absolute/path/to/complete-parent-gate \
  --cxx /absolute/path/to/g++ \
  --cmake /absolute/path/to/cmake \
  --readelf /absolute/path/to/readelf \
  --godot /absolute/path/to/Godot_v4.5.2-stable_linux.x86_64 \
  --godot-cpp /absolute/path/to/pinned-godot-cpp \
  --output-dir results/oscillator-consumers-001
```

Use a fresh output directory. `godot-cpp` must be a clean checkout of
`e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77` (Godot 4.5 API). The tested target
is Godot 4.5.2 Standard on Linux x86-64. CMake builds only the RefCounted class
profile and required core bindings. No godot-cpp source is vendored or made a
core Python dependency. Its license is retained alongside the built extension.

The committed `oscillator-consumers-native.yml` workflow provisions exact
Julia/Rust and Godot versions, uses an installed candidate wheel, enables the
real Julia provider test, rejects skips, reruns the complete original native
gate, and only then runs the consumers gate. It requires no private-provider
credential and changes no existing workflow or access policy.

## Checks and evidence

The C++ probe and actual Godot extension evaluate the same 1,024 input rows as
the Julia reference. Sampled agreement uses the existing `2e-12` absolute and
`2e-13` relative derivative policy. Godot-owned RK4 trajectories are checked
against four existing analytical fixtures (`2e-8` absolute/relative) and the
retained original Tsit5 trajectory (`5e-8` absolute/relative). No tolerance is
weakened to accommodate a consumer.

Qualification also checks wrapper refusals, exact sampled repeat agreement on
the same build, failed-rebind invalidation, wrong-source startup and missing
native library. The built project is relocated before launch; the extension
must use an origin-relative dependency, with loader environment overrides
removed. The copied kernel binary must match the parent artifact digest.

Actual Godot observations are projected to `run.v1`, passed through the existing
native-RHS OperationRegistry/runner, and validated offline with native loading
forbidden. Those derivative results remain `not_verified`: this test report is
not a CIW verification occurrence, SP1 proof, evidence admission or physical
validation. Repeating a probe is a new process, not continuation of saved state.

Source snapshots, compiler/tool identities, command logs, numerical output,
parent-report linkage, native/extension digests, NET records and an independent
consumer-gate occurrence ID are retained in the output. Hashes check integrity
and compatibility, not authenticity of arbitrary supplied reports.

## Qualified Linux execution

The dedicated workflow passed for code commit
`375ec716759b4e1f2c87499595d3b8a3b0c5c565` in
[run 36391016858](https://github.com/giasonpooni/Notations-Engineering-Terminal/actions/runs/36391016858),
job `108826618324`, on 2026-09-28. The measured profile used Godot
`4.5.2.stable.official.6ce3de25a`, G++/GCC 13.3.0, CMake 3.31.6, Julia
1.10.12, Rust 1.90.0 and Python 3.12 on Ubuntu 24.04 x86-64.

| Check | Measured result |
| --- | --- |
| Installed-wheel focused suite | 76 passed, 0 failures/errors/skips, including genuine Julia execution. The 18 new local tests and old 58 tests are subsets of this total. |
| Original Julia/C/Python/Rust/Tsit5 gate | All six original gates passed again, without a fixture fallback or changed tolerance. |
| C++ against direct Julia | 1,024 rows; maximum absolute derivative differences `[0.0, 0.0]`. The C++ wrapper self-test passed all 11 checks. |
| Actual Godot GDExtension against Julia | 1,024 rows; maximum differences `1.1368683772161603e-13 m/s` and `1.1641532182693481e-10 m/s^2`, within the unchanged componentwise absolute-plus-relative policy. |
| Godot repeat | A new Godot process reproduced all 1,024 sampled derivatives exactly in this environment. |
| Godot-owned RK4 against analytical references | Default, mixed, undamped and high-frequency cases all passed. |
| Godot-owned RK4 against retained Tsit5 | 129 samples passed; max q/v/energy differences `1.9215962154817134e-11 m`, `9.940448464362817e-11 m/s`, `3.596349884560368e-10 J`. |
| Refusals and relocation | Wrong source, invalid input, failed rebind and missing library were rejected; the relocated project loaded its origin-relative native dependency. |
| NET retention | Actual Godot observations entered existing run/execution/result records; offline validation passed with native loading forbidden. Results remained `not_verified`. |

The parent and Godot consumers used identical native library bytes:
`sha256:7ba2306c2c1ebcf9eb586d27a1e0a8d875b3e9633f59faa54d996ee4e9b50f7e`.
The consumer report digest is
`sha256:cf1c2fb6c2d33a45125cac09f1bc37949a223eb8db63b2adbb27dc0b910de9d9`.
Sampled agreement does not establish universal or cross-platform determinism.

### Failures found during qualification

The first run (`36389489829`) passed C++/Julia comparisons but failed compiling
the trimmed godot-cpp profile: its core logging code requires the generated
`OS` binding. Commit `fed1f149db7685e7fb41aeab28b16b2f07a878eb` added that
binding; the numerical kernel was unchanged.

The second run (`36390133623`) compiled the extension but crashed during
cold-cache headless editor import. Its shutdown trace is consistent with the
[documented GDExtension documentation-generation race](https://github.com/godotengine/godot/issues/111048).
The acceptance recipe now checks an empty-editor control and applies the
upstream-described workaround: `--frame-delay 1000` during extension import only.
Both startup checks passed in the measured run. The subsequent numerical Godot
processes receive no added frame delay. This is a scoped startup workaround,
not a fix to Godot itself or qualification of zero-delay cold-cache import.
No numerical tolerance or existing parent gate was relaxed. Unexpected command
failures retain their full logs and a bounded diagnostic tail in the report.

### Retained evidence

[Artifact 10955808387](https://github.com/giasonpooni/Notations-Engineering-Terminal/actions/runs/36391016858/artifacts/10955808387)
contains 132 files, 4,691,355 ZIP bytes: the candidate wheel, original/replayed
Tsit5 sessions, parent and consumer reports, generated C, native and extension
libraries, C++/Rust probes, Godot inputs/outputs, NET records and command logs.
ZIP SHA-256:
`8cb89d92c1f844ddb549c87b8a7a222ba8b9e4630544350e6f418f10fae161d8`.
GitHub reports expiry on 2026-10-28 under the configured 30-day retention policy.

A local read-only audit verified the downloaded ZIP digest, all 124 file hashes
listed in the two reports, report digests, parent linkage, six existing record
seals and the 76-test JUnit totals. Recomputing differences from retained output
bytes reproduced the reported C++/Godot and trajectory maxima. These are
post-run integrity/comparison checks, not additional Godot executions.

## Remaining limits

This is a headless numerical/GDExtension increment, not a completed game,
interactive UI, graphics/GPU qualification, live NET control path, performance
budget, distributable export template or a Bevy plugin. Windows/macOS, other
Godot builds and other compilers require separate qualification. The existing
Blender/Godot/Bevy projectile and persistent-simulation work remain independent.

The integration follows the official Godot GDExtension C++ example and the
pinned godot-cpp CMake/test implementation. Upstream references:

- https://docs.godotengine.org/en/4.5/tutorials/scripting/cpp/gdextension_cpp_example.html
- https://github.com/godotengine/godot-cpp/tree/e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77/test
