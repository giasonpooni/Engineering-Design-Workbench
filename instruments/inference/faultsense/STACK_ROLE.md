# Instrument boundary

FDIR consumes declared residual data and emits statistical diagnostics. It belongs alongside estimation and evaluation, with no authority over the observed plant or operational state.

| Participant | Boundary |
| --- | --- |
| PPDA | Preserves observation evidence, acquisition identity, and lineage |
| STFE | Owns telemetry conditioning and feature transformations where used |
| GSIE | Owns estimation, innovation construction, and innovation covariance |
| FDIR | Owns the numerical diagnostic operation and its declared threshold comparison |
| CBSR | Owns constraint reconciliation; FDIR does not replace it |
| SET | Owns offline evaluation, labeled test cases, and comparative benchmarking |
| CIW | Inspects diagnostic records and their source references |
| ESM / operational policy | Owns admission and operational decisions outside FDIR |

Innovation covariance is an estimator input here, not an asserted truth about the physical system. The caller is responsible for compatible residual/covariance coordinates, model provenance, and valid uncertainty semantics. FDIR validates numerical admissibility, not calibration correctness.

FDIR retains raw residual values and declared source IDs. These references are attribution supplied by the caller; the numerical API does not resolve source objects, verify their authenticity, or grant them authority. A surrounding record can bind the input, operation, result, execution, and verification identities separately.

No function reads a sensor, changes an estimator, suppresses an observation, edits a source artifact, admits evidence, or invokes a control adapter. A threshold crossing is a diagnostic observation available to separately governed consumers.

Physical cause isolation, fault confirmation, automatic threshold calibration, and a fault-response policy are absent from this foundation. The repository name defines the instrument domain, not a claim that each domain capability has been implemented.
