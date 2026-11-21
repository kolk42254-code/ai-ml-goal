const { chromium } = require('playwright');
const file = 'file://' + process.argv[2];
const log = (...a) => console.log(...a);

// A stand-in for claude.ai's `sample` capability. mode: 'tools' | 'json' | 'error:<code>'
function claudeMock(mode) {
  return `
    window.__calls = [];
    window.claude = { use: async (name) => {
      if (name !== 'sample') return null;
      const mode = ${JSON.stringify(mode)};
      const fn = async (input, opts) => {
        window.__calls.push({ input, tier: opts && opts.modelTier, tools: !!(opts && opts.tools) });
        if (mode.startsWith('error:')) { await new Promise(r => setTimeout(r, 50)); throw { code: mode.slice(6), message: 'mock', reason: mode === 'error:rate_limited' ? 'usage_limit' : undefined }; }
        const t = opts.tools[0];
        const sig = new AbortController().signal;
        window.__toolResults = [];
        window.__toolResults.push(await t.execute({ moves: "R U R' U'" }, { signal: sig }));
        window.__toolResults.push(await t.execute({ moves: 'F2 foo 2R' }, { signal: sig }));
        opts.onText && opts.onText({ text: 'Working on the cross.', delta: 'Working on the cross.' });
        return { text: 'Working on the cross.\\n\\nI played two batches and will keep building the cross.', truncated: false, modelTierApplied: opts.modelTier || 'default' };
      };
      fn.json = async (input, opts) => { window.__calls.push({ input, json: true }); return { moves: "R U R' F", note: 'Trying a corner.' }; };
      fn.limits = async () => (mode === 'json' ? { maxPromptBytes: 262144, modelTiers: ['quick', 'default', 'complex'] } : { maxPromptBytes: 262144, tools: { maxCount: 8 }, modelTiers: ['quick', 'default', 'complex'] });
      return fn;
    } };`;
}

async function openPage(browser, init) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  if (init) await page.addInitScript(init);
  await page.goto(file);
  await page.waitForFunction(() => window.__t, null, { timeout: 20000 });
  await page.waitForTimeout(500);
  return { page, errors, ev: f => page.evaluate(f) };
}

