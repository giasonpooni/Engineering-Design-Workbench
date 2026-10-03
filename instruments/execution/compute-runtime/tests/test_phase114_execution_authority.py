"""Phase 114: computational workflow / execution authority audit.

Comparative control: AiiDAlab (4,579 LOC), cloned and read.

sec.1 THE CONTROL SUPPLIES NEITHER WORKFLOW NOR PROVENANCE
-----------------------------------------------------------
AiiDAlab was proposed as a workflow/execution control. It is not one.
Grepped over its whole source: `workflow` 0 hits, `calculation` 0,
`provenance` 0, `WorkChain` 0, `CalcJob` 0, `node` 0. It does not import
aiida-core at all, and its 36 `process` hits are `subprocess`.

Its actual primitives are: `AiidaLabApp(traitlets.HasTraits)` -- mutable
and observable -- with `install`/`uninstall`, `AppVersion`,
`AppRemoteUpdateStatus`, `GitManagedAppRepo`, `Release`, `Metadata`, and
`Environment(python_requirements)`. AiiDAlab is a GIT-BACKED APPLICATION
LIFECYCLE MANAGER for notebook apps. Provenance in that ecosystem lives
in aiida-core, which is a different repository.

So the honest comparison table is mostly FALSE ANALOGY, and the control
is informative for exactly one section: sec.12, lifecycle.

sec.7 COMPARISON

  concept              AiiDAlab                  here              equivalence
  application          AiidaLabApp, mutable      --                FALSE ANALOGY
  registry             AppRegistryData           --                FALSE ANALOGY
  workflow             ABSENT                    ABSENT            n/a
  execution            ABSENT (subprocess only)  ActionDispatcher  FALSE ANALOGY
  environment          Environment(reqs)         --                FALSE ANALOGY
  provenance           ABSENT                    the Phase 113 DAG FALSE ANALOGY
  result               ABSENT                    ExperimentalResult FALSE ANALOGY
  observation          ABSENT                    Observation       FALSE ANALOGY
  installation         install/uninstall         --                FALSE ANALOGY
  lifecycle            create/modify/delete      create-only       PARTIAL, and
        the difference is the finding: see sec.12
  user interaction     traitlets/ipywidgets      workbench CLI     PARTIAL

sec.3/sec.19 THE EXECUTION CHAIN IS COMPLETE, AND ITS MIDDLE IS A SEAM
------------------------------------------------------------------------
    declaration        ResearchScenario / Criterion          EXISTS
    executable action  ActionCandidate                       EXISTS
    execution          ActionDispatcher.dispatch  [Protocol] SPECIFIED,
                                                             UNIMPLEMENTED
    result             DispatchedMeasurement -> ExperimentalResult EXISTS
    observation        admit_experimental_result             EXISTS

Every link exists. The execution link is a `Protocol` -- "the ONE and
only place a physical experiment would actually be performed" -- and its
own docstring states that no implementation shipped anywhere in this
codebase, present or future, is a live lab-automation integration. So
execution semantics are PARTIAL BY DESIGN: the boundary is fully
specified and deliberately empty.

sec.19's minimal tuple is therefore already present:
    (ActionCandidate, ActionDispatcher, ExperimentalCampaign entry)
        -> DispatchedMeasurement -> ExperimentalResult
and `DispatchedMeasurement` is documented as PRE-IDENTITY, PRE-POOL --
acquisition's job is acquisition, not identity assignment.

sec.4 WHAT ActionCandidate IS
------------------------------
An IDENTITY FOR A POSSIBLE EXPERIMENT. Not a planned action, not an
execution request, not a result. Its id hashes `action_class` and
`requirement_ids` -- the evidence epoch -- so two candidates are the same
candidate when they answer the same requirements from the same evidence.
It carries no code, no command, no executable, no schedule and no status.

sec.5 WHAT observe(...) IS
---------------------------
(B) AN OBSERVATION-ADMISSION WRAPPER, and nothing else. It builds a
Record from a caller-supplied value, calls `admit_record`/`put_record`,
then `admit_experimental_result`, then `update`. It dispatches nothing
and executes nothing: the VALUE IS AN ARGUMENT. The workbench is a
transcription instrument, not an execution engine.

sec.6 THE FOUR AUTHORITIES
---------------------------
  epistemic authority       DOES NOT EXIST (Phase 105)
  computational authority   EXISTS, trivially -- `predict` is a fixed
                            pure function; nothing chooses it
  execution authority       SPECIFIED AND EMPTY -- `ActionDispatcher` is
                            the only thing that could act, and no
                            implementation exists
  organizational authority  DOES NOT EXIST -- no actor model anywhere

A policy can do exactly one thing: mark candidates eligible or selected.
It cannot execute code (it takes no callable), mutate evidence (it takes
no pool), modify ModelState (it names no state), admit observations, or
generate candidates. `select_candidates(evaluations, policy)` -- two
arguments, neither of them the world.

sec.8 WORKFLOW IS NOT PROVENANCE, AND ONLY ONE IS PRESENT
-----------------------------------------------------------
    WORKFLOW    A -> B -> C   "execute B after A"      ABSENT
    PROVENANCE  C -> B -> A   "C was computed from B"  PRESENT

`run_experiment_step` is a SEQUENCER, not a workflow: a straight-line
function whose ten steps are fixed in source order. There is no
dependency declaration, no scheduler, no ordering object, and no way to
express an alternative order. So the ambiguity sec.8 warns about cannot
arise here -- not because it is prevented, but because one side of it
does not exist.

sec.10/sec.11 EXECUTION IDENTITY DOES NOT EXIST
------------------------------------------------
Nothing records an executable identity, a code version, an environment,
a runtime configuration or an execution time. `DispatchedMeasurement`
carries content, a locator, raw content and a caller-supplied
`extracted_at` -- a TRANSCRIPTION TIMESTAMP, not an execution duration.

Two executions with the same inputs, the same code and different
environments would be INDISTINGUISHABLE, because neither environment is
represented. Workflow definition, workflow execution and workflow result
are not collapsed here: two of the three do not exist, and the third
(result) is `ExperimentalResult`, identified by its campaign, candidate,
content and record.

sec.12 LIFECYCLE MEANS SOMETHING DIFFERENT HERE
------------------------------------------------
AiiDAlab: create -> modify -> delete, on a mutable `HasTraits` object
with an `install`/`uninstall` pair.

Here: CREATE -> SUPERSEDE BY ADDITION. Every scientific object is frozen
and the pool is append-only, so "retire" has no representation and
"delete" is not expressible. A scenario is not uninstalled; a different
scenario is bootstrapped, and the old evidence remains.

sec.17/sec.18 THE CRITICAL DISTINCTION, AND WHY EXECUTION WOULD NOT FIX
PHASE 111
------------------------------------------------------------------------
Execution authority is not epistemic authority, and the code already
enforces the first half: a policy selects, a dispatcher acts, and neither
touches admission.

But sec.18's question has a sharp answer: A GENUINE EXECUTION LAYER WOULD
NOT SOLVE THE PHASE 111 ATTACK. `DispatchedMeasurement` is pre-identity
and pre-pool, and `run_experiment_step` turns whatever the dispatcher
returned into a `Record` whose `raw_content` is that value. A dishonest
dispatcher is Phase 111's attack with a `Protocol` in front of it.
Execution produces a RESULT, never a WARRANT -- and per Phase 111b the
warrant cannot be produced from inside at all.

sec.20 THE EIGHT TARGETS

  1 execution is distinct from evidence          SURVIVES -- and the
        distinction is a type boundary: DispatchedMeasurement has no id
  2 workflow is distinct from provenance         SURVIVES VACUOUSLY --
        no workflow exists
  3 policy is distinct from execution authority  SURVIVES -- a policy
        takes no callable and no pool
  4 computational result != observation          SURVIVES for objects;
        FALSIFIED for values (Phase 111)
  5 an app registry is not the evidence ontology SURVIVES -- FALSE ANALOGY
        throughout
  6 execution identity != evidence identity      SURVIVES VACUOUSLY --
        execution identity does not exist
  7 reproducibility needs more than hashing the
    result                                       SURVIVES -- identical
        outputs can arise from different computations
  8 an agent needs an execution boundary as well
    as a policy boundary                         SURVIVES -- and the
        execution boundary is the seam that is specified and empty

sec.20 VERDICT: EXECUTION SEMANTICS ARE PARTIALLY PRESENT. The boundary
is completely specified (`ActionDispatcher`, `DispatchedMeasurement`,
`run_experiment_step`) and deliberately unimplemented. What is genuinely
absent is EXECUTION IDENTITY -- and it is absent for the same reason
model identity was in Phase 112b: nothing varies that would need
identifying, because nothing executes.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from experiment.interface import ActionDispatcher, DispatchedMeasurement
from experiment.policy import ExperimentPolicy
from experiment.step import run_experiment_step
from materials.candidates import ActionCandidate
from materials.optimization import OptimizationPolicy
from materials.ranking import RankingPolicy
from materials.results import ExperimentalResult
from materials.selection import SelectionPolicy, select_candidates
from workbench import theme
from workbench.interaction import WorkbenchState

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- 3/19. the execution chain, and its empty middle -------------------------------------------------


def test_the_execution_seam_is_a_protocol_with_one_method():
    assert hasattr(ActionDispatcher, "dispatch")
    methods = [m for m in vars(ActionDispatcher) if not m.startswith("_")]
    assert methods == ["dispatch"]
    text = " ".join((REPO / "experiment" / "interface.py").read_text().split())
    assert "the one and only place a physical experiment would actually be performed" in text
    assert "No implementation shipped anywhere in this codebase" in text


def test_no_dispatcher_implementation_ships_in_production():
    implementations = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
                    if "ActionDispatcher" in bases:
                        implementations.append(f"{path.relative_to(REPO)}: {node.name}")
    assert implementations == []


def test_the_dispatched_measurement_is_pre_identity_and_pre_pool():
    fields = {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert fields == {"content", "record_locator", "record_raw_content",
                      "extracted_at", "extraction_method"}
    assert "id" not in fields
    # `extraction_method` is the dispatcher's OWN declaration of what it
    # did -- the string `classify_epistemic_status` later reads by prefix.
    # A simulation dispatcher would declare "simulation:...". Per Phase
    # 111b that is a self-report, never a warrant.
    text = " ".join((REPO / "experiment" / "interface.py").read_text().split())
    assert "pre-identity, pre-pool" in text


# -- 4. what ActionCandidate is ----------------------------------------------------------------------


def test_action_candidate_is_an_identity_for_a_possible_experiment():
    fields = {f.name for f in dataclasses.fields(ActionCandidate)}
    assert fields == {"id", "action_class", "requirement_ids", "formulation",
                      "property", "role", "target_context", "existing_evidence_ids"}
    for absent in ("command", "executable", "code", "status", "scheduled_at", "result"):
        assert absent not in fields
    from materials.candidates import _candidate_identity
    source = inspect.getsource(_candidate_identity)
    assert '"action_class": action_class' in source
    assert '"requirement_ids": sorted(requirement_ids)' in source


# -- 5. what observe() is ----------------------------------------------------------------------------


def test_observe_is_an_admission_wrapper_and_takes_the_value_as_an_argument():
    parameters = list(inspect.signature(WorkbenchState.observe).parameters)
    assert parameters == ["self", "value", "unit"]
    source = inspect.getsource(WorkbenchState.observe)
    assert "admit_record" in source or "put_record" in source
    assert "admit_experimental_result" in source
    # It dispatches nothing: no ActionDispatcher, no subprocess, no call out.
    for absent in ("dispatch", "subprocess", "Popen", "system("):
        assert absent not in source


# -- 6. the four authorities -------------------------------------------------------------------------


@pytest.mark.parametrize("policy", [SelectionPolicy, OptimizationPolicy, RankingPolicy])
def test_a_policy_holds_no_callable_and_no_pool(policy):
    for field in dataclasses.fields(policy):
        annotation = str(field.type)
        assert "Callable" not in annotation
        assert "Pool" not in annotation


def test_the_one_policy_that_holds_a_callable_holds_a_pure_transform():
    """`ExperimentPolicy.utility_input_source` is the exception, and it
    maps one dataclass to another -- it cannot reach the world."""
    annotations = {f.name: str(f.type) for f in dataclasses.fields(ExperimentPolicy)}
    assert annotations["utility_input_source"] == (
        "Callable[[InformationValueEstimate], ExperimentUtilityInput]")


def test_selection_takes_two_arguments_and_neither_is_the_world():
    assert set(inspect.signature(select_candidates).parameters) == {"evaluations", "policy"}


def test_no_actor_or_organizational_authority_exists():
    forbidden = {"actor", "user_id", "owner_id", "role_rank", "permission", "principal"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


# -- 8. sequencer, not workflow -----------------------------------------------------------------------


def test_run_experiment_step_is_a_straight_line_sequencer():
    """Ten steps fixed in source order. No dependency declaration, no
    scheduler, no ordering object."""
    source = inspect.getsource(run_experiment_step)
    tree = ast.parse(source.lstrip())
    function = tree.body[0]
    assert not any(isinstance(n, (ast.While, ast.AsyncFor)) for n in ast.walk(function))
    text = " ".join((REPO / "experiment" / "step.py").read_text().split())
    assert "the one place `experiment/` actually calls things in order" in text


def test_no_workflow_or_scheduling_vocabulary_exists():
    forbidden = {"Workflow", "WorkChain", "Task", "Scheduler", "DependencyGraph",
                 "Job", "Queue", "Pipeline"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


# -- 10/11. execution identity does not exist ---------------------------------------------------------


def test_nothing_records_an_executable_version_or_environment():
    forbidden = {"code_version", "executable", "environment", "hardware",
                 "runtime", "hostname", "git_sha", "exec_time"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    for stmt in node.body:
                        if (isinstance(stmt, ast.AnnAssign)
                                and isinstance(stmt.target, ast.Name)
                                and stmt.target.id in forbidden):
                            hits.append(f"{path.relative_to(REPO)}: {node.name}.{stmt.target.id}")
    assert hits == [], hits


def test_extracted_at_is_a_transcription_timestamp_not_a_duration():
    fields = {f.name for f in dataclasses.fields(ExperimentalResult)}
    assert "extracted_at" in fields
    assert "duration" not in fields and "started_at" not in fields
    text = " ".join((REPO / "experiment" / "interface.py").read_text().split())
    assert "never defaulted to a wall-clock read" in text


# -- 12. lifecycle means create then supersede by addition --------------------------------------------


def test_nothing_can_be_deleted_or_retired():
    pool_methods = [m for m in dir(__import__("evidence.pool", fromlist=["EvidencePool"]).EvidencePool)
                    if not m.startswith("_")]
    for absent in ("delete", "remove", "retire", "uninstall", "drop"):
        assert not any(absent in m for m in pool_methods), (absent, pool_methods)


# -- 18. execution would not fix Phase 111 -------------------------------------------------------------


def test_a_dishonest_dispatcher_is_the_phase_111_attack_with_a_protocol():
    """`run_experiment_step` writes whatever the dispatcher returned into
    a Record's raw_content. Execution produces a RESULT, never a
    WARRANT."""
    source = inspect.getsource(run_experiment_step)
    assert "record_raw_content" in source
    assert "dispatch" in source
    # Nothing between them checks anything about the value.
    assert "verify" not in source and "witness" not in source


# -- 20. nothing was added -----------------------------------------------------------------------------


def test_phase_114_added_no_workflow_machinery():
    forbidden = (
        "aiidalab", "AiidaLabApp", "AppRegistry", "install_app", "uninstall_app",
        "WorkflowGraph", "ExecutionAuthority", "ExecutionIdentity",
    )
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
