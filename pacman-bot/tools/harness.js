// Banco de pruebas: corre el doodle (copia local de macek/google_pacman) en
// Chromium headless, inyecta el bot y acelera el tiempo del juego.
// Uso: node tools/harness.js <ruta a google_pacman> [segundos-reales-max] [semilla-ignorada]
const path = require('path');
const fs = require('fs');
const { chromium } = require(process.env.PW || 'playwright');

const gameDir = path.resolve(process.argv[2] || 'google_pacman');
const maxSec = +(process.argv[3] || 120);
const src = path.join(__dirname, '..', 'src');
const brain = fs.readFileSync(path.join(src, 'brain.js'), 'utf8');
const hook = fs.readFileSync(path.join(src, 'hook.js'), 'utf8');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('PAGEERROR', e.message));
  page.on('console', m => { if (/PacBot|Error/.test(m.text())) console.log('console:', m.text()); });
  await page.addInitScript(brain + '\n' + hook);
  await page.goto('file://' + path.join(gameDir, 'index.html'));
  await page.evaluate(() => { google.pml_installed || (document.f && document.f.btnI.click()); });
  await page.waitForFunction(() => window.__pacbot && __pacbot.G && __pacbot.G.ready && __pacbot.G.actors, null, { timeout: 30000 });
  // Tomamos control del reloj: ejecutamos ticks lo más rápido posible
  await page.evaluate(() => {
    const G = __pacbot.G;
    clearInterval(G.tickTimer);
    G.initializeTickTimer = function () {};
    const D = 90;
    window.__step = function () {
      if (G.gameplayMode == 13) {
        G.advanceCutscene(); G.intervalTime = (G.intervalTime + 1) % D; G.globalTime++; G.checkCutscene();
      } else {
        G.moveActors();
        if (G.gameplayMode == 0 && G.tilesChanged) { G.detectCollisions(); G.updateActorTargetPositions(); }
        G.globalTime++; G.intervalTime = (G.intervalTime + 1) % D;
        G.blinkEnergizers(); G.blinkScoreLabels(); G.handleTimers();
      }
    };
    window.__log = [];
    let lastLives = G.lives, lastLevel = G.level;
    window.__run = function (n) {
      for (let i = 0; i < n; i++) {
        if (G.gameplayMode == 8 || G.gameplayMode == 14) return 'over';
        try { window.__step(); } catch (e) { window.__errs = (window.__errs || 0) + 1; }
        if (G.lives < lastLives || (G.gameplayMode == 2 && !window.__dying)) {
          if (G.gameplayMode == 2 && !window.__dying) {
            window.__dying = true;
            const p = G.actors[0];
            __log.push('MUERTE nivel ' + G.level + ' score ' + G.score[0] + ' dots ' + G.dotsRemaining + ' pac ' + p.tilePos.map(v=>v/8) + ' ghosts ' + G.actors.slice(1).map(a => a.mode + '@' + a.tilePos.map(v=>v/8)).join(' '));
          }
        }
        if (G.gameplayMode != 2 && G.gameplayMode != 3) window.__dying = false;
        lastLives = G.lives;
        if (G.level != lastLevel) { __log.push('nivel ' + G.level + ' score ' + G.score[0] + ' vidas ' + G.lives); lastLevel = G.level; }
      }
      return 'ok';
    };
  });
  const t0 = Date.now();
  let res = 'ok';
  while (res === 'ok' && (Date.now() - t0) / 1000 < maxSec) {
    res = await page.evaluate(() => __run(3000));
    const logs = await page.evaluate(() => __log.splice(0));
    logs.forEach(l => console.log(l));
  }
  const st = await page.evaluate(() => {
    const G = __pacbot.G, s = __pacbot.stats;
    return { level: G.level, score: G.score[0], lives: G.lives, mode: G.gameplayMode, gameErrors: window.__errs || 0, avgMs: s.ms / s.plans, maxMs: s.maxMs, plans: s.plans };
  });
  console.log(res === 'over' ? 'GAME OVER' : 'TIEMPO', JSON.stringify(st), ((Date.now() - t0) / 1000).toFixed(0) + 's');
  await browser.close();
})();
