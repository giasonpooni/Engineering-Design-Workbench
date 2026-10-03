//! Transport and representation checks for the bounded interval worker.
//! Exact enclosure adequacy is checked independently by the caller's oracle.
use crate::{bytes, process, raw_sha, Host, Snapshot, Worker};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

pub const PROFILE: &str = "scalar-square-interval.v1";
pub fn semantics() -> Value {
    json!({"layout":"scalar","input_unit":"1","output_unit":"1","frame":"dimensionless-cartesian","clock":"not_applicable"})
}
pub fn configuration() -> Value {
    json!({"input_encoding":"reduced-rational","endpoint_encoding":"ieee754-binary64-hex","rounding":"correct","power":"slow","decoration":"com","guaranteed":true,"covariance_status":"not_applicable","calibration_status":"not_applicable"})
}
fn keys(value: &Value, expected: &[&str]) -> Result<(), String> {
    let object = value.as_object().ok_or("interval object required")?;
    if object.len() != expected.len() || expected.iter().any(|k| !object.contains_key(*k)) {
        return Err("interval object fields differ".into());
    }
    Ok(())
}
#[derive(Clone, Copy)]
struct Rational {
    n: i128,
    d: i128,
}
impl Rational {
    fn read(value: &Value) -> Result<Self, String> {
        keys(value, &["numerator", "denominator"])?;
        let n = value["numerator"]
            .as_i64()
            .ok_or("integer rational numerator required")?;
        let d = value["denominator"]
            .as_i64()
            .ok_or("integer rational denominator required")?;
        if !(-1_000_000..=1_000_000).contains(&n) || !(1..=1_000_000).contains(&d) {
            return Err("rational integer bound exceeded".into());
        }
        let (mut a, mut b) = (n.abs(), d);
        while b != 0 {
            (a, b) = (b, a % b);
        }
        if a != 1 {
            return Err("rational must be reduced (zero is 0/1)".into());
        }
        Ok(Self {
            n: n.into(),
            d: d.into(),
        })
    }
    fn le(self, other: Self) -> bool {
        self.n * other.d <= other.n * self.d
    }
    fn add(self, other: Self) -> Self {
        Self {
            n: self.n * other.d + other.n * self.d,
            d: self.d * other.d,
        }
    }
    fn bounded(self, lo: i128, hi: i128) -> bool {
        lo * self.d <= self.n && self.n <= hi * self.d
    }
}
pub fn check_input(input: &Value) -> Result<(), String> {
    keys(
        input,
        &[
            "model",
            "x",
            "variation_lower",
            "variation_upper",
            "error_limit",
        ],
    )?;
    if input["model"] != "scalar-square.v1" {
        return Err("interval model differs".into());
    }
    let x = Rational::read(&input["x"])?;
    let lo = Rational::read(&input["variation_lower"])?;
    let hi = Rational::read(&input["variation_upper"])?;
    let epsilon = Rational::read(&input["error_limit"])?;
    // At most 1e6 in each factor: i128 products remain comfortably bounded.
    if !x.bounded(-100, 100)
        || !lo.bounded(-200, 200)
        || !hi.bounded(-200, 200)
        || !lo.le(hi)
        || !x.add(lo).bounded(-100, 100)
        || !x.add(hi).bounded(-100, 100)
        || !epsilon.bounded(0, 40000)
    {
        return Err("interval input outside declared domain".into());
    }
    Ok(())
}
fn endpoint(value: &Value) -> Result<f64, String> {
    let encoded = value.as_str().ok_or("binary64 endpoint hex required")?;
    if encoded.len() != 16
        || !encoded
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("binary64 endpoint representation differs".into());
    }
    let bits = u64::from_str_radix(encoded, 16).map_err(|_| "binary64 endpoint malformed")?;
    let value = f64::from_bits(bits);
    if !value.is_finite() {
        return Err("finite interval endpoint required".into());
    }
    Ok(value)
}
pub fn check_output(output: &Value) -> Result<(), String> {
    keys(
        output,
        &[
            "model",
            "expression",
            "enclosure",
            "requirement",
            "configuration",
        ],
    )?;
    keys(
        &output["enclosure"],
        &["lower_hex", "upper_hex", "decoration", "guaranteed"],
    )?;
    if output["model"] != "scalar-square.v1"
        || output["expression"] != "u^2-error_limit"
        || output["configuration"] != configuration()
        || output["enclosure"]["decoration"] != "com"
        || output["enclosure"]["guaranteed"] != true
    {
        return Err("interval output contract or configuration differs".into());
    }
    let lo = endpoint(&output["enclosure"]["lower_hex"])?;
    let hi = endpoint(&output["enclosure"]["upper_hex"])?;
    if lo > hi {
        return Err("interval endpoints reversed".into());
    }
    let expected = if hi <= 0.0 {
        "holds_throughout"
    } else if lo > 0.0 {
        "fails_throughout"
    } else {
        "inconclusive"
    };
    if output["requirement"] != expected {
        return Err("interval classification differs from enclosure".into());
    }
    Ok(())
}
fn identity(value: &Value, expected: &Value) -> Result<(), String> {
    keys(
        value,
        &[
            "schema",
            "julia_version",
            "platform",
            "threads",
            "packages",
            "worker_sha256",
            "project_sha256",
            "manifest_sha256",
        ],
    )?;
    keys(&value["packages"], &["IntervalArithmetic", "JSON3"])?;
    if value["schema"] != "ciw.interval-julia-identity.v1"
        || value["julia_version"] != "1.10.12"
        || value["platform"].as_str().is_none_or(str::is_empty)
        || value["threads"].as_u64() != Some(1)
        || value["packages"]
            .as_object()
            .unwrap()
            .values()
            .any(|v| v.as_str().is_none_or(str::is_empty))
    {
        return Err("interval worker identity differs".into());
    }
    for (key, hash) in expected.as_object().unwrap() {
        if value[key] != *hash {
            return Err(format!("interval {key} differs from snapshot"));
        }
    }
    Ok(())
}
impl Host {
    pub(crate) fn ensure_interval_worker(&mut self) -> Result<(), String> {
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
        let executable = PathBuf::from(self.options.julia.as_ref().unwrap())
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let executable_hash = raw_sha(&bytes(&executable, 128 * 1024 * 1024)?);
        let files = [
            ("worker.jl", "worker_sha256", bytes(&worker, 1024 * 1024)?),
            (
                "Project.toml",
                "project_sha256",
                bytes(&project.join("Project.toml"), 1024 * 1024)?,
            ),
            (
                "Manifest.toml",
                "manifest_sha256",
                bytes(&project.join("Manifest.toml"), 1024 * 1024)?,
            ),
        ];
        let scratch = std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("host executable parent missing")?
            .join(".ciw-provider-runs");
        fs::create_dir_all(&scratch).map_err(|e| e.to_string())?;
        let base = scratch.join(format!(
            "scr-intervals-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_nanos()
        ));
        fs::create_dir(&base).map_err(|e| e.to_string())?;
        let snapshot = Snapshot(base);
        let mut expected = json!({});
        for (name, key, raw) in &files {
            fs::write(snapshot.0.join(name), raw).map_err(|e| e.to_string())?;
            expected[key] = raw_sha(raw).into();
        }
        let mut child = Worker::start(
            executable.to_str().ok_or("nonUTF8 executable")?,
            snapshot.0.to_str().ok_or("nonUTF8 project")?,
            snapshot
                .0
                .join("worker.jl")
                .to_str()
                .ok_or("nonUTF8 worker")?,
            self.options.timeout,
        )?;
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
            return Err("interval handshake binding/capability differs".into());
        }
        identity(&hello["identity"], &expected)?;
        if raw_sha(&bytes(&executable, 128 * 1024 * 1024)?) != executable_hash {
            return Err("interval executable changed during startup".into());
        }
        self.runtime["julia_executable_sha256"] = executable_hash.into();
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
    fn rational(n: i64, d: i64) -> Value {
        json!({"numerator":n,"denominator":d})
    }
    fn input() -> Value {
        json!({"model":"scalar-square.v1","x":rational(0,1),"variation_lower":rational(-1,2),"variation_upper":rational(1,2),"error_limit":rational(1,4)})
    }
    fn output(lo: f64, hi: f64, requirement: &str) -> Value {
        json!({"model":"scalar-square.v1","expression":"u^2-error_limit","enclosure":{"lower_hex":format!("{:016x}",lo.to_bits()),"upper_hex":format!("{:016x}",hi.to_bits()),"decoration":"com","guaranteed":true},"configuration":configuration(),"requirement":requirement})
    }
    #[test]
    fn reduced_rational_domain_is_exact_and_rejects_coercion() {
        check_input(&input()).unwrap();
        for bad in [
            rational(0, 2),
            rational(2, 4),
            rational(1, 0),
            rational(1, -1),
            rational(1_000_001, 1),
            json!({"numerator":true,"denominator":1}),
            json!({"numerator":1.0,"denominator":2}),
        ] {
            let mut source = input();
            source["variation_lower"] = bad;
            assert!(check_input(&source).is_err());
        }
        let mut source = input();
        source["variation_lower"] = rational(1, 1);
        assert!(check_input(&source).is_err());
        let mut source = input();
        source["x"] = rational(100, 1);
        assert!(check_input(&source).is_err());
        source["variation_upper"] = rational(0, 1);
        check_input(&source).unwrap();
        source["variation_upper"] = rational(1, 1_000_000);
        assert!(check_input(&source).is_err());
    }
    #[test]
    fn endpoint_classification_is_not_an_exact_oracle() {
        for (lo, hi, claim) in [
            (-0.25, 0.0, "holds_throughout"),
            (0.1, 1.0, "fails_throughout"),
            (-0.25, 1e-18, "inconclusive"),
            (-0.0, 0.0, "holds_throughout"),
        ] {
            check_output(&output(lo, hi, claim)).unwrap();
        }
        assert!(check_output(&output(0.0, 1.0, "fails_throughout")).is_err());
        assert!(check_output(&output(1.0, -1.0, "inconclusive")).is_err());
        assert!(check_output(&output(f64::NAN, 1.0, "inconclusive")).is_err());
        assert!(check_output(&output(0.0, f64::INFINITY, "inconclusive")).is_err());
    }
    #[test]
    fn strict_enclosure_and_policy_fields_are_required() {
        for pointer in [
            "/configuration/rounding",
            "/configuration/power",
            "/configuration/guaranteed",
            "/enclosure/guaranteed",
            "/enclosure/decoration",
            "/enclosure/lower_hex",
            "/model",
            "/expression",
        ] {
            let mut result = output(-0.25, 0.0, "holds_throughout");
            *result.pointer_mut(pointer).unwrap() = Value::Null;
            assert!(check_output(&result).is_err(), "{pointer}");
        }
        let mut result = output(-0.25, 0.0, "holds_throughout");
        result["enclosure"]["lower_hex"] = "BFD0000000000000".into();
        assert!(check_output(&result).is_err());
    }
    #[test]
    fn worker_identity_is_separate_and_snapshot_bound() {
        let expected = json!({"worker_sha256":raw_sha(b"worker"),"project_sha256":raw_sha(b"project"),"manifest_sha256":raw_sha(b"manifest")});
        let mut id = expected.clone();
        for (key,value) in json!({"schema":"ciw.interval-julia-identity.v1","julia_version":"1.10.12","platform":"test-only","threads":1,"packages":{"IntervalArithmetic":"1","JSON3":"1"}}).as_object().unwrap() { id[key] = value.clone(); }
        identity(&id, &expected).unwrap();
        for key in [
            "schema",
            "threads",
            "julia_version",
            "packages",
            "worker_sha256",
        ] {
            let mut bad = id.clone();
            bad[key] = Value::Null;
            assert!(identity(&bad, &expected).is_err());
        }
        id["packages"]["unqualified"] = "1".into();
        assert!(identity(&id, &expected).is_err());
    }
}
