# STAQ Estimation Testbed (SET v0)

A deterministic framework for evaluating physical state estimation under degraded observability.

---

## Purpose

To measure how accurately system state can be reconstructed when sensor inputs are incomplete, noisy, delayed, or corrupted.

---

## System Model

Physical system state is inferred through a closed loop:

Physical dynamics  
→ Sensors (GNSS / IMU)  
→ Degradation (noise, drift, dropout, latency)  
→ State estimation (e.g. Kalman filter, dead reckoning)  
→ Error evaluation against ground truth

---

## Core Objective

Quantify reconstruction error of latent system state under controlled failure modes.

---

## Components

- State model: generates ground truth trajectories  
- Sensor model: produces observations from state  
- Degradation model: applies controlled signal corruption  
- Estimator: reconstructs state from observations  
- Metrics: computes deviation from ground truth  

---

## Constraints

- Fully deterministic execution  
- Seed-controlled randomness  
- Reproducible experiments  
- Swappable components  

---

## Scope

This system is not a robotics stack, physics engine, or ML framework.

It is an evaluation environment for state inference under degraded observability.

---

## License

Apache 2.0
