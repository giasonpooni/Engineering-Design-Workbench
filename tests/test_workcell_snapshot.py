"""Frozen evidence and engine JSON boundary regression cases."""
import pytest
from unittest.mock import patch
from test_workcell import FixtureBackend, c, setup


def test_engine_number_serialization_does_not_change_challenges():
    capture=FixtureBackend().invoke('test',{'motion.gd':b''},'sha256:'+'a'*64)
    capture['process']['observations']['challenges'][0]=[0,2,.25]
    assert c.checks_for(capture)['status']=='PASS'
    capture['process']['observations']['challenges'][0][0]=False
    with pytest.raises(ValueError):c.checks_for(capture)


def test_inspection_uses_frozen_bytes_after_validation(setup):
    h,_,_=setup;cand=h.submit('one',{});h.build('one',cand['candidate'])
    original=h.root/'runs/one/production.json'
    from ciw.production import inspect_production as real_inspect
    def inspect_then_change(path, gates):
        value=real_inspect(path,gates)
        original.write_text('{}')
        return value
    with patch('ciw.production.inspect_production',side_effect=inspect_then_change):
        assert h.inspect('one')['status']=='completed'
    with pytest.raises(ValueError):h.inspect('one')


def test_linked_export_is_not_followed(setup,tmp_path):
    h,_,_=setup;cand=h.submit('one',{});h.build('one',cand['candidate'])
    export=h.root/'runs/one/slice.pck';raw=export.read_bytes();export.unlink()
    elsewhere=tmp_path/'elsewhere';elsewhere.write_bytes(raw);export.symlink_to(elsewhere)
    with pytest.raises(ValueError,match='Linked'):h.inspect('one')
