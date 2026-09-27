"""Independent exact-reference and wire-profile tests; no mock proof acceptance."""
from copy import deepcopy
from itertools import combinations, permutations
import json
import os
from pathlib import Path
import random
import subprocess

import pytest

from ciw.proof_f2 import SCHEMA, PROFILE, validate, encode, decode, reference, output_bytes, prepare


def complex_from_facets(n, facets, candidate=None):
    # This is an explicit fixture construction, never a checker repair operation.
    faces = {(v,) for v in range(n)}
    for facet in facets:
        for size in range(1, len(facet) + 1):
            faces.update(combinations(sorted(facet), size))
    simplices = [list(s) for s in sorted(faces, key=lambda s: (len(s), s))]
    return {"schema": SCHEMA, "profile": PROFILE, "coefficient_field": "F2", "homology": "ordinary",
            "vertex_count": n, "simplices": simplices,
            "candidate_betti": candidate if candidate is not None else [0] * len(simplices[-1])}


RP2 = [(0,1,2),(0,1,3),(0,2,4),(0,3,5),(0,4,5),(1,2,5),(1,3,4),(1,4,5),(2,3,4),(2,3,5)]
CASES = [
    (1, [], [1]), (2, [], [2]), (2, [(0,1)], [1,0]),
    (3, [(0,1),(0,2),(1,2)], [1,1]), (3, [(0,1,2)], [1,0,0]),
    (4, list(combinations(range(4),3)), [1,0,1]), (4, [(0,1,2,3)], [1,0,0,0]),
    (6, RP2, [1,1,1]), (6, [(0,1,2),(3,4,5)], [2,0,0]),
    (64, [], [64]),
    (9, list(combinations(range(9),4)), [1,0,0,70]),
    (23, list(combinations(range(23),2))[:232] + [(14,15,16)], [1,209,0]),
]


@pytest.mark.parametrize("n,facets,betti", CASES)
def test_known_ordinary_f2_examples(n, facets, betti):
    source = complex_from_facets(n,facets,betti)
    assert reference(source)["betti"] == betti
    assert reference(source)["candidate_matches"] is True
    assert decode(encode(source)) == source
    report = prepare(json.dumps(source).encode())
    assert report["status"] == "prepared_not_proved"
    assert report["cryptographic_verification"] == "not_performed"
    assert report["guest_registration"] == "pending"
    assert report["expected_output"] == output_bytes(reference(source)).hex()


@pytest.mark.parametrize("field,value", [
    ("schema","other"),("profile","other"),("homology","reduced"),("coefficient_field","Q"),
    ("vertex_count",True),("vertex_count",0),("vertex_count",65),("vertex_count",2.0),
    ("simplices",[]),("simplices",[[0],[0]]),("simplices",[[1],[0]]),
    ("simplices",[[0],[1],[0,0]]),("simplices",[[0],[1],[1,0]]),
    ("simplices",[[0],[1],[0,2]]),("simplices",[[0],[1],[True]]),
    ("candidate_betti",[True]),("candidate_betti",[1.0]),("candidate_betti",[-1]),
    ("candidate_betti",[257]),("candidate_betti",[2,0]),
])
def test_rejects_malformed_inputs(field,value):
    source=complex_from_facets(2,[],[2]); source[field]=value
    with pytest.raises(ValueError): encode(source)


def test_no_silent_face_completion():
    source=complex_from_facets(3,[(0,1,2)],[1,0,0]); source["simplices"].remove([1,2])
    with pytest.raises(ValueError,match="face"): encode(source)


def test_rejects_missing_singleton():
    source=complex_from_facets(2,[],[2]);source["simplices"].pop()
    with pytest.raises(ValueError): validate(source)


def test_candidate_mismatch_has_no_preparation():
    source=complex_from_facets(3,[(0,1),(0,2),(1,2)],[1,0])
    assert reference(source)["candidate_matches"] is False
    with pytest.raises(ValueError,match="disagrees"): prepare(json.dumps(source).encode())


def test_limits_and_no_mutation():
    source=complex_from_facets(10,list(combinations(range(10),4)))
    with pytest.raises(ValueError): encode(source)
    source=complex_from_facets(5,[(0,1,2,3,4)])
    with pytest.raises(ValueError): encode(source)
    source=complex_from_facets(3,[(0,1,2)],[1,0,0]); saved=deepcopy(source)
    reference(source);encode(source);assert source==saved


