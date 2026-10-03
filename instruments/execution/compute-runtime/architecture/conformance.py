"""Conformance gates: the executable checks between canonical
architecture and everything that claims to follow it.

Four gates, all fail-closed:

  check_vertical_contract   a vertical.yaml carries the full contract
                            and pins the current core version -- an
                            unconformant vertical must not be wired
  check_core_closure        no architecture artifact silently extends a
                            different core version than the declaration's
                            -- every artifact except emitted projections,
                            which bind no core because they may span
                            repositories that bind different ones
  lint_doctrine_vendor_free vendor identities never appear in doctrine
                            (generated or otherwise)
  check_doctrine_current    regenerating doctrine from canonical
                            sources reproduces the committed output
                            byte-for-byte; a non-zero diff fails

There is no CI workflow infrastructure in this repository (inspected
2026-08-25: no .github/); the test suite is the gate, and these
functions are what the tests -- and any future CI -- call.
"""

from __future__ import annotations

import pathlib
from typing import List

import yaml

ROOT = pathlib.Path(__file__).resolve().parent

REQUIRED_CONTRACT_KEYS = (
    "extends", "vertical", "extensions", "observation_types",
    "admissibility_class", "instrument_adapters", "retraction_policy",
)

#: Vendor tokens that must never appear in doctrine. Bindings and
#: adapters are where these live; doctrine expresses constraints only.
VENDOR_TOKENS = ("anthropic", "openai", "mistral", "claude", "gpt-", "sonnet", "opus")


class ConformanceError(ValueError):
    """A gate failure: the artifact must not be wired/accepted."""


def core_version() -> str:
    """The DECLARED core version. Read from architecture/core.yaml --
    never from packaging: a package version moves on any release, a
    core-schema version moves only under bend_protocol, and binding
    them would let a routine release renumber the core without a single
    invariant changing meaning."""
    declaration = yaml.safe_load((ROOT / "core.yaml").read_text())
    if declaration.get("referent", {}).get("derived_from_packaging") is not False:
        raise ConformanceError(
            "architecture/core.yaml must declare derived_from_packaging: false "
            "-- the core version is a declaration, not an inference")
    return f"{declaration['name']}@{declaration['version']}"


def check_vertical_contract(path: pathlib.Path) -> dict:
    """The vertical_contract gate. Returns the parsed contract, or
    refuses."""
    contract = yaml.safe_load(path.read_text())
    missing = [key for key in REQUIRED_CONTRACT_KEYS if key not in contract]
    if missing:
        raise ConformanceError(
            f"{path.name}: vertical contract is missing {missing}; an "
            f"unconformant vertical must not be wired"
        )
    expected = core_version()
    if contract["extends"] != expected:
        raise ConformanceError(
            f"{path.name}: extends {contract['extends']!r} but the core is "
            f"{expected!r}; re-run the vertical against the current core"
        )
    return contract


def check_core_closure() -> List[pathlib.Path]:
    """Every architecture artifact that declares `extends` pins the
    current core version -- a mismatch anywhere fails closed."""
    expected = core_version()
    checked = []
    for path in sorted(ROOT.rglob("*.yaml")):
        # invariants.yaml carries the registry; core.yaml IS the core
        # declaration. Neither binds a core -- a declaration cannot
        # extend itself, and demanding it would be the same category
        # error as demanding one from an emitted projection.
        if path.name in ("invariants.yaml", "core.yaml"):
            continue
        data = yaml.safe_load(path.read_text())
        # AN EMITTED PROJECTION IS NOT A THING THAT BINDS A CORE. The
        # derived register spans repositories that may bind different
        # ones, so stamping it with a single `extends` would assert
        # something false.
        #
        # This used to skip the whole `exchange/` directory, which is a
        # LOCATION standing in for the property. That protected exactly
        # one path: a hand-authored declaration filed there was skipped
        # for no reason, and an emitted projection filed anywhere else
        # was demanded to bind. The same substitution -- a directory
        # convention doing a provenance rule's job -- is what let the
        # register be re-read as its own source the moment the rule was
        # generalized in derive_register.py. So both now ask the same
        # question: does the document declare that something generated
        # it?
        if isinstance(data, dict) and data.get("generated_by"):
            continue
        declared = data.get("extends") if isinstance(data, dict) else None
        if declared is None:
            raise ConformanceError(f"{path} declares no `extends: core@<version>`")
        if declared != expected:
            raise ConformanceError(
                f"{path} extends {declared!r}; the core is {expected!r} -- a "
                f"core change requires re-running every declared vertical and probe"
            )
        checked.append(path)
    return checked


def lint_doctrine_vendor_free(text: str, where: str = "doctrine") -> None:
    """no_vendor_in_doctrine, mechanically."""
    lowered = text.lower()
    for token in VENDOR_TOKENS:
        if token in lowered:
            raise ConformanceError(
                f"{where}: vendor token {token!r} found -- vendor identities "
                f"belong in model_binding.yaml and adapters, never in doctrine"
            )


def check_doctrine_current() -> None:
    """generated_doctrine_matches_source: regenerate from canonical
    sources and require a byte-identical match with the committed
    projection. Manual edits to generated doctrine fail here."""
    from architecture.doctrine_generator import generate_doctrine

    generated = generate_doctrine()
    for name, content in generated.items():
        committed = ROOT / "generated" / "doctrine" / name
        if not committed.exists():
            raise ConformanceError(
                f"generated doctrine {name} is not committed; run the generator"
            )
        if committed.read_text() != content:
            raise ConformanceError(
                f"generated doctrine {name} differs from regeneration -- either "
                f"canonical sources changed without regenerating, or the "
                f"projection was edited by hand; both fail closed"
            )
    extras = {p.name for p in (ROOT / "generated" / "doctrine").glob("*.md")} - set(generated)
    if extras:
        raise ConformanceError(
            f"committed doctrine files with no canonical source: {sorted(extras)}"
        )
