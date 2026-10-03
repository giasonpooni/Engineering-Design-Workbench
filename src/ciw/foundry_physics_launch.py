"""Fixed subprocess shim: isolate child user-data environment before engine startup.

Invoked by an explicit operator-bound NET worker, not a saved task. exec preserves
NET's existing timeout/process-group supervision. This is not a security sandbox.
"""
import os
from pathlib import Path
import sys

def main():
    home = Path(sys.argv[1]).resolve(strict=True)
    if not home.is_dir():
        raise ValueError('isolated user directory missing')
    os.environ['HOME'] = str(home)
    os.environ['XDG_DATA_HOME'] = str(home / 'data')
    os.environ['XDG_CONFIG_HOME'] = str(home / 'config')
    os.environ['XDG_CACHE_HOME'] = str(home / 'cache')
    os.environ['APPDATA'] = str(home / 'data')
    os.environ['LOCALAPPDATA'] = str(home / 'local')
    os.environ['GODOT_SILENCE_ROOT_WARNING'] = '1'
    # Explicit native profile currently qualifies Linux only; don't alter unrelated
    # DLL/library search paths or pretend the environment is fully attested.
    os.execv(sys.argv[2], sys.argv[2:])

if __name__ == '__main__':
    main()
