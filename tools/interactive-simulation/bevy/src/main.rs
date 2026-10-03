//! Bounded Bevy ECS-owned projectile. No window, collision solver, or NET runtime.
//! gltf-rs imports mesh coordinates into this headless adapter; this is explicitly
//! not a claim of testing Bevy's renderer or GltfPlugin asset pipeline.
use bevy_ecs::prelude::*;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, error::Error, fs, io::Write};

const PIN: &str = "bevy-ecs@0f38358f573a7dc6ea961076f6151be662142010";
fn sha(bytes: &[u8]) -> String { format!("sha256:{:x}", Sha256::digest(bytes)) }

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Input { id: String, tick: usize, delta_v_m_s: [f64;3] }
#[derive(Resource, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct Scenario {
    schema: String, name: String, model: String, entity: String, frame: String,
    p0_m: [f64;3], v0_m_s: [f64;3], gravity_m_s2: [f64;3], mass_kg: f64,
    step_hz: usize, ticks: usize, inputs: Vec<Input>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request { schema: String, scenario: Scenario, asset_sha256: String, nonce: String, fault: String }
#[derive(Component)] struct Position([f64;3]);
#[derive(Component)] struct Velocity([f64;3]);
#[derive(Resource)] struct Tick(usize);
#[derive(Resource)] struct GravityFactor(f64);
#[derive(Resource, Default)] struct Trace { observations: Vec<Value>, events: Vec<Value> }

fn apply_inputs(s: Res<Scenario>, tick: Res<Tick>, mut body: Query<&mut Velocity>, mut trace: ResMut<Trace>) {
    for event in s.inputs.iter().filter(|e| e.tick == tick.0) {
        for mut velocity in &mut body {
            for i in 0..3 { velocity.0[i] += event.delta_v_m_s[i]; }
        }
        trace.events.push(json!({"id": event.id, "requested_tick": event.tick,
                                 "applied_tick": tick.0, "delta_v_m_s": event.delta_v_m_s}));
    }
}
fn integrate(s: Res<Scenario>, factor: Res<GravityFactor>, mut body: Query<(&mut Position, &mut Velocity)>) {
    let dt = 1.0 / s.step_hz as f64;
    for (mut p, mut v) in &mut body {
        for i in 0..3 {
            v.0[i] += factor.0*s.gravity_m_s2[i]*dt;
            p.0[i] += v.0[i]*dt;
        }
    }
}
fn observe(s: Res<Scenario>, tick: Res<Tick>, body: Query<(&Position, &Velocity)>, mut trace: ResMut<Trace>) {
    for (p, v) in &body {
        trace.observations.push(json!({"tick": tick.0, "time_s": tick.0 as f64/s.step_hz as f64,
                                      "entity": s.entity, "p_m": p.0, "v_m_s": v.0}));
    }
}
fn import_geometry(raw: &[u8]) -> Result<Value, Box<dyn Error>> {
    let glb = gltf::Gltf::from_slice(raw)?;
    let bin = glb.blob.as_deref().ok_or("GLB has no embedded buffer")?;
    let mut landmarks = BTreeMap::new();
    let mut count = 0usize;
    let mut lo = [f64::INFINITY;3];
    let mut hi = [f64::NEG_INFINITY;3];
    for node in glb.nodes() {
        let name = node.name().unwrap_or("");
        if ["origin", "axis_x", "axis_y", "axis_z"].contains(&name) {
            let (translation, _, _) = node.transform().decomposed();
            landmarks.insert(name.to_owned(), translation);
        }
        if name == "projectile" {
            let mesh = node.mesh().ok_or("projectile is not a mesh")?;
            for primitive in mesh.primitives() {
                let reader = primitive.reader(|buffer| match buffer.source() {
                    gltf::buffer::Source::Bin => Some(bin), _ => None
                });
                for vertex in reader.read_positions().ok_or("mesh has no positions")? {
                    count += 1;
                    for i in 0..3 { lo[i] = lo[i].min(vertex[i] as f64); hi[i] = hi[i].max(vertex[i] as f64); }
                }
            }
        }
    }
    if count < 20 || count > 10000 || landmarks.len() != 4 { return Err("unsupported scene geometry".into()); }
    Ok(json!({"landmarks_m": landmarks, "vertex_count": count, "bounds_min_m": lo, "bounds_max_m": hi}))
}
fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() != 3 { return Err("expected request.json scene.glb trace.json".into()); }
    if fs::metadata(&args[0])?.len() > 8*1024*1024 || fs::metadata(&args[1])?.len() > 2*1024*1024 {
        return Err("input byte budget exceeded".into());
    }
    let raw = fs::read(&args[0])?;
    let request: Request = serde_json::from_slice(&raw)?;
    let s = request.scenario;
    if request.schema != "ciw.projectile-request.v1" || request.nonce.len() != 32 || s.schema != "ciw.projectile-scenario.v1"
        || s.model != "point-projectile-no-contact.v1" || s.entity != "projectile" || s.frame != "local-y-up-m"
        || s.name.is_empty() || !s.mass_kg.is_finite() || s.mass_kg <= 0.0 || s.step_hz < 30 || s.step_hz > 1000
        || s.ticks < 1 || s.ticks > 2000 || s.inputs.len() > 128 { return Err("unsupported scenario".into()); }
    let asset = fs::read(&args[1])?;
    let asset_digest = sha(&asset);
    if asset_digest != request.asset_sha256 { return Err("asset binding mismatch".into()); }
    let geometry = import_geometry(&asset)?;
    let factor = match request.fault.as_str() { "none" => 1.0, "double-gravity" => 2.0, _ => return Err("unsupported fault".into()) };
    let mut world = World::new();
    world.spawn((Position(s.p0_m), Velocity(s.v0_m_s)));
    world.insert_resource(s.clone());
    world.insert_resource(Tick(0));
    world.insert_resource(GravityFactor(factor));
    world.insert_resource(Trace::default());
    let mut initial = Schedule::default();
    initial.add_systems(observe);
    initial.run(&mut world);
    let mut schedule = Schedule::default();
    schedule.add_systems((apply_inputs, integrate, observe).chain());
    for tick in 1..=s.ticks {
        world.resource_mut::<Tick>().0 = tick;
        schedule.run(&mut world);
    }
    let trace = world.resource::<Trace>();
    let result = json!({"engine": "bevy", "engine_version": PIN, "state_owner": "bevy",
        "clock": "integer-ticks", "phase": "initial_then_post_step", "precision": "f64",
        "request_sha256": sha(&raw), "asset_sha256": asset_digest, "import_report": geometry,
        "observations": trace.observations, "events": trace.events, "complete": true});
    let mut file = fs::OpenOptions::new().write(true).create_new(true).open(&args[2])?;
    file.write_all(&serde_json::to_vec(&result)?)?;
    file.sync_all()?;
    Ok(())
}
fn main() {
    if let Err(error) = run() { eprintln!("{error}"); std::process::exit(2); }
}
