// Render a 1080x1350 carousel page to a PDF (LinkedIn) and one PNG per <section> (Instagram), and report layout problems:
// anything running into the footer or across the side margins, a footer pushed off the slide, and the smallest text size.
//   node tools/render_carousel.js carousel/pulsedge-carousel.html [out.pdf] [png-prefix]   (outputs land next to the HTML)
const path = require("path"), { chromium } = require("playwright");

(async () => {
  const src = path.resolve(process.argv[2] || "carousel/pulsedge-carousel.html"), dir = path.dirname(src);
  const pdf = process.argv[3] || path.basename(src, ".html") + ".pdf", prefix = process.argv[4] || "slide";
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  await page.goto("file://" + src, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  const issues = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll("section").forEach((s, i) => {
      const sb = s.getBoundingClientRect(), f = s.querySelector(".foot"), pb = parseFloat(getComputedStyle(s).paddingBottom);
      if (!f) { out.push(`slide ${i + 1}: no .foot`); return; }
      const foot = f.getBoundingClientRect();
      s.querySelectorAll("*").forEach((el) => {
        if (el.closest(".foot") || el.closest(".bgl,.grid")) return;          // footer and full-bleed background layers
        const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
        const what = `"${(el.textContent || el.tagName).trim().slice(0, 40)}"`;
        if (r.bottom > foot.top + 1) out.push(`slide ${i + 1}: ${what} ends ${Math.round(r.bottom - foot.top)}px into the footer`);
        if (r.right > sb.right - 79 || r.left < sb.left + 79) out.push(`slide ${i + 1}: ${what} crosses a side margin`);
      });
      if (foot.bottom > sb.bottom - pb + 1) out.push(`slide ${i + 1}: footer pushed down ${Math.round(foot.bottom - (sb.bottom - pb))}px`);
    });
    let min = 99;
    document.querySelectorAll("section *").forEach((el) => { if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) min = Math.min(min, parseFloat(getComputedStyle(el).fontSize)); });
    out.push(`smallest text: ${min}px`);
    return out;
  });
  console.log(issues.join("\n"));
  await page.pdf({ path: path.join(dir, pdf), width: "1080px", height: "1350px", printBackground: true });
  const secs = await page.$$("section");
  for (let i = 0; i < secs.length; i++) await secs[i].screenshot({ path: path.join(dir, `${prefix}-${i + 1}.png`) });
  await browser.close();
  console.log(`${secs.length} slides -> ${path.join(dir, pdf)}`);
})().catch((e) => { console.error(e); process.exit(1); });
