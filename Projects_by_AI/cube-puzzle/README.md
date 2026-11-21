# Big Cube Lab

A 3D cube puzzle in the browser, from 3×3 up to 7×7.

- **Play**: scramble, drag stickers or use the keyboard, race the clock (best time and Ao5 per size).
- **Learn**: a step-by-step method for every size, with a "Show me" button for each algorithm. Every algorithm was checked in a cube simulator before it went in.
- **Solver**: watch a computer solve your cube slowly from the sticker colours alone. The three pieces it is moving light up; you can pause, step, change speed or finish.
- **AI players**: let Claude or Gemini play move by move and see how far they get.

## How to open it

Open `index.html` in a browser (it needs internet to load the 3D library).

## AI players: where each one works

| Player | Where it works | What it uses |
|---|---|---|
| Claude | Only on the published claude.ai page | Your own Claude account, no API key. Each turn uses some of your Claude usage, and claude.ai asks you to allow the page first. |
| Gemini | Only when `index.html` is opened from your computer | Your own Gemini API key. claude.ai pages are not allowed to contact other websites, so Gemini cannot run there. |

The Gemini key goes only from your browser to Google. It is saved only if you tick "Remember the key on this device" (browser storage on your computer). Never commit your key to this repository.

## For changes (dev folder)

The game is built from parts in `dev/`: `page.src.html` (page and game), `cube-solver.js`, `notation.js` and `guide.js`.

```bash
python3 dev/build.py --repo        # rebuilds index.html
node dev/test/solver-test.js 50     # solver on 50 random cubes per size
node dev/test/verify-guide.js       # every guide algorithm parses and keeps what it promises
```

Browser tests (need Playwright): see the top of `dev/test/make-test-page.py`.
