# Use-case coverage report (executable layer)

Generated: `2026-09-27T21:14:49.346628+00:00`

## Catalog exhausted ≠ experiments exhausted

Catalog exhausted ≠ experiments exhausted. 9,074 application descriptions collapse to 10 unique computational profiles (operation + model/uncertainty + expected outcome class). Export/teaching emit was exercised for representatives; scientific execution, numerical regimes, independent checking, replay, and ESM-bound observations remain largely not_run, blocked, unavailable, or cite_only.

## Freeze

- Catalog dirs on disk: **9074** (freeze ≤ 9074; no folder 9075).
- Application description count: **9074**.
- Unique computational profiles: **10** (≪ 9074 because industry titles do not change the owned emitter config).
- No new CIW kinds; no false qualified/proved/calibrated; ESM cite-only.

## Layer counts (unique-profile representatives)

| Layer | Status histogram |
| --- | --- |
| `catalog` | pass=10 |
| `export` | pass=10 |
| `executable` | blocked=1, not_run=8, unavailable=1 |
| `numerical` | blocked=1, not_run=8, unavailable=1 |
| `checking` | pass=10 |
| `replay` | blocked=1, not_run=8, unavailable=1 |
| `ESM` | cite_only=10 |

## Verb → instrument family → operation mapping

| Verb | Family | Operation id | Model / regime | Input source | Scenario |
| --- | --- | --- | --- | --- | --- |
| `shift-check` | `FSRT` | `BLOCKED (HOST replay of published FSRT quickstart; does not mint ciw.fluid-volume.v1; no native set_lcm import)` | two-reservoir linear ConstraintSet; P=I HOST hard reconcile | HOST replay | compare a retained pair before the shift window closes :: reconcile-vs-hold on consistency_stat vs χ² threshold |
| `gate` | `CSE` | `ciw.bim-quantity.v1` | IFC/--demo quantity conditioning; geometry_authority=QUANTITY_ONLY | synthetic | screen a quantity teaching case before review :: ACCEPT / REQUEST_EVIDENCE / REJECT teaching gate |
| `path-sensitivity` | `CSG` | `ciw.curved-path-transfer.v1` | declared constant curvature; no surveyed BIM | synthetic | inspect a retained path and sensitivity strip :: path sensitivity / Jacobi strip inspection |
| `drift-watch` | `RESIDUAL_CUSUM` | `ciw.residual-monitor.v1` | ordered residual windows; OIT-held does not advance CUSUM | synthetic | review ordered residual windows without advancing held windows :: quiet / diagnostic-candidate / OIT-held strip |
| `proof-gate` | `PROVED_HEAT` | `ciw.proved-heat.v1` | bounded registered guest [0,100,200,100,0]→[0,65,92,65,0] | synthetic | present a retained proof-gated result without re-verifying it :: UNAVAILABLE when binaries absent; REFUSED on missing/corrupt proof |
| `circle-fit` | `GTE_CIRCLE` | `ciw.geometric-circle.v1` | declared frame bench-plane only | synthetic | review circle eligibility and held cases :: circle eligibility and radial residual screen |
| `stability-verdict` | `PLSR` | `ciw.identified-stability.v1` | identity certificate / level-set; parameter covariance unknown | HOST replay | review a retained stability verdict and level-set case :: NUMERICAL_INCONCLUSIVE / OUTSIDE_LEVEL_SET teaching |
| `energy-accuracy` | `ENERGY_ACCURACY` | `ciw.energy-accuracy.v1` | synthetic fixtures; free energy / joules / time kept separate | synthetic | compare retained energy-accuracy phases :: baseline-qualified and incomplete-bracket phases |
| `free-energy` | `VFE` | `ciw.variational-free-energy.v1` | synthetic constant-curvature / unmodelled generator bias | synthetic | review a retained free-energy sensor-bias teaching case :: free-energy numerics without physical calibration claim |
| `measurement-chain` | `MEASUREMENT_CHAIN` | `ciw.measurement-chain.v1` | HOST_SYNTHETIC stages; native results keep not_verified | synthetic | trace a retained measurement-chain receipt :: instrument-chain stage walk / chain audit |
| `inventory-balance` | `FSRT` | `BLOCKED (HOST replay of published FSRT quickstart; does not mint ciw.fluid-volume.v1; no native set_lcm import)` | two-reservoir linear ConstraintSet; P=I HOST hard reconcile | HOST replay | reconcile an inventory teaching pair :: reconcile-vs-hold on consistency_stat vs χ² threshold |
| `route-check` | `CSG` | `ciw.curved-path-transfer.v1` | declared constant curvature; no surveyed BIM | synthetic | compare a route sensitivity strip :: path sensitivity / Jacobi strip inspection |
| `quantity-review` | `CSE` | `ciw.bim-quantity.v1` | IFC/--demo quantity conditioning; geometry_authority=QUANTITY_ONLY | synthetic | review retained quantity cases :: ACCEPT / REQUEST_EVIDENCE / REJECT teaching gate |
| `residual-hold` | `RESIDUAL_CUSUM` | `ciw.residual-monitor.v1` | ordered residual windows; OIT-held does not advance CUSUM | synthetic | record a residual hold point :: quiet / diagnostic-candidate / OIT-held strip |
| `thermal-release` | `PROVED_HEAT` | `ciw.proved-heat.v1` | bounded registered guest [0,100,200,100,0]→[0,65,92,65,0] | synthetic | present a thermal teaching release state :: UNAVAILABLE when binaries absent; REFUSED on missing/corrupt proof |
| `radial-screen` | `GTE_CIRCLE` | `ciw.geometric-circle.v1` | declared frame bench-plane only | synthetic | screen retained radial residuals :: circle eligibility and radial residual screen |
| `contour-check` | `PLSR` | `ciw.identified-stability.v1` | identity certificate / level-set; parameter covariance unknown | HOST replay | compare a contour-level stability case :: NUMERICAL_INCONCLUSIVE / OUTSIDE_LEVEL_SET teaching |
| `phase-review` | `ENERGY_ACCURACY` | `ciw.energy-accuracy.v1` | synthetic fixtures; free energy / joules / time kept separate | synthetic | review a retained phase accuracy strip :: baseline-qualified and incomplete-bracket phases |
| `bias-review` | `VFE` | `ciw.variational-free-energy.v1` | synthetic constant-curvature / unmodelled generator bias | synthetic | review a sensor-bias teaching record :: free-energy numerics without physical calibration claim |
| `chain-audit` | `MEASUREMENT_CHAIN` | `ciw.measurement-chain.v1` | HOST_SYNTHETIC stages; native results keep not_verified | synthetic | walk the retained instrument-chain stages :: instrument-chain stage walk / chain audit |
| `reservoir-reconcile` | `FSRT` | `BLOCKED (HOST replay of published FSRT quickstart; does not mint ciw.fluid-volume.v1; no native set_lcm import)` | two-reservoir linear ConstraintSet; P=I HOST hard reconcile | HOST replay | compare two retained reservoir indications :: reconcile-vs-hold on consistency_stat vs χ² threshold |
| `jacobi-strip` | `CSG` | `ciw.curved-path-transfer.v1` | declared constant curvature; no surveyed BIM | synthetic | inspect the retained Jacobi sensitivity strip :: path sensitivity / Jacobi strip inspection |
| `evidence-screen` | `CSE` | `ciw.bim-quantity.v1` | IFC/--demo quantity conditioning; geometry_authority=QUANTITY_ONLY | synthetic | screen retained evidence-needed quantity cases :: ACCEPT / REQUEST_EVIDENCE / REJECT teaching gate |
| `verdict-review` | `PLSR` | `ciw.identified-stability.v1` | identity certificate / level-set; parameter covariance unknown | HOST replay | review a retained numerical verdict :: NUMERICAL_INCONCLUSIVE / OUTSIDE_LEVEL_SET teaching |

