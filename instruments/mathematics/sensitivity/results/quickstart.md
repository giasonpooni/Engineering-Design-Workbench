# Quickstart checks

These checks are first-order and local.

- [PASS] derivative:affine2: analytical vs central; residual=2.635e-11
- [PASS] derivative:quadratic: analytical vs central; residual=1.177e-11
- [PASS] derivative:polar: analytical vs central; residual=4.957e-11
- [PASS] derivative:two-tank: analytical vs central; residual=1.867e-10
- [PASS] composition:scaled-rotation o exp: chain-rule vs composed residual=0.000e+00
- [PASS] coordinates:two-tank:milli: J'dx' vs S J dx residual=3.553e-15; value residual=0.000e+00; J' residual=0.000e+00
- [PASS] covariance:affine2: Frobenius gap=9.687e-03, relative=3.070e-02, n=4000

## Perturbation sweep: exp

Jacobian source: analytical

| scale | absolute remainder | relative remainder |
| --- | --- | --- |
| 1.000e-04 | 4.715e-09 | 4.715e-05 |
| 1.000e-03 | 4.717e-07 | 4.714e-04 |
| 1.000e-02 | 4.730e-05 | 4.708e-03 |
| 1.000e-01 | 4.871e-03 | 4.648e-02 |
| 5.000e-01 | 1.394e-01 | 2.187e-01 |
| 1.500e+00 | 1.832e+00 | 5.526e-01 |

Declared local radius along this direction: 0.1 (first invalid scale: 0.5).
Linear remainder compared along one direction. Tolerances are declared, not universal.
