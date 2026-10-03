"""Closed comparison profile: the unchanged accepted-bench game revision.

Hashes bind source bytes, not a claim that the original game has been released.
Backend settings exist only in disposable copies. No implicit latest/default engine.
"""
import json

GAME_COMMIT = '4869eac467288b99c32268df99d4a06e573fb28d'
GAME_TREE = '5b995b9672af56a070fd1c9ea919832a15df03e2'
INVENTORY = 'sha256:6273a812b038e9b6395ce5671317f9304a3bae6a6c058888566fc42f533a707b'
ENGINE = 'sha256:db07cae7de644278a1884d4552bdf2bca3f5d30131b18faf3a0c4d730080b199'
ENGINE_BUILD = 'f62fdbde15035c5576dad93e586201f4d41ef0cb'
BACKENDS = {'godot': 'GodotPhysics3D', 'jolt': 'Jolt Physics'}
PROFILE = '1792.accepted-bench-backends.v1'
# Exact inherited completion expectations at GAME_COMMIT. These are not rewritten.
SUITES = (
 ('command-story', 'test_command_story.gd', 'COMMAND_STORY_TESTS', 202),
 ('houses', 'test_house_reporting.gd', 'HOUSE_CONFLICT_TESTS', 272),
 ('riding', 'test_riding.gd', 'RIDING_TESTS', 177),
 ('companions', 'test_companions.gd', 'COMPANION_TESTS', 229),
 ('character-names', 'test_character_names.gd', 'CHARACTER_NAMES_TESTS', 56),
 ('childhood', 'test_childhood.gd', 'CHILDHOOD_TESTS', 110),
 ('aftermath', 'test_aftermath.gd', 'AFTERMATH_TESTS', 164),
 ('fixed-interlude', 'test_fixed_interlude.gd', 'FIXED_INTERLUDE_TESTS', 89),
 ('gujranwala', 'test_gujranwala.gd', 'GUJRANWALA_TESTS', 135),
 ('remounts', 'test_remounts.gd', 'REMOUNTS_TESTS', 184),
 ('fabric', 'test_gujranwala_fabric.gd', 'GUJRANWALA_FABRIC_TESTS', 30),
 ('town', 'test_town.gd', 'TOWN_TESTS', 142),
 ('workshop', 'test_workshop.gd', 'WORKSHOP_TESTS', 200),
 ('bench', 'test_workbench_integration.gd', 'BENCH_INTEGRATION_TESTS', 106),
)
POLICY = {'profile': PROFILE, 'source_inventory_id': INVENTORY, 'engine_sha256': ENGINE,
          'physics_hz': 60, 'suite_count': 14, 'assertions_per_pass': 2096,
          'all_suites_required': True, 'cross_backend_exact_trajectory_required': False,
          'automatic_migration': False}
MAX_CAPTURE = 3 * 1024 * 1024
MAX_LOG = 65536

def override(backend):
    if backend not in BACKENDS:
        raise ValueError('Use godot or jolt; DEFAULT, Dummy and arbitrary settings refuse')
    return ('[physics]\n3d/physics_engine='+json.dumps(BACKENDS[backend])+
            '\ncommon/physics_ticks_per_second=60\n'
            '[autoload]\nBackendObserver="*res://backend-observer.gd"\n').encode()

# Observer is instrumentation, not a new game clock/controller. Its autoload is
# selected by the operator-side temporary override, never installed in the game.
OBSERVER = r'''extends Node
var request: Dictionary
var observations: Dictionary
func _ready() -> void:
    request=JSON.parse_string(FileAccess.get_file_as_string("res://backend-request.json"))
    var settings: Dictionary={}
    var options: String=""
    for entry in ProjectSettings.get_property_list():
        if entry.name.begins_with("physics/"):
            settings[entry.name]=ProjectSettings.get_setting_with_override(entry.name)
        if entry.name=="physics/3d/physics_engine": options=entry.hint_string
    observations={"schema":"ciw.physics-backend-observer.v1","request":request,
        "engine":Engine.get_version_info(),"backend":ProjectSettings.get_setting_with_override("physics/3d/physics_engine"),
        "registered_backends":options,"physics_hz":Engine.physics_ticks_per_second,
        "settings":settings,"user_data_dir":OS.get_user_data_dir(),"completed":false}
    _write()
func _exit_tree() -> void:
    if observations.is_empty(): return
    observations.completed=true
    _write()
func _write() -> void:
    var file:=FileAccess.open("user://backend-observer.json",FileAccess.WRITE)
    if file!=null:
        file.store_string(JSON.stringify(observations,"",true,true));file.flush();file.close()
'''

# A separate tiny calibration scene corroborates backend selection behavior. It
# does not enter the game test world: Godot reports the mesh face index, whereas
# default Jolt returns -1. This is a version-specific signature, not attestation.
PROBE = r'''extends SceneTree
func _initialize() -> void: run.call_deferred()
func run() -> void:
    var world:=Node3D.new();root.add_child(world)
    var body:=StaticBody3D.new();world.add_child(body)
    var shape:=CollisionShape3D.new();var mesh:=BoxMesh.new();mesh.size=Vector3(2,.2,2)
    shape.shape=mesh.create_trimesh_shape();body.add_child(shape)
    for _i in range(8): await physics_frame
    await process_frame
    var ray:=PhysicsRayQueryParameters3D.create(Vector3(0,1,0),Vector3(0,-1,0))
    var hit:=world.get_world_3d().direct_space_state.intersect_ray(ray)
    var request: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://backend-request.json"))
    var result: Dictionary={"schema":"ciw.physics-backend-probe.v1","request":request,"hit":not hit.is_empty(),
        "face_index":hit.get("face_index",-999),"position":null,
        "backend":ProjectSettings.get_setting_with_override("physics/3d/physics_engine")}
    if not hit.is_empty(): result.position=[hit.position.x,hit.position.y,hit.position.z]
    var file:=FileAccess.open("user://backend-probe.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(result,"",true,true));file.close()
    world.queue_free();await process_frame;quit(0)
'''
