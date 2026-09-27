"""Source-tree compatibility entry point for provider checkout validation.

Integration gates run before CIW is installed. Bootstrap the adjacent package
source deliberately so they use the same validator as the installed doctor.
"""
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ciw.provider_checkouts import ProviderCheckoutError, _git, validate_checkout


__all__ = ["ProviderCheckoutError", "_git", "validate_checkout"]
