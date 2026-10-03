//! Bounded reaction transport validation. This checks a declared engine result,
//! not the analytical solution, physical validity, or package binary attestation.
use crate::{bytes, process, raw_sha, Host, Snapshot, Worker};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

pub const PROFILE: &str = "reaction-a-to-b.v1";
pub fn family(provider: &str) -> bool {
    matches!(provider, "catalyst" | "cantera")
}
pub fn semantics() -> Value {
    json!({"layout":"time-major","concentration_unit":"mol/m^3","production_rate_unit":"mol/m^3/s","time_unit":"s","temperature_unit":"K","volume_unit":"m^3","frame":"homogeneous-control-volume","clock":"declared-simulation-time"})
}
fn keys(value: &Value, expected: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("reaction object required")?;
    if object.len() != expected.len() || expected.iter().any(|k| !object.contains_key(*k)) {
        return Err("reaction object fields differ".into());
    }
    Ok(())
}
fn finite(value: &Value) -> Result<f64, String> {
    value
        .as_f64()
        .filter(|x| x.is_finite())
        .ok_or("finite reaction number required".into())
}
fn bounded(value: &Value, lo: f64, hi: f64) -> Result<f64, String> {
    let number = finite(value)?;
    if !(lo..=hi).contains(&number) {
        return Err("reaction value outside domain".into());
    }
    Ok(number)
}
fn digest(value: &Value) -> bool {
    value.as_str().is_some_and(|s| {
        s.len() == 71
            && s.starts_with("sha256:")
            && s[7..]
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}
fn identity(provider: &str, value: &Value, expected: &Value) -> Result<(), String> {
    let fields: &[&str] = if provider == "catalyst" {
        &[
            "schema",
            "julia_version",
            "platform",
            "threads",
            "packages",
            "worker_sha256",
            "project_sha256",
            "manifest_sha256",
        ]
    } else {
        &[
            "schema",
            "python_version",
            "platform",
            "packages",
            "worker_sha256",
            "requirements_sha256",
            "extension_sha256",
            "package_files_sha256",
        ]
    };
    keys(value, fields)?;
    if value["schema"] != format!("ciw.reaction-{provider}-identity.v1")
        || value["platform"].as_str().is_none_or(str::is_empty)
        || value[if provider == "catalyst" {
            "julia_version"
        } else {
            "python_version"
        }]
        .as_str()
        .is_none_or(str::is_empty)
        || (provider == "catalyst" && value["threads"].as_u64() != Some(1))
    {
        return Err("reaction worker identity differs".into());
    }
    let packages = value["packages"]
        .as_object()
        .ok_or("reaction package versions required")?;
    if packages.is_empty()
        || packages
            .iter()
            .any(|(k, v)| k.is_empty() || v.as_str().is_none_or(str::is_empty))
    {
        return Err("reaction package versions malformed".into());
    }
    for (key, hash) in expected.as_object().unwrap() {
        if value[key] != *hash {
            return Err(format!("reaction {key} differs from snapshot"));
        }
    }
    if provider == "cantera"
        && (!digest(&value["extension_sha256"]) || !digest(&value["package_files_sha256"]))
    {
        return Err("Cantera installation digest malformed".into());
    }
    Ok(())
}

pub fn check(provider: &str, input: &Value, output: &Value) -> Result<(), String> {
    keys(
        input,
        &[
            "model",
            "species_order",
            "initial_concentration_mol_m3",
            "rate_constant_s_inv",
            "temperature_k",
            "volume_m3",
            "time_s",
            "solver",
        ],
    )?;
    if input["model"] != "closed-isothermal-a-to-b.v1"
        || (input["species_order"] != json!(["A", "B"])
            && input["species_order"] != json!(["B", "A"]))
    {
        return Err("reaction model/species declaration differs".into());
    }
    let initial = input["initial_concentration_mol_m3"]
        .as_array()
        .ok_or("initial vector required")?;
    if initial.len() != 2 {
        return Err("initial vector dimension differs".into());
    }
    let total = bounded(&initial[0], 0.0, 1000.0)? + bounded(&initial[1], 0.0, 1000.0)?;
    if !(1e-6..=1000.0).contains(&total) {
        return Err("initial concentration total outside domain".into());
    }
    let rate = bounded(&input["rate_constant_s_inv"], 0.0, 10.0)?;
    bounded(&input["temperature_k"], 250.0, 500.0)?;
    bounded(&input["volume_m3"], 1e-6, 1.0)?;
    let grid = input["time_s"]
        .as_array()
        .ok_or("reaction time grid required")?;
    if !(2..=128).contains(&grid.len()) || finite(&grid[0])? != 0.0 {
        return Err("reaction time grid outside domain".into());
    }
    let mut last = -1.0;
    for item in grid {
        let t = bounded(item, 0.0, 100.0)?;
        if t <= last {
            return Err("reaction time grid not increasing".into());
        }
        last = t;
    }
    if rate * last > 30.0 {
        return Err("reaction duration outside domain".into());
    }
    keys(&input["solver"], &["reltol", "abstol_mol_m3", "max_steps"])?;
    if finite(&input["solver"]["reltol"])? != 1e-9
        || finite(&input["solver"]["abstol_mol_m3"])? != 1e-11
        || !input["solver"]["max_steps"]
            .as_u64()
            .is_some_and(|x| (1..=100000).contains(&x))
    {
        return Err("reaction solver settings differ".into());
    }
    keys(
        output,
        &[
            "model",
            "species_order",
            "time_s",
            "concentration_mol_m3",
            "production_rate_mol_m3_s",
            "mechanism",
            "solver",
        ],
    )?;
    if output["model"] != input["model"] || output["species_order"] != input["species_order"] {
        return Err("reaction output model/species echo differs".into());
    }
    let out_grid = output["time_s"]
        .as_array()
        .ok_or("reaction output time grid required")?;
    if out_grid.len() != grid.len() {
        return Err("reaction output grid dimension differs".into());
    }
    for (a, b) in grid.iter().zip(out_grid) {
        if finite(a)? != finite(b)? {
            return Err("reaction output grid echo differs".into());
        }
    }
    for field in ["concentration_mol_m3", "production_rate_mol_m3_s"] {
        let rows = output[field]
            .as_array()
            .ok_or("reaction output matrix required")?;
        if rows.len() != grid.len() {
            return Err("reaction output time dimension differs".into());
        }
        for row in rows {
            let row = row.as_array().ok_or("reaction output row required")?;
            if row.len() != 2 {
                return Err("reaction output species dimension differs".into());
            }
            for value in row {
                finite(value)?;
            }
        }
    }
    keys(
        &output["solver"],
        &[
            "algorithm",
            "retcode",
            "reltol",
            "abstol_mol_m3",
            "max_steps",
        ],
    )?;
    let algorithm = if provider == "catalyst" {
        "Catalyst.Tsit5"
    } else {
        "Cantera.CVODES"
    };
    if output["solver"]["algorithm"] != algorithm
        || output["solver"]["retcode"] != "Success"
        || finite(&output["solver"]["reltol"])? != 1e-9
        || finite(&output["solver"]["abstol_mol_m3"])? != 1e-11
        || output["solver"]["max_steps"].as_u64() != input["solver"]["max_steps"].as_u64()
    {
        return Err("reaction output solver differs".into());
    }
    keys(&output["mechanism"], &["format", "bytes_hex", "sha256"])?;
    let format = if provider == "catalyst" {
        "catalyst-code-v1"
    } else {
        "cantera-yaml-v1"
    };
    let encoded = output["mechanism"]["bytes_hex"]
        .as_str()
        .ok_or("mechanism bytes required")?;
    if output["mechanism"]["format"] != format
        || encoded.is_empty()
        || encoded.len() > 131072
        || encoded.len() % 2 != 0
        || !encoded
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("reaction mechanism representation malformed".into());
    }
    let raw: Vec<u8> = (0..encoded.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&encoded[i..i + 2], 16).unwrap())
        .collect();
    std::str::from_utf8(&raw).map_err(|_| "reaction mechanism is not UTF-8")?;
    if output["mechanism"]["sha256"] != raw_sha(&raw) {
        return Err("reaction mechanism digest differs".into());
    }
    Ok(())
}

