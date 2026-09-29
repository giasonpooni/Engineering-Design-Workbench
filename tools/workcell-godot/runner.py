"""Trusted recipe entrypoint. Candidate code runs only in the bounded container.

Returns bytes and observations, never a quality verdict. NET's fixed gates decide.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

WORK = Path('/work')
INPUT = Path('/input')
MAX_FILE = 512 * 1024
PROJECT = '''config_version=5
[application]
config/name="NET Workcell — compiled test slice"
run/main_scene="res://main.scn"
[rendering]
renderer/rendering_method="gl_compatibility"
environment/defaults/default_clear_color=Color(0.08, 0.1, 0.14, 1)
'''

def read(path, maximum=MAX_FILE):
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Not an ordinary artifact: ' + path.name)
    with path.open('rb') as f: data = f.read(maximum + 1)
    if len(data) > maximum: raise ValueError('Artifact exceeds byte bound')
    return data


def execute(args, label):
    log = WORK / (label + '.log')
    with log.open('wb') as out:
        process = subprocess.run(args, cwd=WORK, stdin=subprocess.DEVNULL, stdout=out,
                                 stderr=subprocess.STDOUT, timeout=20, check=False)
    text = read(log,65536).decode('utf-8','replace')
    if process.returncode or 'SCRIPT ERROR:' in text or '\nERROR:' in text:
        raise RuntimeError(label + ': exit ' + str(process.returncode) + '\n' + text[-8000:])
    return text


def engine(script, label):
    return execute(['/usr/local/bin/godot','--headless','--path',str(WORK),'--script',script],label)


def main():
    if len(sys.argv)==3:
        if sys.argv[2]!='1792.smith.v1': raise ValueError('Unknown installed recipe')
        import runpy
        runpy.run_path('/recipe/title_runner.py',run_name='__main__')
        return
    stage = sys.argv[1]
    if stage not in ('build','test','package'): raise ValueError('Unknown installed stage')
    request = json.loads(read(INPUT/'request.json'))
    names = ('compiler.py','motion.gd','spec.json') if stage == 'build' else ('mesh.json','motion.gd','prop.res','main.scn')
    for name in names: (WORK/name).write_bytes(read(INPUT/name))
    for name in ('driver.gd','smoke.gd'): (WORK/name).write_bytes(read(Path('/recipe')/name))
    (WORK/'project.godot').write_text(PROJECT)
    logs = []
    result = {'schema':'ciw.workcell-process.v1','stage':stage,'nonce':request['nonce'],
              'outcome':'completed','diagnostic':'','files':{},'observations':None}
    try:
        if stage == 'build':
            logs.append(execute(['/usr/bin/python3','-I','compiler.py'],'compiler'))
            logs.append(engine('/recipe/compile.gd','godot-compile'))
            outputs = ('mesh.json','motion.gd','prop.res','main.scn')
        elif stage == 'test':
            logs.append(engine('/recipe/probe.gd','godot-probe'))
            result['observations'] = json.loads(read(WORK/'observations.json',65536))
            outputs = ()
        else:
            logs.append(engine('/recipe/package.gd','godot-package'))
            # Fresh process loads only the packaged resources, not loose project files.
            empty = WORK/'empty'; empty.mkdir()
            logs.append(execute(['/usr/local/bin/godot','--headless','--path',str(empty),
                                 '--main-pack',str(WORK/'slice.pck'),'--script','res://smoke.gd'],'pack-smoke'))
            result['observations'] = json.loads(read(WORK/'pack-observations.json',65536))
            outputs = ('slice.pck',)
        for name in outputs:
            raw=read(WORK/name)
            result['files'][name]={'sha256':'sha256:'+hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                                  'base64_chunks':[base64.b64encode(raw[i:i+24000]).decode() for i in range(0,len(raw),24000)]}
    except Exception as exc:
        result['outcome']='timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'failed'
        result['files']={}
        result['observations']=None
        result['diagnostic']=type(exc).__name__+': '+str(exc)[-8000:]
    result['logs']='\n'.join(logs)[-16000:]
    # Fixed entrypoint is the only legitimate stdout writer.
    print(json.dumps(result,allow_nan=False,separators=(',',':')))

if __name__=='__main__': main()
