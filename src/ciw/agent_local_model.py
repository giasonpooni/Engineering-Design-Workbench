"""Explicit local-model boundary. No discovery, pulls, keys, redirects or retries.

The first provider is operator-hosted Ollama's JSON chat API. Endpoint/model
identity is a server declaration, not cryptographic inference attestation.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import http.client
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from .control_contracts import bytes_ref, content_ref, keys
from .session import loads_json

MAX_HTTP_BYTES = 2 * 1024 * 1024


def integer(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'Expected integer in {low}..{high}')
    return value


def endpoint(value: str) -> tuple[str, int]:
    if type(value) is not str:
        raise ValueError('Require an explicit loopback HTTP endpoint')
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', '::1') or
            url.username is not None or url.password is not None or
            url.path not in ('', '/') or url.query or url.fragment or
            any(ch.isspace() for ch in value)):
        raise ValueError('Only literal loopback HTTP endpoints without credentials/paths are supported')
    return url.hostname, integer(url.port, 1, 65535)


def validate_profile(value: dict) -> dict:
    keys(value, {'schema', 'endpoint', 'model', 'model_digest', 'server_version',
                 'num_ctx', 'num_predict', 'max_calls', 'max_total_tokens',
                 'timeout_s', 'vision', 'pricing'})
    if value['schema'] != 'ciw.local-model-profile.v1':
        raise ValueError('Unsupported model profile')
    endpoint(value['endpoint'])
    if (type(value['model']) is not str or
            re.fullmatch(r'[a-zA-Z0-9_./:-]{1,128}', value['model']) is None or
            'cloud' in value['model'].lower() or '..' in value['model']):
        raise ValueError('Require an explicitly named local model')
    content_ref(value['model_digest'])
    if type(value['server_version']) is not str or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value['server_version']):
        raise ValueError('Pin the exact Ollama server version')
    integer(value['num_ctx'], 1024, 131072)
    integer(value['num_predict'], 64, 8192)
    if value['num_predict'] >= value['num_ctx']:
        raise ValueError('Output must leave context for input')
    integer(value['max_calls'], 1, 8)
    integer(value['max_total_tokens'], value['num_ctx'] + value['num_predict'], 2_000_000)
    integer(value['timeout_s'], 1, 600)
    if type(value['vision']) is not bool:
        raise ValueError('Explicit vision mode required')
    price = value['pricing']
    if price is not None:
        keys(price, {'input_usd_per_million', 'output_usd_per_million', 'max_estimated_usd'})
        for key, rate in price.items():
            if type(rate) is not str or not re.fullmatch(r'(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,8})?', rate):
                raise ValueError('Price estimates require bounded decimal strings')
        if Decimal(price['max_estimated_usd']) <= 0:
            raise ValueError('Require a positive estimated-spend cap')
    return deepcopy(value)


def price_for(profile: dict, prompt: int, generated: int) -> str | None:
    """Operator rate-card estimate, never a vendor invoice or full compute cost."""
    p = profile['pricing']
    if p is None:
        return None
    return str((Decimal(prompt) * Decimal(p['input_usd_per_million']) +
                Decimal(generated) * Decimal(p['output_usd_per_million'])) / Decimal(1_000_000))


def validate_identity(profile: dict, records: dict) -> None:
    keys(records, {'version', 'tags', 'show'})
    if records['version'].get('version') != profile['server_version']:
        raise ValueError('Model server version drift')
    models = records['tags'].get('models')
    if type(models) is not list:
        raise ValueError('Missing local model registry')
    matches = [x for x in models if type(x) is dict and x.get('name') == profile['model']]
    if len(matches) != 1:
        raise ValueError('Pinned model must already be installed exactly once; no automatic pull')
    digest = matches[0].get('digest')
    if type(digest) is not str or 'sha256:' + digest.removeprefix('sha256:') != profile['model_digest']:
        raise ValueError('Local model digest drift')
    show = records['show']
    if show.get('remote_model') or show.get('remote_host') or matches[0].get('remote_host'):
        raise ValueError('Cloud/remote inference is outside the local provider grant')
    capabilities = show.get('capabilities', [])
    required = {'completion', 'vision'} if profile['vision'] else {'completion'}
    if type(capabilities) is not list or required - set(capabilities):
        raise ValueError('Pinned model lacks required declared capabilities')


def usage_from(profile: dict, value: dict) -> dict:
    """Provider-reported telemetry only; model-generated prose never supplies usage."""
    if type(value) is not dict:
        raise ValueError('Expected a model response object')
    if value.get('model') != profile['model'] or value.get('done') is not True or 'error' in value:
        raise ValueError('Incomplete response or model mismatch')
    message = value.get('message')
    if type(message) is not dict or message.get('role') != 'assistant' or type(message.get('content')) is not str:
        raise ValueError('Missing model response')
    prompt = integer(value.get('prompt_eval_count'), 1, 2_000_000)
    generated = integer(value.get('eval_count'), 0, 2_000_000)
    durations = {}
    for name in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
        v = value.get(name)
        durations[name] = None if v is None else integer(v, 0, 10**15)
    return {'prompt_tokens': prompt, 'generated_tokens': generated,
            'provider_durations_ns': durations, 'source': 'local_server_report_not_independent_meter',
            'estimated_usd': price_for(profile, prompt, generated), 'billed_usd': None}


class Budget:
    """Reserve before request; unknown usage retains the reservation and stops the run."""
    def __init__(self, profile: dict):
        self.profile = validate_profile(profile)
        self.calls = 0
        self.prompt_tokens = 0
        self.generated_tokens = 0
        self.outstanding = False
        self.breached = False

    def reserve(self) -> dict:
        p = self.profile
        if self.outstanding or self.breached:
            raise ValueError('Previous call unresolved or budget breached; no automatic retry')
        if self.calls >= p['max_calls']:
            raise ValueError('Model call budget exhausted')
        if self.prompt_tokens + self.generated_tokens + p['num_ctx'] + p['num_predict'] > p['max_total_tokens']:
            raise ValueError('Insufficient remaining token reservation')
        estimate = price_for(p, self.prompt_tokens + p['num_ctx'], self.generated_tokens + p['num_predict'])
        if estimate is not None and Decimal(estimate) > Decimal(p['pricing']['max_estimated_usd']):
            raise ValueError('Insufficient remaining rate-card estimate reservation')
        self.calls += 1
        self.outstanding = True
        return {'call': self.calls, 'prompt_tokens_reserved': p['num_ctx'],
                'output_tokens_reserved': p['num_predict'], 'estimate_is_invoice': False}

    def settle(self, value: dict) -> dict:
        if not self.outstanding:
            raise ValueError('No dispatched/reserved model call')
        usage = usage_from(self.profile, value)
        self.prompt_tokens += usage['prompt_tokens']
        self.generated_tokens += usage['generated_tokens']
        self.outstanding = False
        self.breached = (usage['prompt_tokens'] > self.profile['num_ctx'] or
                         usage['generated_tokens'] > self.profile['num_predict'])
        if self.breached:
            raise ValueError('Provider exceeded declared token reservation; retain evidence and halt')
        return usage

    def report(self) -> dict:
        unknown = self.outstanding
        return {'calls_reserved': self.calls,
                'known_prompt_tokens': self.prompt_tokens, 'known_generated_tokens': self.generated_tokens,
                'total_tokens': None if unknown else self.prompt_tokens + self.generated_tokens,
                'usage_coverage': 'incomplete' if unknown else 'complete',
                'unknown_calls': int(unknown), 'reservation_breached': self.breached,
                'estimated_usd': None if unknown else price_for(self.profile, self.prompt_tokens, self.generated_tokens),
                'billed_usd': None, 'rate_source': 'operator_supplied' if self.profile['pricing'] else None,
                'human_active_seconds': None, 'accepted_revisions_per_human_hour': None}


class LocalModel:
    """Blocking bounded HTTP client to an operator-provisioned loopback server."""
    def __init__(self, profile: dict):
        self.profile = validate_profile(profile)
        self.host, self.port = endpoint(profile['endpoint'])

    def request(self, path: str, payload: dict | None = None) -> bytes:
        if path not in ('/api/version', '/api/tags', '/api/show', '/api/chat'):
            raise ValueError('Endpoint is not an installed read/inference operation')
        body = None if payload is None else json.dumps(payload, ensure_ascii=True, allow_nan=False).encode()
        if body is not None and len(body) > MAX_HTTP_BYTES:
            raise ValueError('Model request exceeds byte limit; no silent truncation')
        deadline = time.monotonic() + self.profile['timeout_s']
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.profile['timeout_s'])
        try:
            connection.request('GET' if body is None else 'POST', path, body=body,
                               headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:  # No credential forwarding or automatic redirects/retries.
                raise ValueError(f'Local model HTTP status {response.status}; no retry')
            if response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('Expected non-streamed model JSON')
            parts = []; count = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Local inference observation deadline exceeded')
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                block = response.read1(min(65536, MAX_HTTP_BYTES + 1 - count))
                if not block:
                    break
                count += len(block); parts.append(block)
                if count > MAX_HTTP_BYTES:
                    raise ValueError('Local model response exceeds byte bound')
            return b''.join(parts)
        finally:
            connection.close()

    def probe(self) -> dict:
        records = {'version': loads_json(self.request('/api/version').decode()),
                   'tags': loads_json(self.request('/api/tags').decode()),
                   'show': loads_json(self.request('/api/show', {'model': self.profile['model']}).decode())}
        validate_identity(self.profile, records)
        return records

    def chat_request(self, messages: list[dict], schema: dict) -> dict:
        return {'model': self.profile['model'], 'messages': deepcopy(messages), 'format': deepcopy(schema),
                'stream': False, 'think': False, 'keep_alive': 0,
                'options': {'num_ctx': self.profile['num_ctx'], 'num_predict': self.profile['num_predict'],
                            'temperature': 0, 'seed': 1792}}
