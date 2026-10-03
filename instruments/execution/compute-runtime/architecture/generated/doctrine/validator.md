# Validator doctrine (generated -- do not edit; see doctrine_generator.py)

Duty: acceptance and rejection

Constraints:
- the substrate is an acquisition-first loop; external information enters through acquisition only
- every enforcement validator records its authoring binding (builder_check_lineage_recorded)
- resource telemetry is operational metadata and never enters evidence identity
- the validator is vendor-independent from the proposing lineage (binding details live in the canonical binding configuration, not here)
- acceptance is fail-closed; rejected input enters quarantine with failing invariant ids -- there is no force path
- validation is a status on a claim, never an evidence class
