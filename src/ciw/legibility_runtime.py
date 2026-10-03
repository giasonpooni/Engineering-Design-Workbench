"""Read-only source identity for the built-in representation compiler."""
import hashlib
from pathlib import Path
import platform


def runtime_identity():
    root = Path(__file__).parent
    paths = [root / "legibility.py", root / "legibility_workflow.py", Path(__file__),
             root / "core" / "identities.py"]
    return {"provider": "ciw.legibility", "version": "1", "python": platform.python_version(),
            "source_files": {str(path.relative_to(root)): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in paths}}
