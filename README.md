# Estimation Testbed (SET v0) for Sensor, Telemetry, and Quadrature Systems

A deterministic evaluation framework for state estimation under degraded observability in physical and signal-based systems.

Part of the STAQ Cyber-Physical Inference and Calibration Stack.

---

## Purpose

SET evaluates reconstruction fidelity of latent system states under controlled observability degradation.

It quantifies estimator robustness when observations are:

- noisy  
- incomplete  
- delayed  
- drifted  
- intermittently unavailable  

The focus is controlled failure injection with fully reproducible evaluation dynamics.

---

## System Model

SET is structured as a closed-loop evaluation pipeline:

Physical Dynamics
↓
Observation Layer (Sensors / Telemetry)
↓
Degradation Layer (Noise / Drift / Dropout / Latency / Corruption)
↓
Estimation Layer (State Reconstruction)
↓
Evaluation Layer (Error vs Ground Truth)


## Core Objective

To measure:

> how accurately a latent system state can be reconstructed under systematically controlled observability failure regimes.

---

## Components

### 1. State Model
Generates ground-truth trajectories of a dynamical system:

- motion dynamics  
- latent state evolution  
- controllable system parameters  

---

### 2. Observation Model
Maps latent state into measurement space:

Examples:
- GNSS-like position outputs  
- IMU inertial measurements  
- synthetic telemetry signals  

Produces:

\[
y(t) = h(x(t)) + \epsilon(t)
\]

---

### 3. Degradation Model
Imposes controlled observability breakdown:

- stochastic noise  
- temporal delay  
- packet dropout  
- bias / drift  
- quantization / compression  

Defines the measurement corruption regime:

> how observability fails over time

---

### 4. Estimation Layer
Reconstructs latent state from degraded observations using interchangeable estimators:

- Kalman / extended Kalman filters  
- dead reckoning models  
- particle filters  
- custom inference systems (e.g. lattice-coupled estimators)

Outputs:

\[
\hat{x}(t)
\]

---

### 5. Evaluation Layer
Computes reconstruction error relative to ground truth:

- positional error  
- velocity error  
- trajectory divergence  
- stability under drift  
- long-horizon consistency  

Defines estimator performance under degradation regimes.

---

## Experimental Constraints

- Fully deterministic execution  
- Seed-controlled stochastic processes  
- Reproducible simulation runs  
- Modular and swappable system components  
- Consistent evaluation metrics across experiments  

---

## Scope Definition

SET is strictly a deterministic evaluation and benchmarking environment.

It is intended for:

- estimator comparison under identical failure conditions  
- robustness analysis under controlled degradation  
- structured evaluation of inference stability  

It is not:
- a robotics stack  
- a control system  
- a machine learning training framework  

---

## Relationship to STAQ Architecture

SET defines the evaluation substrate for STAQ systems:

- lattice-based estimators (LCF)  
- geodesic coordinate systems (GCE)  
- structural reconstruction systems (SICRE)  

It provides the controlled environment in which these systems are evaluated, compared, and stress-tested.

---

## License

Apache 2.0
