const CubeSolver = require('../cube-solver.js');
const trials = +process.argv[2] || 20;
for (const n of [3, 4, 5, 6, 7]) {
  const t0 = Date.now();
  const S = CubeSolver.get(n);
  const build = Date.now() - t0, h2 = n - 1;
  let ok = 0, fail = 0, qtSum = 0, qtMax = 0, msMax = 0, segBad = 0, segTotal = 0, errs = [];
  const stageNames = new Set();
  for (let t = 0; t < trials; t++) {
    const scr = [];
    for (let i = 0; i < 40 * n; i++) scr.push({ a: Math.floor(Math.random() * 3), l2: 2 * Math.floor(Math.random() * n) - h2, d: Math.random() < 0.5 ? 1 : -1 });
    let st = S.applyTurns(S.solvedState(), scr);   // the solver only ever sees this colour array
    try {
      const r = S.solve(st);
      for (const sg of r.segments) {
        stageNames.add(sg.name);
        const before = st;
        st = S.applyTurns(st, sg.turns);
        if (sg.kind === 'parity') continue;
        segTotal++;
        // every changed sticker must sit on one of the 3 listed pieces, and all 3 must change
        const listed = new Set(sg.pieces.map(p => p.join(',')));
        const changed = new Set();
        let stray = false;
        for (let i = 0; i < S.F; i++) if (before[i] !== st[i]) { const k = S.faceletCoords(i).join(','); if (!listed.has(k)) stray = true; changed.add(k); }
        if (stray || sg.pieces.length !== 3) segBad++;
      }
      if (S.isSolved(st)) { ok++; qtSum += r.quarterTurns; qtMax = Math.max(qtMax, r.quarterTurns); msMax = Math.max(msMax, r.ms); }
      else fail++;
    } catch (e) { fail++; errs.push(e.message); }
  }
  // the index formula must agree with the facelet list
  let idxBad = 0;
  for (let i = 0; i < S.F; i++) if (CubeSolver.faceletIndex(n, S.faceletCoords(i), S.faceOf(i)) !== i) idxBad++;
  console.log(`${n}x${n}: tables ${build} ms | solved ${ok}/${trials} | avg ${Math.round(qtSum / Math.max(ok, 1))} quarter turns, max ${qtMax} | slowest ${msMax} ms | steps with stray pieces ${segBad}/${segTotal} | index errors ${idxBad}` + (errs.length ? ' | errors: ' + [...new Set(errs)].join('; ') : ''));
  console.log('   stages:', [...stageNames].join(' → '));
}
