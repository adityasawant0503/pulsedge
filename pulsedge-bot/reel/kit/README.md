# PulsEdge social kit

The plan both channels follow is in `PLAYBOOK.md`. Below are the templates and tools for PulsEdge's Instagram posts (and Aditya's LinkedIn notes): voiced reels, how-to walkthroughs made from real screens of the site, and carousels.
Everything renders from HTML with Playwright and ffmpeg, so a post can be rebuilt with new numbers in minutes.

| Folder | Makes | Example |
|---|---|---|
| `data-reel/` | a 25–35 s voiced reel built from numbers, with burned-in captions and a cover | "But this isn't 2021" |
| `howto/` | short walkthroughs from real screenshots of the terminal: highlight rings, taps, captions; plus feed and highlight covers | "How to use PulsEdge", parts 1–3 |
| `carousel/` | a 1080×1350 carousel: a PDF for LinkedIn and PNGs for Instagram | "Best week since 2021" |
| `linkedin/` | Aditya's LinkedIn research note: a white 5-slide "Decoded" PDF with exhibits and signposts | "Same rally, different world" |
| `tools/` | capture, voice timing, music and effects, rendering, review stills | |

Fonts come from `../fonts` (IBM Plex), linked into each template folder.

## You need

- Node with Playwright (`require("playwright")`). Claude Code cloud sessions already have it; elsewhere run `npm i playwright && npx playwright install chromium`.
- ffmpeg and ffprobe.
- Python 3 with numpy.

Work in a scratch copy of a template folder, e.g. `cp -r data-reel /tmp/work && ln -sfn "$PWD/../fonts" /tmp/work/fonts`. The `.gitignore` keeps captures, audio and renders out of git.

## Voice

- Voiceovers come from vidIQ (`vidiq_voiceover_generate`), voice `TX3LPaxmHKxFdv7VOQHJ`.
- Cost: 28 credits per 1,000 characters, rounded up per call. The plan has 150 credits a month. Voice several scripts in one call with `scriptLines` so they share one charge.
- Write for the ear: numbers as words ("eight point six percent"), and "Pulse Edge" so the name is said right. Captions show "PulsEdge" and numerals.
- Download the MP3 from `assets.vidiq.com` into `<work>/audio/`.

## A data reel

1. Write the script. Generate the voice, then download it to `audio/vo.mp3`.
2. List the pauses: `ffmpeg -i audio/vo.mp3 -af silencedetect=noise=-38dB:d=0.18 -f null - 2>&1 | grep silence_`.
3. In `tools/tighten_reel.py`, write one `CH` entry per spoken chunk between pauses (shown word, weight), and name the cues the visuals need.
4. Tighten the pauses and time the words: `python3 -I tools/tighten_reel.py audio/vo.mp3 audio/vo-tight.wav timing.json`.
5. Mix the beat and effects: `python3 -I tools/sound_reel.py timing.json audio/vo-tight.wav audio/mix.wav`.
6. Edit the scenes in `reel.html`. Each scene and pop is keyed to a cue.
7. Review stills with `node tools/stills_reel.js <work> 0 3.2 9.5`, then render: `node tools/render_reel.js <work> <work>/out/reel.mp4`. This also writes the cover from `cover.html`.
8. Check the file itself: `ffprobe`, loudness (`ffmpeg -i out.mp4 -af ebur128 -f null -`, aim near −14 LUFS), and a few frames pulled from the MP4.

## A how-to walkthrough

1. Export the live site and serve it locally:
   ```
   git archive origin/master pulsedge | tar -x -C <work>/site
   cd <work>/site/pulsedge
   python3 -m http.server 8766
   ```
2. Capture the screens at 3×, with the position of each thing to highlight: `node tools/capture_howto.js <work>/cap`. Sign-up forms and API calls are intercepted; nothing is sent.
3. Voice the parts in one `scriptLines` call. Save them as `audio/ep1.mp3` and so on.
4. For each part, edit `CH` and the cues in `tools/tighten_howto.py`. Then run `tighten_howto.py`, `sound_howto.py`, `stills_howto.js` and `render_howto.js`.
5. Join the parts for the feed: `ffmpeg -f concat -safe 0 -i list.txt -c copy full.mp4`.
6. Make the covers: `node tools/covers_howto.js <work>`.

## A carousel or LinkedIn note

Edit `carousel/pulsedge-carousel.html` (or `linkedin/decoded-note.html`), then render it: `node tools/render_carousel.js carousel/pulsedge-carousel.html`.
The report flags text running into the footer or across the margins, a footer pushed off the slide, and the smallest font size. Fix anything it lists, then look at every PNG.

## Rules for every post

- Educational only. No buy or sell calls, price targets, return scenarios, projections or allocation advice.
- Every slide and every reel frame carries "Educational information only · Not investment advice".
- Every data slide or scene names its source and the date of its figures. Check each number before posting.
- PulsEdge posts carry the brand only: no personal names or personal views.
- Text size: at least 20px on carousels, 26px in reels. Reels get burned-in captions for people watching muted.
- Sizes:
  - Carousels: 1080×1350 (4:5).
  - Reels: 1080×1920.
  - Reel covers: keep the key content in the middle 1080×1350, so the profile grid's crop keeps it.
- Brand colours: background `#09080e`, ink `#f6f5fb`, purple `#a58bff`, green `#2ee6a0` (up), red `#ff4d5e` (down), amber `#ffc24d` (caution).

## Posting

- Order: post the carousel first and the reel 2–3 days later, then pin a comment pointing to the carousel.
- Carousels: add a quiet instrumental track.
- Reels: keep the original audio and rename it "PulsEdge · Market Explained".
- Highlights: the how-to parts go under "How to"; the covers are in the how-to output.

## More episodes and reels

- `howto/guide.html` also plays episode 4, "Your 2-minute market routine": capture with `tools/capture_routine.js`, time it with `tighten_howto.py 4 …`, then use `sound_howto.py`, `stills_howto.js` and `render_howto.js` with `4`. Its cover is `howto/cover-routine.html` (`tools/cover_routine.js`).
- `data-reel/one-hand/` holds the "One hand buying, one hand hedging" data reel (FII cash flows vs futures positioning, 16–25 Nov 2026): copy its `reel.html` and `cover.html` into a scratch data-reel folder and its `tighten_reel.py` and `sound_reel.py` into that folder's `tools/`.
- Two-part reels: a data intro from `data-reel/` joined to a how-to episode. Example: `data-reel/record-month/` (record November FPI buying and the sector split) followed by `guide.html` episode 5 (the 2-minute routine; capture with `ASK_TAB=money` so Ask opens a block-deal card). Join the parts with ffmpeg's concat filter, then run loudnorm on the whole file.
