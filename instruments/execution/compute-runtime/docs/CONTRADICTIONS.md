# Contradictions Discovered During Implementation

Frozen Specification: `docs/ARCHITECTURE_SPEC.md` v1.0.0.

Format per entry: conflicting requirements, exact sections, why they
conflict, and the smallest resolution applied (or proposed, if
implementation was blocked pending a decision).

---

## C1: `entity_decl`'s formal grammar does not admit its own worked example

**Sections involved:** §7.A (Lexical structure / KEYWORDS), §7.B
(`entity_decl`, `attr_stmt` productions), §7.C (minimal example).

**Conflict:**

§7.B defines:

```ebnf
entity_decl = "entity" , IDENT , "{" , { attr_stmt } , "}" ;
attr_stmt   = IDENT , ":" , value , ";" ;
```

i.e. an entity body is a flat list of `IDENT : value ;` statements, and
nothing else.

§7.C's own worked example is:

```morpho
entity mass {
    id: "mass";
    type: "scalar";
    value: 10;
    unit: "kg";
    provenance {
        source: "canonical";
        origin_version: "5f2a...c91";
    }
}
```

Two things in this example are not legal under §7.B's `entity_decl`
production:

1. **`type: "scalar";`** — `type` is listed in §7.A's `KEYWORDS` set
   (reserved, case-sensitive: `... , "type" , ...`). A lexer that honors
   §7.A tokenizes `type` as the `TYPE` keyword, not as an `IDENT`. But
   `attr_stmt`'s name position requires `IDENT` specifically. So a
   spec-literal lexer + parser rejects the spec's own example on its
   second line.
2. **`provenance { ... }`** — this is not an `attr_stmt` at all (no `:`
   before `{`). It is a bare `provenance_block` (§7.B) appended directly
   inside the entity body. But `entity_decl`'s production only allows
   `{ attr_stmt }` — there is no alternative in the grammar for a trailing
   `provenance_block` inside an entity, unlike `relation_decl`, which
   explicitly has `[ provenance_block ]` as an optional trailing member.

**Why this is a contradiction, not just an omission:** §7.C is presented
as a worked instance of the §7.B grammar ("Minimal example (canonical
projection of the v1 prototype)"), not as an independent, looser
illustration. A conforming parser cannot satisfy both "implement exactly
the EBNF in §7.B" and "the example in §7.C is valid Morpho" simultaneously
without one of them giving way.

**Smallest resolution applied:**

1. `attr_stmt`'s name position accepts either an `IDENT` token or any
   single reserved-keyword token, using the keyword's literal text as the
   attribute name. This is a lexer/parser-only change (no new keywords, no
   new punctuation, no change to what is a valid identifier elsewhere) --
   the standard "contextual keyword" resolution: a token that is reserved
   in declaration-keyword position is still plain text in attribute-name
   position. Implemented in `morpho/parser.py::_parse_attr_stmt`.
2. `entity_decl`'s grammar is extended with the same optional trailing
   `provenance_block` that `relation_decl` already has:

   ```ebnf
   entity_decl = "entity" , IDENT , "{" , { attr_stmt } , [ provenance_block ] , "}" ;
   ```

   This is the minimal change because it reuses a production
   (`provenance_block`) and a slot shape (`[ provenance_block ]` as the
   last member before the closing brace) that already exists verbatim in
   `relation_decl` -- it does not invent a new construct, only extends
   `entity_decl` to accept the one construct `relation_decl` already
   accepts in the same position. `morpho/ast.py::EntityDecl` carries an
   `Optional[ProvenanceBlock]` field to match.

Both fixes are applied in `morpho/lexer.py`, `morpho/parser.py`, and
`morpho/ast.py`, and are covered by `morpho/test_grammar.py` (which
parses the exact §7.C and §7.D example text as fixtures).

---

## C2: `provenance_block`'s grammar uses two keywords §7.A never declares

**Sections involved:** §7.A (`KEYWORDS` list), §7.B (`provenance_block`
production).

**Conflict:** §7.B's `provenance_block` production uses `"source"` and
`"origin_version"` as fixed literal keywords (parallel to how
`relation_decl` uses the literals `"from"`/`"to"`/`"type"`, which *are*
listed in §7.A). But §7.A's `KEYWORDS` enumeration never lists `source` or
`origin_version`. A lexer built strictly from the §7.A list tokenizes
both as plain `IDENT`, which the literal-keyword-based `provenance_block`
production as written cannot match consistently with how every other
fixed-field production (`relation_decl`, `frame_decl`, `group_decl`,
`constraint_decl`) is actually parsed in this implementation (by matching
a specific keyword token kind, not by matching "some IDENT that happens
to read 'source'").

**Smallest resolution applied:** add `source` and `origin_version` to the
`KEYWORDS` set in `morpho/lexer.py`, matching what §7.B already assumes.
Neither word is used as a generic entity attribute name anywhere in the
frozen spec's own examples (§7.C/§7.D use `id`, `type`, `value`, `unit` at
the entity level), so this addition does not reopen the C1-style
attr-stmt-name collision -- it is a pure omission fix, not a new
ambiguity.

---

## C3: `relation_decl`'s `type` field is grammared as `IDENT` but exemplified as `STRING`

**Sections involved:** §7.B (`relation_decl` production), §7.D (worked
example), §3/§6/§11 (`EdgeRecord.type: str`, `EdgeSchema.type: str`,
`MorphoRelation.type: str`).

**Conflict:** §7.B's `relation_decl` production requires:

```ebnf
"type" , ":" , IDENT , ";"
```

i.e. an unquoted identifier. But both relations in §7.D's own example
write it as a quoted string:

```morpho
type: "depends_on";
...
type: "spatial_adjacency";
```

A spec-literal parser expecting `IDENT` rejects the spec's own example
(confirmed: parsing §7.D verbatim raises `ParseError: expected IDENT, got
STRING` at the first relation's `type` field).

**Smallest resolution applied:** parse `type` in `relation_decl` as
`STRING`, not `IDENT`. This is the smaller change (a one-production
grammar fix vs. rewriting the frozen example), and it is the choice
consistent with the rest of the spec's own type system: every other place
a relation/edge "type" appears -- `EdgeRecord.type: str` (§3),
`EdgeSchema.type: str` (§6), `MorphoRelation.type: str` (§11) -- is
already a plain string, not a restricted-identifier namespace. Treating
`relation_decl`'s `type` as `IDENT` would have made it the sole outlier.
Implemented in `morpho/parser.py::_parse_relation_decl`.

No other section of the frozen specification was found to conflict with
another section during implementation.
