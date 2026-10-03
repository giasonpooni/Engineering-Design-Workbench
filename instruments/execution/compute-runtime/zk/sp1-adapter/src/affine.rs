//! Host-side exact checker and public-values convention for the bounded
//! `affine-d256.v1` SP1 guest.
//!
//! This module intentionally does not reuse the native C++ or Julia result.
//! It decodes the canonical statement, evaluates the bounded affine map with
//! checked integer arithmetic, and compares every candidate field.  The SP1
//! guest has an independent implementation of the same wire contract.  A
//! successful check therefore binds a computation claim to exact bytes; it
//! does not turn those bytes into a measurement or a physical assertion.

use execution_core::{
    canonical, commit, INPUT_TAG as CANONICAL_INPUT_TAG, OUTPUT_TAG as CANONICAL_OUTPUT_TAG,
};
use std::fmt;

pub const OPERATION: &[u8] = b"ciw.affine-d256.v1";
pub const PROFILE: &[u8] = b"exact-d256";
pub const INPUT_TAG: &str = "scout.native.affine-d256-input.v1";
pub const OUTPUT_TAG: &str = "scout.native.affine-d256-output.v1";
pub const STATEMENT_TAG: &str = "scout.native.affine-d256-statement.v1";
pub const PROFILE_COMMITMENT_TAG: &str = "scout.execution.affine-profile.v1";
/// Descriptor that the build recipe and host binding must register for this
/// profile.  It is deliberately separate from the proof's operation bytes.
pub const DESCRIPTOR: &[u8] = concat!(
    "scout.native.affine-d256-kernel.v1\n",
    "profile: affine-d256.v1; arithmetic: exact-d256; denominator: 256\n",
    "input: [rows u32 LE][columns u32 LE][A rows*columns i64 LE row-major]",
    "[b rows i64 LE][x0 columns i64 LE][delta_x columns i64 LE]\n",
    "bounds: 1<=rows,columns<=8; every input numerator abs<=4096;",
    " shifted numerator abs<=8192\n",
    "output: denominator 65536; baseline, contributions, predicted_delta,",
    " predicted_output, model_output, residual as i128 LE row-major\n",
    "faults: 2=malformed, 3=dimensions, 4=numerator bound,",
    " 5=checked arithmetic, 6=candidate mismatch"
)
.as_bytes();
pub const DENOMINATOR: u32 = 256;
pub const OUTPUT_DENOMINATOR: u32 = 65_536;
pub const MAX_DIMENSION: u32 = 8;
pub const MAX_NUMERATOR: i64 = 4_096;
pub const MAX_SHIFTED_NUMERATOR: i64 = 8_192;
pub const PUBLIC_VALUES_TAG: &[u8] = b"ste.sp1.affine-d256-io.v1";

/// The exact checker refused a statement or proof claim.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffineError(pub String);

impl fmt::Display for AffineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for AffineError {}

type Result<T> = std::result::Result<T, AffineError>;

fn error(message: impl Into<String>) -> AffineError {
    AffineError(message.into())
}

/// Validated exact affine input. Values are numerators over D=256.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffineInput {
    pub rows: u32,
    pub columns: u32,
    pub a_row_major: Vec<i64>,
    pub b: Vec<i64>,
    pub x0: Vec<i64>,
    pub delta_x: Vec<i64>,
}

/// Exact output fields. Every output number is a signed i128 numerator over
/// D²=65536; no float conversion or rounding is permitted.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffineOutput {
    pub rows: u32,
    pub columns: u32,
    pub baseline_output: Vec<i128>,
    pub contributions: Vec<i128>,
    pub predicted_delta: Vec<i128>,
    pub predicted_output: Vec<i128>,
    pub model_output: Vec<i128>,
    pub residual: Vec<i128>,
    pub denominator: u32,
}

/// The checked input/candidate pair and all commitments the guest must bind.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffineChecked {
    pub statement_bytes: Vec<u8>,
    pub input_bytes: Vec<u8>,
    pub output_bytes: Vec<u8>,
    pub input: AffineInput,
    pub output: AffineOutput,
    pub input_commitment: [u8; 32],
    pub output_commitment: [u8; 32],
    pub operation_commitment: [u8; 32],
    pub profile_commitment: [u8; 32],
}

