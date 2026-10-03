//! The pairwise-energy kernel's MATH, alone, `no_std`, allocation-free.
//!
//! Extracted from `execution-native` in STE stage 2 for one reason: the
//! same function must run in two places that cannot share `std` -- the
//! native backend (host) and the SP1 guest (RISC-V, `no_std`). One
//! implementation, two substrates, so native output and proved output
//! are outputs of the SAME code, not of two implementations claimed to
//! agree.
//!
//! The semantics are the ones `PAIRWISE_ENERGY_DESCRIPTOR` has committed
//! to since Phase 129 -- this refactor changes no behavior, no fault
//! code, no output byte, and therefore no identity. Check order is part
//! of those semantics and is preserved exactly: length first, then
//! per-particle coordinate bound during parse, then coincidence during
//! the pair loop.
//!
//! No allocation: positions are re-decoded by index, and the output is a
//! fixed 16-byte array -- which is also what makes this trivially
//! compilable for a zkVM guest.

#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![no_std]

extern crate alloc;

/// Fault: input length is not a multiple of 12.
pub const FAULT_MALFORMED_LENGTH: u32 = 2;
/// Fault: two particles are coincident (r2 == 0). An undefined term is
/// refused, never replaced with a zero.
pub const FAULT_COINCIDENT: u32 = 3;
/// Fault: a coordinate exceeds |c| <= 2^20.
pub const FAULT_COORDINATE_BOUND: u32 = 4;

const COORDINATE_BOUND: i32 = 1 << 20;
const REPULSIVE_NUMERATOR: i128 = 1 << 80;
const ATTRACTIVE_NUMERATOR: i128 = 1 << 40;

/// One fault: the exit code the descriptor assigns, plus a static
/// description (no formatting, no allocation).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct KernelFault {
    /// The descriptor's fault exit code (2, 3 or 4).
    pub exit_code: u32,
    /// A static human-readable description.
    pub detail: &'static str,
}

#[inline]
fn position(input: &[u8], index: usize) -> (i32, i32, i32) {
    let at = index * 12;
    let word = |offset: usize| {
        i32::from_le_bytes([
            input[at + offset],
            input[at + offset + 1],
            input[at + offset + 2],
            input[at + offset + 3],
        ])
    };
    (word(0), word(4), word(8))
}

/// Compute the pairwise inverse-power energy over `input`, exactly per
/// the descriptor. Returns the 16 output bytes (sum as i128 LE) or the
/// fault refusing the computation.
pub fn pairwise_energy(input: &[u8]) -> Result<[u8; 16], KernelFault> {
    if !input.len().is_multiple_of(12) {
        return Err(KernelFault {
            exit_code: FAULT_MALFORMED_LENGTH,
            detail: "input length is not a multiple of 12",
        });
    }
    let count = input.len() / 12;
    for index in 0..count {
        let (x, y, z) = position(input, index);
        if x.abs() > COORDINATE_BOUND || y.abs() > COORDINATE_BOUND || z.abs() > COORDINATE_BOUND {
            return Err(KernelFault {
                exit_code: FAULT_COORDINATE_BOUND,
                detail: "a coordinate exceeds |c| <= 2^20",
            });
        }
    }

    let mut energy: i128 = 0;
    for i in 0..count {
        for j in (i + 1)..count {
            let (xi, yi, zi) = position(input, i);
            let (xj, yj, zj) = position(input, j);
            let dx = (xi as i128) - (xj as i128);
            let dy = (yi as i128) - (yj as i128);
            let dz = (zi as i128) - (zj as i128);
            let r2 = dx * dx + dy * dy + dz * dz;
            if r2 == 0 {
                return Err(KernelFault {
                    exit_code: FAULT_COINCIDENT,
                    detail: "two particles are coincident",
                });
            }
            energy += REPULSIVE_NUMERATOR / (r2 * r2) - ATTRACTIVE_NUMERATOR / r2;
        }
    }
    Ok(energy.to_le_bytes())
}

