// Render one guide episode: frames from guide.html piped to ffmpeg with the episode's mix.
//   node tools/render_howto.js <dir> <ep> <out.mp4>
const fs = require("fs"), path = require("path"), { spawn } = require("child_process"), pw = require("playwright");
const [dir, ep, out] = process.argv.slice(2); const FPS = 30;
(async () => {
  const T = JSON.parse(fs.readFileSync(path.join(dir, `timing-ep${ep}.json`), "utf8")), meta = JSON.parse(fs.readFileSync(path.join(dir, "cap", "meta.json"), "utf8"));
  const browser = await pw.chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => console.error("pageerror:", e.message));
  await page.goto("file://" + path.join(dir, "guide.html"));
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate((x) => init(x), { timing: T, meta });
  await page.waitForFunction(() => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0));
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-i", path.join(dir, "audio", `ep${ep}-mix.wav`), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
    "-r", String(FPS), "-c:a", "aac", "-b:a", "160k", "-t", String(T.end), "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error("ffmpeg exited " + c)))));
  const frames = Math.round(T.end * FPS);
  for (let i = 0; i < frames; i++) {
    await page.evaluate((t) => render(t), i / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  }
  ff.stdin.end(); await done; await browser.close();
  console.log(JSON.stringify({ out, frames, seconds: T.end }));
})().catch((e) => { console.error(e); process.exit(1); });
