// Highlight covers: 1080x1080 JPEGs in three colourways (Light is the one in use), plus a mock of the profile's highlight row.
//   node tools/highlight_covers.js <dir holding highlight-covers.html>   (writes highlight-*.jpg and highlight-preview.png there)
const pw = require("playwright"), path = require("path"), fs = require("fs");
const dir = process.argv[2];
(async () => {
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1170, height: 1200 } });
  await p.goto("file://" + path.join(dir, "highlight-covers.html")); await p.evaluate(() => document.fonts.ready);
  const ids = await p.evaluate(() => [...document.querySelectorAll(".cv")].map((e) => e.id));
  for (const id of ids) await p.locator("#" + id).screenshot({ path: path.join(dir, `highlight-${id}.jpg`), type: "jpeg", quality: 95 });
  await p.evaluate(() => {
    const m = document.getElementById("mock"), K = [["howto", "How to"], ["start", "Start"], ["explained", "Explained"]];
    [["dark", "Dark"], ["light", "Light"], ["purple", "Purple"]].forEach(([w, lab]) => {
      const r = document.createElement("div"); r.className = "row";
      r.innerHTML = `<div class="tag">${lab}</div>` + K.map(([k, n]) => `<div class="hl"><div class="ring"><img src="highlight-${w}-${k}.jpg"></div><div class="nm">${n}</div></div>`).join("");
      m.appendChild(r);
    });
    document.getElementById("covers").style.display = "none";
  });
  await p.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  await p.locator("#mock").screenshot({ path: path.join(dir, "highlight-preview.png") });
  await b.close(); console.log(ids.length, "covers");
})().catch((e) => { console.error(e); process.exit(1); });
