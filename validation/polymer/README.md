# Polymer instrument readiness evidence

This gate covers the installed NET reference instrument: retained cycle
metrology, scoped cooling and pressure observations, cited copilot context,
bounded simulated control, numerical audits, complete agent graphs, reports,
native measurement import and fresh replay. Physical validation, calibrated
factory accuracy, LLM inference, trained LEM performance and PLC actuation are
not established by these records.

The installed wheel was exercised from `/tmp`, with `PYTHONPATH` removed, and
its import location was checked inside the isolated installation. The package
SHA256, executed checks and exact scientific runtime fingerprint are retained
in [installed-package-check.json](installed-package-check.json).
The final targeted instrument and existing NET regression run passed **663 tests
and 33 subtests**, including refusal, dependency retention, offline restoration,
measurement-condition and covariance boundaries. The final pass includes
the concurrently merged fluid workflow and CLI regressions.

All 23 installed checks passed, including the full MCP stdio graph, repeated
attempt reuse and fresh replay. The included [qualification.json](qualification.json)
records the complete finite gate with a genuine retained native calibration
fixture.

The existing native calibration stack also executed its isolated installed-wheel
gate with all five exact providers: TBRT, MCUR, STFE, GSIE and SET. All 30 tests
passed with zero skips. The shipped synthetic dimension fixture was generated
by those real providers and independently checked by the polymer importer.
It preserves source bytes, native occurrences, marginal uncertainties, complete
joint covariance and its original computational verification.

Fresh PPDA acquisition is **not qualified by this pass**. The required exact
commit is present in private `atomtrapping/Notations-Data-Intake`, but this
environment lacks an authenticated native checkout. Acquired-window import
uses the existing offline validator; its routing and preservation tests use an
explicit integrity double. A supplied legitimate retained acquired bundle can
be inspected/imported without running PPDA. Source identity was not replaced
with a directory copy or guessed commit.

The [example report](example-report.html) presents numerical audit and part
conformity separately. Its dimension is deliberately nonconforming. The
[sample CSV](example-measurements.csv) preserves every declared sample;
it is a marginal projection, not a joint covariance transport.

From an installed checkout:

```bash
net polymer demo --output-dir polymer-demo
net polymer qualify --output-dir polymer-qualification
python -m ciw.agent_mcp polymer-config --output-dir polymer-agent
python -m ciw.agent_mcp serve --instrument polymer --profile polymer-agent/profile.json
```

See the [operator guide](../../docs/POLYMER_PROCESSING.md) for native ingress,
saved audit receipts, exports and measurement-condition boundaries.