fn dimension(value: u32, label: &str) -> Result<usize> {
    if !(1..=MAX_DIMENSION).contains(&value) {
        return Err(error(format!("{label} outside 1..={MAX_DIMENSION}")));
    }
    Ok(value as usize)
}

fn checked_input(value: i64, label: &str) -> Result<i64> {
    if value < -MAX_NUMERATOR || value > MAX_NUMERATOR {
        return Err(error(format!(
            "{label} outside [-{MAX_NUMERATOR},{MAX_NUMERATOR}]"
        )));
    }
    Ok(value)
}

fn checked_i128(value: i128, label: &str) -> Result<i128> {
    // Keeping this helper makes all arithmetic sites auditable even though
    // Rust's i128 already represents the target range.
    let _ = label;
    Ok(value)
}

fn mul(left: i128, right: i128, label: &str) -> Result<i128> {
    left.checked_mul(right)
        .ok_or_else(|| error(format!("{label} i128 multiplication overflow")))
        .and_then(|value| checked_i128(value, label))
}

fn add(left: i128, right: i128, label: &str) -> Result<i128> {
    left.checked_add(right)
        .ok_or_else(|| error(format!("{label} i128 addition overflow")))
        .and_then(|value| checked_i128(value, label))
}

fn sub(left: i128, right: i128, label: &str) -> Result<i128> {
    left.checked_sub(right)
        .ok_or_else(|| error(format!("{label} i128 subtraction overflow")))
        .and_then(|value| checked_i128(value, label))
}

/// Validate dimensions, lengths, numerator bounds, and shifted-state bounds.
pub fn validate_input(input: AffineInput) -> Result<AffineInput> {
    let rows = dimension(input.rows, "rows")?;
    let columns = dimension(input.columns, "columns")?;
    if input.a_row_major.len() != rows * columns
        || input.b.len() != rows
        || input.x0.len() != columns
        || input.delta_x.len() != columns
    {
        return Err(error("affine array length does not match dimensions"));
    }
    for (at, value) in input.a_row_major.iter().enumerate() {
        checked_input(*value, &format!("A[{at}]"))?;
    }
    for (at, value) in input.b.iter().enumerate() {
        checked_input(*value, &format!("b[{at}]"))?;
    }
    for (at, value) in input.x0.iter().enumerate() {
        checked_input(*value, &format!("x0[{at}]"))?;
    }
    for (at, value) in input.delta_x.iter().enumerate() {
        checked_input(*value, &format!("delta_x[{at}]"))?;
        let shifted = value
            .checked_add(input.x0[at])
            .ok_or_else(|| error("shifted state overflow"))?;
        if shifted < -MAX_SHIFTED_NUMERATOR || shifted > MAX_SHIFTED_NUMERATOR {
            return Err(error(format!("x0+delta_x[{at}] outside shifted bound")));
        }
    }
    Ok(input)
}

/// Evaluate the exact affine map independently of any native provider.
pub fn evaluate(input: &AffineInput) -> Result<AffineOutput> {
    let input = validate_input(input.clone())?;
    let rows = input.rows as usize;
    let columns = input.columns as usize;
    let mut baseline_output = Vec::with_capacity(rows);
    let mut contributions = Vec::with_capacity(rows * columns);
    let mut predicted_delta = Vec::with_capacity(rows);
    let mut predicted_output = Vec::with_capacity(rows);
    let mut model_output = Vec::with_capacity(rows);
    let mut residual = Vec::with_capacity(rows);
    for row in 0..rows {
        let mut baseline = mul(input.b[row] as i128, DENOMINATOR as i128, "offset")?;
        let mut delta = 0i128;
        let mut model = mul(input.b[row] as i128, DENOMINATOR as i128, "offset")?;
        for col in 0..columns {
            let coefficient = input.a_row_major[row * columns + col] as i128;
            baseline = add(
                baseline,
                mul(coefficient, input.x0[col] as i128, "baseline")?,
                "baseline",
            )?;
            let contribution = mul(coefficient, input.delta_x[col] as i128, "contribution")?;
            delta = add(delta, contribution, "predicted_delta")?;
            model = add(
                model,
                mul(
                    coefficient,
                    (input.x0[col] as i128)
                        .checked_add(input.delta_x[col] as i128)
                        .ok_or_else(|| error("model shifted state overflow"))?,
                    "model",
                )?,
                "model_output",
            )?;
            contributions.push(contribution);
        }
        let predicted = add(baseline, delta, "predicted_output")?;
        let difference = sub(model, predicted, "residual")?;
        baseline_output.push(baseline);
        predicted_delta.push(delta);
        predicted_output.push(predicted);
        model_output.push(model);
        residual.push(difference);
    }
    Ok(AffineOutput {
        rows: input.rows,
        columns: input.columns,
        baseline_output,
        contributions,
        predicted_delta,
        predicted_output,
        model_output,
        residual,
        denominator: OUTPUT_DENOMINATOR,
    })
}

