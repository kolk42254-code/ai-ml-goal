extends Node3D
## Tool scene: builds the world, flies a camera to fixed places and saves pictures.
## Used to check the look of the city without playing.
## Run:  SHOT_DIR=/some/folder godot --path . res://tools/shots.tscn

const World := preload("res://scripts/world/world.gd")

const VIEWS := [
	["air", Vector3(-330, 240, 400), Vector3(0, 20, 0), 60.0],
	["avenue", Vector3(-41, 1.7, 170), Vector3(-41, 14, 0), 70.0],
	["downtown", Vector3(34, 1.7, 60), Vector3(72, 40, 3), 75.0],
	["park", Vector3(-150, 2.2, 22), Vector3(-110, 2.5, 3), 70.0],
	["harbour", Vector3(-95, 3.0, 199), Vector3(-30, 6, 215), 70.0],
	["homes", Vector3(-184, 1.7, -150), Vector3(-200, 9, -215), 70.0],
	["carpark", Vector3(-150, 2.5, -60), Vector3(-170, 0.5, -90), 70.0],
	["park_wide", Vector3(-84, 9.0, 44), Vector3(-120, 3.0, 0), 62.0],
	["park_pond", Vector3(-70, 1.8, 20), Vector3(-83, 2.5, 7), 70.0],
	["park_oak", Vector3(-150, 1.8, -12), Vector3(-128, 4.0, 6), 70.0],
]

func _ready() -> void:
	var world := World.new()
	add_child(world)
	var cam := Camera3D.new()
	cam.far = 5000.0
	cam.near = 0.2
	add_child(cam)
	cam.make_current()
	var dir := OS.get_environment("SHOT_DIR")
	var only := OS.get_environment("SHOT_ONLY")
	for i in 6:
		await get_tree().process_frame
	for v: Array in VIEWS:
		if only != "" and not only.split(",").has(v[0]):
			continue
		cam.fov = v[3]
		cam.look_at_from_position(v[1], v[2], Vector3.UP)
		RenderingServer.global_shader_parameter_set("viewer_pos", v[1])
		for i in 3:
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png("%s/%s.png" % [dir, v[0]])
		print("shot ", v[0], "  draw calls ", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			"  tris ", RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME))
	print("renderer: ", RenderingServer.get_current_rendering_method(), " on ", RenderingServer.get_video_adapter_name())
	get_tree().quit()
