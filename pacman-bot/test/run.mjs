// Prueba automática: abre el Pac-Man de prueba, inyecta el bot y lo deja jugar.
// Uso: node test/run.mjs [segundos] [turbo]
import { chromium } from 'playwright';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const secs = +(process.argv[2] || 60);
const turbo = +(process.argv[3] || 1);
const bot = fs.readFileSync(path.join(here, '../extension/bot.js'), 'utf8');

const browser = await chromium.launch();
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('PAGE ERROR', e.message));
await page.addInitScript(bot);
await page.goto('file://' + path.join(here, 'mock-pacman.html'));
await page.evaluate((t) => { window.__pacBot.setEnabled(true); window.__pacBot.setTurbo(t); }, turbo);
for (let i = 0; i < secs; i += 5) {
  await page.waitForTimeout(5000);
  const st = await page.evaluate(() => {
    const m = window.__mock, S = window.__pacBot.state;
    return `t=${m.t.toFixed(0)} L${m.level} cleared=${m.levelsCleared} deaths=${m.deaths} games=${m.games} score=${m.score} ghostsEaten=${m.ghostsEaten||0} | bot: pac=${!!S.pac} mode=${S.mode} tiles=${window.__pacBot.graph.adj.size} fake=${[...window.__pacBot.graph.adj.keys()].filter(k=>{const [c,r]=k.split(',').map(Number);return !(r>=0&&r<31&&c>=0&&c<28&&' .o'.includes(MAP[r][c]))}).join(' ')} err=${S.lastError ? S.lastError.slice(0,200) : ''}`;
  });
  console.log(st);
}
if (process.env.SHOT) {
  await page.evaluate(() => { window.__pacBot.state.showBrain = true; });
  await page.waitForTimeout(300);
  await page.screenshot({ path: process.env.SHOT });
}
console.log(JSON.stringify(await page.evaluate(() => window.__pacBot.diagnostics())).slice(0, 1500));
await browser.close();
