"""Qualify installed local NET workflows from outside the source checkout.

Run this script with the interpreter containing the installed wheel and its
Legibility extra. Results retain actual CLI responses and immutable source
snapshots. Passing qualifies these bounded synthetic workflows only; it grants
no provider authority, physical validation, canonical admission or actuation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile


PROVENANCE = """
import importlib.metadata as metadata, importlib.util, json, sys
distribution = metadata.distribution('computational-instrumentation-workbench')
spec = importlib.util.find_spec('ciw')
direct = distribution.read_text('direct_url.json')
print(json.dumps({'distribution': distribution.metadata['Name'],
    'version': distribution.version, 'python': sys.version,
    'interpreter': sys.executable, 'isolated': bool(sys.flags.isolated),
    'ciw_origin': spec.origin, 'package_root': str(distribution.locate_file('ciw')),
    'direct_url': json.loads(direct) if direct else None,
    'dependencies': {name: metadata.version(name) for name in
                     ('numpy', 'websockets', 'cryptography')}}))
"""


def _hash(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _snapshot(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): _hash(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


class Qualification:
    def __init__(self, destination: Path, timeout: float):
        self.root = destination
        self.timeout = timeout
        self.commands: list[dict] = []
        self.checks: list[dict] = []
        self.root.joinpath("commands").mkdir()

    def require(self, name: str, condition: bool, detail: object = None) -> None:
        self.checks.append({"check": name, "status": "PASS" if condition else "FAIL",
                            "observed": detail})
        if not condition:
            raise ValueError(name)

    def execute(self, name: str, arguments: list[str], expected: int = 0) -> dict:
        # Only runtime locations needed on supported platforms are propagated.
        # Credentials and Python/repository overrides never enter the child.
        allowed = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
                   "TEMP", "TMP", "TMPDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        command = [sys.executable, "-I", *arguments]
        stem = f"{len(self.commands) + 1:02d}-{name}"
        stdout_path = self.root / "commands" / (stem + ".stdout.json")
        stderr_path = self.root / "commands" / (stem + ".stderr.txt")
        record = {"name": name, "argv": command, "cwd": str(self.root),
                  "expected_returncode": expected,
                  "stdout": stdout_path.relative_to(self.root).as_posix(),
                  "stderr": stderr_path.relative_to(self.root).as_posix()}
        self.commands.append(record)
        started = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=self.root, env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            stdout_path.write_bytes(exc.stdout or b"")
            stderr_path.write_bytes(exc.stderr or b"")
            record.update(returncode=None, status="TIMEOUT",
                          elapsed_s=time.monotonic() - started)
            raise ValueError(f"{name} exceeded {self.timeout:g} seconds") from exc
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        record.update(returncode=completed.returncode, elapsed_s=time.monotonic() - started,
                      stdout_sha256=_hash(stdout_path), stderr_sha256=_hash(stderr_path),
                      status="PASS" if completed.returncode == expected else "FAIL")
        if completed.returncode != expected:
            raise ValueError(f"{name} returned {completed.returncode}, expected {expected}; "
                             f"see {stderr_path}")
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise ValueError(f"{name} did not return a JSON object")
        return value

    def ciw(self, name: str, *arguments: str, expected: int = 0) -> dict:
        return self.execute(name, ["-m", "ciw", *arguments], expected)

    def net(self, name: str, *arguments: str, expected: int = 0) -> dict:
        return self.execute(name, ["-m", "ciw.net", *arguments], expected)

    def unchanged(self, name: str, directory: Path, before: dict) -> None:
        after = _snapshot(directory)
        self.require(name, before == after, {"before": before, "after": after})


def _wheel_proof(qualification: Qualification, wheel: Path, package_root: Path) -> dict:
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if item.is_dir() or not item.filename.startswith("ciw/"):
                continue
            relative = Path(item.filename).relative_to("ciw")
            if ".." in relative.parts or relative.is_absolute() or item.filename in files:
                raise ValueError("Wheel contains an invalid or duplicated ciw package path")
            expected = sha256(archive.read(item)).hexdigest()
            installed = package_root / relative
            qualification.require("installed-wheel-byte:" + item.filename,
                                  installed.is_file() and _hash(installed) == expected,
                                  {"expected_sha256": expected, "installed_file": str(installed)})
            files[item.filename] = expected
    qualification.require("wheel-package-present", bool(files))
    return {"wheel": str(wheel), "wheel_sha256": _hash(wheel),
            "ciw_files_matched": len(files), "files": files}


def _scientific(qualification: Qualification, family: str, directory: Path) -> dict:
    arguments = ("impact", "plate") if family == "impact" else ("atmosphere",)
    qualification.net(family + "-example", *arguments, "example", "--output", family + "-request.json")
    created = qualification.net(family + "-run", *arguments, "run", family + "-request.json",
                                "--output-dir", directory.name)
    qualification.require(family + "-numerical-local", created["status"] == "LOCAL")
    before = _snapshot(directory)
    inspected = qualification.net(family + "-inspect", *arguments, "inspect", directory.name)
    verified = qualification.net(family + "-verify", *arguments, "verify", directory.name)
    identity_fields = ("evidence_id", "operation_id", "execution_id", "result_id",
                       "verification_operation_id", "verification_execution_id", "verification_id")
    qualification.require(family + "-retained-identities",
                          all(inspected[key] == verified[key] for key in identity_fields),
                          {key: inspected[key] for key in identity_fields})
    qualification.require(family + "-separate-identities",
                          len({inspected[key] for key in identity_fields}) == len(identity_fields))
    qualification.require(family + "-fresh-numerical-report-only",
                          inspected["fresh_numerical_verification"] is False
                          and verified["fresh_numerical_verification"] is True
                          and inspected["fresh_execution"] is False and verified["fresh_execution"] is False)
    qualification.require(family + "-authority-boundary",
                          verified["authority"]["physical_validation"] == "not_established"
                          and verified["authority"]["state_admission"] == "not_performed"
                          and verified["authority"]["hardware_actuation"] == "not_performed"
                          and verified["preservation"]["state_admission_performed"] is False,
                          verified["authority"])
    qualification.unchanged(family + "-inspect-verify-unchanged", directory, before)
    return {"inspection": inspected, "verification": verified, "snapshot": before}


def qualify(destination: Path, *, expected_wheel: Path | None = None, timeout: float = 120) -> dict:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Output directory already exists; choose a new path to preserve retained results")
    checkout = Path(__file__).resolve().parents[1]
    if (checkout / "src" / "ciw").is_dir() and destination.resolve().is_relative_to(checkout):
        raise ValueError("Output directory must be outside the source checkout")
    destination.mkdir(parents=True, exist_ok=False)
    qualification = Qualification(destination.resolve(), timeout)
    report = {"schema": "ciw.installed-operator-qualification.v1", "status": "FAIL",
              "started_at": datetime.now(timezone.utc).isoformat(),
              "scope": "installed local public synthetic workflows",
              "physical_validation_status": "not_assessed", "canonical_admission": False,
              "physical_actuation": "not_performed", "private_provider_qualification": "not_performed",
              "commands": qualification.commands, "checks": qualification.checks}
    try:
        provenance = qualification.execute("installed-provenance", ["-c", PROVENANCE])
        report["installed_package"] = provenance
        qualification.require("isolated-interpreter", provenance["isolated"] is True)
        package_root = Path(provenance["package_root"]).resolve(strict=True)
        editable = (provenance.get("direct_url") or {}).get("dir_info", {}).get("editable")
        qualification.require("installed-package-without-source-fallback",
                              editable is not True and Path(provenance["ciw_origin"]).resolve()
                              == package_root / "__init__.py" and not package_root.is_relative_to(checkout))
        report["wheel_byte_proof"] = (_wheel_proof(qualification, expected_wheel, package_root)
                                      if expected_wheel else {"status": "not_requested"})
        for profile in ("core", "legibility"):
            result = qualification.ciw("doctor-" + profile, "doctor", "--profile", profile)
            qualification.require("doctor-" + profile + "-preflight",
                                  result["status"] == "preflight_passed"
                                  and result["read_only"] is True
                                  and result["qualification"] == "not_performed")

        providers = qualification.net("provider-discovery", "providers", "--json")
        capabilities = qualification.net("provider-capabilities", "capabilities", "--json")
        indexed = qualification.ciw("instrument-capabilities", "capabilities", "list")
        qualification.require("discovery-grants-no-execution-authority",
                              providers["authorizes_execution"] is False
                              and capabilities["authorizes_execution"] is False
                              and indexed["authorizes_execution"] is False
                              and indexed["qualification"] == "not_performed"
                              and indexed["status"] == "index_only"
                              and all(item["bound"] is False for item in providers["operations"].values()))
        report["discovery"] = {"providers": len(providers["providers"]),
                               "declared_operations": len(capabilities["operations"]),
                               "capability_index_response": indexed}

        demo = qualification.ciw("oscillator-demo", "demo", "--output", "oscillator.json")
        analyzed = qualification.ciw("oscillator-stats", "analyze", "stats", "--recording", "oscillator.json",
                                     "--start", "0", "--end", "12", "--output-dir", "oscillator")
        result = analyzed["payload"]
        before = _snapshot(qualification.root / "oscillator")
        recording_before = _hash(qualification.root / "oscillator.json")
        workspace = qualification.ciw("oscillator-inspect", "inspect", "oscillator/workspace.json")
        reopened = qualification.net("oscillator-reopen", "inspect", "oscillator/workspace.json", "--json")
        qualification.require("oscillator-retained-identities",
                              workspace["run"]["evidence_id"] == demo["evidence_id"] == result["evidence_id"]
                              and result in workspace["results"] and result in reopened["results"].values())
        qualification.require("oscillator-no-verification-promotion",
                              result["verification_status"] == "not_verified" and result["verification_id"] is None
                              and reopened["physical_validation"] == "not_performed"
                              and reopened["state_admission"] == "not_performed")
        qualification.require("oscillator-separate-identities",
                              result["operation_id"] == "statistics.v1"
                              and len({result[key] for key in ("evidence_id", "operation_id", "execution_id", "result_id")}) == 4)
        qualification.unchanged("oscillator-inspection-unchanged", qualification.root / "oscillator", before)
        qualification.require("oscillator-recording-unchanged",
                              recording_before == _hash(qualification.root / "oscillator.json"))

        impact_dir = qualification.root / "impact-plate"
        impact = _scientific(qualification, "impact", impact_dir)
        object_id = "notations:specimen:installed-plate-001"
        qualification.ciw("impact-legibility-import", "legibility", "import-impact", "impact-plate/workspace.json",
                          "--object-id", object_id, "--version", "1", "--output-dir", "impact-legibility")
        imported_dir = qualification.root / "impact-legibility"
        imported_before = _snapshot(imported_dir)
        imported = qualification.ciw("impact-legibility-verify", "legibility", "verify", "impact-legibility",
                                     "--expected-object-id", object_id, "--expected-version", "1")
        bindings = _read(imported_dir / "compilation-binding.json")
        source = _read(imported_dir / "contract.json")
        qualification.require("impact-legibility-preserves-scientific-identities",
                              source["bindings"] == {key: impact["inspection"][key] for key in
                                                     ("evidence_id", "operation_id", "execution_id", "verification_id")}
                              and bindings["source_bindings"] == source["bindings"]
                              and bindings["compilation_execution_id"] != source["bindings"]["execution_id"])
        qualification.require("impact-legibility-content-without-authority",
                              imported["content_intact"] is True and imported["artifact_status"] == "verified"
                              and source["qualification"]["status"] == "numerical_only"
                              and source["qualification"]["canonical_admission"] is False
                              and imported["physical_validation_status"] == "not_assessed"
                              and imported["canonical_admission"] is False)
        qualification.unchanged("impact-import-preserves-original-workspace", impact_dir, impact["snapshot"])
        qualification.unchanged("impact-legibility-verification-unchanged", imported_dir, imported_before)

        published = qualification.ciw("signed-legibility-demo", "legibility", "demo", "--output-dir", "signed-legibility")
        signed_dir = qualification.root / "signed-legibility"
        signed_before = _snapshot(signed_dir)
        signed_source = _read(signed_dir / "contract.json")
        expected = ("--trust", "signed-legibility/demo-trust.json", "--expected-object-id",
                    signed_source["object"]["object_id"], "--expected-version", signed_source["object"]["version"])
        signed = qualification.ciw("signed-legibility-verify", "legibility", "verify", "signed-legibility", *expected)
        refused = qualification.ciw("signed-legibility-wrong-version", "legibility", "verify", "signed-legibility",
                                   *expected[:-1], signed_source["object"]["version"] + "-wrong", expected=2)
        qualification.require("signed-content-trust-and-currentness",
                              all(signed[key] is True for key in ("content_intact", "signature_valid", "issuer_trusted",
                                                                 "object_matches", "version_current"))
                              and signed["verification_id"] != published["verification"]["verification_id"])
        qualification.require("wrong-version-refused-with-intact-signature",
                              refused["version_current"] is False and refused["signature_valid"] is True
                              and refused["verification_id"] != signed["verification_id"])
        qualification.require("legibility-does-not-grant-scientific-authority",
                              signed["physical_validation_status"] == "not_assessed" and signed["canonical_admission"] is False)
        qualification.unchanged("signed-verification-and-refusal-unchanged", signed_dir, signed_before)
        report["trust_scope"] = "Same-run synthetic demo anchor; organizational issuer identity and external freshness are not established"

        atmosphere_dir = qualification.root / "atmosphere-column"
        atmosphere = _scientific(qualification, "atmosphere", atmosphere_dir)
        handoffs = {}
        for provider in ("impact", "fluid", "render"):
            path = "atmosphere-" + provider + ".json"
            exported = qualification.net("atmosphere-handoff-" + provider, "atmosphere", "handoff",
                                         atmosphere_dir.name, "--sample-index", "0", "--provider", provider,
                                         "--output", path)
            payload = _read(qualification.root / path)
            qualification.require("atmosphere-handoff-bindings:" + provider,
                                  payload["provider"] == provider and payload["sample_index"] == 0
                                  and payload["source_evidence_id"] == atmosphere["inspection"]["evidence_id"]
                                  and payload["source_result_id"] == atmosphere["inspection"]["result_id"]
                                  and payload["source_execution_id"] == atmosphere["inspection"]["execution_id"]
                                  and payload["verification_id"] == atmosphere["inspection"]["verification_id"]
                                  and payload["recomputed_report_digest"] == atmosphere["verification"]["recomputed_report_digest"]
                                  and exported["status"] == "exported")
            handoffs[provider] = {"file": path, "sha256": _hash(qualification.root / path),
                                  "record_digest": payload["record_digest"]}
        qualification.unchanged("atmosphere-handoffs-preserve-original-bundle", atmosphere_dir, atmosphere["snapshot"])
        report["handoffs"] = handoffs
        report["numerical_scope"] = {"impact": "bounded simply supported elastic modal plate patch contact",
                                     "atmosphere": "bounded dry ideal-gas hydrostatic column",
                                     "receiving_provider_execution": "not_performed"}
        report["status"] = "PASS"
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        report["failure"] = {"type": type(exc).__name__, "reason": str(exc)}
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write(qualification.root / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory outside the source checkout")
    parser.add_argument("--expected-wheel", type=Path, help="Optional exact ciw package-byte comparison")
    parser.add_argument("--timeout", type=float, default=120, help="Per-command limit in seconds (1–300)")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("timeout must be between 1 and 300 seconds")
    try:
        report = qualify(args.output_dir, expected_wheel=args.expected_wheel, timeout=args.timeout)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": report["status"], "report": str(args.output_dir.absolute() / "report.json"),
                      "commands": len(report["commands"]), "checks": len(report["checks"]),
                      "physical_validation_status": report["physical_validation_status"],
                      "canonical_admission": report["canonical_admission"]}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
