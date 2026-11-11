extends Node3D
## Tool scene: shows the five tree kinds on a lawn under the game's sky and sun,
## and saves a picture of each. Used to compare the trees with reference photos.
## Run:  SHOT_DIR=/some/folder tools/render.sh vk res://tools/tree_shots.tscn

const TreeLibrary := preload("res://scripts/world/tree_library.gd")
const SUN_DIRECTION := Vector3(-0.3775, 0.7418, 0.5544)
const KINDS := ["cherry", "spruce", "maple", "oak_bare", "oak"]


func _ready() -> void:
	var sky_material := ShaderMaterial.new()
	sky_material.shader = load("res://shaders/sky.gdshader")
	sky_material.set_shader_parameter("panorama", load("res://assets/sky/sky_day_2k.hdr"))
	var sky := Sky.new()
	sky.sky_material = sky_material
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_white = 6.0
	env.adjustment_enabled = true
	env.adjustment_contrast = 1.06
	env.adjustment_saturation = 1.12
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_color = Color(1.0, 0.95, 0.86)
	sun.light_energy = 1.7
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 120.0
	add_child(sun)
	sun.look_at_from_position(SUN_DIRECTION * 100.0, Vector3.ZERO, Vector3.UP)

	var lawn := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(600, 600)
	lawn.mesh = plane
	var grass := StandardMaterial3D.new()
	grass.albedo_texture = load("res://assets/textures/grass_color.jpg")
	grass.albedo_color = Color(0.8, 0.95, 0.62)
	grass.uv1_scale = Vector3(170, 170, 1)
	grass.roughness = 0.95
	lawn.material_override = grass
	add_child(lawn)

	var cam := Camera3D.new()
	cam.fov = 38.0
	cam.far = 2000.0
	add_child(cam)
	cam.make_current()
	var far_mode := OS.get_environment("TREE_FAR") != ""
	RenderingServer.global_shader_parameter_set("tree_lod", 0.0 if far_mode else 5000.0)
	var dir := OS.get_environment("SHOT_DIR")
	var x := 0.0
	var spots := {}
	for kind: String in KINDS:
		var mesh := TreeLibrary.model(kind)
		var tree := MeshInstance3D.new()
		tree.mesh = TreeLibrary.far_mesh(mesh) if far_mode else mesh
		tree.material_override = TreeLibrary.far_material(kind, mesh) if far_mode else TreeLibrary.near_material(kind)
		tree.position = Vector3(x, 0, 0)
		add_child(tree)
		spots[kind] = [x, float(mesh.get_meta("width")), float(mesh.get_meta("height"))]
		x += 34.0
	for i in 6:
		await get_tree().process_frame
	for kind: String in KINDS:
		var s: Array = spots[kind]
		var reach: float = maxf(s[1], s[2]) * 1.55 + 4.0
		var eye := Vector3(s[0] - reach * 0.35, 1.7, reach)
		cam.look_at_from_position(eye, Vector3(s[0], s[2] * 0.48, 0), Vector3.UP)
		RenderingServer.global_shader_parameter_set("viewer_pos", eye)
		for i in 3:
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("%s/tree_%s%s.png" % [dir, kind, "_far" if far_mode else ""])
		print("shot ", kind, " tris ", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME))
	get_tree().quit()