// ---------------------------------------------------------------------
// Second kernel (STE stage 4): 1-D heat diffusion -- an explicit
// finite-difference PDE integrator, a fundamentally different
// computational structure from the pairwise kernel: time-stepped
// nearest-neighbour stencil vs all-pairs accumulation.
// ---------------------------------------------------------------------

/// Heat-kernel fault: input shape is wrong (too short, or not 8 + 8n bytes).
pub const HEAT_FAULT_MALFORMED: u32 = 2;
/// Heat-kernel fault: fewer than 3 nodes (no interior to diffuse).
pub const HEAT_FAULT_TOO_SMALL: u32 = 3;
/// Heat-kernel fault: node count exceeds 4096 or steps exceed 100000.
pub const HEAT_FAULT_BOUNDS: u32 = 4;
/// Heat-kernel fault: an initial value exceeds |u| <= 2^40.
pub const HEAT_FAULT_VALUE_BOUND: u32 = 5;

const HEAT_MAX_NODES: usize = 4096;
const HEAT_MAX_STEPS: u32 = 100_000;
const HEAT_VALUE_BOUND: i64 = 1 << 40;

/// Explicit finite-difference integration of the 1-D heat equation on a
/// fixed grid, entirely in integer arithmetic.
///
/// ```text
/// input  := [steps: u32 LE][n: u32 LE][n x i64 LE initial values]
/// bounds := 3 <= n <= 4096; steps <= 100000; |u_i| <= 2^40
/// step   := for i in 1..n-1 (Dirichlet: u_0 and u_{n-1} fixed):
///             u'_i = u_i + (u_{i-1} - 2*u_i + u_{i+1}) / 4
///           integer division truncating toward zero (alpha = 1/4 is
///           inside the explicit-scheme stability bound of 1/2)
/// output := n x i64 LE final values
/// exit   := 0
/// ```
///
/// The update is computed against the PREVIOUS step's values (a carried
/// `left_old`), never against half-updated ones -- the scheme is Jacobi,
/// not Gauss-Seidel, and which one runs is part of the semantics the
/// descriptor commits to.
pub fn heat_diffusion(input: &[u8]) -> Result<alloc::vec::Vec<u8>, KernelFault> {
    if input.len() < 8 {
        return Err(KernelFault {
            exit_code: HEAT_FAULT_MALFORMED,
            detail: "input shorter than the 8-byte header",
        });
    }
    let steps = u32::from_le_bytes([input[0], input[1], input[2], input[3]]);
    let count = u32::from_le_bytes([input[4], input[5], input[6], input[7]]) as usize;
    if input.len() != 8 + 8 * count {
        return Err(KernelFault {
            exit_code: HEAT_FAULT_MALFORMED,
            detail: "input length is not 8 + 8*n bytes",
        });
    }
    if count < 3 {
        return Err(KernelFault {
            exit_code: HEAT_FAULT_TOO_SMALL,
            detail: "fewer than 3 nodes: no interior to diffuse",
        });
    }
    if count > HEAT_MAX_NODES || steps > HEAT_MAX_STEPS {
        return Err(KernelFault {
            exit_code: HEAT_FAULT_BOUNDS,
            detail: "node count or step count exceeds the descriptor's bounds",
        });
    }

    let mut values = alloc::vec::Vec::with_capacity(count);
    for index in 0..count {
        let at = 8 + index * 8;
        let value = i64::from_le_bytes([
            input[at],
            input[at + 1],
            input[at + 2],
            input[at + 3],
            input[at + 4],
            input[at + 5],
            input[at + 6],
            input[at + 7],
        ]);
        if value.abs() > HEAT_VALUE_BOUND {
            return Err(KernelFault {
                exit_code: HEAT_FAULT_VALUE_BOUND,
                detail: "an initial value exceeds |u| <= 2^40",
            });
        }
        values.push(value);
    }

    for _ in 0..steps {
        let mut left_old = values[0];
        for i in 1..count - 1 {
            let old = values[i];
            values[i] = old + (left_old - 2 * old + values[i + 1]) / 4;
            left_old = old;
        }
    }

    let mut output = alloc::vec::Vec::with_capacity(count * 8);
    for value in &values {
        output.extend_from_slice(&value.to_le_bytes());
    }
    Ok(output)
}

