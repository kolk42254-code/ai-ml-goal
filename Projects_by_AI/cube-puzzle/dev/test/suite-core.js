const { chromium } = require('playwright');
const file = 'file://' + process.argv[2];
const log = (...a) => console.log(...a);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(file);
  await page.waitForFunction(() => window.__t, null, { timeout: 20000 });
  await page.waitForTimeout(600);
  const ev = f => page.evaluate(f);
  log('A1 status:', await page.textContent('#status'), '| worker:', await ev(() => __t.worker()));
  // A2: solve by typing the inverse scramble
  const scr = (await page.textContent('#scrambleText')).trim().split(/\s+/);
  for (const tok of scr.slice().reverse()) {
    const m = tok.match(/^(\d*)([RUFLDB])('?)$/);
    if (m[1]) await page.keyboard.press(m[1]);
    await page.keyboard.press(m[3] ? m[2] : 'Shift+' + m[2]);
  }
  await page.waitForFunction(() => __t.phase() === 'solved', null, { timeout: 30000 }).catch(() => {});
  log('A2 typed inverse scramble -> phase', await ev(() => __t.phase()), '| solved', await ev(() => __t.isSolved()), '| time', await page.textContent('#time'));
  await page.waitForTimeout(1700);
  // A3: state text after R on a solved cube in the default view
  await page.keyboard.press('R'); await page.waitForTimeout(400);
  const st = await ev(() => __t.stateText());
  const lines = st.split('\n');
  log('A3 after R: U rows', JSON.stringify(lines.slice(1, 5)), '| F rows', JSON.stringify(lines.slice(11, 15)));
  await page.keyboard.press('Shift+R'); await page.waitForTimeout(400);
  log("A3 back to solved after R':", await ev(() => __t.isSolved()));
  // B: solver on 4x4: pace, highlight, pause, step, speed, finish
  await page.click('#btnScramble'); await page.waitForTimeout(300);
  await page.click('#tab-solver');
  await page.click('#btnSolve');
  await page.waitForFunction(() => __t.bot() && !__t.bot().thinking, null, { timeout: 15000 });
  const t0 = Date.now(); const d0 = await ev(() => __t.bot().done);
  await page.waitForTimeout(3000);
  const d1 = await ev(() => __t.bot().done);
  log(`B1 default pace: ${d1 - d0} quarter turns in ${((Date.now() - t0) / 1000).toFixed(1)} s | highlighted bodies: ${await ev(() => __t.highlighted())} | playbar visible: ${await page.isVisible('#playbar')}`);
  log('B1 steps panel:', (await page.textContent('#solverSteps')).replace(/\s+/g, ' ').slice(0, 160));
  await page.click('#pbPause'); await page.waitForTimeout(300);
  const p0 = await ev(() => __t.bot().done); await page.waitForTimeout(1500); const p1 = await ev(() => __t.bot().done);
  await page.click('#pbStep'); await page.waitForTimeout(700); const p2 = await ev(() => __t.bot().done);
  log(`B2 paused: ${p1 - p0} turns in 1.5 s (want 0) | after Step: +${p2 - p1}`);
  await page.click('#pbPause');
  await page.$eval('#pbSpeed', el => { el.value = '9'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  const f0 = await ev(() => __t.bot().done); await page.waitForTimeout(1000); const f1 = await ev(() => __t.bot().done);
  log(`B3 top speed: ${f1 - f0} turns in 1 s | label ${await page.textContent('#pbSpeedOut')}`);
  await page.click('#pbFinish');
  await page.waitForFunction(() => __t.phase() === 'free', null, { timeout: 10000 });
  log('B4 finish now -> solved', await ev(() => __t.isSolved()), '|', await page.textContent('#status'));
  // B5: stop on 5x5
  await page.$eval('#pbSpeed', el => { el.value = '2'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.click('#size5'); await page.waitForTimeout(300);
  await page.click('#btnSolve');
  await page.waitForFunction(() => __t.bot() && !__t.bot().thinking, null, { timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.click('#pbStop'); await page.waitForTimeout(300);
  log('B5 stop ->', await ev(() => __t.phase()), '| solved', await ev(() => __t.isSolved()), '|', await page.textContent('#status'), '| playbar hidden', !(await page.isVisible('#playbar')));
  // B6: give up after a stopped solver returns to solved
  await page.click('#tab-play'); await page.click('#btnGiveUp');
  await page.waitForFunction(() => __t.phase() === 'free' && !__t.queue().length, null, { timeout: 15000 });
  log('B6 give up after stop -> solved', await ev(() => __t.isSolved()));
  // B7: 7x7 solve, finish now
  await page.click('#size7'); await page.waitForTimeout(300); await page.click('#tab-solver'); await page.click('#btnSolve');
  await page.waitForFunction(() => __t.bot() && !__t.bot().thinking, null, { timeout: 20000 });
  await page.click('#pbFinish');
  await page.waitForFunction(() => __t.phase() === 'free', null, { timeout: 20000 });
  log('B7 7x7 ->', await ev(() => __t.isSolved()), '|', await page.textContent('#status'));
  // C: every guide button on every size
  await page.click('#tab-learn');
  for (const n of [3, 4, 5, 6, 7]) {
    await page.click('#size' + n); await page.waitForTimeout(250);
    const title = await page.textContent('#guideTitle');
    await page.$$eval('#guideSteps details', ds => ds.forEach(d => { d.open = true; }));
    const btns = await page.$$('.showme');
    for (const b of btns) await b.click();
    await page.waitForFunction(() => !__t.queue().length, null, { timeout: 180000 });
    await page.waitForTimeout(300);
    log(`C ${n}x${n}: "${title}" | ${btns.length} Show me buttons played | moves counted ${await page.textContent('#statMoves')}`);
  }
  // C2: R U R' U' six times on a solved 3x3 returns to solved
  await page.click('#size3'); await page.waitForTimeout(200);
  await page.click('#tab-play'); await page.click('#btnGiveUp');
  await page.waitForFunction(() => __t.phase() === 'free' && !__t.queue().length, null, { timeout: 15000 });
  await page.click('#tab-learn');
  await page.$$eval('#guideSteps details', ds => ds.forEach(d => { d.open = true; }));
  const sexy = await page.$('button[aria-label="Show me R U R\' U\'"]');
  for (let i = 0; i < 6; i++) await sexy.click();
  await page.waitForFunction(() => !__t.queue().length, null, { timeout: 30000 }); await page.waitForTimeout(300);
  log("C2 six times R U R' U' from solved -> solved again:", await ev(() => __t.isSolved()));
  log('errors:', errors.length ? errors : 'none');
  await browser.close();
})();
