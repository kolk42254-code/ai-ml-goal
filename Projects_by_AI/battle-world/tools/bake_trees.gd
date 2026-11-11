extends Node3D
## Tool scene: grows the five tree kinds, saves their models, and photographs
## each one for the flat far-away picture.
##
## Run (Linux, needs a virtual screen):
##   OUT_DIR=/tmp/tree_photos tools/render.sh vk res://tools/bake_trees.tscn
##   python3 tools/make_tree_textures.py far /tmp/tree_photos
## The first line writes assets/models/trees/*.res and raw photos, the second
## turns the photos into assets/textures/trees/far_*.png.

const TreeMaker := preload("res://tools/tree_maker.gd")
const TreeLibrary := preload("res://scripts/world/tree_library.gd")


func _ready() -> void:
	var out_dir := OS.get_environment("OUT_DIR")
	var maker := TreeMaker.new()
	for kind in TreeMaker.kinds():
		var started := Time.get_ticks_msec()
		var mesh := maker.make(kind)
		var err := ResourceSaver.save(mesh, TreeLibrary.MODELS + kind + ".res", ResourceSaver.FLAG_COMPRESS)
		print("%s: %d corners, %d triangles, %.1f m wide, %.1f m tall, grown in %d ms, saved: %s" % [kind,
			mesh.surface_get_array_len(0), mesh.surface_get_array_index_len(0) / 3,
			mesh.get_meta("width"), mesh.get_meta("height"), Time.get_ticks_msec() - started, error_string(err)])
		if out_dir != "":
			await _photograph(kind, mesh, out_dir)
	get_tree().quit()


func _photograph(kind: String, mesh: ArrayMesh, out_dir: String) -> void:
	var w: float = mesh.get_meta("width")
	var h: float = mesh.get_meta("height")
	var px := 1024.0 / maxf(w, h)
	var vp := SubViewport.new()
	vp.own_world_3d = true
	vp.transparent_bg = true
	vp.size = Vector2i(int(round(w * px)), int(round(h * px)))
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(vp)
	var material := ShaderMaterial.new()
	material.shader = load("res://tools/tree_capture.gdshader")
	material.set_shader_parameter("leaf_tex", load(TreeLibrary.TEXTURES + TreeLibrary.KINDS[kind].leaves + ".png"))
	material.set_shader_parameter("bark_tex", load(TreeLibrary.TEXTURES + "bark_color.jpg"))
	var tree := MeshInstance3D.new()
	tree.mesh = mesh
	tree.material_override = material
	vp.add_child(tree)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = h
	cam.near = 1.0
	cam.far = 200.0
	cam.position = Vector3(0.0, h * 0.5, 80.0)
	vp.add_child(cam)
	cam.make_current()
	for i in 5:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	vp.get_texture().get_image().save_png("%s/far_%s_raw.png" % [out_dir, kind])
	vp.queue_free()
