extends Node3D
## Tool scene: shows the fighter in many poses side by side, so the body shape
## and the walk / run / jump animation can be checked from pictures.
## Run:  SHOT_DIR=/some/folder tools/render.sh vk res://tools/character_shots.tscn

const Rig := preload("res://scripts/player/character_rig.gd")
const Animator := preload("res://scripts/player/character_animator.gd")

var _cam: Camera3D


func _ready() -> void:
	var env := Environment.new()
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	env.sky = sky
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.32, 0.34, 0.37)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.light_energy = 1.6
	add_child(sun)
	sun.look_at_from_position(Vector3(-3, 6, -5), Vector3.ZERO)
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(80, 80)
	ground.mesh = plane
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.42, 0.43, 0.45)
	gm.roughness = 0.9
	ground.material_override = gm
	add_child(ground)
	_cam = Camera3D.new()
	_cam.fov = 18.0
	add_child(_cam)
	_cam.make_current()

	var dir := OS.get_environment("SHOT_DIR")
	# 1. Standing poses seen from the front, a three-quarter view and the back.
	var row := Node3D.new()
	add_child(row)
	var poses := [
		{"yaw": 0.0}, {"yaw": 0.7}, {"yaw": PI * 0.5}, {"yaw": PI},
		{"yaw": 0.5, "crouch": true}, {"yaw": 0.5, "air": 4.0}, {"yaw": 0.5, "air": -5.0},
	]
	for i in poses.size():
		var pose: Dictionary = poses[i]
		var a := _fighter(row, Vector3((i - 3) * 1.25, 0, 0), pose.yaw)
		a.crouch = pose.get("crouch", false)
		if pose.has("air"):
			a.on_floor = false
			a.velocity = Vector3(0, pose.air, 0)
			a.rig.position.y = 0.5
		a.snap()
		a.update(0.016)
	await _shoot(Vector3(0, 1.1, -10.6), Vector3(0, 1.0, 0), "%s/char_poses.png" % dir)
	row.queue_free()
	await get_tree().process_frame

	# 2. Step cycles seen from the side: 8 moments of a walk, a run and a sprint.
	var cycles := [["walk", 1.6, false], ["run", 4.6, false], ["sprint", 7.2, false], ["crouchwalk", 1.8, true]]
	for c: Array in cycles:
		var strip := Node3D.new()
		add_child(strip)
		for i in 8:
			var a := _fighter(strip, Vector3(0, 0, (3.5 - i) * 1.35), 0.0)
			a.velocity = Vector3(0, 0, -c[1])
			a.crouch = c[2]
			a.snap()
			a.phase = i / 8.0
			a.update(0.0001)
		await _shoot(Vector3(12.4, 1.0, 0), Vector3(0, 0.95, 0), "%s/char_%s.png" % [dir, c[0]])
		strip.queue_free()
		await get_tree().process_frame
	get_tree().quit()


func _fighter(parent: Node3D, pos: Vector3, yaw: float) -> Animator:
	var rig := Rig.new()
	parent.add_child(rig)
	rig.position = pos
	rig.rotation.y = yaw
	rig.build()
	var a := Animator.new()
	a.setup(rig)
	return a


func _shoot(from: Vector3, to: Vector3, path: String) -> void:
	_cam.look_at_from_position(from, to, Vector3.UP)
	for i in 4:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(path)
	print("saved ", path)
