# Float64 oscillator RHS. State: (q [m], v [m/s]); parameters: (gamma [1/s], omega [rad/s]).
# This single definition is both evaluated by Julia and lowered by export.jl.
oscillator_rhs(q, v, gamma, omega) = (v, (((-2.0 * gamma) * v) - ((omega * omega) * q)))
