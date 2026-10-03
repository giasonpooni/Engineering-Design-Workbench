"""Generated buffer bindings. No DSP mathematics. Contract: e166f638e9a41c4c80fcbda8102db7598c4e404cd422e59cc2e8b7828d8ba26d."""
import ctypes as C
import hashlib
from pathlib import Path
CONTRACT_SHA256 = "sha256:e166f638e9a41c4c80fcbda8102db7598c4e404cd422e59cc2e8b7828d8ba26d"
ABI_VERSION = 1
class Library:
    def __init__(self, path, *, expected_sha256):
        self.path = Path(path).expanduser().resolve(strict=True)
        if "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("Native library digest mismatch")
        self.digest = expected_sha256
        self.lib = C.CDLL(str(self.path))
        self.lib.scr_dsp_abi_version.argtypes = []
        self.lib.scr_dsp_abi_version.restype = C.c_uint32
        self.lib.scr_dsp_contract_sha256.argtypes = []
        self.lib.scr_dsp_contract_sha256.restype = C.c_char_p
        if self.lib.scr_dsp_abi_version() != ABI_VERSION or self.lib.scr_dsp_contract_sha256().decode("ascii") != CONTRACT_SHA256[7:]:
            raise ValueError("Native interface mismatch")
        self.lib.scr_dsp_fir_v1.argtypes = [C.POINTER(C.c_double), C.c_size_t] * 5
        self.lib.scr_dsp_fir_v1.restype = C.c_int32
    def fir(self, taps, samples, history):
        if "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:
            raise ValueError("Bound library bytes changed")
        if not isinstance(taps, (list, tuple)) or not 1 <= len(taps) <= 64 or any(type(v) not in (int, float) for v in taps):
            raise ValueError("Invalid taps buffer")
        _taps = (C.c_double * len(taps))(*taps)
        if not isinstance(samples, (list, tuple)) or not 1 <= len(samples) <= 4096 or any(type(v) not in (int, float) for v in samples):
            raise ValueError("Invalid samples buffer")
        _samples = (C.c_double * len(samples))(*samples)
        if not isinstance(history, (list, tuple)) or not 0 <= len(history) <= 63 or any(type(v) not in (int, float) for v in history):
            raise ValueError("Invalid history buffer")
        _history = (C.c_double * len(history))(*history)
        _output = (C.c_double * len(samples))()
        _next_history = (C.c_double * len(history))()
        status = self.lib.scr_dsp_fir_v1(_taps, len(_taps), _samples, len(_samples), _history, len(_history), _output, len(_output), _next_history, len(_next_history))
        if status != 0: raise ValueError(f"Native operation refused: {status}")
        return (list(_output), list(_next_history),)
