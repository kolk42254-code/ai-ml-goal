// Move notation shared by the guide, the AI players and the tests.
// R L U D F B = outer layer; 2R = only the 2nd layer from R; Rw = R + 2R; 3Rw = outer 3 layers;
// M E S = middle slice of an odd cube (M like L, E like D, S like F); x y z = whole cube (like R, U, F).
// ' = counter-clockwise, 2 = half turn. A frame maps R,U,F to world axes (the game's view).
function makeNotation(n) {
  const IDENT = [{ i: 0, s: 1 }, { i: 1, s: 1 }, { i: 2, s: 1 }];
  function layerMove(letter, depth, prime, fr) {
    const idx = 'RUFLDB'.indexOf(letter), k = idx % 3, side = idx < 3 ? 1 : -1;
    const L2 = side * ((n - 1) - 2 * (depth - 1));
    const d = prime ? side : -side;
    const v = fr[k];
    return { a: v.i, l2: v.s * L2, d: v.s * d };
  }
  function parse(text, fr) {
    fr = fr || IDENT;
    const tokens = [], errors = [];
    const raw = String(text == null ? '' : text)
      .replace(/[’‘ʼ´`]/g, "'")
      .replace(/[()\[\]{},;.]/g, ' ')
      .trim().split(/\s+/).filter(Boolean);
    for (const tok of raw) {
      const m = tok.match(/^(\d+)?([RLUDFBMESxyz])(w)?(2'|'2|2|')?$/);
      if (!m) { errors.push(tok); continue; }
      const num = m[1] ? +m[1] : null, L = m[2], wide = !!m[3], suf = m[4] || '';
      const q = suf === '' ? 1 : suf === "'" ? 3 : 2;
      const layers = [];
      let bad = false;
      if ('RLUDFB'.includes(L)) {
        if (wide) { const k = num == null ? 2 : num; if (k < 2 || k > n) bad = true; else for (let d = 1; d <= k; d++) layers.push([L, d]); }
        else { const k = num == null ? 1 : num; if (k < 1 || k > n) bad = true; else layers.push([L, k]); }
      } else if ('MES'.includes(L)) {
        if (num != null || wide || n % 2 === 0) bad = true;
        else layers.push([{ M: 'L', E: 'D', S: 'F' }[L], (n + 1) / 2]);
      } else {
        if (num != null || wide) bad = true;
        else { const f = { x: 'R', y: 'U', z: 'F' }[L]; for (let d = 1; d <= n; d++) layers.push([f, d]); }
      }
      if (bad) { errors.push(tok); continue; }
      const turns = [];
      for (const [f, d] of layers) {
        const mv = layerMove(f, d, q === 3, fr);
        turns.push(mv);
        if (q === 2) turns.push({ a: mv.a, l2: mv.l2, d: mv.d });
      }
      tokens.push({ text: tok, turns });
    }
    return { tokens, errors };
  }
  return { parse, layerMove, IDENT };
}
if (typeof module !== 'undefined') module.exports = makeNotation;
