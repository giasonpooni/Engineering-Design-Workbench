extends VBoxContainer
## Catalog projector for all examples/usecase-* retained render JSON records.
## It discovers files; it never runs a solver, verifies proof, or creates meshes.
const Kit = preload("res://scripts/presentation_kit.gd")

const EXAMPLES_RELATIVE := "../examples"
const FOLDER_PREFIX := "usecase-"

var _status: Label
var _summary: Label
var _path: Label
var _scroll: ScrollContainer
var _cards: VBoxContainer
var _reload: Button


func _ready() -> void:
    add_theme_constant_override("separation", 10)
    _build_ui()
    _try_load()


func _build_ui() -> void:
    var header := HBoxContainer.new()
    header.add_theme_constant_override("separation", 12)
    add_child(header)
    var titles := VBoxContainer.new()
    titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    header.add_child(titles)
    titles.add_child(Kit.make_label("USE-CASE CATALOG  /  9,074 OWNED-FAMILY SCENARIOS", 12, Kit.TEAL))
    titles.add_child(Kit.make_label("Retained render JSON · cards and status", 22))
    titles.add_child(Kit.make_label("Load examples/usecase-index.json paths · presentation only", 12, Kit.MUTED))
    _status = Kit.make_label("●  WAITING", 13, Kit.AMBER)
    _status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    header.add_child(_status)
    _reload = Button.new()
    _reload.text = "Reload"
    _reload.pressed.connect(_try_load)
    header.add_child(_reload)

    _path = Kit.make_label("catalog path —", 11, Kit.MUTED)
    _path.clip_text = true
    add_child(_path)

    var summary_panel := Kit.panel()
    add_child(summary_panel)
    var summary_row := HBoxContainer.new()
    summary_panel.add_child(summary_row)
    _summary = Kit.make_label("Discovering use cases…", 13)
    _summary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    summary_row.add_child(_summary)
    summary_row.add_child(Kit.make_label(Kit.CAPTION, 11, Kit.MUTED))

    _scroll = ScrollContainer.new()
    _scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    add_child(_scroll)
    _cards = VBoxContainer.new()
    _cards.add_theme_constant_override("separation", 8)
    _cards.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    _scroll.add_child(_cards)


func _examples_path() -> String:
    return ProjectSettings.globalize_path("res://").path_join(EXAMPLES_RELATIVE).simplify_path()


func _try_load() -> void:
    for child in _cards.get_children():
        child.queue_free()
    var examples_path := _examples_path()
    _path.text = "catalog path  " + examples_path
    var directory := DirAccess.open(examples_path)
    if directory == null:
        _status.text = "●  " + Kit.format_status_label("STALE")
        _status.add_theme_color_override("font_color", Kit.status_color("STALE"))
        _summary.text = "examples directory unavailable — run from the Godot project"
        return

    var records := _records_from_index(examples_path)
    if records.is_empty():
        # Keep the old discovery path as a local-development fallback when the
        # generated index has not been created yet.
        records = _records_from_scan(examples_path)
    records.sort_custom(_sort_records)

    var counts := {"loaded": 0, "stale": 0}
    for record in records:
        var data: Dictionary = record["data"]
        if data.is_empty():
            counts["stale"] += 1
        else:
            counts["loaded"] += 1
        _cards.add_child(_make_usecase_card(record))
    _summary.text = "%d use-case folders indexed · %d loaded · %d STALE · missing JSON is not an approval" % [records.size(), counts["loaded"], counts["stale"]]
    _status.text = "●  %s" % ("LOADED" if counts["stale"] == 0 else Kit.format_status_label("STALE"))
    _status.add_theme_color_override("font_color", Kit.TEAL if counts["stale"] == 0 else Kit.status_color("STALE"))


