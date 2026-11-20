// Review stills of a data reel at given seconds: node tools/stills_reel.js <dir> t1 t2 ...  (writes <dir>/stills/t-<s>.png)
const fs = require("fs"), path = require("path"), pw = require("playwright");
const [dir, ...ts] = process.argv.slice(2);
(async () => {
  const T = JSON.parse(fs.readFileSync(path.join(dir, "timing.json"), "utf8"));
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  p.on("pageerror", (e) => console.error("pageerror:", e.message));
  await p.goto("file://" + path.join(dir, "reel.html")); await p.evaluate(() => document.fonts.ready);
  await p.evaluate((x) => init(x), T);
  for (const t of ts) { await p.evaluate((v) => render(v), +t); await p.screenshot({ path: path.join(dir, "stills", `t-${t}.png`) }); }
  await b.close(); console.log("ok", ts.length);
})();
