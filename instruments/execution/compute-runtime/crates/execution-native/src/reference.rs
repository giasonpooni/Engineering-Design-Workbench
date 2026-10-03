//! The reference workload: an integer pairwise inverse-power energy
//! kernel.
//!
//! ONE deterministic scientific-computing-shaped workload, chosen to be
//! the smallest thing that exercises the substrate's semantics with a
//! structure relevant to the eventual materials/simulation system: a set
//! of particle positions in, a pairwise-interaction scalar out.
//!
//! # What this is not
//!
//! It is NOT a materials primitive, NOT physically parameterised, NOT
//! admissible anywhere, and asserts nothing about any material. It is
//! Lennard-Jones-SHAPED -- a repulsive short-range term minus an
//! attractive long-range term -- because that shape exercises pairwise
//! iteration and accumulation, not because its constants mean anything.
//! `materials/` remains the only place scientific mathematics lives;
//! this kernel lives here so the substrate has one honest workload to
//! demonstrate identity semantics against.
//!
//! # Why integers
//!
//! The whole kernel is integer arithmetic (`i128` accumulation, integer
//! division truncating toward zero). Floating point would make
//! "deterministic" contingent on FMA contraction, x87 vs SSE, and libm
//! versions; integers make it a property. Determinism here is exercised
//! by tests, not promised by prose.
//!
//! # Exact semantics (these ARE the program, and the canonical
//! descriptor commits to them)
//!
//! ```text
//! input   := N * 12 bytes; each 12 bytes = x, y, z as i32 little-endian
//! bounds  := every coordinate must satisfy |c| <= 2^20        (else fault 4)
//! shape   := input length must be a multiple of 12            (else fault 2)
//! pairs   := for every i < j:
//!              r2 = (xi-xj)^2 + (yi-yj)^2 + (zi-zj)^2   in i128
//!              r2 == 0 is a fault                             (fault 3)
//!              e  = 2^80 / r2^2  -  2^40 / r2           integer division
//! output  := sum of e over all pairs, as i128 little-endian (16 bytes)
//! exit    := 0
//! ```
//!
//! Coincident particles fault rather than contributing anything: an
//! undefined term is refused, never replaced with a zero.

use crate::{DeterministicProgram, NativeCompletion, NativeFault};

/// The canonical descriptor [`PairwiseEnergyKernel`] is identified by.
///
/// It spells out the exact integer semantics above, so two kernels that
/// compute different things cannot honestly share it -- and so a future
/// guest implementation of the SAME semantics inside a zkVM can carry
/// the SAME descriptor and therefore the same `ProgramIdentity`.
pub const PAIRWISE_ENERGY_DESCRIPTOR: &[u8] = concat!(
    "scout.native.pairwise-energy-kernel.v1
",
    "input: N*12 bytes of (x,y,z) as i32 LE; |coord| <= 2^20
",
    "for i<j: r2=(dx^2+dy^2+dz^2) as i128; r2==0 faults;
",
    "e = 2^80/r2^2 - 2^40/r2 (integer division, truncation toward zero)
",
    "output: sum(e) as i128 LE (16 bytes); exit 0
",
    "faults: 2=malformed length, 3=coincident particles, 4=coordinate bound",
)
.as_bytes();

/// The reference workload. See the module documentation for exactly
/// what it computes and exactly what it does not claim.
pub struct PairwiseEnergyKernel;

impl DeterministicProgram for PairwiseEnergyKernel {
    fn canonical_bytes(&self) -> &[u8] {
        PAIRWISE_ENERGY_DESCRIPTOR
    }

    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        // STE stage 2: the math moved to `execution-kernel` (no_std,
        // allocation-free) so the SP1 guest runs the SAME implementation
        // this backend does -- one function, two substrates. Behavior,
        // fault codes, check order and output bytes are unchanged, so
        // every identity is unchanged.
        match execution_kernel::pairwise_energy(input) {
            Ok(output) => Ok(NativeCompletion {
                output: output.to_vec(),
                exit_code: 0,
            }),
            Err(fault) => Err(NativeFault {
                exit_code: fault.exit_code,
                detail: fault.detail.to_string(),
            }),
        }
    }
}

