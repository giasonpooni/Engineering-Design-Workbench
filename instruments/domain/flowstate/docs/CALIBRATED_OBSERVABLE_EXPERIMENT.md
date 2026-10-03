# Calibrated, observable two-channel process experiment

`examples/calibrated_observable_two_reservoir.v1.json` is the bounded synthetic
process declaration used by CIW and ICRH. FSRT owns only the case topology and
ordered process assumptions. The numerical authorities remain separate:

1. TBRT maps each untouched device timestamp into one reference clock and retains
   synchronization evidence, map covariance and validity.
2. MCUR applies each valid affine calibration and refuses unknown
   indication/parameter cross-covariance.
3. OIT evaluates the finite-horizon linear observability matrix and classifies
   rank and conditioning before GSIE is allowed to update.
4. GSIE retains the innovation, innovation covariance and gated posterior.
5. CBSR tests and, when eligible, reconciles the declared 100 kg conservation law.
6. FDIR consumes the retained GSIE residual covariance and declared fault
   signatures; it does not rebuild the estimator.

The two raw device times differ (`1005 s` and `2004 s`). Their independently
evidenced affine maps both produce reference time `5 s`. The raw indicated
masses (`51 kg`, `45 kg`) calibrate to (`52 kg`, `46 kg`). The full calibrated
covariance retains the shared off-diagonal term rather than treating the two
channels as independent.
Each raw observation retains its clock frame independently of its map; a map
whose source frame differs is refused rather than relabeling the evidence.

Alignment is explicitly nominal: each timestamp's uncertainty is retained, and
the experiment does not claim simultaneous physical sampling or infer sample
order from overlapping uncertainty. The bounded process is a stationary hold
(`F = I`, `Q = 0`), so no time-dependent state propagation is hidden in this
case. Timing uncertainty is not propagated into measurement covariance; a
dynamic extension must declare that propagation before using this profile.
The GSIE update also requires an explicit `declared_zero` prior/measurement
cross-covariance policy. Shared measurement covariance remains fully retained.

This fixture is synthetic interoperability evidence. It is not a physical
calibration certificate, a validated reservoir model, or permission to act on a
fault label.