impl Host {
    pub(crate) fn ensure_reaction_worker(&mut self) -> Result<(), String> {
        let provider = self.options.provider.as_str();
        let python = provider == "cantera";
        let project = self
            .options
            .project
            .as_ref()
            .unwrap()
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let worker = self
            .options
            .worker
            .as_ref()
            .unwrap()
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let executable = PathBuf::from(if python {
            self.options.python.as_ref().unwrap()
        } else {
            self.options.julia.as_ref().unwrap()
        })
        .canonicalize()
        .map_err(|e| e.to_string())?;
        let executable_hash = raw_sha(&bytes(&executable, 128 * 1024 * 1024)?);
        let worker_name = if python { "worker.py" } else { "worker.jl" };
        let mut files = vec![(worker_name, bytes(&worker, 1024 * 1024)?)];
        for name in if python {
            vec!["requirements.txt"]
        } else {
            vec!["Project.toml", "Manifest.toml"]
        } {
            files.push((name, bytes(&project.join(name), 1024 * 1024)?));
        }
        let scratch = std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("host executable parent missing")?
            .join(".ciw-provider-runs");
        fs::create_dir_all(&scratch).map_err(|e| e.to_string())?;
        let base = scratch.join(format!(
            "scr-{provider}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_nanos()
        ));
        fs::create_dir(&base).map_err(|e| e.to_string())?;
        let snapshot = Snapshot(base);
        let mut expected = json!({});
        for (name, raw) in &files {
            fs::write(snapshot.0.join(name), raw).map_err(|e| e.to_string())?;
            let key = match *name {
                "worker.py" | "worker.jl" => "worker_sha256",
                "Project.toml" => "project_sha256",
                "Manifest.toml" => "manifest_sha256",
                _ => "requirements_sha256",
            };
            expected[key] = raw_sha(raw).into();
        }
        let executable_str = executable.to_str().ok_or("nonUTF8 executable")?;
        let child_path = snapshot.0.join(worker_name);
        let child_path = child_path.to_str().ok_or("nonUTF8 worker")?;
        let mut child = if python {
            Worker::start_python(executable_str, child_path, self.options.timeout)?
        } else {
            Worker::start(
                executable_str,
                snapshot.0.to_str().ok_or("nonUTF8 project")?,
                child_path,
                self.options.timeout,
            )?
        };
        let request = json!({"schema":"ciw.native-interop-handshake-request.v1","request_id":"scr-host-handshake"});
        let raw = child
            .exchange(&serde_json::to_vec(&request).unwrap())
            .map_err(|e| {
                format!(
                    "{e}; stderr: {}",
                    String::from_utf8_lossy(&child.diagnostics())
                )
            })?;
        let hello = process::parse(&raw)?;
        keys(
            &hello,
            &["schema", "request_id", "status", "identity", "profiles"],
        )?;
        if hello["schema"] != "ciw.native-interop-handshake-response.v1"
            || hello["request_id"] != "scr-host-handshake"
            || hello["status"] != "ok"
            || hello["profiles"] != json!([PROFILE])
        {
            return Err("reaction handshake binding/capability differs".into());
        }
        identity(provider, &hello["identity"], &expected)?;
        if raw_sha(&bytes(&executable, 128 * 1024 * 1024)?) != executable_hash {
            return Err("reaction executable changed during startup".into());
        }
        self.runtime[if python {
            "python_executable_sha256"
        } else {
            "julia_executable_sha256"
        }] = executable_hash.into();
        for (key, value) in expected.as_object().unwrap() {
            self.runtime[key] = value.clone();
        }
        self.runtime["worker_identity"] = hello["identity"].clone();
        self.snapshot = Some(snapshot);
        self.worker = Some(child);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pair() -> (Value, Value) {
        let input = json!({"model":"closed-isothermal-a-to-b.v1","species_order":["A","B"],"initial_concentration_mol_m3":[1,0],"rate_constant_s_inv":1,"temperature_k":300,"volume_m3":0.1,"time_s":[0,1],"solver":{"reltol":1e-9,"abstol_mol_m3":1e-11,"max_steps":10000}});
        let output = json!({"model":input["model"],"species_order":input["species_order"],"time_s":[0.0,1.0],"concentration_mol_m3":[[1,0],[-1e-12,1.000000000001]],"production_rate_mol_m3_s":[[-1,1],[1e-12,-1e-12]],"mechanism":{"format":"catalyst-code-v1","bytes_hex":"616263","sha256":raw_sha(b"abc")},"solver":{"algorithm":"Catalyst.Tsit5","retcode":"Success","reltol":1e-9,"abstol_mol_m3":1e-11,"max_steps":10000}});
        (input, output)
    }
    #[test]
    fn reaction_shape_preserves_negative_samples_without_promoting_accuracy() {
        let (input, output) = pair();
        check("catalyst", &input, &output).unwrap();
        assert!(check("cantera", &input, &output).is_err());
    }
    #[test]
    fn reaction_shape_rejects_wrong_grid_species_solver_and_digest() {
        let (input, output) = pair();
        for pointer in [
            "/time_s/1",
            "/species_order/0",
            "/solver/max_steps",
            "/mechanism/sha256",
            "/concentration_mol_m3/0/1",
        ] {
            let mut bad = output.clone();
            *bad.pointer_mut(pointer).unwrap() = Value::Bool(true);
            assert!(check("catalyst", &input, &bad).is_err(), "{pointer}");
        }
        let mut bad = output.clone();
        bad["unbound"] = 1.into();
        assert!(check("catalyst", &input, &bad).is_err());
    }
    #[test]
    fn reaction_source_domain_is_not_weakened_by_valid_output_shape() {
        let (input, output) = pair();
        for pointer in [
            "/time_s/0",
            "/initial_concentration_mol_m3/0",
            "/rate_constant_s_inv",
            "/solver/max_steps",
        ] {
            let mut bad = input.clone();
            *bad.pointer_mut(pointer).unwrap() = Value::Bool(false);
            assert!(check("catalyst", &bad, &output).is_err(), "{pointer}");
        }
    }
}
