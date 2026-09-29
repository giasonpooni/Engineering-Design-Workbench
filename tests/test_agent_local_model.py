"""Real loopback HTTP fixture; no LLM and no billed-provider claim in these tests."""
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import pytest

from ciw.agent_local_model import Budget, LocalModel, endpoint, validate_profile, validate_identity, usage_from


def profile():
    return {'schema': 'ciw.local-model-profile.v1', 'endpoint': 'http://127.0.0.1:11434',
            'model': 'fixture:vision', 'model_digest': 'sha256:' + 'a'*64, 'server_version': '0.12.7',
            'num_ctx': 1024, 'num_predict': 128, 'max_calls': 3, 'max_total_tokens': 5000,
            'timeout_s': 3, 'vision': True, 'pricing': None}


def identity():
    return {'version': {'version': '0.12.7'}, 'tags': {'models': [{'name': 'fixture:vision', 'digest': 'a'*64}]},
            'show': {'capabilities': ['completion', 'vision']}}


def reply(action=None, **extra):
    return {'model': 'fixture:vision', 'done': True, 'done_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps(action or {'action':'stop','summary':'fixture','edits':[]})},
            'prompt_eval_count': 100, 'eval_count': 20, 'total_duration': 10, **extra}


@pytest.mark.parametrize('url', ['https://127.0.0.1:1', 'http://localhost:80', 'http://example.com:80',
    'http://127.0.0.1', 'http://127.0.0.1:80/api', 'http://user:pass@127.0.0.1:80',
    'http://127.0.0.1:80?key=x', 'http://127.0.0.1:80#x', 'http://127.0.0.1:80\n',
    'http://127.1:80', 'http://2130706433:80', 'http://10.0.0.1:80', True])
def test_no_implicit_credentials_dns_remote_or_proxy_routing(url):
    with pytest.raises((ValueError, TypeError)): endpoint(url)


def test_explicit_ipv6_loopback():
    assert endpoint('http://[::1]:11434') == ('::1', 11434)


@pytest.mark.parametrize('field,value', [('max_calls', True), ('num_ctx', 0), ('num_predict', -1),
    ('model', 'remote:cloud'), ('model_digest', 'sha256:bad'), ('server_version', 'latest'),
    ('pricing', {'input_usd_per_million': 1, 'output_usd_per_million':'1', 'max_estimated_usd':'2'}),
    ('vision', 1), ('timeout_s', 601), ('max_total_tokens', 0), ('shell', 'anything')])
def test_bad_model_profiles(field, value):
    p = profile(); p[field] = value
    with pytest.raises((ValueError, TypeError)): validate_profile(p)


@pytest.mark.parametrize('change', ['version', 'digest', 'missing', 'vision', 'cloud', 'duplicate'])
def test_identity_and_capability_refusal(change):
    p = profile(); i = identity()
    if change == 'version': i['version']['version'] = '0.12.8'
    elif change == 'digest': i['tags']['models'][0]['digest'] = 'b'*64
    elif change == 'missing': i['tags']['models'] = []
    elif change == 'vision': i['show']['capabilities'] = ['completion']
    elif change == 'cloud': i['show']['remote_model'] = 'cloud-model'
    else: i['tags']['models'] *= 2
    with pytest.raises(ValueError): validate_identity(p, i)


@pytest.mark.parametrize('field,value', [('prompt_eval_count', None), ('prompt_eval_count', True),
    ('eval_count', -1), ('total_duration', -1), ('done', 1), ('model', 'other'), ('error','bad')])
def test_invalid_usage_is_not_imputed(field, value):
    with pytest.raises(ValueError): usage_from(profile(), reply(**{field: value}))


def test_unknown_usage_holds_reservation_not_zero_cost():
    b = Budget(profile()); b.reserve()
    with pytest.raises(ValueError): b.settle(reply(eval_count=None))
    assert b.report()['total_tokens'] is None and b.report()['unknown_calls'] == 1
    with pytest.raises(ValueError): b.reserve()


def test_budget_settles_measured_and_reserves_next_call():
    b = Budget(profile()); b.reserve(); b.settle(reply())
    assert b.report()['known_prompt_tokens'] == 100 and b.report()['total_tokens'] == 120
    assert b.report()['estimated_usd'] is None and b.report()['billed_usd'] is None
    b.reserve(); b.settle(reply()); b.reserve(); b.settle(reply())
    with pytest.raises(ValueError): b.reserve()


def test_requested_token_and_estimate_caps_are_checked_before_dispatch():
    p = profile(); p['max_total_tokens'] = 1152
    b = Budget(p); b.reserve(); b.settle(reply())
    with pytest.raises(ValueError, match='reservation'): b.reserve()
    p = profile(); p['pricing'] = {'input_usd_per_million':'2', 'output_usd_per_million':'4', 'max_estimated_usd':'0.00001'}
    with pytest.raises(ValueError, match='rate-card'): Budget(p).reserve()
    p['pricing']['max_estimated_usd'] = '1'
    b = Budget(p); b.reserve(); u = b.settle(reply())
    assert u['estimated_usd'] == '0.00028' and u['billed_usd'] is None


def test_provider_overrun_remains_measured_and_stops():
    b = Budget(profile()); b.reserve()
    with pytest.raises(ValueError, match='exceeded'): b.settle(reply(eval_count=129))
    assert b.report()['known_generated_tokens'] == 129 and b.report()['reservation_breached']
    with pytest.raises(ValueError): b.reserve()


@pytest.fixture
def http_fixture():
    class Handler(BaseHTTPRequestHandler):
        calls = []; mode = 'ok'
        def log_message(self, *_): pass
        def do_GET(self): self.respond()
        def do_POST(self): self.respond()
        def respond(self):
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'null')
            self.calls.append((self.path, data, dict(self.headers)))
            if self.mode == 'redirect':
                self.send_response(302); self.send_header('Location','http://example.invalid/'); self.end_headers(); return
            if self.mode == 'fail': self.send_response(500); self.end_headers(); return
            record = {'/api/version': identity()['version'], '/api/tags':identity()['tags'],
                      '/api/show': identity()['show'], '/api/chat':reply()}[self.path]
            if self.mode == 'badtype': content_type = 'text/plain'
            else: content_type = 'application/json'
            raw = json.dumps(record).encode()
            self.send_response(200); self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    p = profile(); p['endpoint'] = f'http://127.0.0.1:{server.server_port}'
    yield LocalModel(p), Handler
    server.shutdown(); server.server_close(); thread.join()


def test_actual_http_calls_and_no_proxy_environment(http_fixture, monkeypatch):
    model, handler = http_fixture
    monkeypatch.setenv('HTTP_PROXY', 'http://credentials@evil.invalid:123')
    assert model.probe() == identity()
    req = model.chat_request([{'role':'user','content':'fixture','images':['AA==']}], {'type':'object'})
    out = json.loads(model.request('/api/chat', req))
    assert usage_from(profile(), out)['generated_tokens'] == 20
    assert [r[0] for r in handler.calls] == ['/api/version','/api/tags','/api/show','/api/chat']
    assert req['stream'] is False and req['options']['num_predict'] == 128
    assert all('Authorization' not in headers for _,_,headers in handler.calls)
    with pytest.raises(ValueError): model.request('/api/pull', {'model':'anything'})


@pytest.mark.parametrize('mode', ['redirect', 'fail', 'badtype'])
def test_http_failure_never_retries(http_fixture, mode):
    model, handler = http_fixture; handler.mode = mode
    with pytest.raises(ValueError): model.request('/api/chat', {})
    assert len(handler.calls) == 1
