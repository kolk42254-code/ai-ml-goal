extends Node3D
## Third-person camera: sits behind the fighter's right shoulder, turns with the
## look input, and moves closer when a wall is in the way.

const WORLD_LAYER := 1

@export var distance := 3.1          # metres behind the fighter
@export var shoulder := 0.55         # metres to the right
@export var lift := 0.25             # metres above the eyes
@export var base_fov := 70.0

var hero: Node3D
var camera: Camera3D
var yaw := 0.0
var pitch := -0.12

var _eye_y := 1.6
var _closeness := 1.0                # 1 = full distance, smaller = pushed in by a wall
var _side := 1.0                     # same idea for the sideways shoulder offset
var _probe := SphereShape3D.new()


func _ready() -> void:
	top_level = true
	physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	camera = Camera3D.new()
	camera.near = 0.12
	camera.far = 4000.0
	camera.fov = base_fov
	add_child(camera)
	camera.make_current()
	_probe.radius = 0.22


func follow(target: Node3D, start_yaw: float) -> void:
	hero = target
	yaw = start_yaw
	_eye_y = hero.eye_height()
	_closeness = 1.0
	_side = 1.0


func _process(delta: float) -> void:
	if hero == null:
		return
	var look := Controls.take_look()
	yaw = wrapf(yaw - look.x, -PI, PI)
	pitch = clampf(pitch + look.y, -1.15, 1.2)
	hero.camera_yaw = yaw
	hero.camera_pitch = pitch

	var feet: Vector3 = hero.get_global_transform_interpolated().origin
	# Follow height changes softly, so kerbs and crouching do not jolt the view.
	_eye_y = lerpf(_eye_y, hero.eye_height(), 1.0 - exp(-12.0 * delta))
	var pivot := feet + Vector3(0.0, _eye_y, 0.0)
	var aim := Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, pitch)
	# Step 1: move sideways from the head to the shoulder. If a wall is beside the
	# fighter, the camera stays closer to the middle instead of zooming in.
	var side_free := _free_part(pivot, aim.x * shoulder)
	_side = side_free if side_free < _side else lerpf(_side, side_free, 1.0 - exp(-5.0 * delta))
	var from := pivot + aim.x * (shoulder * _side)
	# Step 2: move back (and a little up) from the shoulder. If a wall is behind,
	# stop in front of it. Moving in is instant, moving back out is slow.
	var back := aim * Vector3(0.0, lift, distance + (0.35 if hero.sprinting else 0.0))
	var back_free := _free_part(from, back)
	_closeness = back_free if back_free < _closeness else lerpf(_closeness, back_free, 1.0 - exp(-5.0 * delta))
	global_transform = Transform3D(aim, from + back * _closeness)
	camera.fov = lerpf(camera.fov, base_fov + (6.0 if hero.sprinting else 0.0), 1.0 - exp(-6.0 * delta))


## Slides a small ball from `from` along `motion` and returns how much of the
## way (0..1) it can go before touching the world.
func _free_part(from: Vector3, motion: Vector3) -> float:
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = _probe
	query.transform = Transform3D(Basis.IDENTITY, from)
	query.motion = motion
	query.collision_mask = WORLD_LAYER
	var hit := get_world_3d().direct_space_state.cast_motion(query)
	return clampf(hit[0], 0.0, 1.0) if hit.size() > 0 else 1.0


## Compass direction the camera faces: 0 = north, 90 = east.
func heading_degrees() -> float:
	return fposmod(-rad_to_deg(yaw), 360.0)
