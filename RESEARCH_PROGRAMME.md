# Research programme: computational instrumentation and representation

## Purpose

Build useful scientific instruments and creative tools while testing the representations, interfaces and workflows that connect them. Notation Systems' engineering work and Cartesian Graphics' creative projects supply distinct test cases; neither is reduced to a demonstration of a predetermined theory.

```text
build → run → observe → fix → audit → compare → continue
                           ↓
              candidate principle or counterexample
```

This is an experimental design and reporting guide. It installs no new telemetry collector, execution engine, scientific IR or evidence ledger. Use the existing NET sessions, provider contracts and authorized evidence handoffs; do not introduce a parallel source of canonical state.

## Research questions and specimens

| Question | Candidate specimen | What to observe |
| --- | --- | --- |
| What must survive a measurement transformation? | ClockSync, Calibration, Metrology Adapter | Source identity, units, clock/frame/model, correlated uncertainty, refusal and replay. |
| How far is a local approximation valid? | Surface and Sensitivity | Reference error, convergence, perturbation size, chart/regime boundaries and invalid cases. |
| Which state distinctions do measurements support? | Observability, SensorDesign, FlowState | Rank/conditioning under declared models, confounding, residual behavior and out-of-regime failures. |
| Which operations genuinely compose? | NET and Compute Runtime | Shape/type/unit/effect compatibility, exact provider identity, rejected handoffs and preserved results. |
| What structure is necessary for a task? | NISE and a fixed investigation corpus | Dependency and boundary closure, retained contradictory evidence, reduction/fidelity tradeoffs. |
| Does tooling improve expert output? | Scientific workflows and Cartesian production | Accepted integrated output, total human effort, rework, independent review and transfer to new users. |
| When is another backend useful? | Qualified CPU/GPU or language providers | End-to-end time, memory, transfer/compilation cost, numerical error and supported hardware. |

These are proposed experiments, not a catalogue of completed cross-domain results. A new test may expose a missing adapter or inappropriate mathematical assumption before producing a performance result.

## Evidence levels

Keep an observation, interpretation, empirical pattern, design principle, formal proposition, assumption and theorem distinct. Repeated examples can motivate an axiom for a chosen formal system; they do not empirically prove that axiom universally. Record scope and counterexamples. A theorem requires stated assumptions and an argument or checkable proof; successful execution is not a theorem.

Do not merge synthetic evidence, measured physical data, an agent hypothesis, a creative preference and an independently verified result into a single confidence label. Human feedback may be a valuable annotated judgement without being a calibrated measurement.

## Representation reduction

For a declared task and supported operation family, compare full and reduced representations using task-specific acceptance criteria. Record the reduction's overhead, omitted information, retained uncertainty and reference behavior.

A graph slice is not automatically a closed dynamical subsystem. Retain external inputs, coupling terms, initial conditions, correlations, boundary conditions and any source relationships needed by the chosen operation. Simply deleting rows/columns can change the problem. A locally zero derivative or a successful single ablation is not proof of global irrelevance.

Distinguish a minimal representation (no permitted single reduction succeeds), a global cost minimum and an approximation within a declared tolerance. Passing a finite test corpus does not prove any global minimum. Domain count is coverage, not a statistical confidence estimate; related datasets and implementations are not independent evidence.

Exact mathematical sufficiency, practical usability by a particular agent, and token count are different objectives. A compact representation can preserve an answer mathematically and still be difficult for a user or language model to interpret.

## Comparison protocol

Use a manual/scripted baseline, an LLM/tool baseline and the proposed instrument workflow only where each is appropriate. Hold the task, available evidence, acceptance rule, privacy policy and resource access comparable. Retain setup, failed attempts, prompts, corrections and human review—not just successful final runs.

Measure on held-out operating regimes and, where relevant, users or projects not used to design the abstraction. Include missing inputs, conflicting sources, unit/frame mistakes, uncertain calibration, stale dependencies and adversarially irrelevant context. Do not tune the acceptance rule after observing which candidate wins.

For stochastic components, record seeds, repeated trials and uncertainty on reported metrics. Distinguish cold/warm execution, exact-cache reuse, compilation, data transfer and kernel execution. An actual GPU must be identified before claiming GPU performance; software-rendered images or CPU timings do not qualify.

## Metrics

| Dimension | Required interpretation |
| --- | --- |
| Scientific fidelity | Error relative to a declared reference, coverage/calibration where supported, constraint/refusal behavior and regime of validity. |
| Reproducibility | Exact input/model/source/environment bindings; replay and result comparison scope. |
| Representation | Bytes/tokens/nodes/edges using declared counting conventions, plus task fidelity and reduction overhead. |
| Computation | Wall/CPU/device time and memory where measured; transfer, serialization and orchestration included separately. |
| Agent use | Provider-reported or explicitly labelled estimated input/output tokens, tool calls, retries, cache status and cost basis. |
| Human effort | Setup, supervision, interpretation, integration, rework and final review. Unknown effort remains null. |
| Creative production | Accepted, integrated playable/artistic output under fixed production constraints and separate human review. File count and automated tests alone are inadequate. |
| Transfer | Additional adapters, model assumptions and human work required for a new domain or user. |

Do not add seconds, dollars, tokens and joules directly. Report a vector of costs, or state conversion rates/weights and run sensitivity analysis. Compare Pareto tradeoffs before claiming one universal yield score.

A deterministic calculation can reveal consequences that a bounded user had not computed; it does not create new information about the world from fixed complete evidence. Separate new measurements from reduced computational uncertainty. Information-gain-per-cost is one possible heuristic, not a guarantee of optimal long-horizon policy. Calibrated task performance and decision relevance remain necessary.

## Retained experiment record

Use existing records where available; the following is a checklist, not a replacement schema:

- Question, hypothesis, scope, proposed falsifier and acceptance rule fixed before comparison.
- Evidence/model/source revisions, operation and provider identities, runtime/hardware and dependency/boundary assumptions.
- Attempt-specific inputs, outputs, errors, refusals, annotations, measured resource use and missing telemetry.
- Separate verification identity and method, baseline comparison, repeated-trial summary and reviewer judgement where required.
- Counterexample, limitation and narrowly scoped implication for the next implementation or formal proposition.

Retention, canonical admission, authorization, integration and release remain separate decisions. Existing source terms govern whether an artifact can be included or shared. No test record grants a licence to reuse restricted evidence or a permission to actuate hardware.

## What counts as progress

First demonstrate a useful bounded operation. Then demonstrate a correct composition. Then show transfer to an independently chosen case with measured overhead and failures. Formalize a property only when its objects, assumptions and preservation claim are explicit. Successful theories must predict behavior on new cases; unsuccessful hypotheses can still produce valuable tools, benchmarks and counterexamples.

The programme makes no claim of a new physical law, universal axioms, a complete categorical foundation, guaranteed minimum context, maximum free-energy yield, or quantum breakthrough. Those labels are not substitutes for a result.

## Existing development references

These are separately scoped development increments, not necessarily features of this checkout:

- [ClockSync instrument surface #3](https://github.com/giasonpooni/Notations-ClockSync/pull/3).
- [NET FIR instrument #71](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/71) and [Compute Runtime #11](https://github.com/giasonpooni/Notations-Compute-Runtime/pull/11).
- [NET measured coding/vision revision #76](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/76).
- [NET bounded workflow algebra #79](https://github.com/giasonpooni/Notations-Systems-Terminal/pull/79).

Historical qualification belongs to its exact source and environment. This documentation update does not rerun or independently validate those experiments.
