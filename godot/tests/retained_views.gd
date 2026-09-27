extends SceneTree
## Render actual Python projections. JSON here is display data, never an export.
const View = preload("res://scripts/experiment_view.gd")

class Reader extends "res://scripts/ciw_client.gd":
	func _request(_kind: String, _payload: Dictionary = {}) -> String:
		return ""


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var paths := OS.get_cmdline_user_args()
	if paths.is_empty():
		push_error("Provide actual experiment.inspect JSON paths after --")
		quit(1)
		return
	var reader := Reader.new()
	reader.online = true
	var view := View.new()
	root.add_child(view)
	view.attach(reader)
	var revision := 0
	for path in paths:
		var value = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not value is Dictionary or value.get("schema") != "ciw.experiment-view.v1":
			push_error("Invalid projection: " + path)
			quit(1)
			return
		revision += 1
		view.apply_snapshot({"session_id": "retained-native-views", "workbench": {
			"revision": revision, "sources": [], "operations": [],
			"bundles": [{"bundle_id": value.bundle_id, "kind": value.kind}]}})
		view.apply_view(value)
		if view.view.get("bundle_id") != value.bundle_id or view._summary.text.is_empty():
			push_error("Selected projection was not rendered: " + path)
			quit(1)
			return
		for i in value.panels.size():
			view._select_panel(i)
			if view._plot.panel != value.panels[i] or view._numbers.text.is_empty():
				push_error("Native panel was not rendered: " + path)
				quit(1)
				return
			var render = value.panels[i].get("render", {})
			if render.get("kind") in ["plane2d", "mesh", "strip"] and view._plot.panel.get("render", {}).get("kind") != render.kind:
				push_error("Presentation render was not applied: " + path)
				quit(1)
				return
			if value.get("system_render", {}).get("kind") == "mesh" and not view._system.visible:
				push_error("View system canvas was not applied: " + path)
				quit(1)
				return
			if value.get("system_render", {}).get("kind") == "mesh":
				var caption := ""
				if view._system._caption != null:
					caption = str(view._system._caption.text)
				if caption.is_empty():
					push_error("Mesh canvas identity was not labeled: " + path)
					quit(1)
					return
				var source := str(value.get("system_render", {}).get("source_label", ""))
				if not source.is_empty() and not view._numbers.text.contains(source):
					push_error("Mesh source vertex was not listed: " + path)
					quit(1)
					return
				var frame := str(value.get("system_render", {}).get("canvas_id", value.get("system_render", {}).get("frame", "")))
				if not frame.is_empty() and not view._numbers.text.contains(frame):
					push_error("Mesh frame was not listed: " + path)
					quit(1)
					return
			if value.get("system_render", {}).get("kind") in ["plane2d", "strip"] and render.get("kind") != value.system_render.kind:
				if not view._system_plot.visible or view._system_plot.panel.get("render", {}).get("kind") != value.system_render.kind:
					push_error("Companion canvas was not applied: " + path)
					quit(1)
					return
				var canvases = value.get("system_canvases", [])
				if canvases is Array and canvases.size() > 1 and (not view._canvases.visible or view._canvases.item_count != canvases.size()):
					push_error("Declared system canvases were not offered: " + path)
					quit(1)
					return
				if view._system_plot.panel.get("panel_id", "") == "" and value.get("system_canvas_id", "") != "":
					push_error("Companion canvas identity was not labeled: " + path)
					quit(1)
					return
				var ends := str(value.get("system_render", {}).get("start_label", ""))
				if not ends.is_empty() and not view._numbers.text.contains(ends):
					push_error("Companion endpoints were not listed: " + path)
					quit(1)
					return
				if value.get("system_render", {}).get("kind") == "strip":
					var frame := str(value.get("system_render", {}).get("frame", ""))
					if not frame.is_empty() and not view._numbers.text.contains(frame):
						push_error("Strip path frame was not listed: " + path)
						quit(1)
						return
				if value.get("system_render", {}).get("kind") == "plane2d":
					var plane_frame := str(value.get("system_render", {}).get("frame", ""))
					if typeof(value.get("system_render", {}).get("frame", "")) == TYPE_DICTIONARY:
						plane_frame = str(value.system_render.frame.get("id", ""))
					if not plane_frame.is_empty() and not view._numbers.text.contains(plane_frame):
						push_error("Plane declared frame was not listed: " + path)
						quit(1)
						return
				var overlays = value.get("system_render", {}).get("overlays", [])
				if overlays is Array and not overlays.is_empty():
					var constraint := str(overlays[0].get("constraint_id", overlays[0].get("overlay_title", "")))
					if not constraint.is_empty() and not view._numbers.text.contains(constraint):
						push_error("Companion constraint was not listed: " + path)
						quit(1)
						return
		print("PASS: retained ", value.kind, " occurrence; ", value.panels.size(), " panels")
	view.queue_free()
	reader.free()
	print("PASS: all actual retained projections rendered")
	quit(0)
