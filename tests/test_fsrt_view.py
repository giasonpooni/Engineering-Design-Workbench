"""Provider-free exporter argument and non-overwrite checks. Not pipeline qualification."""
import pytest
from ciw.fsrt_view import export_view, write_view


@pytest.mark.parametrize('identity', ['', 'execution-x', 'result-' + 'a' * 32])
def test_public_invalid_identity_refused_before_read(identity, tmp_path):
    with pytest.raises(ValueError, match='execution identity'):
        export_view(tmp_path / 'absent.json', identity, expected_workspace_sha256='sha256:' + 'a' * 64)


@pytest.mark.parametrize('expected', ['', 'sha256:abc', 'sha256:' + 'A' * 64])
def test_public_invalid_digest_refused_before_read(expected, tmp_path):
    with pytest.raises(ValueError, match='SHA-256'):
        export_view(tmp_path / 'absent.json', 'execution-' + 'a' * 32, expected_workspace_sha256=expected)


def test_public_digest_mismatch_does_not_parse(tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_bytes(b'not JSON')
    with pytest.raises(ValueError, match='bytes differ'):
        export_view(path, 'execution-' + 'a' * 32, expected_workspace_sha256='sha256:' + 'a' * 64)


def test_public_exclusive_output(tmp_path):
    path = tmp_path / 'original.json'
    path.write_bytes(b'original')
    with pytest.raises(FileExistsError):
        write_view({'payload':'example', 'sha256':'sha256:' + 'a'*64}, path)
    assert path.read_bytes() == b'original'
