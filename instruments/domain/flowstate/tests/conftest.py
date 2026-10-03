"""Mark experiment/report modules as extended so the unit gate stays short."""

from __future__ import annotations

import pytest

EXTENDED_MODULES = {
    "test_calibration_sweep.py",
    "test_camera_experiment.py",
    "test_cooling_circuits.py",
    "test_eiv_projection.py",
    "test_errors_in_variables.py",
    "test_experiments.py",
    "test_fluid_baseline.py",
    "test_invariant_experiment.py",
    "test_muskingum_reach.py",
    "test_real_diagnosis.py",
    "test_real_fluid_baseline.py",
    "test_real_noaa.py",
    "test_real_noaa_month.py",
    "test_results_reproduce.py",
    "test_second_balance.py",
    "test_taylor_park.py",
    "test_water_balance.py",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    marker = pytest.mark.extended
    for item in items:
        path = getattr(item, "path", None)
        name = path.name if path is not None else item.nodeid.split("::", 1)[0].rsplit("/", 1)[-1]
        if name in EXTENDED_MODULES:
            item.add_marker(marker)
