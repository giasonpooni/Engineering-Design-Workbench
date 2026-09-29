"""Compile and exercise actual generated language bindings against one FIR library.

Missing Julia or Rust is an incomplete qualification (exit 3), never a pass.
Python's exact rational oracle and Julia's 256-bit convolution are independent
checks; agreement among native callers alone tests interop, not independent math.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def sha(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def executable_path(command):
    # rustup and other multicall launchers dispatch using argv[0]. Preserve the
    # selected symlink name while hashing its actual bytes for the receipt.
    path=Path(shutil.which(str(command)) or command).absolute()
    if not path.is_file(): raise ValueError('Missing executable: '+str(command))
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',required=True)
    parser.add_argument('--rustc')
    parser.add_argument('--julia')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
    bridge=module(ROOT/'tools/instrument_bindings.py','bridge')
    spec=bridge.load(ROOT/'instruments/dsp/interface.json')
    generated=root/'bindings';generated.mkdir()
    for name,text in bridge.compile_interface(spec).items(): (generated/name).write_text(text,encoding='utf-8',newline='\n')
    logs=root/'logs';logs.mkdir(); commands=[]
    def execute(name,argv,timeout=90):
        executable=executable_path(argv[0])
        argv=[str(executable),*map(str,argv[1:])]
        commands.append({'name':name,'argv':argv,'executable_sha256':sha(executable)})
        (root/'commands.json').write_text(json.dumps(commands,indent=2))
        with (logs/(name+'.stdout')).open('wb') as out,(logs/(name+'.stderr')).open('wb') as err:
            subprocess.run(argv,cwd=root,check=True,timeout=timeout,stdout=out,stderr=err)
        return (logs/(name+'.stdout')).read_text()
    execute('compiler-version',[args.cxx,'--version'])
    library=root/'libscr_dsp.so'
    flags=['-std=c++17','-O2','-fno-fast-math','-ffp-contract=off']
    execute('kernel-build',[args.cxx,*flags,'-shared','-fPIC','-I',generated,ROOT/'instruments/dsp/fir.cpp','-o',library])
    api=module(generated/'scr_dsp.py','dsp_native')
    lib=api.Library(library,expected_sha256=sha(library))
    rng=random.Random(1792)
    cases=[]
    for k,n in [(1,9),(2,16),(3,16),(5,65),(64,255),(9,4096),(64,3)]:
        cases.append({'taps':[rng.uniform(-1,1) for _ in range(k)],'history':[rng.uniform(-2,2) for _ in range(k-1)],'samples':[rng.uniform(-2,2) for _ in range(n)],'split':max(1,n//3)})
    cases.extend([{'taps':[.5,.5],'history':[-1.],'samples':[1.,-1.]*8,'split':7},
                  {'taps':[1.,2.,-3.],'history':[0.,0.],'samples':[1.]+[0.]*15,'split':1}])
    corpus=root/'corpus.tsv'
    corpus.write_text('\n'.join(' '.join([str(len(c['taps'])),str(len(c['samples'])),str(c['split'])]+[format(v,'.17g') for v in c['taps']+c['history']+c['samples']]) for c in cases)+'\n')
    references=[];outputs={'python':[]};checks=[]
    for i,c in enumerate(cases):
        b,x,h=c['taps'],c['samples'],c['history'];k=len(b);extended=h+x
        y,z=lib.fir(b,x,h)
        yl,zl=lib.fir(b,x[:c['split']],h);yr,zr=lib.fir(b,x[c['split']:],zl)
        assert y==yl+yr and z==zr;checks.append(f'python:chunk:{i}')
        exact=[float(sum((Fraction(b[j])*Fraction(extended[k-1+n-j]) for j in range(k)),Fraction())) for n in range(len(x))]
        ref=exact+(extended[-(k-1):] if k>1 else [])
        references.append(ref);outputs['python'].append(y+z)
    assert outputs['python'][-2]==[0.]*16+[-1.]
    assert outputs['python'][-1][:4]==[1.,2.,-3.,0.]
    checks.extend(['nyquist-null','impulse-orientation'])
    (root/'cases.json').write_text(json.dumps(cases))
    (root/'rational-reference.json').write_text(json.dumps(references))
    execute('cpp-build',[args.cxx,*flags,'-I',generated,ROOT/'instruments/dsp/probe.cpp','-L',root,'-lscr_dsp','-Wl,-rpath,'+str(root),'-o',root/'cpp-probe'])
    outputs['cpp']=[list(map(float,l.split())) for l in execute('cpp-run',[root/'cpp-probe',corpus]).splitlines()]
    if args.rustc:
        execute('rust-version',[args.rustc,'--version'])
        shutil.copy2(ROOT/'instruments/dsp/probe.rs',generated/'probe.rs')
        execute('rust-build',[args.rustc,'--edition=2021',generated/'probe.rs','-L',root,'-C','link-arg=-Wl,-rpath,'+str(root),'-o',root/'rust-probe'])
        outputs['rust']=[list(map(float,l.split())) for l in execute('rust-run',[root/'rust-probe',corpus]).splitlines()]
    if args.julia:
        execute('julia-version',[args.julia,'--version'])
        outputs['julia-reference']=[list(map(float,l.split())) for l in execute('julia-native-and-reference',[args.julia,'--startup-file=no',ROOT/'instruments/dsp/probe.jl',generated,library,sha(library),corpus]).splitlines() if l.strip()]
    errors={}
    for language,rows in outputs.items():
        assert len(rows)==len(references)
        error=0.
        for i,(row,ref) in enumerate(zip(rows,references)):
            assert len(row)==len(ref)
            assert all(math.isfinite(v) and abs(v-r)<=1e-12+1e-12*abs(r) for v,r in zip(row,ref))
            error=max(error,max(abs(v-r) for v,r in zip(row,ref)))
            checks.append(f'{language}:reference:{i}')
        errors[language]=error
        (root/(language+'.json')).write_text(json.dumps(rows))
    (root/'commands.json').write_text(json.dumps(commands,indent=2))
    report={'schema':'scr.dsp-qualification.v1','status':'passed' if args.julia and args.rustc else 'incomplete',
            'source_class':'synthetic_numerical_corpus','cases':len(cases),'samples':sum(len(c['samples']) for c in cases),
            'contract_sha256':api.CONTRACT_SHA256,'library_sha256':sha(library),'language_max_absolute_error':errors,
            'tolerance':{'atol':1e-12,'rtol':1e-12},'checks':checks,
            'source_files':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'tools/instrument_bindings.py',*sorted((ROOT/'instruments/dsp').glob('*'))] if p.is_file()},
            'scope':'Linux binary64; native callers share one kernel; rational and Julia BigFloat references independent; no physical or real-time qualification'}
    (root/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 3

if __name__=='__main__': raise SystemExit(main())
