const pw = require("playwright"), path = require("path"), { spawn } = require("child_process");
const [dir, out, dur] = process.argv.slice(2); const FPS = 30;
(async () => { const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.goto("file://" + path.join(dir, process.env.INTRO || "intro.html")); await p.evaluate(() => document.fonts.ready);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-", "-i", path.join(dir, "audio", "intro.wav"),
    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", String(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-t", dur, out], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res) => ff.on("close", res));
  for (let i = 0; i < Math.round(+dur * FPS); i++) { await p.evaluate((t) => render(t), i / FPS); const buf = await p.screenshot({ type: "jpeg", quality: 92 }); if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r)); }
  ff.stdin.end(); await done; await b.close(); console.log("ok"); })();
