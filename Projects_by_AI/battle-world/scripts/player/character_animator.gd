extends RefCounted
## Moves a fighter's bones from code, with no animation files: standing, walking,
## running, crouching and jumping.
##
## How it works: one number, `phase`, runs from 0 to 1 for every two steps.
## From the phase we work out where each foot should be, then a small formula
## (two-bone IK) bends hip and knee so the foot reaches that place. The rest of
## the body (hips, spine, arms, head) follows the same phase.
##
## All positions here are in the fighter's own space: -Z forward, +X right, +Y up.

const Rig := preload("res://scripts/player/character_rig.gd")
const B := Rig.B

var rig: Rig
var skeleton: Skeleton3D

# ---- What the owner tells us every frame ----
var velocity := Vector3.ZERO      # x = right, y = up, z = back (metres per second)
var on_floor := true
var crouch := false
var look_pitch := 0.0             # looking up is positive (radians)
var look_yaw := 0.0               # head turned left is positive (radians)

# ---- Our own state ----
var phase := 0.0                  # 0..1 for one left step plus one right step
var _speed := 0.0
var _dir := Vector2(0.0, -1.0)    # travel direction on the ground: x = right, y = back
var _crouch := 0.0
var _air := 0.0
var _drop := 0.0                  # how far the hips sink after a landing
var _drop_speed := 0.0
var _fall_speed := 0.0
var _was_on_floor := true
var _time := 0.0


func setup(p_rig: Rig) -> void:
	rig = p_rig
	skeleton = rig.skeleton


## Jumps straight to the settled pose for the current inputs (used by tests and spawns).
func snap() -> void:
	_speed = Vector2(velocity.x, velocity.z).length()
	if _speed > 0.3:
		_dir = Vector2(velocity.x, velocity.z) / _speed
	_crouch = 1.0 if crouch else 0.0
	_air = 0.0 if on_floor else 1.0
	_drop = 0.0
	_drop_speed = 0.0
	_was_on_floor = on_floor


