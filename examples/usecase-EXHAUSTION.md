# Use-case catalog exhaustion (catalog layer only)

**Defensible completion statement:** all combinations in this version of the
declared industry–verb catalog have been generated.

**Not claimed:** no new experiments are possible; every folder is a distinct
validated investigation; ESM supplies real observations across industries.

## Reported arithmetic (local generator run)

| Metric | Value |
| --- | --- |
| Declared product | 376 industries × 24 verbs = 9,024 |
| Hand-authored extras | 50 |
| Total catalog entries | 9,074 |
| JSON export (local) | 9,074 / 9,074 |
| remaining_unused (product) | 0 |
| Catalog exhausted | true |

Treat **9,074 as a reported local count** until independently audited against a
remote revision that contains the generator.

## Coverage layers (track separately)

| Layer | What it establishes | Status of this catalog |
| --- | --- | --- |
| Catalog coverage | Every declared industry–verb has an entry | Reported complete |
| Export coverage | Every entry can emit expected render JSON | Reported complete (local) |
| Executable coverage | Entries invoke scientific operations with usable inputs | **Not established by folder count** |
| Numerical coverage | Regimes, assumptions, boundaries, failures exercised | **Not established** |
| Result checking | Outputs checked against references / independent impls | **Not established** |
| Real-data grounding | Identifiable observations with provenance | ESM URL alone does **not** establish this |

Preserve `not_run`, `blocked`, and `unknown`. Do not promote catalog completeness
to experimental completeness.

## Scope note

Earlier wording mixed industry × instrument-family × scenario with the final
industry × verb product (ten owned families). The generator must map each verb
explicitly to family + scenario; the two products are not silently equivalent.

Count **application descriptions** separately from **distinct computational
configurations** (dedupe by operation, model, inputs, uncertainty assumptions,
expected outcome — not by industry title).

## Freeze policy

Keep the 9,074 entries and 50 extras. **Stop expanding folder count solely to
grow the number.** Next milestone: executable, meaningfully different, checked
investigations and an execution/coverage report — not folder 9,075.

## Regenerate (catalog / export only)

```bash
python3 examples/workflows/generate_usecase_corpus.py
python3 examples/workflows/emit_all_usecases.py
```

## ESM

Cite [Evidence-and-State-Management](https://github.com/giasonpooni/Evidence-and-State-Management)
as an **Evidence seam** for UNADMITTED candidate retention
(`may_authorize: false`, `canonicalAdmission: false`). That is destination
policy, not proof that experiments obtained inputs from ESM. Real-data cases
must bind artifact digest, selected fields, and transform into instrument
inputs. Synthetic fixtures must be labeled synthetic.
