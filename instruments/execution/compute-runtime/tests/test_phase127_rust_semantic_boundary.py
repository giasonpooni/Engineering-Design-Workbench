"""Phase 127 -- forward guards on the Rust execution semantic boundary.

The Rust substrate's own semantics are tested in Rust
(`crates/execution-core/tests/semantics.rs`, 30 tests). These are the
ARCHITECTURAL guards: they protect the shape of the boundary from
erosion, and they run in the Python suite so that a change to the Rust
layer cannot land without the repository's own test run noticing.

Every guard here works on EXTRACTED STRUCTURE -- function signatures
with comments and string literals removed, struct field lists, Cargo
dependency tables -- never on raw substring matching. That is not
fastidiousness: `crates/execution-verification/src/lib.rs` contains the
literal text `fn verify(proof, expectation) -> bool` inside its module
documentation, as the thing it argues AGAINST. A substring guard would
fire on the very sentence explaining why the guard exists. Roughly
eight lock tests in earlier phases had to be rewritten for exactly this
class of false positive.

What is guarded, and why each matters (Phase 126 §6, §10):

  verify(...) -> bool          would return an identical `true` for a
                               backend that checked the input and one
                               that did not
  Result<(), Error>            carries the same single bit
  backend serialization        SP1 bincode / RISC Zero words / Nexus
                               postcard+COBS are three incompatible
                               encodings; none may become ours
  verification/types.py        a Python verification model would compete
                               with the Rust one for authority
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
CRATES = REPO / "crates"

#: Crate names the substrate is made of. A new crate must be added here
#: deliberately, which is itself a small guard against the workspace
#: growing a backend by accident.
SUBSTRATE_CRATES = (
    "execution-serialization",
    "execution-commitment",
    "execution-kernel",       # added STE stage 2: the workload math, no_std, shared with the SP1 guest
    "execution-model",
    "execution-trace",
    "execution-native",       # added Phase 129: the native backend + engine
    "execution-cli",          # added STE stage 1: the cross-process boundary binary
    "execution-verification",
    "execution-core",
)


# ---------------------------------------------------------------------
# Structural extraction from Rust source
# ---------------------------------------------------------------------

def _strip_rust_noise(source: str) -> str:
    """Remove comments and string literals.

    Doc comments are where the arguments live, and the arguments quote
    the exact constructs being banned. Signatures are what is being
    guarded, so signatures are what survives this."""
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", " ", source)
    # An escape may be backslash-newline (a multi-line literal with
    # continuations), so the escape class must span lines: `.` alone
    # missed it and let literal contents leak into the "code" text.
    source = re.sub(r'"(?:[^"\\]|\\[\s\S])*"', '""', source)
    return source


def _rust_sources() -> list[pathlib.Path]:
    files = sorted(path for crate in SUBSTRATE_CRATES
                   for path in (CRATES / crate).rglob("*.rs"))
    assert files, "expected the Rust substrate to exist under crates/"
    return files


def _fn_signatures(source: str) -> list[tuple[str, str]]:
    """Every `fn NAME(..) -> TYPE`, as (name, return type).

    Functions with no `->` return unit and are not of interest to any
    guard here, so they are simply not extracted."""
    pattern = re.compile(
        r"\bfn\s+(\w+)\s*(?:<[^>]*>)?\s*\((?:[^()]|\([^()]*\))*\)\s*->\s*([^{;]+)"
    )
    return [(m.group(1), " ".join(m.group(2).split())) for m in pattern.finditer(source)]


def _struct_fields(source: str, struct_name: str) -> list[str]:
    """The `pub NAME:` fields declared in `struct_name`'s body."""
    match = re.search(r"\bstruct\s+" + re.escape(struct_name) + r"\s*\{", source)
    assert match, f"struct {struct_name} not found"
    depth, start = 0, match.end() - 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body = source[start + 1 : index]
                break
    else:  # pragma: no cover -- unbalanced braces would not compile
        raise AssertionError(f"unbalanced braces in {struct_name}")
    return re.findall(r"\bpub\s+(\w+)\s*:", body)


# ---------------------------------------------------------------------
# Guard: verification is never Boolean
# ---------------------------------------------------------------------

def test_no_verification_function_returns_bool():
    """`verify(...) -> bool` must never become the canonical API.

    Phase 126 §6: SP1 does not commit to its input at all, RISC Zero's
    input digest is host-declared and must be zero, Nexus binds the
    input. A boolean collapses those three into one indistinguishable
    `true`, and the caller is entitled to believe the strongest reading.
    That is Phase 111's failure mode reintroduced by the abstraction."""
    offenders: list[str] = []
    for path in _rust_sources():
        source = _strip_rust_noise(path.read_text(encoding="utf-8-sig"))
        for name, return_type in _fn_signatures(source):
            if name.startswith("verify") and return_type.strip() == "bool":
                offenders.append(f"{path.relative_to(REPO)}: fn {name} -> {return_type}")
    assert not offenders, (
        "a verification function returns bool, collapsing coverage into one bit:\n"
        + "\n".join(offenders)
    )


