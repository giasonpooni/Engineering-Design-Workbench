# Fluid composition checks

These checks are first-order and local.

- [PASS] derivative:storage: analytical vs central; residual=6.700e-11
- [PASS] composition:storage o balance: chain-rule vs composed residual=0.000e+00
- [PASS] composition:storage o gauge-totalizer: chain-rule vs composed residual=0.000e+00
- [PASS] coordinates:fluid-balance:level-mm: J'dx' vs S J dx residual=0.000e+00; value residual=0.000e+00; J' residual=0.000e+00
- [PASS] coordinates:fluid-observer:level-mm: J'dx' vs S J dx residual=0.000e+00; value residual=0.000e+00; J' residual=0.000e+00
- [PASS] metric:fluid-observer:level-mm:si: unscaled ||J||_2=3.046e+00, ||J'||_2=3.046e-03; scaled gains 3.04634 vs 3.04634
