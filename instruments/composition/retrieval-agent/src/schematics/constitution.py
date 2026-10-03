"""Ownership. This package does not own A, V, samples, or dispositions."""

KERNEL_OWNERS = {
    "jspt": "Jacobian-Sensitivity-Propagation-Testbed owns A = J and chart law.",
    "plsr": "Parameterized-Lyapunov-Stability-Runtime owns V, not A.",
    "rci": "Retrofitted-Computational-Instrumentation owns the sample.",
    "cse": "Construction-State-Estimator-for-BIM owns SATISFIED / VIOLATED / UNRESOLVED.",
}

FORBIDDEN = (
    "Do not import sensitivity at module load or add it as a default dependency.",
    "Do not synthesize P.",
    "Do not treat a fixture A as a JSPT sample or a PLSR input.",
    "Do not invent nets, measures, or h edges from names or renders.",
    "Do not treat USD display or proximity as a measurement factor.",
    "Do not clip a refuse into a sampled highlight.",
    "Do not interpret an RCI digest as a state.",
)
