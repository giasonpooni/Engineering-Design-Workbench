"""Explicit proof obligations and exact-byte composition plans, NOT verifiers.

These records state what must be proved. Hashes, graph validity, and a known guest
hash never establish that a proof exists or is valid. Admission remains external.
"""
from __future__ import annotations
from copy import deepcopy
import re
from .declared_workload import _commit
from .telemetry import digest

CONVENTION = "ste.sp1.kernel-io.v1"
FIELDS = {"schema", "predicate", "specification", "expected_output", "exit_code", "public_values_convention",
          "guest_sha256", "program_identity", "input_identity", "output_identity", "specification_identity",
          "status", "disclosure", "unproved_context", "obligation_id"}


def _hex(value, maximum, *, empty=False):
    if not isinstance(value,str) or len(value)>2*maximum or len(value)%2 or (not value and not empty):
        raise ValueError("Invalid bounded byte encoding")
    if not re.fullmatch(r"[0-9a-f]*",value): raise ValueError("Require canonical lowercase hexadecimal")
    return bytes.fromhex(value)


def obligation(predicate: str, program: bytes, inputs: bytes, output: bytes,
               *, guest_sha256: str | None = None, unproved_context: dict | None = None) -> dict:
    """Prepare a successful-execution obligation with empty native configuration.

    Any mathematical settings must be consumed by the guest or identified by its
    fixed program. Arbitrary host policy is only unproved_context, never a proof.
    """
    if not isinstance(predicate,str) or not 1<=len(predicate)<=128 or not predicate.strip():
        raise ValueError("Require a bounded predicate identity")
    if any(type(x) is not bytes for x in (program,inputs,output)):
        raise ValueError("Obligation fields require exact bytes")
    if not 1<=len(program)<=8192 or not 1<=len(inputs)<=1024**2 or not 1<=len(output)<=1024**2:
        raise ValueError("Obligation byte bounds exceeded")
    if guest_sha256 is not None and (not isinstance(guest_sha256,str) or not re.fullmatch(r"sha256:[0-9a-f]{64}",guest_sha256)):
        raise ValueError("Require an exact expected guest SHA-256 or explicit pending registration")
    context={} if unproved_context is None else deepcopy(unproved_context)
    if not isinstance(context,dict) or len(str(context))>32768: raise ValueError("Invalid unproved context")
    value={"schema":"ciw.proof-obligation.v1", "predicate":predicate,
           "specification":{"program":program.hex(),"configuration":"","input_payload":inputs.hex()},
           "expected_output":output.hex(), "exit_code":0,"public_values_convention":CONVENTION,
           "guest_sha256":guest_sha256,"program_identity":_commit("program",[program]),
           "input_identity":_commit("input",[inputs]),"output_identity":_commit("output",[output]),
           "specification_identity":_commit("specification",[program,b"",inputs]),
           "status":"obligation_only_not_verified", "disclosure":"input_output_public",
           "unproved_context":context}
    value["obligation_id"]=digest(value)
    return value


def validate_obligation(value: dict) -> dict:
    value=deepcopy(value)
    if not isinstance(value,dict) or value.keys()!=FIELDS: raise ValueError("Invalid proof obligation fields")
    spec=value["specification"]
    if not isinstance(spec,dict) or spec.keys()!={"program","configuration","input_payload"} or spec["configuration"]!="":
        raise ValueError("This public-values convention does not separately prove arbitrary native configuration")
    expected=obligation(value["predicate"],_hex(spec["program"],8192),_hex(spec["input_payload"],1024**2),
                        _hex(value["expected_output"],1024**2),guest_sha256=value["guest_sha256"],
                        unproved_context=value["unproved_context"])
    # Canonical equality catches bool/int confusions as well as forged labels.
    if digest(value)!=digest(expected): raise ValueError("Proof obligation commitment or scope mismatch")
    return value


def compose_exact(nodes: list, edges: list, roots: list) -> dict:
    """Check a declared DAG's identity-byte handoffs, without authenticating proofs.

    Nodes are {node_id, obligation}; edges are {source,target,mapping}. The listed
    order is a topological order; roots must be exactly the externally supplied
    inputs. Nonidentity encodings need an explicit, separately checked operation.
    """
    nodes,edges,roots=deepcopy((nodes,edges,roots))
    if not isinstance(nodes,list) or not 1<=len(nodes)<=64 or not isinstance(edges,list) or len(edges)>128:
        raise ValueError("Composition budget exceeded")
    indices={}; records={}
    for i,node in enumerate(nodes):
        if not isinstance(node,dict) or node.keys()!={"node_id","obligation"}: raise ValueError("Invalid node")
        name=node["node_id"]
        if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",name) or name in indices:
            raise ValueError("Invalid or duplicate node identity")
        indices[name]=i;records[name]=validate_obligation(node["obligation"])
    seen=set();targets=set()
    for edge in edges:
        if not isinstance(edge,dict) or edge.keys()!={"source","target","mapping"}: raise ValueError("Invalid dependency edge")
        a,b=edge["source"],edge["target"]
        if not isinstance(a,str) or not isinstance(b,str) or a not in indices or b not in indices:
            raise ValueError("Missing dependency node")
        if edge["mapping"]!="identity-bytes.v1": raise ValueError("A nonidentity map needs its own checked operation")
        if (a,b) in seen or b in targets: raise ValueError("Duplicate or ambiguous whole-input dependency")
        if indices[a]>=indices[b]: raise ValueError("Cyclic, self-referential or misordered dependency")
        if records[a]["expected_output"]!=records[b]["specification"]["input_payload"]:
            raise ValueError("Output/input bytes do not compose")
        seen.add((a,b));targets.add(b)
    if not isinstance(roots,list) or any(not isinstance(r,str) for r in roots) or len(set(roots))!=len(roots):
        raise ValueError("Invalid or duplicate root list")
    if set(roots)!=set(indices)-targets: raise ValueError("Every unbound input must be an explicit root")
    result={"schema":"ciw.proof-composition-plan.v1","nodes":nodes,"edges":edges,"roots":roots,
            "status":"plan_only_not_verified","cryptographic_verification":"not_performed",
            "recursive_aggregation":"not_performed","state_admission":"not_performed",
            "unbound_guest_nodes":[name for name,value in records.items() if value["guest_sha256"] is None]}
    result["plan_id"]=digest(result)
    return result
