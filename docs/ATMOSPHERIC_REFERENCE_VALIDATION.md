# Atmospheric reference comparison and qualification

NET can retain a dry or moist atmospheric candidate, compare selected scalar
states against a separately declared reference, and independently verify the
comparison arithmetic. The reference comparison extends the existing
investigation substrate. The governing-equation verifier, reference evidence,
acceptance policy, comparison result and comparison verification retain
separate identities.

Three questions receive separate answers:

| Question | Evidence and result |
| --- | --- |
| Did the atmospheric provider satisfy its declared equations and domain? | Existing independent dry or moist numerical verification |
| Do selected retained states agree with the reference under the declared acceptance policy? | Pointwise comparison outcome and explicit alignment checks |
| Was the comparison arithmetic and its decision reconstructed correctly? | Separate comparison verification; it can PASS for correctly calculated disagreement |

A numerical PASS does not establish agreement with an external reference.
Agreement does not authenticate a measurement or validate its calibration.
Neither result establishes physical validation of the entire atmospheric
column, a weather forecast, material conditioning or canonical state admission.

## Fixed independent diagnostic benchmark

`net atmosphere compare benchmark --output-dir atmosphere-reference-benchmark`
creates four retained moist atmospheric investigations and their reference
comparisons. The independent reference is NISTIR 5078, Table 1, printed page 4
(first page of the table PDF). That report tabulates saturation properties
from the IAPWS-95 formulation. The benchmark uses these four liquid-water
saturation pressures, converted from MPa to Pa with the exact factor
`1_000_000`:

| Temperature | Reference temperature | Published saturation pressure | Magnus prediction | Absolute relative discrepancy |
| --- | --- | --- | --- | --- |
| 20 °C | 293.15 K | 2339.3 Pa | 2332.5960221 Pa | 0.2866% |
| 25 °C | 298.15 K | 3169.9 Pa | 3160.0569165 Pa | 0.3105% |
| 30 °C | 303.15 K | 4247.0 Pa | 4233.7239159 Pa | 0.3126% |
| 35 °C | 308.15 K | 5629.0 Pa | 5612.8417194 Pa | 0.2871% |

The fixture stores the published values directly. Creating it never calls an
atmospheric compiler or evaluates the Magnus law to generate expected values.
Each case declares an isothermal column with zero water mixing ratio and
heights `[0, 100] m`; only the liquid-water saturation diagnostic at sample
zero is compared. Zero water avoids declaring a saturated atmospheric state.
Evaluating a saturation reference does not perform condensation or phase
equilibrium simulation.

The benchmark permits `0.004` relative engineering discrepancy (0.4%) plus a
`0.05 Pa` reference display-rounding bound. The latter is half the table's
`0.1 Pa` last displayed digit; it is not the physical uncertainty of IAPWS-95
or a calibration certificate. A tighter `0.001` relative allowance correctly
produces disagreement at all four points. This documents a physical-model
approximation discrepancy that the much smaller internal numerical
tolerances cannot measure. The four passing points do not prove a continuous
error bound or qualify any other observable.

The reusable 25 °C reference and policy are in
[`examples/atmosphere-reference`](../examples/atmosphere-reference/README.md).
Use the benchmark-generated 25 °C atmospheric bundle for those files; its
zero-water, isothermal declaration is distinct from the general moist example.

`net atmosphere compare benchmark-inspect atmosphere-reference-benchmark`
reads the retained aggregate. `net atmosphere compare benchmark-verify
atmosphere-reference-benchmark` freshly verifies its case comparisons and
reconstructs the aggregate bindings. The aggregate is not an additional
physical-validation authority.

## Reference contract

For corrected SI measurement logs, [measurement preparation](ATMOSPHERIC_MEASUREMENT_INGRESS.md)
provides `net atmosphere compare prepare`, retains the original CSV and declared
context, and writes sealed reference and policy files. Static inspection checks
retained bindings; explicit preparation verification freshly checks the CSV
mapping. Both preserve the authority limits below.

The sealed reference schema is `ciw.atmosphere-reference.v1`. Its exact groups
are `schema`, `provenance`, `context`, `observations` and `record_digest`.
The separately sealed policy schema is
`ciw.atmosphere-comparison-policy.v1`.