def test_no_verification_function_returns_bare_result_unit():
    """`Result<(), Error>` carries exactly the same single bit as a bool.

    It is how all three substrates' own verifiers report -- RISC Zero's
    `Result<(), VerificationError>`, SP1's `Result<(), SP1VerificationError>`,
    Nexus's `Result<(), Error>` -- and adopting it here would import
    their shape rather than establishing ours."""
    offenders: list[str] = []
    for path in _rust_sources():
        source = _strip_rust_noise(path.read_text(encoding="utf-8-sig"))
        for name, return_type in _fn_signatures(source):
            if not name.startswith("verify"):
                continue
            if re.match(r"Result\s*<\s*\(\s*\)", return_type):
                offenders.append(f"{path.relative_to(REPO)}: fn {name} -> {return_type}")
    assert not offenders, (
        "a verification function returns Result<(), _>, which carries one bit:\n"
        + "\n".join(offenders)
    )


def test_the_proof_backend_entry_point_returns_a_verification_result():
    """Stated positively, so the guard fails if the trait is gutted
    rather than only if it is replaced.

    Since Phase 129 (per the Phase 128 review), `verify_supported`
    returns an AdapterVerdict rather than a VerificationResult: probe 1
    showed an adapter that constructs the final result can detach the
    warrant from its statement, and probe 2 showed it can inflate
    coverage. Result assembly is the sealed entry point's job now, so
    the adapter-facing method returning `VerificationResult` again would
    reopen both holes."""
    source = _strip_rust_noise(
        (CRATES / "execution-verification" / "src" / "lib.rs").read_text()
    )
    returns = dict(_fn_signatures(source))
    assert returns.get("verify") == "VerificationResult", (
        f"ProofBackend::verify returns {returns.get('verify')!r}, not VerificationResult"
    )
    assert returns.get("verify_supported") == "AdapterVerdict", (
        "the backend-implemented check must return an AdapterVerdict -- the sealed "
        "entry point, not the adapter, assembles the VerificationResult"
    )


def test_verification_coverage_keeps_its_four_explicit_fields():
    """The four facts stay four facts.

    Reducing them -- to a count, a level, a score, or a bool -- would
    make `input_checked: false` unrepresentable, which is the one thing
    Phase 126 proved must stay representable."""
    source = _strip_rust_noise(
        (CRATES / "execution-verification" / "src" / "lib.rs").read_text()
    )
    fields = _struct_fields(source, "VerificationCoverage")
    assert fields == [
        "program_checked",
        "input_checked",
        "output_checked",
        "exit_code_checked",
    ], f"VerificationCoverage's fields changed: {fields}"


def test_coverage_is_never_convertible_to_a_single_verdict():
    """No `impl From<VerificationCoverage> for bool`, and no method that
    reduces coverage to one boolean verdict. Either would restore the
    collapse the type exists to prevent."""
    source = _strip_rust_noise(
        (CRATES / "execution-verification" / "src" / "lib.rs").read_text()
    )
    assert not re.search(r"impl\s+From\s*<\s*VerificationCoverage\s*>\s+for\s+bool", source)
    forbidden = {"is_complete", "is_verified", "is_ok", "succeeded", "passed"}
    declared = {name for name, _ in _fn_signatures(source)}
    assert not (declared & forbidden), (
        f"coverage grew a single-verdict accessor: {sorted(declared & forbidden)}"
    )


def test_the_three_verification_outcomes_all_exist():
    """VERIFIED / FAILED / UNSUPPORTED. `Unsupported` is the variant that
    stops an uncheckable requirement from becoming a success by
    omission; losing it would not break compilation of anything that
    only matches on the other two."""
    source = _strip_rust_noise(
        (CRATES / "execution-verification" / "src" / "lib.rs").read_text()
    )
    match = re.search(r"\benum\s+VerificationResult\s*\{(.*?)\n\}", source, flags=re.DOTALL)
    assert match, "VerificationResult enum not found"
    variants = set(re.findall(r"^\s{4}(\w+)\s*[{,(]", match.group(1), flags=re.MULTILINE))
    assert {"Verified", "Failed", "Unsupported"} <= variants, (
        f"VerificationResult lost an outcome; found {sorted(variants)}"
    )


# ---------------------------------------------------------------------
# Guard: no backend's serialization can become ours
# ---------------------------------------------------------------------

