# Moving SPH computational parcels

The `sph` profile moves equal-mass computational parcels in a periodic
one-dimensional barotropic continuum. It implements an acoustic pressure-wave
benchmark with density summation and conservative symmetric pressure forces.
These parcels represent continuum mass. They have no molecular, chemical,
suspended-grain or free-surface identities.

## State and mechanics

The model declares length `L`, cross-sectional area `A`, reference density
`rho0`, acoustic speed `c`, and a small material strain amplitude `a`. At a
resolution of `N` parcels, `dx=L/N`, `h=2*dx`, and every parcel carries
`m=rho0*A*dx`. Coordinates remain unwrapped so a periodic crossing retains the
same parcel and trajectory. Interactions use minimum-image distances and a
fixed kernel whose support radius `2*h` is smaller than half the domain.

For `q=abs(r)/h`, the normalized one-dimensional cubic B-spline is

```math
W(r,h)=\frac{2}{3h}\begin{cases}
1-\frac32q^2+\frac34q^3,&0\le q<1,\\
\frac14(2-q)^3,&1\le q<2,\\
0,&q\ge2.
\end{cases}
```

Its continuous integral is one. At the declared `h=2*dx`, the uniform periodic
lattice also has `dx*sum_j W(x_i-x_j)=1` exactly in exact arithmetic. The area
conversion is explicit:

```math
\rho_i=\sum_j\frac{m_j}{A}W_{ij},\qquad
p_i=c^2(\rho_i-\rho_0),\qquad
\ddot x_i=-\sum_j\frac{m_j}{A}
\left(\frac{p_i}{\rho_i^2}+\frac{p_j}{\rho_j^2}\right)W'_{ij}.
```

The equal and opposite pair forces conserve total linear momentum. The
barotropic internal-energy primitive satisfies `de/drho=p/rho^2`:

```math
e(\rho)=c^2\left[\log(\rho/\rho_0)+\rho_0/\rho-1\right],\qquad
E=\sum_i m_i\left(\frac12v_i^2+e(\rho_i)\right).
```

The provider evaluates a bounded local series for this primitive to avoid
cancellation near `rho=rho0`; the independent reference uses an eight-point
Gaussian integral of `de/drho=p/rho^2`. This independently evaluates the same
primitive without depending on platform-specific extended precision. Negative
pressure perturbations are allowed around the
zero-pressure equilibrium. The profile does not provide tensile-fracture,
cavitation, shock or long-time stability predictions.

The initial material coordinates are `q_i=(i+1/2)*dx`, with
`x_i=q_i-a*sin(k*q_i)/k` and `v_i=c*a*cos(k*q_i)`, where `k=2*pi/L`.
The independent linear continuum benchmark translates this sinusoid at speed
`c`. Finite kernel smoothing and small nonlinear corrections mean that the
continuum benchmark is approximate. A separately derived SPH force and
high-resolution RK4 solution provide the discrete-model reference.

## Bounded qualification

Requests allow 32 or 64 base parcels, 32–128 base timesteps, and at most 4096
base parcel-timestep products. Five retained traces give three timestep levels
at fixed parcels and three parcel counts at the finest timestep. The default
contains 32 parcels and 32 steps, uses about 2.7 MB of result JSON, and requires
only NumPy and bounded CPU computation.

Hard physical guards apply independently of requested numerical tolerances:

- Declared strain amplitude is between `1e-5` and `5e-4`.
- The horizon is between 0.05 and 0.125 acoustic periods.
- Every integration level satisfies `c*dt/h <= 0.1`.
- Retained Mach number and relative density deviation are at most 0.002.
- Parcel order remains intact, with every periodic neighbor gap within one
  percent of the original lattice spacing.

Fresh verification independently checks density summation, EOS, scalar
energies and momenta, every Verlet transition, momentum conservation, bounded
energy drift, and finite-difference Hamiltonian force gradients. It measures
three-level temporal and spatial trends from the actual trajectories. The
refinement comparison retains the mean and first two material-coordinate
Fourier harmonics; complete field histories receive separate numerical audits.
Two RK4 reference resolutions check reference accuracy.

The default benchmark passes with temporal order approximately 2.000 and
spatial order approximately 1.975. Its coarse energy drift is about
`1.8e-6`, and its maximum normalized discrepancy against the linear acoustic
continuum benchmark is approximately 0.035. These are benchmark results,
not bounds for arbitrary geometries or initial states.

`LOCAL` qualifies only this declared synthetic numerical scope. Surface
gravity waves, free surfaces, shocks, turbulence, viscosity, adaptive kernels,
molecular response and structural coupling require additional providers and
route `EXPAND`. Experimental validation and canonical admission claims route
`REFUSE`. Static retained inspection validates declarations, seals and bindings
without executing either solver or verifier; it cannot establish fresh physics
or authenticate an instrument.

## Use

```bash
net fluid example --profile sph --output sph-request.json
net fluid run --request sph-request.json --output-dir sph-run
net fluid inspect sph-run
net fluid verify sph-run --output sph-fresh-verification.json
net fluid export-csv sph-run --output sph-primary.csv
net fluid reduce sph-run --sample-index 0 --bins 4 --output sph-bin-map.json
```

CSV retains each parcel's index, mass, unwrapped position, velocity, density
and pressure at every primary model timestamp. Particle-to-bin reduction
preserves instantaneous extensive mass and momentum and separates resolved
mean-motion kinetic energy from subcell kinetic energy. It discards individual
parcel detail and does not supply a constitutive closure, transport coefficient
or future evolution model.

Run the provider and independent audits with:

```bash
python -m pytest -q tests/test_fluid_sph.py tests/test_fluid_sph_independent.py
```

The installed CLI qualification script also exercises all five fluid profiles,
new verification occurrence identities, gated CSV export, conservative
particle reductions, and a synthetic held-out reservoir comparison. A
synthetic comparison supplies no physical validation or measured support.

## Primary references

- [Price, *Smoothed Particle Hydrodynamics and Magnetohydrodynamics* (2012)](https://arxiv.org/abs/1012.1885)
  derives conservative SPH motion and energy from density estimation and a
  discrete Lagrangian. Its [author-hosted paper](https://users.monash.edu.au/~dprice/pubs/spmhd/price-spmhd-jcp.pdf)
  explains the connection between the density estimate, thermodynamic energy
  and conservative equations. This provider uses fixed smoothing lengths;
  adaptive smoothing terms are absent.
- [Monaghan, *Smoothed Particle Hydrodynamics* (1992)](https://doi.org/10.1146/annurev.aa.30.090192.002551)
  is the foundational review for the compact cubic spline and particle
  hydrodynamics formulation.
- [PySPH's cubic-spline implementation](https://pysph.readthedocs.io/en/main/_modules/pysph/base/kernels.html)
  documents the one-dimensional `2/(3*h)` normalization and piecewise kernel
  derivative. NET supplies its own bounded implementation and does not run
  PySPH.
