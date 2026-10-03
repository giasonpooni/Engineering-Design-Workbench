"""Reproducible guest builds: descriptor -> BuildRecipe -> deterministic ELF.

Stage 5 closes the boundary Stage 4 falsified: "this ELF implements
descriptor X" was a registration -- a declaration no verifier could
check. This module replaces the declaration's AUTHORITY (not its
existence) with a checkable relation:

    descriptor + pinned source closure + pinned toolchain + pinned flags
        = BuildRecipe            (content-addressed)
        -> staged, manifest-verified build at a canonical path
        -> deterministic ELF     (content-addressed)

EMPIRICAL BASIS (this environment, recorded in
docs/STE_STAGE5_REPRODUCIBLE_BUILDS.md): guest builds are NOT naturally
reproducible. Two nondeterminism sources were found and controlled:

  1. absolute source paths embedded as panic-location strings
       -> --remap-path-prefix <staging-root>=/src and <cargo-home>=/cargo
  2. cargo's -C metadata fingerprint bakes path-dependency package ids
     (absolute paths) into symbol disambiguators; on the Nexus target
     this reorders the .text layout itself
       -> -C strip=symbols (the zkVMs load segments, never symbol
          tables) AND building from a CANONICAL STAGING PATH, so the
          path that reaches cargo is a pure function of the recipe

Staging is also what makes the manifest REAL: the build copies exactly
the files the recipe declares -- an undeclared stray source file cannot
influence the artifact, because it is never staged.

WHAT A MATCHING REBUILD ESTABLISHES: the ELF is the deterministic
product of the declared inputs. WHAT REMAINS DECLARED, precisely:
  - that the declared source SEMANTICALLY implements the descriptor's
    mathematics (now pinned to exact reviewable source, but reviewed by
    humans, not proven);
  - the toolchain BINARY matches its recorded identity (rustc -vV
    version/commit/host -- a verifier trusts its own toolchain
    provisioning);
  - the proof-system fork's source, referenced by git commit (a content
    hash -- independently checkable by anyone with the fork, but not
    re-hashed file-by-file here).

Identity discipline: a BuildRecipe/BuildArtifact identity contains NO
wall-clock, hostname, PID, or occurrence -- two builds of one recipe
converge; two different artifacts cannot (SHA-256 collision aside).
Build identities never touch ExecutionSpecification, ExecutionResult,
OperationTrace or VerifiedExecution identities: the registry CONNECTS a
program identity to an artifact identity; it does not merge them.
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from execution.commitments import canonical

_REPO = pathlib.Path(__file__).resolve().parent.parent
RECIPE_TAG = "scout.execution.build-recipe.v1"
#: Canonical staging root. Part of the recipe CONVENTION (the path cargo
#: sees must be a pure function of the recipe), hence a constant, not a
#: tempdir.
STAGING_ROOT = pathlib.Path("/tmp/ste-stage")

#: The flag sets, with {STAGE} and {CARGO_HOME} resolved at build time
#: against the canonical staging path -- so the resolved flags are
#: themselves recipe-determined.
SP1_RUSTFLAGS = (
    "-C", "passes=lower-atomic",
    "-C", "link-arg=--image-base=2013265920",
    "-C", "panic=abort",
    "--cfg", 'getrandom_backend="custom"',
    "-C", "llvm-args=-misched-prera-direction=bottomup",
    "-C", "llvm-args=-misched-postra-direction=bottomup",
    "--remap-path-prefix", "{STAGE}=/src",
    "--remap-path-prefix", "{CARGO_HOME}=/cargo",
    "-C", "strip=symbols",
)
R0_RUSTFLAGS = (
    "-C", "passes=lower-atomic",
    "-C", "link-arg=-Ttext=0x00200800",
    "-C", "link-arg=--fatal-warnings",
    "-C", "panic=abort",
    "--cfg", 'getrandom_backend="custom"',
    "--remap-path-prefix", "{STAGE}=/src",
    "--remap-path-prefix", "{CARGO_HOME}=/cargo",
    "-C", "strip=symbols",
)
NEXUS_RUSTFLAGS = (
    "-C", "relocation-model=pic",
    "-C", "link-arg=-T{STAGE}/Scout-Retrieval-Agent/{GUEST}/nexus-linker.x",
    "-C", "panic=abort",
    "--remap-path-prefix", "{STAGE}=/src",
    "--remap-path-prefix", "{CARGO_HOME}=/cargo",
    "-C", "strip=symbols",
)

_BACKENDS = {
    "sp1": {
        "rustflags": SP1_RUSTFLAGS,
        "target": "riscv64im-succinct-zkvm-elf",
        "toolchain": "succinct",
        "fork": "SP1-zero-knowledge-virtual-machine",
    },
    "nexus": {
        "rustflags": NEXUS_RUSTFLAGS,
        "target": "riscv32im-unknown-none-elf",
        "toolchain": "nightly-2025-05-09",
        "fork": "nexus-zkvm",
    },
    # Stage 6: the third backend fit the existing model without any
    # structural extension -- a flag set, a target, a toolchain, a fork.
    "risc0": {
        "rustflags": R0_RUSTFLAGS,
        "target": "riscv32im-risc0-zkvm-elf",
        "toolchain": "risc0",
        "fork": "risc0-zero",
    },
}

#: The repo-relative source closure every guest build depends on, beyond
#: the guest crate itself: the whole crates/ workspace (the guest's path
#: dependencies and their workspace root).
_CRATES_DIR = "crates"


class BuildRefused(RuntimeError):
    """The live tree does not match the recipe, the fork commit is
    wrong, or the toolchain identity differs -- the build is refused
    BEFORE producing an artifact that would carry a false pedigree."""


class BuildMismatch(RuntimeError):
    """An independent rebuild produced a different artifact identity
    than the one claimed."""


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iter_source_files(root: pathlib.Path, base: pathlib.Path):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        parts = path.relative_to(base).parts
        if "target" in parts or "__pycache__" in parts:
            continue
        yield path


def toolchain_identity(toolchain: str) -> str:
    """`rustc -vV` for the pinned toolchain, reduced to the lines that
    identify the compiler (release, commit-hash, host). No dates beyond
    what the compiler itself embeds in its identity."""
    proc = subprocess.run(
        ["rustc", "-vV"], env={**__import__("os").environ, "RUSTUP_TOOLCHAIN": toolchain},
        capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        raise BuildRefused(f"toolchain {toolchain!r} is not available: {proc.stderr.decode()!r}")
    keep = ("release:", "commit-hash:", "host:")
    lines = [l for l in proc.stdout.decode().splitlines() if l.startswith(keep)]
    return "; ".join(lines)


def fork_commit(fork_name: str, repo_root: pathlib.Path = _REPO) -> str:
    fork = repo_root.parent / "notationsystems" / fork_name
    proc = subprocess.run(["git", "-C", str(fork), "rev-parse", "HEAD"],
                          capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise BuildRefused(f"cannot resolve fork commit for {fork_name}: {proc.stderr.decode()!r}")
    return proc.stdout.decode().strip()


@dataclass(frozen=True)
class GuestBuildRecipe:
    """Everything that determines the guest ELF, content-addressed.

    Contains NO timestamps, hostnames, PIDs, occurrences -- artifact
    identity, not execution identity."""

    descriptor: bytes
    backend: str
    guest_crate: str                    # repo-relative, e.g. "zk/guest-heat"
    target: str
    toolchain: str
    toolchain_id: str                   # rustc -vV identity lines
    rustflags: tuple                    # with {STAGE}/{CARGO_HOME}/{GUEST} placeholders
    profile: str
    fork_name: str
    fork_commit: str
    source_manifest: tuple              # sorted ((relpath, sha256), ...)

    def canonical_bytes(self) -> bytes:
        head = "\n".join([
            "ste-build-recipe v1",
            f"backend {self.backend}",
            f"guest_crate {self.guest_crate}",
            f"target {self.target}",
            f"toolchain {self.toolchain}",
            f"toolchain_id {self.toolchain_id}",
            f"rustflags {' '.join(self.rustflags)}",
            f"profile {self.profile}",
            f"fork {self.fork_name} {self.fork_commit}",
            "[descriptor]",
        ]).encode()
        manifest = "\n".join(f"{p} {h}" for p, h in self.source_manifest).encode()
        return canonical(RECIPE_TAG, [head, self.descriptor, manifest])

    def identity(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class BuildArtifact:
    """The product of one reproducible build: which recipe, which bytes."""

    recipe_identity: str
    elf_sha256: str
    elf_path: str


def make_recipe(
    descriptor: bytes, backend: str, guest_crate: str,
    repo_root: pathlib.Path = _REPO,
) -> GuestBuildRecipe:
    """Collect the recipe from the LIVE tree: manifest every source file
    the build closure declares (guest crate + the crates/ workspace)."""
    spec = _BACKENDS[backend]
    manifest = []
    for rel_root in (guest_crate, _CRATES_DIR):
        root = repo_root / rel_root
        if not root.exists():
            raise BuildRefused(f"source root missing: {root}")
        for path in _iter_source_files(root, repo_root):
            manifest.append((str(path.relative_to(repo_root)), _sha256_file(path)))
    return GuestBuildRecipe(
        descriptor=descriptor, backend=backend, guest_crate=guest_crate,
        target=spec["target"], toolchain=spec["toolchain"],
        toolchain_id=toolchain_identity(spec["toolchain"]),
        rustflags=spec["rustflags"], profile="release",
        fork_name=spec["fork"], fork_commit=fork_commit(spec["fork"], repo_root),
        source_manifest=tuple(sorted(manifest)),
    )


def _stage(recipe: GuestBuildRecipe, repo_root: pathlib.Path) -> pathlib.Path:
    """Copy EXACTLY the manifest's files to the canonical staging path,
    verifying each hash; link the fork tree beside them; refuse on any
    divergence from the recipe."""
    stage = STAGING_ROOT / f"{recipe.backend}-{recipe.identity()[:16]}"
    if stage.exists():
        shutil.rmtree(stage)
    stage_repo = stage / "Scout-Retrieval-Agent"
    for rel, expected in recipe.source_manifest:
        src = repo_root / rel
        if not src.exists():
            raise BuildRefused(f"manifest file missing from live tree: {rel}")
        actual = _sha256_file(src)
        if actual != expected:
            raise BuildRefused(
                f"live tree diverges from recipe at {rel}: {actual} != {expected}"
            )
        dst = stage_repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    actual_fork = fork_commit(recipe.fork_name, repo_root)
    if actual_fork != recipe.fork_commit:
        raise BuildRefused(
            f"fork {recipe.fork_name} is at {actual_fork}, recipe pins {recipe.fork_commit}"
        )
    forks = stage / "notationsystems"
    forks.mkdir(parents=True, exist_ok=True)
    link = forks / recipe.fork_name
    if not link.exists():
        link.symlink_to(repo_root.parent / "notationsystems" / recipe.fork_name)
    return stage


def build_from_recipe(
    recipe: GuestBuildRecipe, repo_root: pathlib.Path = _REPO,
    out_path: Optional[pathlib.Path] = None,
) -> BuildArtifact:
    """Stage, build, hash. Deterministic: the staging path, flags,
    toolchain and sources are all functions of the recipe."""
    import os

    actual_toolchain = toolchain_identity(recipe.toolchain)
    if actual_toolchain != recipe.toolchain_id:
        raise BuildRefused(
            f"toolchain identity differs: {actual_toolchain!r} != {recipe.toolchain_id!r}"
        )
    stage = _stage(recipe, repo_root)
    guest_dir = stage / "Scout-Retrieval-Agent" / recipe.guest_crate
    cargo_home = os.environ.get("CARGO_HOME", str(pathlib.Path.home() / ".cargo"))
    flags = [
        f.replace("{STAGE}", str(stage))
        .replace("{CARGO_HOME}", cargo_home)
        .replace("{GUEST}", recipe.guest_crate)
        for f in recipe.rustflags
    ]
    target_dir = stage / "build-target"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    proc = subprocess.run(
        ["cargo", "build", f"--{recipe.profile}", "--target", recipe.target,
         "--target-dir", str(target_dir), "--locked"],
        cwd=guest_dir,
        env={**os.environ, "RUSTUP_TOOLCHAIN": recipe.toolchain,
             "CARGO_ENCODED_RUSTFLAGS": "\x1f".join(flags)},
        capture_output=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise BuildRefused(f"cargo build failed: {proc.stderr.decode(errors='replace')[-800:]}")
    crate_name = pathlib.Path(recipe.guest_crate).name.replace("guest", "ste-guest", 1) \
        if not pathlib.Path(recipe.guest_crate).name.startswith("ste-") else pathlib.Path(recipe.guest_crate).name
    elf = target_dir / recipe.target / recipe.profile / crate_name
    if not elf.exists():
        # Fall back: exactly one executable file in the profile dir.
        candidates = [p for p in (target_dir / recipe.target / recipe.profile).iterdir()
                      if p.is_file() and p.suffix == "" and p.stat().st_mode & 0o111]
        if len(candidates) != 1:
            raise BuildRefused(f"cannot locate built ELF; candidates: {candidates}")
        elf = candidates[0]
    sha = _sha256_file(elf)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(elf, out_path)
        elf = out_path
    return BuildArtifact(recipe_identity=recipe.identity(), elf_sha256=sha, elf_path=str(elf))


def verify_build(
    recipe: GuestBuildRecipe, expected_elf_sha256: str,
    repo_root: pathlib.Path = _REPO,
) -> BuildArtifact:
    """The independent-rebuild check: rebuild from the recipe and refuse
    on any divergence. THIS, not the registry, is the root of trust."""
    artifact = build_from_recipe(recipe, repo_root=repo_root)
    if artifact.elf_sha256 != expected_elf_sha256:
        raise BuildMismatch(
            f"rebuilt ELF is {artifact.elf_sha256}, claimed {expected_elf_sha256}"
        )
    return artifact


# ---------------------------------------------------------------------
# Recipe persistence: the canonical bytes ARE the stored format.
# ---------------------------------------------------------------------

def save_recipe(recipe: GuestBuildRecipe, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(recipe.canonical_bytes())


def load_recipe(path: pathlib.Path) -> GuestBuildRecipe:
    """Parse a stored recipe back into a live object (the inverse of
    `canonical_bytes`, and pinned equal by a round-trip test)."""
    import struct

    raw = path.read_bytes()

    def read_field(buf, at):
        (n,) = struct.unpack_from("<Q", buf, at)
        return buf[at + 8: at + 8 + n], at + 8 + n

    (tag_len,) = struct.unpack_from("<Q", raw, 0)
    at = 8 + tag_len
    if raw[8:at] != RECIPE_TAG.encode():
        raise BuildRefused(f"not a build recipe: tag {raw[8:at]!r}")
    (count,) = struct.unpack_from("<Q", raw, at)
    at += 8
    fields = []
    for _ in range(count):
        field, at = read_field(raw, at)
        fields.append(field)
    head, descriptor, manifest = fields
    meta = {}
    for line in head.decode().splitlines()[1:]:
        if line == "[descriptor]":
            break
        key, _, value = line.partition(" ")
        meta[key] = value
    fork_name, _, fork_c = meta["fork"].partition(" ")
    return GuestBuildRecipe(
        descriptor=descriptor, backend=meta["backend"], guest_crate=meta["guest_crate"],
        target=meta["target"], toolchain=meta["toolchain"], toolchain_id=meta["toolchain_id"],
        rustflags=tuple(meta["rustflags"].split(" ")), profile=meta["profile"],
        fork_name=fork_name, fork_commit=fork_c,
        source_manifest=tuple(
            tuple(line.rsplit(" ", 1)) for line in manifest.decode().splitlines() if line
        ),
    )


# ---------------------------------------------------------------------
# The four registered guests, and the registry generator.
# ---------------------------------------------------------------------

def registered_guest_builds():
    from execution.specification import (
        HEAT_DIFFUSION_DESCRIPTOR,
        PAIRWISE_ENERGY_DESCRIPTOR,
    )

    return [
        (PAIRWISE_ENERGY_DESCRIPTOR, "sp1", "zk/guest-pairwise", "sp1-pairwise"),
        (PAIRWISE_ENERGY_DESCRIPTOR, "nexus", "zk/guest-pairwise-nexus", "nexus-pairwise"),
        (HEAT_DIFFUSION_DESCRIPTOR, "sp1", "zk/guest-heat", "sp1-heat"),
        (HEAT_DIFFUSION_DESCRIPTOR, "nexus", "zk/guest-heat-nexus", "nexus-heat"),
        (HEAT_DIFFUSION_DESCRIPTOR, "risc0", "zk/guest-heat-risc0", "risc0-heat"),
    ]


def pending_guest_builds():
    """Return guest recipes that are implemented but not yet registered.

    The affine guest is deliberately kept out of ``registered_guest_builds``
    until its pinned SP1 checkout and toolchain produce an independently
    verified ELF.  Returning it here gives CI and a developer an executable
    build gate without fabricating a recipe identity or ELF hash in the
    generated registry.
    """
    from execution.affine import AFFINE_DESCRIPTOR

    return [(AFFINE_DESCRIPTOR, "sp1", "zk/guest-affine", "sp1-affine")]


def affine_build_gate(repo_root: pathlib.Path = _REPO) -> GuestBuildRecipe:
    """Resolve the pending affine recipe or fail with the exact blocker.

    This function does not write a registry entry.  Once the external SP1
    checkout/toolchain is provisioned, callers can pass the returned recipe
    to ``build_from_recipe`` and review the resulting source-closure and ELF
    identities before registration.
    """
    descriptor, backend, guest_crate, _ = pending_guest_builds()[0]
    try:
        return make_recipe(descriptor, backend, guest_crate, repo_root)
    except BuildRefused as error:
        raise BuildRefused(f"affine SP1 build gate unavailable: {error}") from error


def rebuild_all_and_write_registry(repo_root: pathlib.Path = _REPO) -> dict:
    """Build every registered guest reproducibly, store recipes under
    zk/recipes/, artifacts under zk/artifacts/, and regenerate
    execution/guest_registry.py. The generated registry is an INDEX; the
    authority remains `verify_build` over the stored recipes."""
    from execution.commitments import PROGRAM_TAG, commit_hex

    entries = {}
    for descriptor, backend, guest_crate, name in registered_guest_builds():
        recipe = make_recipe(descriptor, backend, guest_crate, repo_root)
        save_recipe(recipe, repo_root / "zk" / "recipes" / f"{name}.recipe")
        artifact = build_from_recipe(
            recipe, repo_root, out_path=repo_root / "zk" / "artifacts" / f"{name}.elf"
        )
        program_id = commit_hex(PROGRAM_TAG, [descriptor])
        entries.setdefault(program_id, {})[backend] = {
            "recipe": f"zk/recipes/{name}.recipe",
            "recipe_identity": artifact.recipe_identity,
            "elf_sha256": artifact.elf_sha256,
            "elf_path": f"zk/artifacts/{name}.elf",
        }
    body = [
        '"""GENERATED by `python3 -m execution.build` -- do not edit by hand.',
        "",
        "An INDEX from program identity to reproducible-build artifacts.",
        "It is NOT the root of trust: every entry names its recipe file,",
        "and `execution.build.verify_build(load_recipe(...), elf_sha256)`",
        "re-derives the artifact identity from source. A verifier who",
        "distrusts this file rebuilds and compares.",
        '"""',
        "",
        f"GUESTS = {entries!r}",
        "",
    ]
    (repo_root / "execution" / "guest_registry.py").write_text("\n".join(body))
    return entries


if __name__ == "__main__":
    for program, backends in rebuild_all_and_write_registry().items():
        for backend, entry in backends.items():
            print(f"{program[:16]} {backend:6} recipe={entry['recipe_identity'][:16]} "
                  f"elf={entry['elf_sha256'][:16]}")
