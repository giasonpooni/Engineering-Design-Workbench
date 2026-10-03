//! CPU gate. NumPy JSPT remains the oracle. No PyO3 yet.

pub mod chart;
pub mod constitution;
pub mod covariance;
pub mod error;
pub mod matrix;
pub mod structure;

pub use chart::Chart;
pub use constitution::{MAX_CONDITION_NUMBER, ROUND_TRIP_TOLERANCE};
pub use covariance::push_covariance;
pub use error::GateError;
pub use matrix::{kappa2, skeel, Mat};
pub use structure::{structure, LocalStructure};
