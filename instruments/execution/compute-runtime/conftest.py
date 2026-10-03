"""Shared pytest fixtures for the whole repository (§21 test plan)."""

import pytest

from core.canonical.schema import FieldConstraints, FieldSchema, StateSchema
from core.canonical.version import create_genesis_version

SAMPLE_SCHEMA = StateSchema(
    schema_version="1.0.0",
    fields={
        "mass": FieldSchema(id="mass", type="scalar", unit="kg", default=10, constraints=FieldConstraints(min=0)),
        "temperature": FieldSchema(id="temperature", type="scalar", unit="K", default=293.15),
        "pressure": FieldSchema(id="pressure", type="scalar", unit="Pa", default=101325),
        "velocity": FieldSchema(id="velocity", type="scalar", unit="m/s", default=0),
        "energy": FieldSchema(id="energy", type="scalar", unit="J", default=0),
        "volume": FieldSchema(id="volume", type="scalar", unit="m^3", default=1.0),
        "density": FieldSchema(id="density", type="scalar", unit="kg/m^3", default=1.0),
        "charge": FieldSchema(id="charge", type="scalar", unit="C", default=0),
        "frequency": FieldSchema(id="frequency", type="scalar", unit="Hz", default=1),
        "luminosity": FieldSchema(id="luminosity", type="scalar", unit="cd", default=0),
    },
)


@pytest.fixture
def sample_schema() -> StateSchema:
    return SAMPLE_SCHEMA


@pytest.fixture
def genesis_version():
    return create_genesis_version(SAMPLE_SCHEMA, "2026-08-22T00:00:00Z")
