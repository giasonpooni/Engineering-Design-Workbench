"""Inspect native thermal covariance contraction; do not rerun or reselect sensors."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from ciw.control_contracts import bytes_ref, save_new
from ciw.math_inspector import analyze_information, validate_report
from ciw.math_visual import write_html


def run(evidence_dir: Path, output_dir: Path) -> dict:
    raw = (evidence_dir / 'posterior.json').read_bytes()
    report = analyze_information(raw, expected_sha256=bytes_ref(raw))
    validate_report(report)
    output_dir.mkdir(parents=True, exist_ok=False)
    save_new(output_dir / 'information-report.json', report)
    write_html(output_dir / 'inspector.html', report)
    summary = {'schema': report['schema'], 'record_digest': report['record_digest'],
        'execution_id': report['retained']['execution_id'],
        'selected_mask': report['retained']['selection']['selected_mask'],
        'tick_variance_ratios': [g['variance_ratios'] for g in report['information']['rows']],
        'candidate_variance_ratios': {str(x['mask']): x['geometry']['variance_ratios'] for x in report['information']['forecast']},
        'scope': report['information']['scope'], 'authority': report['authority']}
    save_new(output_dir / 'demo-summary.json', summary)
    return summary


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a=p.parse_args()
    print(json.dumps(run(a.evidence_dir,a.output_dir),indent=2))