func _records_from_index(examples_path: String) -> Array:
    var index_path := examples_path.path_join("usecase-index.json")
    if not FileAccess.file_exists(index_path):
        return []
    var index_data: Dictionary = Kit.load_json(index_path)
    var entries: Variant = index_data.get("entries", [])
    if not (entries is Array):
        return []
    var repo_path := ProjectSettings.globalize_path("res://").path_join("..").simplify_path()
    var records: Array = []
    for item in entries:
        if not item is Dictionary:
            continue
        var relative := str(item.get("render_path", ""))
        var file_path := repo_path.path_join(relative).simplify_path()
        var data: Dictionary = Kit.load_json(file_path) if not relative.is_empty() and FileAccess.file_exists(file_path) else {}
        records.append({
            "folder": "usecase-" + str(item.get("slug", "")),
            "file": file_path.get_file(),
            "path": file_path,
            "data": data,
            "index": item,
        })
    return records


func _records_from_scan(examples_path: String) -> Array:
    var records: Array = []
    var directory := DirAccess.open(examples_path)
    if directory == null:
        return records
    directory.list_dir_begin()
    var folder := directory.get_next()
    while not folder.is_empty():
        if directory.current_is_dir() and folder.begins_with(FOLDER_PREFIX):
            var result_path := examples_path.path_join(folder).path_join("results")
            var result_dir := DirAccess.open(result_path)
            if result_dir != null:
                result_dir.list_dir_begin()
                var file_name := result_dir.get_next()
                while not file_name.is_empty():
                    if not result_dir.current_is_dir() and file_name.ends_with("_render.json"):
                        var file_path := result_path.path_join(file_name)
                        records.append({"folder": folder, "file": file_name, "path": file_path, "data": Kit.load_json(file_path), "index": {}})
                    file_name = result_dir.get_next()
                result_dir.list_dir_end()
        folder = directory.get_next()
    directory.list_dir_end()
    return records


func _sort_records(a: Dictionary, b: Dictionary) -> bool:
    return str(a["folder"]) < str(b["folder"])


func _make_usecase_card(record: Dictionary) -> PanelContainer:
    var data: Dictionary = record["data"]
    var card := Kit.panel()
    card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    var row := HBoxContainer.new()
    row.add_theme_constant_override("separation", 12)
    card.add_child(row)

    var state := _record_status(data)
    var state_label := Kit.make_label(Kit.format_status_label(state), 12, Kit.status_color(state))
    state_label.custom_minimum_size.x = 150
    row.add_child(state_label)

    var details := VBoxContainer.new()
    details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    row.add_child(details)
    var indexed: Dictionary = record.get("index", {})
    var scenario: Dictionary = data.get("scenario", {})
    var title := str(scenario.get("title", indexed.get("title", str(record["folder"]))))
    details.add_child(Kit.make_label(title, 16))
    var lesson := str(scenario.get("lesson", indexed.get("sentence", data.get("caption", "retained presentation"))))
    var source := str(data.get("source", indexed.get("source", "HOST_FROM_OWNED_CONFIG")))
    details.add_child(Kit.make_label("%s  ·  %s" % [lesson, source], 11, Kit.MUTED))
    details.add_child(Kit.make_label("%s/%s" % [str(record["folder"]), str(record["file"])], 10, Kit.MUTED))
    var verify := Kit.verification_label(data)
    var verify_label := Kit.make_label(verify, 10, Kit.AMBER)
    verify_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    row.add_child(verify_label)
    return card


func _record_status(data: Dictionary) -> String:
    if data.is_empty():
        return "STALE"
    var status := str(data.get("status", ""))
    if not status.is_empty() and status != "HOST_FROM_OWNED_CONFIG":
        return status
    var cards: Variant = data.get("cards", [])
    if cards is Array:
        for item in cards:
            if item is Dictionary:
                for key in ["status", "card_status", "disposition"]:
                    var candidate := str(item.get(key, ""))
                    if not candidate.is_empty():
                        return candidate
    var cases: Variant = data.get("cases", [])
    if cases is Array:
        for item in cases:
            if item is Dictionary:
                for key in ["status", "card_status", "disposition"]:
                    var candidate := str(item.get(key, ""))
                    if not candidate.is_empty():
                        return candidate
    return "HOST_FROM_OWNED_CONFIG"
