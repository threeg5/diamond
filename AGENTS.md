# Diamond — MLB situational research desk

Personal research tool for player-game stats plus the context box scores miss: home/away, rest, park/weather, win and run-line streaks, travel, and missing regulars (injured list). The Slate desk shows today’s games with each team’s numbers (no betting lines) and an expected score from those numbers.

Data comes from the [MLB Stats API](https://statsapi.mlb.com/) (schedule, game logs, venues, transactions). Not an official MLB product and not a betting “lock” engine.

## Structure

- `api/` — FastAPI + SQLite. Entry: `main.py`. Ingest: `python -m diamond.ingest`
- `web/` — Vite + React desk UI

## Run locally

```
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m diamond.ingest
uvicorn main:app --reload --port 8001

cd web
npm install
npm run dev
```

Open `http://127.0.0.1:5174`. API defaults to `http://127.0.0.1:8001`.

## Deploy (Render + HostGator)

Same pattern as Wagechecker and pay.fioatech.com: API + static web on Render, SQLite on a 1 GB disk, HostGator CNAME for the public hostname.

1. Push this repo to GitHub (private).
2. [render.com](https://render.com) → New → **Blueprint** → this repo.
3. First API boot starts ingest in the background if the disk is empty (several minutes). The site will show “database not loaded” until that finishes.
4. HostGator cPanel → Zone Editor → **CNAME**: `diamond` → `diamond-web.onrender.com` (or the hostname Render shows).
5. Render → **diamond-web** → Custom Domains → add `diamond.fioatech.com`.
6. Keep `CORS_ORIGINS` on **diamond-api** as `https://diamond.fioatech.com,https://diamond-web.onrender.com`.

Public URL: `https://diamond.fioatech.com`. The site is public until auth is added. Render free API will sleep when idle.