// ---------------------------------------------------------------------
// Structural kernels (molecular/crystal vertical): a mass-weighted
// molecular descriptor and a periodic lattice kernel. Same discipline
// as the first two kernels -- integer arithmetic only, faults refuse
// rather than repair, and the descriptor commits the exact semantics.
//
// The radius-of-gyration kernel exists for a discovered epistemic
// reason, not convenience: the pairwise kernel consumes COORDINATES
// only, so a proof of it binds coordinates and nothing else -- changing
// an atom's ELEMENT cannot move that input commitment. Here the mass
// (the element's computational shadow) is part of the consumed bytes,
// so element identity participates in the commitment chain.
// ---------------------------------------------------------------------

/// Rg kernel fault: input length is not a multiple of 16.
pub const RG_FAULT_MALFORMED: u32 = 2;
/// Rg kernel fault: zero atoms (no center of mass exists).
pub const RG_FAULT_NO_ATOMS: u32 = 3;
/// Rg kernel fault: a coordinate exceeds |c| <= 2^20.
pub const RG_FAULT_COORDINATE_BOUND: u32 = 4;
/// Rg kernel fault: a mass is outside 1..=2^20.
pub const RG_FAULT_MASS_BOUND: u32 = 5;

const RG_COORDINATE_BOUND: i32 = 1 << 20;
const RG_MASS_BOUND: u32 = 1 << 20;

#[inline]
fn rg_atom(input: &[u8], index: usize) -> (u32, i32, i32, i32) {
    let at = index * 16;
    let u = |o: usize| {
        u32::from_le_bytes([
            input[at + o],
            input[at + o + 1],
            input[at + o + 2],
            input[at + o + 3],
        ])
    };
    let i = |o: usize| {
        i32::from_le_bytes([
            input[at + o],
            input[at + o + 1],
            input[at + o + 2],
            input[at + o + 3],
        ])
    };
    (u(0), i(4), i(8), i(12))
}

/// Mass-weighted squared radius of gyration, exactly per the
/// descriptor: com = sum(m*c)/sum(m) per axis, rg2 =
/// sum(m*|r-com|^2)/sum(m), all i128 with truncation toward zero.
/// Returns the 16 output bytes (rg2 as i128 LE) or the refusing fault.
pub fn radius_of_gyration(input: &[u8]) -> Result<[u8; 16], KernelFault> {
    if !input.len().is_multiple_of(16) {
        return Err(KernelFault {
            exit_code: RG_FAULT_MALFORMED,
            detail: "input length is not a multiple of 16",
        });
    }
    let count = input.len() / 16;
    if count == 0 {
        return Err(KernelFault {
            exit_code: RG_FAULT_NO_ATOMS,
            detail: "zero atoms: no center of mass exists",
        });
    }
    for index in 0..count {
        let (m, x, y, z) = rg_atom(input, index);
        if x.abs() > RG_COORDINATE_BOUND
            || y.abs() > RG_COORDINATE_BOUND
            || z.abs() > RG_COORDINATE_BOUND
        {
            return Err(KernelFault {
                exit_code: RG_FAULT_COORDINATE_BOUND,
                detail: "a coordinate exceeds |c| <= 2^20",
            });
        }
        if m == 0 || m > RG_MASS_BOUND {
            return Err(KernelFault {
                exit_code: RG_FAULT_MASS_BOUND,
                detail: "a mass is outside 1..=2^20",
            });
        }
    }

    let (mut total, mut sx, mut sy, mut sz) = (0i128, 0i128, 0i128, 0i128);
    for index in 0..count {
        let (m, x, y, z) = rg_atom(input, index);
        let m = m as i128;
        total += m;
        sx += m * x as i128;
        sy += m * y as i128;
        sz += m * z as i128;
    }
    let (cx, cy, cz) = (sx / total, sy / total, sz / total);

    let mut weighted = 0i128;
    for index in 0..count {
        let (m, x, y, z) = rg_atom(input, index);
        let (dx, dy, dz) = (x as i128 - cx, y as i128 - cy, z as i128 - cz);
        weighted += m as i128 * (dx * dx + dy * dy + dz * dz);
    }
    Ok((weighted / total).to_le_bytes())
}

