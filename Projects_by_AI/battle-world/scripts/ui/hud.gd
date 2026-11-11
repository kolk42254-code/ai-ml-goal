extends CanvasLayer
## Everything drawn over the 3D view while playing: minimap, compass, the name
## of the place you are in, and the frame-rate counter.

const UiKit := preload("res://scripts/ui/ui_kit.gd")
const MAP_SIZE := 176.0

var world: Node3D
var hero: Node3D
var cam: Node3D

var _root: Control
var _map: ColorRect
var _map_material: ShaderMaterial
var _north: Label
var _place: Label
var _fps: Label
var _hint: Label
var _compass: Compass
var _slow_timer := 0.0
var _hint_time := 9.0


## The strip at the top that shows which way the camera looks.
class Compass extends Control:
	const UiKit := preload("res://scripts/ui/ui_kit.gd")
	const NAMES := {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
	var heading := 0.0

	func _draw() -> void:
		var w := size.x
		var mid := w * 0.5
		var px_per_deg := w / 150.0
		var font := UiKit.font(true)
		draw_rect(Rect2(0, 0, w, 34), Color(0, 0, 0, 0.28))
		for deg in range(0, 360, 15):
			var diff := wrapf(float(deg) - heading, -180.0, 180.0)
			var x := mid + diff * px_per_deg
			if x < 8.0 or x > w - 8.0:
				continue
			var fade := 1.0 - smoothstep(0.7, 1.0, absf(diff) / 75.0)
			if NAMES.has(deg):
				var text: String = NAMES[deg]
				var main := deg % 90 == 0
				var col := UiKit.ACCENT if deg == 0 else UiKit.TEXT
				var fs := 22 if main else 16
				var tw := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
				draw_string(font, Vector2(x - tw * 0.5, 24), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(col.r, col.g, col.b, fade))
			else:
				draw_line(Vector2(x, 12), Vector2(x, 22), Color(1, 1, 1, 0.55 * fade), 2.0)
		# Marker for "straight ahead".
		draw_colored_polygon(PackedVector2Array([Vector2(mid - 7, 34), Vector2(mid + 7, 34), Vector2(mid, 44)]), UiKit.ACCENT)


func setup(p_world: Node3D, p_hero: Node3D, p_cam: Node3D) -> void:
	world = p_world
	hero = p_hero
	cam = p_cam
	layer = 5
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	var safe := UiKit.safe_margins(_root)

	_map = ColorRect.new()
	_map.size = Vector2(MAP_SIZE, MAP_SIZE)
	_map.position = Vector2(22.0 + safe[0], 18.0 + safe[1])
	_map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_map_material = ShaderMaterial.new()
	_map_material.shader = load("res://shaders/minimap.gdshader")
	_map_material.set_shader_parameter("map_tex", ImageTexture.create_from_image(world.city.minimap_image))
	_map.material = _map_material
	_root.add_child(_map)
	var arrow := Polygon2D.new()
	arrow.polygon = PackedVector2Array([Vector2(0, -10), Vector2(8, 9), Vector2(0, 4), Vector2(-8, 9)])
	arrow.color = UiKit.ACCENT
	arrow.position = _map.position + _map.size * 0.5
	_root.add_child(arrow)
	_north = UiKit.label("N", 18, UiKit.ACCENT)
	_root.add_child(_north)
	_place = UiKit.label("", 22)
	_place.position = _map.position + Vector2(4.0, MAP_SIZE + 4.0)
	_root.add_child(_place)

	_compass = Compass.new()
	_compass.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_place_at(_compass, 0.5, 0.0, Rect2(-210.0, 14.0 + safe[1], 420.0, 46.0))
	_root.add_child(_compass)

	_fps = UiKit.label("", 18, UiKit.DIM)
	_fps.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_place_at(_fps, 1.0, 0.0, Rect2(-280.0 - safe[2], 92.0 + safe[1], 262.0, 24.0))
	_root.add_child(_fps)

	_hint = UiKit.label("", 20, UiKit.TEXT, false)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_place_at(_hint, 0.5, 1.0, Rect2(-450.0, -52.0 - safe[3], 900.0, 30.0))
	if not Controls.touch_ui:
		_hint.text = "WASD move  ·  Mouse look  ·  Shift sprint  ·  Space jump  ·  C crouch  ·  Esc pause"
	_root.add_child(_hint)


## Pins a control to a point of the screen (0..1 across and down) and gives it
## a rectangle measured from that point. It then stays in place on any screen size.
func _place_at(c: Control, anchor_x: float, anchor_y: float, rect: Rect2) -> void:
	c.anchor_left = anchor_x
	c.anchor_right = anchor_x
	c.anchor_top = anchor_y
	c.anchor_bottom = anchor_y
	c.offset_left = rect.position.x
	c.offset_top = rect.position.y
	c.offset_right = rect.end.x
	c.offset_bottom = rect.end.y


func _process(delta: float) -> void:
	if hero == null:
		return
	var b: Rect2 = world.layout.bounds
	var pos: Vector3 = hero.global_position
	var yaw: float = cam.yaw
	_map_material.set_shader_parameter("center", Vector2((pos.x - b.position.x) / b.size.x, (pos.z - b.position.y) / b.size.y))
	_map_material.set_shader_parameter("heading", yaw)
	var middle := _map.position + _map.size * 0.5
	_north.position = middle + Vector2(sin(yaw), -cos(yaw)) * (MAP_SIZE * 0.5 - 13.0) - Vector2(6, 12)
	_compass.heading = cam.heading_degrees()
	_compass.queue_redraw()

	if _hint_time > 0.0:
		_hint_time -= delta
		_hint.modulate.a = clampf(_hint_time, 0.0, 1.0)

	# Things that do not need to change every frame.
	_slow_timer -= delta
	if _slow_timer <= 0.0:
		_slow_timer = 0.4
		_place.text = _place_name(Vector2(pos.x, pos.z))
		_fps.visible = Settings.show_fps
		if Settings.show_fps:
			_fps.text = "%d FPS  ·  %s" % [Engine.get_frames_per_second(), Settings.preset().name]


func _place_name(p: Vector2) -> String:
	var layout = world.layout
	for block: Dictionary in layout.blocks:
		if (block.rect as Rect2).has_point(p):
			return layout.kind_name(block.kind).to_upper()
	if not (layout.city_rect as Rect2).has_point(p):
		return "WATERFRONT"
	return "STREET"
