"""Turn the existing thermal observation demonstration into linked mathematical views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ciw.control_contracts import bytes_ref, save_new
from ciw.math_inspector import analyze
from ciw.math_visual import write_html


def run(evidence_dir: Path, output_dir: Path) -> dict:
    source = evidence_dir / 'posterior.json'
    with source.open('rb') as stream:
        raw = stream.read(65537)
    value = analyze(raw, expected_sha256=bytes_ref(raw))
    output_dir.mkdir(parents=True, exist_ok=False)
    save_new(output_dir / 'math-report.json', value)
    write_html(output_dir / 'inspector.html', value)
    summary = {'schema': value['schema'], 'status': 'created',
               'source_sha256': bytes_ref(raw), 'record_digest': value['record_digest'],
               'retained_execution_id': value['retained']['execution_id'],
               'samples': len(value['derived']),
               'active_dimensions': [r['whitened']['dimension'] for r in value['derived']],
               'whitened_nis': [r['whitened']['squared_norm'] for r in value['derived']],
               'conditioning_gain_nats': [r['conditioning_gain_nats'] for r in value['derived']],
               'authority': value['authority']}
    save_new(output_dir / 'demo-summary.json', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.evidence_dir, args.output_dir), indent=2))
