#!/usr/bin/env bash
# Runs all automatic checks without a screen:
#   1. the city data tests            (tests/test_city.gd)
#   2. the self-playing game test     (tests/autopilot.gd) with keyboard, then with touch controls
set -uo pipefail
cd "$(dirname "$0")/.."
G="${GODOT:-godot}"
fail=0
echo "== city data =="
"$G" --headless --path . -s tests/test_city.gd 2>&1 | grep -vE '^\s*$|^Godot Engine' || true
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1
echo "== game, keyboard =="
"$G" --headless --fixed-fps 60 --path . res://scenes/main.tscn -- --autotest 2>&1 | grep -vE '^\s*$|^Godot Engine' || true
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1
echo "== game, touch =="
"$G" --headless --fixed-fps 60 --path . res://scenes/main.tscn -- --autotest --touch 2>&1 | grep -vE '^\s*$|^Godot Engine' || true
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1
[ $fail -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $fail
