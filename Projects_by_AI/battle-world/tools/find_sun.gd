extends SceneTree
## Tool: finds where the sun is in the sky picture, so the game's sun light can match it.
## Run:  godot --headless --path . -s tools/find_sun.gd

func _init() -> void:
	var img := Image.load_from_file("res://assets/sky/sky_day_2k.hdr")
	var w := img.get_width()
	var h := img.get_height()
	var best := 0.0
	var sum := Vector2.ZERO
	var weight := 0.0
	# First pass: brightest pixel. Second pass: average position of the very bright pixels.
	for y in range(0, h / 2):
		for x in w:
			var c := img.get_pixel(x, y)
			var lum := c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
			best = maxf(best, lum)
	for y in range(0, h / 2):
		for x in w:
			var c := img.get_pixel(x, y)
			var lum := c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
			if lum > best * 0.5:
				sum += Vector2(x, y) * lum
				weight += lum
	var p := sum / weight
	var u := (p.x + 0.5) / w
	var v := (p.y + 0.5) / h
	var elevation := (0.5 - v) * 180.0
	var azimuth := u * 360.0
	print("size ", w, "x", h, "  brightest ", best)
	print("sun pixel ", p, "  u=", u, " v=", v)
	print("sun elevation (deg) ", elevation, "  panorama angle (deg) ", azimuth)
	quit()
