"""Opt-in loopback transport for the existing Board, Session and Needle.

Only fixed endpoints and operator-loaded artifacts are exposed. No filesystem
browser, shell endpoint, provider loader, hardware control or remote deployment.
"""
from __future__ import annotations

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
from threading import RLock
import uuid

from .control_contracts import keys, record, save_new
from .control_plane import builtin_registry, run_graph
from .core.identities import validate_evidence_identity
from .instruments import validate_run
from .needle import delta_projection, execute_needle, plan_from_spec
from .semantic_capabilities import builtin_semantic_registry
from .session import Session, loads_json
from .system_board import compile_board, validate_board
from .visual_board import (apply_parameter_edit, default_view, project_scene, render_html,
                           validate_edit, view_from_spec)

MAX_REQUEST_BYTES = 64 * 1024
MAX_ACTIONS = 256
SAFE_OPERATIONS = {"statistics.v1", "spectrum.periodogram.v1"}


class BoardWorkbench:
    """Thin UI adapter. It retains the original Board and one ordinary Session."""
    def __init__(self, board: dict, output_dir: Path, *, source: dict | None = None, allow_run=False):
        self.board = validate_board(board)
        self.concrete = builtin_registry(bind=True)
        self.semantic = builtin_semantic_registry(self.concrete)
        self.source = deepcopy(source)
        self.allow_run = bool(allow_run)
        self.compilation = None
        self.compilation_error = None
        try:
            self.compilation = compile_board(self.board, self.semantic)
        except (ValueError, TypeError, KeyError) as exc:
            self.compilation_error = str(exc)
        self.lock = RLock()
        self.baseline = None
        self.session = None
        self.actions = 0
        if allow_run:
            self._execution_preflight(self.board, self.compilation)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=False)
        save_new(self.output_dir / "board.json", self.board)

    def _execution_preflight(self, board, compilation):
        if not self.allow_run:
            raise ValueError("Execution is disabled; operator must supply --allow-run")
        if self.source is None or compilation is None:
            raise ValueError("Execution requires a valid source and executable Board")
        if board["model_id"] != "analytic-damped-oscillator.v1" or self.source.get("instrument") != board["model_id"]:
            raise ValueError("Visual execution V1 is qualified only for the retained analytic oscillator")
        validate_run(self.source)
        validate_evidence_identity(self.source)
        graph = compilation["semantic_compilation"]["experiment"]
        if len(graph["nodes"]) > 16 or len(self.source["time_s"]) > 4096:
            raise ValueError("Visual execution workload exceeds V1 bounds")
        for node in graph["nodes"]:
            if node["operation_id"] not in SAFE_OPERATIONS or set(node["parameters"]) - {"channel", "interval_s"}:
                raise ValueError("Visual execution permits only existing statistics/periodogram selections")

    def state(self):
        return {"board": deepcopy(self.board), "view": default_view(self.board),
                "execution_enabled": self.allow_run,
                "compilation_error": self.compilation_error,
                "source_evidence_id": self.source["evidence_id"] if self.allow_run else None,
                "baseline_ref": self.baseline["record_digest"] if self.baseline else None}

    def _directory(self, prefix):
        if self.actions >= MAX_ACTIONS:
            raise ValueError("Visual work session reached its 256-action retention budget")
        self.actions += 1
        name = prefix + "-" + uuid.uuid4().hex
        path = self.output_dir / name
        path.mkdir()
        return path

    def retain_view(self, spec):
        view = view_from_spec(self.board, spec)
        scene = project_scene(self.board, view)
        path = self._directory("view")
        save_new(path / "view.json", view)
        return {"view": view, "scene": scene, "retained_directory": path.name}

    def preview(self, request):
        preview = apply_parameter_edit(self.board, request, self.semantic)
        path = self._directory("edit")
        save_new(path / "request.json", request)
        save_new(path / "preview.json", preview)
        save_new(path / "candidate-board.json", preview["candidate_board"])
        return {"preview": preview, "retained_directory": path.name}

    def run_baseline(self):
        self._execution_preflight(self.board, self.compilation)
        path = self._directory("baseline")
        save_new(path / "compilation.json", self.compilation)
        if self.session is None:
            self.session = Session(self.source, self.output_dir / "session", operations=self.concrete.operations)
        run = run_graph(self.session, self.compilation["semantic_compilation"]["experiment"], self.concrete)
        save_new(path / "run.json", run)
        if run["status"] == "completed":
            self.baseline = run  # handle to the retained ordinary graph-run, not a new scientific state
        return {"run": run, "baseline_ref": self.baseline["record_digest"] if self.baseline else None,
                "retained_directory": path.name}

    def run_candidate(self, request, baseline_ref):
        preview = apply_parameter_edit(self.board, request, self.semantic)
        validate_edit(preview, self.board, self.semantic)
        self._execution_preflight(preview["candidate_board"], preview["compilation"])
        if self.baseline is None or self.baseline["record_digest"] != baseline_ref:
            raise ValueError("Candidate must target the exact current completed baseline")
        if self.baseline["experiment"] != self.compilation["semantic_compilation"]["experiment"]:
            raise ValueError("Retained baseline differs from the original Board compilation")
        if self.baseline["source_evidence_id"] != self.source["evidence_id"]:
            raise ValueError("Retained baseline source evidence mismatch")
        spec = {"needle_id": "board-edit-" + preview["record_digest"][7:31],
                "target": {"kind": "NODE_PARAMETER", "node_id": request["node_id"], "parameter": request["parameter"]},
                "replacement": request["replacement"],
                "propagation": {"relation": "DEPENDENCY", "scope": "DESCENDANTS_INCLUSIVE"}}
        plan = plan_from_spec(self.baseline, spec)
        path = self._directory("needle")
        save_new(path / "request.json", request)
        save_new(path / "preview.json", preview)
        save_new(path / "plan.json", plan)
        run = execute_needle(self.session, self.baseline, plan, self.concrete)
        save_new(path / "run.json", run)
        delta = delta_projection(self.baseline, run)
        save_new(path / "delta.json", delta)
        receipt = record("board-visual-run", board_ref=self.board["record_digest"],
                         candidate_board_ref=preview["candidate_board"]["record_digest"],
                         preview_ref=preview["record_digest"], source_evidence_id=self.source["evidence_id"],
                         baseline_ref=baseline_ref, plan_ref=plan["record_digest"],
                         run_ref=run["record_digest"], delta_ref=delta["record_digest"],
                         claims={"ordinary_needle_execution": True, "provider_execution": True,
                                 "dependency_not_causality": True, "baseline_mutated": False,
                                 "state_admission": False, "physical_authority": False,
                                 "representation_expansion_authorized": False})
        save_new(path / "receipt.json", receipt)
        return {"receipt": receipt, "run": run, "delta": delta,
                "baseline_ref": baseline_ref, "retained_directory": path.name}


