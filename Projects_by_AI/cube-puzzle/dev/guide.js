// Step-by-step guides. Every algorithm here was checked in the cube simulator
// (what it changes, what it leaves alone, and the holding position it needs).
const GUIDE_NOTATION = [
  'R, L, U, D, F, B turn the right, left, up, down, front or back layer a quarter turn clockwise, as if you were looking straight at that side.',
  "R' (with ') means counter-clockwise. R2 means a half turn.",
  'On big cubes, 2R means only the 2nd layer from the right, turning the same way as R. 3R is the 3rd layer.',
  'Rw means R and 2R together. 3Uw means the top three layers together. M, E and S turn the middle layer of an odd cube (M like L, E like D, S like F).',
  "In this game F is always the side facing you. To type 2R, press 2 then R. Hold Shift for '.",
  'Show me plays the moves on your cube. Undo takes them back one turn at a time.',
];

const SOLVE_AS_3x3 = {
  h: 'Solve it like a 3×3',
  p: [
    'Each finished centre now works like one centre piece, and each finished edge like one edge piece.',
    'Follow the 3×3 guide (switch the size to 3×3 to read it), using outer-layer turns only: R, L, U, D, F, B, never the inner layers.',
  ],
};

const GUIDES = {
  3: {
    title: 'Solve the 3×3 layer by layer',
    intro: 'The beginner method: white cross, white corners, middle layer, then the yellow side. Seven steps and seven short algorithms.',
    steps: [
      { h: 'White cross', p: [
        'Hold the cube with white on top. Make a white cross: the four white edge pieces around the white centre, each with its other colour matching the centre on its side.',
        'Most of this needs no algorithm. Turn an edge into the bottom layer under the centre it matches, then turn that side twice to bring it up next to white.',
        'If an edge is in its spot but the wrong way round (white facing you), hold it at the front and use this:' ],
        algs: [["F U' R U", 'Flips the white edge at the front. The other white edges stay where they are.']] },
      { h: 'White corners', p: [
        'Turn the cube over so white is on the bottom.',
        'Find a corner in the top layer that has white on it. Turn the top layer until the corner sits right above the place it belongs (its colours match the two centres beside that place). Hold that place at the front right.',
        'Repeat the algorithm until the corner drops in the right way round: 1, 3 or 5 times. If a white corner is in the bottom layer in the wrong place, hold it at the front right and do the algorithm once to lift it out.' ],
        algs: [["R U R' U'", 'Repeat until the corner is solved.']] },
      { h: 'Middle layer', p: [
        'Keep white on the bottom. Find an edge in the top layer with no yellow on it.',
        "Turn the top until the edge's front colour matches the front centre. Then look at its top colour and pick the algorithm.",
        'If an edge sits in the middle layer the wrong way, use either algorithm once to lift it out, then insert it again.' ],
        algs: [["U R U' R' U' F' U F", 'Top colour matches the right centre: the edge goes into the front-right slot.'],
               ["U' L' U L U F U' F'", 'Top colour matches the left centre: the edge goes into the front-left slot.']] },
      { h: 'Yellow cross', p: [
        'Look at the yellow side on top. You will see a dot, an L shape, a line or the cross.',
        'Dot: do the algorithm once and you get an L.',
        'L shape: turn the top so the L points to the back and to the left, then do the algorithm. You get a line.',
        'Line: turn the top so the line goes left to right, then do the algorithm. You get the cross.' ],
        algs: [["F R U R' U' F'", 'Changes only the top layer; the two bottom layers stay solved.']] },
      { h: 'Yellow edges', p: [
        'Turn the top until two edges of the yellow cross match the centres on their sides.',
        'If those two are next to each other, hold them at the back and on the right, then do the algorithm.',
        'If they are opposite each other, do the algorithm once from any side. Afterwards you can turn the top to find two side by side.' ],
        algs: [["R U R' U R U2 R' U", 'Fixes the other two edges when the matching pair is at the back and right.']] },
      { h: 'Yellow corners to their places', p: [
        'A corner is in its place when its three colours match the three centres around it, even if it is twisted.',
        'Find a corner that is in its place and hold it at the front right of the top. Do the algorithm once or twice until all four corners are in their places.',
        'If no corner is in its place, do the algorithm once from any side first.' ],
        algs: [["U R U' L' U R' U' L", 'Keeps the front-right top corner where it is and moves the other three round.']] },
      { h: 'Twist the yellow corners', p: [
        'Hold the cube with yellow on top and an unfinished corner at the front right of the top.',
        "Repeat the algorithm until that corner's yellow faces up (2 or 4 times). The lower layers will look scrambled: keep going.",
        'Turn only the top layer to bring the next unfinished corner to the front right, and repeat. When every corner shows yellow on top, the lower layers fix themselves. Turn the top to finish.' ],
        algs: [["R' D' R D", 'Repeat until this corner shows yellow on top.']] },
    ],
  },
  4: {
    title: 'Solve the 4×4: turn it into a 3×3',
    intro: 'Build the centres, pair the edges, then solve it like a 3×3. Two extra algorithms fix the parity cases a 3×3 never has.',
    steps: [
      { h: 'Centres', p: [
        'Build the six 2×2 centres. Start with white, then yellow on the opposite side.',
        'Then build the four side centres in order around the cube: with white on top and green in front, red goes on the right, blue at the back and orange on the left.',
        'Make 1×2 bars and join them. Inner-layer turns such as 2R move centre pieces between sides; turn an outer side first to line the pieces up.',
        'For the last centres, this algorithm moves exactly three centre pieces (between the front, top and right sides) and nothing else:' ],
        algs: [["2R U 2R' 2U 2R U' 2R' 2U'", 'Moves three centre pieces round between F, U and R.']] },
      { h: 'Pair the edges', p: [
        'Each edge is made of 2 pieces. Pair them up one edge at a time.',
        'Find two pieces with the same two colours. Put one in the front-left edge in the upper slot (2nd layer from the top), and the other in the front-right edge in the lower slot. Line them up: the colour on the left side of the left piece must match the colour on the front of the right piece.',
        "Turn the top so the edge at the back of the top layer is one that is not paired yet, then do the algorithm. The slice joins the pair, R U R' moves it up out of the way, and 2U puts the centres back." ],
        algs: [["2U' R U R' 2U", 'Joins the two pieces into one edge.']] },
      { h: 'Last two edges', p: [
        'When only two edges are left, hold them at the front left and front right, then do the first algorithm.',
        'If they are still not paired, turn the front-right edge over with the second algorithm and do the first one again. This rule worked in every arrangement we checked.' ],
        algs: [["2D R F' U R' F 2D'", 'Swaps the top piece of the front-right edge with the bottom piece of the front-left edge.'],
               ["R U R' F R' F' R", 'Turns the front-right edge over. Other edges move but stay paired.']] },
      SOLVE_AS_3x3,
      { h: 'Parity: one edge flipped', p: [
        "At the yellow cross you may see a shape a 3×3 can't have, such as a single edge flipped. Hold one flipped edge at the front of the top and do the algorithm, then carry on." ],
        algs: [["2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2", 'Flips the top-front edge. Nothing else changes.']] },
      { h: 'Parity: two edges swapped', p: [
        'In the last steps you may find that exactly two pieces need to swap places, which never happens on a 3×3. Do this algorithm once, then carry on with the 3×3 steps.' ],
        algs: [["2R2 U2 2R2 Uw2 2R2 2U2", 'Swaps the top-front and top-back edges. Nothing else changes.']] },
    ],
  },
  5: {
    title: 'Solve the 5×5: turn it into a 3×3',
    intro: 'Build the centres, join each edge from three pieces, then solve it like a 3×3. Odd cubes have no parity in the last layer, but one edge can end up with its outer pieces swapped.',
    steps: [
      { h: 'Centres', p: [
        'Build the six 3×3 centres around the fixed middle pieces. Do white first, then yellow on the opposite side, then the four sides: with white on top and green in front, red goes on the right, blue at the back and orange on the left.',
        'Make bars of three and join them with inner-layer turns.',
        'For the last centres, these move exactly three centre pieces between the front, top and right sides:' ],
        algs: [["2R U 2R' 2U 2R U' 2R' 2U'", 'Moves three corner pieces of the centres (the diagonal ones).'],
               ["M U M' 2U M U' M' 2U'", 'Moves three of the pieces next to the middle (the + shape).']] },
      { h: 'Pair the edges', p: [
        'Each edge has three pieces: a middle piece and two outer pieces. Join the outer pieces to their middle piece one at a time.',
        'Put the middle piece (with any pieces already joined) in the front-right edge. Put the matching outer piece in the front-left edge: in the upper slot (2nd layer from the top) if it goes on top, or the lower slot (2nd layer from the bottom) if it goes underneath. Line up the colours as on the 4×4: the left side of the left piece matches the front of the right pieces.',
        'Turn the top so the edge at the back of the top layer is unfinished, then do the matching algorithm.' ],
        algs: [["2U' R U R' 2U", 'Brings the upper piece from the front-left edge into the front-right edge.'],
               ["2D R U R' 2D'", 'Brings the lower piece from the front-left edge into the front-right edge.']] },
      { h: 'Last two edges', p: [
        'When two edges are left, hold them at the front left and front right.',
        'The first algorithm swaps the upper outer piece of the front-right edge with the lower outer piece of the front-left edge; the middle pieces stay put. The second turns the front-right edge over. Combine them until both edges are complete.',
        'If one edge ends up with its two outer pieces swapped (flipped at the ends but not in the middle), hold it at the front of the top and use the third algorithm.' ],
        algs: [["2D R F' U R' F 2D'", 'Swaps two outer pieces between the front-right and front-left edges.'],
               ["R U R' F R' F' R", 'Turns the front-right edge over. Other edges move but stay paired.'],
               ["2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2", 'Swaps the two outer pieces of the top-front edge. Nothing else changes.']] },
      SOLVE_AS_3x3,
    ],
  },
  6: {
    title: 'Solve the 6×6: turn it into a 3×3',
    intro: 'The same plan as the 4×4 with more pieces: 4×4 centres, edges made of four pieces, then the 3×3 steps. Parity can show up in the outer pieces, the inner pieces or both.',
    steps: [
      { h: 'Centres', p: [
        'Build the six 4×4 centres: white, then yellow opposite, then the four sides (white on top, green in front: red right, blue back, orange left).',
        'Build bars, then join bars into blocks with inner-layer turns.',
        'For the last centres, each of these moves exactly three centre pieces of one kind between the front, top and right sides:' ],
        algs: [["2R U 2R' 2U 2R U' 2R' 2U'", 'Outer corner pieces of the centres.'],
               ["3R U 3R' 3U 3R U' 3R' 3U'", 'Inner corner pieces of the centres.'],
               ["2R U 2R' 3U 2R U' 2R' 3U'", 'The in-between pieces.']] },
      { h: 'Pair the edges', p: [
        'Each edge has four pieces: two inner pieces (layers 3 and 4) and two outer pieces (layers 2 and 5). Join the two inner pieces first, then add the outer ones.',
        'Put the pieces you already have in the front-right edge and the piece to add in the front-left edge, at the height of the slice you will use. Line up the colours: the left side of the left piece matches the front of the right pieces.',
        'Turn the top so the edge at the back of the top layer is unfinished, then do the algorithm for that height.' ],
        algs: [["3U' R U R' 3U", 'Adds the inner piece from layer 3 of the front-left edge.'],
               ["3D R U R' 3D'", 'Adds the inner piece from layer 4 of the front-left edge.'],
               ["2U' R U R' 2U", 'Adds the outer piece from layer 2 of the front-left edge.'],
               ["2D R U R' 2D'", 'Adds the outer piece from layer 5 of the front-left edge.']] },
      { h: 'Last two edges', p: [
        'Hold the last two edges at the front left and front right. These tools each swap one piece between the two edges. Read the side effects: each one also swaps the other pair of pieces inside the front-right edge.',
        'Fix one kind of piece at a time and use the flip when the colours face the wrong way.' ],
        algs: [["2D R F' U R' F 2D'", 'Swaps the layer-2 piece of front right with the layer-5 piece of front left. Also swaps the two inner pieces of front right.'],
               ["3D R F' U R' F 3D'", 'Swaps the layer-3 piece of front right with the layer-4 piece of front left. Also swaps the two outer pieces of front right.'],
               ["R U R' F R' F' R", 'Turns the front-right edge over. Other edges move but stay paired.']] },
      SOLVE_AS_3x3,
      { h: 'Parity: one edge flipped', p: [
        'At the yellow cross, a flipped edge can be flipped in its outer pieces, its inner pieces or both. Hold it at the front of the top and use the matching algorithm (or both).' ],
        algs: [["2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2", 'Swaps the two outer pieces of the top-front edge.'],
               ["3R2 B2 U2 3L U2 3R' U2 3R U2 F2 3R F2 3L' B2 3R2", 'Swaps the two inner pieces of the top-front edge.']] },
      { h: 'Parity: two edges swapped', p: [
        'If at the end exactly two pieces seem to need swapping, swap the outer pieces, the inner pieces or both between the top-front and top-back edges.' ],
        algs: [["2R2 U2 2R2 3Uw2 2R2 2U2 3U2", 'Swaps the outer pieces of the top-front and top-back edges.'],
               ["3R2 U2 3R2 3Uw2 3R2 2U2 3U2", 'Swaps the inner pieces of the top-front and top-back edges.']] },
    ],
  },
  7: {
    title: 'Solve the 7×7: turn it into a 3×3',
    intro: 'The same plan as the 5×5 with more pieces: 5×5 centres, edges made of five pieces, then the 3×3 steps. There is no last-layer parity, but edges can end with pieces swapped.',
    steps: [
      { h: 'Centres', p: [
        'Build the six 5×5 centres around the fixed middle pieces: white, then yellow opposite, then the four sides (white on top, green in front: red right, blue back, orange left).',
        'Build bars of five, then join them with inner-layer turns.',
        'For the last centres, each of these moves exactly three centre pieces of one kind between the front, top and right sides:' ],
        algs: [["2R U 2R' 2U 2R U' 2R' 2U'", 'Outer corner pieces of the centres.'],
               ["3R U 3R' 3U 3R U' 3R' 3U'", 'Inner corner pieces of the centres.'],
               ["2R U 2R' 3U 2R U' 2R' 3U'", 'The in-between pieces.'],
               ["M U M' 2U M U' M' 2U'", 'Outer pieces of the + shape.'],
               ["M U M' 3U M U' M' 3U'", 'Inner pieces of the + shape.']] },
      { h: 'Pair the edges', p: [
        'Each edge has five pieces: a middle piece, two inner pieces (layers 3 and 5) and two outer pieces (layers 2 and 6). Join the inner pieces to the middle piece, then add the outer ones.',
        'Put the pieces you already have in the front-right edge and the piece to add in the front-left edge, at the height of the slice you will use. Line up the colours: the left side of the left piece matches the front of the right pieces.',
        'Turn the top so the edge at the back of the top layer is unfinished, then do the algorithm for that height.' ],
        algs: [["3U' R U R' 3U", 'Adds the inner piece from layer 3 of the front-left edge.'],
               ["3D R U R' 3D'", 'Adds the inner piece from layer 5 of the front-left edge.'],
               ["2U' R U R' 2U", 'Adds the outer piece from layer 2 of the front-left edge.'],
               ["2D R U R' 2D'", 'Adds the outer piece from layer 6 of the front-left edge.']] },
      { h: 'Last two edges', p: [
        'Hold the last two edges at the front left and front right. These tools each swap one piece between the two edges. Each also swaps the other pair of pieces inside the front-right edge, so fix one kind of piece at a time.',
        'If one edge ends with two pieces of the same kind swapped, hold it at the front of the top and use the matching swap algorithm.' ],
        algs: [["2D R F' U R' F 2D'", 'Swaps the layer-2 piece of front right with the layer-6 piece of front left. Also swaps the two inner pieces of front right.'],
               ["3D R F' U R' F 3D'", 'Swaps the layer-3 piece of front right with the layer-5 piece of front left. Also swaps the two outer pieces of front right.'],
               ["R U R' F R' F' R", 'Turns the front-right edge over. Other edges move but stay paired.'],
               ["2R2 B2 U2 2L U2 2R' U2 2R U2 F2 2R F2 2L' B2 2R2", 'Swaps the two outer pieces of the top-front edge.'],
               ["3R2 B2 U2 3L U2 3R' U2 3R U2 F2 3R F2 3L' B2 3R2", 'Swaps the two inner pieces of the top-front edge.']] },
      SOLVE_AS_3x3,
    ],
  },
};
if (typeof module !== 'undefined') module.exports = { GUIDES, GUIDE_NOTATION };
