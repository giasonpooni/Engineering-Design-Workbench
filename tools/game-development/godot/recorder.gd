extends RefCounted
## Selected observations only. No world writes, socket, pause, or hidden runtime control.
## Overflow returns false, counts the loss and marks the exported capture incomplete.

const MAX_SAMPLES := 1024
const MAX_EVENTS := 1024
var samples: Array = []
var events: Array = []
var dropped_samples: int = 0
var dropped_events: int = 0

func sample(tick: int, channel: String, value: Variant) -> bool:
	if samples.size() >= MAX_SAMPLES:
		dropped_samples += 1
		return false
	samples.append({"tick": tick, "channel": channel, "value": value})
	return true

func event(tick: int, kind: String, actor_id: String, target_ids: Array, causes: Array, payload: Dictionary = {}) -> String:
	if events.size() >= MAX_EVENTS:
		dropped_events += 1
		return ""
	var event_id := "event-%d" % events.size()
	events.append({"id": event_id, "tick": tick, "kind": kind, "actor_id": actor_id,
		"target_ids": target_ids.duplicate(), "causes": causes.duplicate(), "payload": payload.duplicate(true)})
	return event_id

func export_trace(request: Dictionary) -> Dictionary:
	return {"schema": "ciw.game-trace.v1", "request_nonce": request["nonce"],
		"scenario_digest": request["scenario_digest"], "engine": "godot",
		"engine_version": Engine.get_version_info()["string"], "samples": samples.duplicate(true),
		"events": events.duplicate(true), "dropped_samples": dropped_samples,
		"dropped_events": dropped_events, "complete": dropped_samples == 0 and dropped_events == 0}
