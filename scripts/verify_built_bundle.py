"""Exercise the publishing integrity guard on the real CI-built distributions."""
from pathlib import Path
import subprocess
import tomllib

from release_guard import check_bundle

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    check_bundle(root, revision, version)
    print("Publishing integrity guard passed for the actual wheel and sdist.")
