"""Independent, bounded STEP inspection for one declared IFC length quantity.

This scanner does not import CSE or certify IFC. It verifies the source links
needed by the IFC quantity adapter and refuses ambiguous/unsupported cases.
"""
from __future__ import annotations

from collections import Counter
import math
import re

TOKEN = re.compile(r"\s+|/\*.*?\*/|'(?:[^']|'')*'|END-ISO-10303-21|ISO-10303-21|#[0-9]+|\.[A-Za-z_][A-Za-z_0-9]*\.|[A-Za-z_][A-Za-z_0-9]*|[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?|[(),;=$*]", re.S | re.I)
CLASSES = {"IFCBUILDINGSTOREY": "IfcBuildingStorey", "IFCWALL": "IfcWall",
           "IFCWALLSTANDARDCASE": "IfcWall", "IFCSPACE": "IfcSpace",
           "IFCOPENINGELEMENT": "IfcOpeningElement", "IFCDOOR": "IfcDoor"}
DEFAULT_SIGMA = {("IfcBuildingStorey", "ClearHeight"): .01, ("IfcWall", "Length"): .005,
                 ("IfcWall", "Width"): .002, ("IfcOpeningElement", "Width"): .005,
                 ("IfcOpeningElement", "Height"): .005, ("IfcDoor", "Width"): .003,
                 ("IfcDoor", "Height"): .003, ("IfcSpace", "Length"): .005,
                 ("IfcSpace", "Width"): .005}
PREFIXES = {"EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6,
            "KILO": 1e3, "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2,
            "MILLI": 1e-3, "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12,
            "FEMTO": 1e-15, "ATTO": 1e-18}


def _parse(raw: bytes) -> tuple[str, dict[int, tuple[str, list]]]:
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise ValueError("IFC verification input exceeds the 64 KiB profile")
    source = raw.decode("utf-8")
    tokens, offset = [], 0
    for token in TOKEN.finditer(source):
        if token.start() != offset:
            raise ValueError("Unsupported STEP token in bounded verifier")
        offset = token.end()
        value = token.group()
        if not value.isspace() and not value.startswith("/*"):
            tokens.append(value)
        if len(tokens) > 20000:
            raise ValueError("STEP verification token budget exceeded")
    if offset != len(source):
        raise ValueError("Unsupported trailing STEP token in bounded verifier")
    cursor = 0

    def take(expected=None):
        nonlocal cursor
        if cursor >= len(tokens):
            raise ValueError("Truncated STEP DATA section")
        value = tokens[cursor]
        cursor += 1
        if expected is not None and value.upper() != expected:
            raise ValueError("Unexpected STEP structural token")
        return value

    def peek():
        if cursor >= len(tokens):
            raise ValueError("Truncated STEP exchange")
        return tokens[cursor]

    def value(depth=0):
        if depth > 24:
            raise ValueError("STEP verification nesting budget exceeded")
        token = take()
        if token == "(":
            out = []
            if peek() != ")":
                while True:
                    out.append(value(depth + 1))
                    if peek() != ",":
                        break
                    take(",")
            take(")")
            return out
        if token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if token.startswith("#"):
            return {"ref": int(token[1:])}
        if token == "$":
            return None
        if token == "*":
            return {"omitted": True}
        if token.startswith(".") and token.endswith("."):
            return {"enum": token[1:-1].upper()}
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", token):
            args = value(depth + 1)
            if type(args) is not list:
                raise ValueError("STEP typed value requires an argument list")
            return {"typed": token.upper(), "args": args}
        result = float(token)
        if not math.isfinite(result) or abs(result) > 1e150:
            raise ValueError("Nonfinite or oversized STEP scalar")
        return result

    take("ISO-10303-21")
    take(";")
    take("HEADER")
    take(";")
    header = {}
    while peek().upper() != "ENDSEC":
        field = take().upper()
        if not re.fullmatch(r"[A-Z_][A-Z_0-9]*", field) or field in header:
            raise ValueError("Invalid or duplicated STEP header field")
        args = value()
        take(";")
        if type(args) is not list:
            raise ValueError("STEP header field requires an argument list")
        header[field] = args
    take("ENDSEC")
    take(";")
    schemas = header.get("FILE_SCHEMA")
    if (type(schemas) is not list or len(schemas) != 1 or type(schemas[0]) is not list
            or len(schemas[0]) != 1 or type(schemas[0][0]) is not str or not schemas[0][0]):
        raise ValueError("Require one explicit STEP FILE_SCHEMA label")
    schema = schemas[0][0].upper()
    take("DATA")
    take(";")
    records = {}
    while peek().upper() != "ENDSEC":
        identifier = take()
        if not re.fullmatch(r"#[0-9]+", identifier):
            raise ValueError("Require simple STEP instance assignment")
        sid = int(identifier[1:])
        take("=")
        kind = take().upper()
        if not re.fullmatch(r"[A-Z_][A-Z_0-9]*", kind):
            raise ValueError("Require a STEP entity type")
        args = value()
        take(";")
        if sid in records or type(args) is not list or len(records) >= 256:
            raise ValueError("Duplicate STEP ID or exceeded 256 instance profile")
        records[sid] = kind, args
    take("ENDSEC")
    take(";")
    take("END-ISO-10303-21")
    take(";")
    if cursor != len(tokens):
        raise ValueError("Unexpected data following STEP exchange closure")
    return schema, records


