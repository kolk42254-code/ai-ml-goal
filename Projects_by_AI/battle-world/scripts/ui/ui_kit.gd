extends RefCounted
## Shared look for all menus and HUD parts: fonts, colours and ready-made widgets.

const ACCENT := Color(1.0, 0.70, 0.12)
const TEXT := Color(0.94, 0.96, 0.98)
const DIM := Color(0.62, 0.68, 0.74)
const PANEL := Color(0.04, 0.06, 0.09, 0.86)


static func font(bold := true) -> Font:
	return load("res://assets/fonts/Rajdhani-Bold.ttf" if bold else "res://assets/fonts/Rajdhani-SemiBold.ttf")


static func label(text: String, size: int, color := TEXT, bold := true) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_override("font", font(bold))
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	l.add_theme_constant_override("shadow_offset_x", 1)
	l.add_theme_constant_override("shadow_offset_y", 2)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


static func box(color: Color, radius := 10, border := Color(0, 0, 0, 0), border_width := 0) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(radius)
	sb.border_color = border
	sb.set_border_width_all(border_width)
	sb.set_content_margin_all(12)
	return sb


## A big, finger-friendly button. `selected` gives it the accent colour.
static func button(text: String, selected := false) -> Button:
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	b.custom_minimum_size = Vector2(150, 58)
	b.add_theme_font_override("font", font(true))
	b.add_theme_font_size_override("font_size", 26)
	style_button(b, selected)
	return b


static func style_button(b: Button, selected: bool) -> void:
	var base := ACCENT if selected else Color(0.16, 0.20, 0.26, 0.95)
	var text := Color(0.06, 0.06, 0.06) if selected else TEXT
	b.add_theme_stylebox_override("normal", box(base, 8))
	b.add_theme_stylebox_override("hover", box(base.lightened(0.12), 8))
	b.add_theme_stylebox_override("pressed", box(base.darkened(0.2), 8))
	for key in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		b.add_theme_color_override(key, text)


## Space to keep free at each screen edge (camera holes, rounded corners), in
## the game's own screen units: [left, top, right, bottom].
static func safe_margins(node: Control) -> Array[float]:
	var out: Array[float] = [0.0, 0.0, 0.0, 0.0]
	if not OS.has_feature("mobile"):
		return out
	var window := Vector2(DisplayServer.window_get_size())
	var view := node.get_viewport_rect().size
	if window.x < 1.0 or window.y < 1.0:
		return out
	var safe := DisplayServer.get_display_safe_area()
	var scale := view.x / window.x
	out[0] = maxf(0.0, safe.position.x * scale)
	out[1] = maxf(0.0, safe.position.y * scale)
	out[2] = maxf(0.0, (window.x - safe.end.x) * scale)
	out[3] = maxf(0.0, (window.y - safe.end.y) * scale)
	return out
