extends Node3D
## Starts the game: builds the world, puts the hero and camera in it, adds the
## HUD and touch controls, and handles pausing.

const World := preload("res://scripts/world/world.gd")
const Hero := preload("res://scripts/player/hero.gd")
const HeroCamera := preload("res://scripts/player/hero_camera.gd")
const Hud := preload("res://scripts/ui/hud.gd")
const TouchControls := preload("res://scripts/ui/touch_controls.gd")
const PauseMenu := preload("res://scripts/ui/pause_menu.gd")
const UiKit := preload("res://scripts/ui/ui_kit.gd")

var world: World
var hero: Hero
var cam: HeroCamera
var hud: Hud
var touch: TouchControls
var pause_menu: PauseMenu
var ready_to_play := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var loading := _loading_screen()
	# Let the loading screen appear before the heavy work starts.
	await get_tree().process_frame
	await get_tree().process_frame

	var started := Time.get_ticks_msec()
	world = World.new()
	world.name = "World"
	world.process_mode = Node.PROCESS_MODE_PAUSABLE
	add_child(world)
	print("City built in %d ms" % (Time.get_ticks_msec() - started))

	hero = Hero.new()
	hero.name = "Hero"
	hero.process_mode = Node.PROCESS_MODE_PAUSABLE
	add_child(hero)
	hero.teleport(world.start_position(), 0.0)

	cam = HeroCamera.new()
	cam.name = "Camera"
	cam.process_mode = Node.PROCESS_MODE_PAUSABLE
	add_child(cam)
	cam.follow(hero, 0.0)

	hud = Hud.new()
	hud.name = "Hud"
	add_child(hud)
	hud.setup(world, hero, cam)

	var ui := CanvasLayer.new()
	ui.name = "Ui"
	ui.layer = 10
	add_child(ui)
	if Controls.touch_ui:
		touch = TouchControls.new()
		touch.name = "TouchControls"
		ui.add_child(touch)
		touch.pause_pressed.connect(set_paused.bind(true))
	else:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	pause_menu = PauseMenu.new()
	pause_menu.name = "PauseMenu"
	ui.add_child(pause_menu)
	pause_menu.resumed.connect(set_paused.bind(false))

	loading.queue_free()
	ready_to_play = true
	if OS.get_cmdline_user_args().has("--autotest"):
		add_child(load("res://tests/autopilot.gd").new())


func _loading_screen() -> CanvasLayer:
	var layer := CanvasLayer.new()
	layer.layer = 50
	add_child(layer)
	var bg := ColorRect.new()
	bg.color = Color(0.027, 0.035, 0.055)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(bg)
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	layer.add_child(box)
	var title := UiKit.label("BATTLE WORLD", 84, UiKit.ACCENT)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	var sub := UiKit.label("Building the city ...", 26, UiKit.DIM, false)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(sub)
	return layer


func _unhandled_input(event: InputEvent) -> void:
	if ready_to_play and event.is_action_pressed("pause"):
		set_paused(not get_tree().paused)


func _notification(what: int) -> void:
	if not ready_to_play:
		return
	match what:
		NOTIFICATION_WM_GO_BACK_REQUEST:
			# The phone's Back button: pause, or go back to the game.
			set_paused(not get_tree().paused)
		NOTIFICATION_APPLICATION_PAUSED, NOTIFICATION_APPLICATION_FOCUS_OUT:
			if not OS.get_cmdline_user_args().has("--autotest"):
				set_paused(true)


func set_paused(on: bool) -> void:
	get_tree().paused = on
	pause_menu.visible = on
	Controls.enabled = not on
	Controls.reset()
	if touch:
		touch.visible = not on
		touch.release_all()
	else:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if on else Input.MOUSE_MODE_CAPTURED
