mod ffi;
mod interval;
mod native;
mod output;
mod process;
mod reaction;
use execution_core::{
    commit, sha256, BackendKind, ExecutionOutcome, ExecutionTrace, InputIdentity, OutputIdentity,
    ProgramIdentity, SPECIFICATION_TAG,
};
use process::{Worker, MAX_DIAGNOSTICS, MAX_FRAME, MAX_RESPONSE};
use serde::Deserialize;
use serde_json::{json, value::RawValue, Value};
use std::{
    collections::HashSet,
    fs, io,
    path::{Path, PathBuf},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const FLOAT_PROFILES: &[&str] = &["affine-binary64.v1", "oscillator-force-energy.v1"];
const JULIA_PROFILES: &[&str] = &[
    "affine-binary64.v1",
    "affine-d256.v1",
    "oscillator-tsit5.v1",
    "control-oscillator.v1",
    "design-qp.v1",
];
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    schema: String,
    request_id: String,
    parent_execution_id: String,
    profile: String,
    arithmetic: String,
    semantics: Box<RawValue>,
    payload: Box<RawValue>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Hello {
    schema: String,
    request_id: String,
}
struct Options {
    provider: String,
    julia: Option<String>,
    python: Option<String>,
    project: Option<PathBuf>,
    worker: Option<PathBuf>,
    timeout: Duration,
}
fn options() -> Result<Options, String> {
    let mut args = std::env::args().skip(1);
    let mut pairs = std::collections::BTreeMap::new();
    while let Some(key) = args.next() {
        if ![
            "--provider",
            "--julia",
            "--python",
            "--project",
            "--worker",
            "--timeout-ms",
        ]
        .contains(&key.as_str())
        {
            return Err(format!("unknown trusted-host argument {key}"));
        }
        let value = args.next().ok_or("argument missing value")?;
        if pairs.insert(key, value).is_some() {
            return Err("duplicate host argument".into());
        }
    }
    let provider = pairs
        .remove("--provider")
        .ok_or("--provider cpp|julia|catalyst|cantera|intervals required")?;
    if !["cpp", "julia", "catalyst", "cantera", "intervals"].contains(&provider.as_str()) {
        return Err("unsupported provider".into());
    }
    let timeout = pairs
        .remove("--timeout-ms")
        .unwrap_or_else(|| "120000".into())
        .parse::<u64>()
        .map_err(|_| "invalid timeout")?;
    if !(1..=600000).contains(&timeout) {
        return Err("timeout outside 1..600000 milliseconds".into());
    }
    let out = Options {
        provider,
        julia: pairs.remove("--julia"),
        python: pairs.remove("--python"),
        project: pairs.remove("--project").map(PathBuf::from),
        worker: pairs.remove("--worker").map(PathBuf::from),
        timeout: Duration::from_millis(timeout),
    };
    if ["julia", "catalyst", "intervals"].contains(&out.provider.as_str())
        && (out.julia.is_none() || out.project.is_none() || out.worker.is_none())
    {
        return Err("Julia requires explicit executable, project, worker".into());
    }
    if out.provider == "cantera"
        && (out.python.is_none() || out.project.is_none() || out.worker.is_none())
    {
        return Err("Cantera requires explicit Python executable, project, worker".into());
    }
    if (out.provider != "cantera" && out.python.is_some())
        || (out.provider == "cantera" && out.julia.is_some())
    {
        return Err("provider refuses unused interpreter configuration".into());
    }
    if out.provider == "cpp"
        && (out.julia.is_some() || out.project.is_some() || out.worker.is_some())
    {
        return Err("native provider refuses unused Julia configuration".into());
    }
    Ok(out)
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn raw_sha(bytes: &[u8]) -> String {
    format!("sha256:{}", hex(&sha256(bytes)))
}
fn bytes(path: &Path, max: usize) -> Result<Vec<u8>, String> {
    let data = fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    if data.len() > max {
        return Err("runtime file exceeds budget".into());
    }
    Ok(data)
}
fn token(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 160
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"-_:./".contains(&c))
}
fn semantic(profile: &str) -> Value {
    if profile == interval::PROFILE {
        interval::semantics()
    } else if profile == reaction::PROFILE {
        reaction::semantics()
    } else if profile.starts_with("affine-") || profile == "design-qp.v1" {
        json!({"layout":"row-major","input_units":"dimensionless","output_units":"dimensionless","frame":"declared-cartesian","clock":"not-applicable"})
    } else {
        json!({"layout":"row-major","input_units":"SI","output_units":"SI","frame":"one-dimensional-inertial","clock":"declared-simulation-time"})
    }
}
fn validate(r: &Request, provider: &str) -> Result<(), String> {
    if r.schema != "ciw.native-interop-request.v1"
        || !token(&r.request_id)
        || !token(&r.parent_execution_id)
    {
        return Err("invalid transport schema or occurrence references".into());
    }
    let allowed = if provider == "cpp" {
        FLOAT_PROFILES.contains(&r.profile.as_str()) || r.profile == "affine-d256.v1"
    } else if reaction::family(provider) {
        r.profile == reaction::PROFILE
    } else if provider == "intervals" {
        r.profile == interval::PROFILE
    } else {
        JULIA_PROFILES.contains(&r.profile.as_str())
    };
    if !allowed {
        return Err("unsupported profile for bound provider".into());
    }
    if r.arithmetic
        != if r.profile == "affine-d256.v1" {
            "exact-d256"
        } else if r.profile == interval::PROFILE {
            "outward-binary64"
        } else {
            "binary64"
        }
    {
        return Err("arithmetic profile differs".into());
    }
    if process::parse(r.semantics.get().as_bytes())? != semantic(&r.profile) {
        return Err("units/layout/frame/clock declaration differs".into());
    }
    Ok(())
}
struct Snapshot(PathBuf);
impl Drop for Snapshot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
struct Host {
    options: Options,
    runtime: Value,
    worker: Option<Worker>,
    snapshot: Option<Snapshot>,
    trace: ExecutionTrace,
    seen: HashSet<String>,
    child_counter: u64,
}
impl Host {
    fn new(options: Options) -> Result<Self, String> {
        let executable = std::env::current_exe().map_err(|e| e.to_string())?;
        let runtime = json!({"provider":options.provider,"host_executable_sha256":raw_sha(&bytes(&executable,128*1024*1024)?),"native_source_id":env!("SCR_NATIVE_SOURCE_ID"),"native_build":include_str!(concat!(env!("OUT_DIR"),"/native-build.txt")),"bridge_version":"1.0.202"});
        Ok(Self {
            options,
            runtime,
            worker: None,
            snapshot: None,
            trace: ExecutionTrace::new(),
            seen: HashSet::new(),
            child_counter: 0,
        })
    }
    fn ensure_worker(&mut self) -> Result<(), String> {
        if self.options.provider == "intervals" && self.worker.is_none() {
            return self.ensure_interval_worker();
        }
        if reaction::family(&self.options.provider) && self.worker.is_none() {
            return self.ensure_reaction_worker();
        }
        if self.options.provider != "julia" || self.worker.is_some() {
            return Ok(());
        }
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
        let old_worker = project
            .parent()
            .ok_or("missing runtime parent")?
            .join("julia-oscillator/oscillator_worker.jl");
        let julia_digest = raw_sha(&bytes(&executable, 128 * 1024 * 1024)?);
        let worker_bytes = bytes(&worker, 1024 * 1024)?;
        let project_bytes = bytes(&project.join("Project.toml"), 1024 * 1024)?;
        let manifest_bytes = bytes(&project.join("Manifest.toml"), 1024 * 1024)?;
        let old_bytes = bytes(&old_worker, 1024 * 1024)?;
        let stem = format!(
            "scr-native-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_nanos()
        );
        let scratch = std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("host executable parent missing")?
            .join(".ciw-provider-runs");
        fs::create_dir_all(&scratch).map_err(|e| e.to_string())?;
        let base = scratch.join(stem);
        fs::create_dir(&base).map_err(|e| e.to_string())?;
        let snapshot = Snapshot(base);
        let native = snapshot.0.join("native-interop");
        let old = snapshot.0.join("julia-oscillator");
        fs::create_dir(&native)
            .and_then(|_| fs::create_dir(&old))
            .map_err(|e| e.to_string())?;
        for (path, data) in [
            (native.join("worker.jl"), &worker_bytes),
            (native.join("Project.toml"), &project_bytes),
            (native.join("Manifest.toml"), &manifest_bytes),
            (old.join("oscillator_worker.jl"), &old_bytes),
        ] {
            fs::write(path, data).map_err(|e| e.to_string())?;
        }
        let mut child = Worker::start(
            executable.to_str().ok_or("nonUTF8 executable")?,
            native.to_str().ok_or("nonUTF8 project")?,
            native.join("worker.jl").to_str().ok_or("nonUTF8 worker")?,
            self.options.timeout,
        )?;
        let request = json!({"schema":"ciw.native-interop-handshake-request.v1","request_id":"scr-host-handshake"});
        let response = child
            .exchange(&serde_json::to_vec(&request).unwrap())
            .map_err(|e| {
                format!(
                    "{e}; stderr: {}",
                    String::from_utf8_lossy(&child.diagnostics())
                )
            })?;
        let hello = process::parse(&response)?;
        if hello["schema"] != "ciw.native-interop-handshake-response.v1"
            || hello["request_id"] != "scr-host-handshake"
            || hello["status"] != "ok"
            || !hello["identity"].is_object()
            || hello["profiles"] != json!(JULIA_PROFILES)
        {
            return Err("Julia handshake binding/capability differs".into());
        }
        if raw_sha(&bytes(&executable, 128 * 1024 * 1024)?) != julia_digest {
            return Err("Julia executable changed during startup".into());
        }
        self.runtime["julia_executable_sha256"] = julia_digest.into();
        self.runtime["worker_sha256"] = raw_sha(&worker_bytes).into();
        self.runtime["project_sha256"] = raw_sha(&project_bytes).into();
        self.runtime["manifest_sha256"] = raw_sha(&manifest_bytes).into();
        self.runtime["oscillator_worker_sha256"] = raw_sha(&old_bytes).into();
        self.runtime["worker_identity"] = hello["identity"].clone();
        self.snapshot = Some(snapshot);
        self.worker = Some(child);
        Ok(())
    }
    fn handshake(&mut self, raw: &[u8]) -> Result<Value, String> {
        let h: Hello = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
        if h.schema != "ciw.native-interop-handshake-request.v1" || !token(&h.request_id) {
            return Err("invalid handshake".into());
        }
        self.ensure_worker()?;
        let profiles = if self.options.provider == "cpp" {
            vec![
                "affine-binary64.v1",
                "affine-d256.v1",
                "oscillator-force-energy.v1",
            ]
        } else if reaction::family(&self.options.provider) {
            vec![reaction::PROFILE]
        } else if self.options.provider == "intervals" {
            vec![interval::PROFILE]
        } else {
            JULIA_PROFILES.to_vec()
        };
        Ok(
            json!({"schema":"ciw.native-interop-handshake-response.v1","request_id":h.request_id,"status":"ok","identity":self.runtime,"profiles":profiles,"limits":{"request_bytes":MAX_FRAME,"response_bytes":MAX_RESPONSE,"diagnostic_bytes":MAX_DIAGNOSTICS,"timeout_ms":self.options.timeout.as_millis(),"max_requests":256},"cancellation":"unsupported"}),
        )
    }
    fn execute(&mut self, raw: &[u8]) -> Result<(Value, bool), String> {
        let label = match self.options.provider.as_str() {
            "cantera" => "Cantera",
            "catalyst" => "Catalyst",
            "intervals" => "IntervalArithmetic",
            _ => "Julia",
        };
        let r: Request = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
        validate(&r, &self.options.provider)?;
        if self.seen.len() >= 256 || !self.seen.insert(r.request_id.clone()) {
            return Err("repeated request ID or stream request limit".into());
        }
        self.ensure_worker()?;
        let program_bytes =
            serde_json::to_vec(&json!({"profile":r.profile,"runtime":self.runtime})).unwrap();
        let configuration_bytes = format!(
            "{{\"arithmetic\":{},\"semantics\":{}}}",
            serde_json::to_string(&r.arithmetic).unwrap(),
            r.semantics.get()
        )
        .into_bytes();
        let input_bytes = r.payload.get().as_bytes();
        let program = ProgramIdentity::of(&program_bytes);
        let input = InputIdentity::of(input_bytes);
        let specification = commit(
            SPECIFICATION_TAG,
            &[&program_bytes, &configuration_bytes, input_bytes],
        );
        let occurrence = self.trace.begin(program, input, BackendKind::Native);
        let started = Instant::now();
        let mut child_response = None;
        let mut child_id = None;
        let mut child_occurrence = None;
        let result: Result<Value, String> = if self.options.provider == "cpp" {
            native::compute(&r.profile, r.payload.get())
        } else {
            let preflight = if self.options.provider == "intervals" {
                interval::check_input(&process::parse(input_bytes)?)
            } else {
                Ok(())
            };
            preflight.and_then(|()| {
                let worker = self.worker.as_mut().unwrap();
                child_id = Some(worker.id());
                child_occurrence = Some(self.child_counter);
                self.child_counter += 1;
                worker.exchange(raw).and_then(|child_raw| {
                    let response = process::parse(&child_raw)?;
                    child_response = Some(child_raw);
                    let object = response
                        .as_object()
                        .ok_or_else(|| format!("{label} response not object"))?;
                    let expected = if response["status"] == "ok" {
                        vec![
                            "schema",
                            "request_id",
                            "parent_execution_id",
                            "profile",
                            "status",
                            "data",
                        ]
                    } else {
                        vec![
                            "schema",
                            "request_id",
                            "parent_execution_id",
                            "profile",
                            "status",
                            "refusal",
                        ]
                    };
                    if object.len() != expected.len()
                        || expected.iter().any(|k| !object.contains_key(*k))
                        || response["schema"] != "ciw.native-interop-response.v1"
                        || response["request_id"] != r.request_id
                        || response["parent_execution_id"] != r.parent_execution_id
                        || response["profile"] != r.profile
                    {
                        return Err(format!("stale/mismatched {label} response"));
                    }
                    if response["status"] != "ok" {
                        return Err(format!("{label} refused: {}", response["refusal"]));
                    }
                    if !response["data"].is_object() {
                        return Err(format!("{label} response data not object"));
                    }
                    if r.profile == "oscillator-tsit5.v1"
                        && response["data"]["request_id"] != r.request_id
                    {
                        return Err("inner oscillator request ID differs".into());
                    }
                    Ok(response["data"].clone())
                })
            })
        };
        let result = result.and_then(|data| {
            if self.options.provider != "cpp"
                && self.runtime[if self.options.provider == "cantera" {
                    "python_executable_sha256"
                } else {
                    "julia_executable_sha256"
                }] != raw_sha(&bytes(
                    Path::new(if self.options.provider == "cantera" {
                        self.options.python.as_ref().unwrap()
                    } else {
                        self.options.julia.as_ref().unwrap()
                    }),
                    128 * 1024 * 1024,
                )?)
            {
                return Err(format!("{label} executable changed during execution"));
            }
            if self.options.provider == "intervals" {
                interval::check_output(&data)?;
            } else if reaction::family(&self.options.provider) {
                reaction::check(&self.options.provider, &process::parse(input_bytes)?, &data)?;
                if self.options.provider == "catalyst"
                    && data["mechanism"]["sha256"] != self.runtime["worker_sha256"]
                {
                    return Err(
                        "Catalyst mechanism bytes differ from the snapshotted worker".into(),
                    );
                }
            } else {
                output::check(&r.profile, &process::parse(input_bytes)?, &data)?;
            }
            Ok(data)
        });
        let diagnostics = self
            .worker
            .as_ref()
            .map(|w| w.diagnostics())
            .unwrap_or_default();
        let mut response = json!({"schema":"ciw.native-interop-response.v1","request_id":r.request_id,"parent_execution_id":r.parent_execution_id,"profile":r.profile});
        let mut output_bytes = None;
        let mut output_id = None;
        let fatal = result.is_err() && self.options.provider != "cpp";
        match result {
            Ok(data) => {
                let encoded = serde_json::to_vec(&data).map_err(|e| e.to_string())?;
                let id = OutputIdentity::of(&encoded);
                self.trace
                    .resolve(
                        occurrence,
                        ExecutionOutcome::Completed {
                            output: id,
                            exit_code: 0,
                        },
                    )
                    .map_err(|e| format!("trace: {e:?}"))?;
                output_id = Some(id.to_hex());
                output_bytes = Some(encoded);
                response["status"] = "ok".into();
                response["data"] = data;
            }
            Err(error) => {
                self.trace
                    .resolve(occurrence, ExecutionOutcome::Halted { exit_code: 1 })
                    .map_err(|e| format!("trace: {e:?}"))?;
                response["status"] = "refused".into();
                response["refusal"] = json!({"code":"execution_failure","detail":error});
            }
        }
        let computation = self
            .trace
            .get(occurrence)
            .unwrap()
            .computation_identity()
            .map(|id| id.to_hex());
        response["host"] = json!({"schema":"scr.provider-host-record.v1","provider":self.options.provider,"process_id":std::process::id(),"occurrence":occurrence,"child_process_id":child_id,"child_occurrence":child_occurrence,"status":if output_id.is_some(){"completed"}else{"halted"},"program_bytes_hex":hex(&program_bytes),"configuration_bytes_hex":hex(&configuration_bytes),"input_bytes_hex":hex(input_bytes),"output_bytes_hex":output_bytes.as_ref().map(|b|hex(b)),"program_id":program.to_hex(),"input_id":input.to_hex(),"output_id":output_id,"specification_id":specification.to_hex(),"computation_id":computation,"child_request_bytes_hex":if child_id.is_some(){Some(hex(raw))}else{None},"child_response_bytes_hex":child_response.as_ref().map(|b|hex(b)),"child_stderr_hex":hex(&diagnostics),"provider_runtime":self.runtime,"proof":Value::Null,"elapsed_seconds":started.elapsed().as_secs_f64()});
        if fatal {
            self.worker.take();
            self.snapshot.take();
        }
        Ok((response, fatal))
    }
}
impl Drop for Host {
    fn drop(&mut self) {
        self.worker.take();
        self.snapshot.take();
    }
}
fn run() -> Result<(), String> {
    let mut host = Host::new(options()?)?;
    let stdin = io::stdin();
    let mut input = stdin.lock();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    while let Some(raw) = process::read_frame(&mut input, MAX_FRAME)? {
        let value = process::parse(&raw)?;
        let (response, fatal) = if value["schema"] == "ciw.native-interop-handshake-request.v1" {
            (host.handshake(&raw)?, false)
        } else {
            host.execute(&raw)?
        };
        process::write_frame(
            &mut output,
            &serde_json::to_vec(&response).map_err(|e| e.to_string())?,
            MAX_RESPONSE,
        )?;
        if fatal {
            let label = match host.options.provider.as_str() {
                "cantera" => "Cantera",
                "catalyst" => "Catalyst",
                "intervals" => "IntervalArithmetic",
                _ => "Julia",
            };
            return Err(format!(
                "failed {label} worker terminated and reaped; start a fresh host occurrence"
            ));
        }
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("SCR provider host refused: {error}");
        std::process::exit(2);
    }
}
