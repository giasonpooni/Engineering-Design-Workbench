"""Provider-free input rejection only, not engine or estimator qualification."""
import pytest
from ciw.simulated_fsrt_view import export_view

@pytest.mark.parametrize('identity',['','latest','result-'+'a'*32])
def test_invalid_occurrence_before_read(tmp_path,identity):
    with pytest.raises(ValueError,match='execution identity'):
        export_view(tmp_path/'absent.json',identity,expected_workspace_sha256='sha256:'+'a'*64)

@pytest.mark.parametrize('digest',['','sha256:abc','sha256:'+'A'*64])
def test_invalid_digest_before_read(tmp_path,digest):
    with pytest.raises(ValueError,match='SHA-256'):
        export_view(tmp_path/'absent.json','execution-'+'a'*32,expected_workspace_sha256=digest)
