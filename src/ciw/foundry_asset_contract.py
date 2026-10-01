"""Independent small GLB profile and fixed workbench acceptance.

Reads actual binary accessors, not a producer's summary or declared min/max.
Intentionally a closed flat, static, textured-free box-mesh profile, not a general
hostile-asset scanner, artistic judgment or physical load-bearing verification.
"""
from __future__ import annotations
import math
import struct
from pathlib import Path
from .control_contracts import number, keys, bytes_ref
from .session import loads_json

PROFILE = 'workbench-visual.v1'
OUTPUT = 'assets/props/workbench.glb'
MAX_ASSET = 48 * 1024
EPS = 1e-5
POLICY = {'profile': PROFILE, 'units': 'm', 'up_axis': 'Y', 'bounds_tolerance_m': EPS,
          'max_bytes': MAX_ASSET, 'expected_parts': 9, 'expected_triangles': 108,
          'human_art_review': 'required_separately'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, low=0, high=65536):
    require(type(value) is int and low <= value <= high, 'invalid bounded integer')
    return value


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional), 'unknown/missing GLB profile fields')


def vec(value, size=3):
    require(type(value) is list and len(value) == size, 'invalid vector')
    return [number(x) for x in value]


def close(left, right):
    return len(left) == len(right) and all(abs(a-b) <= EPS for a,b in zip(left,right))


def expected_bounds():
    # Checker owns target envelopes. Never imported by the production script.
    return {
        'top': ([-.9,.82,-.35], [.9,.9,.35]),
        'leg_0': ([-.81,0,-.29], [-.71,.82,-.19]),
        'leg_1': ([.71,0,-.29], [.81,.82,-.19]),
        'leg_2': ([-.81,0,.19], [-.71,.82,.29]),
        'leg_3': ([.71,0,.19], [.81,.82,.29]),
        'rail_front': ([-.76,.20,-.28], [.76,.28,-.20]),
        'rail_back': ([-.76,.20,.20], [.76,.28,.28]),
        'rail_left': ([-.80,.20,-.24], [-.72,.28,.24]),
        'rail_right': ([.72,.20,-.24], [.80,.28,.24])}