## Computational profiles (deduped)

See also [`computational_profiles.json`](computational_profiles.json). **10** profiles cover **9074** descriptions.

| Profile | Family | Operation | Members | Verbs | Input |
| --- | --- | --- | ---: | --- | --- |
| `9eccaafa8bc49a47` | `CSE` | `ciw.bim-quantity.v1` | 1138 | `evidence-screen`, `gate`, `quantity-review` | synthetic |
| `86c913a772e11a44` | `CSG` | `ciw.curved-path-transfer.v1` | 1144 | `jacobi-strip`, `path-sensitivity`, `route-check` | synthetic |
| `b0e89a20f6c8870e` | `ENERGY_ACCURACY` | `ciw.energy-accuracy.v1` | 752 | `energy-accuracy`, `phase-review` | synthetic |
| `255c3a6953b25b6b` | `FSRT` | `BLOCKED` | 1148 | `inventory-balance`, `reservoir-reconcile`, `shift-check` | HOST replay |
| `f3bf97b187d9d148` | `GTE_CIRCLE` | `ciw.geometric-circle.v1` | 752 | `circle-fit`, `radial-screen` | synthetic |
| `1ad6ec86bd1fcef8` | `MEASUREMENT_CHAIN` | `ciw.measurement-chain.v1` | 752 | `chain-audit`, `measurement-chain` | synthetic |
| `e53d1d4e38444add` | `PLSR` | `ciw.identified-stability.v1` | 1128 | `contour-check`, `stability-verdict`, `verdict-review` | HOST replay |
| `4e1754ccff604b3d` | `PROVED_HEAT` | `ciw.proved-heat.v1` | 755 | `proof-gate`, `thermal-release` | synthetic |
| `23e0f4100e7ba51e` | `RESIDUAL_CUSUM` | `ciw.residual-monitor.v1` | 753 | `drift-watch`, `residual-hold` | synthetic |
| `3a74d4435cc207f4` | `VFE` | `ciw.variational-free-energy.v1` | 752 | `bias-review`, `free-energy` | synthetic |

