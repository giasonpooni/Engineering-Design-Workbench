# STAQ-Estimation-Testbed-Domain-Instantiation-v0-
A controlled environment for evaluating closed-loop physical state inference under degraded observability.

# STAQ Estimation Testbed (SET v0)

## Subtext
Physical State Inference Under Degraded Observability

---

## Overview

STAQ Estimation Testbed is a deterministic experimentation framework for evaluating how physical system state is reconstructed from imperfect, delayed, or degraded sensor observations.

It operates in the domain of closed-loop physical inference systems where:

> physical reality → sensing → degradation → inference → evaluation

is treated as a single reproducible system.

---

## Domain Definition

STAQ operates in systems where:

- physical dynamics generate signals
- sensors produce incomplete or noisy observations
- computation reconstructs latent system state
- downstream control depends on reconstructed state fidelity

This framework formalizes this loop as a deterministic experimental environment.

---

## Core Principle

System behavior is a function of observability under degradation.

---

## System Architecture >

#### 1. State Model (Reality Layer)

Defines deterministic system motion.

Supported v0 models:
- constant velocity
- basic acceleration (optional extension)

Output:
- ground truth state trajectory

---

#### 2. Sensor / Signal Layer

Converts ground truth into imperfect observations.

Supported sensors:
- GNSS (position measurements)
- IMU (motion-derived signals)

Includes:
- Gaussian noise
- bias drift
- scaling error

---

#### 3. Degradation Layer

Controls observability failure modes.

Supported mechanisms:
- dropout windows
- latency injection
- drift amplification
- intermittent corruption

All degradation is:
- deterministic
- seed-controlled
- scenario-defined

---

#### 4. State Estimation Layer

Reconstructs state from observations.

Baseline estimators:
- dead reckoning
- Kalman filter

Interface:

```python
state = estimator.update(observation)## Core Components

#### 1. State Model (Reality Layer)

Defines deterministic system motion.

Supported v0 models:
- constant velocity
- basic acceleration (optional extension)

Output:
- ground truth state trajectory

---

#### 2. Sensor / Signal Layer

Converts ground truth into imperfect observations.

Supported sensors:
- GNSS (position measurements)
- IMU (motion-derived signals)

Includes:
- Gaussian noise
- bias drift
- scaling error

---

#### 3. Degradation Layer

Controls observability failure modes.

Supported mechanisms:
- dropout windows
- latency injection
- drift amplification
- intermittent corruption

All degradation is:
- deterministic
- seed-controlled
- scenario-defined

---

#### 4. State Estimation Layer

Reconstructs state from observations.

Baseline estimators:
- dead reckoning
- Kalman filter

Interface:

```python
state = estimator.update(observation)**
