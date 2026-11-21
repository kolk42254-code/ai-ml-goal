// N×N cube solver (3 ≤ N ≤ 7) that works only from sticker colours.
// Method: fix permutation parity with single turns, then place every piece with
// pure 3-cycles (commutators [A, B] found by search, moved into place with setup
// turns), the way blindfold solvers work. Correct for every legal state; not move-optimal.
// Written as a factory so the same source can run in a Web Worker.
function cubeSolverFactory() {
  'use strict';
  const NORMALS = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
  const KIND_ORDER = { corner: 0, midge: 1, wing: 2, center: 3 };
  function rot(v, a, q) { // q quarter turns, right-handed, about axis a
    let x = v[0], y = v[1], z = v[2];
    for (let i = 0; i < q; i++) {
      if (a === 0) { const ny = -z; z = y; y = ny; }
      else if (a === 1) { const nx = z; z = -x; x = nx; }
      else { const nx = -y; y = x; x = nx; }
    }
    return [x, y, z];
  }
  function faceOfNormal(v) {
    for (let f = 0; f < 6; f++) { const N = NORMALS[f]; if (N[0] === v[0] && N[1] === v[1] && N[2] === v[2]) return f; }
    return -1;
  }
  // Index of the sticker on face f of the cubie at doubled coordinates c (same order as create() builds them).
  function faceletIndex(n, c, f) {
    const h2 = n - 1, A = f >> 1, o0 = A === 0 ? 1 : 0, o1 = A === 2 ? 1 : 2;
    return f * n * n + ((c[o0] + h2) / 2) * n + (c[o1] + h2) / 2;
  }

  function create(n) {
    const h2 = n - 1;
    // ---- facelets: doubled cubie coordinates + face ----
    const fc = [], ff = [];
    for (let f = 0; f < 6; f++) {
      const A = f >> 1, s = (f & 1) ? -1 : 1, o = [0, 1, 2].filter(i => i !== A);
      for (let u = -h2; u <= h2; u += 2) for (let v = -h2; v <= h2; v += 2) {
        const c = [0, 0, 0]; c[A] = s * h2; c[o[0]] = u; c[o[1]] = v;
        fc.push(c); ff.push(f);
      }
    }
    const F = fc.length;
    const cubieOf = new Int32Array(F), cubies = [], cmap = new Map();
    for (let i = 0; i < F; i++) {
      const k = fc[i].join(',');
      if (!cmap.has(k)) { cmap.set(k, cubies.length); cubies.push([]); }
      cubieOf[i] = cmap.get(k); cubies[cubieOf[i]].push(i);
    }
    // ---- moves: axis a, layer li, d in {1,-1,2}; index = (a*n+li)*3+k ----
    const moves = [];
    for (let a = 0; a < 3; a++) for (let li = 0; li < n; li++) for (const d of [1, -1, 2]) {
      const l2 = 2 * li - h2, q = d === -1 ? 3 : d, perm = new Int32Array(F);
      for (let i = 0; i < F; i++) {
        if (fc[i][a] !== l2) { perm[i] = i; continue; }
        perm[i] = faceletIndex(n, rot(fc[i], a, q), faceOfNormal(rot(NORMALS[ff[i]], a, q)));
      }
      const inv = new Int32Array(F); for (let i = 0; i < F; i++) inv[perm[i]] = i;
      const supp = []; for (let i = 0; i < F; i++) if (perm[i] !== i) supp.push(i);
      moves.push({ a, li, l2, d, perm, inv, supp, cost: d === 2 ? 2 : 1 });
    }
    const invIdx = i => i - (i % 3) + [1, 0, 2][i % 3];
    const moveIdx = (a, li, d) => (a * n + li) * 3 + (d === 1 ? 0 : d === -1 ? 1 : 2);

    // ---- orbits of cubies (union-find over all moves) ----
    const par = cubies.map((_, i) => i);
    const find = x => { while (par[x] !== x) { par[x] = par[par[x]]; x = par[x]; } return x; };
    for (const m of moves) for (const i of m.supp) { const a = find(cubieOf[i]), b = find(cubieOf[m.perm[i]]); if (a !== b) par[a] = b; }
    const groups = new Map();
    cubies.forEach((_, c) => { const r = find(c); if (!groups.has(r)) groups.set(r, []); groups.get(r).push(c); });
    const orbits = [];
    for (const list of groups.values()) {
      const nf = cubies[list[0]].length;
      if (nf === 1 && list.length === 6) continue; // fixed centres of an odd cube
      const kind = nf === 3 ? 'corner' : nf === 2 ? 'edge' : 'center';
      orbits.push({ kind, slots: list, facelets: list.flatMap(c => cubies[c]) });
    }
    // edges: wings never flip, so a consistent label per sticker exists; midges can flip.
    for (const O of orbits) {
      if (O.kind !== 'edge') continue;
      const label = new Map(), q = [];
      const [p0, p1] = cubies[O.slots[0]];
      label.set(p0, 0); label.set(p1, 1); q.push(p0, p1);
      let ok = true;
      while (q.length && ok) {
        const i = q.pop();
        for (const m of moves) {
          const j = m.perm[i];
          if (!label.has(j)) { label.set(j, label.get(i)); q.push(j); }
          else if (label.get(j) !== label.get(i)) { ok = false; break; }
        }
      }
      O.kind = ok ? 'wing' : 'midge';
      if (ok) O.label = label;
    }
    // order: corners, middle edges, wings, centres; name each set
    const sortKey = O => fc[cubies[O.slots[0]][0]].map(v => Math.abs(v)).sort((a, b) => a - b).join(',');
    orbits.sort((A, B) => KIND_ORDER[A.kind] - KIND_ORDER[B.kind] || (sortKey(A) < sortKey(B) ? -1 : sortKey(A) > sortKey(B) ? 1 : 0));
    const countKind = k => orbits.filter(O => O.kind === k).length;
    const seenKind = {};
    for (const O of orbits) {
      seenKind[O.kind] = (seenKind[O.kind] || 0) + 1;
      const base = { corner: 'Corners', midge: 'Middle edges', wing: 'Edge wings', center: 'Centre pieces' }[O.kind];
      O.name = countKind(O.kind) > 1 ? `${base}, set ${seenKind[O.kind]}` : base;
      O.slotOf = new Map(); O.slots.forEach((c, i) => O.slotOf.set(c, i));
    }
    for (const O of orbits) {
      O.ref = O.slots.map(c => {
        const fs = cubies[c];
        if (O.kind === 'wing') return fs.find(i => O.label.get(i) === 0);
        if (O.kind === 'corner') return fs.find(i => (ff[i] >> 1) === 1);
        if (O.kind === 'midge') return fs.find(i => (ff[i] >> 1) === 1) ?? fs.find(i => (ff[i] >> 1) === 2);
        return fs[0];
      });
    }

    // ---- search for pure 3-cycles: [A, B] with A = X or X Y X' ----
    const permOf = seq => {
      const P = new Int32Array(F); for (let i = 0; i < F; i++) P[i] = i;
      for (const mi of seq) { const pm = moves[mi].perm; for (let i = 0; i < F; i++) P[i] = pm[P[i]]; }
      return P;
    };
    const orbitOfCubie = new Int32Array(cubies.length).fill(-1);
    orbits.forEach((O, k) => O.slots.forEach(c => { orbitOfCubie[c] = k; }));
    const WANT = 2;
    orbits.forEach(O => { O.comms = []; });
    const mark = new Int32Array(F); let stamp = 0;
    const order = moves.map((_, i) => i).sort((x, y) => moves[x].cost - moves[y].cost);
    function tryComm(Aseq, Bi) {
      const hit = [];
      for (const j of moves[Bi].supp) if (mark[j] === stamp) { hit.push(j); if (hit.length > 3) return; }
      if (!hit.length) return;
      const c = cubieOf[hit[0]];
      if (hit.some(j => cubieOf[j] !== c) || hit.length !== cubies[c].length) return;
      const k = orbitOfCubie[c]; if (k < 0) return;
      const O = orbits[k]; if (O.comms.length >= WANT) return;
      const Ainv = Aseq.slice().reverse().map(invIdx);
      const seq = [...Aseq, Bi, ...Ainv, invIdx(Bi)];
      const P = permOf(seq), moved = new Set();
      for (let i = 0; i < F; i++) if (P[i] !== i) { if (orbitOfCubie[cubieOf[i]] !== k) return; moved.add(cubieOf[i]); }
      if (moved.size !== 3) return;
      O.comms.push({ seq, P });
    }
    const done = () => orbits.every(O => O.comms.length >= WANT);
    for (const X of order) { // tier 1: [X, B]
      stamp++; for (const j of moves[X].supp) mark[j] = stamp;
      for (const B of order) if (moves[B].a !== moves[X].a) tryComm([X], B);
    }
    for (const X of order) { // tier 2: [X Y X', B]
      if (done()) break;
      for (const Y of order) {
        if (moves[Y].a === moves[X].a) continue;
        stamp++; const xi = moves[X].inv;
        for (const j of moves[Y].supp) mark[xi[j]] = stamp;
        for (const B of order) tryComm([X, Y, invIdx(X)], B);
      }
    }
    for (const O of orbits) if (!O.comms.length) throw new Error('no 3-cycle found for ' + O.name);

    // ---- setup table: conjugates S C S' that cycle the buffer's sticker, keyed by (target sticker, next sticker) ----
    const seqCost = s => s.reduce((t, mi) => t + moves[mi].cost, 0);
    for (const O of orbits) {
      const bRef = O.ref[0], table = new Map();
      for (const comm of O.comms) {
        const supp = [], pos = new Map();
        for (let i = 0; i < F; i++) if (comm.P[i] !== i) { pos.set(i, supp.length); supp.push(i); }
        const L = supp.length, img = supp.map(i => pos.get(comm.P[i]));
        const back = new Array(L); img.forEach((t, k) => { back[t] = k; });
        const keyIdx = []; const seenC = new Set();
        supp.forEach((i, k) => { if (!seenC.has(cubieOf[i])) { seenC.add(cubieOf[i]); keyIdx.push(k); } });
        const baseCost = seqCost(comm.seq), Cinv = comm.seq.slice().reverse().map(invIdx);
        const nodes = [{ pre: Int32Array.from(supp), parent: -1, move: -1, depth: 0 }];
        const seen = new Set([keyIdx.reduce((h, k) => h * F + supp[k], 0)]);
        for (let qi = 0; qi < nodes.length; qi++) {
          const nd = nodes[qi];
          for (let dir = 0; dir < 2; dir++) {
            const nx = dir === 0 ? img : back;
            for (let k = 0; k < L; k++) {
              if (nd.pre[k] !== bRef) continue;
              const k1 = nx[k], k2 = nx[k1];
              const x = nd.pre[k1], u = O.slotOf.get(cubieOf[nd.pre[k2]]);
              if (O.slotOf.get(cubieOf[x]) === 0 || u === 0) continue;
              const key = x * F + nd.pre[k2];
              const S = [];
              for (let p = qi; p > 0; p = nodes[p].parent) S.push(nodes[p].move);
              const cost = 2 * seqCost(S) + baseCost, old = table.get(key);
              if (!old || cost < old.cost) {
                const pairs = []; for (let kk = 0; kk < L; kk++) pairs.push([nd.pre[kk], nd.pre[nx[kk]]]);
                table.set(key, { x, u, cost, pairs, seq: [...S, ...(dir === 0 ? comm.seq : Cinv), ...S.slice().reverse().map(invIdx)] });
              }
            }
          }
          if (nd.depth >= 4) continue;
          for (const mi of order) {
            const inv = moves[mi].inv, pre = new Int32Array(L);
            for (let k = 0; k < L; k++) pre[k] = inv[nd.pre[k]];
            const h = keyIdx.reduce((a, k) => a * F + pre[k], 0);
            if (seen.has(h)) continue;
            seen.add(h); nodes.push({ pre, parent: qi, move: mi, depth: nd.depth + 1 });
          }
          if (nodes.length > 60000) break;
        }
      }
      O.table = table;
      O.byX = new Map();
      for (const e of table.values()) { if (!O.byX.has(e.x)) O.byX.set(e.x, []); O.byX.get(e.x).push(e); }
    }

    // merge turns on the same layer and cancel inverses (only inside one step, so steps stay readable)
    function tidy(seq) {
      const merged = [];
      for (const mi of seq) {
        const m = moves[mi]; const q = m.d === -1 ? 3 : m.d; let hit = false;
        for (let j = merged.length - 1; j >= 0 && merged[j].a === m.a; j--) {
          if (merged[j].li === m.li) { merged[j].q = (merged[j].q + q) % 4; if (!merged[j].q) merged.splice(j, 1); hit = true; break; }
        }
        if (!hit) merged.push({ a: m.a, li: m.li, q });
      }
      return merged.map(m => ({ a: m.a, l2: 2 * m.li - h2, q: m.q }));
    }

    // ---- solving ----
    function scheme(st) {
      const T = new Array(6);
      if (n % 2) {
        for (let f = 0; f < 6; f++) {
          const A = f >> 1, c = [0, 0, 0]; c[A] = (f & 1 ? -1 : 1) * h2;
          T[f] = st[faceletIndex(n, c, f)];
        }
      } else { // even cube: take the colour scheme from the DBL corner
        const c = [-h2, -h2, -h2];
        T[1] = st[faceletIndex(n, c, 1)]; T[0] = T[1] ^ 1;
        T[3] = st[faceletIndex(n, c, 3)]; T[2] = T[3] ^ 1;
        T[5] = st[faceletIndex(n, c, 5)]; T[4] = T[5] ^ 1;
      }
      return T;
    }

    function solve(stateIn) {
      const t0 = Date.now();
      const st = Int8Array.from(stateIn), T = scheme(st);
      const tgt = new Int8Array(F); for (let i = 0; i < F; i++) tgt[i] = T[ff[i]];
      const tmp = new Int8Array(F), segments = [];
      const doMove = mi => { const pm = moves[mi].perm; for (let i = 0; i < F; i++) tmp[pm[i]] = st[i]; st.set(tmp); };
      const stats = {};

      const homeKey = (O, fs, colorsOf) => {
        if (O.kind === 'wing') { const a = fs.find(i => O.label.get(i) === 0), b = fs.find(i => O.label.get(i) === 1); return colorsOf[a] * 8 + colorsOf[b]; }
        return fs.reduce((m, i) => m | (1 << colorsOf[i]), 0);
      };
      for (const O of orbits) {
        if (O.kind === 'center') continue;
        O.homeOfKey = new Map();
        O.slots.forEach((c, s) => O.homeOfKey.set(homeKey(O, cubies[c], tgt), s));
      }
      const pieceHome = (O, s) => O.homeOfKey.get(homeKey(O, cubies[O.slots[s]], st));
      const parity = O => {
        const seen = new Uint8Array(O.slots.length); let cycles = 0;
        for (let s = 0; s < O.slots.length; s++) { if (seen[s]) continue; cycles++; for (let x = s; !seen[x]; x = pieceHome(O, x)) seen[x] = 1; }
        return (O.slots.length - cycles) & 1;
      };

      // 1) parity: an odd corner permutation is fixed by U, an odd wing orbit by one inner slice
      const parityMoves = [];
      const corners = orbits.find(O => O.kind === 'corner');
      if (parity(corners)) { const mi = moveIdx(1, n - 1, 1); doMove(mi); parityMoves.push(mi); }
      for (const O of orbits) {
        if (O.kind !== 'wing' || !parity(O)) continue;
        for (let li = 1; li < n - 1; li++) {
          const mi = moveIdx(0, li, 1);
          if (moves[mi].supp.some(i => orbitOfCubie[cubieOf[i]] === orbits.indexOf(O))) { doMove(mi); parityMoves.push(mi); break; }
        }
      }
      if (parityMoves.length) segments.push({ kind: 'parity', name: 'Parity fix', turns: tidy(parityMoves), pieces: [] });

      // 2) place pieces with pure 3-cycles, buffer = slot 0
      const slotSolved = (O, s) => cubies[O.slots[s]].every(i => st[i] === tgt[i]);
      const applyEntry = (O, e) => {
        const pieces = [], seenC = new Set();
        for (const p of e.pairs) { const c = cubieOf[p[0]]; if (!seenC.has(c)) { seenC.add(c); pieces.push(fc[p[0]].slice()); } }
        const vals = e.pairs.map(p => st[p[0]]);
        e.pairs.forEach((p, k) => { st[p[1]] = vals[k]; });
        segments.push({ kind: O.kind, name: O.name, turns: tidy(e.seq), pieces });
      };
      const scoreAfter = (O, e) => { // number of solved slots touched by e after applying it
        const saved = e.pairs.map(p => st[p[1]]), vals = e.pairs.map(p => st[p[0]]);
        e.pairs.forEach((p, k) => { st[p[1]] = vals[k]; });
        const touched = new Set(e.pairs.map(p => O.slotOf.get(cubieOf[p[1]])));
        let sc = 0; for (const s of touched) if (slotSolved(O, s)) sc++;
        e.pairs.forEach((p, k) => { st[p[1]] = saved[k]; });
        return sc;
      };
      const pick = (O, cands) => {
        let best = null, bs = -1;
        for (const e of cands) { const s = scoreAfter(O, e); if (s > bs || (s === bs && e.cost < best.cost)) { best = e; bs = s; } }
        return best;
      };
      for (const O of orbits) {
        const S = O.slots.length, bRef = O.ref[0];
        let cycles = 0, guard = 0;
        const unsolved = () => { const u = []; for (let s = 1; s < S; s++) if (!slotSolved(O, s)) u.push(s); return u; };
        while (true) {
          if (guard++ > 6 * S + 60) throw new Error('stuck on ' + O.name);
          const un = unsolved();
          if (!un.length && slotSolved(O, 0)) break;
          let cands = [];
          if (O.kind === 'center') {
            const c = st[bRef];
            if (c !== tgt[bRef]) {
              for (const x of O.facelets) if (tgt[x] === c && st[x] !== tgt[x] && x !== bRef) for (const e of (O.byX.get(x) || [])) cands.push(e);
              const strict = cands.filter(e => !slotSolved(O, e.u));
              if (strict.length) cands = strict;
            } else {
              for (const s of un) for (const e of (O.byX.get(cubies[O.slots[s]][0]) || [])) if (!slotSolved(O, e.u) && st[cubies[O.slots[e.u]][0]] !== tgt[bRef]) cands.push(e);
              if (!cands.length) for (const s of un) for (const e of (O.byX.get(cubies[O.slots[s]][0]) || [])) cands.push(e);
            }
          } else {
            const home = pieceHome(O, 0);
            if (home !== 0) {
              const t = cubies[O.slots[home]].find(i => tgt[i] === st[bRef]);
              cands = (O.byX.get(t) || []);
              const strict = cands.filter(e => !slotSolved(O, e.u));
              if (strict.length) cands = strict;
            } else {
              for (const s of un) for (const x of cubies[O.slots[s]]) for (const e of (O.byX.get(x) || [])) if (!slotSolved(O, e.u)) cands.push(e);
              if (!cands.length) for (const s of un) for (const x of cubies[O.slots[s]]) for (const e of (O.byX.get(x) || [])) cands.push(e);
            }
          }
          const e = pick(O, cands);
          if (!e) throw new Error('stuck on ' + O.name);
          applyEntry(O, e); cycles++;
        }
        stats[O.name] = cycles;
      }
      let quarterTurns = 0;
      for (const sg of segments) for (const t of sg.turns) quarterTurns += t.q === 2 ? 2 : 1;
      return { segments, stats, quarterTurns, ms: Date.now() - t0 };
    }

    function applyTurns(stateIn, turns) { // turns: {a, l2, q} or {a, l2, d}
      const st = Int8Array.from(stateIn), tmp = new Int8Array(F);
      for (const t of turns) {
        const d = t.q != null ? (t.q === 3 ? -1 : t.q) : t.d;
        const pm = moves[moveIdx(t.a, (t.l2 + h2) / 2, d)].perm;
        for (let i = 0; i < F; i++) tmp[pm[i]] = st[i];
        st.set(tmp);
      }
      return st;
    }
    function isSolved(st) {
      for (let f = 0; f < 6; f++) { let c = -1; for (let i = f * n * n; i < (f + 1) * n * n; i++) { if (c < 0) c = st[i]; else if (st[i] !== c) return false; } }
      return true;
    }
    const solvedState = () => Int8Array.from(ff);
    return { n, F, solve, applyTurns, isSolved, solvedState, faceletCoords: i => fc[i].slice(), faceOf: i => ff[i] };
  }

  const cache = new Map();
  return {
    get(n) { if (!cache.has(n)) cache.set(n, create(n)); return cache.get(n); },
    faceletIndex,
  };
}
const CubeSolver = cubeSolverFactory();
if (typeof module !== 'undefined') module.exports = CubeSolver;
