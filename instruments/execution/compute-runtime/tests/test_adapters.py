"""Phase 10: the external-data adapter boundary (adapters/interface.py).

Demonstrates the whole chain -- External Data -> Adapter.normalize() ->
CandidateDelta -> validate_candidate() -> Version | ValidationError[] --
using a minimal mock adapter (a dict-of-scalars normalizer), since no
real adapter is implemented per this session's "do not overbuild"
instruction. Also verifies the dependency-direction rule: adapters/ is
optional, upstream-only tooling -- nothing in core/, morpho/, backends/,
or runtime/ may depend on it.
"""

import ast as pyast
from pathlib import Path
from typing import Tuple

from adapters.interface import Adapter, ExternalRecord, build_candidate_delta
from core.canonical.delta import CandidateChange
from core.canonical.validation import ValidationError, validate_candidate
from core.canonical.version import ProvenanceInfo

REPO_ROOT = Path(__file__).resolve().parent.parent


class _DictScalarAdapter:
    """Minimal mock: treats `record.raw` as {field_id: new_value} and
    emits one replace-Change per key. This is a TEST FIXTURE, not a real
    adapter -- it exists only to exercise the Adapter Protocol shape."""

    def normalize(self, record: ExternalRecord) -> Tuple[CandidateChange, ...]:
        provenance = ProvenanceInfo(author="adapter", transaction_id="tx-adapter", source=f"adapter:{record.source}")
        return tuple(
            CandidateChange(path=f"fields.{key}.value", operation="replace", old_value=None, new_value=value, provenance=provenance)
            for key, value in record.raw.items()
        )


def test_adapter_conforms_to_the_protocol_shape():
    adapter: Adapter = _DictScalarAdapter()
    record = ExternalRecord(raw={"mass": 77}, source="test_sensor")
    changes = adapter.normalize(record)
    assert len(changes) == 1
    assert changes[0].path == "fields.mass.value"
    assert changes[0].new_value == 77


def test_external_data_reaches_canonical_state_only_through_validate_candidate(sample_schema, genesis_version):
    adapter = _DictScalarAdapter()
    record = ExternalRecord(raw={"mass": 88}, source="test_sensor")
    candidate = build_candidate_delta(
        adapter, record, version_from=genesis_version.id, transaction_id="tx-adapter", timestamp="2026-08-22T00:04:00Z"
    )

    result = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert not isinstance(result, list), result
    assert result.state.fields["mass"].value == 88
    assert result.parent == genesis_version.id


def test_invalid_external_data_is_rejected_not_silently_applied(sample_schema, genesis_version):
    # sample_schema declares fields.mass with a min=0 constraint (see
    # conftest.py) -- an adapter proposing a negative mass must be
    # rejected exactly like an invalid simulation/neural candidate.
    adapter = _DictScalarAdapter()
    record = ExternalRecord(raw={"mass": -50}, source="test_sensor")
    candidate = build_candidate_delta(
        adapter, record, version_from=genesis_version.id, transaction_id="tx-adapter-bad", timestamp="2026-08-22T00:04:00Z"
    )

    result = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert isinstance(result, list)
    assert all(isinstance(e, ValidationError) for e in result)
    assert genesis_version.state.fields["mass"].value == 10  # untouched


def test_unknown_field_from_external_data_is_rejected(sample_schema, genesis_version):
    adapter = _DictScalarAdapter()
    record = ExternalRecord(raw={"totally_unknown_field": 1}, source="test_sensor")
    candidate = build_candidate_delta(
        adapter, record, version_from=genesis_version.id, transaction_id="tx-adapter-unknown", timestamp="2026-08-22T00:04:00Z"
    )

    result = validate_candidate(sample_schema, genesis_version.state, candidate)
    assert isinstance(result, list)
    assert any(e.code == "UNKNOWN_FIELD" for e in result)


def test_nothing_upstream_of_adapters_depends_on_it():
    """adapters/ is optional, upstream-only tooling -- symmetric to how
    core/, morpho/, and backends/ never depend on runtime/ (§2)."""

    def imports_in(path):
        tree = pyast.parse(path.read_text())
        modules = []
        for node in pyast.walk(tree):
            if isinstance(node, pyast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, pyast.ImportFrom) and node.module:
                modules.append(node.module)
        return modules

    for package in ("core", "morpho", "backends", "runtime", "renderer"):
        package_dir = REPO_ROOT / package
        if not package_dir.exists():
            continue
        for path in package_dir.rglob("*.py"):
            if "test_" in path.name:
                continue
            for module in imports_in(path):
                assert not module.startswith("adapters"), (
                    f"{path.relative_to(REPO_ROOT)} imports {module!r} (adapters/ must remain upstream-only)"
                )
