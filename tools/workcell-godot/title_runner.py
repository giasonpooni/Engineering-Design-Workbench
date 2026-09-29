"""Installed title recipe. Sources arrive as a frozen read-only capsule.

No title-owned source is copied into NET. This runner reuses the existing command
bounds and artifact framing; every scene executes in the existing Docker cell.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time

helpers=runpy.run_path('/recipe/runner.py')
read,execute=helpers['read'],helpers['execute']
WORK,INPUT=Path('/work'),Path('/input')
PROJECT='''config_version=5
[application]
config/name="1792 - Smith workcell inspection"
run/main_scene="res://smith.scn"
[display]
window/size/viewport_width=640
window/size/viewport_height=360
[rendering]
renderer/rendering_method="gl_compatibility"
'''


def engine(mode,*,pack=False):
    args=['/usr/local/bin/godot','--audio-driver','Dummy']
    if mode=='test':args+=['--display-driver','x11','--rendering-method','gl_compatibility','--resolution','640x360']
    else:args+=['--headless']
    if pack:
        empty=WORK/'empty';empty.mkdir()
        args+=['--path',str(empty),'--main-pack',str(WORK/'smith.pck')]
    else:args+=['--path',str(WORK)]
    args+=['--script','res://workcells/smith_probe.gd','--',mode]
    return execute(args,'smith-'+mode)


def main():
    if len(sys.argv)!=3 or sys.argv[2]!='1792.smith.v1':raise ValueError('Uninstalled title recipe')
    stage=sys.argv[1]
    config=json.loads(read(Path('/recipe/smith_recipe.json')))
    if stage not in config['outputs']:raise ValueError('Unknown title stage')
    request=json.loads(read(INPUT/'request.json'))
    names=config['sources']+([] if stage=='build' else config['outputs']['build'])
    original={name:read(INPUT/name) for name in names}
    for name,raw in original.items():
        path=WORK/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (WORK/'project.godot').write_text(PROJECT)
    os.environ['SMITH_REPORT']=str(WORK/'observations.json')
    os.environ['LIBGL_ALWAYS_SOFTWARE']='1';os.environ['LP_NUM_THREADS']='1'
    os.environ['MESA_SHADER_CACHE_DISABLE']='true'
    result={'schema':'ciw.workcell-process.v1','stage':stage,'nonce':request['nonce'],
            'outcome':'completed','diagnostic':'','files':{},'observations':None,'logs':''}
    logs=[];xvfb=None
    try:
        if stage=='build':logs.append(engine('build'))
        elif stage=='test':
            os.environ['DISPLAY']=':91'
            with (WORK/'xvfb.log').open('wb') as log:
                xvfb=subprocess.Popen(['/usr/bin/Xvfb',':91','-screen','0','640x360x24','-nolisten','tcp','-ac'],stdout=log,stderr=log)
                for _ in range(100):
                    if xvfb.poll() is not None:raise RuntimeError('Private software display failed')
                    if Path('/tmp/.X11-unix/X91').exists():break
                    time.sleep(.02)
                else:raise RuntimeError('Private software display unavailable')
                logs.append(engine('test'))
        else:
            logs.append(execute(['/usr/local/bin/godot','--headless','--path',str(WORK),'--script','/recipe/title_package.gd'],'smith-package'))
            logs.append(engine('smoke',pack=True))
        # Detect on-disk replacement of any input, including protected recipe source.
        for name,raw in original.items():
            if read(WORK/name)!=raw:raise ValueError('Candidate mutated frozen input: '+name)
        result['observations']=json.loads(read(WORK/'observations.json',65536))
        for name in config['outputs'][stage]:
            raw=read(WORK/name)
            result['files'][name]={'sha256':'sha256:'+hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                'base64_chunks':[base64.b64encode(raw[i:i+24000]).decode() for i in range(0,len(raw),24000)]}
    except Exception as exc:
        result.update(outcome='timeout' if isinstance(exc,subprocess.TimeoutExpired) else 'failed',
                      diagnostic=type(exc).__name__+': '+str(exc)[-8000:],files={},observations=None)
    finally:
        if xvfb is not None:
            xvfb.terminate()
            try:xvfb.wait(timeout=3)
            except subprocess.TimeoutExpired:xvfb.kill();xvfb.wait(timeout=3)
    result['logs']='\n'.join(logs)[-16000:]
    print(json.dumps(result,allow_nan=False,separators=(',',':')))


if __name__=='__main__':main()
