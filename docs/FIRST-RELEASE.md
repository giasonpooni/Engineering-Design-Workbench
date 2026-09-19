# First-release acceptance gate

The first release must provide executable evidence for all of the following:

- paired edges match in length within a declared tolerance and reverse orientation;
- total area is positive and stable under an equivalent polygon presentation;
- vertex equivalence classes produce the declared cone-angle inventory;
- a square-torus trajectory agrees with the exact flat-torus oracle;
- every simulated transition records source edge, target edge, local coordinate,
  direction, and accumulated arclength;
- a closed orbit returns within declared position and direction tolerances;
- a singular hit is separated from ordinary closure and finite-horizon truncation;
- identical inputs produce byte-stable canonical JSON after volatile metadata is removed.

No gallery image or qualitative orbit plot substitutes for these checks.
