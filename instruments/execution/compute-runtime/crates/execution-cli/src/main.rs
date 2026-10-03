//! The cross-process execution boundary: stdin in, one execution, stdout out.
//!
//! This binary is the ENTIRE bridge between the Python orchestration
//! layer and the Rust execution substrate -- no FFI, no bindings, no
//! shared memory. Python writes an execution request to stdin, this
//! process runs it against the built-in program registry, and writes a
//! line-oriented result to stdout. One request STREAM per process:
//! state cannot leak between streams because the process that ran one
//! is gone; within a stream, requests share one trace deliberately and
//! the occurrence numbers are the record of that sharing.
//!
//! # Request format (stdin, binary)
//!
//! ONE OR MORE requests, each three length-prefixed fields
//! (`u64 LE length` + raw bytes):
//!
//! ```text
//! [program descriptor][configuration][input]   (repeated B >= 1 times)
//! ```
//!
//! The batch extension (Transformer phase 2) amortizes process startup
//! over independent computations WITHOUT a second protocol: a single
//! request is exactly the old wire format, and every request in a batch
//! is answered by its own complete result block, in request order. The
//! whole stream is parsed BEFORE anything executes -- a truncated or
//! trailing-garbage stream is a protocol error and NOTHING runs. All
//! requests share one process-local trace, so occurrence numbers count
//! executed requests in order (unrunnable requests mint none).
//!
//! # Result format (stdout, lines)
//!
//! ```text
//! ste-execution-result v1
//! spec <64 hex>          commitment over (program, configuration, input)
//! program <64 hex>
//! input <64 hex>
//! occurrence <u64>       process-local: counts executed requests in order
//! status completed|halted|unrunnable
//! exit_code <u32>                        (completed | halted)
//! output <hex of output bytes>           (completed only; empty output = empty hex)
//! output_id <64 hex>                     (completed only)
//! computation <64 hex>                   (completed only)
//! detail <text>                          (halted | unrunnable)
//! ```
//!
//! Every identity echoed here is RECOMPUTABLE by the caller from bytes
//! the caller already holds -- and the Python engine recomputes and
//! compares all of them on every run, so this process is CHECKED, not
//! trusted. The `spec` echo exists because a result that does not name
//! its request is the detachable-warrant hazard (Phase 128, probe 1) at
//! the process boundary.
//!
//! # The three statuses
//!
//! `completed` and `halted` mean the program RAN (an occurrence was
//! minted and resolved). `unrunnable` means the engine REFUSED to start:
//! unknown program descriptor, or configuration bytes for a program
//! that takes none. Refusal matters: silently ignoring configuration
//! would let two different requests produce "the same" computation --
//! the exact silent-drop hazard the audits exist to prevent. No
//! occurrence is minted for an unrunnable request (the operations
//! ledger's NEVER_STARTED, at this seam).
//!
//! # Process exit codes
//!
//! 0 = a well-formed request was answered (any status above).
//! 2 = protocol error: stdin did not parse. Nothing was executed.

#![forbid(unsafe_code)]

use std::io::{Read, Write};

use execution_core::reference::{
    CrystalLatticeKernel, HardmaxAttentionKernel, HeatDiffusionKernel, PairwiseEnergyKernel,
    RadiusOfGyrationKernel,
};
use execution_core::{
    commit, execute, DeterministicProgram, ExecutionOutcome, ExecutionTrace, SPECIFICATION_TAG,
};

/// The three request fields, in wire order.
type RequestFields = (Vec<u8>, Vec<u8>, Vec<u8>);

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

fn read_field(input: &mut &[u8]) -> Result<Vec<u8>, String> {
    if input.len() < 8 {
        return Err("truncated length prefix".into());
    }
    let (len_bytes, rest) = input.split_at(8);
    let len = u64::from_le_bytes(len_bytes.try_into().expect("split_at(8)")) as usize;
    if rest.len() < len {
        return Err(format!("field claims {len} bytes, {} remain", rest.len()));
    }
    let (field, rest) = rest.split_at(len);
    *input = rest;
    Ok(field.to_vec())
}

