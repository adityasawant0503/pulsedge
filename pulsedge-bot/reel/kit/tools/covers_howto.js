// Feed cover + highlight covers for the how-to set: node tools/covers_howto.js <dir>  (writes <dir>/out/*.jpg)
const pw = require("playwright"), path = require("path");
const dir = process.argv[2];
(async () => {
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.goto("file://" + path.join(dir, "covers.html")); await p.evaluate(() => document.fonts.ready);
  await p.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  for (const [id, f] of [["feed", "pulsedge-how-to-cover.jpg"], ["hl-howto", "highlight-cover-how-to.jpg"], ["hl-start", "highlight-cover-start.jpg"]])
    await p.locator("#" + id).screenshot({ path: path.join(dir, "out", f), type: "jpeg", quality: 94 });
  await b.close(); console.log("ok");
})();