| Comparison field | Exact SI unit | Available candidate profiles |
| --- | --- | --- |
| `temperature_k` | `K` | Dry and moist |
| `pressure_pa` | `Pa` | Dry and moist |
| `density_kg_per_m3` | `kg/m^3` | Dry and moist |
| `water_vapour_pressure_pa` | `Pa` | Moist |
| `relative_humidity` | `1` | Moist, with a compatible explicit convention |
| `liquid_water_saturation_pressure_pa` | `Pa` | Moist |

The reference contains 1–129 observations with unique, increasing integer
sample indices. Each observation declares its exact height and a nonempty
subset of the six scalar fields. At most 774 scalar comparisons can be
requested. There is no interpolation, extrapolation, frame conversion,
geodetic transformation or inferred unit conversion. Coordinate frame,
height-origin label, retained sample height and UTC context must align before
the values are evaluated. A reference at an unretained height requires an
expanded sampling investigation rather than a hidden interpolator.

Provenance distinguishes `synthetic_fixture`, `published_reference` and
`declared_measurements`. It retains a source reference, an optional HTTP(S)
source URL and an explicit independence declaration. URLs are metadata;
reading or comparing a saved artifact does not fetch them. A content hash
binds the declared reference but does not prove its authorship or independence.

Declared measurements require a nonnull UTC timestamp, an instrument
reference and a nonzero declared uncertainty bound. Calibration references
can be retained, but the comparison engine does not inspect a certificate,
assess traceability or certify the instrument. Missing calibration evidence
remains visible as a null reference.

## Engineering acceptance and reference bounds

The policy uses the rule
`absolute_plus_relative_plus_reference_bound`. For candidate scalar `c`,
reference scalar `v`, declared absolute allowance `a`, relative allowance `r`
and reference bound `b`,

$$
\Delta=c-v,\qquad A=a+r|v|,\qquad B=A+b,
\qquad \eta=\frac{|\Delta|}{B}.
$$

A point passes when `abs(Delta) <= B`. The result retains signed and absolute
differences, engineering allowance, reference bound, total allowance,
normalized acceptance residual and the pointwise decision. Exact agreement
with a zero total allowance is treated explicitly; no division-by-zero
substitute invents uncertainty.

`eta` is an engineering acceptance residual. It is not a statistical z-score,
confidence interval, estimated model uncertainty or probability of failure.
The additive rule does not infer covariance, fit parameters or combine
multiple points into a statistical confidence claim. Policy limits and the
reference bound remain separate declarations.

Reference uncertainty records distinguish `declared_expanded`,
`declared_absolute_bound`, `rounding_bound` and `exact_fixture`. For
`declared_expanded`, the supplied absolute bound is already the expanded
uncertainty `U`; the supplied coverage factor `k` is retained rather than
applied a second time. The engine does not infer a confidence level from `k`.
Only a synthetic fixture can use `exact_fixture`; published display rounding
does not turn a tabulated reference into an exact physical standard.

NIST TN 1297 distinguishes standard uncertainty from expanded uncertainty and
requires reporting the coverage factor with an expanded value. Its propagation
law includes covariance where relevant. This bounded comparator performs the
declared engineering rule; it does not implement a full uncertainty-propagation
or calibration evaluation.

## Humidity conventions and unsupported transitions

The current moist provider's humidity is
`pure_liquid_magnus_17_62_243_12.v1`: vapour partial pressure divided by the
selected pure-liquid Magnus saturation approximation. `relative_humidity`
is a fraction, so `0.50` means 50%. The context must explicitly name that
convention before this field can be compared.

Pressure-enhanced humid-air relative humidity uses a different saturation
reference. NIST SP 250-83r1, Appendix I, Eq. A21 includes the enhancement factor
`f(T,p)` in the denominator. Such a declaration produces EXPAND for a current
pure-liquid humidity comparison. The engine retains the unsupported request
and does not silently relabel the sensor reading, insert an enhancement law
or relax the numerical model's humidity guard. Saturation-pressure benchmark
references use `humidity_convention: not_applicable` because they compare a
pure-water thermodynamic diagnostic rather than ambient RH.

