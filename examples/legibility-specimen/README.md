# One specimen, three representations

Run the complete reproducible fixture from the repository root:

```sh
ciw legibility demo --output-dir results/legibility-demo
ciw legibility verify results/legibility-demo \
  --trust results/legibility-demo/demo-trust.json \
  --expected-object-id notations:specimen:demo-coupon-001 --expected-version 1
```

Open `results/legibility-demo/review.html` and inspect the linked JSON records.
The fixture summarizes synthetic force samples with an actual NET operation,
then executes `legibility.compile.v1` in a separate NET Session. A failed
demonstration threshold, unknown uncertainty and unresolved physical validity
remain visible across human, reasoning and vision views.

The diagram is an SVG, not an acquired photograph. The ephemeral signer is a
demo identity and its private key is discarded. The demo trust file tests
explicit trust policy; it is not an authenticated organizational trust anchor.

[Instrument contracts and real-source commands](../../docs/LEGIBILITY.md).