func update(delta: float) -> void:
	_time += delta
	var planar := Vector2(velocity.x, velocity.z)
	var speed := planar.length()
	_speed = lerpf(_speed, speed, 1.0 - exp(-12.0 * delta))
	if speed > 0.3:
		var mixed := _dir.lerp(planar / speed, 1.0 - exp(-10.0 * delta))
		if mixed.length() > 0.01:
			_dir = mixed.normalized()
	_crouch = move_toward(_crouch, 1.0 if crouch else 0.0, delta * 5.0)
	_air = move_toward(_air, 0.0 if on_floor else 1.0, delta * (9.0 if on_floor else 6.0))

	# Landing: the hips dip and spring back up.
	if on_floor and not _was_on_floor:
		_drop_speed += clampf(_fall_speed * 0.5, 0.0, 5.0)
	if not on_floor:
		_fall_speed = maxf(0.0, -velocity.y)
	_was_on_floor = on_floor
	_drop_speed += (-_drop * 180.0 - _drop_speed * 22.0) * delta
	_drop += _drop_speed * delta

	var run := clampf((_speed - 2.2) / 2.6, 0.0, 1.0)        # 0 = walking, 1 = running
	var sprint := clampf((_speed - 5.4) / 1.4, 0.0, 1.0)
	var moving := smoothstep(0.15, 0.9, _speed)               # 0 = standing still
	var gait := moving * (1.0 - _air)
	# Longer steps at higher speed (numbers picked to match how people walk and run).
	var step_len := (0.38 + 0.26 * _speed - 0.006 * _speed * _speed) * lerpf(1.0, 0.7, _crouch)
	if _speed > 0.05 and on_floor:
		phase = fposmod(phase + _speed / (2.0 * step_len) * delta, 1.0)
	# Share of a step cycle each foot spends on the ground: more when walking, less when running.
	var stance := lerpf(0.60, 0.34, run) - 0.07 * sprint
	var forward := -_dir.y
	var right := _dir.x
	var breathe := sin(_time * 1.7)

	# ---- Where the feet want to be ----
	var foot_pos: Array[Vector3] = [Vector3.ZERO, Vector3.ZERO]
	var foot_pitch: Array[float] = [0.0, 0.0]
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		var left := i == 0
		var p := fposmod(phase + (0.0 if left else 0.5), 1.0)
		var step := _step_foot(side, p, stance, step_len, run, sprint)
		var stagger := (-0.03 - 0.15 * _crouch) if left else (0.04 + 0.13 * _crouch)
		var idle := Vector3(side * lerpf(0.105, 0.16, _crouch), Rig.ANKLE_H, stagger)
		foot_pos[i] = idle.lerp(step[0], moving)
		foot_pitch[i] = step[1] * moving

	# ---- Hips ----
	var hip_h := lerpf(lerpf(0.955, 0.93, run), 0.63, _crouch)
	# Running: lowest when a foot is under the body, highest in the air between steps.
	hip_h -= 0.035 * run * cos(TAU * 2.0 * (phase - stance * 0.5)) * gait
	hip_h += 0.003 * breathe * (1.0 - moving) - 0.02 * sprint
	var sway := -0.02 * cos(TAU * (phase - stance * 0.5)) * gait * (1.0 - 0.6 * run)
	# The hips sink just enough for both feet to reach their places. This is what
	# gives walking its small up-and-down movement.
	var max_leg := Rig.UPPER_LEG + Rig.LOWER_LEG - 0.006
	var reach_limit := 10.0
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		var flat := Vector2(foot_pos[i].x - (side * 0.10 + sway), foot_pos[i].z).length()
		reach_limit = minf(reach_limit, foot_pos[i].y + sqrt(maxf(max_leg * max_leg - flat * flat, 0.01)) + 0.04)
	var soft := 0.012
	var limited := -soft * log(exp(-hip_h / soft) + exp(-reach_limit / soft))
	hip_h = lerpf(limited, hip_h, _air) - _drop

	var twist := -deg_to_rad(lerpf(5.0, 9.0, run)) * cos(TAU * phase) * gait
	var roll := -deg_to_rad(lerpf(3.0, 2.0, run)) * cos(TAU * (phase - stance * 0.5)) * gait
	var lean := deg_to_rad(2.0 + 7.0 * run + 7.0 * sprint) * moving
	var hips_pitch := -lean * forward * 0.6 - deg_to_rad(10.0) * _crouch
	var hips_roll := roll - lean * right * 0.6
	var hips_basis := Basis(Vector3.UP, twist) * Basis(Vector3.RIGHT, hips_pitch) * Basis(Vector3.BACK, hips_roll)
	var hips_pos := Vector3(sway, hip_h, 0.03 * _crouch)
	skeleton.set_bone_pose_position(B.HIPS, hips_pos)
	skeleton.set_bone_pose_rotation(B.HIPS, hips_basis.get_rotation_quaternion())

	# ---- Legs ----
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		var left := i == 0
		var pos := foot_pos[i]
		var pitch := foot_pitch[i]
		if _air > 0.001:
			# In the air: knees come up while rising, legs reach down while falling.
			var rising := smoothstep(-3.0, 2.0, velocity.y)
			var hip := Vector3(side * 0.10, hip_h - 0.04, 0.0)
			var tuck := hip + (Vector3(0.0, -0.58, -0.22) if left else Vector3(0.0, -0.74, 0.14))
			var reach := hip + (Vector3(0.0, -0.80, -0.08) if left else Vector3(0.0, -0.83, 0.07))
			pos = pos.lerp(reach.lerp(tuck, rising), _air)
			pitch = lerpf(pitch, -0.45, _air)
		_solve_leg(side, hips_pos, hips_basis, pos, pitch)

	# ---- Spine and head ----
	var fold := deg_to_rad(16.0) * _crouch
	var spine_pitch := -lean * forward * 0.4 - fold + look_pitch * 0.15
	var chest_pitch := -fold * 0.5 + look_pitch * 0.25 + 0.012 * breathe
	skeleton.set_bone_pose_rotation(B.SPINE, Quaternion(Vector3.UP, -twist * 0.6 + look_yaw * 0.15)
		* Quaternion(Vector3.RIGHT, spine_pitch) * Quaternion(Vector3.BACK, -hips_roll * 0.5))
	skeleton.set_bone_pose_rotation(B.CHEST, Quaternion(Vector3.UP, -twist * 0.7 + look_yaw * 0.25)
		* Quaternion(Vector3.RIGHT, chest_pitch) * Quaternion(Vector3.BACK, -hips_roll * 0.5))
	# The head stays level: it tilts back by about as much as the body leans forward.
	var level := (lean * forward + deg_to_rad(10.0) * _crouch + fold * 1.5) * 0.85
	skeleton.set_bone_pose_rotation(B.NECK, Quaternion(Vector3.UP, look_yaw * 0.25)
		* Quaternion(Vector3.RIGHT, look_pitch * 0.2 + level * 0.4))
	skeleton.set_bone_pose_rotation(B.HEAD, Quaternion(Vector3.UP, look_yaw * 0.35)
		* Quaternion(Vector3.RIGHT, look_pitch * 0.4 + level * 0.6))

	# ---- Arms (they swing opposite to the legs) ----
	for side: float in [-1.0, 1.0]:
		var left := side < 0.0
		var swing_dir := -1.0 if left else 1.0
		var beat := cos(TAU * phase) * gait
		var swing := swing_dir * deg_to_rad(lerpf(20.0, 42.0, run) + 10.0 * sprint) * beat
		var elbow := deg_to_rad(12.0) + deg_to_rad(lerpf(8.0, 78.0, run)) * gait + maxf(swing, 0.0) * 0.4
		var out := side * deg_to_rad(lerpf(7.0, 11.0, run))
		# Crouching: arms come forward, ready.
		swing += deg_to_rad(30.0) * _crouch
		elbow += deg_to_rad(48.0) * _crouch
		# In the air: arms lift out to the sides for balance.
		swing = lerpf(swing, deg_to_rad(-12.0), _air)
		out = lerpf(out, side * deg_to_rad(36.0), _air)
		elbow = lerpf(elbow, deg_to_rad(42.0), _air)
		skeleton.set_bone_pose_rotation(B.UARM_L if left else B.UARM_R,
			Quaternion(Vector3.RIGHT, swing) * Quaternion(Vector3.BACK, out))
		skeleton.set_bone_pose_rotation(B.FARM_L if left else B.FARM_R, Quaternion(Vector3.RIGHT, elbow))


