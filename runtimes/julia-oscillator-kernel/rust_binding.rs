//! Safe Rust binding plus a bounded TSV probe. No Cargo dependencies.
//! Build against the generated libciw_oscillator_kernel; do not reimplement the RHS.
use std::ffi::{c_char, CStr};
use std::io::{self, Read};

#[link(name = "ciw_oscillator_kernel")]
unsafe extern "C" {
    fn ciw_oscillator_abi_v1() -> u32;
    fn ciw_oscillator_source_sha256_v1() -> *const c_char;
    fn ciw_oscillator_rhs_v1(state: *const f64, ns: usize, params: *const f64,
                            np: usize, out: *mut f64, no: usize) -> i32;
}

pub struct Kernel { _private: () }
impl Kernel {
    pub fn bind(expected_source: &str) -> Result<Self, String> {
        if expected_source.len() != 64 || !expected_source.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("expected source SHA-256".into());
        }
        // SAFETY: these functions have the declared C ABI in the explicitly linked,
        // trusted library. Its source string is static, NUL terminated and non-null.
        let (abi, ptr) = unsafe { (ciw_oscillator_abi_v1(), ciw_oscillator_source_sha256_v1()) };
        if abi != 1 || ptr.is_null() { return Err("native ABI mismatch".into()); }
        let source = unsafe { CStr::from_ptr(ptr) }.to_str().map_err(|e| e.to_string())?;
        if source != expected_source { return Err("native source mismatch".into()); }
        Ok(Self { _private: () })
    }

    pub fn rhs(&self, state: [f64; 2], parameters: [f64; 2]) -> Result<[f64; 2], i32> {
        if !state.iter().chain(parameters.iter()).all(|v| v.is_finite()) { return Err(3); }
        let [q,v] = state;
        let [gamma,omega] = parameters;
        if q.abs() > 1e6 || v.abs() > 1e6 || !(f64::EPSILON..=20.0).contains(&omega)
            || !(0.0..=0.5*omega).contains(&gamma) { return Err(4); }
        let mut output = [0.0; 2];
        // SAFETY: arrays are live, aligned, correctly sized, disjoint for this call;
        // the C function retains no pointers and writes only after success checks.
        let status = unsafe { ciw_oscillator_rhs_v1(state.as_ptr(),2,parameters.as_ptr(),2,
                                                   output.as_mut_ptr(),2) };
        if status != 0 { return Err(status); }
        if !output.iter().all(|x| x.is_finite()) { return Err(5); }
        Ok(output)
    }
}

fn probe() -> Result<(), String> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments.len() != 1 { return Err("usage: rust-probe EXPECTED_SOURCE_SHA256 < cases.tsv".into()); }
    let kernel = Kernel::bind(&arguments[0])?;
    let mut bytes = Vec::new();
    io::stdin().take(1_048_577).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    if bytes.len() > 1_048_576 { return Err("input exceeds byte limit".into()); }
    let text = std::str::from_utf8(&bytes).map_err(|e| e.to_string())?;
    let rows: Vec<&str> = text.lines().collect();
    if rows.is_empty() || rows.len() > 4096 { return Err("input exceeds row limits".into()); }
    let mut output = String::new();
    for row in rows {
        let fields: Vec<&str> = row.split('\t').collect();
        if fields.len() != 4 { return Err("expected q, v, gamma, omega".into()); }
        let mut value = [0.0;4];
        for (i, field) in fields.iter().enumerate() {
            value[i] = field.parse::<f64>().map_err(|_| "invalid floating-point field")?;
        }
        let y = kernel.rhs([value[0],value[1]], [value[2],value[3]])
            .map_err(|code| format!("native RHS refused: {code}"))?;
        output.push_str(&format!("{:.17e}\t{:.17e}\n", y[0],y[1]));
    }
    print!("{output}");
    Ok(())
}

fn main() {
    if let Err(error) = probe() { eprintln!("{error}"); std::process::exit(2); }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn kernel() -> Kernel {
        let source = unsafe { CStr::from_ptr(ciw_oscillator_source_sha256_v1()) }.to_str().unwrap();
        Kernel::bind(source).unwrap()
    }
    #[test] fn mixed_state() { assert_eq!(kernel().rhs([1.0,-2.0],[0.25,2.0]), Ok([-2.0,-3.0])); }
    #[test] fn undamped() { assert_eq!(kernel().rhs([2.0,3.0],[0.0,2.0]), Ok([3.0,-8.0])); }
    #[test] fn rejects_nonfinite() { assert_eq!(kernel().rhs([f64::NAN,0.0],[0.0,1.0]),Err(3)); }
    #[test] fn rejects_domain() { assert_eq!(kernel().rhs([0.0,0.0],[1.0,1.0]),Err(4)); }
    #[test] fn rejects_identity() { assert!(Kernel::bind(&"0".repeat(64)).is_err()); }
}
