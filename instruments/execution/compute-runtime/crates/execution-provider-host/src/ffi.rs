#[cxx::bridge(namespace = "scr")]
pub mod bridge {
    #[derive(Debug)]
    struct FloatResponse {
        baseline_output: Vec<f64>,
        contributions: Vec<f64>,
        predicted_delta: Vec<f64>,
        predicted_output: Vec<f64>,
        model_output: Vec<f64>,
        residual: Vec<f64>,
    }
    #[derive(Debug)]
    struct ExactResponse {
        baseline_output: Vec<i64>,
        contributions: Vec<i64>,
        predicted_delta: Vec<i64>,
        predicted_output: Vec<i64>,
        model_output: Vec<i64>,
        residual: Vec<i64>,
    }
    #[derive(Debug)]
    struct ForceResponse {
        stiffness_n_m: f64,
        damping_n_s_m: f64,
        restoring_force_n: Vec<f64>,
        damping_force_n: Vec<f64>,
        net_force_n: Vec<f64>,
        acceleration_m_s2: Vec<f64>,
        potential_energy_j: Vec<f64>,
        kinetic_energy_j: Vec<f64>,
        energy_j: Vec<f64>,
    }
    unsafe extern "C++" {
        include!("kernels.h");
        fn affine_f64(
            rows: u32,
            columns: u32,
            a: &[f64],
            b: &[f64],
            x: &[f64],
            delta: &[f64],
        ) -> Result<FloatResponse>;
        fn affine_d256(
            rows: u32,
            columns: u32,
            a: &[i64],
            b: &[i64],
            x: &[i64],
            delta: &[i64],
        ) -> Result<ExactResponse>;
        fn oscillator_force(
            mass: f64,
            omega: f64,
            gamma: f64,
            q: &[f64],
            v: &[f64],
        ) -> Result<ForceResponse>;
    }
}
