#!/usr/bin/env python3
"""Inline the solver, notation and guide into the page template -> big-cube-lab.html."""
import pathlib, re, sys

here = pathlib.Path(__file__).resolve().parent
src = (here / 'page.src.html').read_text(encoding='utf-8')

def body(name):
    text = (here / name).read_text(encoding='utf-8')
    # drop the Node-only export line
    text = re.sub(r"^if \(typeof module !== 'undefined'\).*$", '', text, flags=re.M)
    if '</script' in text.lower():
        sys.exit(f'{name} contains </script')
    return text.strip() + '\n'

for marker, name in (('/*@@SOLVER@@*/', 'cube-solver.js'), ('/*@@NOTATION@@*/', 'notation.js'), ('/*@@GUIDE@@*/', 'guide.js')):
    if src.count(marker) != 1:
        sys.exit(f'marker {marker} not found exactly once')
    src = src.replace(marker, body(name))

if '--repo' in sys.argv:
    # a standalone file you can open from disk: needs its own doctype and head
    head = '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    out = here.parent / 'index.html'
    out.write_text(head + src, encoding='utf-8')
else:
    out = here / 'big-cube-lab.html'
    out.write_text(src, encoding='utf-8')
print('built', out.name, len(out.read_bytes()), 'bytes')
