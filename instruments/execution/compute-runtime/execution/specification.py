"""ExecutionSpecification: the request to execute -- before any run.

WHAT PROPOSITION IT REPRESENTS: "run the program identified by these
canonical bytes, under this configuration, over this input." A request,
not an event: constructing one executes nothing, and its identity is a
content hash precisely because two identical requests ARE the same
request (asking twice is asking the same thing -- it is RUNNING twice
that must remain two, and that distinction belongs to the operation
ledgers, never to this type).

WHAT IT DOES NOT ESTABLISH: that the program bytes describe any real
behavior (that coupling is declared, not proven -- see
`native_program_identity_binds_bytes_not_behavior`), that the input was
measured, or that execution will be possible at all (the engine may
refuse: unknown program, unsupported configuration).

WHY THIS TYPE EXISTS NOW when the Phase 128 review rejected it: the
review rejected a specification identity FOR LACK OF A CONSUMER. The
consumer arrived with the cross-process boundary: a result coming back
from another process must name which request it answers, or it is the
detachable-warrant hazard (Phase 128 probe 1) at the process seam. The
reversal is recorded here and at `SPECIFICATION_TAG`'s definition in
`crates/execution-model`, not made silently.

IDENTITY: `commit(SPECIFICATION_TAG, [program, configuration, input])`.
Deliberately NOT part of it: any occurrence number, any timestamp, any
hostname, any engine version -- a request is the same request no matter
when, where, or how often it is made.
"""

from __future__ import annotations

from dataclasses import dataclass

from execution.commitments import (
    INPUT_TAG,
    PROGRAM_TAG,
    SPECIFICATION_TAG,
    commit_hex,
)

#: The reference workload's canonical descriptor -- byte-for-byte
#: `execution_native::reference::PAIRWISE_ENERGY_DESCRIPTOR`. The
#: round-trip test pins the agreement: if these bytes drift from the
#: Rust constant, the engine answers `unrunnable` and everything fails
#: loudly.
PAIRWISE_ENERGY_DESCRIPTOR = (
    b"scout.native.pairwise-energy-kernel.v1\n"
    b"input: N*12 bytes of (x,y,z) as i32 LE; |coord| <= 2^20\n"
    b"for i<j: r2=(dx^2+dy^2+dz^2) as i128; r2==0 faults;\n"
    b"e = 2^80/r2^2 - 2^40/r2 (integer division, truncation toward zero)\n"
    b"output: sum(e) as i128 LE (16 bytes); exit 0\n"
    b"faults: 2=malformed length, 3=coincident particles, 4=coordinate bound"
)


@dataclass(frozen=True)
class ExecutionSpecification:
    """See the module docstring -- it is this type's contract."""

    program: bytes
    configuration: bytes
    input_payload: bytes

    def identity(self) -> str:
        """The request's content identity (64 lowercase hex)."""
        return commit_hex(
            SPECIFICATION_TAG, [self.program, self.configuration, self.input_payload]
        )

    def program_identity(self) -> str:
        """Our commitment to the program bytes."""
        return commit_hex(PROGRAM_TAG, [self.program])

    def input_identity(self) -> str:
        """Our commitment to the input bytes.

        The canonicalization burden is the CALLER'S: this hashes the
        bytes it is given (Phase 128, probe 3). For the reference
        workload, `encode_positions` below is the one canonical
        encoding."""
        return commit_hex(INPUT_TAG, [self.input_payload])


#: The heat-diffusion kernel's canonical descriptor -- byte-for-byte
#: `execution_native::reference::HEAT_DIFFUSION_DESCRIPTOR` (stage 4's
#: second provable workload; the round-trip through the engine pins the
#: agreement, exactly as for the pairwise descriptor).
HEAT_DIFFUSION_DESCRIPTOR = (
    b"scout.native.heat-diffusion-kernel.v1\n"
    b"input: [steps u32 LE][n u32 LE][n x i64 LE]; 3<=n<=4096; steps<=100000; |u|<=2^40\n"
    b"per step, Jacobi, Dirichlet ends fixed: u'_i = u_i + (u_{i-1} - 2u_i + u_{i+1})/4\n"
    b"(integer division, truncation toward zero; alpha=1/4 within stability bound 1/2)\n"
    b"output: n x i64 LE final values; exit 0\n"
    b"faults: 2=malformed, 3=n<3, 4=n/steps bound, 5=value bound"
)


def encode_heat_input(steps: int, values: list[int]) -> bytes:
    """The heat kernel's canonical input encoding -- mirrors
    `execution_native::reference::encode_heat_input`."""
    import struct

    out = struct.pack("<II", steps, len(values))
    for value in values:
        out += struct.pack("<q", value)
    return out