fn fields<'a>(raw: &'a [u8], tag: &str, count: usize) -> Result<Vec<&'a [u8]>> {
    if raw.len() > 1 << 20 {
        return Err(error("canonical affine payload exceeds 1 MiB"));
    }
    let mut at = 0usize;
    let mut take = |length: usize, label: &str| -> Result<&'a [u8]> {
        let end = at
            .checked_add(length)
            .ok_or_else(|| error(format!("{label} length overflow")))?;
        if end > raw.len() {
            return Err(error(format!("truncated {label}")));
        }
        let out = &raw[at..end];
        at = end;
        Ok(out)
    };
    let u64le = |bytes: &[u8], label: &str| -> Result<u64> {
        let array: [u8; 8] = bytes
            .try_into()
            .map_err(|_| error(format!("{label} is not eight bytes")))?;
        Ok(u64::from_le_bytes(array))
    };
    let tag_length = u64le(take(8, "tag length")?, "tag length")?;
    let tag_bytes = take(
        usize::try_from(tag_length).map_err(|_| error("tag length does not fit usize"))?,
        "tag",
    )?;
    if tag_bytes != tag.as_bytes() {
        return Err(error("unexpected canonical tag"));
    }
    let field_count = u64le(take(8, "field count")?, "field count")?;
    if field_count != count as u64 {
        return Err(error("unexpected canonical field count"));
    }
    let mut result = Vec::with_capacity(count);
    for index in 0..count {
        let length = u64le(take(8, "field length")?, "field length")?;
        let length = usize::try_from(length)
            .map_err(|_| error(format!("field {index} length does not fit usize")))?;
        result.push(take(length, "field")?);
    }
    if at != raw.len() {
        return Err(error("trailing bytes after canonical affine payload"));
    }
    Ok(result)
}

fn u32_field(raw: &[u8], label: &str) -> Result<u32> {
    let bytes: [u8; 4] = raw
        .try_into()
        .map_err(|_| error(format!("{label} is not four bytes")))?;
    Ok(u32::from_le_bytes(bytes))
}

fn i64_values(raw: &[u8], count: usize, label: &str) -> Result<Vec<i64>> {
    if raw.len() != count * 8 {
        return Err(error(format!("{label} has wrong byte length")));
    }
    let mut values = Vec::with_capacity(count);
    for index in 0..count {
        let start = index * 8;
        let bytes: [u8; 8] = raw[start..start + 8].try_into().unwrap();
        values.push(i64::from_le_bytes(bytes));
    }
    Ok(values)
}

fn i128_values(raw: &[u8], count: usize, label: &str) -> Result<Vec<i128>> {
    if raw.len() != count * 16 {
        return Err(error(format!("{label} has wrong byte length")));
    }
    let mut values = Vec::with_capacity(count);
    for index in 0..count {
        let start = index * 16;
        let bytes: [u8; 16] = raw[start..start + 16].try_into().unwrap();
        values.push(i128::from_le_bytes(bytes));
    }
    Ok(values)
}

fn i64_bytes(values: &[i64]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(values.len() * 8);
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    bytes
}

fn i128_bytes(values: &[i128]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(values.len() * 16);
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    bytes
}

