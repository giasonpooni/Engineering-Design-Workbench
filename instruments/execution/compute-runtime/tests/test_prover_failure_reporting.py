"""A killed prover must say what happened.

SPLIT OUT OF `test_numerics.py`, AND THE SPLIT IS THE POINT. These
checks import `execution.proving`, which the open-source distribution
does not ship. The release deriver selects only test files whose every
internal import is a shipped package, so putting these in the numerics
file made THAT WHOLE FILE ineligible -- and the locks protecting the
shipped correlation and variance code silently stopped shipping with it.

Nothing failed. The derived suite went from 48 files to 47 and from 557
tests to 545, and only the count said so. That is the same "true and
silent" shape the deriver itself has: a green result, honest about what
it ran and quiet about what it no longer covers.

The lesson is about file boundaries rather than about provers. A test
file is the unit the release selects, so mixing a shipped concern with
an unshipped one in a single file removes the shipped one from the
release.

WHAT THESE CHECK. A message that cannot distinguish two situations costs
whoever reads it the time to tell them apart. `host exited -9:` with
nothing after the colon is what nineteen proving tests reported while a
C++ build ran alongside the suite. The prover holds several gigabytes;
the kernel killed it. Stderr was empty BECAUSE of the signal, so the
line was indistinguishable from a prover that failed silently for a
reason inside this repository.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_a_signal_death_is_named_rather_than_left_as_a_number():
    from execution.proving import _signal_reason

    kill = _signal_reason(-9)
    assert "SIGKILL" in kill
    assert "out-of-memory" in kill or "memory" in kill
    # and it must say why stderr is empty, which is the part that
    # actually misleads a reader
    assert "stderr is empty" in kill

    assert "SIGSEGV" in _signal_reason(-11)
    assert "SIGTERM" in _signal_reason(-15)


def test_signals_are_distinguished_from_one_another_and_from_exit_codes():
    """A reason that read the same for every death would be no better
    than the number it replaced."""
    from execution.proving import _signal_reason

    reasons = {_signal_reason(code) for code in (-9, -11, -15, -6)}
    assert len(reasons) == 4, "distinct signals produced the same explanation"

    # a POSITIVE code is an exit status, not a signal, and must not be
    # described as one -- the caller guards this today, and a helper
    # that answers confidently for an input it can be handed is what
    # later gets called from somewhere that does not
    for code in (1, 2, 127):
        reason = _signal_reason(code)
        assert "killed" not in reason
        assert "signal" not in reason
        assert str(code) in reason


def test_the_host_runner_actually_uses_the_explanation():
    """A helper nothing calls explains nothing. This drives a REAL
    subprocess that kills itself with SIGKILL -- the exact shape of the
    failure that motivated this -- rather than calling `_signal_reason`
    and trusting the wiring."""
    from execution.proving import ProvedRunError, _run_host

    with pytest.raises(ProvedRunError) as caught:
        _run_host(pathlib.Path("/bin/sh"), ["-c", "kill -9 $$"], timeout=30)
    message = str(caught.value)
    assert "SIGKILL" in message, message
    assert "memory" in message, message
    assert "-9:" not in message.split("SIGKILL")[0], (
        "the bare number is still the leading explanation")
