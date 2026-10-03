# Evidence-pool architecture reference

The implemented evidence objects are defined in `evidence/types.py`; admission is defined in `evidence/admission.py`. [SCOUT architecture](SCOUT_ARCHITECTURE.md) documents acquisition, extraction and the complete admission boundary.

## B. Objects

| Object | Meaning |
| --- | --- |
| `Source` | Named origin of retrieved documents |
| `Document` | Retrieved content and its retrieval method |
| `Record` | A source-located structural unit within a document |
| `Observation` | Extracted content linked to its input records and extraction method |
| `Referent` | An explicitly keyed subject, separate from a Morpho entity |
| `ClaimedRelationship` | A source-supported claim between referents |
| `DerivedValue` | A computed value linked to observations or other derived values |
| `DerivedGrounding` | Explicit subjects of a derived value, separate from its inputs |

Use the `make_*` factories to derive identities from content. Timestamps and confidence are retained annotations; they do not substitute for provenance.

## D. Payloads and identity

Record locators and observation contents are source-defined. The structural contract does not impose a universal domain ontology. Observation identity includes sorted record identifiers, extraction method and content. Confidence and extraction time are excluded from that identity.

## E. Conflicting claims

A claimed relationship's identity includes its supporting observation. Different source claims can coexist without one overwriting the other. A relationship's confidence is not an instruction to merge referents or promote a claim to canonical state.

## G. Derived graph and provenance

`evidence/trust_graph.py` derives a graph view from the pool. Provenance tracing follows retained object references. The graph is not a mutable canonical store and cannot create a new canonical version.

## K. Extraction and epistemic status

Model-attributed extraction retains its method, confidence and provenance. The admission gate validates the required structure and references. Model output is not silently converted into a canonical fact. `retrieval/epistemic.py` classifies observations from their extraction-method labels; the status taxonomy is documented in [Computational evidence reference](COMPUTATIONAL_COMMONS.md).

## M. Subjects and inputs

`DerivedValue.derived_from` names inputs. `DerivedGrounding.referent_ids` names subjects. These are different relationships with separate identities. Multiple groundings can coexist without changing a derivation's content identity.

## O. Authority boundary

SCOUT acquires source documents, extracts candidate evidence and submits it to evidence admission. It does not import canonical validation or construct canonical states and versions. Retrieval reads the pool and returns context packages without mutating it. The evidence pool does not itself define a promotion path into canonical state.

## S. Limits

Referent identity is computed from an explicit natural key and kind. No fuzzy entity-resolution merge is implied by similar names. Graph metrics describe the recorded structure; they are not evidence of independent corroboration or scientific truth. Admission, extraction, derivation, retrieval and canonical validation remain separate operations.
