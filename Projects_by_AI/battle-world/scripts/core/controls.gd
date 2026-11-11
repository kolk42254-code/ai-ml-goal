extends Node
## Autoload "Controls": turns keyboard, mouse, gamepad and touch input into a few
## simple values. The hero script only reads these values, so it does not care
## which device the player uses.

const MOUSE_RAD_PER_PIXEL := 0.0022
const TOUCH_RAD_PER_PIXEL := 0.0042
const STICK_RAD_PER_SEC := 2.6

## Movement wish: x = right(+) / left(-), y = forward(+) / back(-). Length 0..1.
var move := Vector2.ZERO
var sprint := false
var crouch := false                 # toggled by the crouch button
## False while a menu is open: the hero then gets no input.
var enabled := true
## True on phones and tablets (or when started with `-- --touch` on a PC).
var touch_ui := false

# Values the on-screen touch controls write into.
var touch_move := Vector2.ZERO
var touch_sprint := false

var _look := Vector2.ZERO           # radians not used yet: x = turn right, y = look up
var _jump := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	touch_ui = DisplayServer.is_touchscreen_available() or OS.has_feature("mobile") \
			or OS.get_cmdline_user_args().has("--touch")
	_add_key_action("move_forward", [KEY_W, KEY_UP])
	_add_key_action("move_back", [KEY_S, KEY_DOWN])
	_add_key_action("move_left", [KEY_A, KEY_LEFT])
	_add_key_action("move_right", [KEY_D, KEY_RIGHT])
	_add_key_action("jump", [KEY_SPACE])
	_add_key_action("sprint", [KEY_SHIFT])
	_add_key_action("crouch", [KEY_C, KEY_CTRL])
	_add_key_action("pause", [KEY_ESCAPE, KEY_P])
	_add_pad_button("jump", JOY_BUTTON_A)
	_add_pad_button("crouch", JOY_BUTTON_B)
	_add_pad_button("sprint", JOY_BUTTON_LEFT_STICK)
	_add_pad_button("pause", JOY_BUTTON_START)


func _add_key_action(action: String, keys: Array) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action, 0.3)
	for key: Key in keys:
		var ev := InputEventKey.new()
		ev.physical_keycode = key
		InputMap.action_add_event(action, ev)


func _add_pad_button(action: String, button: JoyButton) -> void:
	var ev := InputEventJoypadButton.new()
	ev.button_index = button
	InputMap.action_add_event(action, ev)


func _process(delta: float) -> void:
	if not enabled:
		move = Vector2.ZERO
		sprint = false
		return
	# Keyboard
	var keys := Input.get_vector("move_left", "move_right", "move_back", "move_forward")
	# Gamepad left stick (axis 1 is negative when pushed forward)
	var stick := Vector2(Input.get_joy_axis(0, JOY_AXIS_LEFT_X), -Input.get_joy_axis(0, JOY_AXIS_LEFT_Y))
	if stick.length() < 0.2:
		stick = Vector2.ZERO
	var wish := keys + stick + touch_move
	move = wish.limit_length(1.0)
	sprint = Input.is_action_pressed("sprint") or touch_sprint
	if Input.is_action_just_pressed("jump"):
		_jump = true
	if Input.is_action_just_pressed("crouch"):
		crouch = not crouch
	# Gamepad right stick turns the camera.
	var look_stick := Vector2(Input.get_joy_axis(0, JOY_AXIS_RIGHT_X), -Input.get_joy_axis(0, JOY_AXIS_RIGHT_Y))
	if look_stick.length() > 0.2:
		_look += look_stick * STICK_RAD_PER_SEC * delta * Settings.look_sensitivity


func _unhandled_input(event: InputEvent) -> void:
	if not enabled:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		add_look_pixels(event.relative, MOUSE_RAD_PER_PIXEL)


## Called by mouse and touch code: `pixels` is how far the pointer moved.
func add_look_pixels(pixels: Vector2, rad_per_pixel: float) -> void:
	var s := rad_per_pixel * Settings.look_sensitivity
	var up := -pixels.y if not Settings.invert_y else pixels.y
	_look += Vector2(pixels.x * s, up * s)


## Returns how far the camera should turn since the last call, then forgets it.
func take_look() -> Vector2:
	var out := _look
	_look = Vector2.ZERO
	return out


func press_jump() -> void:
	if enabled:
		_jump = true


## True once per jump press.
func take_jump() -> bool:
	var out := _jump
	_jump = false
	return out


func toggle_crouch() -> void:
	if enabled:
		crouch = not crouch


## Forgets all held input (used when a menu opens or the game loses focus).
func reset() -> void:
	move = Vector2.ZERO
	touch_move = Vector2.ZERO
	touch_sprint = false
	sprint = false
	_look = Vector2.ZERO
	_jump = false
