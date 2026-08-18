from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from diamond.config import HTTP_WORKERS

BASE = "https://statsapi.mlb.com/api/v1"
UA = "diamond-research-desk/0.1 (personal research; +https://github.com)"


def get_json(url: str, retries: int = 4, timeout: int = 60) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(8.0, 0.6 * (2**attempt)))
    raise RuntimeError(f"GET failed {url}: {last}")


def get_many(urls: list[str], workers: int | None = None) -> list[tuple[str, dict | None, str | None]]:
    out: list[tuple[str, dict | None, str | None]] = []
    if not urls:
        return out

    def one(url: str):
        try:
            return url, get_json(url), None
        except Exception as exc:
            return url, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers or HTTP_WORKERS) as pool:
        futures = [pool.submit(one, url) for url in urls]
        for fut in as_completed(futures):
            out.append(fut.result())
    return out


def teams_url(season: int) -> str:
    return f"{BASE}/teams?sportId=1&season={season}"


def schedule_url(start: str, end: str) -> str:
    return (
        f"{BASE}/schedule?sportId=1&startDate={start}&endDate={end}"
        "&hydrate=venue,weather,probablePitcher,linescore,team"
    )


def venue_url(venue_id: int) -> str:
    return f"{BASE}/venues/{venue_id}?hydrate=location,fieldInfo,timezone"


def season_stats_url(group: str, season: int) -> str:
    return (
        f"{BASE}/stats?stats=season&group={group}&season={season}"
        "&sportIds=1&gameType=R&playerPool=all&limit=2000"
    )


def player_log_url(player_id: int, group: str, season: int) -> str:
    return f"{BASE}/people/{player_id}/stats?stats=gameLog&group={group}&season={season}"


def team_log_url(team_id: int, group: str, season: int) -> str:
    return f"{BASE}/teams/{team_id}/stats?stats=gameLog&group={group}&season={season}&gameType=R"


def transactions_url(start: str, end: str) -> str:
    return f"{BASE}/transactions?sportId=1&startDate={start}&endDate={end}"