## Where one foot (its ankle) should be at point `p` of its step, and how the foot tilts.
## `p` runs 0..1: first the foot is on the ground and slides back, then it swings forward.
func _step_foot(side: float, p: float, stance: float, step_len: float, run: float, sprint: float) -> Array:
	var contact := stance * 2.0 * step_len            # how far the body travels while this foot is down
	var front := contact * lerpf(0.40, 0.32, run)     # the foot lands this far ahead of the hip
	var back := contact - front
	var roll := lerpf(0.13, 0.16, run)                # the ankle rolls forward over the toes at push-off
	var heel := lerpf(0.11, 0.15, run)                # ... and rises this high
	var along := 0.0
	var lift := 0.0
	var pitch := 0.0
	if p < stance:
		# On the ground: heel lands first, the foot lies flat, then the heel lifts to push off.
		var t := p / stance
		var push := smoothstep(0.55, 1.0, t)
		along = lerpf(front, -back, t) + roll * push
		lift = heel * push
		pitch = 0.2 * (1.0 - smoothstep(0.0, 0.2, t)) - 0.75 * push
	else:
		# In the air: the foot swings forward in an arc.
		var t := (p - stance) / (1.0 - stance)
		var e := t * t * (3.0 - 2.0 * t)
		along = lerpf(-back + roll, front, e)
		var height := lerpf(0.07, 0.30, run) + 0.12 * sprint
		lift = heel * (1.0 - e) + height * sin(PI * pow(t, 0.7))
		pitch = lerpf(-0.75, 0.2, smoothstep(0.1, 0.9, t)) - 0.4 * run * sin(PI * t)
	var travel := Vector3(_dir.x, 0.0, _dir.y)
	var pos := Vector3(side * lerpf(0.10, 0.07, run), Rig.ANKLE_H + lift, 0.0) + travel * along
	return [pos, pitch]


## Bends hip and knee so the ankle reaches `ankle` (two-bone IK).
func _solve_leg(side: float, hips_pos: Vector3, hips_basis: Basis, ankle: Vector3, foot_pitch: float) -> void:
	var left := side < 0.0
	var hip := hips_pos + hips_basis * Vector3(side * 0.10, -0.04, 0.0)
	var to := ankle - hip
	var reach := clampf(to.length(), 0.12, Rig.UPPER_LEG + Rig.LOWER_LEG - 0.003)
	var n := to.normalized()
	# The knee sits on a circle around the hip-to-ankle line. `a` is how far along
	# that line, `h` how far out from it (both from the triangle's side lengths).
	var a := (Rig.UPPER_LEG * Rig.UPPER_LEG - Rig.LOWER_LEG * Rig.LOWER_LEG + reach * reach) / (2.0 * reach)
	var h := sqrt(maxf(Rig.UPPER_LEG * Rig.UPPER_LEG - a * a, 0.0))
	var pole := Vector3(side * 0.12, 0.25, -1.0).normalized()      # knees point forward, a little outward
	var bend := pole - n * pole.dot(n)
	bend = bend.normalized() if bend.length() > 0.001 else Vector3.FORWARD
	var knee := hip + n * a + bend * h
	var thigh_basis := _aim_down(knee - hip, bend)
	var shin_basis := _aim_down(hip + n * reach - knee, bend)
	var foot_basis := Basis(Vector3.RIGHT, foot_pitch)
	skeleton.set_bone_pose_rotation(B.THIGH_L if left else B.THIGH_R,
		(hips_basis.inverse() * thigh_basis).get_rotation_quaternion())
	skeleton.set_bone_pose_rotation(B.SHIN_L if left else B.SHIN_R,
		(thigh_basis.inverse() * shin_basis).get_rotation_quaternion())
	skeleton.set_bone_pose_rotation(B.FOOT_L if left else B.FOOT_R,
		(shin_basis.inverse() * foot_basis).get_rotation_quaternion())


## A rotation whose "down" (-Y) points along `down` and whose front (-Z) faces `front` as well as it can.
static func _aim_down(down: Vector3, front: Vector3) -> Basis:
	var y := -down.normalized()
	var z := -front - y * (-front).dot(y)
	z = z.normalized() if z.length() > 0.001 else Vector3.BACK
	var x := y.cross(z).normalized()
	return Basis(x, y, x.cross(y))
