"""Local, self-contained mathematical inspector. No network, server or engine load."""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
import tempfile

from .control_contracts import load
from .math_inspector import validate_report
from .telemetry import canonical

MAX_HTML_BYTES = 12 * 1024 * 1024


def render_html(report: dict) -> bytes:
    """Validate retained numerical context before embedding inert, base64 data.

    Hash-based CSP permits only the packaged CSS/JS. User text is never interpolated
    as HTML or JavaScript. The browser performs display transforms, not inference.
    """
    validate_report(report)
    assets = files('ciw').joinpath('web')
    template = assets.joinpath('math_inspector.html').read_text(encoding='utf-8')
    css = assets.joinpath('math_inspector.css').read_text(encoding='utf-8')
    js = assets.joinpath('math_inspector.js').read_text(encoding='utf-8')
    digest = lambda text: base64.b64encode(sha256(text.encode('utf-8')).digest()).decode('ascii')
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; connect-src 'none'; "
           f"script-src 'sha256-{digest(js)}'; style-src 'sha256-{digest(css)}'; img-src data:")
    replacements = {'__CSP__': csp, '__STYLE__': css, '__SCRIPT__': js,
                    '__DATA__': base64.b64encode(canonical(report)).decode('ascii')}
    for marker, content in replacements.items():
        if template.count(marker) != 1:
            raise ValueError('Packaged mathematical viewer template is inconsistent')
        template = template.replace(marker, content)
    raw = template.encode('utf-8')
    if len(raw) > MAX_HTML_BYTES:
        raise ValueError('Mathematical viewer exceeds its HTML byte budget')
    return raw


def write_html(path: Path, report: dict) -> None:
    raw = render_html(report)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.net-math-', dir=path.parent) as tmp:
        staged = Path(tmp) / 'view.html'
        with staged.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.link(staged, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='net view', description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        write_html(args.output, load(args.report))
        print(json.dumps({'status': 'created', 'output': str(args.output),
                          'network': 'disabled', 'engine_execution': 'not_performed'}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({'status': 'refused', 'reason': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
