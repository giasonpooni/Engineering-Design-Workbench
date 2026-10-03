"""STE Stage 5 -- the reproducible-build substrate, audited live.

The boundary being closed: stage 4 proved a falsely REGISTERED
ELF<->descriptor binding verifies. Stage 5 makes the binding checkable:

    descriptor + source closure + toolchain + flags = BuildRecipe
        -> manifest-verified staged build at a canonical path
        -> deterministic ELF identity
        -> the proving driver refuses any ELF that is not the
           registered reproducible artifact -- and the registration
           itself is re-derivable by rebuild (verify_build).

Tests that build actually build (Nexus-target builds, ~20s each, chosen
over SP1's ~40s where either would do). Real-proof tests are in the
E2E section, gated on artifacts.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import shutil

import pytest

from execution.build import (
    BuildMismatch,
    BuildRefused,
    build_from_recipe,
    load_recipe,
    make_recipe,
    save_recipe,
    verify_build,
)
from execution.specification import HEAT_DIFFUSION_DESCRIPTOR

REPO = pathlib.Path(__file__).resolve().parent.parent
RECIPES = REPO / "zk" / "recipes"
ARTIFACTS = REPO / "zk" / "artifacts"

pytestmark = pytest.mark.skipif(
    not (RECIPES / "nexus-heat.recipe").exists() or not ARTIFACTS.exists(),
    reason="recipes/artifacts not generated (python3 -m execution.build); environment gap",
)


def _registry():
    from execution.guest_registry import GUESTS

    return GUESTS


# -- identity: cheap, exhaustive over the recipe's dimensions ----------------------------------------


def test_recipe_roundtrip_and_identity_stability():
    recipe = load_recipe(RECIPES / "nexus-heat.recipe")
    fresh = make_recipe(HEAT_DIFFUSION_DESCRIPTOR, "nexus", "zk/guest-heat-nexus")
    assert recipe.identity() == fresh.identity(), (
        "the stored recipe and a freshly collected one agree -- the live tree "
        "has not drifted from what the registry was generated from"
    )
    # round-trip through persistence is identity-preserving
    tmp = pathlib.Path("/tmp/ste-recipe-roundtrip.recipe")
    save_recipe(fresh, tmp)
    assert load_recipe(tmp).identity() == fresh.identity()


def test_recipe_identity_is_sensitive_to_every_declared_dimension():
    base = load_recipe(RECIPES / "nexus-heat.recipe")
    variants = {
        "descriptor": dataclasses.replace(base, descriptor=b"other descriptor"),
        "toolchain": dataclasses.replace(base, toolchain_id=base.toolchain_id + "; patched"),
        "flags": dataclasses.replace(base, rustflags=base.rustflags + ("-C", "opt-level=2")),
        "fork": dataclasses.replace(base, fork_commit="0" * 40),
        "source": dataclasses.replace(
            base,
            source_manifest=(
                (base.source_manifest[0][0], "0" * 64),
            ) + base.source_manifest[1:],
        ),
    }
    identities = {name: v.identity() for name, v in variants.items()}
    identities["base"] = base.identity()
    assert len(set(identities.values())) == len(identities), identities


def test_registry_artifacts_match_their_recorded_identities():
    for program, backends in _registry().items():
        for backend, entry in backends.items():
            elf = REPO / entry["elf_path"]
            assert elf.exists(), f"{entry['elf_path']} missing"
            assert hashlib.sha256(elf.read_bytes()).hexdigest() == entry["elf_sha256"], (
                f"{entry['elf_path']} does not match the registry -- rebuild via "
                f"python3 -m execution.build"
            )
            recipe = load_recipe(REPO / entry["recipe"])
            assert recipe.identity() == entry["recipe_identity"]


# -- real rebuilds: reproducibility and the independent check ----------------------------------------


def test_independent_rebuild_reproduces_the_registered_artifact():
    """The third-party path: from the STORED recipe alone (no trust in
    the registration process), rebuild and converge on the registered
    identity. This is the stage's root-of-trust operation."""
    recipe = load_recipe(RECIPES / "nexus-heat.recipe")
    expected = _registry()[
        __import__("execution.commitments", fromlist=["commit_hex"]).commit_hex(
            "scout.execution.program.v1", [recipe.descriptor]
        )
    ]["nexus"]["elf_sha256"]
    artifact = verify_build(recipe, expected)
    assert artifact.elf_sha256 == expected


def test_a_false_artifact_claim_is_caught_by_rebuild():
    recipe = load_recipe(RECIPES / "nexus-heat.recipe")
    with pytest.raises(BuildMismatch):
        verify_build(recipe, "0" * 64)


def test_modified_kernel_changes_recipe_and_artifact_and_breaks_attribution(tmp_path):
    """Alter one relevant build input (the kernel source): the recipe
    identity changes, the rebuilt ELF identity changes, the old artifact
    cannot be attributed to the modified build, and a stored recipe
    refuses to build from the tampered tree at the staging step."""
    # A relocated copy of the build closure, with the fork linked beside it.
    root = tmp_path / "repo"
    (root / "zk").mkdir(parents=True)
    shutil.copytree(REPO / "crates", root / "crates",
                    ignore=shutil.ignore_patterns("target"))
    shutil.copytree(REPO / "zk" / "guest-heat-nexus", root / "zk" / "guest-heat-nexus",
                    ignore=shutil.ignore_patterns("target"))
    (tmp_path / "notationsystems").symlink_to(REPO.parent / "notationsystems")

    # Stored recipe vs tampered tree: staging refuses before building.
    kernel = root / "crates" / "execution-kernel" / "src" / "lib.rs"
    kernel.write_text(kernel.read_text().replace(
        "const HEAT_VALUE_BOUND: i64 = 1 << 40;",
        "const HEAT_VALUE_BOUND: i64 = 1 << 39;",
    ))
    stored = load_recipe(RECIPES / "nexus-heat.recipe")
    with pytest.raises(BuildRefused, match="diverges from recipe"):
        build_from_recipe(stored, repo_root=root)

    # A recipe honestly collected from the tampered tree: different
    # identity, different artifact, and the OLD identity is not
    # attributable to it.
    modified = make_recipe(HEAT_DIFFUSION_DESCRIPTOR, "nexus", "zk/guest-heat-nexus", root)
    assert modified.identity() != stored.identity()
    old_sha = _registry()[
        __import__("execution.commitments", fromlist=["commit_hex"]).commit_hex(
            "scout.execution.program.v1", [HEAT_DIFFUSION_DESCRIPTOR]
        )
    ]["nexus"]["elf_sha256"]
    artifact = build_from_recipe(modified, repo_root=root)
    assert artifact.elf_sha256 != old_sha, "a changed kernel is a changed executable"
    with pytest.raises(BuildMismatch):
        verify_build(modified, old_sha, repo_root=root)


# -- the driver gate ---------------------------------------------------------------------------------


def test_proving_driver_refuses_non_registered_artifacts():
    from execution.proving import ProvedRunError, _require_registered_artifact
    from execution.specification import ExecutionSpecification, encode_heat_input

    spec = ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(10, [0, 1, 2, 3, 4, 0])
    )
    # the registered artifact passes; the pairwise artifact -- a real,
    # honestly built ELF, just not THIS program's -- is refused by identity
    _require_registered_artifact(spec, ARTIFACTS / "sp1-heat.elf")
    with pytest.raises(ProvedRunError, match="not the reproducible-build artifact"):
        _require_registered_artifact(spec, ARTIFACTS / "sp1-pairwise.elf")
