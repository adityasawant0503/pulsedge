const pw = require("playwright"), path = require("path"), fs = require("fs"), { spawn } = require("child_process");
const [dir, wav, out, dur] = process.argv.slice(2); const FPS = 30;
(async () => { const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  p.on("pageerror", (e) => console.error("pageerror:", e.message));
  await p.goto("file://" + path.join(dir, "reel.html")); await p.evaluate(() => document.fonts.ready);
  await p.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  const meta = JSON.parse(fs.readFileSync(path.join(dir, "cap", "meta.json"))); meta.timing = JSON.parse(fs.readFileSync(path.join(dir, "timing.json"))); console.log(await p.evaluate((m) => init(m), meta));
  if (process.env.STILLS) { for (const t of process.env.STILLS.split(",").map(Number)) { await p.evaluate((x) => render(x), t); await p.screenshot({ path: path.join(dir, "out", `st-${t}.png`) }); } await b.close(); return; }
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-", "-i", wav,
    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", String(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-t", dur, "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res) => ff.on("close", res));
  for (let i = 0; i < Math.round(+dur * FPS); i++) { await p.evaluate((t) => render(t), i / FPS); const buf = await p.screenshot({ type: "jpeg", quality: 92 }); if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r)); }
  ff.stdin.end(); await done; await b.close(); console.log("ok"); })();
