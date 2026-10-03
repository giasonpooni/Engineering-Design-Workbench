# Independently authored IFC inputs

These unmodified certification datasets are from buildingSMART International,
`buildingSMART/Certification-datasets`, commit
`80d976a9b193a26a8e928c3e79bff67af1de68a8`. They are CC BY 4.0;
see LICENSE.txt. They are external IFC data, not surveyed physical observations.

| Local file | Upstream path | Git blob | SHA256 |
|---|---|---|---|
| wall.ifc | IFC 4.0.2.1 (IFC 4 ADD2 TC1)/ISO Spec - ReferenceView_V1.2/wall-with-opening-and-window.ifc | 8820193e625f693712be860d79291a0ee48eacd7 | 73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832 |
| structural.ifc | IFC 4.0.2.1 (IFC 4 ADD2 TC1)/Simple-Scene/Building-Structural.ifc | 0a0fc46360cd713fb92cf424f134356dc868a103 | 903b5a005901397aa2b235daf6a60f46c099eae286cb01c815abf0a341707432 |

[Upstream repository](https://github.com/buildingSMART/Certification-datasets/tree/80d976a9b193a26a8e928c3e79bff67af1de68a8).
No source records were modified or silently supplied with invented quantities.

The unchanged architectural file is refused by native whole-file CSE lowering:
its storey lacks required ClearHeight. The structural beam's 3-D RefDirection
is also outside native placement support. Both are retained negative results.

The scoped positive experiment extracts the externally declared beam Length
from quantity #179 (2700 mm) on beam #175 / GlobalId
`0fqX614OH1YO1Njdxms2$Q`. It creates a **quantity-only** computation carrier in
metres. The original source bytes, geometry and placement chain remain retained;
the carrier has no original spatial authority. The synthetic observation is
2.69 m with variance 0.000025 m² and assumed independent noise. CSE's prior
variance is 0.000025 m²; the posterior is 2.695 m, variance 0.0000125 m².

This tests declared scalar extraction and preservation across native CSE
conditioning/export/reload. It does not implement a general solid-model adapter,
update the original mesh to match the posterior length, authenticate calibration,
or establish a lossless whole-BIM transformation.
