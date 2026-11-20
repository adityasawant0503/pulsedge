// Review stills of one how-to episode: node tools/stills_howto.js <dir> <ep> t1,t2,...  (writes <dir>/stills/)
const pw = require("playwright"), fs = require("fs"), path = require("path");
const [dir, ep, times] = process.argv.slice(2);
(async () => {
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  p.on("pageerror", (e) => console.error("pageerror:", e.message));
  await p.goto("file://" + path.join(dir, "guide.html")); await p.evaluate(() => document.fonts.ready);
  const data = { timing: JSON.parse(fs.readFileSync(path.join(dir, `timing-ep${ep}.json`))), meta: JSON.parse(fs.readFileSync(path.join(dir, "cap", "meta.json"))) };
  console.log(JSON.stringify(await p.evaluate((x) => init(x), data)));
  await p.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  const outs = [];
  for (const t of times.split(",").map(Number)) { await p.evaluate((x) => render(x), t); const f = path.join(dir, "stills", `e${ep}-${t.toFixed(2)}.png`); await p.screenshot({ path: f }); outs.push(f); }
  await b.close(); console.log(outs.length);
})().catch((e) => { console.error(e); process.exit(1); });
