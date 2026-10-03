//! Provider-free native checker for `affine-d256.v1`.
//!
//! This binary includes the same Rust checker module used by the SP1 host
//! adapter, but does not depend on SP1.  It is the executable local gate for
//! validating a canonical statement before a provider is selected:
//!
//! ```text
//! cargo run --manifest-path zk/affine-check/Cargo.toml -- --statement-file run.bin
//! cargo run --manifest-path zk/affine-check/Cargo.toml -- --statement-hex HEX
//! ```

#[allow(dead_code)]
#[path = "../../sp1-adapter/src/affine.rs"]
mod affine;

use std::path::Path;

const MAX_STATEMENT_BYTES: usize = 65_536;

fn from_hex(text: &str) -> Result<Vec<u8>, String> {
    if !text.is_ascii() || !text.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("statement hex must contain only ASCII hexadecimal digits".into());
    }
    if text.len() % 2 != 0 {
        return Err("statement hex has odd length".into());
    }
    if text.len() / 2 > MAX_STATEMENT_BYTES {
        return Err("statement exceeds the 65536-byte gate".into());
    }
    (0..text.len())
        .step_by(2)
        .map(|at| {
            u8::from_str_radix(&text[at..at + 2], 16)
                .map_err(|error| format!("invalid statement hex at {at}: {error}"))
        })
        .collect()
}

fn usage() -> &'static str {
    "usage: ste-affine-check (--statement-file PATH | --statement-hex HEX)"
}

fn run(args: &[String]) -> Result<(), String> {
    let statement = match args {
        [_, flag, value] if flag == "--statement-file" => {
            let path = Path::new(value);
            let length = std::fs::metadata(path)
                .map_err(|error| format!("reading statement metadata: {error}"))?
                .len();
            if length > MAX_STATEMENT_BYTES as u64 {
                return Err("statement exceeds the 65536-byte gate".into());
            }
            let bytes =
                std::fs::read(path).map_err(|error| format!("reading statement: {error}"))?;
            if bytes.len() > MAX_STATEMENT_BYTES {
                return Err("statement exceeds the 65536-byte gate".into());
            }
            bytes
        }
        [_, flag, value] if flag == "--statement-hex" => from_hex(value)?,
        _ => return Err(usage().into()),
    };
    let checked = affine::check_statement(&statement).map_err(|error| error.to_string())?;
    println!("status accepted");
    println!("profile affine-d256.v1");
    println!("arithmetic exact-d256");
    println!("rows {}", checked.input.rows);
    println!("columns {}", checked.input.columns);
    println!("input_commitment {}", hex(&checked.input_commitment));
    println!("output_commitment {}", hex(&checked.output_commitment));
    println!(
        "operation_commitment {}",
        hex(&checked.operation_commitment)
    );
    println!("profile_commitment {}", hex(&checked.profile_commitment));
    println!("statement_bytes {}", checked.statement_bytes.len());
    Ok(())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if let Err(error) = run(&args) {
        eprintln!("ste-affine-check refused: {error}");
        std::process::exit(2);
    }
}
