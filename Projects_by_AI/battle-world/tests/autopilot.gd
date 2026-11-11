extends Node
## Self-playing test. The game adds this node when it is started with
## `-- --autotest`. It presses the controls like a player would, checks that the
## hero really does what was asked, and (when there is a screen) saves pictures.
##
##   Fast check, no screen:   tools/test.sh
##   With pictures:           SHOT_DIR=/some/folder tools/render.sh vk res://scenes/main.tscn --autotest --touch
##
## The process ends with exit code 0 when every check passed, 1 when one failed.

var game: Node
var hero: CharacterBody3D
var failed := 0
var passed := 0
var shot_dir := ""
var has_screen := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	game = get_parent()
	hero = game.hero
	shot_dir = OS.get_environment("SHOT_DIR")
	has_screen = DisplayServer.get_name() != "headless" and shot_dir != ""
	_run()


func _run() -> void:
	await _wait(0.6)
	var start := hero.global_position
	_check("the hero stands on the road", hero.is_on_floor() and absf(start.y) < 0.05, "y = %.3f" % start.y)
	await _shot("01_start")
	if OS.get_environment("AUTOTEST_QUICK") != "":
		get_tree().quit(0)
		return

	# --- Run forward (north) for 2 seconds.
	Input.action_press("move_forward")
	await _wait(2.0)
	var run_dist := Vector2(hero.global_position.x - start.x, hero.global_position.z - start.z).length()
	_check("running 2 s covers about 9 m", run_dist > 8.2 and run_dist < 9.4, "%.2f m" % run_dist)
	_check("running goes north (away from the camera)", hero.global_position.z < start.z - 8.0)
	_check("run speed is 4.6 m/s", absf(_ground_speed() - 4.6) < 0.1, "%.2f" % _ground_speed())
	await _shot("02_run")

	# --- Sprint.
	Input.action_press("sprint")
	await _wait(1.2)
	_check("sprint speed is 7 m/s", absf(_ground_speed() - 7.0) < 0.1, "%.2f" % _ground_speed())
	await _shot("03_sprint")
	Input.action_release("sprint")
	Input.action_release("move_forward")
	await _wait(0.6)
	_check("the hero stops when the keys are let go", _ground_speed() < 0.05, "%.2f" % _ground_speed())

	# --- Jump.
	await _tap("jump")
	var top := 0.0
	var mid_air_shot := false
	for i in 70:
		await get_tree().physics_frame
		top = maxf(top, hero.global_position.y)
		if i == 16 and not mid_air_shot:
			mid_air_shot = true
			await _shot("04_jump")
	_check("a jump is about 1.2 m high", top > 1.05 and top < 1.4, "%.2f m" % top)
	_check("the hero lands again", hero.is_on_floor() and hero.global_position.y < 0.05)

	# --- Side step right (east): up the kerb, onto the pavement, then a wall stops us.
	var before := hero.global_position
	Input.action_press("move_right")
	await _wait(1.6)
	await _shot("05_kerb")
	_check("side step goes east", hero.global_position.x > before.x + 3.0, "x %.2f -> %.2f" % [before.x, hero.global_position.x])
	_check("the hero steps up the kerb onto the pavement", absf(hero.global_position.y - 0.12) < 0.03, "y = %.3f" % hero.global_position.y)
	await _wait(2.5)
	Input.action_release("move_right")
	var wall_x: float = game.world.layout.roads_x[4].x + game.world.layout.roads_x[4].y * 0.5 + 3.5
	_check("a building wall stops the hero", hero.global_position.x < wall_x + 1.8 and hero.global_position.x > wall_x - 1.5,
		"x = %.2f, wall near %.2f" % [hero.global_position.x, wall_x])
	_check("the hero was not pushed through the floor", hero.global_position.y > -0.05)
	await _shot("06_wall")

	# --- Turn the camera a quarter turn to the right, then walk "forward": that is east now... blocked,
	# so turn left instead and walk west across the street.
	Controls.add_look_pixels(Vector2(-PI * 0.5 / Controls.MOUSE_RAD_PER_PIXEL / Settings.look_sensitivity, 0.0), Controls.MOUSE_RAD_PER_PIXEL)
	await _wait(0.2)
	_check("the camera turned a quarter turn left (faces west)", absf(wrapf(game.cam.yaw - PI * 0.5, -PI, PI)) < 0.02, "yaw %.3f" % game.cam.yaw)
	var west_from := hero.global_position
	Input.action_press("move_forward")
	await _wait(1.5)
	Input.action_release("move_forward")
	_check("forward now means west", hero.global_position.x < west_from.x - 5.5 and absf(hero.global_position.z - west_from.z) < 0.6,
		"moved %.2f, %.2f" % [hero.global_position.x - west_from.x, hero.global_position.z - west_from.z])
	_check("the body turned to face west too", absf(wrapf(hero.facing_yaw() - PI * 0.5, -PI, PI)) < 0.15)
	await _shot("07_turned")

	# --- Crouch.
	await _tap("crouch")
	Input.action_press("move_forward")
	await _wait(1.0)
	_check("crouching is on and slow", hero.crouching and absf(_ground_speed() - 2.0) < 0.1, "%.2f" % _ground_speed())
	await _shot("08_crouch")
	Input.action_release("move_forward")
	await _tap("crouch")
	await _wait(0.3)
	_check("the hero stands up again", not hero.crouching)

	# --- Touch controls (only when the on-screen controls are shown).
	if Controls.touch_ui:
		await _touch_checks()

	# --- Pause and resume.
	game.set_paused(true)
	var frozen := hero.global_position
	Input.action_press("move_forward")
	for i in 20:
		await get_tree().process_frame
	_check("nothing moves while paused", hero.global_position.is_equal_approx(frozen) and get_tree().paused)
	await _shot("10_paused")
	Input.action_release("move_forward")
	game.set_paused(false)
	await _wait(0.2)
	_check("the game runs again after resume", not get_tree().paused and Controls.enabled)

	# --- Graphics levels can be switched without errors.
	for q in [0, 2, 1]:
		Settings.quality = q
		Settings.apply()
		await _wait(0.1)
	_check("graphics levels switch", Settings.quality == 1)
	await _shot("11_end")

	print("AUTOTEST: %d passed, %d failed" % [passed, failed])
	get_tree().quit(1 if failed > 0 else 0)


