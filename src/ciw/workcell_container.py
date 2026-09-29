"""Explicit Docker build-cell binding; no shell, pulls, writable host mount or fallback.

The local daemon and image are operator-trusted. Docker's kernel isolation is not
VM isolation and this adapter is not a security proof for hostile native code.
"""
from __future__ import annotations
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid

from .control_contracts import bytes_ref, content_ref, load
from .core.identities import content_identity
from .interactive_simulation import run_process
from .workcell_contracts import RECIPE, STAGES, validate_capture
from .workcell_recipe import PROP, Recipe, installed
from .foundry_packets import relative

POLICY = {'network':'none','read_only':True,'user':'65534:65534','cap_drop':['ALL'],
          'no_new_privileges':True,'cpus':1,'memory_bytes':536870912,'pids':64,
          'work_tmpfs_bytes':67108864,'timeout_s':45,'host_mount':'one_read_only_input',
          'docker_socket_in_child':False,'automatic_pull':False}


def create_args(image_id: str, name: str, source: Path, stage: str, *, recipe_id=RECIPE) -> list[str]:
    installed(recipe_id)
    content_ref(image_id)
    if stage not in STAGES or re.fullmatch('net-cell-[0-9a-f]{32}',name) is None:
        raise ValueError('Unsupported cell stage or name')
    source=Path(source).absolute()
    if ',' in str(source) or '\n' in str(source): raise ValueError('Unrepresentable mount path')
    return ['create','--pull=never','--name',name,'--network=none','--read-only',
            '--user=65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges',
            '--cpus=1','--memory=512m','--memory-swap=512m','--pids-limit=64',
            '--ulimit=nofile=128:128','--ulimit=fsize=8388608:8388608','--no-healthcheck',
            '--log-driver=none','--tmpfs=/work:rw,exec,nosuid,nodev,size=67108864,uid=65534,gid=65534',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8388608,uid=65534,gid=65534',
            '--mount',f'type=bind,source={source},target=/input,readonly,bind-propagation=rprivate',
            '--workdir=/work','--entrypoint=/usr/bin/python3',image_id,'-I','/recipe/runner.py',stage] + ([] if recipe_id==RECIPE else [recipe_id])


def verify_config(value: dict, image: str, source: Path):
    h,c=value['HostConfig'],value['Config']
    expected = {'NetworkMode':'none','ReadonlyRootfs':True,'Privileged':False,
                'Memory':536870912,'MemorySwap':536870912,'NanoCpus':1000000000,'PidsLimit':64}
    if any(type(h.get(k)) is not type(v) or h.get(k)!=v for k,v in expected.items()):
        raise ValueError('Daemon did not apply workcell resource/isolation policy')
    if set(h.get('CapDrop') or [])!={'ALL'} or h.get('CapAdd') or set(h.get('SecurityOpt') or [])!={'no-new-privileges'}:
        raise ValueError('Unexpected container privileges')
    if c.get('User')!='65534:65534' or value.get('Image')!=image or c.get('Entrypoint')!=['/usr/bin/python3']:
        raise ValueError('Unexpected container image, user or entrypoint')
    if h.get('Devices') or h.get('DeviceRequests') or h.get('PidMode') or h.get('IpcMode') not in ('private',''):
        raise ValueError('Unexpected shared device/namespace')
    mounts=value.get('Mounts',[])
    if len(mounts)!=1 or mounts[0].get('Destination')!='/input' or mounts[0].get('Source')!=str(source) or mounts[0].get('RW') is not False or mounts[0].get('Type')!='bind':
        raise ValueError('Unexpected mount or host write grant')
    tmpfs=h.get('Tmpfs',{})
    if set(tmpfs)!={'/work','/tmp'} or 'size=67108864' not in tmpfs['/work'] or 'size=8388608' not in tmpfs['/tmp']:
        raise ValueError('Missing bounded scratch storage')
    if h.get('LogConfig',{}).get('Type')!='none':raise ValueError('Unbounded daemon log storage')


