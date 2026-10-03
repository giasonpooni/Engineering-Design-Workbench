extends RefCounted

# Candidate-owned mechanic. The runtime clock is owned by the scene driver.
func integrate(position: float, target: float, delta: float) -> float:
	return move_toward(position, target, 2.0 * delta)