## Top incompatible / blocked reasons (useful gaps)

| Weight | Reason |
| ---: | --- |
| 9074 | ESM_real_artifact_bindings_absent_cite_only |
| 7926 | scientific_execution_requires_workbench_session_or_ICRH |
| 1148 | FSRT_ciw.fluid-volume.v1_not_minted |
| 1144 | native_session_ciw.curved-path-transfer.v1_not_invoked |
| 1138 | native_session_ciw.bim-quantity.v1_not_invoked |
| 1128 | native_session_ciw.identified-stability.v1_not_invoked |
| 755 | PROVED_HEAT_SP1_binaries_or_fresh_verify_unavailable |
| 753 | native_session_ciw.residual-monitor.v1_not_invoked |
| 752 | native_session_ciw.energy-accuracy.v1_not_invoked |
| 752 | native_session_ciw.geometric-circle.v1_not_invoked |
| 752 | native_session_ciw.measurement-chain.v1_not_invoked |
| 752 | native_session_ciw.variational-free-energy.v1_not_invoked |

## Representative run results

Commands below ran locally without private providers. SP1/proved-heat scientific execution marked unavailable/not_run when binaries unbound.

### CSE · unique_computational_config

- profile_id: `9eccaafa8bc49a47`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['CSE'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-CSE-vbj22xfc/cse_rep_render.json bytes=8611
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.bim-quantity.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### CSG · unique_computational_config

- profile_id: `86c913a772e11a44`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['CSG'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-CSG-o1fjose1/csg_rep_render.json bytes=7532
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.curved-path-transfer.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### ENERGY_ACCURACY · unique_computational_config

- profile_id: `b0e89a20f6c8870e`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['ENERGY_ACCURACY'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-ENERGY_ACCURACY-x40m30xe/energy_accuracy_rep_render.json bytes=9436
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.energy-accuracy.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### FSRT · unique_computational_config

- profile_id: `255c3a6953b25b6b`
- layers: `catalog=pass`, `export=pass`, `executable=blocked`, `numerical=blocked`, `checking=pass`, `replay=blocked`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['FSRT'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-FSRT-o7oai6mn/fsrt_rep_render.json bytes=6908
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `native_operation.execute ciw.fluid-volume.v1` → **blocked** (rc=None)
  - stderr: HOST replay of published FSRT quickstart; does not mint ciw.fluid-volume.v1; no native set_lcm import

### GTE_CIRCLE · unique_computational_config

- profile_id: `f3bf97b187d9d148`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['GTE_CIRCLE'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-GTE_CIRCLE-vnm5_gce/gte_circle_rep_render.json bytes=7607
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.geometric-circle.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### MEASUREMENT_CHAIN · unique_computational_config

- profile_id: `1ad6ec86bd1fcef8`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['MEASUREMENT_CHAIN'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-MEASUREMENT_CHAIN-hstwvl_6/measurement_chain_rep_render.json bytes=5537
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.measurement-chain.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### PLSR · unique_computational_config

- profile_id: `e53d1d4e38444add`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['PLSR'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-PLSR-x_23c4d6/plsr_rep_render.json bytes=9011
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.identified-stability.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### PROVED_HEAT · unique_computational_config

- profile_id: `4e1754ccff604b3d`
- layers: `catalog=pass`, `export=pass`, `executable=unavailable`, `numerical=unavailable`, `checking=pass`, `replay=unavailable`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['PROVED_HEAT'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-PROVED_HEAT-_f4iye6w/proved_heat_rep_render.json bytes=10554
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `scripts/check_proved_heat.py (not invoked — binaries/providers)` → **unavailable** (rc=None)
  - stdout: {"cargo": true, "rustc": true, "sp1_cli": false, "guest_elf_hits": [], "scientific_execution": "unavailable", "reason": "host_binaries_absent_or_unbound"}

### RESIDUAL_CUSUM · unique_computational_config

- profile_id: `23e0f4100e7ba51e`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['RESIDUAL_CUSUM'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-RESIDUAL_CUSUM-8t8esgr9/residual_cusum_rep_render.json bytes=10632
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.residual-monitor.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### VFE · unique_computational_config

- profile_id: `3a74d4435cc207f4`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c usecase_templates.EMIT_FUNCTIONS['VFE'](...)` → **pass** (rc=0)
  - stdout: wrote /tmp/cov-VFE-j4q17_4x/vfe_rep_render.json bytes=5881
- command: `python3 -c structural_checks(emitted_json)` → **pass** (rc=0)
  - stdout: checks_ok=True issues=[]
- command: `ciw operation.execute ciw.variational-free-energy.v1` → **not_run** (rc=None)
  - stdout: local teaching emit only; workbench session / ICRH not started

### PROVED_HEAT · boundary_refuse · binaries-absent UNAVAILABLE

- profile_id: `4e1754ccff604b3d`
- layers: `catalog=pass`, `export=pass`, `executable=unavailable`, `numerical=unavailable`, `checking=pass`, `replay=unavailable`, `ESM=cite_only`
- command: `python3 -c assert case_ids subset of PROVED_HEAT.build_payload()['cases']` → **pass** (rc=0)
  - stdout: present=['teaching-statement-binaries-absent'] missing=[]

### PROVED_HEAT · boundary_refuse · missing-proof REFUSED

- profile_id: `4e1754ccff604b3d`
- layers: `catalog=pass`, `export=pass`, `executable=unavailable`, `numerical=unavailable`, `checking=pass`, `replay=unavailable`, `ESM=cite_only`
- command: `python3 -c assert case_ids subset of PROVED_HEAT.build_payload()['cases']` → **pass** (rc=0)
  - stdout: present=['missing-guest-elf-pin-refused', 'missing-proof-refused', 'resealed-corrupt-refused'] missing=[]

### CSE · boundary_refuse · quantity REJECT / REQUEST_EVIDENCE

- profile_id: `9eccaafa8bc49a47`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c assert case_ids subset of CSE.build_payload()['cases']` → **pass** (rc=0)
  - stdout: present=['held-request-evidence', 'refused-violated'] missing=[]

### PLSR · boundary_refuse · OUTSIDE_LEVEL_SET / NUMERICAL_INCONCLUSIVE

- profile_id: `e53d1d4e38444add`
- layers: `catalog=pass`, `export=pass`, `executable=not_run`, `numerical=not_run`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c assert case_ids subset of PLSR.build_payload()['cases']` → **pass** (rc=0)
  - stdout: present=['identity-certificate-inconclusive', 'level-zero-outside'] missing=[]

### FSRT · boundary_refuse · large-disagreement HELD (operation BLOCKED for fluid-volume mint)

- profile_id: `255c3a6953b25b6b`
- layers: `catalog=pass`, `export=pass`, `executable=blocked`, `numerical=blocked`, `checking=pass`, `replay=not_run`, `ESM=cite_only`
- command: `python3 -c assert case_ids subset of FSRT.build_payload()['cases']` → **pass** (rc=0)
  - stdout: present=['large-disagreement-held'] missing=[]

### PROVED_HEAT · sp1_teaching_export

- profile_id: `4e1754ccff604b3d`
- layers: `catalog=pass`, `export=pass`, `executable=unavailable`, `numerical=unavailable`, `checking=not_run`, `replay=unavailable`, `ESM=cite_only`
- command: `/usr/bin/python3 /workspace/Parametric-Design-Terminal/examples/workflows/emit_sp1_teaching_bundle.py` → **pass** (rc=0)
  - stdout: orrupt-refused: card=REFUSED
  retained-historical-requires-fresh: card=HISTORICAL
ok examples/proved-heat/emit_proof_render.py
ok examples/usecase-thermal-proof-gate/emit_render.py
orchestrated=2 emitters=proved-heat,usecase-thermal-proof-gate operation=ciw.proved-heat.v1 fake_proofs=false layer_ex

## SP1 / proved-heat gate

- scientific_execution: **unavailable** (host_binaries_absent_or_unbound)
- cargo=True rustc=True sp1_cli=False
- guest_elf_hits: []
- Teaching export: `python3 examples/workflows/emit_sp1_teaching_bundle.py` → **pass**

## Machine-readable twin

- [`coverage_report.json`](coverage_report.json)
- [`computational_profiles.json`](computational_profiles.json)

## Non-claims

- Does not authorize operations (`may_authorize` false).
- Does not claim ESM verification or invent pins.
- Does not expand the industry×verb catalog.
- Export pass ≠ numerical / checking / replay / proved completeness.
