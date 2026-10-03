"""§21 tests 1-3: projection preserves fields, leaves canonical state
untouched, and produces deterministic Morpho IR."""

from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho


def test_all_canonical_fields_survive_projection(genesis_version):
    projected = project_state(genesis_version)
    assert set(projected.fields.keys()) == set(genesis_version.state.fields.keys())
    for key, field in genesis_version.state.fields.items():
        assert projected.fields[key] == field


def test_canonical_state_remains_unchanged_by_projection(genesis_version):
    # CanonicalState/Field are immutable (frozen dataclasses over a
    # MappingProxyType), so a plain snapshot of the field/edge contents
    # is as strong a mutation check as a deep copy would be -- and
    # avoids relying on `copy.deepcopy`, which does not support
    # MappingProxyType in this Python version.
    fields_before = dict(genesis_version.state.fields)
    edges_before = genesis_version.state.edges

    project_state(genesis_version)

    assert genesis_version.state.fields == fields_before
    assert genesis_version.state.edges == edges_before


def test_same_version_produces_identical_morpho_ir(genesis_version):
    # projection_is_deterministic (I6/I7): the same Version always
    # projects to the same IR.
    config = CompilerConfig()
    doc1 = compile_morpho(project_state(genesis_version), config)
    doc2 = compile_morpho(project_state(genesis_version), config)
    assert doc1 == doc2
