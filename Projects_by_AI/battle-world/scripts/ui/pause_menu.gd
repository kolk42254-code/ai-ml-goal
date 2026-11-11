extends Control
## The pause screen with the game settings: graphics level, look speed, FPS counter.

signal resumed

const UiKit := preload("res://scripts/ui/ui_kit.gd")

var _quality_buttons: Array[Button] = []
var _fps_button: Button
var _rate_button: Button


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false
	var dim := ColorRect.new()
	dim.color = Color(0.0, 0.01, 0.03, 0.6)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(dim)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(center)
	var panel := PanelContainer.new()
	var style := UiKit.box(UiKit.PANEL, 18, Color(1, 1, 1, 0.14), 2)
	style.set_content_margin_all(30)
	panel.add_theme_stylebox_override("panel", style)
	center.add_child(panel)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	panel.add_child(col)

	col.add_child(UiKit.label("PAUSED", 46, UiKit.ACCENT))
	col.add_child(UiKit.label("GRAPHICS", 20, UiKit.DIM))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	col.add_child(row)
	for q in 3:
		var b := UiKit.button(["LOW", "MEDIUM", "HIGH"][q], Settings.quality == q)
		b.pressed.connect(_on_quality.bind(q))
		row.add_child(b)
		_quality_buttons.append(b)

	col.add_child(UiKit.label("LOOK SPEED", 20, UiKit.DIM))
	var slider := HSlider.new()
	slider.min_value = 0.3
	slider.max_value = 2.5
	slider.step = 0.05
	slider.value = Settings.look_sensitivity
	slider.custom_minimum_size = Vector2(470, 44)
	slider.focus_mode = Control.FOCUS_NONE
	slider.add_theme_stylebox_override("slider", UiKit.box(Color(0.16, 0.20, 0.26), 6))
	slider.add_theme_stylebox_override("grabber_area", UiKit.box(UiKit.ACCENT, 6))
	slider.add_theme_stylebox_override("grabber_area_highlight", UiKit.box(UiKit.ACCENT, 6))
	var knob := _knob_texture()
	slider.add_theme_icon_override("grabber", knob)
	slider.add_theme_icon_override("grabber_highlight", knob)
	slider.value_changed.connect(_on_look_speed)
	col.add_child(slider)

	var toggles := HBoxContainer.new()
	toggles.add_theme_constant_override("separation", 10)
	col.add_child(toggles)
	_fps_button = UiKit.button("")
	_fps_button.custom_minimum_size.x = 230
	_fps_button.pressed.connect(_on_fps_counter)
	toggles.add_child(_fps_button)
	_rate_button = UiKit.button("")
	_rate_button.custom_minimum_size.x = 230
	_rate_button.pressed.connect(_on_frame_rate)
	toggles.add_child(_rate_button)

	var gap := Control.new()
	gap.custom_minimum_size.y = 8
	col.add_child(gap)
	var resume := UiKit.button("RESUME", true)
	resume.pressed.connect(func() -> void: resumed.emit())
	col.add_child(resume)
	var quit := UiKit.button("EXIT GAME")
	quit.pressed.connect(func() -> void: get_tree().quit())
	col.add_child(quit)
	_refresh()


func _knob_texture() -> Texture2D:
	var size := 40
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var mid := Vector2(size, size) * 0.5
	for y in size:
		for x in size:
			var d := Vector2(x + 0.5, y + 0.5).distance_to(mid)
			img.set_pixel(x, y, Color(1, 1, 1, clampf(size * 0.5 - 1.0 - d, 0.0, 1.0)))
	return ImageTexture.create_from_image(img)


func _refresh() -> void:
	for q in _quality_buttons.size():
		UiKit.style_button(_quality_buttons[q], Settings.quality == q)
	_fps_button.text = "FPS COUNTER: %s" % ("ON" if Settings.show_fps else "OFF")
	_rate_button.text = "FRAME RATE: %d" % Settings.fps_cap


func _on_quality(q: int) -> void:
	Settings.set_quality(q)
	_refresh()


func _on_look_speed(value: float) -> void:
	Settings.look_sensitivity = value
	Settings.save_settings()


func _on_fps_counter() -> void:
	Settings.show_fps = not Settings.show_fps
	Settings.save_settings()
	_refresh()


func _on_frame_rate() -> void:
	Settings.fps_cap = 30 if Settings.fps_cap == 60 else 60
	Settings.apply()
	Settings.save_settings()
	_refresh()