def observe_glb(raw: bytes) -> dict:
    require(type(raw) is bytes and 28 <= len(raw) <= MAX_ASSET, 'asset byte budget')
    magic, version, length = struct.unpack_from('<4sII', raw)
    require(magic == b'glTF' and version == 2 and length == len(raw), 'GLB header')
    offset, chunks = 12, []
    while offset < len(raw):
        require(offset + 8 <= len(raw) and len(chunks) < 2, 'chunk framing')
        n, kind = struct.unpack_from('<II',raw,offset);offset += 8
        require(n % 4 == 0 and offset+n <= len(raw), 'chunk size')
        chunks.append((kind,raw[offset:offset+n]));offset+=n
    require(len(chunks) == 2 and [c[0] for c in chunks] == [0x4e4f534a,0x004e4942], 'embedded JSON/BIN required')
    d = loads_json(chunks[0][1].decode('utf-8'))
    fields(d, {'asset','scenes','nodes','meshes','buffers','bufferViews','accessors','materials'}, {'scene'})
    fields(d['asset'], {'version'}, {'generator','copyright'})
    require(d['asset']['version'] == '2.0', 'glTF version')
    for name, limit in [('nodes',12),('meshes',12),('bufferViews',36),('accessors',36),('materials',1),('scenes',1),('buffers',1)]:
        require(type(d[name]) is list and 1 <= len(d[name]) <= limit, 'GLB table budget '+name)
    binary=chunks[1][1]
    fields(d['buffers'][0], {'byteLength'})
    declared=integer(d['buffers'][0]['byteLength'],1,MAX_ASSET)
    require(0 <= len(binary)-declared <= 3, 'embedded buffer length')
    require(integer(d.get('scene',0),0,0) == 0, 'scene selection')
    scene=d['scenes'][0];fields(scene,{'nodes'},{'name'})
    require(type(scene['nodes']) is list and all(type(i) is int for i in scene['nodes']) and sorted(scene['nodes']) == list(range(len(d['nodes']))), 'flat scene roots')
    mat=d['materials'][0];fields(mat,{'pbrMetallicRoughness'},{'name','doubleSided','alphaMode'})
    require(mat.get('doubleSided',False) is False and mat.get('alphaMode','OPAQUE')=='OPAQUE', 'opaque one-sided material')
    pbr=mat['pbrMetallicRoughness'];fields(pbr,set(),{'baseColorFactor','metallicFactor','roughnessFactor'})
    color=vec(pbr.get('baseColorFactor',[1,1,1,1]),4)
    require(all(0<=x<=1 for x in color) and color[3] == 1, 'material color')
    metallic=number(pbr.get('metallicFactor',1)); roughness=number(pbr.get('roughnessFactor',1))
    require(0 <= metallic <= .1 and .5 <= roughness <= 1, 'wood-like nonmetal roughness profile')
    access_used, view_used, meshes_used = set(), set(), set()

    def accessor(index, typ):
        index=integer(index,0,len(d['accessors'])-1); access_used.add(index)
        a=d['accessors'][index]
        fields(a,{'bufferView','componentType','count','type'},{'byteOffset','min','max'})
        require(a['type']==typ, 'accessor type')
        component=integer(a['componentType']); components=3 if typ=='VEC3' else 1
        require(component==5126 if typ=='VEC3' else component in (5123,5125), 'accessor component')
        fmt, size={5126:('f',4),5123:('H',2),5125:('I',4)}[component]
        count=integer(a['count'],1,4096)
        vi=integer(a['bufferView'],0,len(d['bufferViews'])-1); view_used.add(vi)
        v=d['bufferViews'][vi];fields(v,{'buffer','byteLength'},{'byteOffset','byteStride','target'})
        require(integer(v['buffer'],0,0)==0, 'external buffer')
        start=integer(v.get('byteOffset',0),0,declared)
        length=integer(v['byteLength'],1,declared)
        offset=integer(a.get('byteOffset',0),0,length)
        width=size*components;stride=integer(v.get('byteStride',width),width,252)
        require(stride % size==0 and offset % size==0 and (start+offset)%size==0, 'accessor alignment')
        require(typ=='VEC3' or 'byteStride' not in v, 'indices cannot be strided')
        if 'target' in v: require(v['target']==(34962 if typ=='VEC3' else 34963), 'buffer target')
        require(start+length<=declared and offset+(count-1)*stride+width<=length, 'accessor outside view')
        values=[struct.unpack_from('<'+fmt*components,binary,start+offset+i*stride) for i in range(count)]
        require(all(math.isfinite(x) for row in values for x in row), 'nonfinite binary values')
        for key, op in [('min',min),('max',max)]:
            if key in a:
                bound=vec(a[key],components)
                require(close(bound,[op(row[j] for row in values) for j in range(components)]), 'declared bounds disagree with binary')
        return values

    parts={}
    for node in d['nodes']:
        fields(node,{'name','mesh'},{'translation','rotation','scale'})
        name=node['name'];require(type(name) is str and 0<len(name)<=64 and name not in parts, 'duplicate/invalid part name')
        require(vec(node.get('rotation',[0,0,0,1]),4)==[0,0,0,1] and vec(node.get('scale',[1,1,1]))==[1,1,1], 'apply rotations and scales')
        translation=vec(node.get('translation',[0,0,0]))
        mi=integer(node['mesh'],0,len(d['meshes'])-1);require(mi not in meshes_used,'mesh instances outside profile');meshes_used.add(mi)
        mesh=d['meshes'][mi];fields(mesh,{'primitives'},{'name'})
        require(type(mesh['primitives']) is list and len(mesh['primitives'])==1,'one primitive per part')
        p=mesh['primitives'][0];fields(p,{'attributes','indices','material'},{'mode'})
        require(integer(p.get('mode',4))==4 and integer(p['material'],0,0)==0,'indexed material triangles')
        keys(p['attributes'],{'POSITION','NORMAL'})
        positions=accessor(p['attributes']['POSITION'],'VEC3');normals=accessor(p['attributes']['NORMAL'],'VEC3')
        indices=[v[0] for v in accessor(p['indices'],'SCALAR')]
        require(len(normals)==len(positions) and len(indices)==36 and max(indices)<len(positions),'triangle/index coverage')
        require(set(indices)==set(range(len(positions))), 'unused vertices')
        require(all(abs(sum(n*n for n in row)-1)<1e-4 for row in normals),'unit normals')
        points=[[p[i]+translation[i] for i in range(3)] for p in positions]
        lo=[min(v[i] for v in points) for i in range(3)];hi=[max(v[i] for v in points) for i in range(3)]
        require(all(0<hi[i]-lo[i]<=4 for i in range(3)),'degenerate/oversize geometry')
        corner=lambda p: tuple(0 if abs(p[i]-lo[i])<=EPS else 1 if abs(p[i]-hi[i])<=EPS else 2 for i in range(3))
        require(len({corner(p) for p in points})==8 and all(2 not in corner(p) for p in points),'closed box corners')
        faces={}
        for i in range(0,len(indices),3):
            idx=indices[i:i+3];a,b,c=[points[j] for j in idx]
            u=[b[j]-a[j] for j in range(3)];w=[c[j]-a[j] for j in range(3)]
            cross=[u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0]]
            magnitude=math.sqrt(sum(x*x for x in cross));require(magnitude>1e-8,'degenerate triangle')
            face=[(axis,side) for axis in range(3) for side,bound in enumerate((lo[axis],hi[axis])) if all(abs(v[axis]-bound)<=EPS for v in (a,b,c))]
            require(len(face)==1,'triangle crosses part interior')
            axis,side=face[0];require(cross[axis]*(1 if side else -1)>0,'inward winding')
            require(all(sum(cross[j]/magnitude*normals[k][j] for j in range(3))>.999 for k in idx),'normal/winding mismatch')
            key=tuple(sorted(corner(p) for p in (a,b,c)))
            group=faces.setdefault((axis,side),[]);require(key not in [x[0] for x in group], 'duplicate face triangle')
            group.append((key,magnitude/2))
        require(len(faces)==6 and all(len(v)==2 for v in faces.values()), 'complete six faces')
        for (axis,side),triangles in faces.items():
            other=[j for j in range(3) if j!=axis]
            require(abs(sum(v[1] for v in triangles)-(hi[other[0]]-lo[other[0]])*(hi[other[1]]-lo[other[1]]))<EPS,'face area mismatch')
            require(len(set(triangles[0][0])|set(triangles[1][0]))==4, 'incomplete face')
        parts[name]={'min':lo,'max':hi,'triangles':len(indices)//3,'vertices':len(points)}
    require(meshes_used==set(range(len(d['meshes']))) and access_used==set(range(len(d['accessors']))) and view_used==set(range(len(d['bufferViews']))),'unused/hidden mesh data')
    return {'parts':dict(sorted(parts.items())), 'triangles':sum(p['triangles'] for p in parts.values()),
            'bytes':len(raw),'asset_sha256':bytes_ref(raw)}


def semantic_checks(observed: dict, imported: dict | None, request: dict) -> dict:
    parts=observed['parts']; expected=expected_bounds()
    checks={'all_parts':set(parts)==set(expected), 'triangle_budget':observed['triangles']==108}
    for name,(lo,hi) in expected.items():
        checks['bounds:'+name]=name in parts and close(parts[name]['min'],lo) and close(parts[name]['max'],hi)
    if imported is None:
        return {'status':'INDETERMINATE','detail':{'reason':'missing_independent_import_observations','checks':checks}}
    keys(imported, {'schema','request','asset_sha256','engine_version','parts','rays'})
    require(imported['schema']=='ciw.workbench-import.v1' and imported['request']==request and imported['asset_sha256']==observed['asset_sha256'], 'import identity mismatch')
    require(type(imported['engine_version']) is str and imported['engine_version']=='4.5.1-stable (official)','unqualified importer version')
    ip=imported['parts'];require(type(ip) is dict and len(ip)<=12,'import table budget')
    checks['import_parts']=set(ip)==set(parts)
    for name,p in parts.items():
        if name not in ip: checks['import:'+name]=False;continue
        q=ip[name];keys(q,{'min','max','vertices','triangles'})
        checks['import:'+name]=(close(vec(q['min']),p['min']) and close(vec(q['max']),p['max']) and q['triangles']==p['triangles'] and q['vertices']==p['vertices'])
    rays=imported['rays'];require(type(rays) is list and len(rays)==6,'import ray coverage')
    probes=[([0,1.5,0],[0,.5,0],'top',[0,.9,0]),
            ([-.76,.1,-1],[-.76,.1,0],'leg_0',[-.76,.1,-.29]),
            ([.76,.1,-1],[.76,.1,0],'leg_1',[.76,.1,-.29]),
            ([-.76,.1,1],[-.76,.1,0],'leg_2',[-.76,.1,.29]),
            ([.76,.1,1],[.76,.1,0],'leg_3',[.76,.1,.29]),
            ([2,1.5,0],[2,-.2,0],None,None)]
    for i,(r,(start,end,name,p)) in enumerate(zip(rays,probes)):
        keys(r,{'from','to','hit','position','name'})
        require(type(r['hit']) is bool and close(vec(r['from']),start) and close(vec(r['to']),end),'changed physical probe')
        checks['ray:'+str(i)]=(r['hit']==(name is not None) and r['name']==name and
            (r['position'] is None if p is None else r['position'] is not None and close(vec(r['position']),p)))
    return {'status':'PASS' if all(checks.values()) else 'FAIL','detail':{'checks':checks,
        'scope':'technical static visual prop and six mesh-ray checks; not art approval, gameplay collision, structural safety or release'}}
