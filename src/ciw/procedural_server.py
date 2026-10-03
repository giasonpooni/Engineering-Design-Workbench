"""Loopback authoring surface for bounded graphics programs and retained runs."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import re
import stat
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs
import uuid

from .control_contracts import json_tree
from .session import loads_json

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RUNS = 64
RUN_ID = re.compile(r"run-[0-9a-f]{32}")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class GraphicsServer(ThreadingHTTPServer):
    """An explicitly local authoring server; no generic Session socket is opened."""
    daemon_threads = True

    def __init__(self, output_dir: Path, port: int = 0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Graphics port must be an integer inside 0..65535")
        self.root = Path(output_dir)
        if self.root.is_symlink():
            raise ValueError("Graphics output directory cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()
        metadata = self.root.lstat()
        self._root_identity = (metadata.st_dev, metadata.st_ino)
        self.operation_lock = threading.Lock()
        self.run_paths()  # Reject unrelated files and unbounded histories.
        super().__init__(("127.0.0.1", port), GraphicsHandler)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server_port}"

    def run_paths(self):
        metadata = self.root.lstat()
        if (not stat.S_ISDIR(metadata.st_mode)
                or (metadata.st_dev, metadata.st_ino) != self._root_identity):
            raise ValueError("Graphics output directory was replaced")
        paths = sorted(self.root.iterdir(), key=lambda p: p.name)
        if len(paths) > MAX_RUNS:
            raise ValueError("Retained graphics history exceeds 64 runs")
        if any(not RUN_ID.fullmatch(p.name) or not stat.S_ISDIR(p.lstat().st_mode) for p in paths):
            raise ValueError("Graphics history must contain only its retained run directories")
        return paths

    def run_path(self, identity):
        if not RUN_ID.fullmatch(identity):
            raise ValueError("Unknown graphics run identity")
        path = self.root / identity
        if path not in self.run_paths():
            raise ValueError("Unknown graphics run identity")
        return path


class GraphicsHandler(BaseHTTPRequestHandler):
    server: GraphicsServer

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def _respond(self, status, content, content_type="application/json", filename=None):
        if not isinstance(content, bytes):
            content = json.dumps(content, allow_nan=False, separators=(",", ":")).encode()
        if len(content) > MAX_RESPONSE_BYTES:
            raise ValueError("Graphics response exceeds the bounded 8 MiB transfer budget")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A cancelled transient preview is never admitted as a run.

    def _boundary(self):
        hosts = self.headers.get_all("Host", [])
        if hosts != [self.server.origin.removeprefix("http://")]:
            raise ValueError("Use the advertised loopback host and port")
        origins = self.headers.get_all("Origin", [])
        if origins and origins != [self.server.origin]:
            raise ValueError("Graphics requests must come from the same local origin")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ValueError("Cross-site graphics requests are not permitted")

    def _body(self):
        if self.headers.get_all("Transfer-Encoding", []):
            raise ValueError("Chunked graphics requests are unsupported")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]):
            raise ValueError("Graphics requests require one bounded Content-Length")
        length = int(lengths[0])
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("Graphics request exceeds the 64 KiB input budget")
        if self.headers.get_all("Content-Type", []) != ["application/json"]:
            raise ValueError("Graphics requests require application/json")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Incomplete graphics request")
        value = loads_json(raw.decode("utf-8"))
        json_tree(value)
        if type(value) is not dict:
            raise ValueError("Graphics request must be a JSON object")
        return value

    def _retained(self, path):
        from . import procedural_workflow as workflow
        # One validated, detached snapshot; static inspection activates no provider.
        return {"id": path.name, **workflow.read_bundle(path)}

    def do_GET(self):
        try:
            self._boundary()
            parsed = urlsplit(self.path)
            path = parsed.path
            assets = {"/": ("procedural_workbench.html", "text/html; charset=utf-8"),
                      "/procedural_workbench.css": ("procedural_workbench.css", "text/css; charset=utf-8"),
                      "/procedural_workbench.js": ("procedural_workbench.js", "text/javascript; charset=utf-8")}
            if path in assets and not parsed.query:
                name, mime = assets[path]
                self._respond(200, files("ciw").joinpath("web", name).read_bytes(), mime)
            elif path == "/api/examples" and not parsed.query:
                from .procedural_contract import example_request
                from .procedural_surface import example_surface
                from .procedural_texture import example_texture
                self._respond(200, {"examples": [{"id": name, "label": name.title(), "request": example_request(name)}
                                                  for name in ("sphere", "gyroid", "wave")]
                                    + [{"id": "parametric", "label": "Parametric torus", "request": example_surface()},
                                       {"id": "texture", "label": "Texture and shader", "request": example_texture()}],
                                    "limits": {"resolution": [8, 24], "surface_resolution": [8, 48],
                                               "texture_resolution": [16, 256], "parameters": 8, "retained_runs": MAX_RUNS}})
            elif path == "/api/history" and not parsed.query:
                from .procedural_workflow import inspect
                self._respond(200, {"runs": [{"id": p.name, "summary": inspect(p)} for p in self.server.run_paths()]})
            elif re.fullmatch(r"/api/runs/run-[0-9a-f]{32}", path) and not parsed.query:
                self._respond(200, self._retained(self.server.run_path(path.rsplit("/", 1)[1])))
            elif re.fullmatch(r"/api/runs/run-[0-9a-f]{32}/export", path):
                formats = parse_qs(parsed.query, strict_parsing=True)
                if set(formats) != {"format"} or len(formats["format"]) != 1 or formats["format"][0] not in {"obj", "png", "json", "manifest"}:
                    raise ValueError("Select obj, png, json or manifest export")
                directory = self.server.run_path(path.split("/")[3])
                from . import procedural_workflow as workflow
                if not self.server.operation_lock.acquire(blocking=False):
                    self._respond(429, {"status": "REFUSE", "reason": "A graphics operation is running; retry shortly"})
                    return
                try:
                    with tempfile.TemporaryDirectory(prefix="net-graphics-export-") as temporary:
                        fmt = formats["format"][0]
                        output = Path(temporary) / {"json": "artifact.json", "obj": "mesh.obj", "png": "texture.png", "manifest": "export-manifest.json"}[fmt]
                        if fmt == "json":
                            workflow.export_json(directory, output)
                        elif fmt == "manifest":
                            workflow.export_manifest(directory, output)
                        else:
                            export = workflow.export_png if fmt == "png" else workflow.export_obj
                            export(directory, output)
                        mime = {"obj": "text/plain", "png": "image/png", "json": "application/json", "manifest": "application/json"}[fmt]
                        self._respond(200, output.read_bytes(), mime, output.name)
                finally:
                    self.server.operation_lock.release()
            else:
                self._respond(404, {"status": "REFUSE", "reason": "Unknown graphics route"})
        except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration, RecursionError) as exc:
            self._respond(400, {"status": "REFUSE", "reason": str(exc)})

    def do_POST(self):
        acquired = False
        try:
            self._boundary()
            body = self._body()
            parsed = urlsplit(self.path)
            if parsed.query:
                raise ValueError("Graphics mutations do not accept query parameters")
            if not self.server.operation_lock.acquire(blocking=False):
                self._respond(429, {"status": "REFUSE", "reason": "A graphics operation is running; retry shortly"})
                return
            acquired = True
            from . import procedural_workflow as workflow
            if parsed.path == "/api/preview":
                if set(body) != {"request"}:
                    raise ValueError("Preview requires exactly one request")
                request = workflow.validate_request(body["request"])
                artifact = workflow.generate_artifact(request)
                self._respond(200, {"status": "preview", "transient": True, "request": request,
                                    "artifact": artifact, "report": workflow.verify_artifact(request, artifact)})
            elif parsed.path == "/api/run":
                if set(body) != {"request"}:
                    raise ValueError("Run requires exactly one request")
                if len(self.server.run_paths()) >= MAX_RUNS:
                    raise ValueError("Graphics history is full; start a new output directory")
                destination = self.server.root / ("run-" + uuid.uuid4().hex)
                workflow.run(body["request"], destination)
                self._respond(200, self._retained(destination))
            elif re.fullmatch(r"/api/runs/run-[0-9a-f]{32}/replay", parsed.path):
                if body:
                    raise ValueError("Replay does not accept modified inputs")
                if len(self.server.run_paths()) >= MAX_RUNS:
                    raise ValueError("Graphics history is full; start a new output directory")
                original = self.server.run_path(parsed.path.split("/")[3])
                destination = self.server.root / ("run-" + uuid.uuid4().hex)
                replay = workflow.replay(original, destination)
                result = self._retained(destination)
                result["replay"] = replay
                self._respond(200, result)
            else:
                self._respond(404, {"status": "REFUSE", "reason": "Unknown graphics route"})
        except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration, RecursionError) as exc:
            self._respond(400, {"status": "REFUSE", "reason": str(exc)})
        finally:
            if acquired:
                self.server.operation_lock.release()


def serve(output_dir: Path, port: int = 8788):
    with GraphicsServer(output_dir, port) as server:
        print(f"NET procedural graphics: {server.origin}", flush=True)
        print("Transient previews; retained runs require an explicit Run action. Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
