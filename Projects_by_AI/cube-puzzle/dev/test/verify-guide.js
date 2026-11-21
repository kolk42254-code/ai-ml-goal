const { GUIDES } = require('../guide.js');
const env = require('./alg-lib.js');
const verified = new Set([
  "F U' R U", "R U R' U'", "U R U' R' U' F' U F", "U' L' U L U F U' F'", "F R U R' U' F'", "R U R' U R U2 R' U", "U R U' L' U R' U' L", "R' D' R D",
  "2R U 2R' 2U 2R U' 2R' 2U'", "3R U 3R' 3U 3R U' 3R' 3U'", "2R U 2R' 3U 2R U' 2R' 3U'", "M U M' 2U M U' M' 2U'", "M U M' 3U M U' M' 3U'",
  "2U' R U R' 2U", "2D R U R' 2D'", "3U' R U R' 3U", "3D R U R' 3D'",
  "2D R F' U R' F 2D'", "3D R F' U R' F 3D'", "R U R' F R' F' R",
  "2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2", "3R2 B2 U2 3L U2 3R' U2 3R U2 F2 3R F2 3L' B2 3R2",
  "2R2 U2 2R2 Uw2 2R2 2U2", "2R2 U2 2R2 3Uw2 2R2 2U2 3U2", "3R2 U2 3R2 3Uw2 3R2 2U2 3U2",
]);
let count = 0, problems = 0;
for (const [n, g] of Object.entries(GUIDES)) {
  const E = env(+n);
  for (const st of g.steps) for (const [alg] of (st.algs || [])) {
    count++;
    const p = E.N.parse(alg);
    if (p.errors.length) { problems++; console.log(`${n}x${n} "${alg}": unknown moves ${p.errors}`); }
    if (!verified.has(alg)) { problems++; console.log(`${n}x${n} "${alg}": not in the verified list`); }
    // centre tools must be pure on this size; parity tools must keep centres; everything must keep centres solved except none
    const s = E.run(E.solved, alg);
    const ch = E.changed(s);
    const isCentreTool = /^(2R|3R|M) U /.test(alg);
    if (isCentreTool) { if (!(ch.length === 3 && ch.every(c => E.typeOf(c) === 1))) { problems++; console.log(`${n}x${n} "${alg}": centre tool is not a clean 3-cycle`); } }
    else if (!E.centresSolved(s)) { problems++; console.log(`${n}x${n} "${alg}": breaks centres`); }
  }
}
console.log(`${count} guide algorithms checked, ${problems} problems`);