def make_server(workbench: BoardWorkbench, *, port=0) -> HTTPServer:
    """IPv4 loopback only, fixed Host/Origin, per-process bearer capability."""
    token = secrets.token_urlsafe(32)
    html = render_html(None, live=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # do not log bearer tokens, source artifacts or requests

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def send(self, code, payload, media="application/json"):
            raw = payload if type(payload) is bytes else json.dumps(payload, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", media + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def permitted(self, auth=True):
            host = "127.0.0.1:" + str(self.server.server_port)
            if self.headers.get("Host") != host or len(self.headers.get_all("Host", [])) != 1:
                self.send(403, {"status": "refused", "reason": "Host is not the configured loopback origin"})
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin != "http://" + host:
                self.send(403, {"status": "refused", "reason": "Cross-origin request refused"})
                return False
            supplied = self.headers.get("X-NET-Board-Token", "")
            if auth and not secrets.compare_digest(supplied, token):
                self.send(403, {"status": "refused", "reason": "Missing or invalid local capability"})
                return False
            return True

        def do_GET(self):
            if not self.permitted(auth=self.path != "/"):
                return
            if self.path == "/":
                self.send(200, html, "text/html")
            elif self.path == "/api/state":
                self.send(200, workbench.state())
            else:
                self.send(404, {"status": "refused", "reason": "Unknown fixed endpoint"})

        def do_POST(self):
            if not self.permitted():
                return
            routes = {"/api/view", "/api/edit", "/api/baseline", "/api/candidate"}
            if self.path not in routes:
                self.send(404, {"status": "refused", "reason": "Unknown fixed endpoint"})
                return
            try:
                if self.headers.get("Transfer-Encoding") is not None:
                    raise ValueError("Chunked request bodies are not supported")
                if self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Require application/json")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isdigit():
                    raise ValueError("Require one explicit bounded Content-Length")
                length = int(lengths[0])
                if not 1 <= length <= MAX_REQUEST_BYTES:
                    raise ValueError("Request exceeds 64 KiB budget")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body")
                value = loads_json(raw.decode("utf-8"))
                with workbench.lock:
                    if self.path == "/api/view":
                        result = workbench.retain_view(value)
                    elif self.path == "/api/edit":
                        result = workbench.preview(value)
                    elif self.path == "/api/baseline":
                        keys(value, {"board_ref"})
                        if value["board_ref"] != workbench.board["record_digest"]:
                            raise ValueError("Baseline request targets a different Board")
                        result = workbench.run_baseline()
                    else:
                        keys(value, {"request", "baseline_ref"})
                        result = workbench.run_candidate(value["request"], value["baseline_ref"])
                self.send(200, result)
            except (ValueError, TypeError, KeyError, OverflowError, UnicodeError, RecursionError) as exc:
                self.send(400, {"status": "refused", "reason": str(exc)})
            except OSError:
                self.send(500, {"status": "refused", "reason": "Local retention failed; no success claimed"})

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.board_token = token
    server.board_url = f"http://127.0.0.1:{server.server_port}/#token={token}"
    return server
