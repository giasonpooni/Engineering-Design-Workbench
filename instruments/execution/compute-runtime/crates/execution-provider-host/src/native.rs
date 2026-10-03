use crate::ffi::bridge;
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Affine<T> {
    rows: u32,
    columns: u32,
    a_row_major: Vec<T>,
    b: Vec<T>,
    x0: Vec<T>,
    delta_x: Vec<T>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Model {
    mass_kg: f64,
    omega_0_rad_s: f64,
    gamma_s_inv: f64,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Force {
    model: Model,
    time_s: Vec<f64>,
    q_m: Vec<f64>,
    v_m_s: Vec<f64>,
}

fn shape<T>(p: &Affine<T>) -> Result<(), String> {
    let count = p
        .rows
        .checked_mul(p.columns)
        .ok_or("affine size overflow")? as usize;
    if !(1..=8).contains(&p.rows)
        || !(1..=8).contains(&p.columns)
        || p.a_row_major.len() != count
        || p.b.len() != p.rows as usize
        || p.x0.len() != p.columns as usize
        || p.delta_x.len() != p.columns as usize
    {
        return Err("invalid native affine shape".into());
    }
    Ok(())
}

pub fn compute(profile: &str, raw: &str) -> Result<Value, String> {
    match profile {
        "affine-binary64.v1" => {
            let p: Affine<f64> = serde_json::from_str(raw).map_err(|e| e.to_string())?;
            shape(&p)?;
            if [&p.a_row_major, &p.b, &p.x0, &p.delta_x]
                .iter()
                .flat_map(|v| v.iter())
                .any(|v| !v.is_finite() || v.abs() > 1e6)
            {
                return Err("native binary64 domain differs".into());
            }
            let o = bridge::affine_f64(p.rows, p.columns, &p.a_row_major, &p.b, &p.x0, &p.delta_x)
                .map_err(|e| e.to_string())?;
            Ok(
                json!({"rows":p.rows,"columns":p.columns,"denominator":1,"baseline_output":o.baseline_output,"contributions":o.contributions,"predicted_delta":o.predicted_delta,"predicted_output":o.predicted_output,"model_output":o.model_output,"residual":o.residual}),
            )
        }
        "affine-d256.v1" => {
            let p: Affine<i64> = serde_json::from_str(raw).map_err(|e| e.to_string())?;
            shape(&p)?;
            if [&p.a_row_major, &p.b, &p.x0, &p.delta_x]
                .iter()
                .flat_map(|v| v.iter())
                .any(|v| !(-4096..=4096).contains(v))
            {
                return Err("native D256 domain differs".into());
            }
            let o = bridge::affine_d256(p.rows, p.columns, &p.a_row_major, &p.b, &p.x0, &p.delta_x)
                .map_err(|e| e.to_string())?;
            Ok(
                json!({"rows":p.rows,"columns":p.columns,"denominator":65536,"baseline_output":o.baseline_output,"contributions":o.contributions,"predicted_delta":o.predicted_delta,"predicted_output":o.predicted_output,"model_output":o.model_output,"residual":o.residual}),
            )
        }
        "oscillator-force-energy.v1" => {
            let p: Force = serde_json::from_str(raw).map_err(|e| e.to_string())?;
            if p.time_s.is_empty()
                || p.time_s.len() > 4096
                || p.q_m.len() != p.time_s.len()
                || p.v_m_s.len() != p.time_s.len()
                || p.time_s[0] != 0.0
                || p.time_s
                    .iter()
                    .any(|t| !t.is_finite() || *t < 0.0 || *t > 12.0)
                || p.time_s.windows(2).any(|w| w[1] <= w[0])
            {
                return Err("invalid declared oscillator sample time grid".into());
            }
            if !p.model.mass_kg.is_finite()
                || p.model.mass_kg <= 1e-12
                || p.model.mass_kg > 100.0
                || !p.model.omega_0_rad_s.is_finite()
                || p.model.omega_0_rad_s <= 1e-12
                || p.model.omega_0_rad_s > 20.0
                || !p.model.gamma_s_inv.is_finite()
                || p.model.gamma_s_inv < 0.0
                || p.model.gamma_s_inv > p.model.omega_0_rad_s / 2.0
                || p.q_m
                    .iter()
                    .chain(&p.v_m_s)
                    .any(|v| !v.is_finite() || v.abs() > 1000.0)
            {
                return Err("native oscillator physical domain differs".into());
            }
            let o = bridge::oscillator_force(
                p.model.mass_kg,
                p.model.omega_0_rad_s,
                p.model.gamma_s_inv,
                &p.q_m,
                &p.v_m_s,
            )
            .map_err(|e| e.to_string())?;
            Ok(
                json!({"time_s":p.time_s,"stiffness_n_m":o.stiffness_n_m,"damping_n_s_m":o.damping_n_s_m,"restoring_force_n":o.restoring_force_n,"damping_force_n":o.damping_force_n,"net_force_n":o.net_force_n,"acceleration_m_s2":o.acceleration_m_s2,"potential_energy_j":o.potential_energy_j,"kinetic_energy_j":o.kinetic_energy_j,"energy_j":o.energy_j}),
            )
        }
        _ => Err("unsupported native profile".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rectangular_affine_cpp_golden() {
        let r=compute("affine-binary64.v1",r#"{"rows":2,"columns":3,"a_row_major":[2,1,-1,-1,3,2],"b":[5,-2],"x0":[3,4,2],"delta_x":[0.25,-0.5,0.125]}"#).unwrap();
        assert_eq!(r["baseline_output"], json!([13.0, 11.0]));
        assert_eq!(r["predicted_delta"], json!([-0.125, -1.5]));
        assert_eq!(r["model_output"], json!([12.875, 9.5]));
        assert_eq!(r["residual"], json!([0.0, 0.0]));
    }
    #[test]
    fn exact_cpp_golden_and_shifted_state() {
        let r=compute("affine-d256.v1",r#"{"rows":2,"columns":3,"a_row_major":[512,256,-256,-256,768,512],"b":[1280,-512],"x0":[768,1024,512],"delta_x":[64,-128,32]}"#).unwrap();
        assert_eq!(r["baseline_output"], json!([851968, 720896]));
        assert_eq!(r["predicted_delta"], json!([-8192, -98304]));
        assert_eq!(r["model_output"], json!([843776, 622592]));
        let s = bridge::affine_d256(1, 1, &[4096], &[4096], &[4096], &[4096]).unwrap();
        assert_eq!(s.model_output, vec![34603008]);
    }
    #[test]
    fn oscillator_nonunit_mass_golden() {
        let r=compute("oscillator-force-energy.v1",r#"{"model":{"mass_kg":2,"omega_0_rad_s":2,"gamma_s_inv":0.1},"time_s":[0],"q_m":[1],"v_m_s":[-0.25]}"#).unwrap();
        assert_eq!(r["stiffness_n_m"], json!(8.0));
        assert_eq!(r["damping_n_s_m"], json!(0.4));
        assert_eq!(r["energy_j"], json!([4.0625]));
        assert_eq!(r["acceleration_m_s2"], json!([-3.95]));
    }
    #[test]
    fn typed_cpp_refuses_bad_shapes_nonfinite_and_exact_bounds() {
        assert!(bridge::affine_f64(0, 1, &[], &[], &[1.0], &[1.0]).is_err());
        assert!(bridge::affine_f64(1, 1, &[f64::NAN], &[0.0], &[1.0], &[1.0]).is_err());
        assert!(bridge::affine_d256(1, 1, &[i64::MAX], &[0], &[1], &[1]).is_err());
        assert!(bridge::oscillator_force(0.0, 2.0, 0.1, &[1.0], &[0.0]).is_err());
    }
}
