extends CharacterBody3D
## The player's fighter. Reads the "Controls" values, moves with physics, and
## tells the animator what the body is doing.

const Rig := preload("res://scripts/player/character_rig.gd")
const Animator := preload("res://scripts/player/character_animator.gd")

const WALK_SPEED := 1.8
const RUN_SPEED := 4.6
const SPRINT_SPEED := 7.0
const CROUCH_SPEED := 2.0
const ACCEL := 24.0             # how fast the fighter reaches the wanted speed on the ground
const AIR_ACCEL := 5.0          # ... and in the air (less control while jumping)
const GRAVITY := 22.0
const JUMP_SPEED := 7.4         # gives a jump about 1.2 m high
const RADIUS := 0.34
const STAND_HEIGHT := 1.8
const CROUCH_HEIGHT := 1.25
const WORLD_LAYER := 1
const HERO_LAYER := 2

## Where the camera looks. The camera script sets these every frame.
var camera_yaw := 0.0
var camera_pitch := 0.0
## True while the fighter is sprinting (the camera widens its view a little).
var sprinting := false
var crouching := false

var rig: Rig
var animator: Animator
var _visual: Node3D
var _shape: CapsuleShape3D
var _collider: CollisionShape3D
var _yaw := 0.0                 # the way the body faces


func _ready() -> void:
	collision_layer = HERO_LAYER
	collision_mask = WORLD_LAYER
	floor_max_angle = deg_to_rad(50.0)
	floor_snap_length = 0.35
	_shape = CapsuleShape3D.new()
	_shape.radius = RADIUS
	_shape.height = STAND_HEIGHT
	_collider = CollisionShape3D.new()
	_collider.shape = _shape
	_collider.position.y = STAND_HEIGHT * 0.5
	add_child(_collider)

	# The body you see is not a child of the physics body: it is placed by hand
	# every drawn frame, which keeps it smooth on 90 and 120 Hz phone screens.
	_visual = Node3D.new()
	_visual.name = "HeroVisual"
	_visual.top_level = true
	_visual.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	add_child(_visual)
	rig = Rig.new()
	_visual.add_child(rig)
	rig.build()
	animator = Animator.new()
	animator.setup(rig)


## Puts the fighter somewhere at once (start of a match, respawn).
func teleport(pos: Vector3, yaw: float) -> void:
	global_position = pos
	velocity = Vector3.ZERO
	_yaw = yaw
	reset_physics_interpolation()
	animator.snap()


func _physics_process(delta: float) -> void:
	var move := Controls.move
	# Crouch only changes while standing on the ground, and standing up needs head room.
	var want_crouch := Controls.crouch
	if want_crouch != crouching and is_on_floor():
		if want_crouch or _can_stand():
			_set_crouch(want_crouch)
		else:
			Controls.crouch = true
	# The stick direction is turned by the camera, so "up" always means "away from the camera".
	var wish := Basis(Vector3.UP, camera_yaw) * Vector3(move.x, 0.0, -move.y)
	var amount := minf(move.length(), 1.0)
	sprinting = Controls.sprint and not crouching and move.y > 0.35 and amount > 0.6
	# A small push on the stick walks, a full push runs.
	var speed := 0.0
	if amount > 0.05:
		if crouching:
			speed = CROUCH_SPEED * amount
		elif sprinting:
			speed = SPRINT_SPEED
		elif amount < 0.55:
			speed = WALK_SPEED * amount / 0.55
		else:
			speed = lerpf(WALK_SPEED, RUN_SPEED, (amount - 0.55) / 0.45)
	var target := wish.normalized() * speed if amount > 0.05 else Vector3.ZERO
	var flat := Vector3(velocity.x, 0.0, velocity.z)
	flat = flat.move_toward(target, (ACCEL if is_on_floor() else AIR_ACCEL) * delta)
	velocity.x = flat.x
	velocity.z = flat.z
	if is_on_floor():
		if Controls.take_jump() and not crouching:
			velocity.y = JUMP_SPEED
		elif velocity.y < 0.0:
			velocity.y = 0.0
	else:
		Controls.take_jump()            # a jump pressed in the air is forgotten
		velocity.y -= GRAVITY * delta
	move_and_slide()
	# Safety net: if something ever goes wrong and the fighter falls out of the world, put it back.
	if global_position.y < -20.0:
		teleport(Vector3(global_position.x, 2.0, global_position.z), _yaw)


func _process(delta: float) -> void:
	# Turn the body towards where the camera looks while moving. Standing still,
	# only the head turns, until the camera has turned far enough.
	var moving := Vector2(velocity.x, velocity.z).length() > 0.4
	var off := wrapf(camera_yaw - _yaw, -PI, PI)
	if moving or absf(off) > 1.1:
		_yaw = lerp_angle(_yaw, camera_yaw, 1.0 - exp(-(12.0 if moving else 5.0) * delta))
		off = wrapf(camera_yaw - _yaw, -PI, PI)
	var here := get_global_transform_interpolated().origin
	_visual.global_transform = Transform3D(Basis(Vector3.UP, _yaw), here)

	animator.velocity = _visual.global_basis.inverse() * velocity
	animator.on_floor = is_on_floor()
	animator.crouch = crouching
	animator.look_pitch = clampf(camera_pitch, -0.9, 0.9)
	animator.look_yaw = clampf(off, -1.2, 1.2)
	animator.update(delta)


func _set_crouch(on: bool) -> void:
	crouching = on
	_shape.height = CROUCH_HEIGHT if on else STAND_HEIGHT
	_collider.position.y = _shape.height * 0.5


func _can_stand() -> bool:
	var rise := STAND_HEIGHT - CROUCH_HEIGHT
	return not test_move(global_transform, Vector3(0.0, rise, 0.0))


## Height of the fighter's eyes above its feet (the camera aims around here).
func eye_height() -> float:
	return 1.18 if crouching else 1.58


## The way the body faces, as an angle around the up axis.
func facing_yaw() -> float:
	return _yaw
