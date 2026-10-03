"""Explicit candidate mapping into SET's pinned result-artifact contract."""
from dataclasses import asdict
import json

from sidt import fit_lti
from sidt.exchange import export_result

try:
    from .replay import trajectory
except ImportError:
    from replay import trajectory


def export_candidate(candidate, states, inputs, outputs=None, *, execution_ref="execution:sidt-synthetic-1"):
    """Example-only mapping; refs, time, and all-zero revision are synthetic declarations."""
    metadata = candidate.metadata
    components = []
    for label, matrix, rows, columns, row_units, column_units in (
        ("A", candidate.A, metadata.state_names, metadata.state_names, metadata.state_units, metadata.state_units),
        ("B", candidate.B, metadata.state_names, metadata.input_names, metadata.state_units, metadata.input_units),
        ("C", candidate.C, metadata.output_names, metadata.state_names, metadata.output_units, metadata.state_units),
        ("D", candidate.D, metadata.output_names, metadata.input_names, metadata.output_units, metadata.input_units),
    ):
        if matrix is not None:
            for row, row_name in enumerate(rows):
                for column, column_name in enumerate(columns):
                    numerator, denominator = row_units[row], column_units[column]
                    components.append({
                        "name": f"{label}[{row_name},{column_name}]",
                        "value": float(matrix[row, column]),
                        "unit": "1" if numerator == denominator else f"({numerator})/({denominator})",
                    })
    diagnostic = candidate.diagnostics
    numerical_result = {
        "status": "candidate_only", "candidate_digest": candidate.candidate_digest,
        "A": candidate.A.tolist(), "B": candidate.B.tolist(),
        "C": None if candidate.C is None else candidate.C.tolist(),
        "D": None if candidate.D is None else candidate.D.tolist(),
        "metadata": asdict(metadata),
        "diagnostics": {
            "sample_count": diagnostic.sample_count,
            "regressor_count": diagnostic.regressor_count,
            "rank": diagnostic.rank,
            "singular_values": diagnostic.singular_values.tolist(),
            "relative_rank_cutoff": diagnostic.relative_rank_cutoff,
            "degrees_of_freedom": diagnostic.degrees_of_freedom,
            "state_residuals": diagnostic.state_residuals.tolist(),
            "state_residual_sum_squares": diagnostic.state_residual_sum_squares.tolist(),
            "output_residuals": None if diagnostic.output_residuals is None else diagnostic.output_residuals.tolist(),
            "output_residual_sum_squares": None if diagnostic.output_residual_sum_squares is None else diagnostic.output_residual_sum_squares.tolist(),
        },
    }
    return export_result(
        operation_id=metadata.operation,
        execution_ref=execution_ref,
        source_revision="0" * 40,  # Synthetic caller declaration, never an attested repository revision.
        created_at="2026-01-01T00:00:00Z",
        input_refs=["evidence:sidt-synthetic-trajectory"],
        input_payload={
            "states": states.tolist(), "inputs": inputs.tolist(),
            "outputs": None if outputs is None else outputs.tolist(),
            "metadata": asdict(metadata),
            "relative_rank_cutoff": diagnostic.relative_rank_cutoff,
        },
        numerical_result=numerical_result,
        components=components,
        covariance={
            "status": "unknown", "matrix": None,
            "variables": [component["name"] for component in components],
            "units": [component["unit"] for component in components],
            "frame": {"id": "sidt:ordered-model-coefficients", "semantics": "arbitrary_model_space"},
            "method": "parameter covariance is not estimated by this operation",
            "source_refs": [], "calibration_refs": [],
        },
        applicability="Synthetic fully observed discrete LTI candidate; no admission or adoption implied.",
    )


def main():
    states, inputs = trajectory(100, 20)
    candidate = fit_lti(states, inputs, sample_interval=0.1,
                        state_names=("position", "velocity"), state_units=("m", "m/s"),
                        input_names=("force",), input_units=("N",))
    print(json.dumps(export_candidate(candidate, states, inputs), indent=2))


if __name__ == "__main__":
    main()
