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

API on Render (Python + SQLite disk). Public site is a HostGator folder, not Fioatech DNS.

1. Push this repo to GitHub (private).
2. [render.com](https://render.com) → New → **Blueprint** → this repo.
3. First API boot starts ingest in the background if the disk is empty (several minutes).
4. Confirm the API hostname (usually `https://diamond-api.onrender.com`) and put it in `web/.env.hostgator` as `VITE_API_URL` if it differs.
5. From `web/`: `npm run build:hostgator`.
6. HostGator cPanel → File Manager → `public_html/thediamond/` → upload the contents of `web/dist` (including `.htaccess`).
7. Keep `CORS_ORIGINS` on **diamond-api** as `https://theprofitengineer.com,https://www.theprofitengineer.com`.

Public URL: `https://theprofitengineer.com/thediamond`. The site is public until auth is added. Render free API will sleep when idle.
