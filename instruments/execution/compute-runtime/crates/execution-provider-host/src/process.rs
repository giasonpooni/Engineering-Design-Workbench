use serde_json::Value;
use std::{
    io::{Read, Write},
    process::{Child, Command, Stdio},
    sync::{
        mpsc::{self, Receiver},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};

pub const MAX_FRAME: usize = 1_048_576;
pub const MAX_RESPONSE: usize = 4_194_304;
pub const MAX_DIAGNOSTICS: usize = 65_536;

pub fn read_frame(mut input: impl Read, max: usize) -> Result<Option<Vec<u8>>, String> {
    let mut header = [0u8; 4];
    let n = input.read(&mut header[..1]).map_err(|e| e.to_string())?;
    if n == 0 {
        return Ok(None);
    }
    input
        .read_exact(&mut header[1..])
        .map_err(|_| "truncated frame header")?;
    let size = u32::from_be_bytes(header) as usize;
    if size == 0 || size > max {
        return Err("empty or oversized frame".into());
    }
    let mut bytes = vec![0; size];
    input
        .read_exact(&mut bytes)
        .map_err(|_| "truncated frame payload")?;
    Ok(Some(bytes))
}
pub fn write_frame(mut output: impl Write, bytes: &[u8], max: usize) -> Result<(), String> {
    if bytes.is_empty() || bytes.len() > max {
        return Err("empty or oversized output frame".into());
    }
    output
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .and_then(|_| output.write_all(bytes))
        .and_then(|_| output.flush())
        .map_err(|e| e.to_string())
}
#[derive(Default)]
struct Diagnostics {
    bytes: Vec<u8>,
    overflow: bool,
}

#[cfg(windows)]
struct Job(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
impl Job {
    fn attach(child: &Child) -> Result<Self, String> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::{Foundation::CloseHandle, System::JobObjects::*};
        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err("cannot create child lifetime job".into());
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
            {
                CloseHandle(handle);
                return Err("cannot attach child lifetime job".into());
            }
            Ok(Job(handle))
        }
    }
}
#[cfg(windows)]
impl Drop for Job {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

pub struct Worker {
    child: Child,
    input: mpsc::SyncSender<Vec<u8>>,
    write_error: Arc<Mutex<Option<String>>>,
    responses: Receiver<Result<Vec<u8>, String>>,
    diagnostics: Arc<Mutex<Diagnostics>>,
    timeout: Duration,
    label: &'static str,
    #[cfg(windows)]
    _job: Job,
}
impl Worker {
    pub fn start(
        executable: &str,
        project: &str,
        worker: &str,
        timeout: Duration,
    ) -> Result<Self, String> {
        let mut command = Command::new(executable);
        command
            .args([
                "--startup-file=no",
                "--history-file=no",
                &format!("--project={project}"),
                worker,
            ])
            .env("JULIA_NUM_THREADS", "1")
            .env("JULIA_PKG_OFFLINE", "true");
        Self::spawn(command, timeout, "Julia")
    }
    pub fn start_python(executable: &str, worker: &str, timeout: Duration) -> Result<Self, String> {
        let mut command = Command::new(executable);
        // Isolated mode excludes user-site packages and PYTHON* environment
        // configuration. The trusted installation supplies the dependencies.
        command.args(["-I", "-u", worker]);
        Self::spawn(command, timeout, "Python")
    }
    fn spawn(mut command: Command, timeout: Duration, label: &'static str) -> Result<Self, String> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            let parent = std::process::id();
            unsafe {
                command.pre_exec(move || {
                    #[cfg(target_os = "linux")]
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0
                        || libc::getppid() != parent as i32
                    {
                        return Err(std::io::Error::last_os_error());
                    }
                    Ok(())
                });
            }
        }
        let mut child = command
            .spawn()
            .map_err(|e| format!("unavailable {label} provider: {e}"))?;
        #[cfg(windows)]
        let job = match Job::attach(&child) {
            Ok(job) => job,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
        };
        let mut stdin = child.stdin.take().ok_or("missing child input")?;
        let stdout = child.stdout.take().ok_or("missing child output")?;
        let mut stderr = child.stderr.take().ok_or("missing child diagnostics")?;
        let (input_tx, input_rx) = mpsc::sync_channel::<Vec<u8>>(1);
        let write_error = Arc::new(Mutex::new(None));
        let writer_error = Arc::clone(&write_error);
        thread::spawn(move || {
            while let Ok(raw) = input_rx.recv() {
                if let Err(error) = write_frame(&mut stdin, &raw, MAX_FRAME) {
                    *writer_error.lock().unwrap() = Some(error);
                    break;
                }
            }
        });
        let (tx, rx) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut input = stdout;
            loop {
                let next = match read_frame(&mut input, MAX_FRAME) {
                    Ok(Some(v)) => Ok(v),
                    Ok(None) => Err(format!("{label} worker exited before response")),
                    Err(e) => Err(e),
                };
                let stop = next.is_err();
                if tx.send(next).is_err() || stop {
                    break;
                }
            }
        });
        let diagnostics = Arc::new(Mutex::new(Diagnostics::default()));
        let shared = Arc::clone(&diagnostics);
        thread::spawn(move || {
            let mut buffer = [0u8; 4096];
            while let Ok(n) = stderr.read(&mut buffer) {
                if n == 0 {
                    break;
                }
                let mut state = shared.lock().unwrap();
                let remaining = MAX_DIAGNOSTICS.saturating_sub(state.bytes.len());
                state.bytes.extend_from_slice(&buffer[..n.min(remaining)]);
                if n > remaining {
                    state.overflow = true;
                }
            }
        });
        Ok(Self {
            child,
            input: input_tx,
            write_error,
            responses: rx,
            diagnostics,
            timeout,
            label,
            #[cfg(windows)]
            _job: job,
        })
    }
    pub fn id(&self) -> u32 {
        self.child.id()
    }
    pub fn diagnostics(&self) -> Vec<u8> {
        self.diagnostics.lock().unwrap().bytes.clone()
    }
    pub fn exchange(&mut self, request: &[u8]) -> Result<Vec<u8>, String> {
        // One request in flight; queued output before a new request is stale.
        if self.responses.try_recv().is_ok() {
            return Err(format!("unsolicited or stale {} response", self.label));
        }
        self.input
            .try_send(request.to_vec())
            .map_err(|_| format!("{} writer busy or stopped", self.label))?;
        let deadline = Instant::now() + self.timeout;
        loop {
            if let Some(error) = self.write_error.lock().unwrap().clone() {
                return Err(error);
            }
            if self.diagnostics.lock().unwrap().overflow {
                return Err(format!(
                    "{} stderr exceeded bounded diagnostics",
                    self.label
                ));
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(format!("{} worker timeout", self.label));
            }
            match self
                .responses
                .recv_timeout(remaining.min(Duration::from_millis(10)))
            {
                Ok(value) => return value,
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(_) => return Err(format!("{} response channel closed", self.label)),
            }
        }
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

// serde_json's Value normally accepts duplicate object keys. This visitor
// rejects them recursively before typed envelope or payload validation.
pub fn parse(raw: &[u8]) -> Result<Value, String> {
    use serde::{
        de::{self, MapAccess, SeqAccess, Visitor},
        Deserialize, Deserializer,
    };
    struct Unique(Value);
    impl<'de> Deserialize<'de> for Unique {
        fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
            struct V;
            impl<'de> Visitor<'de> for V {
                type Value = Unique;
                fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                    write!(f, "unique-key JSON")
                }
                fn visit_bool<E: de::Error>(self, v: bool) -> Result<Unique, E> {
                    Ok(Unique(Value::Bool(v)))
                }
                fn visit_i64<E: de::Error>(self, v: i64) -> Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_u64<E: de::Error>(self, v: u64) -> Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_f64<E: de::Error>(self, v: f64) -> Result<Unique, E> {
                    serde_json::Number::from_f64(v)
                        .map(|v| Unique(Value::Number(v)))
                        .ok_or_else(|| E::custom("nonfinite JSON"))
                }
                fn visit_str<E: de::Error>(self, v: &str) -> Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_string<E: de::Error>(self, v: String) -> Result<Unique, E> {
                    Ok(Unique(v.into()))
                }
                fn visit_unit<E: de::Error>(self) -> Result<Unique, E> {
                    Ok(Unique(Value::Null))
                }
                fn visit_none<E: de::Error>(self) -> Result<Unique, E> {
                    Ok(Unique(Value::Null))
                }
                fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<Unique, A::Error> {
                    let mut out = vec![];
                    while let Some(Unique(v)) = a.next_element()? {
                        if out.len() >= 32768 {
                            return Err(de::Error::custom("array limit"));
                        }
                        out.push(v);
                    }
                    Ok(Unique(Value::Array(out)))
                }
                fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<Unique, A::Error> {
                    let mut out = serde_json::Map::new();
                    while let Some((k, Unique(v))) = a.next_entry::<String, Unique>()? {
                        if out.contains_key(&k) {
                            return Err(de::Error::custom("duplicate JSON field"));
                        }
                        out.insert(k, v);
                    }
                    Ok(Unique(Value::Object(out)))
                }
            }
            d.deserialize_any(V)
        }
    }
    serde_json::from_slice::<Unique>(raw)
        .map(|v| v.0)
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn framing_golden_and_short_reads() {
        let mut out = vec![];
        write_frame(&mut out, b"abc", MAX_FRAME).unwrap();
        assert_eq!(out, b"\0\0\0\x03abc");
        assert_eq!(
            read_frame(&out[..], MAX_FRAME).unwrap(),
            Some(b"abc".to_vec())
        );
        for bad in [
            &b"\0"[..],
            &b"\0\0\0\x03a"[..],
            &b"\0\0\0\0"[..],
            &b"\xff\xff\xff\xff"[..],
        ] {
            assert!(read_frame(bad, MAX_FRAME).is_err());
        }
    }
    #[test]
    fn captured_julia_binary64_values_survive_parsing_and_retention() {
        // Decimal tokens captured from genuine Tsit5 and HiGHS responses.
        // Expected IEEE-754 bits are independent of serde_json's parser.
        for (token, expected) in [
            ("-0.9844478744098741", 0xbfef8098d426a0c4_u64),
            ("3.8941834684251964", 0x400f2749a98c149e_u64),
            ("0.39999999723076923", 0x3fd9999996a0664f_u64),
            ("5.999999985739635e-08", 0x3e701b2b29000000_u64),
        ] {
            let parsed = parse(token.as_bytes()).unwrap();
            assert_eq!(parsed.as_f64().unwrap().to_bits(), expected, "{token}");
            let retained = serde_json::to_vec(&parsed).unwrap();
            assert_eq!(
                parse(&retained).unwrap().as_f64().unwrap().to_bits(),
                expected
            );
            let typed: f64 = serde_json::from_str(token).unwrap();
            assert_eq!(typed.to_bits(), expected);
        }
    }
    #[test]
    fn duplicate_fields_and_contamination_refuse() {
        assert!(parse(br#"{"x":1,"x":2}"#).is_err());
        assert!(parse(br#"{"a":{"x":1,"x":2}}"#).is_err());
        assert!(parse(b"{} noise").is_err());
        assert!(parse(b"{\"x\":NaN}").is_err());
    }
}
