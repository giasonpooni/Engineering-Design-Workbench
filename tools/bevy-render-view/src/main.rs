//! Thin Bevy projector for CIW host render JSON.
//!
//! Same retained record as Godot tabs (Analog / Fluid / Geodesic / BIM / Proof).
//! Neither engine computes science. No CIW viewport kind. Never treat a report
//! as VERIFIED unless `fresh_verifier_occurrence` is true in JSON.
//!
//! Status vocab (shared with Godot PresentationKit):
//! LIVE, STALE, UNAVAILABLE, REFUSED, HELD, RECONCILED, SATISFIED, VIOLATED,
//! REQUEST_EVIDENCE, HISTORICAL
//! HISTORICAL display → retained_runtime_report_requires_fresh_verification
//!
//! Bevy pin: giasonpooni/bevy @ 0f38358f573a7dc6ea961076f6151be662142010
//! Local checkout: /workspace/bevy (patched via .cargo/config.toml). Do not
//! patch instrument tabs into the engine tree.

use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

use bevy::prelude::*;
use serde_json::Value;

const CAPTION: &str = "presentation of retained values; meshes do not compute";

const STATUS_VOCAB: &[&str] = &[
    "LIVE",
    "STALE",
    "UNAVAILABLE",
    "REFUSED",
    "HELD",
    "RECONCILED",
    "SATISFIED",
    "VIOLATED",
    "REQUEST_EVIDENCE",
    "HISTORICAL",
];

/// Night-ish clear, aligned with Godot house clear Color(0.031, 0.047, 0.071).
const CLEAR: Color = Color::srgb(0.031, 0.047, 0.071);
const LIVE_PATH: Color = Color::srgb(0.376, 0.875, 0.804); // 60dfcd
const GAP_PATH: Color = Color::srgb(0.498, 0.608, 0.722); // 7f9bb8
const AXIS: Color = Color::srgb(0.306, 0.392, 0.494); // 4e647e

#[derive(Resource, Clone)]
struct RenderPayload {
    path: PathBuf,
    data: Option<Value>,
    missing: bool,
}

fn format_status_label(status: &str) -> String {
    let key = status.trim().to_uppercase();
    if key == "HISTORICAL" {
        "retained_runtime_report_requires_fresh_verification".to_string()
    } else if key.is_empty() {
        "—".to_string()
    } else {
        key
    }
}

fn verification_label(data: &Value) -> &'static str {
    if data
        .get("fresh_verifier_occurrence")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        "VERIFIED"
    } else {
        "VERIFICATION  /  NOT CLAIMED"
    }
}

fn load_json(path: &PathBuf) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", path.display()))
}

fn summarize(path: &PathBuf, data: &Value) {
    println!("bevy-render-view  (presentation only)");
    println!("path={}", path.display());
    println!("caption_constant={CAPTION}");
    println!(
        "schema={}",
        data.get("schema").and_then(|v| v.as_str()).unwrap_or("—")
    );
    println!(
        "source={}",
        data.get("source").and_then(|v| v.as_str()).unwrap_or("—")
    );
    println!(
        "claim_scope={}",
        data.get("claim_scope")
            .and_then(|v| v.as_str())
            .unwrap_or("computational-integrity-only")
    );
    println!(
        "may_authorize={}",
        data.get("may_authorize")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    );
    let status = data
        .get("status")
        .or_else(|| data.get("upstream_status"))
        .and_then(|v| v.as_str())
        .unwrap_or("STALE");
    println!("status={}", format_status_label(status));
    println!("verification={}", verification_label(data));
    println!("status_vocab={}", STATUS_VOCAB.join(","));
    if let Some(cards) = data.get("cards") {
        match cards {
            Value::Array(items) => println!("cards_count={}", items.len()),
            Value::Object(map) => {
                println!(
                    "cards_keys={}",
                    map.keys().cloned().collect::<Vec<_>>().join(",")
                )
            }
            _ => println!("cards=present"),
        }
    } else if let Some(cases) = data.get("cases").and_then(|v| v.as_array()) {
        println!("cases_count={}", cases.len());
    } else {
        println!("cards=absent");
    }
    println!("note=Bevy does not call Godot; Godot does not call Bevy; no CIW viewport kind");
}

fn print_stale(path: &PathBuf) {
    println!("bevy-render-view");
    println!("path={}", path.display());
    println!("status={}", format_status_label("STALE"));
    println!("verification=VERIFICATION  /  NOT CLAIMED");
    println!("detail=render JSON missing");
    println!("caption_constant={CAPTION}");
}

fn card_lines(data: &Value) -> Vec<String> {
    let mut lines = Vec::new();
    let status = data
        .get("status")
        .or_else(|| data.get("upstream_status"))
        .and_then(|v| v.as_str())
        .unwrap_or("STALE");
    lines.push(format!("status  {}", format_status_label(status)));
    lines.push(format!("verify  {}", verification_label(data)));
    lines.push(CAPTION.to_string());
    if let Some(Value::Array(cards)) = data.get("cards") {
        for card in cards.iter().take(12) {
            let label = card
                .get("label")
                .or_else(|| card.get("name"))
                .or_else(|| card.get("key"))
                .and_then(|v| v.as_str())
                .unwrap_or("card");
            let value = card
                .get("value")
                .or_else(|| card.get("text"))
                .map(|v| match v {
                    Value::String(s) => s.clone(),
                    other => other.to_string(),
                })
                .unwrap_or_else(|| "—".to_string());
            lines.push(format!("{label}  {value}"));
        }
    } else if let Some(Value::Object(map)) = data.get("cards") {
        for (k, v) in map.iter().take(12) {
            lines.push(format!("{k}  {v}"));
        }
    }
    lines
}

