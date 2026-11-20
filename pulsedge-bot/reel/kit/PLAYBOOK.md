# Content pipeline: PulsEdge Instagram + Aditya's LinkedIn

Two channels, two voices, one production system. Claude drafts and renders on a fixed rhythm. Aditya approves and posts. Nothing is posted automatically.

## The two channels

| | PulsEdge Instagram (@pulsedge.in) | Aditya Sawant, LinkedIn |
|---|---|---|
| Voice | The brand. Descriptive and plain-English. No personal names or views. | First person, analyst. A clear thesis and "My read". |
| Look | Dark, IBM Plex, red/green/amber tags, "PULSEDGE · EXPLAINED" mark | White research note: navy and sky blue, serif headlines, numbered exhibits, hairline rules |
| Reader | Retail investors who are fairly new to markets | Market professionals and serious investors |
| Goal | Reach (reels), saves (carousels), sign-ups (bio link to the terminal) | Authority, saves, profile views, conversations |
| Rule | | Don't mention PulsEdge on LinkedIn until Aditya decides to introduce it |

## Weekly rhythm

**Instagram: 2–3 feed posts a week**
- Mon or Tue: carousel, "PulsEdge Explained". The week's market story, or the week ahead.
- Wed or Thu: reel. A data reel (money moves, a big index move, then vs now) or a product use-case reel.
- Weekend: share the week's posts to Stories and file them in highlights. "Explained" holds market posts; "How to" holds product videos.

**LinkedIn: 1 post a week, alternating**
- Week A: a "Decoded" research note. A 5-slide PDF carousel with a thesis, 3–5 exhibits, signposts and "My read".
- Week B: a text post with one exhibit, e.g. "The number that matters this week" or "Then vs now".
- Event weeks (RBI, Fed, Budget, big results): a short note after the event, in place of that week's post.

## Pillars

| Instagram | LinkedIn |
|---|---|
| 1. Market Explained: the week's story in 6–8 slides | 1. Decoded: a thesis-led research note |
| 2. Money moves: FII/DII flows, block and bulk deals, index moves (data reels) | 2. The number that matters: one chart, one take |
| 3. Learn the market: what a bulk deal, the repo rate or VIX is (carousels) | 3. Then vs now: historical context for today's move |
| 4. Use PulsEdge: routines and features (reels, the "How to" highlight) | 4. Event notes: before and after RBI, Fed, Budget |

## Production runs (Claude, scheduled)

**Sunday, about 5:45 PM IST: plan and draft the week**
1. Read this playbook, the calendar below, and any changes Aditya asked for.
2. Gather the facts:
   - PulsEdge data on origin/master: `pulsedge/data/feed.json`, `flows.json`, `premarket.json`, `prices.json`.
   - Official and press sources: NSE, NSDL, RBI, MoSPI, IMD, NOAA, US Treasury.
   - Check every figure against a second source. Leave out any number the sources disagree on.
3. Draft and render:
   - The Instagram carousel (`carousel/`) and its caption.
   - The week's reel script. Voice and render it if vidIQ credits allow (`data-reel/` or `howto/`).
   - The LinkedIn post: text plus one exhibit, or a Decoded PDF (`linkedin/`) in a Decoded week.
4. Run the checklist below. Send every draft with captions and a "post on" day for each.

**Wednesday, about 5:45 PM IST: midweek**
- The reel on the week's biggest story, or a product use-case reel.
- Refresh any draft whose numbers have moved.
- Draft the LinkedIn post if Sunday didn't.

**Event days:** once an RBI, Fed or Budget date is confirmed, the Sunday run schedules a one-off reaction draft for that evening.

## Checklist before anything is sent

- [ ] Educational only. No buy, sell or "apply" calls, price targets, return scenarios, grey-market premium or allocation sizing. SEBI restricts unregistered individuals from giving recommendations.
- [ ] No forecasts. Use signposts ("what would change the picture") instead.
- [ ] No company logos.
- [ ] Every slide or frame carries the footer disclaimer. Carousels also carry the full disclaimer on the last slide.
- [ ] Every data slide or scene names its source and the date of its figures.
- [ ] Text sizes: at least 20px on carousels and 26px in reels. Reels have burned-in captions.
- [ ] PulsEdge content has no personal name. LinkedIn content has no PulsEdge mention.
- [ ] Frames are pulled from the rendered file and looked at; the layout report is clean.

## Budgets

- **vidIQ voice:**
  - 150 credits a month, renewing on the 26th.
  - Each call costs 28 credits per 1,000 characters, rounded up. That allows about 4 voiced reels a month.
  - Several short scripts can go in one `scriptLines` call.
  - Keep 28 credits in reserve for an event reel.
- **Aditya's time:** about 15 minutes a week to approve and post. Drafts arrive with captions ready to paste.

## Formats and templates (this kit)

| Format | Template | Size |
|---|---|---|
| Instagram carousel | `carousel/pulsedge-carousel.html` | 1080×1350, PNGs |
| Instagram data reel | `data-reel/reel.html` + `cover.html` | 1080×1920, about 30 s, voiced |
| Instagram how-to and use-case reel | `howto/guide.html` + `covers.html` | 1080×1920, 15–30 s, voiced |
| LinkedIn Decoded note | `linkedin/decoded-note.html` | 1080×1350, PDF |
| Highlight covers | flat colour + line icon, "Light" set | 1080×1080 |

## Calendar

Event anchors to date: RBI policy (early Dec) · NOAA El Niño update (10 Dec) · November CPI (mid-Dec) · US Fed (mid-Dec) · Union Budget (1 Feb) · IMD summer outlook (late Feb). Confirm exact dates before scheduling.

| Week | Instagram (PulsEdge) | LinkedIn (Aditya) |
|---|---|---|
| 23–29 Nov | Thu 26: "Your 2-minute market routine" reel (already scheduled) · weekend carousel: "What is a bulk deal?" (the Big money tab, explained) | "The number that matters: 27%". Two weeks of foreign buying reversed about a quarter of ten months of selling. One exhibit. |
| 30 Nov – 6 Dec (RBI) | Before: "RBI week: what to watch" carousel · after: "The repo rate in 30 seconds" reel | Decoded No. 4, after the decision: the RBI and a food-led inflation problem |
| 7–13 Dec (NOAA, CPI) | "El Niño update" carousel · "November inflation in 30 seconds" reel | Text + exhibit: food vs headline inflation since September |
| 14–20 Dec (Fed) | "What the Fed decision means for India" reel · glossary carousel: FII, DII, repo, VIX | Decoded No. 5: "2026 in five exhibits" (year-end) |

## What to measure (every Sunday)

- **Instagram:**
  - Reels: reach from non-followers.
  - Carousels: saves and shares.
  - Profile visits → link taps → sign-ups tagged `via=instagram`. This tagging needs the sign-up source change (PR #12) merged.
- **LinkedIn:** impressions, saves, profile views and new followers, and who comments.
- Aditya sends the week's Insights screenshots on Sunday, and that run shifts topics toward what worked.
