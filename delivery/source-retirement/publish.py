"""Publish checksum-bound native history using only objects carried in NET."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

EXPECTED_TARGET = '235032554b9847bf88103e95c401374466f2ac51'
EXPECTED_BASE = '98b7dfccec61f295d0bd0240723fb64bf0f58d17'
PREVIOUS_TARGET = 'c7762d8ad632ac5e5ff4d021c3911fd29a3451ab'
EXPECTED_BUNDLE = 'fce7284b31fb3990b3ac106331d895547cd6e90c3cb5f3d1c9e1c6d81c79ffc0'
EXPECTED_SIZE = 14655761
PARTS = (
    ('native-full-final.bundle.part01', 5242880, 'f0292ea7cb2ceed6d55948729b5e806ccc233ab2e0e7490a0fc4b3f5461fb2ac'),
    ('native-full-final.bundle.part02', 5242880, 'ac9f9883e941274467a18a52edd65e9303be5c372f5a4eb1b704741481010b37'),
    ('native-full-final.bundle.part03', 4170001, '9025803ed329a16ea7b87e10380d6f85950240fa4d78c2a77e8fd77eaee0e617'),
)
TARGET_BRANCH = 'feat/source-retirement-20261003'
TRANSPORT_BRANCH = 'transfer/source-retirement-20261003'
PREFIX = Path('delivery/source-retirement')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(*args, capture=False):
    result = subprocess.run(['git', '--no-replace-objects', *args], check=True,
                            capture_output=capture, text=True)
    return result.stdout.strip() if capture else None


def require_current_transport():
    expected = os.environ.get('TRANSPORT_HEAD', '')
    require(re.fullmatch(r'[0-9a-f]{40}', expected), 'Missing transport event head')
    observed = git('ls-remote', 'origin', 'refs/heads/' + TRANSPORT_BRANCH, capture=True)
    require(observed and observed.split()[0] == expected, 'Stale transport workflow')


def main():
    require_current_transport()
    catalog_bytes = (PREFIX / 'sources.json').read_bytes()
    catalog = json.loads(catalog_bytes)
    require(catalog['schema'] == 'notations.source-retirement.v1' and
            len(catalog['modules']) == 23, 'Unexpected catalog')
    expected = {}
    for module in catalog['modules']:
        for ref in module['refs']:
            name = 'refs/tags/retired/' + module['id'] + '/' + ref['ref'].removeprefix('refs/')
            require(ref['retained_ref'] == name and name not in expected, 'Invalid retained label')
            require(re.fullmatch(r'[0-9a-f]{40}', ref['object']), 'Invalid object identity')
            git('check-ref-format', name)
            expected[name] = ref['object']
    require(len(expected) == 397, 'Incomplete captured refs')
    # The temporary bundle survives checking out the native target. No old source
    # repository is fetched: base NET history and these parts hold all objects.
    with tempfile.TemporaryDirectory(prefix='net-native-publication-') as temp:
        bundle = Path(temp) / 'native.bundle'
        digest = hashlib.sha256()
        with bundle.open('wb') as output:
            for name, size, checksum in PARTS:
                data = (PREFIX / name).read_bytes()
                require(len(data) == size and hashlib.sha256(data).hexdigest() == checksum,
                        'Bundle part checksum mismatch: ' + name)
                output.write(data)
                digest.update(data)
        require(bundle.stat().st_size == EXPECTED_SIZE and digest.hexdigest() == EXPECTED_BUNDLE,
                'Native bundle checksum mismatch')
        git('bundle', 'verify', str(bundle))
        git('fetch', '--no-tags', str(bundle),
            'refs/heads/' + TARGET_BRANCH + ':refs/heads/native-retirement')
        require(git('rev-parse', 'native-retirement', capture=True) == EXPECTED_TARGET,
                'Unexpected native target')
        git('merge-base', '--is-ancestor', EXPECTED_BASE, EXPECTED_TARGET)
        for name, object_id in expected.items():
            git('cat-file', '-e', object_id)
            git('update-ref', name, object_id)
        git('checkout', '--detach', EXPECTED_TARGET)
        require(Path('instruments/retirement.json').read_bytes() == catalog_bytes,
                'Transport catalog differs from native target')
        subprocess.run([sys.executable, 'scripts/superrepo.py', 'audit'], check=True)
        subprocess.run([sys.executable, 'scripts/check_source_retirement.py',
                        '--require-retained-refs'], check=True)
        subprocess.run([sys.executable, '-m', 'pytest', '-q',
                        'tests/test_source_retirement.py', 'tests/test_local_provider_sources.py',
                        'tests/test_monorepo.py', 'tests/test_monorepo_schematics.py',
                        'scripts/tests/test_ci_policy.py'], check=True)
        require_current_transport()
        remote = subprocess.run(['git', 'ls-remote', '--exit-code', 'origin',
                                 'refs/heads/' + TARGET_BRANCH], capture_output=True, text=True)
        require(remote.returncode in (0, 2), 'Cannot inspect publication destination')
        if remote.returncode == 0:
            old = remote.stdout.split()[0]
            require(old in (EXPECTED_TARGET, PREVIOUS_TARGET), 'Unexpected destination branch')
            git('merge-base', '--is-ancestor', old, EXPECTED_TARGET)
        # Create or fast-forward only. Conflicting existing remote tags make the
        # entire push fail; --atomic prevents a partial history publication.
        git('push', '--atomic', 'origin', EXPECTED_TARGET + ':refs/heads/' + TARGET_BRANCH,
            *sorted(expected))
        require(git('ls-remote', 'origin', 'refs/heads/' + TARGET_BRANCH,
                    capture=True).split()[0] == EXPECTED_TARGET, 'Publication verification failed')
        print('Published verified native retirement branch:', EXPECTED_TARGET)


if __name__ == '__main__':
    main()