/// Encode the canonical exact input bytes.
pub fn encode_input(input: &AffineInput) -> Result<Vec<u8>> {
    let input = validate_input(input.clone())?;
    let rows = input.rows.to_le_bytes();
    let columns = input.columns.to_le_bytes();
    let a = i64_bytes(&input.a_row_major);
    let b = i64_bytes(&input.b);
    let x0 = i64_bytes(&input.x0);
    let delta_x = i64_bytes(&input.delta_x);
    Ok(canonical(
        INPUT_TAG,
        &[&rows, &columns, &a, &b, &x0, &delta_x],
    ))
}

/// Encode the canonical candidate/result bytes.
pub fn encode_output(output: &AffineOutput) -> Result<Vec<u8>> {
    let rows = dimension(output.rows, "rows")?;
    let columns = dimension(output.columns, "columns")?;
    if output.baseline_output.len() != rows
        || output.contributions.len() != rows * columns
        || output.predicted_delta.len() != rows
        || output.predicted_output.len() != rows
        || output.model_output.len() != rows
        || output.residual.len() != rows
        || output.denominator != OUTPUT_DENOMINATOR
    {
        return Err(error("output shape or denominator is invalid"));
    }
    let rows_bytes = output.rows.to_le_bytes();
    let columns_bytes = output.columns.to_le_bytes();
    let baseline = i128_bytes(&output.baseline_output);
    let contributions = i128_bytes(&output.contributions);
    let predicted_delta = i128_bytes(&output.predicted_delta);
    let predicted_output = i128_bytes(&output.predicted_output);
    let model_output = i128_bytes(&output.model_output);
    let residual = i128_bytes(&output.residual);
    let denominator = output.denominator.to_le_bytes();
    Ok(canonical(
        OUTPUT_TAG,
        &[
            &rows_bytes,
            &columns_bytes,
            &baseline,
            &contributions,
            &predicted_delta,
            &predicted_output,
            &model_output,
            &residual,
            &denominator,
        ],
    ))
}

/// Encode the outer statement binding profile, input, and candidate bytes.
pub fn encode_statement(input: &AffineInput, output: &AffineOutput) -> Result<Vec<u8>> {
    let input_bytes = encode_input(input)?;
    let output_bytes = encode_output(output)?;
    let scale = DENOMINATOR.to_le_bytes();
    let bound = (MAX_NUMERATOR as u32).to_le_bytes();
    Ok(canonical(
        STATEMENT_TAG,
        &[
            OPERATION,
            PROFILE,
            &scale,
            &bound,
            &input_bytes,
            &output_bytes,
        ],
    ))
}

/// Decode and validate canonical input bytes.
pub fn decode_input(raw: &[u8]) -> Result<AffineInput> {
    let values = fields(raw, INPUT_TAG, 6)?;
    let rows = u32_field(values[0], "rows")?;
    let columns = u32_field(values[1], "columns")?;
    let rows_usize = dimension(rows, "rows")?;
    let columns_usize = dimension(columns, "columns")?;
    let input = AffineInput {
        rows,
        columns,
        a_row_major: i64_values(values[2], rows_usize * columns_usize, "A")?,
        b: i64_values(values[3], rows_usize, "b")?,
        x0: i64_values(values[4], columns_usize, "x0")?,
        delta_x: i64_values(values[5], columns_usize, "delta_x")?,
    };
    validate_input(input)
}

/// Decode canonical output bytes.
pub fn decode_output(raw: &[u8]) -> Result<AffineOutput> {
    let values = fields(raw, OUTPUT_TAG, 9)?;
    let rows = u32_field(values[0], "rows")?;
    let columns = u32_field(values[1], "columns")?;
    let rows_usize = dimension(rows, "rows")?;
    let columns_usize = dimension(columns, "columns")?;
    let output = AffineOutput {
        rows,
        columns,
        baseline_output: i128_values(values[2], rows_usize, "baseline_output")?,
        contributions: i128_values(values[3], rows_usize * columns_usize, "contributions")?,
        predicted_delta: i128_values(values[4], rows_usize, "predicted_delta")?,
        predicted_output: i128_values(values[5], rows_usize, "predicted_output")?,
        model_output: i128_values(values[6], rows_usize, "model_output")?,
        residual: i128_values(values[7], rows_usize, "residual")?,
        denominator: u32_field(values[8], "denominator")?,
    };
    if output.denominator != OUTPUT_DENOMINATOR {
        return Err(error("output denominator is not 65536"));
    }
    // encode_output performs the shape check without changing the decoded
    // values, and keeps this parser's accepted language identical to the
    // serializer's language.
    let _ = encode_output(&output)?;
    Ok(output)
}

