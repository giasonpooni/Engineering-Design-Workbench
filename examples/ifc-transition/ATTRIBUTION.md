# Original public IFC sample

`buildingSMART-wall-opening-window.ifc` is the unchanged original
`wall-with-opening-and-window.ifc` from buildingSMART's Sample-Test-Files repository.

- Author/source: buildingSMART International / Sample-Test-Files.
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
- Source repository: <https://github.com/buildingSMART/Sample-Test-Files>.
- Source revision: `e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7`.
- Source path: `IFC 4.0.2.1 (IFC 4)/ISO Spec - ReferenceView_V1.2/wall-with-opening-and-window.ifc`.
- Original bytes: 12,492.
- SHA-256: `73b0e45d931d5dc13bfee5fdc7bd80f796526445458b2de74c4168d209097832`.
- Modifications: none; only the local filename differs.

The file is a public IFC reference example. It is not authenticated as-built
industrial evidence. The native CSE audit parses its 127 instances and finds
that required `ClearHeight`, `Length`, `Width` and other declared quantities are
missing. Tests preserve the complete bytes and the resulting refused transition
without supplying missing dimensions or admitting a world. Any accompanying
observation declaration is a synthetic negative-path stimulus.
