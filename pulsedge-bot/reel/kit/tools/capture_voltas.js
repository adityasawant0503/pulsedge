const pw = require("playwright"), fs = require("fs"), path = require("path");
const OUT = process.argv[2], FONTS = process.env.PE_FONTS || require("path").join(__dirname, "..", "..", "fonts"), BASE = "http://127.0.0.1:8766/";
const meta = {};
(async () => {
  const b = await pw.chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, colorScheme: "dark", timezoneId: "Asia/Kolkata", locale: "en-IN" });
  await c.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", body: [400, 500, 600].map((w) => `@font-face{font-family:"IBM Plex Sans";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-sans-latin-${w}-normal.woff2) format("woff2")}@font-face{font-family:"IBM Plex Mono";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-mono-latin-${w}-normal.woff2) format("woff2")}`).join("\n") }));
  await c.route(/fonts\.gstatic\.com\/local\//, (r) => { const f = path.join(FONTS, path.basename(new URL(r.request().url()).pathname)); fs.existsSync(f) ? r.fulfill({ contentType: "font/woff2", body: fs.readFileSync(f) }) : r.abort(); });
  await c.route(/formspree\.io|workers\.dev/, (r) => r.fulfill({ contentType: "application/json", body: '{"ok":true}' }));
  await c.addInitScript(() => { if (!localStorage.pe_trial) localStorage.pe_trial = JSON.stringify({ email: "you@example.com", at: new Date().toISOString(), n: 5, sent: 1 }); });
  const p = await c.newPage(); p.on("pageerror", (e) => console.error("pageerror:", e.message));
  const R = (r) => (r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null);
  const box = async (loc) => R(await loc.first().boundingBox().catch(() => null));
  const shot = async (n, r) => { await p.waitForTimeout(450); await p.screenshot({ path: path.join(OUT, n + ".png") }); meta[n] = r || {}; console.log("shot", n, JSON.stringify(r || {})); };
  const scrollTo = async (y) => { await p.evaluate((v) => window.scrollTo(0, v), y); await p.waitForTimeout(300); };
  const topOf = async (loc) => (await loc.first().evaluate((e) => e.getBoundingClientRect().top + window.scrollY));
  await p.goto(BASE + "terminal.html"); await p.waitForTimeout(1800);
  for (const name of ["Urban Company", "Voltas"]) {
    await scrollTo(0); await p.click("#q"); await p.fill("#q", ""); await p.keyboard.type(name); await p.waitForTimeout(700);
    await p.keyboard.press("Enter"); await p.waitForTimeout(900);
    const add = p.locator("button", { hasText: /Add to My stocks/ }).first();
    if (await add.count()) { await add.click(); await p.waitForTimeout(500); console.log("added", name); }
    await p.locator("button", { hasText: /All news/ }).first().click().catch(() => {}); await p.waitForTimeout(500);
  }
  const mine = p.locator('.tab[data-t="mine"]').first(); await mine.scrollIntoViewIfNeeded(); await mine.click(); await p.waitForTimeout(900);
  console.log("cards:", await p.evaluate(() => [...document.querySelectorAll(".sig")].map((s) => (s.querySelector("h3") || s).textContent.trim().slice(0, 70))));
  for (const [n, re] of [["filing", "The company is starting to sell air conditioners."], ["own", "under its own brand"]]) {
    const card = p.locator(".sig").filter({ hasText: re }).first();
    if (!(await card.count())) { console.log("missing", n); continue; }
    await scrollTo((await topOf(card)) - 110);
    const tm = await card.evaluate((c) => { const e = [...c.querySelectorAll("*")].find((x) => /^\d{1,2}:\d{2}(:\d{2})?$|^\d{1,2} \w{3} \d{1,2}:\d{2}$|Today|Yesterday|\d{2} Nov/.test(x.textContent.trim()) && x.children.length === 0); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height), e.textContent.trim()]; });
    await shot(n, { card: await box(card), head: await box(card.locator("h3")), time: tm, src: await box(card.locator("text=/NSE Announcements|Business Standard/")) });
  }
  fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
