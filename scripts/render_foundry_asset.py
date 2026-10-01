"""Render actual exported/rejected GLBs in a separate Godot preview, not generated art.

Run under Xvfb/Mesa in CI. Captures are inspection aids, not acceptance or GPU
performance evidence. This creates no 1792 scene or live game state.
"""
from pathlib import Path
import argparse
import tempfile
import shutil
from ciw.interactive_simulation import run_process
from ciw.foundry_asset_inspector import PROJECT
from ciw.foundry_asset_contract import OUTPUT

SCRIPT = r'''extends SceneTree
func _initialize() -> void:
    run.call_deferred()
func run() -> void:
    root.size=Vector2i(1280,720)
    var args:=OS.get_cmdline_user_args()
    var doc:=GLTFDocument.new();var state:=GLTFState.new()
    if doc.append_from_file(args[0],state)!=OK:
        push_error("preview import failed");quit(2);return
    var world:=Node3D.new();root.add_child(world)
    var environment:=WorldEnvironment.new();var env:=Environment.new()
    env.background_mode=Environment.BG_COLOR;env.background_color=Color("212a33")
    env.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color=Color("dce6ef");env.ambient_light_energy=0.55
    environment.environment=env;world.add_child(environment)
    var light:=DirectionalLight3D.new();light.rotation_degrees=Vector3(-55,-35,0)
    light.light_energy=1.6;light.shadow_enabled=true;world.add_child(light)
    var floor:=MeshInstance3D.new();var plane:=PlaneMesh.new();plane.size=Vector2(200,200);floor.mesh=plane
    var mat:=StandardMaterial3D.new();mat.albedo_color=Color("485662");mat.roughness=0.95
    floor.material_override=mat;floor.position.y=-0.012;world.add_child(floor)
    var asset:=doc.generate_scene(state);world.add_child(asset)
    var camera:=Camera3D.new();camera.fov=40;world.add_child(camera)
    camera.position=Vector3(2.7,1.95,2.6);camera.look_at(Vector3(0,.45,0));camera.current=true
    var canvas:=CanvasLayer.new();root.add_child(canvas)
    var panel:=PanelContainer.new();panel.position=Vector2(32,26);panel.size=Vector2(1216,92);canvas.add_child(panel)
    var label:=Label.new();label.text="  NOTATIONS / FOUNDRY ASSET WORKER\n  "+args[2]+"  |  Original workbench blockout  |  Blender GLB -> Godot"
    label.add_theme_font_size_override("font_size",24);panel.add_child(label)
    var note:=Label.new();note.position=Vector2(34,650);note.add_theme_font_size_override("font_size",19)
    note.text="1.8 m x 0.7 m x 0.9 m target  /  Y-up metres  /  no historical or final-art approval";canvas.add_child(note)
    for _i in range(12): await process_frame
    await RenderingServer.frame_post_draw
    var image:=root.get_texture().get_image()
    if image.is_empty() or image.save_png(args[1])!=OK:
        push_error("preview capture failed");quit(2);return
    world.queue_free();canvas.queue_free();await process_frame
    print("ASSET_PREVIEW_WRITTEN");quit(0)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',required=True,type=Path)
    parser.add_argument('--qualification',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=False)
    for label,path,title in [('accepted',args.qualification/'accepted/candidate'/OUTPUT,'ACCEPTED TECHNICAL CANDIDATE'),
                             ('rejected',args.qualification/'rejected-three-leg.glb','REJECTED / MISSING FOURTH LEG')]:
        with tempfile.TemporaryDirectory(prefix='net-asset-preview-') as t:
            root=Path(t);(root/'preview.gd').write_text(SCRIPT);(root/'project.godot').write_bytes(PROJECT)
            shutil.copyfile(path,root/'asset.glb')
            image=(args.output_dir/(label+'.png')).resolve()
            run_process([str(args.godot.resolve()),'--path',str(root),'--rendering-method','gl_compatibility',
                '--audio-driver','Dummy','--script','res://preview.gd','--',str(root/'asset.glb'),str(image),title],root,[image],timeout=60)
            for stream in ['stdout','stderr']:
                raw=(root/(stream+'.log')).read_bytes();(args.output_dir/(label+'.'+stream+'.log')).write_bytes(raw)
                if b'ERROR:' in raw:raise RuntimeError('preview reported engine error')
    print('FOUNDRY_ASSET_PREVIEWS: 2 written; 0 failures')


if __name__=='__main__':main()
