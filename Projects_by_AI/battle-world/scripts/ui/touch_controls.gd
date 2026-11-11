extends Control
## On-screen controls for phones:
##   left side  - a move stick that appears where the thumb lands
##   right side - drag anywhere to look around
##   buttons    - jump, crouch, sprint (stays on until tapped again) and pause
## Several fingers can be used at once; each finger keeps the job it started with.

signal pause_pressed

const UiKit := preload("res://scripts/ui/ui_kit.gd")

const STICK_RADIUS := 78.0
const KNOB_RADIUS := 34.0
const DEAD_ZONE := 0.12

var _stick_finger := -1
var _stick_origin := Vector2.ZERO
var _stick_offset := Vector2.ZERO
var _stick_home := Vector2(170, 550)
var _stick_sprint := false
var _look_finger := -1
var _sprint_on := false
var _shown_crouch := false
## name -> {pos, radius, finger}
var _buttons := {}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(_layout)
	_layout()


func _layout() -> void:
	var s := size
	var safe := UiKit.safe_margins(self)
	var right := s.x - safe[2]
	var bottom := s.y - safe[3]
	_buttons = {
		"jump": {"pos": Vector2(right - 120, bottom - 150), "radius": 56.0, "finger": -1},
		"crouch": {"pos": Vector2(right - 250, bottom - 96), "radius": 44.0, "finger": -1},
		"sprint": {"pos": Vector2(right - 98, bottom - 294), "radius": 42.0, "finger": -1},
		"pause": {"pos": Vector2(right - 54, 52 + safe[1]), "radius": 30.0, "finger": -1},
	}
	_stick_home = Vector2(175 + safe[0], bottom - 170)
	queue_redraw()


func _input(event: InputEvent) -> void:
	if not is_visible_in_tree():
		return
	if event is InputEventScreenTouch:
		var ev := make_input_local(event) as InputEventScreenTouch
		if ev.pressed:
			_finger_down(ev.index, ev.position)
		else:
			_finger_up(ev.index)
	elif event is InputEventScreenDrag:
		var ev := make_input_local(event) as InputEventScreenDrag
		_finger_move(ev.index, ev.position, ev.relative)


func _finger_down(finger: int, pos: Vector2) -> void:
	for name: String in _buttons:
		var b: Dictionary = _buttons[name]
		if pos.distance_to(b.pos) <= b.radius * 1.2:
			b.finger = finger
			_press(name)
			queue_redraw()
			return
	if pos.x < size.x * 0.45:
		if _stick_finger == -1:
			_stick_finger = finger
			_stick_origin = Vector2(maxf(pos.x, STICK_RADIUS + 10.0), minf(pos.y, size.y - STICK_RADIUS - 10.0))
			_stick_offset = Vector2.ZERO
			queue_redraw()
	elif _look_finger == -1:
		_look_finger = finger


func _finger_move(finger: int, pos: Vector2, relative: Vector2) -> void:
	if finger == _stick_finger:
		var pull := pos - _stick_origin
		_stick_offset = pull.limit_length(STICK_RADIUS)
		var v := Vector2(_stick_offset.x, -_stick_offset.y) / STICK_RADIUS
		Controls.touch_move = v if v.length() > DEAD_ZONE else Vector2.ZERO
		# Pushing the stick far up also sprints, so one thumb is enough to run fast.
		_stick_sprint = pull.length() > STICK_RADIUS * 1.45 and v.y > 0.75
		Controls.touch_sprint = _sprint_on or _stick_sprint
		queue_redraw()
	elif finger == _look_finger:
		Controls.add_look_pixels(relative, Controls.TOUCH_RAD_PER_PIXEL)


func _finger_up(finger: int) -> void:
	if finger == _stick_finger:
		_stick_finger = -1
		_stick_offset = Vector2.ZERO
		_stick_sprint = false
		Controls.touch_move = Vector2.ZERO
		Controls.touch_sprint = _sprint_on
		queue_redraw()
	elif finger == _look_finger:
		_look_finger = -1
	else:
		for name: String in _buttons:
			if _buttons[name].finger == finger:
				_buttons[name].finger = -1
				queue_redraw()


func _press(name: String) -> void:
	match name:
		"jump":
			Controls.press_jump()
		"crouch":
			Controls.toggle_crouch()
			_sprint_on = false
			Controls.touch_sprint = _stick_sprint
		"sprint":
			_sprint_on = not _sprint_on
			Controls.touch_sprint = _sprint_on or _stick_sprint
		"pause":
			pause_pressed.emit()


## Lets go of everything (called when a menu opens).
func release_all() -> void:
	_stick_finger = -1
	_look_finger = -1
	_stick_offset = Vector2.ZERO
	_stick_sprint = false
	for name: String in _buttons:
		_buttons[name].finger = -1
	Controls.touch_move = Vector2.ZERO
	Controls.touch_sprint = _sprint_on
	queue_redraw()


func _process(_delta: float) -> void:
	# Crouch can also change from the keyboard or the game itself, so keep the button in step.
	if _shown_crouch != Controls.crouch:
		_shown_crouch = Controls.crouch
		queue_redraw()


func _draw() -> void:
	# Move stick
	var active := _stick_finger != -1
	var base := _stick_origin if active else _stick_home
	var a := 0.6 if active else 0.3
	draw_circle(base, STICK_RADIUS, Color(0, 0, 0, 0.16))
	draw_arc(base, STICK_RADIUS, 0.0, TAU, 48, Color(1, 1, 1, a), 3.0, true)
	var knob_col := UiKit.ACCENT if (_stick_sprint or _sprint_on) and active else Color(1, 1, 1)
	draw_circle(base + _stick_offset, KNOB_RADIUS, Color(knob_col.r, knob_col.g, knob_col.b, a * 0.85))
	# Buttons
	for name: String in _buttons:
		var b: Dictionary = _buttons[name]
		var held: bool = b.finger != -1
		var lit := held or (name == "sprint" and _sprint_on) or (name == "crouch" and Controls.crouch)
		var ring := UiKit.ACCENT if lit else Color(1, 1, 1, 0.55)
		draw_circle(b.pos, b.radius, Color(UiKit.ACCENT.r, UiKit.ACCENT.g, UiKit.ACCENT.b, 0.28) if lit else Color(0, 0, 0, 0.26))
		draw_arc(b.pos, b.radius, 0.0, TAU, 40, ring, 3.0, true)
		_icon(name, b.pos, b.radius * 0.42, Color(1, 1, 1, 0.92))


func _icon(name: String, c: Vector2, s: float, col: Color) -> void:
	var w := 5.0
	match name:
		"jump":
			draw_polyline(PackedVector2Array([c + Vector2(-s, s * 0.35), c + Vector2(0, -s * 0.65), c + Vector2(s, s * 0.35)]), col, w, true)
		"crouch":
			draw_polyline(PackedVector2Array([c + Vector2(-s, -s * 0.35), c + Vector2(0, s * 0.65), c + Vector2(s, -s * 0.35)]), col, w, true)
		"sprint":
			for dy: float in [-0.45, 0.45]:
				draw_polyline(PackedVector2Array([c + Vector2(-s, s * (dy + 0.4)), c + Vector2(0, s * (dy - 0.4)), c + Vector2(s, s * (dy + 0.4))]), col, w, true)
		"pause":
			draw_rect(Rect2(c + Vector2(-s * 0.75, -s * 0.8), Vector2(s * 0.5, s * 1.6)), col)
			draw_rect(Rect2(c + Vector2(s * 0.25, -s * 0.8), Vector2(s * 0.5, s * 1.6)), col)
