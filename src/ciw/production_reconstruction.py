"""Agent data proposals -> original NET production -> game-owned reconstruction checks.

This module never edits the game checkout or dispatches an agent/model/process.
An operator supplies the work packet; an external worker supplies only data.
The one executable attachment is the independently pinned 1792 validator.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from typing import Callable
import uuid

SOURCE_PATH = "game/data/gujranwala_reconstruction.v1.json"
VALIDATOR_PATH = "tools/check_reconstruction.py"
GAME_REVISION = "5b19fda41a50516bc595c32a5455c07016b90212"
VALIDATOR_SHA256 = "sha256:180a3c867a0dbfd3c72a9fc0adf0711e487bae1a59cd923cb99ce2681e507568"
PACKET = "ciw.reconstruction-work-packet.v1"
PROPOSAL = "ciw.reconstruction-proposal.v1"
CANDIDATE = "ciw.reconstruction-candidate.v1"
BATCH = "ciw.reconstruction-batch.v1"
OPERATION = "game.reconstruction-compose.v1"
GATE = "game.reconstruction-contract.v1"
MAX_BYTES = 65536
AUTHORITY = {"verification_id": None, "state_admission": "not_performed",
             "publication": "not_performed", "game_integration": "not_performed",
             "claim_scope": "bounded_reconstruction_candidate_only"}
_REGISTERED = False


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def fields(value: dict, names: set[str]) -> None:
    require(type(value) is dict and set(value) == names, "Unexpected or missing fields")


def name(value: str) -> str:
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value) is not None,
            "Require a bounded identifier, not a path or command")
    return value


def sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON member")
        result[key] = value
    return result


def _bounded(value, depth: int = 0) -> None:
    require(depth <= 16, "JSON nesting exceeds limit")
    if type(value) is dict:
        require(len(value) <= 128 and all(type(k) is str and len(k) <= 128 for k in value), "Object exceeds limit")
        for item in value.values():
            _bounded(item, depth + 1)
    elif type(value) is list:
        require(len(value) <= 128, "Array exceeds limit")
        for item in value:
            _bounded(item, depth + 1)
    elif type(value) is str:
        require(len(value.encode("utf-8")) <= MAX_BYTES, "String exceeds limit")
    elif type(value) in (int, float):
        require(abs(value) <= 1e12 and math.isfinite(value), "Unbounded or nonfinite number")
    else:
        require(value is None or type(value) is bool, "Not JSON data")


def encode(value) -> bytes:
    _bounded(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def parse(raw: bytes) -> dict:
    require(0 < len(raw) <= MAX_BYTES, "Input exceeds 64 KiB")
    def invalid(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid)
    _bounded(result)
    require(type(result) is dict, "Require a JSON object")
    return result


def read_regular(path: Path, limit: int = MAX_BYTES) -> bytes:
    path = Path(path).absolute()
    require(all(not p.is_symlink() for p in (path, *path.parents)), "Symlink paths are not supported")
    require(path.is_file(), "Require a regular file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "File exceeds byte budget")
    return raw


def load(path: Path) -> dict:
    return parse(read_regular(path))


def save_new(path: Path, value: dict) -> None:
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    parse(raw)
    require(all(not p.is_symlink() for p in (path, *path.parents)), "Symlink destination refused")
    with path.open("xb") as stream:
        stream.write(raw)


def require_external_destination(game_root: Path, destination: Path) -> None:
    game = Path(game_root).resolve(strict=True)
    target = Path(destination).resolve(strict=False)
    require(not target.is_relative_to(game), "Production output must be outside the game checkout")


def new_directory(path: Path) -> Path:
    path = Path(path).absolute()
    require(all(not p.is_symlink() for p in (path, *path.parents)), "Symlink destination refused")
    path.mkdir(parents=True, exist_ok=False)
    return path


def validate_packet(packet: dict) -> dict:
    fields(packet, {"schema", "task_id", "project_id", "source_path", "source_sha256", "baseline_utf8",
                    "validator_sha256", "allowed_fields", "max_edits", "authority", "packet_sha256"})
    require(packet["schema"] == PACKET and packet["project_id"] == "1792", "Wrong work-packet profile")
    name(packet["task_id"])
    require(packet["source_path"] == SOURCE_PATH and packet["validator_sha256"] == VALIDATOR_SHA256,
            "Unsupported source or validator profile")
    require(packet["authority"] == AUTHORITY, "Work packet cannot grant admission or release authority")
    require(type(packet["baseline_utf8"]) is str, "Baseline must be exact UTF-8 text")
    raw = packet["baseline_utf8"].encode("utf-8")
    require(len(raw) <= 32768 and sha(raw) == packet["source_sha256"], "Baseline content binding mismatch")
    baseline = parse(raw)
    require(baseline.get("schema") == "1792.gujranwala-reconstruction.v1", "Wrong game manifest")
    features = baseline.get("features")
    require(type(features) is list and 1 <= len(features) <= 64, "Require bounded game features")
    ids = [name(f["id"]) for f in features]
    require(len(ids) == len(set(ids)), "Duplicate baseline feature")
    allowed = packet["allowed_fields"]
    require(type(allowed) is dict and 1 <= len(allowed) <= 16 and set(allowed) <= set(ids), "Invalid feature allowlist")
    for feature_id, names in allowed.items():
        feature = next(f for f in features if f["id"] == feature_id)
        permitted = {"position", "size"} | ({"bays"} if feature.get("kind") == "arcade" else set())
        require(type(names) is list and 1 <= len(names) <= 3 and all(type(n) is str for n in names)
                and len(set(names)) == len(names) and set(names) <= permitted, "Forbidden editable field")
    require(type(packet["max_edits"]) is int and 1 <= packet["max_edits"] <= 16, "Invalid edit budget")
    unsigned = {k: v for k, v in packet.items() if k != "packet_sha256"}
    require(sha(encode(unsigned)) == packet["packet_sha256"], "Work packet digest mismatch")
    require(len(encode(packet)) <= MAX_BYTES, "Work packet exceeds size budget")
    return baseline


class GameValidator:
    """Explicit host binding to an audited game-owned Python checker, not a sandbox.

    Its code is not copied into NET and no packet can select executable code.
    A changed checker requires a reviewed profile revision, not a relaxed gate.
    """
    def __init__(self, game_root: Path):
        self.root = Path(game_root).absolute()
        self.path = self.root / VALIDATOR_PATH
        raw = read_regular(self.path)
        require(sha(raw) == VALIDATOR_SHA256, "Game validator differs from the audited profile")
        namespace = {"__name__": "net_bound_1792_reconstruction", "__file__": str(self.path)}
        exec(compile(raw, str(self.path), "exec"), namespace)
        self._validate = namespace["validate"]

    def runtime_identity(self) -> dict:
        require(sha(read_regular(self.path)) == VALIDATOR_SHA256, "Game validator changed after binding")
        return {"provider": "1792.reconstruction-checker", "validator_sha256": VALIDATOR_SHA256,
                "adapter_sha256": sha(Path(__file__).read_bytes()), "python": platform.python_version(),
                "scope": "game-owned pure checks; not gameplay, aesthetics or historical validation"}

    def check(self, candidate: dict) -> dict:
        self.runtime_identity()
        try:
            self._validate(deepcopy(candidate))
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            return {"status": "FAIL", "detail": str(exc)[:1024]}
        return {"status": "PASS", "detail": "game_owned_reconstruction_contract"}


def prepare(game_root: Path, task_id: str, allowed_fields: dict[str, list[str]], *, max_edits: int = 16) -> dict:
    validator = GameValidator(game_root)
    raw = read_regular(Path(game_root) / SOURCE_PATH, 32768)
    baseline = parse(raw)
    require(validator.check(baseline)["status"] == "PASS", "Baseline fails its own game validator")
    packet = {"schema": PACKET, "task_id": name(task_id), "project_id": "1792", "source_path": SOURCE_PATH,
              "source_sha256": sha(raw), "baseline_utf8": raw.decode("utf-8"), "validator_sha256": VALIDATOR_SHA256,
              "allowed_fields": deepcopy(allowed_fields), "max_edits": max_edits, "authority": deepcopy(AUTHORITY)}
    packet["packet_sha256"] = sha(encode(packet))
    validate_packet(packet)
    return packet


def proposal(packet: dict, worker_label: str, edits: list[dict]) -> dict:
    value = {"schema": PROPOSAL, "packet_sha256": packet["packet_sha256"],
             "worker_label": name(worker_label), "edits": deepcopy(edits)}
    compose(packet, value)
    return value


def compose(packet: dict, reply: dict) -> dict:
    baseline = validate_packet(packet)
    fields(reply, {"schema", "packet_sha256", "worker_label", "edits"})
    require(reply["schema"] == PROPOSAL and reply["packet_sha256"] == packet["packet_sha256"], "Stale or foreign proposal")
    name(reply["worker_label"])
    require(type(reply["edits"]) is list and 1 <= len(reply["edits"]) <= packet["max_edits"], "Invalid edit count")
    features = {f["id"]: f for f in baseline["features"]}
    seen = set()
    for edit in reply["edits"]:
        fields(edit, {"feature_id", "field", "value"})
        feature_id, field = name(edit["feature_id"]), name(edit["field"])
        require(field in packet["allowed_fields"].get(feature_id, []), "Edit outside operator allowlist")
        require((feature_id, field) not in seen, "Duplicate edit")
        seen.add((feature_id, field))
        value = edit["value"]
        if field == "bays":
            require(type(value) is int and 1 <= value <= 12, "Invalid bay count")
        else:
            require(type(value) is list and len(value) == 3 and
                    all(type(n) in (int, float) and abs(n) <= 500 and math.isfinite(n)
                        and (field != "size" or n > 0) for n in value), "Invalid feature vector")
        features[feature_id][field] = deepcopy(value)
    text = json.dumps(baseline, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    require(len(text.encode("utf-8")) <= 32768, "Candidate manifest exceeds byte budget")
    return {"schema": CANDIDATE, "packet_sha256": packet["packet_sha256"], "source_sha256": packet["source_sha256"],
            "proposal": deepcopy(reply), "candidate_utf8": text, "candidate_sha256": sha(text.encode("utf-8")),
            "authority": deepcopy(AUTHORITY)}


def request_proposal(packet: dict, worker: Callable[[dict], dict]) -> dict:
    """Host-selected agent callback; permission and provider budgets belong to its host.

    This adapter sends detached data and accepts data only. It does not sandbox a
    Python callable, authenticate a worker label, or attest remote model execution.
    """
    validate_packet(packet)
    reply = worker(deepcopy(packet))
    compose(packet, reply)
    return deepcopy(reply)


def _validate_payload(operation, data, run, parameters, selection):
    fields(parameters, {"proposal"})
    require(operation == OPERATION, "Wrong reconstruction operation")
    expected = compose(run["metadata"]["reconstruction_packet"], parameters["proposal"])
    require(encode(data) == encode(expected), "Candidate differs from its declared source and edits")


def register_schemas() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OPERATION, _validate_payload)
        _REGISTERED = True


def make_source(packet: dict) -> dict:
    from .adapters.protocol import InstrumentManifest
    from .core.identities import evidence_id
    validate_packet(packet)
    instrument = "org.notationsystems.reconstruction-work-packet"
    manifest = InstrumentManifest(instrument_id=instrument, version="1", role="operation_provider",
        inputs=(PACKET,), outputs=("run.v1",), units={"declaration": "1"}, frames=("reconstruction-work-declaration",),
        sampling={"mode": "declared_work"}, normalization={"state": "unchanged"}, supported_operations=(),
        determinism={"claim": "none_from_declaration"}, tolerance_policy={"policy": "game_owned_checker"},
        calibration_requirements={"status": "not_applicable_authored_content"})
    source = {"run_schema": "run.v1", "run_id": "run-" + uuid.uuid4().hex, "instrument": instrument,
        "time_s": [0.0], "channels": {"declaration": {"unit": "1", "kind": "declared_initial_condition", "values": [0.0]}},
        "render": {}, "metadata": {"sample_count": 1, "sample_rate_hz": None, "duration_s": 1.0,
        "coordinate_frame": "reconstruction-work-declaration", "manifest": manifest.to_dict(),
        "provenance": {"origin": "game_file_snapshot_not_play_observation", "duration_s_semantics": "selection support only"},
        "reconstruction_packet": deepcopy(packet)}}
    source["evidence_id"] = evidence_id(source)
    return source


def registry():
    from .adapters.protocol import InstrumentManifest
    from .control_plane import CapabilityRegistry
    from .operations.registry import Operation
    register_schemas()
    result = CapabilityRegistry()
    def runtime():
        return {"provider": "ciw.reconstruction-compose", "source_sha256": sha(Path(__file__).read_bytes()),
                "python": platform.python_version(), "execution_mode": "pure_data_transformation"}
    manifest = InstrumentManifest(instrument_id="org.notationsystems.reconstruction-compose", version="1", role="operation_provider",
        inputs=("run.v1",), outputs=("ciw.operation-result.v1",), units={}, frames=(),
        sampling={"mode": "explicit_work_order"}, normalization={"state": "candidate_only"}, supported_operations=(OPERATION,),
        determinism={"claim": "exact_typed_json"}, tolerance_policy={"policy": "independent_game_owned_gate"},
        calibration_requirements={"status": "not_applicable_authored_content"})
    result.advertise(manifest, runtime=runtime(), capabilities={OPERATION: ["game.reconstruction.compose"]})
    def invoke(run, parameters):
        fields(parameters, {"proposal"})
        return compose(run["metadata"]["reconstruction_packet"], parameters["proposal"])
    result.bind(Operation(OPERATION, "backend", invoke, runtime))
    return result


def gates(validator: GameValidator):
    from .production import Gate
    def policy(value):
        fields(value, {"packet_sha256"})
        require(type(value["packet_sha256"]) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value["packet_sha256"]), "Bad packet reference")
    def evaluate(result, value):
        if result is None:
            return {"status": "INDETERMINATE", "detail": "missing_candidate"}
        require(result["operation_id"] == OPERATION, "Wrong candidate operation")
        data = result["data"]
        require(data["packet_sha256"] == value["packet_sha256"] and data["authority"] == AUTHORITY, "Gate binding mismatch")
        raw = data["candidate_utf8"].encode("utf-8")
        require(sha(raw) == data["candidate_sha256"], "Candidate byte mismatch")
        return validator.check(parse(raw))
    return {GATE: Gate(GATE, validator.runtime_identity(), policy, evaluate)}


def make_plan(source: dict, batch: dict) -> dict:
    from .control_plane import experiment
    from .production import plan
    packet = source["metadata"]["reconstruction_packet"]
    validate_packet(packet)
    fields(batch, {"schema", "jobs"})
    require(batch["schema"] == BATCH and type(batch["jobs"]) is list and 1 <= len(batch["jobs"]) <= 64, "Invalid reconstruction batch")
    jobs = []
    for job in batch["jobs"]:
        fields(job, {"job_id", "proposals", "depends_on"})
        job_id = name(job["job_id"])
        require(type(job["proposals"]) is list and 1 <= len(job["proposals"]) <= 3, "Declare 1..3 candidate attempts")
        require(type(job["depends_on"]) is list and len(job["depends_on"]) <= 64, "Invalid dependencies")
        for dependency in job["depends_on"]:
            name(dependency)
        attempts = []
        for index, reply in enumerate(job["proposals"]):
            compose(packet, reply)  # Reject every malformed alternative before any dispatch.
            attempts.append(experiment(job_id + "-" + str(index), model_id="1792.gujranwala-reconstruction.v1", nodes=[
                {"node_id": "candidate", "operation_id": OPERATION, "parameters": {"proposal": deepcopy(reply)}, "inputs": {}, "depends_on": []}]))
        jobs.append({"job_id": job_id, "worker_id": "reconstruction-compose", "requires": ["game.reconstruction.compose"],
            "depends_on": list(job["depends_on"]), "attempts": attempts,
            "checks": [{"check_id": "game-owned-contract", "node_id": "candidate", "gate_id": GATE,
                        "policy": {"packet_sha256": packet["packet_sha256"]}}]})
    return plan(packet["task_id"], project_id="1792-reconstruction-development", source_evidence_id=source["evidence_id"], jobs=jobs)


def run_batch(packet: dict, batch: dict, game_root: Path, output_dir: Path, *, max_operations: int = 32) -> dict:
    from .production import Worker, run_production
    validate_packet(packet)
    require_external_destination(game_root, output_dir)
    validator = GameValidator(game_root)
    require(sha(read_regular(Path(game_root) / SOURCE_PATH)) == packet["source_sha256"], "Game baseline changed after work was prepared")
    require(validator.check(parse(packet["baseline_utf8"].encode("utf-8")))["status"] == "PASS", "Invalid baseline")
    source = make_source(packet)
    specification = make_plan(source, batch)
    require(all(not p.is_symlink() for p in (Path(output_dir).absolute(), *Path(output_dir).absolute().parents)), "Symlink destination refused")
    return run_production(source, specification, registry(), (Worker("reconstruction-compose", (OPERATION,)),),
                          gates(validator), output_dir, max_operations=max_operations)


def inspect(output_dir: Path, game_root: Path) -> dict:
    from .production import inspect_production
    register_schemas()
    root = Path(output_dir).absolute()
    require(all(not p.is_symlink() for p in (root, *root.parents)), "Symlink inspection path refused")
    return inspect_production(root, gates(GameValidator(game_root)))


def export_candidate(output_dir: Path, game_root: Path, job_id: str, destination: Path) -> dict:
    """Export only the exact accepted primary candidate; never merge or edit the game."""
    from .production import _read
    name(job_id)
    require_external_destination(game_root, destination)
    inspect(output_dir, game_root)
    # inspect_production returns an inspection summary; follow original records,
    # not the last Session result (which may belong to a different dependent job).
    root = Path(output_dir)
    production = _read(root, "production.json")
    outcome = production["jobs"][job_id]
    require(outcome["status"] == "accepted", "Only an accepted job can be exported")
    receipt = _read(root, outcome["attempts"][-1]["name"], outcome["attempts"][-1])
    graph = _read(root, receipt["graph"]["name"], receipt["graph"])
    result = graph["nodes"]["candidate"]["result"]
    data = result["data"]
    raw = data["candidate_utf8"].encode("utf-8")
    require(sha(raw) == data["candidate_sha256"], "Export content mismatch")
    target = new_directory(destination)
    asset = target / "gujranwala_reconstruction.v1.json"
    asset.write_bytes(raw)
    manifest = {"schema": "ciw.reconstruction-export.v1", "job_id": job_id,
        "production_id": production["production_id"], "execution_id": result["execution_id"], "result_id": result["result_id"],
        "source_sha256": data["source_sha256"], "packet_sha256": data["packet_sha256"],
        "candidate_sha256": data["candidate_sha256"], "file": asset.name,
        "authority": deepcopy(AUTHORITY), "native_gameplay_validation": "not_performed_by_export"}
    save_new(target / "export.json", manifest)
    return manifest