Existing LOCAL / EXPAND / REFUSE behavior governs the requested transition.
LOCAL means the comparison is supported and aligned; its agreement outcome
can be PASS or FAIL. EXPAND retains unsupported fields or conventions, while
REFUSE records incompatible retained alignment. Agreement remains FAIL if
any evaluated point fails, including a mixed request with unsupported fields.
A fresh comparison verification can PASS when it confirms a correctly
computed disagreement or unsupported transition; this remains distinct from
accepting the comparison.

## Retained use and readiness

Use `net atmosphere compare run` with an existing numerically qualified
atmospheric bundle, a sealed reference and a sealed policy. The comparison
retains the reference evidence identity separately from the atmospheric
evidence, compiler result and execution, atmospheric verification, comparison
operation and execution, and comparison verification. Inspection reads the
saved records. Explicit verification independently reconstructs their
arithmetic and bindings. Export follows fresh verification and preserves
pointwise outcomes; it does not authorize provider activation or state
admission.

`net atmosphere compare example --profile dry --reference-output reference.json
--policy-output policy.json` creates a synthetic origin-temperature/pressure
lifecycle fixture for the selected default profile. Choose `--profile moist`
for the default moist profile. These generic fixtures derive only from the
declared origin configuration and explicitly declare no independence from it;
they are distinct from the published NIST benchmark. Export with
`net atmosphere compare export comparison-bundle --format csv --output
comparison.csv`, or select `--format json` for the structured retained result.

Comparison commands return exit code `0` for supported agreement, `2` for a
qualified EXPAND/REFUSE decision or reference disagreement, and `1` for invalid
input or an I/O error. A numerically verified LOCAL disagreement can be
exported for diagnosis; the export creates the file and returns `2` to retain
the agreement outcome. Check the JSON receipt and output file as well as the
exit code when automating this case.

After editing a reference or policy, regenerate its seal with Python from the
same environment as the installed `net` command. This example validates both
edited artifacts before writing create-only outputs:

```python
from pathlib import Path
from ciw.atmosphere_comparison_contract import validate_reference, validate_policy
from ciw.control_contracts import save_new
from ciw.operations.runner import seal
from ciw.session import loads_json

reference = seal(loads_json(Path("edited-reference.json").read_text(encoding="utf-8")))
policy = seal(loads_json(Path("edited-policy.json").read_text(encoding="utf-8")))
validate_reference(reference)
validate_policy(reference, policy)
save_new(Path("reference-ready.json"), reference)
save_new(Path("policy-ready.json"), policy)
```

Sealing records content integrity. It does not authenticate the source,
establish calibration or grant physical-validation authority.

To use physical measurements, acquire a stable declared environment and
retain corrected SI values, acquisition time, exact sampled heights,
instrument and calibration references, uncertainty bounds and compatible
humidity definitions. Choose engineering allowances before interpreting
agreement. Independently assessed source authenticity, traceability,
representativeness and model discrepancy are still needed to establish a
physical validation claim. Repeated synthetic runs do not supply that evidence.

The engine is usable for its bounded declared models and for auditing
selected reference comparisons. General weather, phase change, turbulent
mixing, transport coefficients for moist air, radiation and polymer moisture
conditioning require separate qualified providers and evidence.

## Primary references

- [NISTIR 5078 report and table index](https://www.nist.gov/system/files/documents/srd/NISTIR5078.htm)
- [NISTIR 5078, Table 1: saturation by temperature](https://www.nist.gov/system/files/documents/srd/NISTIR5078-Tab1.pdf)
- [NIST TN 1297: law of propagation of uncertainty](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty)
- [NIST TN 1297: reporting uncertainty](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-7-reporting-uncertainty)
- [NIST policy on metrological traceability](https://www.nist.gov/calibrations/traceability)
- [NIST SP 250-83r1: calibration of hygrometers with the Hybrid Humidity Generator](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.250-83r1.pdf)
- [WMO-No. 8: current guide and meteorological-variable chapter index](https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/instruments-and-methods-of-observation-programme-imop/guide-instruments-and-methods-of-observation-wmo-no-8-0)
