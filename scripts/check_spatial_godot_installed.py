"""Actual installed NET -> pinned GSC -> disconnected Godot qualification."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gsc-root', type=Path, required=True)
    parser.add_argument('--gsc-revision', required=True)
    parser.add_argument('--godot', type=Path, required=True)
    parser.add_argument('--godot-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    import ciw
    from ciw.core.identities import evidence_id
    from ciw.spatial_records import demo_run
    from ciw.spatial_workflow import create
    from ciw.spatial_godot import prepare, verify, check, encode, digest
    if Path(ciw.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise RuntimeError('Installed-wheel qualification cannot use checkout imports')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    initial, origin = demo_run()
    cases = {'mixed': initial}
    missing = deepcopy(initial)
    for channel in missing['channels'].values():
        channel['values'] = [None] * 6
    missing['evidence_id'] = evidence_id(missing)
    cases['all-missing'] = missing
    single = deepcopy(initial)
    single['metadata'].update(duration_s=1., sample_count=1)
    single['time_s'] = [0.]
    for channel in single['channels'].values():
        channel['values'] = channel['values'][:1]
    single['evidence_id'] = evidence_id(single)
    cases['single'] = single
    reports = {}
    for name, run in cases.items():
        root = output / name
        value = create(run, origin, root/'source', gsc_root=args.gsc_root,
                       revision=args.gsc_revision, python_executable=sys.executable)
        if value['status'] != 'completed':
            raise RuntimeError('Actual GSC execution refused: '+name)
        workspace = root/'source/workspace.json'
        before = digest(workspace.read_bytes())
        prepare(workspace, value['result']['result_id'], root/'viewer', expected_workspace_sha256=before)
        offline = verify(root/'viewer')
        headless = check(root/'viewer', args.godot, args.godot_sha256, root/'headless')
        rendered = check(root/'viewer', args.godot, args.godot_sha256, root/'rendered', render=True) if args.render else None
        if digest(workspace.read_bytes()) != before:
            raise RuntimeError('Source modified by consumer campaign')
        reports[name] = {'offline': offline, 'headless': headless, 'rendered': rendered}
    report = {'status': 'passed', 'installed_module': str(Path(ciw.__file__).resolve()),
              'python': sys.version, 'gsc_revision': args.gsc_revision, 'cases': reports,
              'scope': 'Synthetic retained sample inspection; not simulation, physics validation, or state admission.'}
    (output/'qualification.json').write_bytes(encode(report))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
