"""Phase 126 -- Rust Execution Substrate Reconnaissance: forward guards.

Reconnaissance phase. No production code was written or changed. What
IS lockable today is the boundary the reconnaissance says a future Rust
substrate must not cross, and the two facts about the Python side that
must stay true while it is built.

The reconnaissance itself lives in `docs/RUST_EXECUTION_SUBSTRATE_RECON.md`,
read from RISC Zero `3bbcd44`, SP1 `b38b612` and Nexus `f2ad126`. Its
three load-bearing findings:

  1. SP1 does not commit to its input at all (`SP1Stdin` is never
     hashed and never reaches `verify_proof`).
  2. RISC Zero's `ReceiptClaim.input` is structurally inert -- `Input`
     is an uninhabited type, and the only value that can reach the field
     is a HOST-DECLARED `input_digest` which the standard
     `Receipt::verify` path requires to be zero.
  3. Nexus alone binds the input, via `verify_expected(...)`
     reconstructing the whole execution `View`.

Therefore a shared `verify(...) -> bool` would return an identical
`true` for a backend that checked the input and one that did not --
the caller cannot tell them apart and would be entitled to believe the
stronger claim in both. That is Phase 111's failure mode (an unwarranted
claim entering through a gate that looks like it checked) reintroduced
BY THE ABSTRACTION. Coverage must be reported, never collapsed.

These tests do not test the forks -- the forks are not part of this
repository and must never become a dependency of it. They test that the
Python architecture stays where the reconnaissance left it.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The layers a proof/verification concept must not reach. `operations/`
#: is included deliberately: Phase 124 built it importing stdlib only,
#: and a Rust bridge is exactly the kind of thing that would erode that.
PRODUCTION_LAYERS = ("evidence", "retrieval", "materials", "experiment", "core", "operations")

#: Vocabulary that would signal a verification claim having leaked into
#: a layer that cannot substantiate one. Matched against IDENTIFIERS
#: ONLY (never prose): every previous phase that matched substrings
#: against source text produced a false positive off a docstring.
PROOF_VOCABULARY = frozenset({
    "verified", "is_verified", "proof", "proven", "receipt", "zkvm",
    "image_id", "vkey", "vkey_hash", "journal", "public_values",
    "verification_key", "proof_backend", "verified_execution",
})


def _identifiers(path: pathlib.Path) -> set[str]:
    """Every NAME a module actually binds or references -- never its prose."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            found.add(node.name.split(".")[0])
            if node.asname:
                found.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def _production_modules() -> list[pathlib.Path]:
    modules: list[pathlib.Path] = []
    for layer in PRODUCTION_LAYERS:
        modules.extend(sorted((REPO / layer).rglob("*.py")))
    assert modules, "expected production modules to exist"
    return modules


def test_no_proof_vocabulary_in_production_layers():
    """A layer that cannot check a proof must not name one.

    Nothing below `workbench/` has any means of verifying an execution,
    and the reconnaissance found that even the substrates themselves
    disagree about what verification covers. A `verified` field here
    would be a declaration, exactly like Phase 119's
    `extraction_method`, and Phase 119 proved a declaration is not a
    witness."""
    offenders: list[str] = []
    for module in _production_modules():
        leaked = _identifiers(module) & PROOF_VOCABULARY
        if leaked:
            offenders.append(f"{module.relative_to(REPO)}: {sorted(leaked)}")
    assert not offenders, (
        "proof/verification vocabulary reached a layer that cannot substantiate it:\n"
        + "\n".join(offenders)
    )


def test_operations_trace_still_imports_only_stdlib():
    """The operation ledger stays free of the execution substrate.

    Phase 124 built `operations/trace.py` on stdlib alone. A Rust
    bridge, an FFI module, or a proof type imported here would make the
    ledger depend on whether a prover was available -- and an occurrence
    that only exists when a prover is installed is not a record of what
    happened."""
    tree = ast.parse((REPO / "operations" / "trace.py").read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import is a package-local import
                roots.add("operations")
            elif node.module:
                roots.add(node.module.split(".")[0])
    local = {p.name for p in REPO.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    assert not (roots & local), f"operations/trace.py grew a repo-local import: {sorted(roots & local)}"


def test_no_python_verification_package_exists():
    """Phase 126 replaced 'write `verification/types.py`' with
    'map the substrate first'. The Python package drafted before that
    redirect is not part of this repository, and a `VerifiedExecution`
    must not reappear in Python ahead of a substrate that can produce
    one. A certificate type with nothing behind it is a fabricated
    warrant with a type annotation."""
    assert not (REPO / "verification").exists(), (
        "a Python `verification/` package exists; the reconnaissance concluded that "
        "the verification layer belongs in the Rust substrate, and that no verification "
        "type may exist before a backend that can actually produce one"
    )


def test_forks_are_not_a_dependency_of_this_repository():
    """Reconnaissance read three forks. It must not have attached them.

    The substrates are version-bound (SP1 hard-fails on version
    mismatch; RISC Zero binds verifier parameters; Nexus embeds the
    memory layout). A repository that imports them inherits that
    binding into every test run."""
    substrate_roots = frozenset({"risc0_zkvm", "sp1_sdk", "sp1_zkvm", "nexus_sdk", "nexus_rt"})
    offenders: list[str] = []
    for module in _production_modules():
        leaked = _identifiers(module) & substrate_roots
        if leaked:
            offenders.append(f"{module.relative_to(REPO)}: {sorted(leaked)}")
    assert not offenders, "a zkVM substrate became an import of this repository:\n" + "\n".join(offenders)


def test_reconnaissance_record_is_present_and_names_its_revisions():
    """A reconnaissance whose revisions are not recorded cannot be
    re-run against the same code. All three findings are properties of
    specific commits, not of the projects in general -- RISC Zero's
    `Input` type says so itself ('may become inhabited in a future
    release')."""
    doc = (REPO / "docs" / "RUST_EXECUTION_SUBSTRATE_RECON.md").read_text()
    for revision in ("3bbcd44", "b38b612", "f2ad126"):
        assert revision in doc, f"reconnaissance does not record revision {revision}"
