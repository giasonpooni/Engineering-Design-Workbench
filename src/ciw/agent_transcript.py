"""Bounded lossless retention of large MCP SDK responses, not new execution grants."""
import base64
import json
from .control_contracts import bytes_ref, content_ref, keys
from .session import loads_json


MAX_SDK_RESPONSE_BYTES = 4 * 1024 * 1024
SDK_CHUNK_BYTES = 24000


def capture_sdk_response(value: dict) -> dict:
    """Retain the complete SDK response, without oversized duplicate JSON strings.

    This is canonicalized SDK output, not a byte-identical network-wire capture.
    Opaque chunks do not grant execution or relax the original workcell schemas.
    """
    if type(value) is not dict:
        raise ValueError('SDK response must be an object')
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                     separators=(',', ':')).encode('utf-8')
    if not 0 < len(raw) <= MAX_SDK_RESPONSE_BYTES:
        raise ValueError('SDK response exceeds the retained byte budget')
    return {'schema': 'ciw.mcp-sdk-response.v1', 'encoding': 'canonical-sdk-json',
        'bytes': len(raw), 'sha256': bytes_ref(raw),
        'base64_chunks': [base64.b64encode(raw[i:i+SDK_CHUNK_BYTES]).decode('ascii')
                          for i in range(0, len(raw), SDK_CHUNK_BYTES)]}


def restore_sdk_response(value: dict) -> dict:
    """Decode a bounded retained SDK response as untrusted data, never execute it."""
    keys(value, {'schema', 'encoding', 'bytes', 'sha256', 'base64_chunks'})
    if value['schema'] != 'ciw.mcp-sdk-response.v1' or value['encoding'] != 'canonical-sdk-json':
        raise ValueError('Unsupported SDK response retention format')
    count = value['bytes']
    if type(count) is not int or not 0 < count <= MAX_SDK_RESPONSE_BYTES:
        raise ValueError('Invalid SDK response size')
    content_ref(value['sha256'])
    chunks = value['base64_chunks']
    if type(chunks) is not list or len(chunks) != (count + SDK_CHUNK_BYTES - 1)//SDK_CHUNK_BYTES:
        raise ValueError('SDK response chunk count mismatch')
    pieces = []
    for index, chunk in enumerate(chunks):
        if type(chunk) is not str or not 1 <= len(chunk) <= 32000:
            raise ValueError('Invalid SDK response chunk')
        raw = base64.b64decode(chunk, validate=True)
        required = min(SDK_CHUNK_BYTES, count - index*SDK_CHUNK_BYTES)
        if len(raw) != required:
            raise ValueError('SDK response chunk size mismatch')
        pieces.append(raw)
    raw = b''.join(pieces)
    if bytes_ref(raw) != value['sha256']:
        raise ValueError('SDK response digest mismatch')
    result = loads_json(raw.decode('utf-8'))
    if type(result) is not dict:
        raise ValueError('SDK response is not an object')
    return result
