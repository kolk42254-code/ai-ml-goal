#!/usr/bin/env python3
"""Make test/test.html: the built game (../../index.html) plus a hook that exposes internals to the browser tests.

Build first:  python3 dev/build.py --repo
Then:         python3 dev/test/make-test-page.py
              node dev/test/suite-core.js "$PWD/dev/test/test.html"
              node dev/test/suite-ai.js "$PWD/dev/test/test.html"
"""
import pathlib

here = pathlib.Path(__file__).resolve().parent
page = (here.parent.parent / 'index.html').read_text(encoding='utf-8')
boot = "window.claude?.hot?.ready ? window.claude.hot.ready(start) : start(window.claude?.hot?.data ?? {});"
hook = ("window.__t = { isSolved, phase: () => phase, queue: () => queue, bot: () => bot, ai: () => ai, aiBusy: () => aiBusy, "
        "stateText, progress, applied: () => applied, stickers: () => stickers, toScreen, FACE_DIR, n: () => n, "
        "worker: () => !!solverWorker, highlighted: () => highlighted.length, speedIdx: () => speedIdx, claudeState: () => claudeState, "
        "idle: () => !queue.length && !anim };\n")
assert page.count(boot) == 1, 'boot line not found'
(here / 'test.html').write_text(page.replace(boot, hook + boot), encoding='utf-8')
print('wrote', here / 'test.html')
