const CubeSolver = require('../cube-solver.js');
const makeNotation = require('../notation.js');
const COL = 'ROWYGB'; // face id -> colour letter (R red, O orange, W white, Y yellow, G green, B blue)
function env(n) {
  const S = CubeSolver.get(n), N = makeNotation(n), h2 = n - 1;
  const solved = S.solvedState();
  const turnsOf = alg => { const p = N.parse(alg); if (p.errors.length) throw new Error('bad tokens: ' + p.errors.join(' ')); return p.tokens.flatMap(t => t.turns); };
  const run = (st, alg) => S.applyTurns(st, turnsOf(alg));
  const invert = alg => alg.trim().split(/\s+/).reverse().map(t => t.endsWith("'") ? t.slice(0, -1) : t.endsWith('2') ? t : t + "'").join(' ');
  const fi = (c, f) => CubeSolver.faceletIndex(n, c, f);
  const facesOf = c => [0,1,2,3,4,5].filter(f => { const A = f >> 1, s = f & 1 ? -1 : 1; return c[A] === s * h2; });
  const allCubies = () => { const m = new Map(); for (let i = 0; i < S.F; i++) { const c = S.faceletCoords(i); m.set(c.join(','), c); } return [...m.values()]; };
  const typeOf = c => c.filter(v => Math.abs(v) === h2).length;
  const nm = c => (c[1] === h2 ? 'U' : c[1] === -h2 ? 'D' : '') + (c[2] === h2 ? 'F' : c[2] === -h2 ? 'B' : '') + (c[0] === h2 ? 'R' : c[0] === -h2 ? 'L' : '') + (typeOf(c) === 2 && n > 3 ? '[' + c.map(v => Math.abs(v) === h2 ? '' : v).join('') + ']' : '');
  const changed = st => allCubies().filter(c => facesOf(c).some(f => st[fi(c, f)] !== solved[fi(c, f)]));
  const centresSolved = st => allCubies().filter(c => typeOf(c) === 1).every(c => { const f = facesOf(c)[0]; return st[fi(c, f)] === f; });
  // colours of the piece at c: {face: colourLetter}
  const piece = (st, c) => Object.fromEntries(facesOf(c).map(f => ['RLUDFB'[f], COL[st[fi(c, f)]]]));
  // where is the piece whose colour set equals the solved colours of home cubie h (corners / midges / 3x3 edges)?
  const find = (st, home) => {
    const want = facesOf(home).map(f => f).sort().join(',');
    return allCubies().filter(c => typeOf(c) === typeOf(home) && facesOf(c).map(f => st[fi(c, f)]).sort().join(',') === want);
  };
  return { n, S, N, h2, solved, run, invert, fi, facesOf, allCubies, typeOf, nm, changed, centresSolved, piece, find, COL };
}
module.exports = env;
