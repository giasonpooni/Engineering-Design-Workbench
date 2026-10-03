use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateError {
    Condition,
    RoundTrip,
    ExactZeroCross,
    NotFinite,
    Shape,
    NotPsd,
}

impl GateError {
    pub fn message(&self, name: &str) -> String {
        match self {
            GateError::Condition => format!("{name} must be invertible with condition number <= 1e12"),
            GateError::RoundTrip => format!("{name} loses precision in the coordinate round trip (tolerance 1e-8)"),
            GateError::ExactZeroCross => format!("{name} creates uncertainty in an exact zero direction during the coordinate round trip"),
            GateError::NotFinite => format!("{name} must contain finite numbers"),
            GateError::Shape => format!("{name} has incompatible shape"),
            GateError::NotPsd => format!("{name} must be positive semidefinite"),
        }
    }
}

impl fmt::Display for GateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message("matrix"))
    }
}

impl std::error::Error for GateError {}