(async () => {
  const browser = await chromium.launch();

  // ---- C2 retest: guide button six times on a solved 3x3 ----
  {
    const { page, errors, ev } = await openPage(browser);
    await page.click('#size3'); await page.waitForTimeout(200);
    await page.click('#btnGiveUp');
    await page.waitForFunction(() => __t.idle() && __t.phase() === 'free', null, { timeout: 15000 });
    await page.click('#tab-learn');
    await page.$$eval('#guideSteps details', ds => ds.forEach(d => { d.open = true; }));
    const b = await page.$('button[aria-label="Show me R U R\' U\'"]');
    for (let i = 0; i < 6; i++) await b.click();
    await page.waitForFunction(() => __t.idle(), null, { timeout: 30000 });
    log("C2 six times R U R' U' from solved -> solved again:", await ev(() => __t.isSolved()), '| errors', errors.length);
    await page.close();
  }

  // ---- Claude with the turn tool ----
  {
    const { page, errors, ev } = await openPage(browser, claudeMock('tools'));
    await page.click('#tab-ai');
    await page.waitForFunction(() => __t.claudeState() === 'ready', null, { timeout: 15000 });
    log('D1 Claude note:', await page.textContent('#claudeNote'));
    log('D1 Gemini blocked inside claude.ai:', await page.isDisabled('#geminiKey') ? 'yes (disabled)' : 'NO', '|', (await page.textContent('#geminiNote')).slice(0, 70));
    await page.selectOption('#claudeTier', 'complex');
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 60000 });
    const r = await ev(() => window.__toolResults);
    log('D2 tool call 1 played:', r[0].played, '| progress', r[0].progress_percent, '| solved', r[0].solved);
    log('D2 tool call 2 played:', r[1].played, '| skipped', JSON.stringify(r[1].skipped), '| moves left', r[1].moves_left);
    log('D2 cube text sent back has 6 sides:', (r[1].cube.match(/^[ULFRBD]:$/gm) || []).length);
    const calls = await ev(() => window.__calls);
    log('D2 tier sent:', calls[0].tier, '| prompt mentions inner layers:', /2R is the 2nd layer/.test(calls[0].input), '| has CURRENT CUBE:', calls[0].input.includes('CURRENT CUBE'));
    log('D2 moves box:', await page.textContent('#aiMoves'), '| status:', await page.textContent('#aiStatus'));
    log('D2 go button:', await page.textContent('#aiGo'), '| phase', await ev(() => __t.phase()));
    log('D2 log:', (await page.$$eval('#aiLog li', ls => ls.map(l => l.textContent))).join(' || ').slice(0, 400));
    // continue once, then stop
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 60000 });
    log('D3 after continue, moves:', await page.textContent('#aiMoves'));
    await page.click('#aiStop');
    await page.waitForTimeout(300);
    log('D3 stop ->', await ev(() => __t.phase()), '|', await page.textContent('#aiStatus'));
    log('D3 history line:', await page.textContent('#aiHistory'));
    // playing yourself works again, and give up restores the cube
    await page.click('#tab-play'); await page.click('#btnGiveUp');
    await page.waitForFunction(() => __t.idle() && __t.phase() === 'free', null, { timeout: 15000 });
    log('D4 give up after the AI game -> solved', await ev(() => __t.isSolved()), '| errors:', errors.length ? errors : 'none');
    await page.close();
  }

  // ---- Claude without tools (JSON answers) ----
  {
    const { page, errors, ev } = await openPage(browser, claudeMock('json'));
    await page.click('#tab-ai');
    await page.waitForFunction(() => __t.claudeState() === 'ready', null, { timeout: 15000 });
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 60000 });
    log('E1 JSON mode moves used:', await page.textContent('#aiMoves'), '| json call made:', (await ev(() => window.__calls)).some(c => c.json), '| errors', errors.length);
    await page.close();
  }

  // ---- Claude errors ----
  for (const code of ['rate_limited', 'not_granted']) {
    const { page, errors, ev } = await openPage(browser, claudeMock('error:' + code));
    await page.click('#tab-ai');
    await page.waitForFunction(() => __t.claudeState() === 'ready', null, { timeout: 15000 });
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 30000 });
    await page.waitForTimeout(200);
    log(`E2 ${code}: status "${await page.textContent('#aiStatus')}" | phase ${await ev(() => __t.phase())} | claude state ${await ev(() => __t.claudeState())} | go disabled ${await page.isDisabled('#aiGo')} | errors ${errors.length}`);
    await page.close();
  }

  // ---- Gemini from a local file (Google's API replaced by a stand-in) ----
  {
    const { page, errors, ev } = await openPage(browser);
    const seen = [];
    let mode = 'ok';
    await page.route('https://generativelanguage.googleapis.com/**', async route => {
      const req = route.request();
      seen.push({ url: req.url(), key: req.headers()['x-goog-api-key'], body: req.postData() });
      const cors = { 'access-control-allow-origin': '*', 'content-type': 'application/json' };
      if (req.url().includes('/models?')) {
        return route.fulfill({ status: 200, headers: cors, body: JSON.stringify({ models: [
          { name: 'models/gemini-flash-latest', displayName: 'Gemini Flash Latest', supportedGenerationMethods: ['generateContent', 'countTokens'] },
          { name: 'models/text-embedding-004', displayName: 'Embedding', supportedGenerationMethods: ['embedContent'] },
          { name: 'models/gemini-3.5-flash-lite', displayName: 'Gemini 3.5 Flash-Lite', supportedGenerationMethods: ['generateContent'] },
        ] }) });
      }
      if (mode === '429') return route.fulfill({ status: 429, headers: cors, body: JSON.stringify({ error: { code: 429, message: 'Resource exhausted' } }) });
      if (mode === 'badkey') return route.fulfill({ status: 400, headers: cors, body: JSON.stringify({ error: { code: 400, message: 'API key not valid: test-key-123 is wrong' } }) });
      return route.fulfill({ status: 200, headers: cors, body: JSON.stringify({ candidates: [{ content: { role: 'model', parts: [
        { text: 'Let me think about the corners first...', thought: true },
        { text: '```json\n{"moves": "R U R\' U\'", "note": "Moving a corner."}\n```' },
      ] } }] }) });
    });
    await page.click('#tab-ai');
    await page.click('#aiPickGemini');
    log('F1 Gemini note:', (await page.textContent('#geminiNote')).slice(0, 80), '| key enabled:', !(await page.isDisabled('#geminiKey')));
    log('F1 Claude here:', await ev(() => __t.claudeState()));
    await page.fill('#geminiKey', 'test-key-123');
    await page.check('#geminiRemember');
    log('F2 key stored when remembered:', await ev(() => localStorage.getItem('big-cube-lab:gemini-key')));
    await page.click('#geminiLoad');
    await page.waitForFunction(() => document.querySelectorAll('#geminiModel option').length >= 2, null, { timeout: 10000 });
    log('F2 models:', await page.$$eval('#geminiModel option', os => os.map(o => o.value).join(', ')), '| selected', await page.inputValue('#geminiModel'));
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 60000 });
    const gen = seen.filter(s => s.url.includes(':generateContent'));
    log(`F3 rounds sent: ${gen.length} | key header sent: ${gen.every(s => s.key === 'test-key-123')} | key never in URL: ${seen.every(s => !s.url.includes('test-key-123'))} | model in URL: ${gen[0] && gen[0].url.includes('gemini-flash-latest')}`);
    log('F3 moves used:', await page.textContent('#aiMoves'), '| status:', await page.textContent('#aiStatus'));
    mode = '429';
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 30000 });
    log('F4 429 ->', await page.textContent('#aiStatus'));
    mode = 'badkey';
    await page.click('#aiGo');
    await page.waitForFunction(() => !__t.aiBusy(), null, { timeout: 30000 });
    const bad = await page.textContent('#aiStatus');
    log('F5 bad key ->', bad, '| key hidden in the message:', !bad.includes('test-key-123'));
    await page.uncheck('#geminiRemember');
    log('F6 key removed when unticked:', await ev(() => localStorage.getItem('big-cube-lab:gemini-key')) === null);
    await page.click('#aiStop');
    log('F7 stopped ->', await ev(() => __t.phase()), '| errors:', errors.length ? errors : 'none');
    await page.close();
  }
  await browser.close();
})();