def test_every_truncation_trailing_bytes_and_policy_byte():
    raw=encode(complex_from_facets(3,[(0,1,2)],[1,0,0]))
    for n in range(len(raw)):
        with pytest.raises(ValueError): decode(raw[:n])
    with pytest.raises(ValueError): decode(raw+b'\0')
    for i in range(8):
        altered=bytearray(raw);altered[i]^=1
        with pytest.raises(ValueError): decode(bytes(altered))


@pytest.mark.parametrize("raw",[b'{}',b'null',b'[]',b'{"x":1,"x":1}',b' ' * 32769])
def test_bad_json_refuses(raw):
    with pytest.raises(ValueError): prepare(raw)


def test_relabelling_is_an_explicit_transformation():
    source=complex_from_facets(4,[(0,1),(1,2),(2,3),(0,3)],[1,1])
    original=encode(source)
    for perm in permutations(range(4)):
        other=deepcopy(source)
        other["simplices"] = sorted([sorted(perm[v] for v in s) for s in source["simplices"]],key=lambda s:(len(s),s))
        assert reference(other)["betti"] == [1,1]
        assert decode(encode(other))==other
    assert encode(source)==original


def full_vertex_complexes(n):
    optional=[s for k in range(2,n+1) for s in combinations(range(n),k)]
    for mask in range(1 << len(optional)):
        faces={(v,) for v in range(n)} | {s for i,s in enumerate(optional) if mask & (1 << i)}
        if any(s[:i]+s[i+1:] not in faces for s in faces if len(s)>1 for i in range(len(s))):
            continue
        source=complex_from_facets(n,[])
        source["simplices"]=[list(s) for s in sorted(faces,key=lambda s:(len(s),s))]
        source["candidate_betti"]=[0]*len(source["simplices"][-1])
        source["candidate_betti"]=reference(source)["betti"]
        yield source


def test_exhaustive_small_complexes_euler_and_component_oracles():
    seen=0
    for n in range(1,5):
        for source in full_vertex_complexes(n):
            result=reference(source); seen+=1
            assert sum((-1)**k*v for k,v in enumerate(result["counts"])) == sum((-1)**k*v for k,v in enumerate(result["betti"]))
            # Independent graph reachability oracle for ordinary beta_0.
            groups=[{v} for v in range(n)]
            for s in source["simplices"]:
                if len(s)!=2:continue
                touched=[g for g in groups if set(s)&g]
                joined=set().union(*touched);groups=[g for g in groups if g not in touched]+[joined]
            assert result["betti"][0]==len(groups)
            assert decode(encode(source))==source
    assert seen==126


def test_rp2_detects_coefficient_field_confusion():
    source=complex_from_facets(6,RP2,[1,1,1]);result=reference(source)
    assert result["counts"]==[6,15,10]
    assert result["ranks"]==[0,5,9]
    source["candidate_betti"]=[1,0,0]
    assert reference(source)["candidate_matches"] is False


def test_native_rust_differential_corpus():
    executable=os.environ.get("CIW_F2_CHECKER")
    if not executable:
        pytest.skip("Independent Rust checker executable is not bound; no native claim")
    assert Path(executable).is_file()
    cases=[complex_from_facets(*args) for args in CASES]
    cases += [c for n in range(1,5) for c in full_vertex_complexes(n)]
    rng=random.Random(20260927)
    for _ in range(48):
        n=rng.randint(4,8)
        facets=[tuple(sorted(rng.sample(range(n),rng.randint(1,4)))) for _ in range(12)]
        value=complex_from_facets(n,facets);value["candidate_betti"]=reference(value)["betti"];cases.append(value)
    for value in cases:
        raw=encode(value)
        proc=subprocess.run([executable],input=raw,capture_output=True,timeout=10,check=False)
        assert proc.returncode==0,proc.stderr
        assert proc.stdout==output_bytes(reference(value))
        bad=deepcopy(value);bad["candidate_betti"][0]=(bad["candidate_betti"][0]+1)%257
        rejected=subprocess.run([executable],input=encode(bad),capture_output=True,timeout=10,check=False)
        assert rejected.returncode==7 and rejected.stdout==b""
    raw=encode(cases[3])
    malformed=[raw[:i] for i in range(len(raw))]+[raw+b'\0',b'',b'NSF2'+b'\0'*20]
    for i in range(8):
        x=bytearray(raw);x[i]^=1;malformed.append(bytes(x))
    for payload in malformed:
        proc=subprocess.run([executable],input=payload,capture_output=True,timeout=10,check=False)
        assert proc.returncode!=0 and proc.stdout==b""
