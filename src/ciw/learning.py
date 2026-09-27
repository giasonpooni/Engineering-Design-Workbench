"""An optional teaching surface over existing CIW operations and workspaces.

Lesson text is explanation, not an executable language or a proof. The only
initial workload is the built-in synthetic oscillator's displacement RMS.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from .instruments import make_demo_run
from .session import Session

TOPIC = "oscillator-rms"
LEVELS = ("concrete", "structural", "formal", "computational")
BOOKS = (
    ("I", "WHY", "Problems that motivate mathematical capabilities"),
    ("II", "GRAMMAR", "State, structure, change, computation and scoped checks"),
    ("III", "BUILD", "Derive constructions from declared assumptions"),
    ("IV", "COMPUTE", "Representation, algorithm, execution and verification"),
    ("V", "ATLAS", "Connections between supported mathematical structures"),
    ("VI", "FRONTIER", "Recognize limitations and propose testable extensions"),
)
EXPLANATIONS = {
    "concrete": "Opposite displacements can cancel in a mean while motion persists. RMS describes sample amplitude without that sign cancellation.",
    "structural": "The sample vector q in R^N maps to ||q||_2 / sqrt(N). Its units remain metres; sign and time ordering are lost.",
    "formal": "For N > 0 equally weighted real samples, r(q) = sqrt(sum(q_i^2)/N). r(-q) = r(q) and r(Pq) = r(q) for any permutation P.",
    "computational": "statistics.v1 evaluates all samples in [start, end), scaling before binary64 reductions. The educational check uses Decimal arithmetic on the retained binary64 samples.",
}
LESSON = {
    "topic": TOPIC,
    "title": "From oscillating displacement to RMS amplitude",
    "prerequisites": ["real numbers", "vectors of samples", "mean", "square root"],
    "phenomenon": "A signed average can hide oscillation. Ask for an amplitude summary while retaining the original trajectory.",
    "state": "q = (q_1, ..., q_N), displacement samples in metres from a synthetic oscillator.",
    "structure": "Finite, uniformly sampled data. The selected interval is half-open [start, end); samples have equal weight.",
    "question": "What scalar measures the amplitude of these samples, and which distinctions does it erase?",
    "transformation": "q -> square each sample -> arithmetic mean -> nonnegative square root.",
    "invariants": "RMS is unchanged by sign reversal or sample permutation. These are algebraic properties of this map, not claims that the dynamics preserve RMS.",
    "information_loss": "RMS alone cannot recover sign, phase, time ordering or the original trajectory.",
    "computation": "Use the existing statistics.v1 operation through operation.execute. The retained output also includes mean, minimum and maximum.",
    "verification": "Compare the retained RMS with an 80-digit Decimal evaluation of the same binary64 samples. This is a numerical cross-check, not a formal proof or physical validation.",
    "generalization": "RMS is a normalized Euclidean norm. Irregular sampling requires an explicitly chosen weighting before interpreting a time average.",
    "uncertainty": "No sensor uncertainty or calibration is inferred from this synthetic example.",
    "exercise": "Before running: predict what sign reversal, permuting samples, doubling amplitude and adding an offset do to RMS. Which changes can an RMS value distinguish?",
    "derive": [
        "Choose the finite real sample vector q and require N > 0.",
        "Square each coordinate so opposite signs do not cancel.",
        "Average the squares: s = (q_1^2 + ... + q_N^2)/N.",
        "Take the nonnegative root r = sqrt(s), restoring the original unit.",
        "By the Euclidean norm definition, r = ||q||_2/sqrt(N).",
        "Squaring removes each sign; a permutation leaves the finite sum unchanged.",
    ],
    "bridge": [
        "Sampled signal -> vector in R^N -> quadratic form q^T q -> normalized norm.",
        "RMS displacement is not energy. The oscillator energy also requires velocity, mass and frequency.",
        "A numerical residual assesses this finite calculation; a proof needs stated premises and a proof method.",
    ],
    "history": {
        "problem": "How can an alternating quantity have a useful nonzero amplitude summary when its signed average is zero?",
        "context": "Alternating electrical signals provide one motivation for distinguishing instantaneous, peak and effective quantities. Here we explore displacement samples.",
        "new_capability": "Aggregate squared values and restore the quantity's unit with a square root.",
        "scope": "A problem-led prologue, not a chronology or a claim that all mathematics arose from one grammar.",
        "reading": "https://openstax.org/books/university-physics-volume-2/pages/15-1-ac-sources",
    },
}


def catalog():
    return {
        "surface": "learning",
        "grammar": ["state", "structure", "change", "compute", "verify"],
        "books": [{"book": number, "title": title, "purpose": purpose,
                   "status": "curriculum_outline"} for number, title, purpose in BOOKS],
        "available_lessons": [TOPIC],
        "available_commands": ["history", "learn", "explore", "work", "inspect", "verify", "replay"],
        "pending": ["broader lessons and sourced historical narratives",
                    "learner-selected prerequisite records", "symbolic and proof-provider bindings"],
        "authority": "Lesson prose never assigns verification, admission or equipment authority.",
    }


def lesson(topic=TOPIC, level="structural"):
    if topic != TOPIC or level not in LEVELS:
        raise ValueError("Unsupported lesson or abstraction level")
    return {**deepcopy(LESSON), "level": level, "explanation": EXPLANATIONS[level]}


def _execute(session, parameters):
    reply = session.handle({
        "protocol_version": 1, "request_id": uuid4().hex,
        "type": "operation.execute",
        "payload": {"operation_id": "statistics.v1", "parameters": parameters},
    })
    if reply["type"] == "error":
        raise ValueError(reply["payload"]["message"])
    return reply["payload"]


def _result(session, result_id):
    if result_id not in session.results:
        raise ValueError("Select a retained result_id from this workspace")
    result = session.results[result_id]
    if (session.run["instrument"] != "analytic-damped-oscillator.v1"
            or result.get("schema") != "ciw.operation-result.v1"
            or result["operation_id"] != "statistics.v1"
            or result["channel"] != "q" or result["data"]["unit"] != "m"):
        raise ValueError("Lesson requires a retained statistics.v1 displacement result from the synthetic oscillator")
    return result


def _projection(session, result):
    return {
        "topic": TOPIC,
        "meaning": lesson(),
        "representation": {
            "state": "finite displacement sample vector",
            "unit": session.run["channels"]["q"]["unit"],
            "coordinate_frame": session.run["metadata"]["coordinate_frame"],
            "time_reference": session.run["metadata"]["provenance"].get("time_reference", "not_declared"),
            "sampling": session.run["metadata"]["provenance"].get("sampling", "not_declared"),
            "interval_s": deepcopy(result["interval_s"]),
            "measurement_uncertainty": "not_declared_synthetic_source",
        },
        "result": deepcopy(result),
        "execution": deepcopy(session.executions[result["execution_id"]]),
        "source": {"run_id": session.run["run_id"], "evidence_id": session.run["evidence_id"],
                   "provenance": deepcopy(session.run["metadata"]["provenance"])},
        "authority": {"numerical_check": "not_performed_by_inspection",
                      "physical_validation": "not_established", "state_admission": "not_performed"},
    }


def work(output_dir):
    output_dir = Path(output_dir)
    # A new directory reserves this occurrence and prevents silent replacement.
    output_dir.mkdir(parents=True, exist_ok=False)
    session = Session(make_demo_run(), output_dir)
    reply = _execute(session, {"channel": "q", "interval_s": [0.0, 12.0]})
    path = session.save_workspace(output_dir / "workspace.json")
    return {"topic": TOPIC, "workspace_file": str(path), **reply}


def inspect_workspace(path, result_id):
    # Session reopen validates all existing contracts and writes restored copies
    # only into scratch storage. The user's retained workspace is untouched.
    with tempfile.TemporaryDirectory(prefix="ciw-learn-inspect-") as directory:
        session = Session.from_workspace(Path(path), Path(directory))
        return _projection(session, _result(session, result_id))


def _compare_rms(session, result):
    start, end = result["interval_s"]
    values = [q for t, q in zip(session.run["time_s"], session.run["channels"]["q"]["values"])
              if start <= t < end]
    with localcontext() as context:
        context.prec = 80
        numbers = [Decimal.from_float(float(q)) for q in values]
        reference = (sum((q * q for q in numbers), Decimal(0)) / Decimal(len(numbers))).sqrt()
        actual = Decimal.from_float(float(result["data"]["rms"]))
        error = abs(actual - reference)
        tolerance = Decimal("1e-12") * max(abs(reference), Decimal(1))
        matched = error <= tolerance
        return {
            "kind": "educational_numerical_comparison",
            "claim": "retained displacement RMS agrees with Decimal evaluation of the selected binary64 samples",
            "result_id": result["result_id"], "execution_id": result["execution_id"],
            "evidence_id": session.run["evidence_id"],
            "sample_count": len(values), "unit": "m",
            "method": "Decimal, 80 digits; exact conversion of retained binary64 values",
            "reference_rms": str(reference), "absolute_error": str(error),
            "tolerance": str(tolerance), "tolerance_rule": "1e-12 * max(1 m, abs(reference))",
            "status": "matched" if matched else "mismatch",
            "verification_status": "not_verified",
            "limits": "Checks RMS only. No source/model validation, uncertainty calibration, formal proof or admission.",
        }


def verify_workspace(path, result_id):
    with tempfile.TemporaryDirectory(prefix="ciw-learn-check-") as directory:
        session = Session.from_workspace(Path(path), Path(directory))
        return _compare_rms(session, _result(session, result_id))


def replay_workspace(path, result_id, output_dir):
    output_dir = Path(output_dir)
    with tempfile.TemporaryDirectory(prefix="ciw-learn-replay-") as directory:
        original = Session.from_workspace(Path(path), Path(directory))
        prior = _result(original, result_id)
        output_dir.mkdir(parents=True, exist_ok=False)
        session = Session(original.run, output_dir)
        reply = _execute(session, deepcopy(prior["parameters"]))
        saved = session.save_workspace(output_dir / "workspace.json")
        report = {"topic": TOPIC, "workspace_file": str(saved),
                  "source_result_id": prior["result_id"],
                  "source_execution_id": prior["execution_id"], **reply}
        if reply["status"] == "completed":
            current = reply["result"]
            runtime_match = current["runtime"] == prior["runtime"]
            data_match = current["data"] == prior["data"]
            report["comparison"] = {
                "runtime_match": runtime_match, "data_match": data_match,
                "scope": "Exact equality of retained runtime declarations and statistics payloads",
                "verification_status": "not_verified",
            }
            report["status"] = "matched" if runtime_match and data_match else "mismatch"
        return report


def register_commands(commands):
    math = commands.add_parser("math", help="Learn and inspect mathematics through existing CIW operations")
    actions = math.add_subparsers(dest="math_command")
    for name in ("history", "learn", "explore"):
        action = actions.add_parser(name, help="Read the bounded lesson without running an operation")
        action.add_argument("topic", choices=[TOPIC])
        action.add_argument("--level", choices=LEVELS, default="structural")
        action.add_argument("--json", action="store_true", help="Print structured lesson content")
        if name == "explore":
            action.add_argument("--view", choices=["why", "derive", "bridge"], default="why")
    action = actions.add_parser("work", help="Run the lesson through statistics.v1 and retain a workspace")
    action.add_argument("topic", choices=[TOPIC])
    action.add_argument("--output-dir", type=Path, required=True, help="New directory for this occurrence")
    for name in ("inspect", "verify", "replay"):
        action = actions.add_parser(name, help={
            "inspect": "Reopen and explain a retained result without rerunning numerics",
            "verify": "Numerically cross-check RMS; never promote verification or admission",
            "replay": "Rerun the retained request as a new execution and compare",
        }[name])
        action.add_argument("path", type=Path)
        action.add_argument("--result-id", required=True)
        if name == "replay":
            action.add_argument("--output-dir", type=Path, required=True, help="New directory for the fresh occurrence")


def run_cli(args):
    action = args.math_command
    if action is None:
        value = catalog()
    elif action in {"history", "learn", "explore"}:
        value = lesson(args.topic, args.level)
        if action == "history":
            value = value["history"]
        elif action == "explore":
            value = {"why": value["phenomenon"]} if args.view == "why" else {args.view: value[args.view]}
        if not args.json:
            for name, content in value.items():
                print(name.upper().replace("_", " "))
                print("  " + (content if isinstance(content, str) else json.dumps(content, ensure_ascii=True)))
            return 0
    elif action == "work":
        value = work(args.output_dir)
    elif action == "inspect":
        value = inspect_workspace(args.path, args.result_id)
    elif action == "verify":
        value = verify_workspace(args.path, args.result_id)
    else:
        value = replay_workspace(args.path, args.result_id, args.output_dir)
    print(json.dumps(value, indent=2, allow_nan=False))
    return 3 if value.get("status") == "mismatch" else 2 if value.get("status") == "refused" else 0
