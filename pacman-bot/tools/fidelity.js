// Verifica que el simulador del cerebro predice exactamente el juego real.
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PW || 'playwright');
const gameDir = path.resolve(process.argv[2]);
const src = path.join(__dirname, '..', 'src');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('PAGEERROR', e.message));
  await page.addInitScript(fs.readFileSync(path.join(src, 'brain.js'), 'utf8') + '\n' + fs.readFileSync(path.join(src, 'hook.js'), 'utf8'));
  await page.goto('file://' + path.join(gameDir, 'index.html'));
  await page.evaluate(() => { document.f && document.f.btnI.click(); });
  await page.waitForFunction(() => window.__pacbot && __pacbot.G && __pacbot.G.ready && __pacbot.G.actors, null, { timeout: 30000 });
  const out = await page.evaluate(() => {
    const G = __pacbot.G, B = PacBrain._sim; clearInterval(G.tickTimer);
    const D = 90;
    function step() {
      if (G.gameplayMode == 13) { G.advanceCutscene(); G.intervalTime = (G.intervalTime + 1) % D; G.globalTime++; G.checkCutscene(); }
      else { G.moveActors(); if (G.gameplayMode == 0 && G.tilesChanged) { G.detectCollisions(); G.updateActorTargetPositions(); }
        G.globalTime++; G.intervalTime = (G.intervalTime + 1) % D; G.blinkEnergizers(); G.blinkScoreLabels(); G.handleTimers(); }
    }
    let checks = 0, bad = 0, msgs = [];
    for (let it = 0; it < 400000 && G.gameplayMode != 8 && checks < 250; it++) {
      if (it % 37 == 0 && G.gameplayMode == 0) {
        __pacbot.enabled = false;
        B.buildMap();
        const S = B.snapshot(); S.noAuto = true;
        const K = 120;
        let ok = true, lastTile = '';
        for (let k = 0; k < K; k++) {
          if (G.gameplayMode != 0 && G.gameplayMode != 1) { ok = false; break; }
          const p = G.actors[0], tile = p.tilePos + '';
          if (G.gameplayMode == 0 && (tile != lastTile || p.dir == 0)) {
            lastTile = tile;
            const c = PacBrain.plan();
            if (c) { PacBrain.applyChoice(p, c.dir); if (S.mode == 0) B.applyChoice(S, S.actors[0], c.dir); }
          }
          step(); B.simTick(S);
        }
        __pacbot.enabled = true;
        if (!ok || S.dead) continue;
        checks++;
        const diffs = [];
        G.actors.forEach((a, i) => {
          const s = S.actors[i];
          if (a.pos[0] != s.pos[0] || a.pos[1] != s.pos[1] || a.mode != s.mode || a.dir != s.dir) diffs.push(i + ': real ' + a.pos + ' m' + a.mode + ' d' + a.dir + ' sim ' + s.pos + ' m' + s.mode + ' d' + s.dir);
        });
        if (G.randSeed != S.randSeed) diffs.push('seed');
        if (G.dotsRemaining != S.dotsRemaining) diffs.push('dots ' + G.dotsRemaining + ' vs ' + S.dotsRemaining);
        if (G.mainGhostMode != S.mainGhostMode) diffs.push('main ' + G.mainGhostMode + ' vs ' + S.mainGhostMode);
        if (diffs.length) { bad++; if (msgs.length < 15) msgs.push('L' + G.level + ' ' + diffs.join(' | ')); }
      } else step();
    }
    return { checks, bad, msgs, level: G.level, score: G.score[0] };
  });
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