/// Crystal kernel fault: input shape is wrong (not 76 + 12n bytes).
pub const CRYSTAL_FAULT_MALFORMED: u32 = 2;
/// Crystal kernel fault: zero atoms or more than 1024.
pub const CRYSTAL_FAULT_ATOM_COUNT: u32 = 3;
/// Crystal kernel fault: a lattice component exceeds |L| <= 2^30.
pub const CRYSTAL_FAULT_LATTICE_BOUND: u32 = 4;
/// Crystal kernel fault: a fractional coordinate is outside 0..1000000.
pub const CRYSTAL_FAULT_FRACTION_BOUND: u32 = 5;
/// Crystal kernel fault: the lattice is degenerate (det == 0).
pub const CRYSTAL_FAULT_DEGENERATE: u32 = 6;
/// Crystal kernel fault: two atoms (or periodic images) coincide.
pub const CRYSTAL_FAULT_COINCIDENT: u32 = 7;

const CRYSTAL_LATTICE_BOUND: i64 = 1 << 30;
const CRYSTAL_MAX_ATOMS: usize = 1024;
const CRYSTAL_FRACTION_DENOM: i128 = 1_000_000;

#[inline]
fn crystal_i64(input: &[u8], at: usize) -> i64 {
    i64::from_le_bytes([
        input[at],
        input[at + 1],
        input[at + 2],
        input[at + 3],
        input[at + 4],
        input[at + 5],
        input[at + 6],
        input[at + 7],
    ])
}

#[inline]
fn crystal_frac(input: &[u8], index: usize) -> (i32, i32, i32) {
    let at = 76 + index * 12;
    let i = |o: usize| {
        i32::from_le_bytes([
            input[at + o],
            input[at + o + 1],
            input[at + o + 2],
            input[at + o + 3],
        ])
    };
    (i(0), i(4), i(8))
}

