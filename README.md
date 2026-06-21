# 📊 State Estimation Testbed (SET v0)

A deterministic evaluation framework for spatiotemporal state reconstruction under degraded observability in physical field systems.

Part of the **STAQ Lyapunov-stabilized inference and calibration stack**.

---

## Purpose

SET evaluates reconstruction fidelity of latent **spatiotemporal state fields** under controlled observability degradation.

It quantifies how well a system reconstructs:

\[
I(x, y, t)
\]

when observations are corrupted, incomplete, delayed, or spectrally compressed.

It focuses on **controlled failure injection with fully reproducible evaluation dynamics**.

---

## Core Objective

To measure:

> how accurately a latent spatiotemporal field can be reconstructed under structured observability degradation regimes.

---

## System Model

SET is structured as a closed-loop field inference evaluation pipeline:


Spatiotemporal Ground Truth Field I(x,y,t)
↓
Observation Operator h(·)
↓
Degradation Layer (Noise / Drift / Dropout / Latency / JPEG-like compression)
↓
Estimation Layer (State Reconstruction)
↓
LCM Calibration Layer (Constraint + Stability Projection)
↓
Evaluation Layer (Error + Stability Metrics vs Ground Truth)


---

## Components

### 1. Field State Model

Generates ground-truth evolution of a continuous system:

- spatial dynamics  
- temporal evolution  
- phase structure (quadrature decomposition)  
- structural deformation  

---

### 2. Observation Model

Maps field → measurable signals:

\[
y(t) = h(I(x,y,t)) + \epsilon(t)
\]

Includes:

- GNSS-like sampling  
- IMU / inertial projections  
- telemetry streams  
- quadrature-phase signals  

---

### 3. Degradation Model

Simulates controlled loss of observability:

- stochastic noise  
- drift and bias  
- temporal delay  
- packet dropout  
- quantization  
- JPEG-like spectral compression (lossy projection operator)  
- PNG lossless sampling (ground-truth anchor mode)  

Defines:

> how field observability collapses over time

---

### 4. Estimation Layer

Reconstructs latent field:

- Kalman / Extended Kalman Filters  
- Particle Filters  
- PINNs  
- graph-based estimators  
- STAQ hybrid inference systems  

Outputs:

\[
\hat{I}(x,y,t)
\]

---

### 5. Lattice-Calibration Layer (LCM)

Projects reconstructed state onto:

- constraint manifold  
- physically valid state space  
- Lyapunov-stabilized region  

Ensures:

- geometric consistency  
- physical validity  
- temporal stability  

---

### 6. Evaluation Layer

Computes multi-domain error:

#### Spatial error
- geodesic deviation on manifold  

#### Temporal error
- drift accumulation over time  

#### Spectral error
- ω-domain distortion (loss of structure vs motion separation)

#### Stability error
- Lyapunov violation:
\[
V(x_{t+1}) \leq V(x_t)
\]

#### Constraint error
- manifold projection residual  

---

## Experimental Constraints

- Fully deterministic execution  
- Seed-controlled stochastic processes  
- Reproducible simulation runs  
- Modular estimator injection  
- Consistent cross-system metrics  

---

## Scope Definition

SET is NOT:

- a robotics control system  
- a machine learning training framework  
- an autonomous decision engine  

It IS:

> a deterministic evaluation substrate for spatiotemporal field reconstruction systems under controlled observability failure regimes  

---

## Relationship to STAQ Architecture

SET evaluates:

- **GCE** → geometric correctness of reconstruction  
- **SICRE** → structural validity of ingestion  
- **LCM** → constraint + stability enforcement  
- **Estimator stack** → inference quality under degradation  
- **JPEG/PNG operators** → spectral vs lossless field reconstruction modes  

---

## Key Conceptual Shift

SET does NOT evaluate “accuracy”.

It evaluates:

> stability of reconstructed reality under degraded observability

---

## License

Apache 2.0
```

---
