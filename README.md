# PulsEdge

AI triage of Indian market news: every headline marked Ignore, Watch or Act, with the reason and the source, filtered to the stocks you own, before 9:15.

- **Site:** https://adityasawant0503.github.io/pulsedge/ (landing page, PULSE terminal, track record)
- **`pulsedge/`**: the static site published to GitHub Pages, with its data files in `pulsedge/data/`
- **`pulsedge-bot/`**: the data pipeline
  - `news_pipeline.py`: collects and classifies news (Indian and global sources)
  - `flows.py`: bulk and block deals, FII positioning, sector index moves
  - `premarket.py`: the pre-market panel
  - `track_record.py`: scores calls against NSE closing prices
  - `reel/`: the daily reel renderer
  - `pulse_bot.py`: Telegram posts
- **`.github/workflows/pulsedge-news.yml`**: runs the pipeline every 15 minutes in market hours and after the close, commits the data, deploys the site, posts to Telegram and publishes the daily reel

## Secrets (Settings → Secrets and variables → Actions)

| Name | What it does |
| --- | --- |
| `AI_API_KEY` | Google Gemini key for AI verdicts (keyword rules are used without it) |
| `TELEGRAM_BOT_TOKEN` | Bot token for posting to the Telegram channel |

Educational information only. Not investment advice.
