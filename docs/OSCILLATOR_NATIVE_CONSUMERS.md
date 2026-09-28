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

## Status and limits

Initial local development: 18 Python/C++ boundary tests passed. Their compiled C
fixture is explicitly hand-lowered and does not count as Julia or Godot execution.
Real native consumer qualification must be established by the dedicated workflow;
results are recorded against the measured code commit, not inferred from source.

This is a headless numerical/GDExtension increment, not a completed game,
interactive UI, graphics/GPU qualification, live NET control path, performance
budget, distributable export template or a Bevy plugin. Windows/macOS, other
Godot builds and other compilers require separate qualification. The existing
Blender/Godot/Bevy projectile and persistent-simulation work remain independent.

The integration follows the official Godot GDExtension C++ example and the
pinned godot-cpp CMake/test implementation. Upstream references:

- https://docs.godotengine.org/en/4.5/tutorials/scripting/cpp/gdextension_cpp_example.html
- https://github.com/godotengine/godot-cpp/tree/e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77/test
