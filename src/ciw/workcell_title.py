"""Operator-only source capsule intake for explicitly installed title recipes."""
from __future__ import annotations
from pathlib import Path

from .control_contracts import bytes_ref, content_ref, keys, load, save_new
from .foundry_packets import inventory,read_file,root_dir
from .workcell_recipe import installed


def freeze(title_root: Path, profile: Path, expected_profile: str) -> tuple[object,dict[str,bytes],dict]:
    content_ref(expected_profile)
    profile=Path(profile)
    if profile.is_symlink():raise ValueError('Linked title profile')
    with profile.open('rb') as stream:raw=stream.read(65537)
    if len(raw)>65536 or bytes_ref(raw)!=expected_profile:raise ValueError('Title profile identity mismatch')
    from .session import loads_json
    p=loads_json(raw.decode())
    keys(p,{'schema','recipe','sources','writable','scope'})
    if p['schema']!='ciw.workcell-title-profile.v1':raise ValueError('Unsupported title profile')
    recipe=installed(p['recipe'])
    if recipe.recipe_id=='godot-prop.v1' or type(p['sources']) is not dict or set(p['sources'])!=set(recipe.source_paths) or p['writable']!=list(recipe.writable_paths):
        raise ValueError('Title profile cannot change installed source/write contract')
    title=root_dir(title_root);source={}
    for name,expected in p['sources'].items():
        keys(expected,{'sha256','bytes'});content_ref(expected['sha256'])
        if type(expected['bytes']) is not int or not 0<expected['bytes']<=65536:raise ValueError('Title source bound')
        data=read_file(title,name);data.decode('utf-8')
        if bytes_ref(data)!=expected['sha256'] or len(data)!=expected['bytes']:raise ValueError('Title source drift: '+name)
        source[name]=data
    if sum(map(len,source.values()))>512*1024:raise ValueError('Title capsule budget')
    return recipe,source,p


def configure(*,title_root,profile,profile_sha256,docker,image_id,output_dir,allow_package=False):
    recipe,files,manifest=freeze(title_root,profile,profile_sha256)
    raw_profile=Path(profile).read_bytes()
    if bytes_ref(raw_profile)!=profile_sha256:raise ValueError('Title profile changed during freezing')
    content_ref(image_id);docker=Path(docker).absolute();docker_hash=bytes_ref(docker.read_bytes())
    root=Path(output_dir).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Linked output directory')
    root.mkdir(parents=True,exist_ok=False)
    source=root/'source';source.mkdir()
    for name,raw in files.items():
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (root/'source-profile.json').write_bytes(raw_profile)
    value={'schema':'ciw.workcell-title-host.v1','recipe':recipe.recipe_id,'source_root':'source',
           'source_id':inventory(source)['inventory_id'],'source_profile_sha256':profile_sha256,
           'output_dir':'cell','docker':str(docker),'docker_sha256':docker_hash,'image_id':image_id,
           'socket':'unix:///var/run/docker.sock','writable':list(recipe.writable_paths),'max_candidates':8,'max_runs':8,'allow_package':allow_package}
    save_new(root/'profile.json',value)
    return root/'profile.json'
