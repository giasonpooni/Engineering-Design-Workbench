"""Local, source-locked Godot backend comparison using original game tests.

The existing process supervisor supplies time/output limits. Its fixed Python shim
isolates user-data environment, without changing the caller's environment. Failed
suite logs remain observations and later suites still run. No migration or repair.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import platform
import sys
import tempfile

from . import foundry_packets as packets, foundry_physics_spec as s
from .foundry_asset_worker import write_snapshot, read_snapshot
from .control_contracts import bytes_ref, keys, number
from .interactive_simulation import file_sha, run_process
from . import foundry_physics_checks as checks


def parameters(p):
    import re
    keys(p,{'backend','replicate','nonce'})
    if type(p['backend']) is not str or p['backend'] not in s.BACKENDS or type(p['replicate']) is not int or p['replicate'] not in (1,2):
        raise ValueError('Only the two installed backends and declared replicates')
    if type(p['nonce']) is not str or re.fullmatch('[0-9a-f]{32}',p['nonce']) is None:raise ValueError('invalid occurrence nonce')


def scripts():
    return {'backend-observer.gd':s.OBSERVER.encode(),'backend-probe.gd':s.PROBE.encode(),
            'launch.py':Path(__file__).with_name('foundry_physics_launch.py').read_bytes()}


def validate_capture(data, objective, p):
    parameters(p)
    if objective!={'schema':'ciw.physics-backend-objective.v1','profile':s.PROFILE,'source_inventory_id':s.INVENTORY}:
        raise ValueError('wrong physics objective')
    if data['parameters']!=p or data['scripts']!={k:bytes_ref(v) for k,v in scripts().items()}:
        raise ValueError('changed capture request or fixed observation script')
    # Structurally valid failed candidates remain retained for the acceptance gate.
    checks.evaluate_data(data)


class PhysicsBinding:
    def __init__(self, source_root, executable, expected_sha256):
        if sys.platform!='linux':raise ValueError('Native profile is Linux-qualified only; Python contracts are portable')
        if expected_sha256!=s.ENGINE:raise ValueError('Unqualified Godot build; this profile requires its exact tested binary')
        self.executable=Path(executable).expanduser().resolve(strict=True)
        if file_sha(self.executable)!=expected_sha256:raise ValueError('Godot binary digest mismatch')
        self.inventory=packets.inventory(source_root)
        if self.inventory['inventory_id']!=s.INVENTORY:raise ValueError('Source drift: require the exact accepted-bench source revision')
        self.raws=read_snapshot(source_root,self.inventory)
        self.fixed=scripts()
        self.identity={'provider':'ciw.foundry.godot-backend-comparison','execution_mode':'isolated_native_matrix',
            'executable_sha256':expected_sha256,'source_inventory_id':s.INVENTORY,
            'scripts':{k:bytes_ref(v) for k,v in self.fixed.items()},
            'host_sha256':bytes_ref(Path(__file__).read_bytes()),'python':sys.version,
            'python_sha256':file_sha(Path(sys.executable).resolve()),'platform':platform.platform(),
            'scope':'operator-trusted runtime, full pinned game source; not an OS/network sandbox'}

    def runtime_identity(self):
        if file_sha(self.executable)!=s.ENGINE or file_sha(Path(sys.executable).resolve())!=self.identity['python_sha256']:
            raise ValueError('Runtime changed after binding')
        if {p:bytes_ref(v) for p,v in self.raws.items()}!={p:v['sha256'] for p,v in self.inventory['files'].items()}:
            raise ValueError('Bound game snapshot changed')
        if scripts()!=self.fixed:raise ValueError('Fixed observer or launcher changed')
        return deepcopy(self.identity)

    def invoke(self, objective, params):
        from .adapters.protocol import AdapterRefusal
        parameters(params);self.runtime_identity()
        try:
            return self._invoke(objective,params)
        except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
            raise AdapterRefusal('backend_comparison_capture_refused',str(exc)[:4096]) from exc

    def _invoke(self, objective, p):
        with tempfile.TemporaryDirectory(prefix='net-physics-') as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            write_snapshot(source,self.inventory,self.raws)
            project=source/'game';home=root/'home';home.mkdir()
            # No inherited autoloads, plugin execution or feature backend overrides
            # are introduced: the entire source is already pinned to one known tree.
            (project/'override.cfg').write_bytes(s.override(p['backend']))
            (project/'backend-observer.gd').write_bytes(self.fixed['backend-observer.gd'])
            (project/'backend-probe.gd').write_bytes(self.fixed['backend-probe.gd'])
            (root/'launch.py').write_bytes(self.fixed['launch.py'])
            user=home/'data/godot/app_userdata/1792'
            events={};calls=0
            def call(label,command, *, observe=True, watched=()):
                nonlocal calls
                launch=root/('process-'+label);launch.mkdir()
                if observe:
                    (project/'backend-request.json').write_text(json.dumps(checks.request(p,label)))
                    (user/'backend-observer.json').unlink(missing_ok=True)
                # run_process is unchanged. A nonzero suite exit is retained with
                # its diagnostic; it is not converted into a missing result or PASS.
                try: diagnostic=run_process(command,launch,watched=watched,timeout=120)
                except RuntimeError as exc:
                    diagnostic=json.loads(str(exc))
                calls+=1
                logs={name:checks.blob((launch/(name+'.log')).read_bytes()) for name in ('stdout','stderr')}
                record={**logs,'returncode':diagnostic['returncode'],'failure':diagnostic['failure'],
                    'elapsed_wall_s':diagnostic['elapsed_wall_s'],'observer':None}
                path=user/'backend-observer.json'
                if observe and path.is_file():
                    record['observer']=checks.blob(path.read_bytes())
                    if Path(json.loads(checks.read_blob(record['observer'],65536))['user_data_dir']).resolve()!=user.resolve():
                        raise ValueError('Engine user data was not isolated inside the disposable run')
                # Logs are bounded before committing a payload; oversized diagnostics
                # retain a refusal rather than truncating evidence and claiming success.
                checks.process_checks(record)
                events[label]=record
                return record
            prefix=[sys.executable,str(root/'launch.py'),str(home),str(self.executable),'--headless','--path',str(project)]
            imp=call('import',prefix+['--editor','--import'],observe=False)
            if imp['returncode']==0:
                call('probe',prefix+['--fixed-fps','60','--script','res://backend-probe.gd'],watched=[user/'backend-probe.json'])
                for label,script,_,_ in s.SUITES:
                    call(label,prefix+['--fixed-fps','60','--script','res://tests/'+script],watched=[user/'bench-integration-gameplay.json'])
                # Run the game's own existing checker intact, in a separate Python
                # process. Its success never substitutes for NET's observation gate.
                call('recheck',[sys.executable,str(source/'tools/check_bench_artifact.py'),
                    '--evidence',str(user/'bench-integration-gameplay.json')],observe=False)
            for label in ['probe']+[r[0] for r in s.SUITES]+['recheck']:events.setdefault(label,None)
            def maybe(name,limit):
                path=user/name
                if not path.is_file():return None
                if path.stat().st_size>limit:raise ValueError('native output exceeds bound')
                return checks.blob(path.read_bytes())
            preserved=all((source/name).read_bytes()==raw for name,raw in self.raws.items())
            preserved &= ((project/'override.cfg').read_bytes()==s.override(p['backend']) and
                (project/'backend-observer.gd').read_bytes()==self.fixed['backend-observer.gd'] and
                (project/'backend-probe.gd').read_bytes()==self.fixed['backend-probe.gd'])
            recheck=events.get('recheck')
            data={'schema':'ciw.physics-backend-capture.v1','parameters':deepcopy(p),
                'source_inventory_id':s.INVENTORY,'engine_sha256':s.ENGINE,
                'override':checks.blob(s.override(p['backend'])),
                'scripts':{k:bytes_ref(v) for k,v in self.fixed.items()},'processes':events,
                'probe':maybe('backend-probe.json',16384),'gameplay':maybe('bench-integration-gameplay.json',2*1024*1024),
                'game_recheck':recheck['stdout'] if recheck is not None and recheck['returncode']==0 else None,
                'source_preserved':bool(preserved),'process_calls':calls,
                'elapsed_wall_s':sum(v['elapsed_wall_s'] for v in events.values() if v is not None)}
            if len(json.dumps(data,ensure_ascii=False).encode())>s.MAX_CAPTURE:raise ValueError('capture exceeds retained payload budget')
            validate_capture(data,objective,p);self.runtime_identity()
            return data
