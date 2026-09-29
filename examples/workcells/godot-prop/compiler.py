"""Original bounded mesh compiler example; candidate-editable, executed only in a cell.

Not a historical reconstruction. Input length unit is one engine metre.
"""
import json
from pathlib import Path

spec = json.loads(Path('spec.json').read_text())
x, y, z = [float(v) / 2.0 for v in spec['size']]
vertices = [[-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],
            [-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]]
triangles = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
             [3,7,6],[3,6,2],[0,4,7],[0,7,3],[1,2,6],[1,6,5]]
Path('mesh.json').write_text(json.dumps({'vertices':vertices,'triangles':triangles}))
