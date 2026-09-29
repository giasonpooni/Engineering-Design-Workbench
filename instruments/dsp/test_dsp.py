"""Native tests; no simulated engine or hidden fallback."""
import ctypes as C
from copy import deepcopy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bridge=module(ROOT/'tools/instrument_bindings.py','bridge')
SPEC=bridge.load(ROOT/'instruments/dsp/interface.json')

@pytest.fixture(scope='session')
def native(tmp_path_factory):
    root=tmp_path_factory.mktemp('dsp-native')
    for name,text in bridge.compile_interface(SPEC).items(): (root/name).write_text(text)
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-O2','-fno-fast-math','-ffp-contract=off','-I',str(root),str(ROOT/'instruments/dsp/fir.cpp'),'-o',str(root/'libscr_dsp.so')],check=True,timeout=30)
    digest='sha256:'+hashlib.sha256((root/'libscr_dsp.so').read_bytes()).hexdigest()
    api=module(root/'scr_dsp.py','native_dsp')
    return root,api,api.Library(root/'libscr_dsp.so',expected_sha256=digest)

@pytest.mark.parametrize('k,n',[(1,2),(2,15),(3,16),(7,3),(64,129),(64,4096)])
def test_chunk_partition_and_fraction_reference(native,k,n):
    rng=random.Random(4831+k+n)
    b=[rng.uniform(-1,1) for _ in range(k)];h=[rng.uniform(-2,2) for _ in range(k-1)];x=[rng.uniform(-2,2) for _ in range(n)]
    _,_,lib=native;y,z=lib.fir(b,x,h); ext=h+x
    ref=[float(sum((Fraction(b[j])*Fraction(ext[k-1+i-j]) for j in range(k)),Fraction(0))) for i in range(n)]
    assert y==pytest.approx(ref,rel=1e-12,abs=1e-12)
    outputs=[];state=h[:];i=0
    while i<n:
        size=min(n-i,rng.randint(1,23));chunk,state=lib.fir(b,x[i:i+size],state);outputs+=chunk;i+=size
    assert outputs==y and state==z
    assert z==(ext[-(k-1):] if k>1 else [])


def test_impulse_dc_nyquist_and_asymmetric_orientation(native):
    lib=native[2]
    assert lib.fir([1.,2.,-3.],[1.,0.,0.,0.],[0.,0.])[0]==[1.,2.,-3.,0.]
    assert lib.fir([.5,.5],[1.]*8,[1.])[0]==[1.]*8
    assert lib.fir([.5,.5],[1.,-1.]*4,[-1.])[0]==[0.]*8
    assert lib.fir([1.,2.,3.],[10.],[4.,5.])==([32.],[5.,10.])

@pytest.mark.parametrize('b,x,h', [([], [1.], []),([1.],[],[]),([1.],[float('nan')],[]),([float('inf')],[1.],[]),([1.,2.],[1.],[float('nan')]),([1.,2.],[1.],[]),([True],[1.],[]),([1.],[None],[]),([1.]*65,[1.],[0.]*64),([1.],[1.]*4097,[])])
def test_invalid_inputs(native,b,x,h):
    with pytest.raises((ValueError,TypeError)): native[2].fir(b,x,h)


def test_raw_atomic_overflow_null_lengths_and_alias(native):
    lib=native[2].lib;fn=lib.scr_dsp_fir_v1
    arr=lambda xs:(C.c_double*len(xs))(*xs)
    b=arr([1e308,1e308]);x=arr([1.,2.]);h=arr([0.]);out=arr([91.,92.]);z=arr([93.])
    assert fn(b,2,x,2,h,1,out,2,z,1)==4
    assert list(out)==[91.,92.] and list(z)==[93.]
    assert fn(b,2,x,2,h,1,out,1,z,1)==2
    assert fn(None,2,x,2,h,1,out,2,z,1)==1
    b=arr([.5,.5]); assert fn(b,2,x,2,h,1,x,2,h,1)==0
    assert list(x)==[.5,1.5] and list(h)==[2.]
    assert fn(b,2,x,2,h,1,out,2,out,1)==5


def test_explicit_empty_history_for_one_tap(native):
    assert native[2].fir([2.],[1.,3.],[])==([2.,6.],[])


