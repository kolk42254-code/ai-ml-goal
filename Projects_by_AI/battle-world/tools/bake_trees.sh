#!/usr/bin/env bash
# Rebuilds everything about the trees: leaf pictures, tree models, far-away pictures.
# Run this after changing tools/tree_maker.gd or tools/make_tree_textures.py.
set -euo pipefail
cd "$(dirname "$0")/.."
photos="$(mktemp -d)"
python3 tools/make_tree_textures.py
"${GODOT:-godot}" --headless --path . --import >/dev/null 2>&1 || true
OUT_DIR="$photos" tools/render.sh vk res://tools/bake_trees.tscn 2>&1 | grep -E 'triangles|ERROR' || true
python3 tools/make_tree_textures.py far "$photos"
"${GODOT:-godot}" --headless --path . --import >/dev/null 2>&1 || true
rm -rf "$photos"
