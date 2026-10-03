"""Qualification command: real installed CIW, external GSC and OpenUSD SDK."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--gsc-root',type=Path,required=True)
    parser.add_argument('--gsc-revision',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    import ciw
    from ciw.spatial_records import demo_run
    from ciw.spatial_workflow import create, inspect
    from ciw.spatial_scene import export, verify_export
    checkout=Path(__file__).resolve().parents[1]
    if Path(ciw.__file__).resolve().is_relative_to(checkout):
        raise RuntimeError('Qualification requires installed CIW, not checkout imports')
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
    run,origin=demo_run()
    result=create(run,origin,root/'execution',gsc_root=args.gsc_root,
                  revision=args.gsc_revision,python_executable=sys.executable)
    if result['status']!='completed':
        raise RuntimeError('Native GSC execution did not complete')
    payload=result['result'];data=payload['data'];source=root/'execution/workspace.json'
    before=sha256(source.read_bytes()).hexdigest()
    if data['positions_enu_m'][3] is not None or payload['verification_status']!='not_verified':
        raise RuntimeError('Missingness or verification boundary failed')
    if inspect(source)['provider_execution']!='not_performed':
        raise RuntimeError('Inspect unexpectedly executed a provider')
    exported=export(source,payload['result_id'],root/'scene',with_usd=True)
    checked=verify_export(root/'scene')
    if (exported['usd']['status']!='sdk_roundtrip_matched'
            or checked['artifacts_checked']!=4
            or sha256(source.read_bytes()).hexdigest()!=before):
        raise RuntimeError('Export qualification failed')
    report={'status':'passed','ciw_module':str(Path(ciw.__file__).resolve()),
        'gsc_revision':args.gsc_revision,'python':sys.version,
        'result_id':payload['result_id'],'execution_id':payload['execution_id'],
        'source_evidence_id':payload['evidence_id'], 'runtime':data['runtime'],
        'export':exported,'retained_integrity_check':checked,
        'limits':'Synthetic coordinate transformation; no calibration, game runtime, or state admission.'}
    (root/'qualification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
