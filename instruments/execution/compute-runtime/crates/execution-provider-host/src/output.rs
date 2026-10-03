use serde_json::{json, Value};
fn keys(data: &Value, names: &[&str]) -> Result<(), String> {
    let map = data.as_object().ok_or("output must be an object")?;
    if map.len() != names.len() || names.iter().any(|k| !map.contains_key(*k)) {
        return Err("output field set differs".into());
    }
    Ok(())
}
fn vector(data: &Value, key: &str, len: usize, integer: bool) -> Result<(), String> {
    let v = data[key]
        .as_array()
        .ok_or_else(|| format!("output {key} is not an array"))?;
    if v.len() != len {
        return Err(format!("output {key} shape differs"));
    }
    for x in v {
        if integer {
            if x.as_i64().is_none() {
                return Err("exact output is not signed integer".into());
            }
        } else if x
            .as_f64()
            .map(|n| !n.is_finite() || n.abs() > 1e100)
            .unwrap_or(true)
        {
            return Err("nonfinite or invalid numerical output".into());
        }
    }
    Ok(())
}
fn same_grid(a: &Value, b: &Value) -> bool {
    match (a.as_array(), b.as_array()) {
        (Some(a), Some(b)) => {
            a.len() == b.len()
                && a.iter()
                    .zip(b)
                    .all(|(x, y)| match (x.as_f64(), y.as_f64()) {
                        (Some(x), Some(y)) => x.is_finite() && y.is_finite() && x == y,
                        _ => false,
                    })
        }
        _ => false,
    }
}
pub fn check(profile: &str, input: &Value, output: &Value) -> Result<(), String> {
    if profile.starts_with("affine-") {
        keys(
            output,
            &[
                "rows",
                "columns",
                "denominator",
                "baseline_output",
                "contributions",
                "predicted_delta",
                "predicted_output",
                "model_output",
                "residual",
            ],
        )?;
        let m = input["rows"]
            .as_u64()
            .filter(|n| (1..=8).contains(n))
            .ok_or("invalid affine input rows")? as usize;
        let n = input["columns"]
            .as_u64()
            .filter(|n| (1..=8).contains(n))
            .ok_or("invalid affine input columns")? as usize;
        let exact = profile == "affine-d256.v1";
        if output["rows"] != input["rows"]
            || output["columns"] != input["columns"]
            || output["denominator"] != json!(if exact { 65536 } else { 1 })
        {
            return Err("output shape or arithmetic scale differs".into());
        }
        for k in [
            "baseline_output",
            "predicted_delta",
            "predicted_output",
            "model_output",
            "residual",
        ] {
            vector(output, k, m, exact)?;
        }
        vector(
            output,
            "contributions",
            m.checked_mul(n).ok_or("size overflow")?,
            exact,
        )?;
    } else if profile == "oscillator-tsit5.v1" || profile == "control-oscillator.v1" {
        if profile == "oscillator-tsit5.v1" {
            keys(
                output,
                &[
                    "schema",
                    "operation_id",
                    "request_id",
                    "time_s",
                    "q_m",
                    "v_m_s",
                    "energy_j",
                    "solver",
                ],
            )?;
        } else {
            keys(
                output,
                &[
                    "time_s",
                    "q_m",
                    "v_m_s",
                    "energy_j",
                    "state_order",
                    "solver",
                ],
            )?;
            if output["state_order"] != json!(["q", "v"]) {
                return Err("control output state ordering differs".into());
            }
        }
        let n = input["time_s"]
            .as_array()
            .ok_or("input grid missing")?
            .len();
        if n == 0 || n > 4096 || !same_grid(&output["time_s"], &input["time_s"]) {
            return Err("output time grid differs".into());
        }
        for k in ["q_m", "v_m_s", "energy_j"] {
            vector(output, k, n, false)?;
        }
        if !output["solver"].is_object() {
            return Err("solver declaration missing".into());
        }
    } else if profile == "design-qp.v1" {
        keys(
            output,
            &[
                "delta",
                "objective_value",
                "lower_residual",
                "upper_residual",
                "gradient",
                "solver",
            ],
        )?;
        let n = input["columns"]
            .as_u64()
            .filter(|n| (1..=8).contains(n))
            .ok_or("input QP columns invalid")? as usize;
        for k in ["delta", "lower_residual", "upper_residual", "gradient"] {
            vector(output, k, n, false)?;
        }
        if output["objective_value"]
            .as_f64()
            .map(|v| v.is_finite())
            .unwrap_or(false)
            == false
            || !output["solver"].is_object()
        {
            return Err("invalid QP numerical/solver output".into());
        }
    } else if profile == "oscillator-force-energy.v1" {
        keys(
            output,
            &[
                "time_s",
                "stiffness_n_m",
                "damping_n_s_m",
                "restoring_force_n",
                "damping_force_n",
                "net_force_n",
                "acceleration_m_s2",
                "potential_energy_j",
                "kinetic_energy_j",
                "energy_j",
            ],
        )?;
        let n = input["time_s"]
            .as_array()
            .ok_or("input grid missing")?
            .len();
        if !same_grid(&output["time_s"], &input["time_s"]) {
            return Err("force output time grid differs".into());
        }
        for k in [
            "restoring_force_n",
            "damping_force_n",
            "net_force_n",
            "acceleration_m_s2",
            "potential_energy_j",
            "kinetic_energy_j",
            "energy_j",
        ] {
            vector(output, k, n, false)?;
        }
    } else {
        return Err("unsupported output profile".into());
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn refuses_wrong_shape_scale_and_noninteger_exact() {
        let input = json!({"rows":1,"columns":1});
        let mut output = json!({"rows":1,"columns":1,"denominator":65536,"baseline_output":[0],"contributions":[0],"predicted_delta":[0],"predicted_output":[0],"model_output":[0],"residual":[0]});
        assert!(check("affine-d256.v1", &input, &output).is_ok());
        output["baseline_output"] = json!([0.0]);
        assert!(check("affine-d256.v1", &input, &output).is_err());
        output["baseline_output"] = json!([]);
        assert!(check("affine-d256.v1", &input, &output).is_err());
    }
}
