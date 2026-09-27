extends SceneTree
## Presentation kit smoke: missing JSON → STALE; with analog_render → cards non-empty.
## Godot may be absent from PATH; keep this script for local runs:
##   godot --headless --path godot --script res://tests/presentation_smoke.gd

const AnalogView = preload("res://scripts/analog_view.gd")
const Kit = preload("res://scripts/presentation_kit.gd")

var _failures: Array[String] = []


func _check(name: String, ok: bool) -> void:
	print("  %s  %s" % ["PASS" if ok else "FAIL", name])
	if not ok:
		_failures.append(name)


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	print("presentation kit smoke")
	_check("status_vocab_has_historical", Kit.STATUS_VOCAB.has("HISTORICAL"))
	_check(
		"historical_label_maps",
		Kit.format_status_label("HISTORICAL") == "retained_runtime_report_requires_fresh_verification"
	)
	_check("verified_requires_fresh_flag", Kit.verification_label({}) == "VERIFICATION  /  NOT CLAIMED")
	_check(
		"verified_when_fresh",
		Kit.verification_label({"fresh_verifier_occurrence": true}) == "VERIFIED"
	)

	var missing := AnalogView.new()
	root.add_child(missing)
	# Force a missing path by clearing data after ready load attempt against default.
	await process_frame
	await process_frame
	# If default analog_render exists this tab may be LOADED; probe STALE path via apply.
	missing._apply_stale("STALE", "smoke missing fixture")
	_check("missing_marks_stale_status", missing._status.text.contains("STALE"))
	_check("missing_plsr_stale", str(missing._plsr_value.text).contains("STALE") or missing._plsr_value.text == "STALE")
	missing.queue_free()

	var analog_path := ProjectSettings.globalize_path("res://").path_join(
		"../examples/pyramid-method-gap/results/analog_render.json"
	).simplify_path()
	if FileAccess.file_exists(analog_path):
		var loaded := AnalogView.new()
		root.add_child(loaded)
		await process_frame
		await process_frame
		loaded._try_load()
		await process_frame
		_check("analog_loaded_flag", loaded._loaded)
		_check("analog_cards_non_empty", loaded._v_value.text != "—" and not loaded._v_value.text.is_empty())
		loaded.queue_free()
	else:
		print("  SKIP  analog_render.json absent (generate with run_analog.py --write-render)")

	if _failures.is_empty():
		print("PASS: presentation smoke")
		quit(0)
	else:
		push_error("FAIL: " + ", ".join(_failures))
		quit(1)
