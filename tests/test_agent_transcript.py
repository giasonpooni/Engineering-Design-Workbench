"""Transport-size regressions; all payloads here are explicitly synthetic."""
import pytest



def test_complete_sdk_text_and_image_survive_original_json_limits(tmp_path):
    from ciw.agent_transcript import capture_sdk_response, restore_sdk_response
    from ciw.control_contracts import save_new, load
    import base64
    # Realistic representation size, deliberately synthetic pixels/text, not a render.
    doc = {'content': [{'type':'text','text':'x'*100000},
                       {'type':'image','mimeType':'image/png',
                        'data':base64.b64encode(b'pixel-fixture'*16000).decode()}],
           'structuredContent': {'status':'fixture'}, 'isError':False}
    with pytest.raises(ValueError, match='text exceeds'):
        save_new(tmp_path/'unsafe.json', doc)
    encoded = capture_sdk_response(doc)
    save_new(tmp_path/'safe.json', encoded)
    assert restore_sdk_response(load(tmp_path/'safe.json')) == doc
    assert all(len(s)<=32000 for s in encoded['base64_chunks'])


@pytest.mark.parametrize('field,value', [('bytes',True),('bytes',4194305),
    ('sha256','sha256:'+'0'*64),('base64_chunks',['!!!!']),
    ('encoding','executable'),('base64_chunks',[])])
def test_sdk_transcript_tamper_refuses(field,value):
    from ciw.agent_transcript import capture_sdk_response, restore_sdk_response
    encoded=capture_sdk_response({'content':[{'text':'retained fixture'}]})
    encoded[field]=value
    with pytest.raises((ValueError,TypeError)):
        restore_sdk_response(encoded)


def test_sdk_response_byte_budget_and_nonfinite_refuse():
    from ciw.agent_transcript import capture_sdk_response
    with pytest.raises(ValueError): capture_sdk_response({'text':'x'*4194304})
    with pytest.raises(ValueError): capture_sdk_response({'number':float('nan')})