def scan(raw: bytes) -> dict[int, tuple[str, list]]:
    return _parse(raw)[1]


def _ref(value):
    if type(value) is not dict or set(value) != {"ref"}:
        raise ValueError("Expected STEP reference")
    return value["ref"]


def _num(value):
    if type(value) is dict and set(value) == {"typed", "args"} and len(value["args"]) == 1:
        return _num(value["args"][0])
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Expected numeric STEP quantity")
    return float(value)


def _inspect_source(raw: bytes, target: dict) -> dict:
    schema, records = _parse(raw)
    if schema != "IFC4":
        raise ValueError("Source FILE_SCHEMA is outside the bounded IFC4 profile")
    if (type(target) is not dict or set(target) != {"ifc_class", "global_id", "quantity"}
            or any(type(item) is not str or not item for item in target.values())
            or (target["ifc_class"], target["quantity"]) not in DEFAULT_SIGMA):
        raise ValueError("Target is outside the bounded explicit length profile")
    minimum_fields = {"IFCPROJECT": 9, "IFCUNITASSIGNMENT": 1, "IFCSIUNIT": 4,
                      "IFCCONVERSIONBASEDUNIT": 3, "IFCRELDEFINESBYPROPERTIES": 6,
                      "IFCELEMENTQUANTITY": 6, "IFCPROPERTYSET": 5,
                      "IFCPROPERTYSINGLEVALUE": 4, "IFCQUANTITYLENGTH": 4,
                      "IFCQUANTITYAREA": 4, "IFCQUANTITYVOLUME": 4}
    if any(len(fields) < minimum_fields[name] for name, fields in records.values()
           if name in minimum_fields):
        raise ValueError("Truncated source entity in bounded length profile")
    inventory = []
    product_ids = set()
    for _, (kind, fields) in sorted(records.items()):
        if kind not in CLASSES:
            continue
        if not fields or type(fields[0]) is not str or not fields[0] or fields[0] in product_ids:
            raise ValueError("Supported source product GlobalId is missing or duplicated")
        product_ids.add(fields[0])
        for canonical_class, quantity in sorted(DEFAULT_SIGMA):
            if canonical_class == CLASSES[kind]:
                inventory.append({"ifc_class": canonical_class, "global_id": fields[0], "quantity": quantity})
    inventory.sort(key=lambda item: (item["ifc_class"], item["global_id"], item["quantity"]))
    products = [(sid, kind, args) for sid, (kind, args) in records.items()
                if kind in CLASSES and args and CLASSES[kind] == target["ifc_class"]
                and args[0] == target["global_id"]]
    # A duplicate GlobalId across product classes is ambiguous as well.
    same_id = [sid for sid, (kind, args) in records.items()
               if kind in CLASSES and args and args[0] == target["global_id"]]
    if len(products) != 1 or len(same_id) != 1:
        raise ValueError("Declared source object is absent, duplicated or outside the verifier profile")
    sid, kind, args = products[0]
    assignments = []
    assignment_declared = False
    for _, (name, fields) in records.items():
        if name == "IFCPROJECT" and len(fields) > 8 and fields[8] is not None:
            assignment_declared = True
            assignment_kind, assignment = records[_ref(fields[8])]
            if assignment_kind != "IFCUNITASSIGNMENT":
                raise ValueError("Project length units must use IfcUnitAssignment")
            assignments.extend(_ref(ref) for ref in assignment[0])
    if not assignment_declared:
        raise ValueError("Bounded profile requires an explicit project unit assignment")
    unit_rows = []
    for uid, (name, fields) in records.items():
        if assignment_declared and uid not in assignments:
            continue
        if name in {"IFCSIUNIT", "IFCCONVERSIONBASEDUNIT"} and fields[1] == {"enum": "LENGTHUNIT"}:
            if name != "IFCSIUNIT" or fields[3] != {"enum": "METRE"}:
                raise ValueError("Bounded verifier accepts explicit SI metre length units")
            prefix = fields[2]["enum"] if fields[2] is not None else None
            if prefix is not None and prefix not in PREFIXES:
                raise ValueError("Unknown SI length prefix")
            unit_rows.append((uid, prefix, PREFIXES[prefix] if prefix else 1.0))
    if not unit_rows or len({row[2] for row in unit_rows}) != 1:
        raise ValueError("Source length units are missing or ambiguous")
    unit_rows.sort()
    uid, prefix, scale = unit_rows[0]
    definitions = []
    for _, (name, fields) in records.items():
        if name == "IFCRELDEFINESBYPROPERTIES" and any(_ref(ref) == sid for ref in fields[4]):
            definitions.append(_ref(fields[5]))
    quantities, overrides = [], {}
    for did in definitions:
        name, fields = records[did]
        if name == "IFCELEMENTQUANTITY":
            for reference in fields[5]:
                qid = _ref(reference)
                qname, qfields = records[qid]
                if qname in {"IFCQUANTITYAREA", "IFCQUANTITYVOLUME"} and qfields[0] == target["quantity"]:
                    raise ValueError("Source target quantity type is outside the explicit length profile")
                if qname == "IFCQUANTITYLENGTH" and qfields[0] == target["quantity"]:
                    if qfields[2] is not None:
                        raise ValueError("Per-quantity unit override is outside the bounded verifier profile")
                    quantities.append((qid, _num(qfields[3])))
        if name == "IFCPROPERTYSET" and fields[2] in {"GAT_Uncertainty", "GAT_Posterior"}:
            for reference in fields[4]:
                pname, pfields = records[_ref(reference)]
                if pname == "IFCPROPERTYSINGLEVALUE" and pfields[0] == target["quantity"] + "Sigma":
                    if len(pfields) != 4 or pfields[3] is not None:
                        raise ValueError("Per-property sigma unit override is outside the bounded verifier profile")
                    if pfields[0] in overrides:
                        raise ValueError("Ambiguous source prior sigma override")
                    overrides[pfields[0]] = _num(pfields[2]) * scale
    if len(quantities) > 1:
        raise ValueError("Ambiguous source target quantity")
    sigma = overrides.get(target["quantity"] + "Sigma", DEFAULT_SIGMA.get((target["ifc_class"], target["quantity"])))
    if sigma is None or sigma <= 0:
        raise ValueError("No supported positive prior sigma policy for declared source target")
    qid, nominal = quantities[0] if quantities else (None, None)
    length_units = [{"step_id": row_id, "kind": "SI", "name": "METRE", "prefix": row_prefix,
                     "scale_to_metres": row_scale, "normalization_required": row_scale != 1.0,
                     "accepted_by_current_adapter": True} for row_id, row_prefix, row_scale in unit_rows]
    return {"source_schema": schema, "length_units": length_units,
            "raw_quantity_inventory": inventory,
            "instance_count": len(records), "type_counts": dict(sorted(Counter(kind for kind, _ in records.values()).items())),
            "source_step_id": sid, "source_ifc_type": kind, "target": dict(target),
            "quantity_step_id": qid, "quantity_present": bool(quantities),
            "nominal_metres": None if nominal is None else nominal * scale,
            "prior_sigma_metres": sigma,
            "unit_context": {"scale_to_metres": scale, "kind": "SI", "name": "METRE",
                             "prefix": prefix, "source_step_id": uid, "assumed": False}}


def inspect_source(raw: bytes, target: dict) -> dict:
    try:
        return _inspect_source(raw, target)
    except (KeyError, IndexError, TypeError, AttributeError, OverflowError, UnicodeError) as error:
        raise ValueError("Malformed source links or values in bounded IFC verifier") from error
