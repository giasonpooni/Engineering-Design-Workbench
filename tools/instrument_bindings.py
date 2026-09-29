"""Compile a bounded buffer interface into C/C++/Python/Rust/Julia bindings.

This compiler translates contracts, not arbitrary programs or numerical kernels.
Only binary64 buffers with explicit lengths, caller-owned results and int32 status
are supported. Unknown fields/types, unsafe names and unbounded buffers refuse.
No generated module loads a library at import time. No input chooses code to run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "scr.native-buffer-interface.v1"
RESERVED = set("lib handle status abi contract resolved path digest asm auto bool break case catch char class const continue crate def delete do double else enum except extern false final finally float fn for from function global goto if impl import in inline int let long loop match mod module mutable namespace new nil none noexcept null nullptr operator output_len pass private protected pub public ref register return self short signed sizeof static str struct super switch template this throw trait true try type typedef typename union unsafe unsigned use using var virtual void volatile where while with yield".split())


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("Unexpected or missing contract fields")


def name(value):
    if type(value) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", value) or value in RESERVED or value.endswith("_len"):
        raise ValueError("Unsafe or reserved native identifier")
    return value


def validate(value):
    keys(value, {"schema", "namespace", "abi_version", "semantics", "functions"})
    if value["schema"] != SCHEMA or type(value["abi_version"]) is not int or not 1 <= value["abi_version"] <= 999:
        raise ValueError("Unsupported interface/ABI")
    name(value["namespace"])
    if type(value["semantics"]) is not str or not 1 <= len(value["semantics"]) <= 4096:
        raise ValueError("Require explicit bounded numerical semantics")
    if type(value["functions"]) is not list or not 1 <= len(value["functions"]) <= 16:
        raise ValueError("Require 1..16 operations")
    seen = set()
    for fn in value["functions"]:
        keys(fn, {"name", "inputs", "outputs"}); name(fn["name"])
        if fn["name"] in seen or fn["name"] in {"abi", "contract", "bind", "close"}:
            raise ValueError("Duplicate or reserved operation")
        seen.add(fn["name"])
        for kind in ("inputs", "outputs"):
            if type(fn[kind]) is not list or not 1 <= len(fn[kind]) <= 8:
                raise ValueError("Require bounded buffer ports")
        ports = set()
        for port in fn["inputs"]:
            keys(port, {"name", "type", "min", "max"}); name(port["name"])
            if port["type"] != "f64_buffer" or type(port["min"]) is not int or type(port["max"]) is not int or not 0 <= port["min"] <= port["max"] <= 65536:
                raise ValueError("Unsupported buffer type or bounds")
            if port["name"] in ports: raise ValueError("Duplicate port")
            ports.add(port["name"])
        inputs = set(ports)
        for port in fn["outputs"]:
            keys(port, {"name", "type", "length_from"}); name(port["name"])
            if port["type"] != "f64_buffer" or port["length_from"] not in inputs or port["name"] in ports:
                raise ValueError("Invalid result length relation")
            ports.add(port["name"])
    return value


def compile_interface(value):
    """Return generated UTF-8 files, without executing providers or writing files."""
    validate(value)
    ns, version = value["namespace"], value["abi_version"]
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    prefix = ns.upper()
    c = [f"/* Generated interface only. Contract SHA256: {digest} */", "#pragma once", "#include <stddef.h>", "#include <stdint.h>", f'#define {prefix}_CONTRACT_SHA256 "{digest}"', f"#define {prefix}_ABI_VERSION {version}u", '#ifdef __cplusplus\nextern "C" {\n#endif', f"uint32_t {ns}_abi_version(void);", f"const char* {ns}_contract_sha256(void);"]
    cpp = [f'#pragma once\n#include "{ns}.h"', '#include <vector>\n#include <tuple>\n#include <stdexcept>\n#include <string>', f"namespace {ns} {{"]
    py = [f'"""Generated buffer bindings. No DSP mathematics. Contract: {digest}."""', 'import ctypes as C\nimport hashlib\nfrom pathlib import Path', f'CONTRACT_SHA256 = "sha256:{digest}"', f'ABI_VERSION = {version}', 'class Library:', '    def __init__(self, path, *, expected_sha256):', '        self.path = Path(path).expanduser().resolve(strict=True)', '        if "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest() != expected_sha256:', '            raise ValueError("Native library digest mismatch")', '        self.digest = expected_sha256', '        self.lib = C.CDLL(str(self.path))', f'        self.lib.{ns}_abi_version.argtypes = []', f'        self.lib.{ns}_abi_version.restype = C.c_uint32', f'        self.lib.{ns}_contract_sha256.argtypes = []', f'        self.lib.{ns}_contract_sha256.restype = C.c_char_p', f'        if self.lib.{ns}_abi_version() != ABI_VERSION or self.lib.{ns}_contract_sha256().decode("ascii") != CONTRACT_SHA256[7:]:', '            raise ValueError("Native interface mismatch")']
    rs = [f'// Generated buffer interface. Contract SHA256: {digest}', f'#[link(name="{ns}")]\nunsafe extern "C" {{', f'    fn {ns}_abi_version() -> u32;', f'    fn {ns}_contract_sha256() -> *const std::ffi::c_char;']
    jl = [f'# Generated interface. Contract SHA256: {digest}', f'module {ns.title().replace("_", "")}\nusing Libdl, SHA', 'mutable struct Library\n    handle::Ptr{Cvoid}\nend', 'function Library(path::AbstractString; expected_sha256::AbstractString)', '    resolved = realpath(path)', '    "sha256:" * bytes2hex(sha256(read(resolved))) == expected_sha256 || error("Native library digest mismatch")', '    handle = Libdl.dlopen(resolved)', '    try', f'        abi = ccall(Libdl.dlsym(handle, :{ns}_abi_version), UInt32, ())', f'        contract = unsafe_string(ccall(Libdl.dlsym(handle, :{ns}_contract_sha256), Cstring, ()))', f'        abi == {version} && contract == "{digest}" || error("Native interface mismatch")', '    catch\n        Libdl.dlclose(handle)\n        rethrow()\n    end', '    Library(handle)\nend', 'function Base.close(lib::Library)\n    if lib.handle != C_NULL\n        Libdl.dlclose(lib.handle)\n        lib.handle = C_NULL\n    end\nend']
    for fn in value["functions"]:
        symbol = f'{ns}_{fn["name"]}_v{version}'
        ports = fn["inputs"] + fn["outputs"]
        args_c, args_rs = [], []
        for p in ports:
            const = p in fn["inputs"]
            args_c += [f'{"const " if const else ""}double* {p["name"]}', f'size_t {p["name"]}_len']
            args_rs += [f'{p["name"]}: *{"const" if const else "mut"} f64', f'{p["name"]}_len: usize']
        c += [f'int32_t {symbol}({", ".join(args_c)});']
        rs += [f'    fn {symbol}({", ".join(args_rs)}) -> i32;']
        py += [f'        self.lib.{symbol}.argtypes = [C.POINTER(C.c_double), C.c_size_t] * {len(ports)}', f'        self.lib.{symbol}.restype = C.c_int32']
    rs += ['}']
    # Separate methods from Python constructor.
    for fn in value["functions"]:
        symbol = f'{ns}_{fn["name"]}_v{version}'
        ins, outs = fn["inputs"], fn["outputs"]
        input_names = [p["name"] for p in ins]
        py += [f'    def {fn["name"]}(self, {", ".join(input_names)}):', '        if "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:', '            raise ValueError("Bound library bytes changed")']
        rs += [f'pub fn {fn["name"]}({", ".join(p["name"] + ": &[f64]" for p in ins)}) -> Result<({", ".join("Vec<f64>" for _ in outs)},), i32> {{', f'    if unsafe {{ {ns}_abi_version() }} != {version} || unsafe {{ std::ffi::CStr::from_ptr({ns}_contract_sha256()) }}.to_bytes() != b"{digest}" {{ return Err(7); }}']
        cpp += [f'inline auto {fn["name"]}({", ".join("const std::vector<double>& " + p["name"] for p in ins)}) {{', f'    if ({ns}_abi_version() != {version} || std::string({ns}_contract_sha256()) != {prefix}_CONTRACT_SHA256) throw std::runtime_error("Native interface mismatch");']
        jl += [f'function {fn["name"]}(lib::Library, {", ".join(p["name"] + "::Vector{Float64}" for p in ins)})', '    lib.handle != C_NULL || error("Closed native library")']
        for p in ins:
            n, lo, hi = p["name"], p["min"], p["max"]
            py += [f'        if not isinstance({n}, (list, tuple)) or not {lo} <= len({n}) <= {hi} or any(type(v) not in (int, float) for v in {n}):', f'            raise ValueError("Invalid {n} buffer")', f'        _{n} = (C.c_double * len({n}))(*{n})']
            rs += [f'    if {n}.len() < {lo} || {n}.len() > {hi} {{ return Err(2); }}']
            cpp += [f'    if ({n}.size() < {lo} || {n}.size() > {hi}) throw std::invalid_argument("Invalid {n} length");']
            jl += [f'    {lo} <= length({n}) <= {hi} || error("Invalid {n} length")']
        for p in outs:
            n, src = p["name"], p["length_from"]
            py += [f'        _{n} = (C.c_double * len({src}))()']
            rs += [f'    let mut {n} = vec![0.0_f64; {src}.len()];']
            cpp += [f'    std::vector<double> {n}({src}.size());']
            jl += [f'    {n} = zeros(Float64, length({src}))']
        ports = ins + outs
        pyargs = ', '.join(f'_{p["name"]}, len(_{p["name"]})' for p in ports)
        rsargs = ', '.join(f'{p["name"]}.as_{"" if p in ins else "mut_"}ptr(), {p["name"]}.len()' for p in ports)
        cppargs = ', '.join(f'{p["name"]}.data(), {p["name"]}.size()' for p in ports)
        jlargs = ', '.join(f'{p["name"]}, length({p["name"]})' for p in ports)
        jltypes = ', '.join('Ptr{Float64}, Csize_t' for p in ports)
        py += [f'        status = self.lib.{symbol}({pyargs})', '        if status != 0: raise ValueError(f"Native operation refused: {status}")', '        return (' + ', '.join(f'list(_{p["name"]})' for p in outs) + ',)']
        rs += [f'    let status = unsafe {{ {symbol}({rsargs}) }};', '    if status != 0 { return Err(status); }', '    Ok((' + ', '.join(p["name"] for p in outs) + ',))', '}']
        cpp += [f'    const auto status = {symbol}({cppargs});', '    if (status) throw std::runtime_error("Native operation refused: " + std::to_string(status));', '    return std::make_tuple(' + ', '.join('std::move(' + p["name"] + ')' for p in outs) + ');', '}']
        jl += [f'    status = ccall(Libdl.dlsym(lib.handle, :{symbol}), Int32, ({jltypes},), {jlargs})', '    status == 0 || error("Native operation refused: $status")', '    (' + ', '.join(p["name"] for p in outs) + ',)', 'end']
    c += ['#ifdef __cplusplus\n}\n#endif']
    cpp += ['}']
    jl += ['end']
    result = {f'{ns}.h': '\n'.join(c)+'\n', f'{ns}.hpp': '\n'.join(cpp)+'\n', f'{ns}.py': '\n'.join(py)+'\n', f'{ns}.rs': '\n'.join(rs)+'\n', f'{ns}.jl': '\n'.join(jl)+'\n'}
    result['interface.canonical.json'] = canonical.decode()+'\n'
    result['bindings.json'] = json.dumps({'schema': 'scr.generated-bindings.v1', 'contract_sha256': 'sha256:'+digest, 'compiler_sha256': 'sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'files': {k:'sha256:'+hashlib.sha256(v.encode()).hexdigest() for k,v in result.items()}}, sort_keys=True, indent=2)+'\n'
    return result


def load(path):
    def pairs(items):
        result = {}
        for k,v in items:
            if k in result: raise ValueError("Duplicate JSON key")
            result[k] = v
        return result
    with Path(path).open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536: raise ValueError("Interface exceeds 64 KiB")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('interface', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    files = compile_interface(load(args.interface))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for filename, content in files.items():
        (args.output_dir / filename).write_text(content, encoding='utf-8', newline='\n')

if __name__ == '__main__': main()
