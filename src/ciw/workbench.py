"""Shared retained sources and native instrument results for one CIW session.

This catalog does not estimate state. GSIE's retained posterior and conditional
prediction remain separate, explicitly selected contexts. Repository bindings
are trusted process configuration and never enter the saved workspace.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import RLock

from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
