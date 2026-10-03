extends Node3D
var rule = preload("res://motion.gd").new()
var target := 0.0
var height := 0.0
func _physics_process(delta: float) -> void:
	if Input.is_action_just_pressed("ui_accept"):
		target = 0.0 if target > 0.0 else 2.0
	height = rule.integrate(height, target, delta)
	get_node("Platform").position.y = height + 0.3
