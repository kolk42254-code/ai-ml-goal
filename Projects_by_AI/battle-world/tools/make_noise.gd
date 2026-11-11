extends SceneTree
## Tool: makes `assets/textures/noise_rgb.png`, a repeating cloud-like picture the
## shaders use for dirt, wear and uneven edges. Each colour channel holds a
## different pattern size. Run:  godot --headless --path . -s tools/make_noise.gd

func _init() -> void:
	var size := 256
	var channels: Array[Image] = []
	var frequency := [0.012, 0.03, 0.07]
	for i in 3:
		var n := FastNoiseLite.new()
		n.seed = 11 + i * 7
		n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		n.frequency = frequency[i]
		n.fractal_octaves = 4
		channels.append(n.get_seamless_image(size, size, false, false, 0.3))
	var img := Image.create(size, size, false, Image.FORMAT_RGB8)
	for y in size:
		for x in size:
			img.set_pixel(x, y, Color(channels[0].get_pixel(x, y).r, channels[1].get_pixel(x, y).r,
				channels[2].get_pixel(x, y).r))
	img.save_png("res://assets/textures/noise_rgb.png")
	print("saved noise_rgb.png")
	quit()
