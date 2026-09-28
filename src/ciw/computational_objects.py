"""First-class computational-object selection and bounded agent context packages.

This module describes existing computation. It never imports or executes a provider,
rewrites source, or promotes a retained result to verified evidence.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Any

SCHEMA = "ciw.computational-object.v1"
SELECTION_SCHEMA = "ciw.computational-selection.v1"
CONTEXT_SCHEMA = "ciw.context-package.v1"
PERTURBATION_SCHEMA = "ciw.perturbation-request.v1"
COMPARISON_SCHEMA = "ciw.computational-comparison.v1"

_KINDS = frozenset({"function","module","type","trait","ecs-system","shader","numerical-kernel",
                    "solver","state-transition","coordinate-transform","graph-substructure",
                    "dataflow","experiment","proof-obligation"})
_VIEWS = frozenset({"source","state","algebra","graph","geometry","topology","composition",
                    "evidence","experiments"})
_PERTURB = frozenset({"input","parameter","implementation","precision","solver","backend","representation"})
_COMPARE = frozenset({"output","residual","covariance","invariant","topology","performance","provenance"})
_ID = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*\.v[1-9][0-9]*\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= value.keys() <= required | optional:
        raise ValueError("Unexpected or missing computational-object fields")


def _text(value: Any, name: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a nonempty bounded string")
    return value


def _string_list(value: Any, name: str, *, allowed=None, maximum: int = 64) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{name} must be a bounded string list")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")
    if allowed is not None and any(x not in allowed for x in value):
        raise ValueError(f"{name} contains an unsupported value")
    return value


def validate_object(value: Any) -> dict:
    required={"schema","object_id","kind","label","operation_id","source","mathematics","relations",
              "invariants","evidence","experiments","authority"}
    _keys(value, required)
    if value["schema"] != SCHEMA or not _ID.fullmatch(str(value["object_id"])):
        raise ValueError("Unsupported computational object identity")
    if value["kind"] not in _KINDS:
        raise ValueError("Unsupported computational object kind")
    _text(value["label"], "label")
    if value["operation_id"] is not None and not _ID.fullmatch(str(value["operation_id"])):
        raise ValueError("operation_id must be null or a versioned operation identity")
    _keys(value["source"], {"repository","revision","path","span","language","sha256"})
    for key in ("repository","revision","path","language"): _text(value["source"][key], "source."+key)
    if not _SHA.fullmatch(str(value["source"]["sha256"])):
        raise ValueError("source.sha256 must bind exact source content")
    span=value["source"]["span"]
    if (not isinstance(span,list) or len(span)!=2 or any(type(x) is not int for x in span)
            or span[0] < 1 or span[1] < span[0]):
        raise ValueError("source.span must be inclusive positive line bounds")
    _keys(value["mathematics"], {"domain","codomain","expression","units","assumptions"})
    for key in ("domain","codomain","expression"): _text(value["mathematics"][key], "mathematics."+key, 4096)
    if not isinstance(value["mathematics"]["units"], dict):
        raise ValueError("mathematics.units must be an object")
    _string_list(value["mathematics"]["assumptions"], "assumptions")
    _keys(value["relations"], {"dependencies","consumers","equivalent_implementations","compositions"})
    for key in value["relations"]: _string_list(value["relations"][key], "relations."+key)
    _string_list(value["invariants"], "invariants")
    _string_list(value["evidence"], "evidence")
    _string_list(value["experiments"], "experiments")
    _keys(value["authority"], {"describes","may_execute","may_edit","may_verify","may_admit_state"})
    if value["authority"] != {"describes":True,"may_execute":False,"may_edit":False,
                              "may_verify":False,"may_admit_state":False}:
        raise ValueError("Computational-object records are descriptive only")
    _canonical(value)
    return deepcopy(value)


def make_object(*, object_id: str, kind: str, label: str, operation_id: str|None, source: dict,
                mathematics: dict, relations: dict|None=None, invariants: list[str]|None=None,
                evidence: list[str]|None=None, experiments: list[str]|None=None) -> dict:
    value={"schema":SCHEMA,"object_id":object_id,"kind":kind,"label":label,"operation_id":operation_id,
           "source":deepcopy(source),"mathematics":deepcopy(mathematics),
           "relations":deepcopy(relations or {"dependencies":[],"consumers":[],"equivalent_implementations":[],"compositions":[]}),
           "invariants":list(invariants or []),"evidence":list(evidence or []),"experiments":list(experiments or []),
           "authority":{"describes":True,"may_execute":False,"may_edit":False,"may_verify":False,"may_admit_state":False}}
    return validate_object(value)


def select(obj: dict, *, views: list[str]|None=None, edit_paths: list[str]|None=None) -> dict:
    obj=validate_object(obj)
    views=_string_list(views or ["source","algebra","evidence"], "views", allowed=_VIEWS, maximum=len(_VIEWS))
    edit_paths=_string_list(edit_paths or [], "edit_paths")
    if any(p != obj["source"]["path"] for p in edit_paths):
        raise ValueError("v1 edit envelope may name only the selected object's bound source path")
    body={"schema":SELECTION_SCHEMA,"object_id":obj["object_id"],"object_digest":_digest(obj),
          "views":views,"edit_envelope":{"paths":edit_paths,"requires_human_or_executor_authorization":True},
          "authority":{"may_execute":False,"may_edit":False,"may_verify":False,"may_admit_state":False}}
    body["selection_id"]="selection:"+_digest(body)
    return body


def context_package(obj: dict, selection: dict) -> dict:
    obj=validate_object(obj)
    _keys(selection, {"schema","selection_id","object_id","object_digest","views","edit_envelope","authority"})
    if (selection["schema"] != SELECTION_SCHEMA or selection["object_id"] != obj["object_id"]
            or selection["object_digest"] != _digest(obj)):
        raise ValueError("Selection is stale or bound to another computational object")
    _string_list(selection["views"], "views", allowed=_VIEWS, maximum=len(_VIEWS))
    package={"schema":CONTEXT_SCHEMA,"selection":deepcopy(selection),"object":obj,
             "direct_context":{"dependencies":obj["relations"]["dependencies"],
                               "consumers":obj["relations"]["consumers"],
                               "evidence":obj["evidence"],"experiments":obj["experiments"],
                               "invariants":obj["invariants"]},
             "instructions":{"preserve_invariants":True,"stay_within_edit_envelope":True,
                             "execution_requires_separate_authority":True,
                             "verification_requires_separate_identity":True}}
    package["context_digest"]=_digest(package)
    return package


def perturbation_request(obj: dict, *, dimension: str, change: dict) -> dict:
    obj=validate_object(obj)
    if dimension not in _PERTURB or not isinstance(change,dict) or not change:
        raise ValueError("Perturbation needs a supported dimension and nonempty declared change")
    _canonical(change)
    body={"schema":PERTURBATION_SCHEMA,"object_id":obj["object_id"],"object_digest":_digest(obj),
          "dimension":dimension,"change":deepcopy(change),"execute":False,
          "required_observations":["result","invariants","residuals","provenance"]}
    body["request_id"]="perturbation:"+_digest(body)
    return body


def compare_observations(obj: dict, left: dict, right: dict, *, metrics: list[str]) -> dict:
    obj=validate_object(obj)
    metrics=_string_list(metrics,"metrics",allowed=_COMPARE,maximum=len(_COMPARE))
    if not isinstance(left,dict) or not isinstance(right,dict):
        raise ValueError("Comparison observations must be objects")
    def finite_numbers(value):
        if isinstance(value,bool): return []
        if isinstance(value,(int,float)):
            if not math.isfinite(value): raise ValueError("Nonfinite comparison value")
            return [float(value)]
        if isinstance(value,list):
            out=[]
            for x in value: out.extend(finite_numbers(x))
            return out
        if isinstance(value,dict):
            out=[]
            for k in sorted(value): out.extend(finite_numbers(value[k]))
            return out
        return []
    a,b=finite_numbers(left),finite_numbers(right)
    numerical=None
    if a and len(a)==len(b):
        diffs=[abs(x-y) for x,y in zip(a,b)]
        numerical={"count":len(diffs),"max_abs":max(diffs),"l2":math.sqrt(sum(x*x for x in diffs))}
    result={"schema":COMPARISON_SCHEMA,"object_id":obj["object_id"],"object_digest":_digest(obj),
            "metrics":metrics,"left_digest":_digest(left),"right_digest":_digest(right),
            "numerical_summary":numerical,"invariants_assessed":False,"verification_status":"not_verified"}
    result["comparison_digest"]=_digest(result)
    return result
