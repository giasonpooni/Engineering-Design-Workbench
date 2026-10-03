# Classical atomistic-site provider

The molecular profile propagates actual three-dimensional positions and
velocities for 2–32 structureless interaction sites in a cubic periodic box.
A site has no water, polymer, bonded, electronic or chemical identity. The
default eight-site moving cluster is a numerical benchmark, not a validated
bulk liquid or equilibrium sample.

The potential is a force-shifted 12–6 Lennard-Jones model. Both potential and
radial force approach zero at the cutoff; the cutoff is strictly below half
the box length. Pair forces are equal and opposite. Velocity Verlet runs at
three time resolutions. A separately implemented scalar radial derivative
and RK4 integrator run at eightfold and sixteenfold primary resolution.
Verification also checks force/potential finite differences, every retained
pair force, the discrete integrator equations, momentum and energy histories.

The provider uses reduced LJ units with mass, sigma, epsilon and Boltzmann
constant set to one. An optional declaration of `sigma_m`, `epsilon_j` and
`site_mass_kg` defines SI scales: length = sigma; energy = epsilon; time =
sigma × sqrt(mass/epsilon). These scales remain explicitly unvalidated.
Retained trajectories and CSV exports keep their reduced-unit labels.

Number density is site count divided by box volume. Kinetic temperature
subtracts center-of-mass velocity and uses 3(N−1) degrees of freedom. The
instantaneous virial pressure uses the same thermal kinetic energy. These
toy observables establish neither equilibrium nor transport coefficients.

Hard initial separation, runtime overlap, timestep, site count and allocation
bounds apply independently of requested tolerances. Numerical qualification
can be LOCAL only when all checks pass and desired observables remain within
scope. Material calibration, water/polymer models, transport parameters and
cross-scale arrows require further providers and evidence; experimental or
design authority is refused.

Primary references, consulted 2026-10-03:

- [LAMMPS force-shifted LJ](https://docs.lammps.org/pair_lj_smooth_linear.html).
- [LAMMPS reduced LJ units](https://docs.lammps.org/units.html).
- [LAMMPS temperature convention](https://docs.lammps.org/compute_temp.html).
- [LAMMPS pressure/virial convention](https://docs.lammps.org/compute_pressure.html).
