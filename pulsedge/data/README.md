# PulsEdge data

Three files drive the site. Each has a filled-in `*.sample.json` next to it,
which is used until the real file exists. Push a real file to `master` and the
site, the terminal and the Telegram bot switch to it within a couple of minutes.

| File             | Used by                                   | Sample                    |
|------------------|-------------------------------------------|---------------------------|
| `feed.json`      | Terminal signal feed, landing page feed, Telegram bot | `feed.sample.json` |
| `premarket.json` | Terminal pre-market panel                 | `premarket.sample.json`   |
| `universe.json`  | Stock list with names and sectors         | `universe.sample.json`    |
| `track.json`     | Track record page (`track.html`), written by `pulsedge-bot/track_record.py` | none: the page shows an empty state |
| `calendar.json`  | NSE trading holidays; trials count trading sessions with it | built into `assets/member.js` |
| `keys.json`      | Public keys allowed to sign access links (one per PulsEdge HQ device) | none |
| `revoked.json`   | Access-link ids that no longer work         | none |
| `prices.json`    | Plan prices, launch date and Founding 100 seats for `index.html` pricing and `pay.html`. Edit, then run `python pulsedge-bot/offers.py qr` and `check` | none |
| `offers.json`    | Discount codes, stored as SHA-256 hashes; manage with `pulsedge-bot/offers.py` | none |
| `monthly/`       | Monthly reports (`<YYYY-MM>.json`) and their list (`index.json`), written by `pulsedge-bot/monthly_report.py` and read by `report.html`. Drafts show only to the owner until published | none |
| `newscal/`       | The news calendar (`calendar.html`): each month's Act and Watch stories with the NSE closes for "on the day" and "since" (`<YYYY-MM>.json`), and the months plus every stock's latest close (`index.json`). Written by `pulsedge-bot/news_calendar.py` on every news run | none |
| `live.json`      | NSE's own live view for the day trader and the terminal's Nifty, Bank Nifty and VIX tiles: every figure with its source, `quality` (`realtime`, `delayed_10m`, `delayed_15m`, `final`, `stale`) and time, plus breadth, sector moves, previous-session levels and pivots, and the Nifty and Bank Nifty option chains (PCR, max pain, walls, straddle). Written by `pulsedge-bot/live_market.py` through `premarket.py`: every minute from 08:30 to 09:30 IST, every three minutes in the session, every ten outside it, by the fast lane | none |
| `events.json`    | Dates ahead for the news calendar: Nifty 500 results dates, board meetings and ex-dates from NSE; RBI, Fed, Budget and F&O expiry dates; and world and India economic dates (US CPI and jobs, ECB, Bank of Japan, Bank of England, China and India data) from TradingView's economic calendar. Written by `pulsedge-bot/events.py` from the news run (NSE at most every 3 hours); the RBI and Fed dates are set by hand in that script | none |
| `reviews.json`   | Real member reviews (from `review.html`, with permission). The landing page shows them, with the average, once there are 3 or more | none |

## `feed.json`: signals

```json
{ "updated": "2026-10-20T10:37:30+05:30", "items": [ { ... }, { ... } ] }
```

Each item is one news signal. Only `headline` and `time` are required.

| Field        | Example / values                                          |
|--------------|-----------------------------------------------------------|
| `id`         | `"powermech-2026-10-20-order"`, stable and unique. Stops the bot posting twice. |
| `time`       | `"2026-10-20T09:57:18+05:30"`                              |
| `headline`   | `"Power Mech Projects discloses new order win"`            |
| `source`     | `"NSE Announcements"`, `"RedBox India"`, `"FinancialJuice"` |
| `call`       | `buy`, `sell`, `watch` or `ignore`                         |
| `horizon`    | `intraday`, `swing` or `positional`                        |
| `direction`  | `up`, `down` or `mixed` (worked out from tickers if left out) |
| `latency`    | Seconds from news to analysis, `2.9`                       |
| `tickers`    | `[{"symbol": "BPCL", "direction": "down"}]`, or just `["TCS"]` |
| `sectors`    | `["OMCs", "Paints"]`                                       |
| `impact`     | 0–100                                                      |
| `confidence` | 0–100                                                      |
| `category`   | `"Order Win"`, `"Commodity"`, `"Government Policy"`        |
| `action`     | The 🎯 line: `"Buy only above the first 15-min high"`      |
| `reason`     | List of bullet points                                      |
| `risks`      | List of bullet points                                      |
| `original`   | The source text as published                               |
| `url`        | Link to the filing or article                              |
| `after`      | `{"symbol": "POWERMECH", "from": 2710.5, "m15": 1.2, "h1": 2.1, "close": 2.8, "status": "played out"}` |