def test_the_substrate_has_no_external_dependencies():
    """The strongest available guard against a backend's serialization
    becoming canonical: nothing external can be reached at all.

    Phase 126 §4 found three mutually incompatible encodings -- RISC
    Zero's word-oriented serde, SP1's bincode, Nexus's postcard+COBS.
    An empty dependency table means none of them, nor `serde`, nor
    `borsh`, can silently become the canonical form. It also keeps
    `ProgramIdentity` from depending on which version of a crate
    computed it."""
    offenders: list[str] = []
    for crate in SUBSTRATE_CRATES:
        manifest = (CRATES / crate / "Cargo.toml").read_text()
        section = manifest.split("[dependencies]", 1)
        assert len(section) == 2, f"{crate} has no [dependencies] section"
        for line in section[1].splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            if 'path = "../execution-' not in line:
                offenders.append(f"{crate}: {line}")
    assert not offenders, (
        "the substrate gained a dependency that is not another substrate crate:\n"
        + "\n".join(offenders)
    )


def test_no_backend_is_named_in_the_substrate():
    """Phase 127 is backend-neutral by construction. SP1, Nexus and
    RISC Zero may be DISCUSSED (the reasoning is why the shapes are what
    they are) but may not be imported, depended on, or referenced by any
    identifier."""
    backend_paths = ("sp1", "nexus", "risc0", "risc_zero", "bincode", "postcard", "borsh", "serde")
    offenders: list[str] = []
    for path in _rust_sources():
        source = _strip_rust_noise(path.read_text(encoding="utf-8-sig"))
        for match in re.finditer(r"\buse\s+([\w:]+)", source):
            root = match.group(1).split("::", 1)[0].lower()
            if root in backend_paths:
                offenders.append(f"{path.relative_to(REPO)}: use {match.group(1)}")
        for match in re.finditer(r"\bextern\s+crate\s+(\w+)", source):
            if match.group(1).lower() in backend_paths:
                offenders.append(f"{path.relative_to(REPO)}: extern crate {match.group(1)}")
    assert not offenders, "a backend crate reached the substrate:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------
# Guard: Python must not define a competing verification model
# ---------------------------------------------------------------------

def test_python_defines_no_competing_verification_model():
    """The Rust layer is the authoritative semantic boundary for
    execution. A Python `VerificationCoverage` or `Expectation` would be
    a second authority, and two authorities on the same semantics is how
    they drift apart.

    AST-based: a name in a docstring is prose, and prose is allowed --
    it is a definition that is not."""
    reserved = {
        "VerificationCoverage",
        "VerificationResult",
        "VerifiedExecution",
        "ProofBackend",
        "ProofIdentity",
        "ProgramIdentity",
        "InputIdentity",
        "OutputIdentity",
        "ExecutionOccurrence",
    }
    offenders: list[str] = []
    for path in sorted(REPO.rglob("*.py")):
        if any(part in {".venv", "__pycache__", "tests"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in reserved:
                offenders.append(f"{path.relative_to(REPO)}: {node.name}")
    assert not offenders, (
        "Python defined a type the Rust substrate is authoritative for:\n" + "\n".join(offenders)
    )


def test_no_python_verification_package_reappeared():
    """Restated from Phase 126, because Phase 127 is exactly the phase
    where the temptation to add one returns: the Rust types now exist,
    and mirroring them in Python would feel like integration. It would
    be a second model with no backend behind it."""
    assert not (REPO / "verification").exists()
    assert not (REPO / "verification" / "types.py").exists()


# ---------------------------------------------------------------------
# Guard: what this phase deliberately did not build
# ---------------------------------------------------------------------

def test_frozen_substrate_and_explicit_outer_host_have_separate_ownership():
    """The explicit outer provider host is a separate std workspace; frozen crates
    and their zero-dependency guards remain unchanged. Historical Phase 129: `execution-native` is the one
    deliberate addition (a backend that proves nothing and says so). An
    sp1/nexus/risc0 adapter crate appearing here still means the
    boundary was crossed without the phase that was supposed to cross
    it."""
    present = {p.name for p in CRATES.iterdir() if p.is_dir() and p.name != "target"}
    assert present == set(SUBSTRATE_CRATES) | {"execution-provider-host"}, (
        f"the workspace gained or lost a crate: {sorted(present)}"
    )


def test_the_substrate_does_not_reach_into_the_python_architecture():
    """No EvidencePool, no CanonicalState, no persistence, no
    orchestration. The substrate knows nothing about what will use it,
    which is what lets it be attached to later without renegotiating its
    semantics."""
    forbidden = ("evidencepool", "evidence_pool", "canonicalstate", "canonical_state", "scout", "graphrag")
    offenders: list[str] = []
    for path in _rust_sources():
        source = _strip_rust_noise(path.read_text(encoding="utf-8-sig")).lower()
        for term in forbidden:
            # `scout` appears in the domain tags ("scout.execution.*"),
            # which are string literals -- already stripped above.
            if re.search(r"\b" + term + r"\b", source):
                offenders.append(f"{path.relative_to(REPO)}: {term}")
    assert not offenders, (
        "the substrate referenced the Python architecture:\n" + "\n".join(offenders)
    )
