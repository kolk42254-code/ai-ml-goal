const env = require('./alg-lib.js');
const EDGES = { UF: [2, 4], UR: [2, 0], UB: [2, 5], UL: [2, 1], DF: [3, 4], DR: [3, 0], DB: [3, 5], DL: [3, 1], FR: [4, 0], FL: [4, 1], BR: [5, 0], BL: [5, 1] };
function edgeCubies(E, name) {
  const [f1, f2] = EDGES[name], h = E.h2;
  return E.allCubies().filter(c => E.typeOf(c) === 2 && E.facesOf(c).includes(f1) && E.facesOf(c).includes(f2));
}
function unpaired(E, st) {
  return Object.keys(EDGES).filter(name => {
    const cs = edgeCubies(E, name), [f1, f2] = EDGES[name];
    const a = new Set(cs.map(c => st[E.fi(c, f1)])), b = new Set(cs.map(c => st[E.fi(c, f2)]));
    return a.size > 1 || b.size > 1;
  });
}
function describe(E, st, names) {
  return names.map(nm => nm + ':' + edgeCubies(E, nm).sort((p, q) => p.join() < q.join() ? -1 : 1).map(c => { const [f1, f2] = EDGES[nm]; return E.COL[st[E.fi(c, f1)]] + E.COL[st[E.fi(c, f2)]]; }).join('/')).join('  ');
}
if (require.main === module) for (const n of [4, 5]) {
  const E = env(n);
  console.log(`=== ${n}x${n} pairing procedures (state each one fixes = inverse applied to a solved cube) ===`);
  for (const P of ["2U' R U R' 2U", "2U' R U' R' 2U", "2U' R U R' F R' F' R 2U", "Uw' R U R' F R' F' R Uw", "2D R U R' 2D'", "2U R U R' 2U'"]) {
    const X0 = E.run(E.solved, E.invert(P));
    const un = unpaired(E, X0);
    console.log(`"${P}": centres solved in start ${E.centresSolved(X0)} | unpaired edges in start: [${un}] | ${describe(E, X0, un)}`);
  }
  for (const P of ["2D R F' U R' F 2D'", "Dw R F' U R' F Dw'", "2U' R F' U R' F 2U"]) {
    const X0 = E.run(E.solved, E.invert(P));
    const un = unpaired(E, X0);
    console.log(`L2E "${P}": centres solved ${E.centresSolved(X0)} | unpaired in start: [${un}] | ${describe(E, X0, un)}`);
  }
}
module.exports = { unpaired, describe, edgeCubies, EDGES };
