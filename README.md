# Diamond

MLB research desk: searchable player stats with the game’s environment attached — home/away, rest, park, weather, win/run-line streaks, and who is usually there but isn’t (IL).

## What this first cut does

Search a batter or pitcher, pick a stat and a line, then see how often they cleared it in comparable games. Each game row shows rest, park/weather, streaks, and missing regulars on both sidelines.

Today’s Games shows the slate with each team’s recent run environment and an expected score from those numbers. No spreads, totals, or moneylines.

## Run

**API** (from `api/`):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m diamond.ingest
uvicorn main:app --reload --port 8001
```

**Web** (from `web/`):

```
npm install
npm run dev
```

Then open http://127.0.0.1:5174

First ingest pulls 2022–2026 from the MLB Stats API. Takes several minutes.

## Online (Render + HostGator)

`render.yaml` creates **diamond-api** (Python + SQLite on a disk). Public site is HostGator at **https://theprofitengineer.com/thediamond** — not Fioatech.

After the API is up:

```
cd web
npm run build:hostgator
```

Upload `web/dist` into HostGator `public_html/thediamond/`. CORS on the API allows `https://theprofitengineer.com`.

This is decision support from historical data, not a prediction of future results.