Tabs in the terminal: **Trade ideas** = `buy`/`sell`, **Watch** = `watch`,
**RedBox** = source contains "RedBox", **Filings** = NSE/BSE announcements,
**My stocks** = tickers in the visitor's watchlist.

The Telegram bot posts every new `buy` or `sell` signal once.

Older items in the `verdict` / `impacts` format still work: `act` becomes
`buy` (or `sell` when the direction is down).

## `premarket.json`: pre-market panel

See `premarket.sample.json` for every field. In short:

- `updated`, `sentiment` ("Mildly bearish"), `breadth` (`{"up": 2, "down": 3}`), `writer` (`premarket` for the 15-minute run,
  `live` for the fast lane's refreshes), `data_as_of`, `market` (NSE's open/closed status)
- `checklist`: items with `title`, `dir` (`up`/`down`/`flat`), `value`, `detail` (lines), and for each item `quality`
  (`realtime`, `delayed_10m`, `delayed_15m`, `final`, `scheduled`), `src` and `as_of`. The last `detail` line repeats them in words
  ("NSE · live · as of 13:48 IST"). Nifty, Bank Nifty and India VIX come from NSE itself, so they are live to the minute
  (not TradingView's 15-minute-late copy); GIFT Nifty, Asia, USD/INR, DXY and gold are real time; US futures and Brent
  are 10 minutes late. The key levels, options, breadth and calendar items are context for the day trader and are not part
  of the sentiment score or the up/down count
- `checklist` items also carry `label` (short name for the card), `group` (`india`, `global`, `trade`, `today`: how the
  terminal files them: India open, Global cues, Levels and positioning, Today) and `sub` (the one line worth reading at a
  glance; the full lines stay in `detail`). The terminal shows the label, value, freshness and `sub`; tapping the value
  opens `detail`. `title` is unchanged, for other readers (the Telegram brief and the reel match on it)
- `data`: the same numbers as fields, so a program need not read the text: `instruments` (`v`, `chg_pct`, `prev`, `open`,
  `high`, `low`, `quality`, `src`, `as_of`), `levels` (previous session OHLC, pivots, CPR) and `options` (PCR, max pain,
  call and put walls, straddle, implied move, ATM IV), for Nifty and Bank Nifty
- `summary`, `global_cues`, `india_triggers` (bullets)
- `focus` (`[{symbol, note}]`), `sector_tags` (`[{label, tone: positive|negative|watch}]`)
- `key_risk`, `also` (`[{name, value, change}]`, change in %)

Visitors' checklist ticks are saved per day in their own browser.

## `universe.json`: stock list

Download `ind_nifty500list.csv` from niftyindices.com and run:

```
python pulsedge-bot/universe_from_nse.py ind_nifty500list.csv
```

## Sending data by hand

A spreadsheet works. Use the field names above as column headers, put
multiple tickers in one cell like `ONGC OIL -BPCL -HINDPETRO` (a leading `-`
means negative), and send it as CSV.

## Trials and access links

The terminal (`terminal.html`) opens for people with a free trial or an access link; everyone else sees
the sample data and a sign-up card. The logic is in `assets/member.js`.

- **Free trial:** a visitor enters their email and gets 5 NSE trading sessions (about a week) in that
  browser. The email goes to Formspree with `source: "trial"`.
- **Access links:** `terminal.html#pass=…`, made in PulsEdge HQ (or `pulsedge-bot/issue_pass.js`) and
  signed with a private key that never leaves the device that made it. Plans: `trial7` and `trial14`
  (5 or 10 trading sessions from a start date), `monthly`, `yearly`, `founding` and `comp` (valid until
  a date). A link only opens if its key's public half is in `keys.json` and its id isn't in `revoked.json`.
- Weekends and the holidays in `calendar.json` don't count. A trial ends when trading opens on the day
  after its last session. Update `calendar.json` every December from NSE's holiday circular.
- This is a front-end gate for the beta: the data files themselves are public. Real logins come later.
