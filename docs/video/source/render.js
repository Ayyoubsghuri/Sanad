const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto('file://' + __dirname + '/promo.html'); await p.evaluate(() => window.ready); await p.waitForTimeout(500);
  const FPS = 30, N = 16 * FPS;
  for (let i = 0; i < N; i++) {
    await p.evaluate(t => window.render(t), i / FPS);
    await p.screenshot({ path: `frames/f${String(i).padStart(4, '0')}.jpg`, type: 'jpeg', quality: 92 });
  }
  await b.close();
})();
