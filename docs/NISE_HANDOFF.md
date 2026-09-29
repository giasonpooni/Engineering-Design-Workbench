# NISE → NET handoff

This bridge closes one missing architectural seam without merging NISE and NET.

```text
scientific intent
    ↓
NISE
candidate inference schematic
    ↓
operator binding plan
    ↓
NET semantic capability compiler
    ↓
ordinary ciw.experiment.v1
```

## Ownership

**NISE owns meaning/relevance:** which entities, evidence, models, constraints and
semantic operations are relevant to the investigation.

**NET owns execution:** parameters, dataflow bindings, dependencies, resources,
acceptance criteria, engine lowering and actual execution.

Therefore NISE cannot specify:

- a provider/engine identity;
- an executable/container;
- NET parameters;
- NET input bindings;
- execution authority.

## Binding plan

The operator supplies `ciw.nise-binding-plan.v1` with one entry per NISE
operation selected for execution:

```json
{
  "nise_node_id": "op.spectrum",
  "node_id": "spectrum",
  "parameters": {"channel": "q"},
  "inputs": {},
  "depends_on": ["statistics"],
  "resources": ["cpu"],
  "acceptance": {},
  "inspection": false
}
```

There is deliberately **no capability field** in that record. The capability is
read from NISE `P_q`, preventing the binding packet from silently changing the
meaning NISE selected.

NET then runs the ordinary semantic compiler, which selects only an explicitly
bound qualified lowering.

## Retention

The handoff result retains:

- NISE schematic/query/catalog identity;
- selected NISE operation nodes and epistemic standing;
- NISE unresolved capabilities;
- relevant operation evidence references;
- unselected NISE operation nodes;
- the complete semantic compilation receipt.

The handoff remains `authorizes_execution=false`. It creates an executable
*experiment contract*, but execution is still a separate NET action.

Hypothesized NISE operation nodes cannot be bound in V1.

## CLI

```sh
net nise compile-handoff schematic.json binding.json --output handoff.json
```

No provider executes during this command.