/// Encode particle positions into the kernel's canonical input bytes.
///
/// This is the caller-side half of the canonicalization burden the Phase
/// 128 review named: the kernel identifies its input by BYTES, so a
/// caller that wants "the same particles -> the same InputIdentity" must
/// encode them the same way every time. This function is that one way.
pub fn encode_positions(positions: &[(i32, i32, i32)]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(positions.len() * 12);
    for (x, y, z) in positions {
        bytes.extend_from_slice(&x.to_le_bytes());
        bytes.extend_from_slice(&y.to_le_bytes());
        bytes.extend_from_slice(&z.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn determinism_same_bytes_same_energy() {
        let input = encode_positions(&[(0, 0, 0), (4, 0, 0), (0, 7, 0)]);
        let kernel = PairwiseEnergyKernel;
        assert_eq!(kernel.run(&input), kernel.run(&input));
    }

    #[test]
    fn energy_depends_on_geometry() {
        let kernel = PairwiseEnergyKernel;
        let near = kernel
            .run(&encode_positions(&[(0, 0, 0), (2, 0, 0)]))
            .unwrap();
        let far = kernel
            .run(&encode_positions(&[(0, 0, 0), (100, 0, 0)]))
            .unwrap();
        assert_ne!(near.output, far.output);
    }

    #[test]
    fn malformed_length_faults_with_code_2() {
        let fault = PairwiseEnergyKernel.run(&[1, 2, 3]).unwrap_err();
        assert_eq!(fault.exit_code, 2);
    }

    #[test]
    fn coincident_particles_fault_rather_than_contribute_zero() {
        let input = encode_positions(&[(5, 5, 5), (5, 5, 5)]);
        let fault = PairwiseEnergyKernel.run(&input).unwrap_err();
        assert_eq!(fault.exit_code, 3);
    }

    #[test]
    fn out_of_bounds_coordinate_faults_with_code_4() {
        let input = encode_positions(&[(0, 0, 0), (1 << 21, 0, 0)]);
        let fault = PairwiseEnergyKernel.run(&input).unwrap_err();
        assert_eq!(fault.exit_code, 4);
    }

    #[test]
    fn empty_and_single_particle_complete_with_zero_pairs() {
        // Zero pairs is a REAL result (there is nothing to sum), not an
        // unknown one -- so this completes with an output, unlike the
        // faults above which complete with none.
        let kernel = PairwiseEnergyKernel;
        let none = kernel.run(&[]).unwrap();
        let one = kernel.run(&encode_positions(&[(3, 3, 3)])).unwrap();
        assert_eq!(none.output, 0i128.to_le_bytes().to_vec());
        assert_eq!(one.output, 0i128.to_le_bytes().to_vec());
    }
}

// ---------------------------------------------------------------------
// STE stage 4: the second reference workload -- 1-D heat diffusion.
// A fundamentally different computational structure (time-stepped
// nearest-neighbour stencil) behind the same DeterministicProgram
// contract, the same identity discipline, and -- via its own guests --
// the same proof backends.
// ---------------------------------------------------------------------

/// The canonical descriptor [`HeatDiffusionKernel`] is identified by.
/// Spells out the exact integer semantics, including that the scheme is
/// Jacobi (updates read the previous step), so a reimplementation that
/// quietly went Gauss-Seidel could not honestly share it.
pub const HEAT_DIFFUSION_DESCRIPTOR: &[u8] = concat!(
    "scout.native.heat-diffusion-kernel.v1\n",
    "input: [steps u32 LE][n u32 LE][n x i64 LE]; 3<=n<=4096; steps<=100000; |u|<=2^40\n",
    "per step, Jacobi, Dirichlet ends fixed: u'_i = u_i + (u_{i-1} - 2u_i + u_{i+1})/4\n",
    "(integer division, truncation toward zero; alpha=1/4 within stability bound 1/2)\n",
    "output: n x i64 LE final values; exit 0\n",
    "faults: 2=malformed, 3=n<3, 4=n/steps bound, 5=value bound",
)
.as_bytes();

/// The heat-diffusion reference workload. Same contract, same caveats
/// as [`PairwiseEnergyKernel`]: not a materials primitive, asserts
/// nothing about any material, exists to exercise the substrate with a
/// second computational shape.
pub struct HeatDiffusionKernel;

impl DeterministicProgram for HeatDiffusionKernel {
    fn canonical_bytes(&self) -> &[u8] {
        HEAT_DIFFUSION_DESCRIPTOR
    }

    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        match execution_kernel::heat_diffusion(input) {
            Ok(output) => Ok(NativeCompletion {
                output,
                exit_code: 0,
            }),
            Err(fault) => Err(NativeFault {
                exit_code: fault.exit_code,
                detail: fault.detail.to_string(),
            }),
        }
    }
}

/// Encode a heat-diffusion input: step count plus initial node values.
pub fn encode_heat_input(steps: u32, values: &[i64]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(8 + values.len() * 8);
    bytes.extend_from_slice(&steps.to_le_bytes());
    bytes.extend_from_slice(&(values.len() as u32).to_le_bytes());
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod heat_tests {
    use super::*;

    #[test]
    fn diffusion_moves_toward_the_boundary_values() {
        // A hot interior between cold fixed ends must cool monotonically
        // toward the ends' values -- a semantic check on the workload.
        let input = encode_heat_input(1000, &[0, 1_000_000, 1_000_000, 1_000_000, 0]);
        let out = HeatDiffusionKernel.run(&input).unwrap();
        let finals: Vec<i64> = out
            .output
            .chunks_exact(8)
            .map(|c| i64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        assert_eq!(finals[0], 0, "Dirichlet: ends fixed");
        assert_eq!(finals[4], 0);
        assert!(finals[2] < 1_000_000, "interior cooled");
        assert!(
            finals[1] <= finals[2],
            "profile is symmetric-ish and peaked at centre"
        );
    }

    #[test]
    fn deterministic_and_step_dependent() {
        let short = encode_heat_input(10, &[0, 500, 900, 500, 0]);
        let long = encode_heat_input(200, &[0, 500, 900, 500, 0]);
        assert_eq!(
            HeatDiffusionKernel.run(&short),
            HeatDiffusionKernel.run(&short)
        );
        assert_ne!(
            HeatDiffusionKernel.run(&short).unwrap().output,
            HeatDiffusionKernel.run(&long).unwrap().output,
            "steps are part of the computation"
        );
    }

    #[test]
    fn faults_are_the_descriptor_codes() {
        assert_eq!(HeatDiffusionKernel.run(b"xx").unwrap_err().exit_code, 2);
        assert_eq!(
            HeatDiffusionKernel
                .run(&encode_heat_input(1, &[1, 2]))
                .unwrap_err()
                .exit_code,
            3
        );
        assert_eq!(
            HeatDiffusionKernel
                .run(&encode_heat_input(200_000, &[1, 2, 3]))
                .unwrap_err()
                .exit_code,
            4
        );
        assert_eq!(
            HeatDiffusionKernel
                .run(&encode_heat_input(1, &[1 << 41, 0, 0]))
                .unwrap_err()
                .exit_code,
            5
        );
    }
}

// ---------------------------------------------------------------------
// Structural kernels (molecular/crystal vertical): the third and fourth
// reference workloads. Same contract and caveats as the first two --
// deterministic integer semantics committed by the descriptor, faults
// refuse rather than repair, and no claim about any physical material.
// ---------------------------------------------------------------------

/// The canonical descriptor [`RadiusOfGyrationKernel`] is identified by.
/// The mass field is the point of this kernel: it makes the element's
/// computational shadow part of the CONSUMED bytes, so a changed atom
/// type moves the input commitment (the pairwise kernel, consuming
/// coordinates only, cannot bind element identity).
pub const RADIUS_OF_GYRATION_DESCRIPTOR: &[u8] = concat!(
    "scout.native.radius-of-gyration-kernel.v1\n",
    "input: N*16 bytes of (mass u32 LE, x,y,z i32 LE); N>=1; |coord|<=2^20; 1<=mass<=2^20\n",
    "com = sum(m*c)/sum(m) per axis; rg2 = sum(m*|r-com|^2)/sum(m)\n",
    "(all i128, integer division truncating toward zero; coordinate checked before mass)\n",
    "output: rg2 as i128 LE (16 bytes); exit 0\n",
    "faults: 2=malformed length, 3=no atoms, 4=coordinate bound, 5=mass bound",
)
.as_bytes();

/// The mass-weighted radius-of-gyration workload.
pub struct RadiusOfGyrationKernel;

impl DeterministicProgram for RadiusOfGyrationKernel {
    fn canonical_bytes(&self) -> &[u8] {
        RADIUS_OF_GYRATION_DESCRIPTOR
    }

    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        match execution_kernel::radius_of_gyration(input) {
            Ok(output) => Ok(NativeCompletion {
                output: output.to_vec(),
                exit_code: 0,
            }),
            Err(fault) => Err(NativeFault {
                exit_code: fault.exit_code,
                detail: fault.detail.to_string(),
            }),
        }
    }
}

/// Encode (mass, x, y, z) atoms into the Rg kernel's canonical input.
pub fn encode_rg_input(atoms: &[(u32, i32, i32, i32)]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(atoms.len() * 16);
    for (m, x, y, z) in atoms {
        bytes.extend_from_slice(&m.to_le_bytes());
        bytes.extend_from_slice(&x.to_le_bytes());
        bytes.extend_from_slice(&y.to_le_bytes());
        bytes.extend_from_slice(&z.to_le_bytes());
    }
    bytes
}

/// The canonical descriptor [`CrystalLatticeKernel`] is identified by.
/// Periodicity is SEMANTIC here: nearest neighbours include an atom's
/// own images over the committed {-1,0,1}^3 shift set, which is why a
/// crystal cannot honestly be run as "a molecule with extra fields".
pub const CRYSTAL_LATTICE_DESCRIPTOR: &[u8] = concat!(
    "scout.native.crystal-lattice-kernel.v1\n",
    "input: [9 x i64 LE lattice rows a,b,c in pm][n u32 LE][n*12 bytes (fx,fy,fz) i32 LE millionths]\n",
    "bounds: |L|<=2^30; 1<=n<=1024; 0<=f<1000000; cart(f) = (fx*a+fy*b+fz*c)/1000000 per axis\n",
    "volume = |det(L)|; mind2 = min over sites i<=j and shifts s in {-1,0,1}^3 (i==j excludes s=0)\n",
    "of |cart_i - cart_j + s*L|^2 (all i128, truncation toward zero; zero distance faults)\n",
    "output: [volume i128 LE][mind2 i128 LE] (32 bytes); exit 0\n",
    "faults: 2=malformed, 3=atom count, 4=lattice bound, 5=fraction bound, 6=degenerate, 7=coincident",
)
.as_bytes();

/// The periodic-lattice workload.
pub struct CrystalLatticeKernel;

impl DeterministicProgram for CrystalLatticeKernel {
    fn canonical_bytes(&self) -> &[u8] {
        CRYSTAL_LATTICE_DESCRIPTOR
    }

    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        match execution_kernel::crystal_lattice(input) {
            Ok(output) => Ok(NativeCompletion {
                output: output.to_vec(),
                exit_code: 0,
            }),
            Err(fault) => Err(NativeFault {
                exit_code: fault.exit_code,
                detail: fault.detail.to_string(),
            }),
        }
    }
}

/// Encode a lattice (three row vectors, pm) and fractional sites
/// (millionths) into the crystal kernel's canonical input.
pub fn encode_crystal_input(lattice: &[[i64; 3]; 3], sites: &[(i32, i32, i32)]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(76 + sites.len() * 12);
    for row in lattice {
        for component in row {
            bytes.extend_from_slice(&component.to_le_bytes());
        }
    }
    bytes.extend_from_slice(&(sites.len() as u32).to_le_bytes());
    for (fx, fy, fz) in sites {
        bytes.extend_from_slice(&fx.to_le_bytes());
        bytes.extend_from_slice(&fy.to_le_bytes());
        bytes.extend_from_slice(&fz.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod structural_tests {
    use super::*;

    #[test]
    fn rg_is_deterministic_and_mass_sensitive() {
        // the water-shaped case: same coordinates, one mass changed
        // (O -> S, say) => different rg2. THIS is what the pairwise
        // kernel cannot see.
        let water = encode_rg_input(&[(16, 0, 0, 0), (1, 757, 587, 0), (1, -757, 587, 0)]);
        let heavier = encode_rg_input(&[(32, 0, 0, 0), (1, 757, 587, 0), (1, -757, 587, 0)]);
        let kernel = RadiusOfGyrationKernel;
        assert_eq!(kernel.run(&water), kernel.run(&water));
        assert_ne!(
            kernel.run(&water).unwrap().output,
            kernel.run(&heavier).unwrap().output,
            "a changed mass is a changed computation"
        );
    }

    #[test]
    fn rg_faults_are_the_descriptor_codes() {
        let kernel = RadiusOfGyrationKernel;
        assert_eq!(kernel.run(&[1, 2, 3]).unwrap_err().exit_code, 2);
        assert_eq!(kernel.run(&[]).unwrap_err().exit_code, 3);
        assert_eq!(
            kernel
                .run(&encode_rg_input(&[(1, 1 << 21, 0, 0)]))
                .unwrap_err()
                .exit_code,
            4
        );
        assert_eq!(
            kernel
                .run(&encode_rg_input(&[(0, 1, 1, 1)]))
                .unwrap_err()
                .exit_code,
            5
        );
    }

    #[test]
    fn crystal_volume_and_periodic_neighbour_are_exact_for_cubic_argon() {
        // FCC argon, a = 526 pm scaled to a small integer test cell:
        // cubic a=526000 pm cell with 4 sites. volume = a^3 exactly;
        // nearest neighbour = a/sqrt(2) -- mind2 = a^2/2 up to the
        // committed truncation.
        let a = 526_000i64;
        let lattice = [[a, 0, 0], [0, a, 0], [0, 0, a]];
        let sites = [
            (0, 0, 0),
            (500_000, 500_000, 0),
            (500_000, 0, 500_000),
            (0, 500_000, 500_000),
        ];
        let out = CrystalLatticeKernel
            .run(&encode_crystal_input(&lattice, &sites))
            .unwrap();
        let volume = i128::from_le_bytes(out.output[..16].try_into().unwrap());
        let mind2 = i128::from_le_bytes(out.output[16..].try_into().unwrap());
        assert_eq!(volume, (a as i128).pow(3));
        assert_eq!(mind2, (a as i128).pow(2) / 2);
    }

    #[test]
    fn crystal_periodicity_is_semantic_one_atom_still_has_neighbours() {
        // a single atom's nearest neighbour is its own image one cell
        // over -- the property a "molecule with unused fields" would not
        // have.
        let lattice = [[100, 0, 0], [0, 200, 0], [0, 0, 300]];
        let out = CrystalLatticeKernel
            .run(&encode_crystal_input(&lattice, &[(0, 0, 0)]))
            .unwrap();
        let mind2 = i128::from_le_bytes(out.output[16..].try_into().unwrap());
        assert_eq!(mind2, 100 * 100, "shortest lattice vector wins");
    }

    #[test]
    fn crystal_faults_are_the_descriptor_codes() {
        let kernel = CrystalLatticeKernel;
        let cube = [[1000i64, 0, 0], [0, 1000, 0], [0, 0, 1000]];
        assert_eq!(kernel.run(&[0u8; 10]).unwrap_err().exit_code, 2);
        assert_eq!(
            kernel
                .run(&encode_crystal_input(&cube, &[]))
                .unwrap_err()
                .exit_code,
            3
        );
        let big = [[1i64 << 31, 0, 0], [0, 1000, 0], [0, 0, 1000]];
        assert_eq!(
            kernel
                .run(&encode_crystal_input(&big, &[(0, 0, 0)]))
                .unwrap_err()
                .exit_code,
            4
        );
        assert_eq!(
            kernel
                .run(&encode_crystal_input(&cube, &[(-1, 0, 0)]))
                .unwrap_err()
                .exit_code,
            5
        );
        let flat = [[1000i64, 0, 0], [2000, 0, 0], [0, 0, 1000]];
        assert_eq!(
            kernel
                .run(&encode_crystal_input(&flat, &[(0, 0, 0)]))
                .unwrap_err()
                .exit_code,
            6
        );
        assert_eq!(
            kernel
                .run(&encode_crystal_input(&cube, &[(0, 0, 0), (0, 0, 0)]))
                .unwrap_err()
                .exit_code,
            7
        );
    }
}

// ---------------------------------------------------------------------
// Transformer kernel (fifth reference workload): integer single-head
// hardmax attention -- the Transformer Engine's model computation,
// behind the same contract and caveats as every other kernel.
// ---------------------------------------------------------------------

/// The canonical descriptor [`HardmaxAttentionKernel`] is identified
/// by. Hardmax is exact in integers; which token wins a tie is part of
/// the committed semantics (lowest index), so two implementations
/// cannot honestly disagree about it.
pub const HARDMAX_ATTENTION_DESCRIPTOR: &[u8] = concat!(
    "scout.native.attention-kernel.v1\n",
    "input: [d u32 LE][n u32 LE][n*d i32 LE X][d*d i32 Wq][d*d Wk][d*d Wv]\n",
    "bounds: 1<=d<=64; 1<=n<=1024; every value |v|<=2^20\n",
    "Q=X.Wq K=X.Wk V=X.Wv (i128 accumulation); S_ij = Q_i . K_j\n",
    "attend(i) = argmax_j S_ij, ties -> lowest j (hardmax); out_i = V_attend(i)\n",
    "output: n*d i64 LE; exit 0\n",
    "faults: 2=malformed, 3=dimensions, 4=value bound",
)
.as_bytes();

/// The transformer attention workload.
pub struct HardmaxAttentionKernel;

impl DeterministicProgram for HardmaxAttentionKernel {
    fn canonical_bytes(&self) -> &[u8] {
        HARDMAX_ATTENTION_DESCRIPTOR
    }

    fn run(&self, input: &[u8]) -> Result<NativeCompletion, NativeFault> {
        match execution_kernel::hardmax_attention(input) {
            Ok(output) => Ok(NativeCompletion {
                output,
                exit_code: 0,
            }),
            Err(fault) => Err(NativeFault {
                exit_code: fault.exit_code,
                detail: fault.detail.to_string(),
            }),
        }
    }
}

/// Encode an attention input: token matrix X (n rows of d values) and
/// the three d*d projection matrices, row-major.
pub fn encode_attention_input(
    d: u32,
    tokens: &[Vec<i32>],
    wq: &[Vec<i32>],
    wk: &[Vec<i32>],
    wv: &[Vec<i32>],
) -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(&d.to_le_bytes());
    bytes.extend_from_slice(&(tokens.len() as u32).to_le_bytes());
    for row in tokens.iter().chain(wq).chain(wk).chain(wv) {
        for value in row {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
    }
    bytes
}

#[cfg(test)]
mod attention_tests {
    use super::*;

    fn identity(d: usize) -> Vec<Vec<i32>> {
        (0..d)
            .map(|i| (0..d).map(|j| i32::from(i == j)).collect())
            .collect()
    }

    #[test]
    fn identity_weights_attend_to_the_largest_token() {
        // with identity projections, S_ij = X_i . X_j; every token
        // attends to the largest-norm token and outputs ITS features.
        let kernel = HardmaxAttentionKernel;
        let tokens = vec![vec![1, 0], vec![10, 0], vec![3, 4]];
        let eye = identity(2);
        let out = kernel
            .run(&encode_attention_input(2, &tokens, &eye, &eye, &eye))
            .unwrap();
        let values: Vec<i64> = out
            .output
            .chunks_exact(8)
            .map(|c| i64::from_le_bytes(c.try_into().unwrap()))
            .collect();
        assert_eq!(
            values,
            vec![10, 0, 10, 0, 10, 0],
            "every token attends to token 2 (token 3: S=30 beats self 25)"
        );
    }

    #[test]
    fn deterministic_and_weight_sensitive() {
        let kernel = HardmaxAttentionKernel;
        let tokens = vec![vec![1, 2], vec![3, 4]];
        let eye = identity(2);
        let mut wv = identity(2);
        let input_a = encode_attention_input(2, &tokens, &eye, &eye, &wv);
        assert_eq!(kernel.run(&input_a), kernel.run(&input_a));
        wv[0][0] = 2; // a changed weight is a changed computation
        let input_b = encode_attention_input(2, &tokens, &eye, &eye, &wv);
        assert_ne!(
            kernel.run(&input_a).unwrap().output,
            kernel.run(&input_b).unwrap().output
        );
    }

    #[test]
    fn faults_are_the_descriptor_codes() {
        let kernel = HardmaxAttentionKernel;
        assert_eq!(kernel.run(&[1, 2, 3]).unwrap_err().exit_code, 2);
        let eye = identity(2);
        let bad_dims = encode_attention_input(0, &[], &eye, &eye, &eye);
        assert_eq!(kernel.run(&bad_dims).unwrap_err().exit_code, 3);
        let big = vec![vec![1 << 21, 0], vec![0, 1]];
        let bound = encode_attention_input(2, &big, &eye, &eye, &eye);
        assert_eq!(kernel.run(&bound).unwrap_err().exit_code, 4);
    }
}
