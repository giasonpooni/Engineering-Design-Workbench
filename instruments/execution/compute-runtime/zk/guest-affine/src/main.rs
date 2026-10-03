//! Independent SP1 guest for the bounded exact affine profile.
//!
//! The host checker in `zk/sp1-adapter/src/affine.rs` intentionally has a
//! separate parser and evaluator.  This guest repeats those operations in
//! the proved execution, then commits the exact input and candidate bytes.
//! A valid proof therefore establishes only that this registered checker
//! accepted the supplied exact affine statement.

#![no_main]

extern crate alloc;

use alloc::vec::Vec;
use execution_commitment::commit;

sp1_zkvm::entrypoint!(main);

const OPERATION: &[u8] = b"ciw.affine-d256.v1";
const PROFILE: &[u8] = b"exact-d256";
const INPUT_TAG: &str = "scout.execution.input.v1";
const OUTPUT_TAG: &str = "scout.execution.output.v1";
const AFFINE_INPUT_TAG: &str = "scout.native.affine-d256-input.v1";
const AFFINE_OUTPUT_TAG: &str = "scout.native.affine-d256-output.v1";
const AFFINE_STATEMENT_TAG: &str = "scout.native.affine-d256-statement.v1";
const PROFILE_COMMITMENT_TAG: &str = "scout.execution.affine-profile.v1";
const PUBLIC_VALUES_TAG: &[u8] = b"ste.sp1.affine-d256-io.v1";
const DENOMINATOR: u32 = 256;
const OUTPUT_DENOMINATOR: u32 = 65_536;
const MAX_DIMENSION: u32 = 8;
const MAX_NUMERATOR: i64 = 4_096;
const MAX_SHIFTED_NUMERATOR: i64 = 8_192;
const FAULT_MALFORMED: u32 = 2;
const FAULT_DIMENSIONS: u32 = 3;
const FAULT_BOUND: u32 = 4;
const FAULT_ARITHMETIC: u32 = 5;
const FAULT_CANDIDATE: u32 = 6;

#[derive(Clone, PartialEq, Eq)]
struct Input {
    rows: u32,
    columns: u32,
    a: Vec<i64>,
    b: Vec<i64>,
    x0: Vec<i64>,
    delta_x: Vec<i64>,
}

#[derive(Clone, PartialEq, Eq)]
struct Output {
    rows: u32,
    columns: u32,
    baseline: Vec<i128>,
    contributions: Vec<i128>,
    predicted_delta: Vec<i128>,
    predicted_output: Vec<i128>,
    model_output: Vec<i128>,
    residual: Vec<i128>,
    denominator: u32,
}

struct Reader<'a> {
    raw: &'a [u8],
    at: usize,
}

impl<'a> Reader<'a> {
    fn new(raw: &'a [u8]) -> Self {
        Self { raw, at: 0 }
    }

    fn take(&mut self, length: usize) -> Option<&'a [u8]> {
        let end = self.at.checked_add(length)?;
        if end > self.raw.len() {
            return None;
        }
        let value = &self.raw[self.at..end];
        self.at = end;
        Some(value)
    }

    fn u64(&mut self) -> Option<u64> {
        Some(u64::from_le_bytes(self.take(8)?.try_into().ok()?))
    }

    fn done(&self) -> bool {
        self.at == self.raw.len()
    }
}

fn fields<'a>(raw: &'a [u8], tag: &str, count: usize) -> Option<Vec<&'a [u8]>> {
    if raw.len() > 1 << 20 {
        return None;
    }
    let mut reader = Reader::new(raw);
    let tag_length = usize::try_from(reader.u64()?).ok()?;
    if reader.take(tag_length)? != tag.as_bytes() {
        return None;
    }
    if reader.u64()? != count as u64 {
        return None;
    }
    let mut result = Vec::with_capacity(count);
    for _ in 0..count {
        let length = usize::try_from(reader.u64()?).ok()?;
        result.push(reader.take(length)?);
    }
    if !reader.done() {
        return None;
    }
    Some(result)
}

