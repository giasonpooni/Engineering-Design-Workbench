"""Schematics Retrieval Agent.

Canonical object: function graph + factor graph.
USD and mermaid are projections. Companion kernels own A, V, samples, dispositions.
"""

from .agent import AgentReport, run
from .eligibility import Decision, decide, eligible
from .fixtures import quadratic_drag
from .ir import Edge, EdgeKind, Node, NodeKind, Schematic, Status
from .retrieve import blanket, by_attr, by_id, by_kind, path
from .validate import SchematicError, require, validate

__all__ = [
    "AgentReport", "Decision", "Edge", "EdgeKind", "Node", "NodeKind",
    "Schematic", "SchematicError", "Status", "blanket", "by_attr", "by_id",
    "by_kind", "decide", "eligible", "path", "quadratic_drag", "require", "run", "validate",
]
