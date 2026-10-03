"""Explicit game-owned Godot slices on NET's original Session and production loop.

Profiles are operator-selected code grants, not agent-supplied authorizations.
Only bounded parameter assignments cross the candidate boundary. A fresh private
source snapshot is used per invocation; the live title checkout is never edited.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
import platform
import re
import tempfile

from . import game_trace as trace
from .adapters.protocol import AdapterRefusal, InstrumentManifest
from .control_contracts import bytes_ref, content_ref, detached, keys, load, save_new, text
from .control_plane import CapabilityRegistry, ParameterSpace
from .core.identities import content_identity, evidence_id
from .interactive_simulation import file_sha, run_process
from .operations.registry import Operation
from .production import Gate

CAPTURE_OP = "game.project-capture.v1"
PROFILE = "ciw.godot-project-profile.v1"
PROJECT = ('config_version=5\n[application]\nconfig/name="NET isolated game slice"\n'
           '[rendering]\nrenderer/rendering_method="gl_compatibility"\n').encode()
MAX_FILE = 256 * 1024
MAX_TOTAL = 4 * 1024 * 1024
_REGISTERED = False


def relative_script(value: str) -> str:
    text(value)
    parts = PurePosixPath(value).parts
    if (not re.fullmatch(r"[A-Za-z0-9_./-]+\.gd", value) or not parts or
            str(PurePosixPath(value)) != value or PurePosixPath(value).is_absolute() or
            any(p in {".", ".."} or p.startswith(".") for p in parts)):
        raise ValueError("Require a canonical relative GDScript path")
    # Keep identical path semantics on Windows and Linux.
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(p.split('.')[0].lower() in reserved or p.endswith('.') for p in parts):
        raise ValueError("Reserved platform path")
    return value


def validate_profile(value: dict) -> ParameterSpace:
    detached(value)
    keys(value, {"schema", "project_id", "source_revision", "source_scope", "engine_version_prefix",
                 "entrypoint", "files", "scenario", "parameter_space"})
    if value["schema"] != PROFILE:
        raise ValueError("Unsupported game project profile")
    for field in ("project_id", "source_scope"):
        text(value[field])
    if type(value["source_revision"]) is not str or not re.fullmatch(r"[0-9a-f]{40}", value["source_revision"]):
        raise ValueError("Declare an exact source revision context")
    if type(value["engine_version_prefix"]) is not str or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["engine_version_prefix"]):
        raise ValueError("Declare an engine major.minor.patch version")
    files = value["files"]
    if type(files) is not dict or not 1 <= len(files) <= 32:
        raise ValueError("Profile requires 1..32 explicitly pinned script files")
    if len({name.casefold() for name in files}) != len(files):
        raise ValueError("Case-colliding source paths")
    for name, digest in files.items():
        relative_script(name)
        content_ref(digest)
    if relative_script(value["entrypoint"]) not in files:
        raise ValueError("Entrypoint must belong to the exact source manifest")
    scenario = value["scenario"]
    trace.validate_scenario(scenario)
    if scenario["project_id"] != value["project_id"] or scenario["source_class"] != "authored_game":
        raise ValueError("Require an explicitly authored game-owned scenario")
    space = ParameterSpace.from_dict(value["parameter_space"])
    names = set(value["parameter_space"]["parameters"])
    if not names <= set(scenario["parameters"]):
        raise ValueError("Candidate domain refers to undeclared scenario parameters")
    space.validate({name: scenario["parameters"][name] for name in names})
    if not scenario["checks"]:
        raise ValueError("A project workload needs fixed authored checks")
    return space


def candidate_scenario(profile: dict, parameters: dict) -> dict:
    space = validate_profile(profile)
    keys(parameters, {"assignment", "nonce", "diagnostic_fault"})
    text(parameters["nonce"])
    if parameters["diagnostic_fault"] not in {"none", "drop-sample"}:
        raise ValueError("Only a declared missing-sample recorder diagnostic is supported")
    assignment = space.validate(parameters["assignment"])
    scenario = deepcopy(profile["scenario"])
    scenario["parameters"].update(assignment)
    trace.validate_scenario(scenario)
    return scenario


def read_profile(path: Path, expected_sha256: str) -> dict:
    content_ref(expected_sha256)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Require a regular operator-owned profile")
    with path.open('rb') as handle:
        raw = handle.read(65537)
    if len(raw) > 65536 or bytes_ref(raw) != expected_sha256:
        raise ValueError("Operator profile size/digest mismatch")
    from .session import loads_json
    value = loads_json(raw.decode('utf-8'))
    validate_profile(value)
    return detached(value)


class GodotProjectBinding:
    """Operator-trusted native code with a frozen explicit source closure, not a sandbox."""

    def __init__(self, executable: Path, source_root: Path, profile: dict, *, expected_sha256: str):
        validate_profile(profile)
        self._profile = detached(profile)
        content_ref(expected_sha256)
        if Path(executable).is_symlink() or not Path(executable).is_file():
            raise ValueError("Require a regular engine executable")
        self.executable = Path(executable).resolve(strict=True)
        if file_sha(self.executable) != expected_sha256:
            raise ValueError("Engine executable digest mismatch")
        root = Path(source_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("Require a regular source directory")
        root = root.resolve(strict=True)
        self._scripts = {}
        total = 0
        for name, expected in self._profile["files"].items():
            path = root
            for part in PurePosixPath(name).parts:
                path = path / part
                if path.is_symlink():
                    raise ValueError("Source manifest cannot follow symlinks")
            if not path.is_file():
                raise ValueError("Missing declared source file: " + name)
            with path.open('rb') as handle:
                raw = handle.read(MAX_FILE + 1)
            total += len(raw)
            if not raw or len(raw) > MAX_FILE or total > MAX_TOTAL or bytes_ref(raw) != expected:
                raise ValueError("Source size/digest mismatch: " + name)
            raw.decode('utf-8')
            self._scripts[name] = raw
        self._identity = {"provider": "ciw.game.godot-project", "execution_mode": "native_process",
            "executable_sha256": expected_sha256, "profile_digest": content_identity(self._profile),
            "source_revision_context": self._profile["source_revision"], "source_files": deepcopy(self._profile["files"]),
            "project_config_sha256": bytes_ref(PROJECT), "platform": platform.platform(),
            "scope": "frozen explicit game slice; not whole-checkout/shared-library attestation or OS sandbox"}

    @property
    def profile(self) -> dict:
        return deepcopy(self._profile)

    def runtime_identity(self) -> dict:
        if file_sha(self.executable) != self._identity["executable_sha256"]:
            raise AdapterRefusal("game_engine_drift", "Engine executable changed after binding")
        return deepcopy(self._identity)

    def invoke(self, profile: dict, parameters: dict) -> dict:
        if profile != self._profile:
            raise AdapterRefusal("game_profile_mismatch", "Source profile differs from explicit runtime grant")
        scenario = candidate_scenario(profile, parameters)
        self.runtime_identity()
        request = {"scenario": scenario, "scenario_digest": content_identity(scenario),
                   "nonce": parameters["nonce"], "diagnostic_fault": parameters["diagnostic_fault"]}
        try:
            with tempfile.TemporaryDirectory(prefix="net-game-project-") as directory:
                root = Path(directory)
                for name, raw in self._scripts.items():
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                (root / 'project.godot').write_bytes(PROJECT)
                save_new(root / 'request.json', request)
                target = root / 'trace.json'
                run_process([str(self.executable), '--headless', '--path', str(root), '--script',
                             'res://' + profile['entrypoint'], '--', str(root / 'request.json'), str(target)],
                            root, [target, root / 'checkpoint.json'], timeout=30)
                for name in ('stdout.log', 'stderr.log'):
                    with (root / name).open('rb') as handle:
                        raw = handle.read(MAX_TOTAL + 1)
                    if len(raw) > MAX_TOTAL or b'ERROR:' in raw:
                        raise ValueError('Engine output/error guard failed')
                if target.is_symlink() or not target.is_file():
                    raise ValueError('Expected a regular trace file')
                with target.open('rb') as handle:
                    raw = handle.read(65537)
                if not raw or len(raw) > 65536:
                    raise ValueError('Trace exceeds retained text budget')
                result = {"schema": trace.CAPTURE, "request": request, "trace_utf8": raw.decode('utf-8'),
                          "trace_sha256": bytes_ref(raw)}
                trace.validate_capture(result)
                native = trace.unpack(result)[1]
                prefix = re.escape(profile['engine_version_prefix'])
                if native['engine'] != 'godot' or re.match(prefix + r'(?:[-. (]|$)', native['engine_version']) is None:
                    raise ValueError('Native engine version differs from profile')
                self.runtime_identity()
                return result
        except (OSError, ValueError, RuntimeError) as exc:
            raise AdapterRefusal('game_project_failed', str(exc)[:4096]) from exc


def make_run(profile: dict) -> dict:
    from .game_workflow import make_run as scenario_run
    validate_profile(profile)
    run = scenario_run(profile['scenario'])
    run['metadata']['game_project'] = detached(profile)
    run['evidence_id'] = evidence_id(run)
    return run


def _validate_payload(operation, data, run, parameters, selection):
    profile = run['metadata']['game_project']
    expected = candidate_scenario(profile, parameters)
    if run['metadata']['game_scenario'] != profile['scenario']:
        raise ValueError('Original source scenario/profile mismatch')
    trace.validate_capture(data)
    if data['request']['scenario'] != expected:
        raise ValueError('Candidate changed a fixed scenario, check or source binding')
    for key in ('nonce', 'diagnostic_fault'):
        if data['request'][key] != parameters[key]:
            raise ValueError('Capture occurrence parameters mismatch')


def register_schemas() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(CAPTURE_OP, _validate_payload)
        _REGISTERED = True


def registry_for(binding: GodotProjectBinding) -> CapabilityRegistry:
    register_schemas()
    registry = CapabilityRegistry()
    manifest = InstrumentManifest(instrument_id='org.notationsystems.game-project', version='1', role='operation_provider',
        inputs=('run.v1',), outputs=('ciw.operation-result.v1',), units={}, frames=(),
        sampling={'mode': 'declared_game_capture'}, normalization={'state': 'game_owned'},
        supported_operations=(CAPTURE_OP,), determinism={'claim': 'none_from_declaration'},
        tolerance_policy={'policy': 'fixed_game_checks'}, calibration_requirements={'status': 'not_applicable_authored_game'})
    registry.advertise(manifest, runtime=binding.runtime_identity(), capabilities={CAPTURE_OP: ['game.project.capture']})
    def capture(run, parameters):
        return binding.invoke(run['metadata']['game_project'], parameters)
    registry.bind(Operation(CAPTURE_OP, 'backend', capture, binding.runtime_identity))
    return registry


def project_gates() -> dict[str, Gate]:
    from . import control_checks, control_contracts
    register_schemas()
    def policy(value):
        keys(value, set())
    def evaluate(result, unused):
        if result is None:
            return {'status': 'INDETERMINATE', 'detail': 'missing_capture'}
        if result['operation_id'] != CAPTURE_OP:
            raise ValueError('Project check requires an original project capture')
        checked = trace.audit(result['data'], result['execution_id'])
        return {'status': checked['status'], 'detail': checked}
    files = [Path(__file__), Path(trace.__file__), Path(control_checks.__file__), Path(control_contracts.__file__)]
    name = 'game.project-authored.v1'
    return {name: Gate(name, {'provider': 'ciw.game.project-checks',
        'source_files': {p.name: file_sha(p) for p in files}, 'scope': 'ordinary fixed authored-rule checks'}, policy, evaluate)}
