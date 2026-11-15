#!/usr/bin/env node
// Render the PulsEdge intro video (1920x1080 MP4, about 54 s, silent with on-screen captions) and its poster.
//
//   PULSEDGE_PASS=<an access pass> node pulsedge-bot/intro/render.js [--out pulsedge/assets/intro.mp4] [--fps 30] [--crf 25]
//
// It serves the site from pulsedge/, opens the real terminal with the pass, captures the screens the tour shows
// (search, stock brief, My stocks, chat, Simple and Pro views), then plays intro.html frame by frame into ffmpeg,
// the same way as the daily reel. The pass is only read from the environment; never commit one.
// Options: --stock RELIANCE --type Reliance picks the company the tour searches for.
const fs = require("fs");
const path = require("path");
const http = require("http");
const { spawn } = require("child_process");
let pw;
try { pw = require("playwright"); } catch (e) { pw = require("playwright-core"); }

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith("--") ? a.concat([[v.slice(2), all[i + 1]]]) : a), []));
const HERE = __dirname;
const SITE = path.join(HERE, "..", "..", "pulsedge");
const OUT = path.resolve(args.out || path.join(SITE, "assets", "intro.mp4"));
const FPS = +(args.fps || 30);
const CRF = String(args.crf || 25);
const STOCK = args.stock || "RELIANCE";
const TYPE = args.type || "Reliance";
const SHOTS = path.join(HERE, "out", "screens");
const PASS = process.env.PULSEDGE_PASS || "";

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".mp4": "video/mp4" };
function serve(root) {
  return new Promise((res) => {
    const srv = http.createServer((req, rsp) => {
      const p = path.join(root, decodeURIComponent(req.url.split(/[?#]/)[0]).replace(/\/$/, "/index.html"));
      if (!p.startsWith(root)) { rsp.writeHead(403); return rsp.end(); }
      fs.readFile(p, (err, buf) => {
        if (err) { rsp.writeHead(404); return rsp.end(); }
        rsp.writeHead(200, { "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" });
        rsp.end(buf);
      });
    }).listen(0, "127.0.0.1", () => res(srv));
  });
}

async function capture(browser, base) {
  if (!PASS) throw new Error("set PULSEDGE_PASS to an access pass so the real terminal can be captured");
  fs.mkdirSync(SHOTS, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" });
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  await p.goto(base + "/terminal.html#pass=" + PASS);
  await p.waitForTimeout(1500);
  await p.evaluate(() => { localStorage.setItem("pe_intro", "1"); localStorage.setItem("pe_view", "simple"); localStorage.removeItem("pe_hold"); localStorage.setItem("th", "dark"); });
  await p.goto(base + "/terminal.html");
  await p.waitForTimeout(2500);
  const box = async (sel, last) => {
    const l = p.locator(sel);
    if (!(await l.count())) return null;
    const r = await (last ? l.last() : l.first()).boundingBox();
    return r && { x: r.x, y: r.y, w: r.width, h: r.height };
  };
  const meta = {};
  const shot = async (name, extra) => { await p.waitForTimeout(350); await p.screenshot({ path: path.join(SHOTS, name + ".png") }); meta[name] = extra || {}; };

  await shot("feed", { search: await box(".askbox"), view: await box(".view"), tabs: await box(".tabs") });
  await p.click("#q");
  for (let i = 0; i < TYPE.length; i++) { await p.keyboard.type(TYPE[i]); await p.waitForTimeout(140); await shot("typing" + (i + 1)); }
  meta.typing = { n: TYPE.length, list: await box("#q-list"), first: await box("#q-list li") };
  await p.evaluate((s) => { const li = [...document.querySelectorAll("#q-list li")]; const hit = li.find((l) => l.textContent.includes(s)) || li[0]; if (hit) { hit.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); hit.click(); } }, STOCK);
  await p.waitForTimeout(900);
  await p.evaluate(() => scrollTo(0, 0));
  const add = '#brief button:has-text("Add to My stocks")';
  await shot("brief", { brief: await box("#brief"), add: await box(add), ai: await box("#brief .ai") });
  await p.click(add);
  await shot("added", { add: await box('#brief button:has-text("In My stocks")') });
  await p.fill("#q", "");
  await p.evaluate(() => document.getElementById("q").dispatchEvent(new Event("input", { bubbles: true })));
  await p.waitForTimeout(500);
  await p.click('.tab[data-t="mine"]');
  await p.waitForTimeout(500);
  await p.evaluate(() => scrollTo(0, 0));
  await shot("mine", { tab: await box('.tab[data-t="mine"]'), first: await box("#feed li") });
  await p.click('.tab[data-t="all"]');
  await p.click("#chat-open");
  await p.waitForTimeout(500);
  const question = "What could go wrong with " + TYPE + "?";
  await p.fill("#chat-q", question);
  await p.press("#chat-q", "Enter");
  await p.waitForTimeout(800);
  await shot("chat", { chat: await box("#chat"), question: await box("#chat-m .msg.u", true), answer: await box("#chat-m .msg.b", true) });
  await p.click("#chat-x");
  await p.click("#v-pro");
  await p.waitForTimeout(600);
  await p.evaluate(() => scrollTo(0, 0));
  await shot("pro", {});
  await ctx.close();
  if (errs.length) throw new Error("terminal errors while capturing: " + errs.join("; "));
  meta.question = question;
  return meta;
}

function pickData() {
  const feed = JSON.parse(fs.readFileSync(path.join(SITE, "data", "feed.json"), "utf8"));
  const items = (feed.items || []).filter((x) => x && x.headline);
  const advice = /\b(buy|sell|target|multibagger|should you|upside potential|check price)\b/i;
  // real headlines, lightly tidied: "X Limited: X Limited has informed the Exchange regarding Y" -> "X Limited: Y"
  const text = (x) => {
    let h = String(x.headline).replace(/\s+\|.*$/, "").replace(/-XBRL\b/g, "").trim();
    h = h.replace(/^(.+?):\s*\1\s+has (?:informed|submitted to) the Exchange,?(?: regarding| that| about| the)?\s*/i, "$1: ");
    return h.charAt(0).toUpperCase() + h.slice(1);
  };
  const clean = items.filter((x) => !advice.test(text(x)) && text(x).length <= 92 && text(x).length >= 30);
  const kind = (x) => (x.call === "buy" || x.call === "sell" ? "act" : x.call === "watch" ? "watch" : "ignore");
  const take = (k, n) => clean.filter((x) => kind(x) === k).slice(0, n).map((x) => ({ text: text(x), call: k }));
  // the sorting scene: 2 act, 4 watch, 6 ignore, interleaved the way news arrives
  const a = take("act", 2), w = take("watch", 4), g = take("ignore", 6);
  const order = ["ignore", "watch", "ignore", "act", "ignore", "watch", "ignore", "watch", "ignore", "act", "ignore", "watch"];
  const pools = { act: a, watch: w, ignore: g };
  const sort = order.map((k) => pools[k].shift()).filter(Boolean);
  const seen = new Set(), stream = clean.map(text).filter((h) => { const k = h.slice(0, 18); if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 40);
  const ex = items.filter((x) => x.plain && x.why && x.check && x.call === "watch" && x.tickers && x.tickers.length && !advice.test(x.plain + x.why + x.check))
    .sort((p, q) => (q.impact || 0) - (p.impact || 0))[0];
  const example = ex && {
    text: ex.plain, why: ex.why, check: ex.check, sym: ex.tickers[0].symbol, source: ex.source || "",
    date: new Date(ex.time).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }),
  };
  return { stream, sort, example };
}

async function main() {
  const srv = await serve(SITE);
  const base = "http://127.0.0.1:" + srv.address().port;
  const chrome = process.env.CHROME_PATH;
  const browser = await pw.chromium.launch(chrome ? { executablePath: chrome, headless: false, args: ["--headless=new"] } : {});
  const meta = args["no-capture"] ? JSON.parse(fs.readFileSync(path.join(SHOTS, "meta.json"), "utf8")) : await capture(browser, base);
  fs.writeFileSync(path.join(SHOTS, "meta.json"), JSON.stringify(meta, null, 1));

  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.join(HERE, "intro.html"));
  const data = Object.assign(pickData(), { meta, shots: "out/screens/", logo: "../../pulsedge/assets/logo-dark.png" });
  await page.evaluate((d) => init(d), data);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  const duration = await page.evaluate(() => INTRO.duration);

  if (args.frame) { // preview single frames: --frame 12.5,27 writes out/frame-<t>.jpg
    for (const t of String(args.frame).split(",")) { await page.evaluate((v) => render(v), +t); await page.screenshot({ path: path.join(HERE, "out", "frame-" + t + ".jpg"), type: "jpeg", quality: 90 }); }
    await browser.close(); srv.close(); return;
  }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-pix_fmt", "yuv420p", "-r", String(FPS), "-movflags", "+faststart", OUT], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error("ffmpeg exited " + c)))));
  const frames = Math.round(duration * FPS);
  for (let i = 0; i < frames; i++) {
    await page.evaluate((t) => render(t), i / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 93 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (i % 150 === 0) process.stderr.write(`frame ${i}/${frames}\n`);
  }
  ff.stdin.end();
  await done;

  // poster: PulsEdge sorting headlines, with its caption on screen
  await page.evaluate(() => render(INTRO.poster));
  await page.screenshot({ path: OUT.replace(/\.mp4$/, "-poster.jpg"), type: "jpeg", quality: 86 });
  await browser.close();
  srv.close();
  console.log(JSON.stringify({ video: OUT, frames, seconds: duration }, null, 1));
}
main().catch((e) => { console.error(e.message); process.exit(1); });