/// Periodic lattice kernel, exactly per the descriptor: |det(L)| plus
/// the minimum squared distance between distinct atom sites over the
/// 27 neighbour images {-1,0,1}^3 (an atom's own periodic copies
/// included). Returns 32 output bytes ([volume i128 LE][mind2 i128 LE])
/// or the refusing fault. Periodicity is SEMANTIC here -- a molecule
/// has no images; this kernel's nearest neighbour may be a copy of the
/// same atom one cell over.
pub fn crystal_lattice(input: &[u8]) -> Result<[u8; 32], KernelFault> {
    if input.len() < 76 || !(input.len() - 76).is_multiple_of(12) {
        return Err(KernelFault {
            exit_code: CRYSTAL_FAULT_MALFORMED,
            detail: "input length is not 76 + 12*n bytes",
        });
    }
    let count = u32::from_le_bytes([input[72], input[73], input[74], input[75]]) as usize;
    if input.len() != 76 + 12 * count {
        return Err(KernelFault {
            exit_code: CRYSTAL_FAULT_MALFORMED,
            detail: "atom count disagrees with input length",
        });
    }
    if count == 0 || count > CRYSTAL_MAX_ATOMS {
        return Err(KernelFault {
            exit_code: CRYSTAL_FAULT_ATOM_COUNT,
            detail: "atom count is outside 1..=1024",
        });
    }
    let mut lattice = [[0i64; 3]; 3];
    for (row, lattice_row) in lattice.iter_mut().enumerate() {
        for (col, component) in lattice_row.iter_mut().enumerate() {
            let value = crystal_i64(input, (row * 3 + col) * 8);
            if value.abs() > CRYSTAL_LATTICE_BOUND {
                return Err(KernelFault {
                    exit_code: CRYSTAL_FAULT_LATTICE_BOUND,
                    detail: "a lattice component exceeds |L| <= 2^30",
                });
            }
            *component = value;
        }
    }
    for index in 0..count {
        let (fx, fy, fz) = crystal_frac(input, index);
        for f in [fx, fy, fz] {
            if !(0..CRYSTAL_FRACTION_DENOM as i32).contains(&f) {
                return Err(KernelFault {
                    exit_code: CRYSTAL_FAULT_FRACTION_BOUND,
                    detail: "a fractional coordinate is outside 0..1000000",
                });
            }
        }
    }

    let a = [
        lattice[0][0] as i128,
        lattice[0][1] as i128,
        lattice[0][2] as i128,
    ];
    let b = [
        lattice[1][0] as i128,
        lattice[1][1] as i128,
        lattice[1][2] as i128,
    ];
    let c = [
        lattice[2][0] as i128,
        lattice[2][1] as i128,
        lattice[2][2] as i128,
    ];
    let det = a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0]);
    if det == 0 {
        return Err(KernelFault {
            exit_code: CRYSTAL_FAULT_DEGENERATE,
            detail: "the lattice is degenerate (det == 0)",
        });
    }
    let volume = det.abs();

    let cart = |index: usize| -> [i128; 3] {
        let (fx, fy, fz) = crystal_frac(input, index);
        let mut out = [0i128; 3];
        for (axis, slot) in out.iter_mut().enumerate() {
            *slot = (fx as i128 * a[axis] + fy as i128 * b[axis] + fz as i128 * c[axis])
                / CRYSTAL_FRACTION_DENOM;
        }
        out
    };

    let mut mind2: Option<i128> = None;
    for i in 0..count {
        let ri = cart(i);
        for j in i..count {
            let rj = cart(j);
            for sx in -1i128..=1 {
                for sy in -1i128..=1 {
                    for sz in -1i128..=1 {
                        if i == j && sx == 0 && sy == 0 && sz == 0 {
                            continue;
                        }
                        let mut d2 = 0i128;
                        for axis in 0..3 {
                            let shift = sx * a[axis] + sy * b[axis] + sz * c[axis];
                            let d = ri[axis] - rj[axis] + shift;
                            d2 += d * d;
                        }
                        if d2 == 0 {
                            return Err(KernelFault {
                                exit_code: CRYSTAL_FAULT_COINCIDENT,
                                detail: "two atom sites (or periodic images) coincide",
                            });
                        }
                        if mind2.is_none_or(|m| d2 < m) {
                            mind2 = Some(d2);
                        }
                    }
                }
            }
        }
    }
    let mind2 = mind2.expect("count >= 1 guarantees at least the self-image distances");

    let mut output = [0u8; 32];
    output[..16].copy_from_slice(&volume.to_le_bytes());
    output[16..].copy_from_slice(&mind2.to_le_bytes());
    Ok(output)
}

// ---------------------------------------------------------------------
// Transformer kernel: integer single-head HARDMAX attention. The
// Transformer Engine's first model computation, behind the same
// DeterministicProgram discipline as every other kernel: integer
// arithmetic only, faults refuse, the descriptor commits the exact
// semantics. Hardmax (argmax attention, ties to the lowest index) is
// chosen precisely because it is exactly representable in integers --
// no softmax approximation whose rounding would be a hidden semantic.
// ---------------------------------------------------------------------