def encode_positions(positions: list[tuple[int, int, int]]) -> bytes:
    """The reference workload's canonical input encoding -- mirrors
    `execution_native::reference::encode_positions` so the same particle
    list yields the same InputIdentity from either language."""
    import struct

    return b"".join(struct.pack("<iii", x, y, z) for (x, y, z) in positions)


# ---------------------------------------------------------------------
# Structural kernels (molecular/crystal vertical) -- byte-for-byte the
# Rust constants in `execution_native::reference`, like the two above;
# the engine round-trip pins the agreement.
# ---------------------------------------------------------------------

#: The mass-weighted radius-of-gyration kernel. The mass field is the
#: point: it puts the element's computational shadow into the CONSUMED
#: bytes, so changing an atom's element moves the input commitment --
#: which the coordinate-only pairwise kernel structurally cannot do.
RADIUS_OF_GYRATION_DESCRIPTOR = (
    b"scout.native.radius-of-gyration-kernel.v1\n"
    b"input: N*16 bytes of (mass u32 LE, x,y,z i32 LE); N>=1; |coord|<=2^20; 1<=mass<=2^20\n"
    b"com = sum(m*c)/sum(m) per axis; rg2 = sum(m*|r-com|^2)/sum(m)\n"
    b"(all i128, integer division truncating toward zero; coordinate checked before mass)\n"
    b"output: rg2 as i128 LE (16 bytes); exit 0\n"
    b"faults: 2=malformed length, 3=no atoms, 4=coordinate bound, 5=mass bound"
)

#: The periodic-lattice kernel. Periodicity is semantic: nearest
#: neighbours include an atom's own images over the committed shift set.
CRYSTAL_LATTICE_DESCRIPTOR = (
    b"scout.native.crystal-lattice-kernel.v1\n"
    b"input: [9 x i64 LE lattice rows a,b,c in pm][n u32 LE][n*12 bytes (fx,fy,fz) i32 LE millionths]\n"
    b"bounds: |L|<=2^30; 1<=n<=1024; 0<=f<1000000; cart(f) = (fx*a+fy*b+fz*c)/1000000 per axis\n"
    b"volume = |det(L)|; mind2 = min over sites i<=j and shifts s in {-1,0,1}^3 (i==j excludes s=0)\n"
    b"of |cart_i - cart_j + s*L|^2 (all i128, truncation toward zero; zero distance faults)\n"
    b"output: [volume i128 LE][mind2 i128 LE] (32 bytes); exit 0\n"
    b"faults: 2=malformed, 3=atom count, 4=lattice bound, 5=fraction bound, 6=degenerate, 7=coincident"
)


def encode_rg_input(atoms: list[tuple[int, int, int, int]]) -> bytes:
    """The Rg kernel's canonical input encoding -- mirrors
    `execution_native::reference::encode_rg_input`; atoms are
    (mass, x, y, z)."""
    import struct

    out = b""
    for mass, x, y, z in atoms:
        out += struct.pack("<Iiii", mass, x, y, z)
    return out


def encode_crystal_input(lattice, sites) -> bytes:
    """The crystal kernel's canonical input encoding -- mirrors
    `execution_native::reference::encode_crystal_input`; `lattice` is
    three (x, y, z) integer rows in pm, `sites` are (fx, fy, fz) in
    millionths."""
    import struct

    out = b""
    for row in lattice:
        for component in row:
            out += struct.pack("<q", component)
    out += struct.pack("<I", len(sites))
    for fx, fy, fz in sites:
        out += struct.pack("<iii", fx, fy, fz)
    return out


#: The transformer attention kernel -- byte-for-byte the Rust constant,
#: like the others; the engine round-trip pins the agreement.
HARDMAX_ATTENTION_DESCRIPTOR = (
    b"scout.native.attention-kernel.v1\n"
    b"input: [d u32 LE][n u32 LE][n*d i32 LE X][d*d i32 Wq][d*d Wk][d*d Wv]\n"
    b"bounds: 1<=d<=64; 1<=n<=1024; every value |v|<=2^20\n"
    b"Q=X.Wq K=X.Wk V=X.Wv (i128 accumulation); S_ij = Q_i . K_j\n"
    b"attend(i) = argmax_j S_ij, ties -> lowest j (hardmax); out_i = V_attend(i)\n"
    b"output: n*d i64 LE; exit 0\n"
    b"faults: 2=malformed, 3=dimensions, 4=value bound"
)


def encode_attention_input(d, tokens, wq, wk, wv) -> bytes:
    """The attention kernel's canonical input encoding -- mirrors
    `execution_native::reference::encode_attention_input`. `tokens` is
    n rows of d ints; the weight matrices are d rows of d ints."""
    import struct

    out = struct.pack("<II", d, len(tokens))
    for row in list(tokens) + list(wq) + list(wk) + list(wv):
        for value in row:
            out += struct.pack("<i", value)
    return out
