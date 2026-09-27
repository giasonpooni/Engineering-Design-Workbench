extends Control
## Optional 2-node rectangle schematic + residual bar (FSRT/CSE style).
## Presentation only — does not compute balance or quantities.
const Kit = preload("res://scripts/presentation_kit.gd")

var _nodes: Array = []  # [{name, level 0..1, original 0..1}]
var _residual := 0.0  # 0..1 normalized display
var _stale := true
var _caption := ""


func _ready() -> void:
	custom_minimum_size = Vector2(280, 180)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func clear_view() -> void:
	_nodes.clear()
	_residual = 0.0
	queue_redraw()


func set_nodes(nodes: Array, residual_norm: float = 0.0) -> void:
	_nodes = nodes
	_residual = clampf(residual_norm, 0.0, 1.0)
	queue_redraw()


func set_stale(value: bool) -> void:
	_stale = value
	queue_redraw()


func set_caption(text: String) -> void:
	_caption = text
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Kit.BG, true)
	var margin := 24.0
	var area := Rect2(margin, margin, size.x - margin * 2.0, size.y - margin * 2.0)
	draw_rect(area, Kit.PANEL, true)
	if _nodes.is_empty():
		draw_string(ThemeDB.fallback_font, area.position + Vector2(8, 20), "NO SCHEMATIC", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Kit.MUTED)
		return
	var count := maxi(_nodes.size(), 1)
	var gap := 16.0
	var bar_w := (area.size.x - gap * float(count + 1)) / float(count)
	var max_h := area.size.y * 0.62
	var base_y := area.position.y + area.size.y * 0.78
	for i in range(_nodes.size()):
		var entry: Dictionary = _nodes[i]
		var level := clampf(float(entry.get("level", 0.0)), 0.02, 1.0)
		var original := clampf(float(entry.get("original", level)), 0.02, 1.0)
		var x := area.position.x + gap + float(i) * (bar_w + gap)
		# Original wash
		var oh := original * max_h
		var orect := Rect2(Vector2(x, base_y - oh), Vector2(bar_w, oh))
		draw_rect(orect, Kit.WASH if not _stale else Kit.STEEL, true)
		# Display level
		var h := level * max_h
		var fill := Kit.STEEL if _stale else Kit.TEAL
		var drect := Rect2(Vector2(x + bar_w * 0.18, base_y - h), Vector2(bar_w * 0.64, h))
		draw_rect(drect, fill, true)
		draw_rect(Rect2(Vector2(x, base_y - max_h), Vector2(bar_w, max_h)), Kit.AXIS, false, 1.0)
		var name := str(entry.get("name", "n%d" % i))
		draw_string(ThemeDB.fallback_font, Vector2(x, base_y + 16), name, HORIZONTAL_ALIGNMENT_LEFT, int(bar_w), 11, Kit.LABEL)
	# Residual bar under nodes
	var r_y := area.position.y + area.size.y * 0.88
	var r_w := area.size.x * 0.5
	var r_x := area.position.x + (area.size.x - r_w) * 0.5
	draw_rect(Rect2(Vector2(r_x, r_y), Vector2(r_w, 8)), Kit.AXIS, true)
	var fill_c := Kit.AMBER if not _stale else Kit.STEEL
	draw_rect(Rect2(Vector2(r_x, r_y), Vector2(r_w * _residual, 8)), fill_c, true)
	draw_string(ThemeDB.fallback_font, Vector2(r_x, r_y - 4), "residual", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Kit.MUTED)
	if not _caption.is_empty():
		draw_string(ThemeDB.fallback_font, area.position + Vector2(4, 14), _caption, HORIZONTAL_ALIGNMENT_LEFT, int(area.size.x - 8), 10, Kit.MUTED)