/// Attention kernel fault: input shape is wrong.
pub const ATTN_FAULT_MALFORMED: u32 = 2;
/// Attention kernel fault: dimensions out of range.
pub const ATTN_FAULT_DIMENSIONS: u32 = 3;
/// Attention kernel fault: a value exceeds |v| <= 2^20.
pub const ATTN_FAULT_VALUE_BOUND: u32 = 4;

const ATTN_MAX_DIM: usize = 64;
const ATTN_MAX_TOKENS: usize = 1024;
const ATTN_VALUE_BOUND: i32 = 1 << 20;

#[inline]
fn attn_i32(input: &[u8], at: usize) -> i32 {
    i32::from_le_bytes([input[at], input[at + 1], input[at + 2], input[at + 3]])
}

/// Single-head integer hardmax attention, exactly per the descriptor:
/// Q = X·Wq, K = X·Wk, V = X·Wv (i128 accumulation); S_ij = Q_i · K_j;
/// each token attends to argmax_j S_ij (ties -> lowest j); output row i
/// is V_attend(i) as i64. Returns the n*d*8 output bytes or the
/// refusing fault.
pub fn hardmax_attention(input: &[u8]) -> Result<alloc::vec::Vec<u8>, KernelFault> {
    if input.len() < 8 {
        return Err(KernelFault {
            exit_code: ATTN_FAULT_MALFORMED,
            detail: "input shorter than the 8-byte header",
        });
    }
    let d = u32::from_le_bytes([input[0], input[1], input[2], input[3]]) as usize;
    let n = u32::from_le_bytes([input[4], input[5], input[6], input[7]]) as usize;
    if d == 0 || d > ATTN_MAX_DIM || n == 0 || n > ATTN_MAX_TOKENS {
        return Err(KernelFault {
            exit_code: ATTN_FAULT_DIMENSIONS,
            detail: "d outside 1..=64 or n outside 1..=1024",
        });
    }
    let expected = 8 + 4 * (n * d + 3 * d * d);
    if input.len() != expected {
        return Err(KernelFault {
            exit_code: ATTN_FAULT_MALFORMED,
            detail: "input length is not 8 + 4*(n*d + 3*d*d) bytes",
        });
    }
    let x_at = 8;
    let wq_at = x_at + 4 * n * d;
    let wk_at = wq_at + 4 * d * d;
    let wv_at = wk_at + 4 * d * d;
    for offset in (8..input.len()).step_by(4) {
        let value = attn_i32(input, offset);
        if value.abs() > ATTN_VALUE_BOUND {
            return Err(KernelFault {
                exit_code: ATTN_FAULT_VALUE_BOUND,
                detail: "a value exceeds |v| <= 2^20",
            });
        }
    }

    // projected rows: P[i][k] = sum_j X[i][j] * W[j][k] (i128)
    let project = |w_at: usize, i: usize, k: usize| -> i128 {
        let mut acc: i128 = 0;
        for j in 0..d {
            let x = attn_i32(input, x_at + 4 * (i * d + j)) as i128;
            let w = attn_i32(input, w_at + 4 * (j * d + k)) as i128;
            acc += x * w;
        }
        acc
    };

    let mut output = alloc::vec::Vec::with_capacity(n * d * 8);
    for i in 0..n {
        let q: alloc::vec::Vec<i128> = (0..d).map(|k| project(wq_at, i, k)).collect();
        let mut best_j = 0usize;
        let mut best_score = i128::MIN;
        for j in 0..n {
            let mut score: i128 = 0;
            for (k, q_k) in q.iter().enumerate() {
                score += q_k * project(wk_at, j, k);
            }
            if score > best_score {
                best_score = score;
                best_j = j;
            }
        }
        for k in 0..d {
            let value = project(wv_at, best_j, k);
            output.extend_from_slice(&(value as i64).to_le_bytes());
        }
    }
    Ok(output)
}
