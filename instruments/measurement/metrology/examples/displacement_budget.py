"""Declared GUM budget for the displacement stand. Not a field certificate."""

from instrument_chain.uncertainty_budget import Budget, Dist, TypeA, TypeB


def bench_budget() -> Budget:
    # y = 0.01 * raw  is a declared scale; components already in millimetres.
    return Budget(
        measurand="displacement",
        unit="mm",
        traceability="none_claimed",
        components=[
            TypeB("quantization", Dist.RECTANGULAR, half_width=0.005),
            TypeB("nonlinearity", Dist.TRIANGULAR, half_width=0.004),
            TypeA("repeatability", s=0.0031, n=50, statistic="mean"),
            TypeB("thermal_drift", Dist.RECTANGULAR, half_width=1.2e-4 * 5.0),
            TypeB("ref_mass", Dist.NORMAL, std=0.0004, k=2.0),
        ],
    )


def main() -> None:
    b = bench_budget()
    rec = b.to_record()
    print(f"u_c     = {rec['u_c']:.6f} mm")
    print(f"dof_eff = {rec['dof_eff']}")
    print(f"k       = {rec['k']:.3f}")
    print(f"U(95%)  = {rec['U']:.6f} mm")
    print(f"traceability = {rec['traceability']}")
    for row in rec["contributions"]:
        print(f"  {row['source']:16s} u_i={row['u_i']:.6f}  share={row['variance_share']*100:.1f}%")


if __name__ == "__main__":
    main()
