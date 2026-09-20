# sensitivity-gate

The `sensitivity-gate/` directory contains an incomplete Rust crate scaffold.
It includes numerical constants and typed error definitions, but the modules
`chart`, `covariance`, `matrix`, and `structure` declared by `src/lib.rs` are
absent from the committed source. The crate therefore does not currently build.

There are no Python bindings, C ABI, Julia bindings, or CUDA backend in this
repository. The supported implementation is the Python `sensitivity` package;
see [the kernel documentation](../docs/KERNEL.md) for its numerical constraints.
