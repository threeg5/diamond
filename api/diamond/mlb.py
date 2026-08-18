from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

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


def get_many(
    urls: list[str], workers: int | None = None
) -> Iterator[tuple[str, dict | None, str | None]]:
    """Fetch URLs with a small in-flight window so payloads are not all held at once."""
    if not urls:
        return
    n = max(1, workers or HTTP_WORKERS)

    def one(url: str):
        try:
            return url, get_json(url), None
        except Exception as exc:
            return url, None, str(exc)

    pending: set = set()
    it = iter(urls)
    with ThreadPoolExecutor(max_workers=n) as pool:
        def fill() -> None:
            while len(pending) < n * 2:
                try:
                    url = next(it)
                except StopIteration:
                    return
                pending.add(pool.submit(one, url))

        fill()
        while pending:
            done, not_done = wait(pending, return_when=FIRST_COMPLETED)
            pending = set(not_done)
            for fut in done:
                yield fut.result()
            fill()


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


def people_url(person_ids: list[str] | list[int]) -> str:
    joined = ",".join(str(pid) for pid in person_ids)
    return f"{BASE}/people?personIds={joined}"


def player_log_url(player_id: int, group: str, season: int) -> str:
    return f"{BASE}/people/{player_id}/stats?stats=gameLog&group={group}&season={season}"


def team_log_url(team_id: int, group: str, season: int) -> str:
    return f"{BASE}/teams/{team_id}/stats?stats=gameLog&group={group}&season={season}&gameType=R"


def transactions_url(start: str, end: str) -> str:
    return f"{BASE}/transactions?sportId=1&startDate={start}&endDate={end}"
