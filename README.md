# STAQ Estimation Testbed (SET v0)

A deterministic evaluation framework for state estimation under degraded observability in physical and signal-based systems.

---

## Purpose

To evaluate how accurately latent system states can be reconstructed when observations are:
- noisy  
- incomplete  
- delayed  
- drifted  
- intermittently unavailable  

The focus is on controlled degradation of observability and measurement integrity.

---

## System Model

The framework is structured as a closed-loop estimation pipeline:

**Physical system dynamics**  
→ **Observation layer (sensors / telemetry)**  
→ **Degradation layer (noise, drift, dropout, latency, corruption)**  
→ **State estimator (e.g. Kalman filter, dead reckoning, particle methods)**  
→ **Evaluation layer (error vs ground truth)**  

---

## Core Objective

Quantitatively measure reconstruction accuracy of latent system state under systematically controlled failure modes.

---

## Components

### 1. State Model
Generates ground-truth trajectories of a dynamical system.

### 2. Observation Model
Maps latent state into measurable signals (e.g. GNSS, IMU, synthetic telemetry).

### 3. Degradation Model
Applies controlled impairments to observations, including:
- stochastic noise injection  
- temporal delay  
- signal dropout  
- bias / drift  
- quantization or compression effects  

### 4. Estimation Layer
Reconstructs latent state from degraded observations using configurable inference methods.

### 5. Evaluation Layer
Computes deviation metrics between estimated state and ground truth, including:
- positional error  
- velocity error  
- trajectory divergence  
- stability under drift conditions  

---

## Experimental Constraints

- Fully deterministic execution environment  
- Seed-controlled stochastic processes  
- Reproducible simulation runs  
- Modular and swappable system components  
- Consistent evaluation metrics across experiments  

---

## Scope Definition

This framework is an evaluation environment for state inference under degraded observability conditions.

It is designed for:
- comparative estimator analysis  
- robustness testing under controlled signal degradation  
- structured evaluation of inference stability  

It is not a robotics stack, control system, or machine learning training framework.

---

## License

Apache 2.0
