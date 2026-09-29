# Mathematical model

For fixed source and reference anchors,

```text
t_ref = reference_origin + skew * (t_device - device_origin) + offset
```

The uncertainty coordinates are

```text
[device_time, skew, offset]
```

with units `[s, 1, s]`. The Jacobian is

```text
J = [skew, t_device - device_origin, 1]
```

and the first-order propagated variance is

```text
variance = J @ joint_covariance @ J.T
```

Cross-covariance terms are retained. The source observation, model, anchors,
Jacobian and covariance are preserved in the result.

This model does **not** fit skew/offset, convert civil time scales, provide a
confidence interval, or establish metrological traceability. See
`docs/NUMERICS.md` for the numerical boundary.
