// Capture the real PulsEdge screens for the 3-part how-to, at 3x, plus the on-screen position (site px) of the things we point at.
//   node tools/capture_howto.js <dir>/cap   (site served at PE_BASE, default http://127.0.0.1:8766/)
// Served from a local copy of the site; form posts and API calls are intercepted, nothing is sent.
const pw = require("playwright"), fs = require("fs"), path = require("path");
const OUT = process.argv[2], FONTS = path.join(__dirname, "..", "..", "fonts"), BASE = process.env.PE_BASE || "http://127.0.0.1:8766/";
const meta = {};
(async () => {
  const b = await pw.chromium.launch();
  async function mk(trial) {
    const c = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, colorScheme: "dark", timezoneId: "Asia/Kolkata", locale: "en-IN" });
    await c.route(/fonts\.googleapis\.com/, (r) => r.fulfill({ contentType: "text/css", body: [400, 500, 600].map((w) => `@font-face{font-family:"IBM Plex Sans";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-sans-latin-${w}-normal.woff2) format("woff2")}@font-face{font-family:"IBM Plex Mono";font-weight:${w};src:url(https://fonts.gstatic.com/local/ibm-plex-mono-latin-${w}-normal.woff2) format("woff2")}`).join("\n") }));
    await c.route(/fonts\.gstatic\.com\/local\//, (r) => { const f = path.join(FONTS, path.basename(new URL(r.request().url()).pathname)); fs.existsSync(f) ? r.fulfill({ contentType: "font/woff2", body: fs.readFileSync(f) }) : r.abort(); });
    await c.route(/formspree\.io|workers\.dev/, (r) => r.fulfill({ contentType: "application/json", body: '{"ok":true}' }));
    if (trial) await c.addInitScript(() => { if (!localStorage.pe_trial) localStorage.pe_trial = JSON.stringify({ email: "you@example.com", at: new Date().toISOString(), n: 5, sent: 1 }); localStorage.pe_pm_open = "1"; });
    const p = await c.newPage(); p.on("pageerror", (e) => console.error("pageerror:", e.message));
    return p;
  }
  const R = (r) => (r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null);
  const box = async (loc) => R(await loc.first().boundingBox().catch(() => null));
  const boxJS = async (p, fn, arg) => p.evaluate(([src, a]) => { const e = new Function("__arg", src)(a); if (!e) return null; const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }, [fn, arg]);
  const shot = async (p, n, r) => { await p.waitForTimeout(450); await p.screenshot({ path: path.join(OUT, n + ".png") }); meta[n] = r || {}; console.log("shot", n, JSON.stringify(r || {})); };
  const scrollTo = async (p, y) => { await p.evaluate((v) => window.scrollTo(0, v), y); await p.waitForTimeout(250); };
  const topOf = async (loc) => (await loc.first().evaluate((e) => e.getBoundingClientRect().top + window.scrollY));

  // ---------- Episode 1: get started ----------
  let p = await mk(false); await p.goto(BASE + "index.html"); await p.waitForTimeout(1500);
  await shot(p, "home", { cta: await box(p.locator('a.btn.pri.lg[href="terminal.html#trial"]')) });
  await p.goto(BASE + "terminal.html#trial"); await p.waitForSelector(".pe-card input[type=email]"); await p.waitForTimeout(600);
  const EMAIL = "you@example.com", inp = p.locator(".pe-card input[type=email]").first();
  const g = { input: await box(inp), btn: await box(p.locator(".pe-card button.pe-b:not(.ghost)[type=submit]")) };
  await shot(p, "gate-0", g); await inp.click();
  let k = 0; for (const n of [3, 7, 11, 15]) { await p.keyboard.type(EMAIL.slice(k, n)); k = n; await shot(p, "gate-" + n, g); }
  await Promise.all([p.waitForNavigation().catch(() => {}), p.click(".pe-card button.pe-b:not(.ghost)[type=submit]")]); await p.waitForTimeout(1200);
  await scrollTo(p, 0);
  const newHere = await boxJS(p, "const h=[...document.querySelectorAll('h1,h2,h3,h4,b,strong,div')].find(x=>/^New here\\?/.test(x.textContent.trim())&&x.children.length<3);return h&&h.parentElement;");
  await shot(p, "term", { plan: await box(p.locator(".pill.plan")), market: await box(p.locator("text=/^MARKET (OPEN|CLOSED)/")), newhere: newHere,
    legend: await boxJS(p, "const h=[...document.querySelectorAll('li')].find(x=>/gets a label/.test(x.textContent));return h;"), q: await box(p.locator("#q")), view: await box(p.locator("#v-simple")) });

  // ---------- Episode 2: read the feed ----------
  // one story card in All, scrolled so the card sits near the top
  const card = p.locator(".sig").first(); const cy = await topOf(card); await scrollTo(p, cy - 110);
  const cardR = {
    card: await box(card), head: await box(card.locator("h3")),
    why: await boxJS(p, "const c=document.querySelector('.sig');const w=[...c.querySelectorAll('*')].find(x=>/^WHY IT MATTERS$/i.test(x.textContent.trim()));const k=[...c.querySelectorAll('*')].find(x=>/^WHAT TO CHECK$/i.test(x.textContent.trim()));if(!w||!k)return null;const a=w.getBoundingClientRect(),b=k.getBoundingClientRect();return {getBoundingClientRect:()=>({x:a.x,y:a.y,width:c.getBoundingClientRect().width-32,height:b.y-a.y-4})};"),
    check: await boxJS(p, "const c=document.querySelector('.sig');const k=[...c.querySelectorAll('*')].find(x=>/^WHAT TO CHECK$/i.test(x.textContent.trim()));const m=[...c.querySelectorAll('*')].find(x=>/^Importance/.test(x.textContent.trim())&&x.children.length===0);if(!k||!m)return null;const a=k.getBoundingClientRect(),b=m.getBoundingClientRect();return {getBoundingClientRect:()=>({x:a.x,y:a.y,width:c.getBoundingClientRect().width-32,height:b.y-a.y-6})};"),
    chips: await boxJS(p, "const c=document.querySelector('.sig');const m=[...c.querySelectorAll('*')].filter(x=>/^(Importance|Reads as|Could go|Matters)/.test(x.textContent.trim())&&x.children.length===0);if(!m.length)return null;const rs=m.map(x=>x.getBoundingClientRect());const x0=Math.min(...rs.map(r=>r.x)),y0=Math.min(...rs.map(r=>r.y)),x1=Math.max(...rs.map(r=>r.right)),y1=Math.max(...rs.map(r=>r.bottom));return {getBoundingClientRect:()=>({x:x0,y:y0,width:x1-x0,height:y1-y0})};"),
    label: await boxJS(p, "const c=document.querySelector('.sig');return [...c.querySelectorAll('*')].find(x=>/^(ACT|WATCH|IGNORE)\\b/.test(x.textContent.trim())&&x.children.length<=2&&x.getBoundingClientRect().height<40);"),
    text: (await card.locator("h3").first().textContent()).trim() };
  await shot(p, "card", cardR);
  // the tab bar
  const tabs = p.locator("[role=tablist]").first(); await scrollTo(p, (await topOf(tabs)) - 300);
  const tr = { bar: await box(tabs) }; for (const t of ["ideas", "watch", "global", "filings", "money", "mine"]) tr[t] = await box(p.locator(`.tab[data-t="${t}"]`));
  await shot(p, "tabs", tr);
  await p.locator('.tab[data-t="money"]').first().click(); await p.waitForTimeout(600);
  await scrollTo(p, (await topOf(tabs)) - 300);
  await shot(p, "money", { tab: await box(p.locator('.tab[data-t="money"]')), card: await box(p.locator(".sig")), text: (await p.locator(".sig h3").first().textContent().catch(() => "")).trim() });
  // the pre-market panel, open
  await p.locator('.tab[data-t="all"]').first().click(); await scrollTo(p, 0);
  const pmOpen = await p.evaluate(() => { const b = document.getElementById("pm-body"); return b && b.offsetHeight > 0; });
  if (!pmOpen) { await p.click("#pm-tog"); await p.waitForTimeout(500); }
  const pmTop = await p.evaluate(() => { const t = document.getElementById("pm-tog"); let e = t; while (e && e.parentElement && e.getBoundingClientRect().height < 120) e = e.parentElement; return e.getBoundingClientRect().top + scrollY; });
  await scrollTo(p, pmTop - 120);
  await shot(p, "pm", { panel: await boxJS(p, "const t=document.getElementById('pm-tog');let e=t;while(e&&e.parentElement&&!e.contains(document.getElementById('pm-body')))e=e.parentElement;return e;"), tog: await box(p.locator("#pm-tog")) });
  console.log("pm:", (await p.evaluate(() => { const t = document.getElementById("pm-tog"); let e = t; while (e && !e.contains(document.getElementById("pm-body"))) e = e.parentElement; return e.innerText; })).replace(/\n+/g, " | ").slice(0, 500));

  // ---------- Episode 3: make it yours ----------
  await p.goto(BASE + "terminal.html"); await p.waitForTimeout(800); await scrollTo(p, 0);
  const q = { box: await box(p.locator("#q")) }; await shot(p, "search-0", q); await p.click("#q");
  const WORD = "Meesho"; k = 0; for (const n of [2, 4, 6]) { await p.keyboard.type(WORD.slice(k, n)); k = n; await p.waitForTimeout(300); q.opt = await box(p.locator("#q-list li")); await shot(p, "search-" + n, Object.assign({}, q)); }
  console.log("suggestions:", await p.evaluate(() => [...document.querySelectorAll("#q-list li")].map((x) => x.textContent.trim()).slice(0, 5)));
  await p.keyboard.press("Enter"); await p.waitForTimeout(800);
  const briefTop = async () => scrollTo(p, (await topOf(p.locator(".brief"))) - 104);
  await briefTop();
  const add = p.locator("button", { hasText: /Add to My stocks/ }).first();
  await shot(p, "brief", { brief: await box(p.locator(".brief")), add: await box(add), say: await box(p.locator(".brief .say")) });
  console.log("brief:", (await p.locator(".brief").first().innerText()).replace(/\n+/g, " | ").slice(0, 500));
  await add.click(); await p.waitForTimeout(500); await briefTop();
  await shot(p, "brief-added", { add: await box(p.locator(".brief button")), label: (await p.locator(".brief button").first().textContent()).trim() });
  await p.locator("button", { hasText: /All news/ }).first().click().catch(() => {}); await p.waitForTimeout(400);
  const mine = p.locator('.tab[data-t="mine"]').first(); await mine.scrollIntoViewIfNeeded(); await mine.click(); await p.waitForTimeout(700);
  await scrollTo(p, (await topOf(p.locator("[role=tablist]"))) - 300);
  await shot(p, "mine", { tab: await box(mine), card: await box(p.locator(".sig")) });
  console.log("my stocks:", await p.locator(".sig").count(), "|", (await p.locator(".sig").first().innerText().catch(() => "")).replace(/\n+/g, " | ").slice(0, 200));
  await shot(p, "ask-fab", { fab: await box(p.locator(".askfab")) });
  await p.click(".askfab"); await p.waitForTimeout(800);
  const chip = p.locator(".chip", { hasText: "What happened today?" }).first();
  await shot(p, "chat-open", { chip: await box(chip) });
  await chip.click(); await p.waitForTimeout(1800);
  await p.evaluate(() => { const m = document.querySelector(".chm"), u = m && [...m.querySelectorAll(".msg.u")].pop(); if (u) m.scrollTop += u.getBoundingClientRect().top - m.getBoundingClientRect().top - 12; }); await p.waitForTimeout(300);
  await shot(p, "chat-answer", { user: await box(p.locator(".msg.u").last()), bot: await box(p.locator(".msg.b").last()) });
  console.log("answer:", (await p.locator(".msg.b").last().innerText().catch(() => "")).replace(/\n+/g, " | ").slice(0, 400));
  fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 1));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