class DockerCell:
    def __init__(self, *, docker: Path, docker_sha256: str, image_id: str,
                 socket: str='unix:///var/run/docker.sock', recipe: Recipe=PROP):
        self.recipe=recipe
        if os.name!='posix' or not socket.startswith('unix:///') or '\n' in socket:
            raise ValueError('First workcell profile requires an explicit local Unix Docker daemon')
        self.docker=Path(docker).absolute()
        content_ref(docker_sha256); content_ref(image_id)
        if not self.docker.is_file() or bytes_ref(self.docker.read_bytes())!=docker_sha256:
            raise ValueError('Docker executable differs from operator binding')
        self.socket=socket
        self.identity={'provider':'net.docker-workcell','recipe':recipe.recipe_id,'docker_sha256':docker_sha256,
                       'image_id':image_id,'policy_sha256':content_identity(POLICY),
                       'adapter_sha256':bytes_ref(Path(__file__).read_bytes()),'execution_mode':'docker_container'}
        self.image_id=image_id
        # Inspection only. No image pull/build is implicit in agent access.
        image=self._control(['image','inspect',image_id])[0]
        if image['Id']!=image_id or image.get('Os')!='linux' or image.get('Architecture')!='amd64' or image['Config'].get('Volumes'):
            raise ValueError('Image must be a local Linux amd64 build without implicit volumes')

    def command(self, args, home: Path):
        # Neither Docker CLI credentials/context nor API keys flow into the child.
        return ['/usr/bin/env','-i','PATH=/usr/bin:/bin','HOME='+str(home),'DOCKER_CONFIG='+str(home),
                str(self.docker),'--host',self.socket,*args]

    def _control(self, args, *, json_output=True):
        with tempfile.TemporaryDirectory(prefix='net-docker-control-') as home:
            r=subprocess.run(self.command(args,Path(home)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL,timeout=15,check=False)
        if r.returncode or len(r.stdout)>1024*1024 or len(r.stderr)>65536:
            raise ValueError('Docker control refused: '+r.stderr[-2000:].decode('utf-8','replace'))
        return json.loads(r.stdout) if json_output else r.stdout.decode().strip()

    def runtime_identity(self):
        if bytes_ref(self.docker.read_bytes())!=self.identity['docker_sha256']:
            raise ValueError('Docker executable changed')
        return deepcopy(self.identity)

    def invoke(self, stage: str, files: dict[str,bytes], candidate_id: str):
        self.runtime_identity(); content_ref(candidate_id)
        expected = self.recipe.input_paths(stage)
        if stage not in STAGES or set(files)!=expected or any(type(v) is not bytes or len(v)>512*1024 for v in files.values()):
            raise ValueError('Invalid workcell stage input set')
        start=time.monotonic(); name='net-cell-'+uuid.uuid4().hex; nonce=uuid.uuid4().hex
        created=False; container_id=None
        with tempfile.TemporaryDirectory(prefix='net-cell-') as temp:
            root=Path(temp); root.chmod(0o755)
            source=root/'input';source.mkdir(mode=0o755)
            for path,raw in files.items():
                relative(path)
                p=source/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(0o444)
            (source/'request.json').write_text(json.dumps({'nonce':nonce}));(source/'request.json').chmod(0o444)
            try:
                container_id=self._control(create_args(self.image_id,name,source,stage,recipe_id=self.recipe.recipe_id),json_output=False)
                created=True
                state=self._control(['inspect',name])[0]
                verify_config(state,self.image_id,source)
                logs=root/'logs';logs.mkdir()
                try:
                    run_process(self.command(['start','--attach',name],root/'docker-home'),logs,timeout=45)
                    process=load(logs/'stdout.log')
                except RuntimeError as exc:
                    process={'schema':'ciw.workcell-process.v1','stage':stage,'nonce':nonce,'outcome':'timeout' if 'timeout' in str(exc) else 'failed',
                             'diagnostic':str(exc)[-8000:],'files':{},'observations':None,'logs':''}
                if process.get('nonce')!=nonce:raise ValueError('Container response nonce mismatch')
                for path,raw in files.items():
                    if (source/path).read_bytes()!=raw:raise ValueError('Read-only source changed')
            finally:
                # Reap this unique named container even if the attached CLI timed out.
                # Never delete other containers or touch the operator image cache.
                if created:self._control(['rm','--force',name],json_output=False)
        result={'schema':'ciw.workcell-capture.v1','stage':stage,'candidate_id':candidate_id,
                'process':process,'elapsed_wall_s':time.monotonic()-start,
                'isolation':{'mode':'docker_container','image_id':self.image_id,'container_id':container_id,
                             'policy_sha256':content_identity(POLICY),'checked_before_start':True,'cleanup_complete':True}}
        self.recipe.validate(result,stage,candidate_id)
        return result
