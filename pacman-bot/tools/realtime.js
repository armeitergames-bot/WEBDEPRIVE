// Prueba a velocidad real (reloj propio del juego), como en el navegador.
const path = require('path'), fs = require('fs');
const { chromium } = require(process.env.PW || 'playwright');
const gameDir = path.resolve(process.argv[2]); const secs = +(process.argv[3] || 60);
const src = path.join(__dirname, '..', 'src');
(async () => {
  const browser = await chromium.launch(); const page = await browser.newPage();
  page.on('pageerror', e => console.log('PAGEERROR', e.message));
  await page.addInitScript(fs.readFileSync(path.join(src, 'brain.js'), 'utf8') + '\n' + fs.readFileSync(path.join(src, 'hook.js'), 'utf8'));
  await page.goto('file://' + path.join(gameDir, 'index.html'));
  await page.evaluate(() => { document.f && document.f.btnI.click(); });
  for (let i = 0; i < secs / 10; i++) {
    await page.waitForTimeout(10000);
    console.log(await page.evaluate(() => { const G = __pacbot.G, s = __pacbot.stats;
      return JSON.stringify({ level: G.level, score: G.score && G.score[0], lives: G.lives, fps: G.fps, avgMs: +(s.ms / s.plans).toFixed(1), maxMs: +s.maxMs.toFixed(1), hud: !!document.getElementById('pacbot-hud') }); }));
  }
  await page.screenshot({ path: process.argv[4] || 'shot.png' });
  await browser.close();
})();
