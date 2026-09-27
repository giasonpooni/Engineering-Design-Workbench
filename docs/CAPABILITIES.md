# Provider-free capability index

`ciw capabilities` prints a data-only index of surfaces that already exist in
this tree and do not need a private provider checkout. Printing or showing a
record does not execute that surface, bind a provider, discover a private
repository, or perform qualification.

This is not the shared profile/capability discovery registry. That row in
[the development-gap audit](DEVELOPMENT_GAPS.md) stays open. A record here
grants no execution authority. `authorizes_execution` is false and
`qualification` is `not_performed` on the index and on every record. Unknown
ids are refused with `capability_unavailable` and exit 2. The refusal is not a
zero result and it is not a successful lookup.

The index does not register a composition schema. It does not include typed
composition, frame transformations, a device gateway, or planned providers.

```text
ciw capabilities
ciw capabilities list
ciw capabilities show statistics.v1
```

| Id | What already exists | Separate invocation, not performed by the index |
| --- | --- | --- |
| `synthetic-oscillator-demo` | Deterministic synthetic oscillator recording | `ciw demo` |
| `statistics.v1` | Built-in sample statistics | `ciw analyze stats` |
| `spectrum.periodogram.v1` | Built-in periodogram | `ciw analyze spectrum` |
| `learning.oscillator-rms` | One retained RMS lesson over `statistics.v1` | `ciw math` |
| `doctor.preflight` | Read-only local identity preflight | `ciw doctor` |
| `linear-response.library` | Analytic educational preview library; no command | none |

`doctor` profile `core` can report `preflight_passed` when the local install
matches its metadata checks. That status is not qualification. The other
doctor profiles need explicit bindings this index does not supply. The
linear-response library is named only; the index does not import it.