/// Check a complete exact statement, returning the bytes and commitments the
/// SP1 guest must bind in its public values.
pub fn check_statement(statement: &[u8]) -> Result<AffineChecked> {
    let values = fields(statement, STATEMENT_TAG, 6)?;
    if values[0] != OPERATION || values[1] != PROFILE {
        return Err(error("operation or profile is not affine-d256.v1"));
    }
    if u32_field(values[2], "scale")? != DENOMINATOR {
        return Err(error("statement scale is not D=256"));
    }
    if u32_field(values[3], "bound")? != MAX_NUMERATOR as u32 {
        return Err(error("statement bound is not 4096"));
    }
    let input = decode_input(values[4])?;
    let expected = evaluate(&input)?;
    let output = decode_output(values[5])?;
    if output != expected {
        return Err(error("candidate output does not equal exact affine result"));
    }
    let input_bytes = values[4].to_vec();
    let output_bytes = values[5].to_vec();
    Ok(AffineChecked {
        statement_bytes: statement.to_vec(),
        input_bytes: input_bytes.clone(),
        output_bytes: output_bytes.clone(),
        input,
        output,
        input_commitment: *commit(CANONICAL_INPUT_TAG, &[&input_bytes]).as_bytes(),
        output_commitment: *commit(CANONICAL_OUTPUT_TAG, &[&output_bytes]).as_bytes(),
        operation_commitment: *commit(PROFILE_COMMITMENT_TAG, &[OPERATION]).as_bytes(),
        profile_commitment: *commit(PROFILE_COMMITMENT_TAG, &[PROFILE]).as_bytes(),
    })
}

/// The public-values fields committed by a valid affine guest execution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffinePublicValues {
    pub input_commitment: [u8; 32],
    pub output_commitment: Option<[u8; 32]>,
    pub operation_commitment: [u8; 32],
    pub profile_commitment: [u8; 32],
    pub rows: u32,
    pub columns: u32,
    pub denominator: u32,
    pub bound: u32,
    pub exit_code: u32,
}

/// Serialize the profile-specific public-values layout.
pub fn encode_public_values(value: &AffinePublicValues) -> Vec<u8> {
    let mut out = Vec::with_capacity(32 + 1 + 32 + 32 + 32 + 4 * 5 + PUBLIC_VALUES_TAG.len());
    out.extend_from_slice(PUBLIC_VALUES_TAG);
    out.extend_from_slice(&value.input_commitment);
    match value.output_commitment {
        Some(output) => {
            out.push(0);
            out.extend_from_slice(&output);
        }
        None => out.push(1),
    }
    out.extend_from_slice(&value.operation_commitment);
    out.extend_from_slice(&value.profile_commitment);
    out.extend_from_slice(&value.rows.to_le_bytes());
    out.extend_from_slice(&value.columns.to_le_bytes());
    out.extend_from_slice(&value.denominator.to_le_bytes());
    out.extend_from_slice(&value.bound.to_le_bytes());
    out.extend_from_slice(&value.exit_code.to_le_bytes());
    out
}

/// Parse the profile-specific public-values layout strictly.
fn public_take<'a>(raw: &'a [u8], at: &mut usize, length: usize) -> Result<&'a [u8]> {
    let end = at
        .checked_add(length)
        .ok_or_else(|| error("public length overflow"))?;
    if end > raw.len() {
        return Err(error("truncated affine public values"));
    }
    let value = &raw[*at..end];
    *at = end;
    Ok(value)
}