fn points_from_traj(data: &Value, key: &str) -> Vec<Vec3> {
    let Some(traj) = data.get("trajectories").and_then(|t| t.get(key)) else {
        return Vec::new();
    };
    let arr = if let Some(a) = traj.as_array() {
        a
    } else if let Some(a) = traj.get("points").and_then(|p| p.as_array()) {
        a
    } else {
        return Vec::new();
    };
    arr.iter()
        .filter_map(|p| {
            let coords = p.as_array()?;
            if coords.len() < 3 {
                return None;
            }
            Some(Vec3::new(
                coords[0].as_f64()? as f32,
                coords[1].as_f64()? as f32,
                coords[2].as_f64()? as f32,
            ))
        })
        .collect()
}

fn setup(mut commands: Commands, payload: Res<RenderPayload>) {
    commands.spawn((
        Camera3d::default(),
        Transform::from_xyz(2.8, 2.2, 4.2).looking_at(Vec3::ZERO, Vec3::Y),
    ));

    let hud = if payload.missing {
        format!(
            "bevy-render-view\npath={}\nstatus=STALE\ndetail=render JSON missing\n{CAPTION}",
            payload.path.display()
        )
    } else if let Some(ref data) = payload.data {
        let mut body = format!(
            "bevy-render-view\npath={}\n",
            payload.path.display()
        );
        body.push_str(&card_lines(data).join("\n"));
        body
    } else {
        format!("bevy-render-view\nstatus=STALE\n{CAPTION}")
    };

    commands.spawn((
        Text::new(hud),
        Node {
            position_type: PositionType::Absolute,
            top: px(12),
            left: px(12),
            ..default()
        },
    ));
}

fn draw_paths(mut gizmos: Gizmos, payload: Res<RenderPayload>) {
    // Axes (presentation only).
    gizmos.line(Vec3::ZERO, Vec3::X, AXIS);
    gizmos.line(Vec3::ZERO, Vec3::Y, AXIS);
    gizmos.line(Vec3::ZERO, Vec3::Z, AXIS);

    let Some(ref data) = payload.data else {
        return;
    };

    let live = points_from_traj(data, "live");
    let gap = points_from_traj(data, "gap");
    // Fallbacks used by analog_render.json
    let live = if live.is_empty() {
        points_from_traj(data, "renewal")
    } else {
        live
    };
    let live = if live.is_empty() {
        points_from_traj(data, "theta0")
    } else {
        live
    };
    let gap = if gap.is_empty() {
        let g = points_from_traj(data, "theta1");
        if g.is_empty() {
            points_from_traj(data, "gap_path")
        } else {
            g
        }
    } else {
        gap
    };

    for window in live.windows(2) {
        gizmos.line(window[0], window[1], LIVE_PATH);
    }
    for window in gap.windows(2) {
        gizmos.line(window[0], window[1], GAP_PATH);
    }

    // Optional polyline under series.primary / path
    if live.is_empty() && gap.is_empty() {
        if let Some(series) = data.get("series").and_then(|s| s.as_array()) {
            for series_item in series.iter().take(2) {
                let pts = series_item
                    .get("points")
                    .and_then(|p| p.as_array())
                    .into_iter()
                    .flatten()
                    .filter_map(|p| {
                        let c = p.as_array()?;
                        if c.len() < 2 {
                            return None;
                        }
                        Some(Vec3::new(
                            c[0].as_f64()? as f32,
                            c.get(1).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
                            c.get(2).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
                        ))
                    })
                    .collect::<Vec<_>>();
                for window in pts.windows(2) {
                    gizmos.line(window[0], window[1], LIVE_PATH);
                }
            }
        }
    }
}

fn run_window(payload: RenderPayload) {
    App::new()
        .insert_resource(ClearColor(CLEAR))
        .insert_resource(payload)
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                title: "bevy-render-view (presentation only)".into(),
                resolution: (1280, 800).into(),
                ..default()
            }),
            ..default()
        }))
        .add_systems(Startup, setup)
        .add_systems(Update, draw_paths)
        .run();
}

fn main() -> ExitCode {
    let mut args = env::args().skip(1).collect::<Vec<_>>();
    if args.is_empty() {
        eprintln!(
            "usage: bevy-render-view [--summary] <path-to-*-render.json>\n\
             Reads the same host render JSON as Godot. Missing file → STALE.\n\
             Default: Bevy window (night clear, path gizmos, card text).\n\
             --summary: print cards/status to stdout only (no window)."
        );
        return ExitCode::from(2);
    }
    if args.first().map(String::as_str) == Some("--") {
        args.remove(0);
    }
    let summary_only = args.first().map(String::as_str) == Some("--summary");
    if summary_only {
        args.remove(0);
    }
    if args.is_empty() {
        eprintln!("missing render JSON path");
        return ExitCode::from(2);
    }
    let path = PathBuf::from(&args[0]);
    if !path.exists() {
        print_stale(&path);
        if summary_only {
            return ExitCode::from(1);
        }
        run_window(RenderPayload {
            path,
            data: None,
            missing: true,
        });
        return ExitCode::from(1);
    }
    match load_json(&path) {
        Ok(data) => {
            summarize(&path, &data);
            if summary_only {
                return ExitCode::SUCCESS;
            }
            run_window(RenderPayload {
                path,
                data: Some(data),
                missing: false,
            });
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("STALE: {err}");
            ExitCode::from(1)
        }
    }
}