fn u32_field(raw: &[u8]) -> Option<u32> {
    Some(u32::from_le_bytes(raw.try_into().ok()?))
}

fn dimension(value: u32) -> Option<usize> {
    if !(1..=MAX_DIMENSION).contains(&value) {
        return None;
    }
    Some(value as usize)
}

fn i64_values(raw: &[u8], count: usize) -> Option<Vec<i64>> {
    if raw.len() != count.checked_mul(8)? {
        return None;
    }
    let mut result = Vec::with_capacity(count);
    for index in 0..count {
        let at = index * 8;
        result.push(i64::from_le_bytes(raw[at..at + 8].try_into().ok()?));
    }
    Some(result)
}

fn i128_values(raw: &[u8], count: usize) -> Option<Vec<i128>> {
    if raw.len() != count.checked_mul(16)? {
        return None;
    }
    let mut result = Vec::with_capacity(count);
    for index in 0..count {
        let at = index * 16;
        result.push(i128::from_le_bytes(raw[at..at + 16].try_into().ok()?));
    }
    Some(result)
}

fn checked_input(value: i64) -> bool {
    (-MAX_NUMERATOR..=MAX_NUMERATOR).contains(&value)
}

fn decode_input(raw: &[u8]) -> Option<Input> {
    let values = fields(raw, AFFINE_INPUT_TAG, 6)?;
    let rows = u32_field(values[0])?;
    let columns = u32_field(values[1])?;
    let rows_len = dimension(rows)?;
    let columns_len = dimension(columns)?;
    let input = Input {
        rows,
        columns,
        a: i64_values(values[2], rows_len.checked_mul(columns_len)?)?,
        b: i64_values(values[3], rows_len)?,
        x0: i64_values(values[4], columns_len)?,
        delta_x: i64_values(values[5], columns_len)?,
    };
    if input
        .a
        .iter()
        .chain(input.b.iter())
        .chain(input.x0.iter())
        .chain(input.delta_x.iter())
        .any(|v| !checked_input(*v))
    {
        return None;
    }
    for at in 0..columns_len {
        let shifted = input.x0[at].checked_add(input.delta_x[at])?;
        if !(-MAX_SHIFTED_NUMERATOR..=MAX_SHIFTED_NUMERATOR).contains(&shifted) {
            return None;
        }
    }
    Some(input)
}

fn decode_output(raw: &[u8]) -> Option<Output> {
    let values = fields(raw, AFFINE_OUTPUT_TAG, 9)?;
    let rows = u32_field(values[0])?;
    let columns = u32_field(values[1])?;
    let rows_len = dimension(rows)?;
    let columns_len = dimension(columns)?;
    let denominator = u32_field(values[8])?;
    if denominator != OUTPUT_DENOMINATOR {
        return None;
    }
    Some(Output {
        rows,
        columns,
        baseline: i128_values(values[2], rows_len)?,
        contributions: i128_values(values[3], rows_len.checked_mul(columns_len)?)?,
        predicted_delta: i128_values(values[4], rows_len)?,
        predicted_output: i128_values(values[5], rows_len)?,
        model_output: i128_values(values[6], rows_len)?,
        residual: i128_values(values[7], rows_len)?,
        denominator,
    })
}

