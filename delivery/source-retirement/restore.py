"""Restore the qualified NET workspace from its local checksum-bound bundle."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import tempfile

from publish import EXPECTED_BASE, EXPECTED_BUNDLE, EXPECTED_SIZE, EXPECTED_TARGET, PARTS, TARGET_BRANCH, git, require


def main():
    root = Path(__file__).resolve().parents[2]
    require(Path.cwd().resolve() == root, 'Run this command from the root of the NET checkout')
    require(Path(git('rev-parse', '--show-toplevel', capture=True)).resolve() == root,
            'Run this command from the root of the NET checkout')
    require(not git('status', '--porcelain', capture=True), 'Use a clean NET checkout')
    require(git('rev-parse', '--is-shallow-repository', capture=True) == 'false',
            'Complete Git history is required')
    require(not git('for-each-ref', '--format=%(refname)', 'refs/replace', capture=True),
            'Replacement objects are not supported')
    require(not Path(git('rev-parse', '--git-path', 'info/grafts', capture=True)).exists(),
            'Grafted history is not supported')
    require(not os.environ.get('GIT_GRAFT_FILE'), 'Grafted history is not supported')
    directory = Path(__file__).resolve().parent
    catalog_bytes = (directory / 'sources.json').read_bytes()
    import json
    catalog = json.loads(catalog_bytes)
    require(catalog['schema'] == 'notations.source-retirement.v1' and
            len(catalog['modules']) == 23, 'Unexpected catalog')
    refs = {ref['retained_ref']: ref['object'] for module in catalog['modules'] for ref in module['refs']}
    require(len(refs) == 397, 'Incomplete retained refs')
    for module in catalog['modules']:
        for ref in module['refs']:
            require(ref['retained_ref'] == 'refs/tags/retired/' + module['id'] + '/' +
                    ref['ref'].removeprefix('refs/'), 'Unexpected retained label')
    with tempfile.TemporaryDirectory(prefix='net-native-restore-') as temp:
        bundle = Path(temp) / 'native.bundle'
        digest = hashlib.sha256()
        with bundle.open('wb') as output:
            for name, size, checksum in PARTS:
                data = (directory / name).read_bytes()
                require(len(data) == size and hashlib.sha256(data).hexdigest() == checksum,
                        'Bundle part checksum mismatch: ' + name)
                output.write(data)
                digest.update(data)
        require(bundle.stat().st_size == EXPECTED_SIZE and digest.hexdigest() == EXPECTED_BUNDLE,
                'Bundle checksum mismatch')
        git('bundle', 'verify', str(bundle), capture=True)
        advertised = git('bundle', 'list-heads', str(bundle), capture=True)
        require(advertised == EXPECTED_TARGET + ' refs/heads/' + TARGET_BRANCH,
                'Unexpected bundle branch')
        git('bundle', 'unbundle', str(bundle), capture=True)
        git('merge-base', '--is-ancestor', EXPECTED_BASE, EXPECTED_TARGET)
        require(subprocess.check_output(['git', '--no-replace-objects', 'show',
                                        EXPECTED_TARGET + ':instruments/retirement.json']) == catalog_bytes,
                'Bundle catalog mismatch')
        refs['refs/heads/' + TARGET_BRANCH] = EXPECTED_TARGET
        transaction = ['start']
        for name, object_id in sorted(refs.items()):
            git('check-ref-format', name)
            git('cat-file', '-e', object_id)
            current = subprocess.run(['git', '--no-replace-objects', 'rev-parse', '--verify',
                                      '--quiet', name], capture_output=True, text=True)
            require(current.returncode in (0, 1), 'Cannot inspect local ref')
            if current.returncode == 0:
                require(current.stdout.strip() == object_id, 'Existing ref differs: ' + name)
                transaction.append('verify ' + name + ' ' + object_id)
            else:
                transaction.append('create ' + name + ' ' + object_id)
        transaction.extend(['prepare', 'commit'])
        subprocess.run(['git', 'update-ref', '--stdin'], input='\n'.join(transaction) + '\n',
                       text=True, check=True, capture_output=True)
        git('checkout', TARGET_BRANCH)
        for command in [['scripts/superrepo.py', 'audit'],
                        ['scripts/check_source_retirement.py', '--require-retained-refs']]:
            result = subprocess.run([sys.executable, *command], capture_output=True, text=True)
            require(result.returncode == 0, result.stderr + result.stdout)
    print('NET restored and audited: 23 instruments, 397 retained branch/PR heads.')
    print('Next: python -m pip install .')
    print('Then: net --help')


if __name__ == '__main__':
    main()