fn main() {
    let mut raw = Vec::new();
    if let Err(error) = std::io::stdin().read_to_end(&mut raw) {
        eprintln!("protocol error: {error}");
        std::process::exit(2);
    }
    let mut cursor = raw.as_slice();
    let parsed = (|| -> Result<Vec<RequestFields>, String> {
        let mut requests = Vec::new();
        loop {
            let program = read_field(&mut cursor)?;
            let configuration = read_field(&mut cursor)?;
            let input = read_field(&mut cursor)?;
            requests.push((program, configuration, input));
            if cursor.is_empty() {
                break;
            }
        }
        Ok(requests)
    })();
    let requests = match parsed {
        Ok(requests) => requests,
        Err(error) => {
            eprintln!("protocol error: {error}");
            std::process::exit(2);
        }
    };

    // One trace for the whole batch: occurrences count executed
    // requests, in order, within this one process.
    let mut trace = ExecutionTrace::new();
    let mut out = String::new();
    for (program_bytes, configuration, input) in requests {
        out.push_str(&answer(&mut trace, &program_bytes, &configuration, &input));
    }
    print!("{out}");
    std::io::stdout().flush().expect("flush stdout");
}

/// Answer ONE request: the pre-batch body, verbatim in behavior --
/// every echoed identity remains recomputable by the caller.
fn answer(
    trace: &mut ExecutionTrace,
    program_bytes: &[u8],
    configuration: &[u8],
    input: &[u8],
) -> String {
    let spec = commit(SPECIFICATION_TAG, &[program_bytes, configuration, input]);

    let mut out = String::new();
    out.push_str("ste-execution-result v1\n");
    out.push_str(&format!("spec {}\n", spec.to_hex()));

    // The registry: every program this engine can run. Adding one means
    // adding it HERE, visibly -- there is no dynamic loading.
    let registry: [&dyn DeterministicProgram; 5] = [
        &PairwiseEnergyKernel,
        &HeatDiffusionKernel,
        &RadiusOfGyrationKernel,
        &CrystalLatticeKernel,
        &HardmaxAttentionKernel,
    ];
    let program = registry
        .iter()
        .find(|p| p.canonical_bytes() == program_bytes);

    let Some(program) = program else {
        out.push_str("status unrunnable\n");
        out.push_str("detail unknown program descriptor\n");
        return out;
    };
    if !configuration.is_empty() {
        out.push_str("status unrunnable\n");
        out.push_str(
            "detail this program accepts no configuration; refusing rather than ignoring it\n",
        );
        return out;
    }

    let run = execute(trace, *program, input);
    let occurrence = trace
        .get(run.occurrence)
        .expect("occurrence minted by this trace");

    out.push_str(&format!("program {}\n", occurrence.program().to_hex()));
    out.push_str(&format!("input {}\n", occurrence.input().to_hex()));
    out.push_str(&format!("occurrence {}\n", run.occurrence));

    match (&run.result, occurrence.outcome()) {
        (Ok(completion), ExecutionOutcome::Completed { output, exit_code }) => {
            out.push_str("status completed\n");
            out.push_str(&format!("exit_code {exit_code}\n"));
            out.push_str(&format!("output {}\n", hex(&completion.output)));
            out.push_str(&format!("output_id {}\n", output.to_hex()));
            let computation = occurrence
                .computation_identity()
                .expect("completed executions have a computation identity");
            out.push_str(&format!("computation {}\n", computation.to_hex()));
        }
        (Err(fault), ExecutionOutcome::Halted { exit_code }) => {
            out.push_str("status halted\n");
            out.push_str(&format!("exit_code {exit_code}\n"));
            out.push_str(&format!("detail {}\n", fault.detail.replace('\n', " ")));
        }
        (result, outcome) => unreachable!(
            "execute() resolves Completed for Ok and Halted for Err; got {result:?} / {outcome:?}"
        ),
    }

    out
}
