const pw = require("playwright"), path = require("path");
const dir = process.argv[2];
(async () => {
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.goto("file://" + path.join(dir, "cover-routine.html")); await p.evaluate(() => document.fonts.ready);
  await p.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  await p.locator("#feed").screenshot({ path: path.join(dir, "out", "PulsEdge-2-Minute-Routine-cover.jpg"), type: "jpeg", quality: 94 });
  await b.close(); console.log("ok");
})();