def test_interface_codegen_is_reproducible_and_has_no_math():
    a=bridge.compile_interface(SPEC);b=bridge.compile_interface(deepcopy(SPEC));assert a==b
    assert set(a)=={'scr_dsp.h','scr_dsp.hpp','scr_dsp.py','scr_dsp.rs','scr_dsp.jl','interface.canonical.json','bindings.json'}
    for suffix in ['py','rs','jl','hpp']: assert 'taps[k]' not in a['scr_dsp.'+suffix]

@pytest.mark.parametrize('fault',['unknown_type','unknown_field','path_name','reserved_name','duplicate_op','duplicate_input','invalid_length','bool_bound','too_large','bad_relation','alias_name','bad_version'])
def test_codegen_refuses_unqualified_contracts(fault):
    spec=deepcopy(SPEC);fn=spec['functions'][0]
    if fault=='unknown_type': fn['inputs'][0]['type']='strided_tensor'
    elif fault=='unknown_field': spec['shell']='anything'
    elif fault=='path_name': spec['namespace']='../native'
    elif fault=='reserved_name': fn['inputs'][0]['name']='return'
    elif fault=='duplicate_op': spec['functions']*=2
    elif fault=='duplicate_input': fn['inputs'].append(deepcopy(fn['inputs'][0]))
    elif fault=='invalid_length': fn['inputs'][0]['min']=-1
    elif fault=='bool_bound': fn['inputs'][0]['max']=True
    elif fault=='too_large': fn['inputs'][0]['max']=65537
    elif fault=='bad_relation': fn['outputs'][0]['length_from']='unknown'
    elif fault=='alias_name': fn['outputs'][0]['name']='taps'
    else: spec['abi_version']=True
    with pytest.raises(ValueError): bridge.compile_interface(spec)


def test_binary_pin_and_contract_drift(native,tmp_path):
    root,api,lib=native
    with pytest.raises(ValueError):api.Library(root/'libscr_dsp.so',expected_sha256='sha256:'+'0'*64)
    # A wrong ABI/contract is tested against an actual separately built library.
    source=tmp_path/'wrong.cpp';source.write_text('extern "C" unsigned int scr_dsp_abi_version(){return 999;}\nextern "C" const char* scr_dsp_contract_sha256(){return "wrong";}\n')
    subprocess.run(['g++','-shared','-fPIC',str(source),'-o',str(tmp_path/'wrong.so')],check=True,timeout=30)
    digest='sha256:'+hashlib.sha256((tmp_path/'wrong.so').read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='interface'):api.Library(tmp_path/'wrong.so',expected_sha256=digest)


def test_multiple_generated_operations_share_the_same_interface():
    spec=deepcopy(SPEC);op=deepcopy(spec['functions'][0]);op['name']='condition';spec['functions'].append(op)
    compiled=bridge.compile_interface(spec)
    assert 'def condition(' in compiled['scr_dsp.py'] and 'scr_dsp_condition_v1' in compiled['scr_dsp.h']
    compile(compiled['scr_dsp.py'],'generated','exec')


def test_concurrent_calls_have_no_shared_filter_state(native):
    from concurrent.futures import ThreadPoolExecutor
    lib=native[2]
    def run(i):return lib.fir([.25,.5,.25],[float(i)]*31,[float(i),float(i)])
    with ThreadPoolExecutor(max_workers=4) as executor: results=list(executor.map(run,range(16)))
    for i,(y,z) in enumerate(results): assert y==[float(i)]*31 and z==[float(i)]*2


def test_nondefault_rounding_refuses_without_writing(native):
    process=C.CDLL(None)
    old=process.fegetround()
    try:
        assert process.fesetround(0x800)==0  # FE_UPWARD in qualified Linux profile.
        with pytest.raises(ValueError,match='refused: 6'):native[2].fir([1.],[1.],[])
    finally: assert process.fesetround(old)==0


def test_qualification_preserves_multicall_launcher_name(tmp_path):
    qualify=module(ROOT/'instruments/dsp/qualify.py','qualify')
    target=tmp_path/'launcher';target.write_text('#!/bin/sh\nprintf "%s" "$0"\n');target.chmod(0o755)
    alias=tmp_path/'compiler';alias.symlink_to(target)
    selected=qualify.executable_path(alias)
    assert selected==alias and selected!=target
    assert subprocess.check_output([str(selected)],text=True)==str(alias)
