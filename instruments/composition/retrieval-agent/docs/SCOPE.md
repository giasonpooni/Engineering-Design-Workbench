# Scope

First slice:

- authored function graph + factor graph
- well-typed edges only
- retrieval by id, kind, typed path, blanket
- eligibility for `jspt.jacobian_at`, `jspt.sweep_perturbation_scale`, `lyapunov.evaluate`, `rci.bind`, `cse.dispose`
- annotation nodes `SAMPLED` / `REFUSED` / `NOT_ELIGIBLE` / `UNRESOLVED`
- JSON canonical store, mermaid sheet, USDA projection
- shipped quadratic-drag plant

Not in this slice:

- vendoring JSPT / PLSR or making them mandatory core dependencies
  (optional pinned adapters can import installed kernels on explicit calls)
- synthesizing `P`
- USD schema plugins or `pxr` runtime
- image / P&ID OCR
- vector search, GraphRAG, USD Search
- sparse factor-graph belief updates
- inferring `measures` or `nets` from names, proximity, or renders
- a production observer runtime