fn evaluate(input: &Input) -> Option<Output> {
    let rows = input.rows as usize;
    let columns = input.columns as usize;
    let mut baseline = Vec::with_capacity(rows);
    let mut contributions = Vec::with_capacity(rows.checked_mul(columns)?);
    let mut predicted_delta = Vec::with_capacity(rows);
    let mut predicted_output = Vec::with_capacity(rows);
    let mut model_output = Vec::with_capacity(rows);
    let mut residual = Vec::with_capacity(rows);
    for row in 0..rows {
        let mut base = (input.b[row] as i128).checked_mul(DENOMINATOR as i128)?;
        let mut delta = 0i128;
        let mut model = (input.b[row] as i128).checked_mul(DENOMINATOR as i128)?;
        for col in 0..columns {
            let coefficient = input.a[row * columns + col] as i128;
            base = base.checked_add(coefficient.checked_mul(input.x0[col] as i128)?)?;
            let contribution = coefficient.checked_mul(input.delta_x[col] as i128)?;
            delta = delta.checked_add(contribution)?;
            let shifted = (input.x0[col] as i128).checked_add(input.delta_x[col] as i128)?;
            model = model.checked_add(coefficient.checked_mul(shifted)?)?;
            contributions.push(contribution);
        }
        let predicted = base.checked_add(delta)?;
        baseline.push(base);
        predicted_delta.push(delta);
        predicted_output.push(predicted);
        model_output.push(model);
        residual.push(model.checked_sub(predicted)?);
    }
    Some(Output {
        rows: input.rows,
        columns: input.columns,
        baseline,
        contributions,
        predicted_delta,
        predicted_output,
        model_output,
        residual,
        denominator: OUTPUT_DENOMINATOR,
    })
}

fn commit_public(
    input: &[u8; 32],
    output: Option<&[u8; 32]>,
    rows: u32,
    columns: u32,
    exit_code: u32,
) {
    let operation = commit(PROFILE_COMMITMENT_TAG, &[OPERATION]);
    let profile = commit(PROFILE_COMMITMENT_TAG, &[PROFILE]);
    sp1_zkvm::io::commit_slice(PUBLIC_VALUES_TAG);
    sp1_zkvm::io::commit_slice(input);
    match output {
        Some(value) => {
            sp1_zkvm::io::commit_slice(&[0u8]);
            sp1_zkvm::io::commit_slice(value);
        }
        None => sp1_zkvm::io::commit_slice(&[1u8]),
    }
    sp1_zkvm::io::commit_slice(operation.as_bytes());
    sp1_zkvm::io::commit_slice(profile.as_bytes());
    sp1_zkvm::io::commit_slice(&rows.to_le_bytes());
    sp1_zkvm::io::commit_slice(&columns.to_le_bytes());
    sp1_zkvm::io::commit_slice(&DENOMINATOR.to_le_bytes());
    sp1_zkvm::io::commit_slice(&(MAX_NUMERATOR as u32).to_le_bytes());
    sp1_zkvm::io::commit_slice(&exit_code.to_le_bytes());
}

fn fault(raw: &[u8], code: u32) {
    let input = commit(INPUT_TAG, &[raw]);
    commit_public(input.as_bytes(), None, 0, 0, code);
}

pub fn main() {
    let statement = sp1_zkvm::io::read_vec();
    let Some(values) = fields(&statement, AFFINE_STATEMENT_TAG, 6) else {
        fault(&statement, FAULT_MALFORMED);
        return;
    };
    if values[0] != OPERATION || values[1] != PROFILE {
        fault(&statement, FAULT_MALFORMED);
        return;
    }
    if u32_field(values[2]) != Some(DENOMINATOR)
        || u32_field(values[3]) != Some(MAX_NUMERATOR as u32)
    {
        fault(&statement, FAULT_BOUND);
        return;
    }
    let Some(input) = decode_input(values[4]) else {
        fault(&statement, FAULT_DIMENSIONS);
        return;
    };
    let Some(expected) = evaluate(&input) else {
        fault(values[4], FAULT_ARITHMETIC);
        return;
    };
    let Some(candidate) = decode_output(values[5]) else {
        fault(values[4], FAULT_CANDIDATE);
        return;
    };
    if candidate != expected {
        fault(values[4], FAULT_CANDIDATE);
        return;
    }
    let input_commitment = commit(INPUT_TAG, &[values[4]]);
    let output_commitment = commit(OUTPUT_TAG, &[values[5]]);
    commit_public(
        input_commitment.as_bytes(),
        Some(output_commitment.as_bytes()),
        input.rows,
        input.columns,
        0,
    );
}
