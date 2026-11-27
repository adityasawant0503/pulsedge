// Capture the screens for the "2-minute market routine" reel at 3x, with the position (site px) of everything we point at.
//   node tools/capture_routine.js <dir>/cap   (site served at PE_BASE, default http://127.0.0.1:8766/)
// Served from a local copy of the site; form posts and API calls are intercepted, nothing is sent.
const pw = require("playwright"), fs = require("fs"), path = require("path");
const OUT = process.argv[2], FONTS = process.env.PE_FONTS || path.join(__dirname, "..", "..", "fonts"), BASE = process.env.PE_BASE || "http://127.0.0.1:8766/";
const meta = {};
(async () => {
  const b = await pw.chromium.launch();
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, colorScheme: "dark", timezoneId: "Asia/Kolkata", locale: "en-IN" });
  await c.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", body: [400, 500, 600].map((w) => `@font-face{font-family:"IBM Plex Sans";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-sans-latin-${w}-normal.woff2) format("woff2")}@font-face{font-family:"IBM Plex Mono";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-mono-latin-${w}-normal.woff2) format("woff2")}`).join("\n") }));
  await c.route(/fonts\.gstatic\.com\/local\//, (r) => { const f = path.join(FONTS, path.basename(new URL(r.request().url()).pathname)); fs.existsSync(f) ? r.fulfill({ contentType: "font/woff2", body: fs.readFileSync(f) }) : r.abort(); });
  await c.route(/formspree\.io|workers\.dev/, (r) => r.fulfill({ contentType: "application/json", body: '{"ok":true}' }));
  await c.addInitScript(() => { if (!localStorage.pe_trial) localStorage.pe_trial = JSON.stringify({ email: "you@example.com", at: new Date().toISOString(), n: 5, sent: 1 }); localStorage.pe_pm_open = "1"; });
  const p = await c.newPage(); p.on("pageerror", (e) => console.error("pageerror:", e.message));
  const R = (r) => (r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null);
  const box = async (loc) => R(await loc.first().boundingBox().catch(() => null));
  const boxes = async (sel) => p.evaluate((s) => [...document.querySelectorAll(s)].map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }), sel);
  const shot = async (n, r) => { await p.waitForTimeout(450); await p.screenshot({ path: path.join(OUT, n + ".png") }); meta[n] = r || {}; console.log("shot", n, JSON.stringify(r || {})); };
  const scrollTo = async (y) => { await p.evaluate((v) => window.scrollTo(0, v), y); await p.waitForTimeout(300); };
  const topOf = async (loc) => (await loc.first().evaluate((e) => e.getBoundingClientRect().top + window.scrollY));

  await p.goto(BASE + "terminal.html"); await p.waitForTimeout(1800);
  // 1. Pre-market panel, open, with each checklist row
  const open = await p.evaluate(() => { const b = document.getElementById("pm-body"); return b && b.offsetHeight > 0; });
  if (!open) { await p.click("#pm-tog"); await p.waitForTimeout(500); }
  await scrollTo((await topOf(p.locator("#pm-tog"))) - 70);
  const rows = await boxes("#pm-cl > li");
  await shot("pm", { tog: await box(p.locator("#pm-tog")), list: await box(p.locator("#pm-cl")), rows });
  console.log("pm rows:", await p.evaluate(() => [...document.querySelectorAll("#pm-cl > li .ct")].map((x) => x.textContent.trim())));

  // 2. The tab bar, then Act now
  const tabs = p.locator("[role=tablist]").first(); await scrollTo((await topOf(tabs)) - 160);
  await shot("tabs", { bar: await box(tabs), ideas: await box(p.locator('.tab[data-t="ideas"]')), money: await box(p.locator('.tab[data-t="money"]')), mine: await box(p.locator('.tab[data-t="mine"]')) });
  await p.locator('.tab[data-t="ideas"]').first().click(); await p.waitForTimeout(700);
  await scrollTo((await topOf(tabs)) - 160);
  await shot("ideas", { tab: await box(p.locator('.tab[data-t="ideas"]')), card: await box(p.locator(".sig")), n: await p.locator(".sig").count(), text: (await p.locator(".sig h3").first().textContent().catch(() => "")).trim() });

  // 3. Big money
  await p.locator('.tab[data-t="money"]').first().click(); await p.waitForTimeout(700);
  await scrollTo((await topOf(tabs)) - 160);
  await shot("money", { tab: await box(p.locator('.tab[data-t="money"]')), card: await box(p.locator(".sig")), text: (await p.locator(".sig h3").first().textContent().catch(() => "")).trim() });

  // 4. My stocks, with one stock added through search
  await scrollTo(0); await p.click("#q"); await p.keyboard.type("Torrent Power"); await p.waitForTimeout(700); console.log("suggest:", await p.evaluate(() => [...document.querySelectorAll("#q-list li")].map((x) => x.textContent.trim()).slice(0, 4)));
  await p.keyboard.press("Enter"); await p.waitForTimeout(900);
  const add = p.locator("button", { hasText: /Add to My stocks/ }).first();
  if (await add.count()) { await add.click(); await p.waitForTimeout(500); }
  await p.locator("button", { hasText: /All news/ }).first().click().catch(() => {}); await p.waitForTimeout(500);
  const mine = p.locator('.tab[data-t="mine"]').first(); await mine.scrollIntoViewIfNeeded(); await mine.click(); await p.waitForTimeout(800);
  await scrollTo((await topOf(p.locator("[role=tablist]"))) - 160);
  await shot("mine", { tab: await box(mine), card: await box(p.locator(".sig")), n: await p.locator(".sig").count(), text: (await p.locator(".sig h3").first().textContent().catch(() => "")).trim() });

  const mc = p.locator(".sig").first(); await scrollTo((await topOf(mc)) - 110);
  await shot("mine2", { card: await box(mc) });
  // 5. Ask on a card: back to All, first card with an Ask button near the top
  await p.locator('.tab[data-t="' + (process.env.ASK_TAB || "all") + '"]').first().click(); await p.waitForTimeout(700);
  const card = p.locator(".sig").filter({ has: p.locator(".askb") }).first();
  await scrollTo((await topOf(card)) - 120);
  const askb = card.locator(".askb").first();
  await shot("card", { card: await box(card), ask: await box(askb), text: (await card.locator("h3").first().textContent()).trim() });
  await askb.click(); await p.waitForTimeout(2200);
  await p.evaluate(() => { const m = document.querySelector(".chm"), u = m && [...m.querySelectorAll(".msg.u")].pop(); if (u) m.scrollTop += u.getBoundingClientRect().top - m.getBoundingClientRect().top - 12; }); await p.waitForTimeout(300);
  await shot("chat", { user: await box(p.locator(".msg.u").last()), bot: await box(p.locator(".msg.b").last()), q: (await p.locator(".msg.u").last().innerText().catch(() => "")).trim() });
  console.log("answer:", (await p.locator(".msg.b").last().innerText().catch(() => "")).replace(/\n+/g, " | ").slice(0, 400));
  fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
