# Independent atmospheric diagnostic reference

These sealed files compare the moist provider's liquid-water saturation
diagnostic at 25 °C against **3169.9 Pa**, transcribed from NISTIR 5078,
Table 1, printed page 4. They declare a 0.4% relative engineering allowance
and a 0.05 Pa display-rounding bound. The published value is independent of
the compiler; its seal does not certify the reference or a physical measurement.

Generate the four retained benchmark cases:

```sh
net atmosphere compare benchmark --output-dir atmosphere-reference-benchmark
net atmosphere compare benchmark-inspect atmosphere-reference-benchmark
net atmosphere compare benchmark-verify atmosphere-reference-benchmark
```

The benchmark creates a compatible 25 °C atmospheric case with zero water,
zero lapse rate and heights `[0, 100] m`. Use its atmospheric bundle as the
candidate when reusing `reference.json` and `policy.json`:

```sh
net atmosphere compare run PATH_TO_25C_ATMOSPHERIC_BUNDLE \
  --reference examples/atmosphere-reference/reference.json \
  --policy examples/atmosphere-reference/policy.json \
  --output-dir atmosphere-reference-comparison
net atmosphere compare inspect atmosphere-reference-comparison
net atmosphere compare verify atmosphere-reference-comparison
```

The diagnostic's current prediction is approximately **3160.0569165 Pa**,
about **0.3105%** below this reference. It passes the declared 0.4% allowance
and fails a tighter 0.1% allowance. Independent comparison verification can
PASS for either correctly calculated result. Neither outcome establishes
ambient humidity accuracy, instrument calibration or full physical validation.

The zero-water column evaluates a pure-liquid saturation reference without
declaring saturated atmospheric air or performing condensation. The humidity
convention is `not_applicable`; these files do not compare ambient RH.

See [the reference comparison contract and qualification scope](../../docs/ATMOSPHERIC_REFERENCE_VALIDATION.md)
and [the original NIST table](https://www.nist.gov/system/files/documents/srd/NISTIR5078-Tab1.pdf).