func _touch_checks() -> void:
	var view := get_viewport().get_visible_rect().size
	var from := hero.global_position
	# Thumb down on the left side, pushed straight up: the hero runs forward (west).
	_touch(0, Vector2(200, view.y - 200), true)
	_drag(0, Vector2(200, view.y - 200), Vector2(200, view.y - 290))
	await _wait(1.0)
	_check("touch stick: pushing up runs forward", hero.global_position.x < from.x - 3.0 and Controls.touch_move.y > 0.9,
		"moved %.2f m" % (from.x - hero.global_position.x))
	# A second finger drags on the right side: the camera turns while the stick is still held.
	var yaw_before: float = game.cam.yaw
	_touch(1, Vector2(view.x - 400, 300), true)
	_drag(1, Vector2(view.x - 400, 300), Vector2(view.x - 300, 300))
	await _wait(0.2)
	var turned := wrapf(yaw_before - game.cam.yaw, -PI, PI)
	_check("touch look: dragging right turns the camera right", absf(turned - 100.0 * Controls.TOUCH_RAD_PER_PIXEL * Settings.look_sensitivity) < 0.01,
		"turned %.3f rad" % turned)
	_touch(1, Vector2(view.x - 300, 300), false)
	await _shot("09_touch")
	# Jump button while the stick is held.
	var jump_pos: Vector2 = game.touch._buttons.jump.pos
	_touch(2, jump_pos, true)
	await _wait(0.25)
	_check("touch jump button", hero.global_position.y > 0.3, "y = %.2f" % hero.global_position.y)
	_touch(2, jump_pos, false)
	_touch(0, Vector2(200, view.y - 290), false)
	await _wait(0.9)
	_check("letting go of the stick stops the hero", _ground_speed() < 0.05 and Controls.touch_move == Vector2.ZERO)


func _touch(finger: int, pos: Vector2, pressed: bool) -> void:
	var ev := InputEventScreenTouch.new()
	ev.index = finger
	ev.position = pos
	ev.pressed = pressed
	_send(ev)


func _drag(finger: int, from: Vector2, to: Vector2) -> void:
	var ev := InputEventScreenDrag.new()
	ev.index = finger
	ev.position = to
	ev.relative = to - from
	_send(ev)


## Delivers a fake touch. With a real window it goes the same way a finger on
## the glass would (through the engine's input system). Without a screen there
## is no window to map through, so it is handed straight to the game's viewport.
func _send(ev: InputEvent) -> void:
	if DisplayServer.get_name() == "headless":
		get_viewport().push_input(ev, true)
	else:
		Input.parse_input_event(ev)


## A short key press. It starts at the beginning of a drawn frame, which is
## when the engine hands real key presses to the game.
func _tap(action: String) -> void:
	await get_tree().process_frame
	Input.action_press(action)
	await _wait(0.15)
	Input.action_release(action)


func _ground_speed() -> float:
	return Vector2(hero.velocity.x, hero.velocity.z).length()


## Waits for game time (counted in physics steps), so the test gives the same
## result on a slow and on a fast computer.
func _wait(seconds: float) -> void:
	for i in int(round(seconds * Engine.physics_ticks_per_second)):
		await get_tree().physics_frame


func _check(what: String, ok: bool, detail := "") -> void:
	if ok:
		passed += 1
		print("  PASS  ", what, ("  (" + detail + ")") if detail != "" else "")
	else:
		failed += 1
		print("  FAIL  ", what, ("  (" + detail + ")") if detail != "" else "")


func _shot(name: String) -> void:
	if not has_screen:
		return
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("%s/%s.png" % [shot_dir, name])
	print("  shot %s: %d draw calls, %d triangles" % [name,
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)])
