extends RefCounted
## Shared presentation helpers for host-render JSON viewers.
## Provider-neutral: Godot and Bevy both project the same retained render JSON.
## Meshes/cards do not compute science. Never paint VERIFIED unless JSON has
## fresh_verifier_occurrence == true.
class_name PresentationKit

const TEXT := Color("dce6f1")
const MUTED := Color("899cb2")
const TEAL := Color("60dfcd")
const STEEL := Color("537778")
const AMBER := Color("ffcc80")
const WASH := Color(0.24, 0.42, 0.66, 0.36)
const AXIS := Color("4e647e")
const LABEL := Color("a4b4c8")
const BG := Color("0c1521")
const PANEL := Color("101a28")

const CAPTION := "presentation of retained values; meshes do not compute"

const STATUS_VOCAB := [
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
]

const _STATUS_COLORS := {
	"LIVE": TEAL,
	"RECONCILED": TEAL,
	"SATISFIED": TEAL,
	"STALE": AMBER,
	"UNAVAILABLE": AMBER,
	"HELD": AMBER,
	"REQUEST_EVIDENCE": AMBER,
	"HISTORICAL": AMBER,
	"REFUSED": Color("e57373"),
	"VIOLATED": Color("e57373"),
}


static func unshaded(color: Color, transparent: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = color
	if transparent:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return material


static func status_color(status: String) -> Color:
	var key := status.strip_edges().to_upper()
	if _STATUS_COLORS.has(key):
		return _STATUS_COLORS[key]
	return AMBER


static func format_status_label(status: String) -> String:
	var key := status.strip_edges().to_upper()
	if key == "HISTORICAL":
		return "retained_runtime_report_requires_fresh_verification"
	if key.is_empty():
		return "—"
	return key


static func panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL
	style.border_color = Color("273549")
	style.set_border_width_all(1)
	style.set_corner_radius_all(9)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	return style


static func make_label(text: String, font_size: int = 14, color: Color = TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label


static func make_card(title: String, value_label: Label = null) -> Dictionary:
	var card := PanelContainer.new()
	card.add_theme_stylebox_override("panel", panel_style())
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var contents := VBoxContainer.new()
	card.add_child(contents)
	contents.add_child(make_label(title, 11, MUTED))
	var value := value_label if value_label != null else make_label("—", 20)
	value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	contents.add_child(value)
	return {"card": card, "value": value}


static func resolve_render_path(default_relative: String, match_name: String = "") -> String:
	var arguments := OS.get_cmdline_user_args()
	for argument in arguments:
		var text := str(argument)
		var matched := false
		if not match_name.is_empty():
			matched = text.ends_with(match_name) or text.ends_with("/" + match_name)
		elif text.ends_with(".json"):
			matched = true
		if matched:
			if text.is_absolute_path():
				return text
			return ProjectSettings.globalize_path("res://").path_join("..").path_join(text).simplify_path()
	var project_dir := ProjectSettings.globalize_path("res://").rstrip("/")
	return project_dir.path_join(default_relative).simplify_path()


static func load_json(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed


static func apply_stale(controls: Array, stale: bool) -> void:
	var filter := Control.MOUSE_FILTER_IGNORE if stale else Control.MOUSE_FILTER_STOP
	for control in controls:
		if control is Control:
			(control as Control).mouse_filter = filter


static func verification_label(data: Dictionary) -> String:
	## Never paint VERIFIED unless the retained JSON asserts a fresh verifier occurrence.
	if bool(data.get("fresh_verifier_occurrence", false)):
		return "VERIFIED"
	return "VERIFICATION  /  NOT CLAIMED"


static func panel() -> PanelContainer:
	var node := PanelContainer.new()
	node.add_theme_stylebox_override("panel", panel_style())
	return node