pub fn parse_public_values(raw: &[u8]) -> Result<AffinePublicValues> {
    let mut at = 0usize;
    if public_take(raw, &mut at, PUBLIC_VALUES_TAG.len())? != PUBLIC_VALUES_TAG {
        return Err(error("unexpected affine public-values tag"));
    }
    let input: [u8; 32] = public_take(raw, &mut at, 32)?.try_into().unwrap();
    let marker = *public_take(raw, &mut at, 1)?.first().unwrap();
    let output = match marker {
        0 => Some(public_take(raw, &mut at, 32)?.try_into().unwrap()),
        1 => None,
        _ => return Err(error("invalid affine public output marker")),
    };
    let operation: [u8; 32] = public_take(raw, &mut at, 32)?.try_into().unwrap();
    let profile: [u8; 32] = public_take(raw, &mut at, 32)?.try_into().unwrap();
    let u32_value = |raw: &[u8], at: &mut usize, label: &str| -> Result<u32> {
        let bytes: [u8; 4] = public_take(raw, at, 4)?.try_into().unwrap();
        let value = u32::from_le_bytes(bytes);
        let _ = label;
        Ok(value)
    };
    let values = AffinePublicValues {
        input_commitment: input,
        output_commitment: output,
        operation_commitment: operation,
        profile_commitment: profile,
        rows: u32_value(raw, &mut at, "rows")?,
        columns: u32_value(raw, &mut at, "columns")?,
        denominator: u32_value(raw, &mut at, "denominator")?,
        bound: u32_value(raw, &mut at, "bound")?,
        exit_code: u32_value(raw, &mut at, "exit_code")?,
    };
    if at != raw.len() {
        return Err(error("trailing bytes after affine public values"));
    }
    Ok(values)
}

impl AffinePublicValues {
    /// Construct the expected successful public values for a checked input.
    pub fn completed(checked: &AffineChecked) -> Self {
        Self {
            input_commitment: checked.input_commitment,
            output_commitment: Some(checked.output_commitment),
            operation_commitment: checked.operation_commitment,
            profile_commitment: checked.profile_commitment,
            rows: checked.input.rows,
            columns: checked.input.columns,
            denominator: DENOMINATOR,
            bound: MAX_NUMERATOR as u32,
            exit_code: 0,
        }
    }

    /// Check all public fields against the canonical statement, including
    /// fixed arithmetic parameters and the output marker.
    pub fn matches(&self, checked: &AffineChecked) -> bool {
        self == &Self::completed(checked)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn golden_input() -> AffineInput {
        AffineInput {
            rows: 2,
            columns: 3,
            a_row_major: vec![512, 256, -256, -256, 768, 512],
            b: vec![1280, -512],
            x0: vec![768, 1024, 512],
            delta_x: vec![64, -128, 32],
        }
    }

    #[test]
    fn exact_golden_and_canonical_roundtrip() {
        let input = golden_input();
        let output = evaluate(&input).unwrap();
        assert_eq!(output.baseline_output, vec![851_968, 720_896]);
        assert_eq!(
            output.contributions,
            vec![32_768, -32_768, -8_192, -16_384, -98_304, 16_384]
        );
        assert_eq!(output.predicted_delta, vec![-8_192, -98_304]);
        assert_eq!(output.predicted_output, vec![843_776, 622_592]);
        assert_eq!(output.model_output, output.predicted_output);
        assert_eq!(output.residual, vec![0, 0]);
        let statement = encode_statement(&input, &output).unwrap();
        let checked = check_statement(&statement).unwrap();
        assert_eq!(checked.input, input);
        assert_eq!(checked.output, output);
        let public = AffinePublicValues::completed(&checked);
        assert_eq!(
            parse_public_values(&encode_public_values(&public)).unwrap(),
            public
        );
    }

    #[test]
    fn candidate_mutation_and_profile_mutation_refuse() {
        let input = golden_input();
        let output = evaluate(&input).unwrap();
        let mut statement = encode_statement(&input, &output).unwrap();
        let last = statement.len() - 1;
        statement[last] ^= 1;
        assert!(check_statement(&statement).is_err());
        let mut statement = encode_statement(&input, &output).unwrap();
        let marker = statement
            .windows(OPERATION.len())
            .position(|window| window == OPERATION)
            .unwrap();
        statement[marker] = b'x';
        assert!(check_statement(&statement).is_err());
    }
}
