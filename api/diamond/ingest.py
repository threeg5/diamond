from __future__ import annotations

import gc
import math
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timezone

import pandas as pd

from diamond.config import (
    REGULAR_IP,
    REGULAR_LOOKBACK_GAMES,
    REGULAR_PA,
    SEASONS,
)
from diamond.db import connect, reset_schema
from diamond.mlb import (
    get_json,
    get_many,
    player_log_url,
    schedule_url,
    season_stats_url,
    team_log_url,
    teams_url,
    transactions_url,
    venue_url,
)
from diamond.venues import (
    TEAM_HOMES,
    classify_roof,
    hop_travel,
    hour_et,
    is_altitude_game,
    is_early_window,
    is_night_game,
    is_overseas_venue,
    parse_temp,
    parse_wind,
    surface_group,
    team_travel_from_origin,
)

KEEP_TYPES = {"R": "REG", "F": "POST", "D": "POST", "L": "POST", "W": "POST"}


def _num(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    num = _num(value)
    if num is None:
        return None
    return int(num)


def _str(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _cell(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def innings_to_outs(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            whole, frac = text.split(".", 1)
            return int(whole) * 3 + int(frac)
        return int(float(text) * 3)
    except (TypeError, ValueError):
        return None


def month_windows(year: int) -> list[tuple[str, str]]:
    windows = []
    for month in range(2, 12):
        last = monthrange(year, month)[1]
        windows.append((f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"))
    return windows


def next_streak(current: int, won: bool | None) -> int:
    if won is None:
        return current
    if won:
        return current + 1 if current >= 0 else 1
    return current - 1 if current <= 0 else -1


def load_teams(years: list[int]) -> dict[int, dict]:
    teams: dict[int, dict] = {}
    for year in years:
        payload = get_json(teams_url(year))
        for row in payload.get("teams") or []:
            team_id = row.get("id")
            abbr = row.get("abbreviation")
            if not team_id or not abbr:
                continue
            teams[int(team_id)] = {
                "team_id": int(team_id),
                "abbr": abbr,
                "name": row.get("name"),
                "league_id": (row.get("league") or {}).get("id"),
                "division_id": (row.get("division") or {}).get("id"),
                "venue_id": (row.get("venue") or {}).get("id"),
            }
    return teams


def load_venues(venue_ids: set[int]) -> dict[int, dict]:
    urls = [venue_url(vid) for vid in sorted(venue_ids) if vid]
    found: dict[int, dict] = {}
    print(f"  venues: {len(urls)}")
    for url, payload, err in get_many(urls):
        if err or not payload:
            print(f"  skip venue {url}: {err}")
            continue
        for row in payload.get("venues") or []:
            loc = row.get("location") or {}
            coords = loc.get("defaultCoordinates") or {}
            tz = row.get("timeZone") or {}
            field = row.get("fieldInfo") or {}
            found[int(row["id"])] = {
                "name": row.get("name"),
                "lat": coords.get("latitude"),
                "lon": coords.get("longitude"),
                "tz": tz.get("offset"),
                "elevation": loc.get("elevation"),
                "country": loc.get("country"),
                "roof": classify_roof(field.get("roofType")),
                "surface": field.get("turfType"),
                "surface_group": surface_group(field.get("turfType")),
            }
    return found


def load_schedule(years: list[int]) -> list[dict]:
    urls = []
    for year in years:
        urls.extend(schedule_url(start, end) for start, end in month_windows(year))
    print(f"  schedule windows: {len(urls)}")
    games = []
    seen = set()
    for url, payload, err in get_many(urls, workers=6):
        if err or not payload:
            print(f"  skip schedule {url}: {err}")
            continue
        for day in payload.get("dates") or []:
            for game in day.get("games") or []:
                kind = KEEP_TYPES.get(game.get("gameType"))
                if not kind:
                    continue
                game_id = str(game.get("gamePk"))
                if not game.get("gamePk") or game_id in seen:
                    continue
                seen.add(game_id)
                games.append(game)
    print(f"  unique games: {len(games)}")
    return games


def prepare_games(raw: list[dict], teams: dict[int, dict], venues: dict[int, dict]) -> pd.DataFrame:
    id_to_abbr = {tid: t["abbr"] for tid, t in teams.items()}
    rows = []
    for game in raw:
        home = (game.get("teams") or {}).get("home") or {}
        away = (game.get("teams") or {}).get("away") or {}
        home_team = home.get("team") or {}
        away_team = away.get("team") or {}
        home_abbr = home_team.get("abbreviation") or id_to_abbr.get(home_team.get("id"))
        away_abbr = away_team.get("abbreviation") or id_to_abbr.get(away_team.get("id"))
        if not home_abbr or not away_abbr:
            continue
        venue = game.get("venue") or {}
        weather = game.get("weather") or {}
        linescore = game.get("linescore") or {}
        ls_teams = linescore.get("teams") or {}
        home_score = _int(home.get("score"))
        away_score = _int(away.get("score"))
        if home_score is None:
            home_score = _int((ls_teams.get("home") or {}).get("runs"))
        if away_score is None:
            away_score = _int((ls_teams.get("away") or {}).get("runs"))
        status = (game.get("status") or {}).get("abstractGameState")
        if status != "Final":
            home_score = None
            away_score = None
        gameday = game.get("officialDate") or str(game.get("gameDate") or "")[:10]
        venue_id = venue.get("id")
        meta = venues.get(int(venue_id), {}) if venue_id else {}
        home_div = teams.get(home_team.get("id"), {}).get("division_id")
        away_div = teams.get(away_team.get("id"), {}).get("division_id")
        result = None
        total = None
        if home_score is not None and away_score is not None:
            result = home_score - away_score
            total = home_score + away_score
        weekday = None
        if gameday:
            try:
                weekday = datetime.strptime(gameday[:10], "%Y-%m-%d").strftime("%A")
            except ValueError:
                weekday = None
        hour = hour_et(game.get("gameDate"))
        gametime = None if hour is None else f"{hour:02d}:00"
        reverse = bool(game.get("reverseHomeAwayStatus"))
        rows.append(
            {
                "game_id": str(game.get("gamePk")),
                "season": _int(game.get("season")),
                "gameday": gameday[:10] if gameday else None,
                "weekday": weekday,
                "gametime": gametime,
                "game_date": game.get("gameDate"),
                "season_type": KEEP_TYPES.get(game.get("gameType"), "REG"),
                "home_team": home_abbr,
                "away_team": away_abbr,
                "home_score": home_score,
                "away_score": away_score,
                "result": result,
                "total": total,
                "stadium": venue.get("name") or meta.get("name"),
                "stadium_id": str(venue_id) if venue_id else None,
                "venue_id": int(venue_id) if venue_id else None,
                "roof": meta.get("roof"),
                "surface": meta.get("surface"),
                "surface_group": meta.get("surface_group"),
                "temp": parse_temp(weather.get("temp")),
                "wind": parse_wind(weather.get("wind")),
                "condition": _str(weather.get("condition")),
                "day_night": _str(game.get("dayNight")),
                "location": "Neutral" if reverse else "Home",
                "div_game": int(bool(home_div and home_div == away_div)),
                "is_night": is_night_game(game.get("dayNight")),
                "is_early_window": is_early_window(game.get("dayNight"), game.get("gameDate")),
                "home_sp_id": str((home.get("probablePitcher") or {}).get("id") or "") or None,
                "home_sp_name": (home.get("probablePitcher") or {}).get("fullName"),
                "away_sp_id": str((away.get("probablePitcher") or {}).get("id") or "") or None,
                "away_sp_name": (away.get("probablePitcher") or {}).get("fullName"),
                "elevation": meta.get("elevation"),
                "venue_lat": meta.get("lat"),
                "venue_lon": meta.get("lon"),
                "venue_tz": meta.get("tz"),
                "venue_country": meta.get("country"),
            }
        )
    games = pd.DataFrame(rows)
    if games.empty:
        return games
    games = games.dropna(subset=["game_id", "home_team", "away_team", "season"])
    games = enrich_games(games)
    return games


def enrich_games(games: pd.DataFrame) -> pd.DataFrame:
    work = games.copy()
    work["_sort"] = pd.to_datetime(work["gameday"], errors="coerce")
    work = work.sort_values(["_sort", "game_id"])

    home_ml, away_ml, home_rl, away_rl = [], [], [], []
    ml_streak: dict[str, int] = {}
    rl_streak: dict[str, int] = {}
    last_day: dict[str, date] = {}
    last_venue: dict[str, tuple[tuple[float, float], int]] = {}
    road_streak: dict[str, int] = {}
    home_rest, away_rest = [], []
    home_travel, away_travel = [], []
    home_miles, away_miles = [], []
    home_tz, away_tz = [], []
    overseas, altitude, home_road, away_road = [], [], [], []

    def venue_xy_tz(row) -> tuple[tuple[float, float], int]:
        lat = _num(row.venue_lat)
        lon = _num(row.venue_lon)
        tz = _int(row.venue_tz)
        if lat is not None and lon is not None:
            return (lat, lon), tz if tz is not None else -6
        home = TEAM_HOMES.get(row.home_team)
        if home:
            return (home[0], home[1]), home[2]
        return (39.0, -98.0), -6

    for row in work.itertuples(index=False):
        gameday = None
        if row.gameday:
            try:
                gameday = datetime.strptime(str(row.gameday)[:10], "%Y-%m-%d").date()
            except ValueError:
                gameday = None
        xy, tz = venue_xy_tz(row)
        overseas_flag = is_overseas_venue(row.stadium, getattr(row, "venue_country", None))
        altitude.append(is_altitude_game(row.home_team, _num(row.elevation), row.stadium))
        overseas.append(overseas_flag)

        def rest_for(team: str) -> int | None:
            if not gameday or team not in last_day:
                return None
            return (gameday - last_day[team]).days

        home_rest.append(rest_for(row.home_team))
        away_rest.append(rest_for(row.away_team))

        true_home = str(row.location or "Home").lower() != "neutral" and not overseas_flag
        home_origin = TEAM_HOMES.get(row.home_team)
        away_origin = TEAM_HOMES.get(row.away_team)
        # Prefer hop from the previous game (series / road trip); fall back to home-park origin.
        home_prev = last_venue.get(row.home_team)
        away_prev = last_venue.get(row.away_team)
        if home_prev:
            home_hop = hop_travel(home_prev[0], home_prev[1], xy, tz, bool(overseas_flag))
        else:
            home_hop = team_travel_from_origin(home_origin, xy, tz, bool(overseas_flag), true_home)
        if away_prev:
            away_hop = hop_travel(away_prev[0], away_prev[1], xy, tz, bool(overseas_flag))
        else:
            away_hop = team_travel_from_origin(away_origin, xy, tz, bool(overseas_flag), False)

        home_travel.append(home_hop["travel"])
        away_travel.append(away_hop["travel"])
        home_miles.append(home_hop["travel_miles"])
        away_miles.append(away_hop["travel_miles"])
        home_tz.append(home_hop["tz_change"])
        away_tz.append(away_hop["tz_change"])
        home_road.append(road_streak.get(row.home_team, 0))
        away_road.append(road_streak.get(row.away_team, 0))
        home_ml.append(ml_streak.get(row.home_team, 0))
        away_ml.append(ml_streak.get(row.away_team, 0))
        home_rl.append(rl_streak.get(row.home_team, 0))
        away_rl.append(rl_streak.get(row.away_team, 0))

        result = _num(row.result)
        if result is None:
            continue
        home_won = True if result > 0 else False if result < 0 else None
        ml_streak[row.home_team] = next_streak(ml_streak.get(row.home_team, 0), home_won)
        ml_streak[row.away_team] = next_streak(
            ml_streak.get(row.away_team, 0), None if home_won is None else not home_won
        )
        # Run line as if each side laid -1.5: cover by winning by 2+.
        if result == 0:
            home_cover = away_cover = None
        else:
            home_cover = result >= 2
            away_cover = result <= -2
        rl_streak[row.home_team] = next_streak(rl_streak.get(row.home_team, 0), home_cover)
        rl_streak[row.away_team] = next_streak(rl_streak.get(row.away_team, 0), away_cover)
        road_streak[row.home_team] = 0 if true_home else road_streak.get(row.home_team, 0) + 1
        road_streak[row.away_team] = road_streak.get(row.away_team, 0) + 1
        if gameday:
            last_day[row.home_team] = gameday
            last_day[row.away_team] = gameday
        last_venue[row.home_team] = (xy, tz)
        last_venue[row.away_team] = (xy, tz)

    work["home_rest"] = home_rest
    work["away_rest"] = away_rest
    work["home_ml_streak"] = home_ml
    work["away_ml_streak"] = away_ml
    work["home_rl_streak"] = home_rl
    work["away_rl_streak"] = away_rl
    work["home_travel"] = home_travel
    work["away_travel"] = away_travel
    work["home_travel_miles"] = home_miles
    work["away_travel_miles"] = away_miles
    work["home_tz_change"] = home_tz
    work["away_tz_change"] = away_tz
    work["home_road_streak"] = home_road
    work["away_road_streak"] = away_road
    work["is_overseas"] = overseas
    work["is_altitude"] = altitude
    return work.drop(columns=["_sort", "game_date", "venue_id", "venue_lat", "venue_lon", "venue_tz", "venue_country"], errors="ignore")


def season_player_ids(years: list[int]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    hitting: dict[int, set[int]] = {year: set() for year in years}
    pitching: dict[int, set[int]] = {year: set() for year in years}
    urls = []
    for year in years:
        urls.append(("hitting", year, season_stats_url("hitting", year)))
        urls.append(("pitching", year, season_stats_url("pitching", year)))
    print(f"  season stat lists: {len(urls)}")
    for group, year, url in urls:
        try:
            payload = get_json(url)
        except Exception as exc:
            print(f"  skip {group} {year}: {exc}")
            continue
        splits = []
        for block in payload.get("stats") or []:
            splits.extend(block.get("splits") or [])
        bucket = hitting if group == "hitting" else pitching
        for split in splits:
            pid = (split.get("player") or {}).get("id")
            if pid:
                bucket[year].add(int(pid))
        print(f"  {year} {group}: {len(bucket[year])} players")
    return hitting, pitching


def _log_splits(payload: dict | None) -> list[dict]:
    splits = []
    for block in (payload or {}).get("stats") or []:
        splits.extend(block.get("splits") or [])
    return splits


def _player_row_from_split(split: dict, id_to_abbr: dict[int, str]) -> dict | None:
    kind = KEEP_TYPES.get(split.get("gameType"))
    if split.get("gameType") and not kind:
        return None
    game = split.get("game") or {}
    player = split.get("player") or {}
    team = split.get("team") or {}
    opp = split.get("opponent") or {}
    pid = str(player.get("id") or "")
    gid = str(game.get("gamePk") or "")
    if not pid or not gid:
        return None
    gameday = split.get("date")
    if gameday and str(gameday)[5:7] in {"01", "02"} and split.get("gameType") in {None, "S", "E"}:
        return None
    if not kind and split.get("gameType") in {None, "S", "E", "A"}:
        return None
    row = {
        "player_id": pid,
        "player_name": player.get("fullName"),
        "position": None,
        "team": team.get("abbreviation") or id_to_abbr.get(team.get("id")),
        "opponent": opp.get("abbreviation") or id_to_abbr.get(opp.get("id")),
        "season": _int(split.get("season")),
        "gameday": gameday,
        "season_type": kind or "REG",
        "game_id": gid,
        "is_home": int(bool(split.get("isHome"))),
    }
    positions = split.get("positionsPlayed") or []
    if positions:
        first = positions[0]
        if isinstance(first, dict):
            row["position"] = first.get("abbreviation")
        else:
            row["position"] = str(first)
    stat = split.get("stat") or {}
    if "inningsPitched" in stat:
        row["pitching_strikeouts"] = _num(stat.get("strikeOuts"))
        row["pitching_walks"] = _num(stat.get("baseOnBalls"))
        row["earned_runs"] = _num(stat.get("earnedRuns"))
        row["hits_allowed"] = _num(stat.get("hits"))
        outs = _int(stat.get("outs")) or innings_to_outs(stat.get("inningsPitched"))
        row["pitcher_outs"] = outs
        row["innings_pitched"] = None if outs is None else round(outs / 3.0, 3)
        row["pitches_thrown"] = _num(stat.get("numberOfPitches"))
        row["batters_faced"] = _num(stat.get("battersFaced"))
        row["home_runs_allowed"] = _num(stat.get("homeRuns"))
        row["games_started"] = _num(stat.get("gamesStarted"))
        if not row.get("position"):
            row["position"] = "P"
    else:
        row["hits"] = _num(stat.get("hits"))
        row["home_runs"] = _num(stat.get("homeRuns"))
        row["rbi"] = _num(stat.get("rbi"))
        row["runs"] = _num(stat.get("runs"))
        row["doubles"] = _num(stat.get("doubles"))
        row["triples"] = _num(stat.get("triples"))
        row["stolen_bases"] = _num(stat.get("stolenBases"))
        row["total_bases"] = _num(stat.get("totalBases"))
        row["walks"] = _num(stat.get("baseOnBalls"))
        row["strikeouts"] = _num(stat.get("strikeOuts"))
        row["at_bats"] = _num(stat.get("atBats"))
        row["plate_appearances"] = _num(stat.get("plateAppearances"))
    return row


def _merge_player_row(existing: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        if value is not None and (existing.get(key) is None or key not in existing):
            existing[key] = value
        elif key in {
            "hits", "home_runs", "rbi", "runs", "doubles", "triples", "stolen_bases",
            "total_bases", "walks", "strikeouts", "at_bats", "plate_appearances",
            "pitching_strikeouts", "pitching_walks", "earned_runs", "hits_allowed",
            "innings_pitched", "pitcher_outs", "pitches_thrown", "batters_faced",
            "home_runs_allowed", "games_started", "position",
        } and value is not None:
            existing[key] = value


def upsert_player_games(conn, rows: list[dict]) -> None:
    if not rows:
        return
    pk = {"player_id", "game_id"}
    updates = ",".join(
        f"{col}=COALESCE(excluded.{col}, player_games.{col})"
        for col in PLAYER_GAME_COLS
        if col not in pk
    )
    placeholders = ",".join("?" for _ in PLAYER_GAME_COLS)
    sql = (
        f"INSERT INTO player_games ({','.join(PLAYER_GAME_COLS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(player_id, game_id) DO UPDATE SET {updates}"
    )
    records = [tuple(_cell(row.get(col)) for col in PLAYER_GAME_COLS) for row in rows]
    conn.executemany(sql, records)
    conn.commit()


def ingest_player_games(
    conn,
    years: list[int],
    hitting_ids: dict[int, set[int]],
    pitching_ids: dict[int, set[int]],
    teams: dict[int, dict],
    game_ids: set[str],
    home_teams: dict[str, str],
    game_meta: dict[str, tuple],
) -> int:
    id_to_abbr = {tid: t["abbr"] for tid, t in teams.items()}
    jobs: list[tuple[int, int, str]] = []
    for year in years:
        for pid in hitting_ids[year]:
            jobs.append((year, pid, "hitting"))
        for pid in pitching_ids[year]:
            jobs.append((year, pid, "pitching"))
    urls = [player_log_url(pid, group, year) for year, pid, group in jobs]
    print(f"  player game logs: {len(urls)}", flush=True)
    batch: list[dict] = []
    done = 0
    written = 0
    for _url, payload, err in get_many(urls):
        done += 1
        if done % 100 == 0:
            print(f"    {done}/{len(urls)} written={written}", flush=True)
            gc.collect()
        if err or not payload:
            continue
        by_key: dict[tuple[str, str], dict] = {}
        for split in _log_splits(payload):
            row = _player_row_from_split(split, id_to_abbr)
            if not row or row["game_id"] not in game_ids:
                continue
            meta = game_meta.get(row["game_id"])
            if meta:
                season_type, gameday = meta
                if season_type:
                    row["season_type"] = season_type
                if gameday:
                    row["gameday"] = gameday
            if row["game_id"] in home_teams:
                row["is_home"] = 1 if home_teams[row["game_id"]] == row.get("team") else 0
            key = (row["player_id"], row["game_id"])
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = row
            else:
                _merge_player_row(existing, row)
        batch.extend(by_key.values())
        if len(batch) >= 400:
            upsert_player_games(conn, batch)
            written += len(batch)
            batch.clear()
    if batch:
        upsert_player_games(conn, batch)
        written += len(batch)
    print(f"  player-game rows written: {written}", flush=True)
    return written


def rebuild_players(conn) -> int:
    conn.execute("DELETE FROM players")
    conn.execute(
        """
        INSERT INTO players (player_id, player_name, position, latest_team)
        SELECT player_id, player_name, position, team
        FROM (
          SELECT player_id, player_name, position, team,
                 ROW_NUMBER() OVER (
                   PARTITION BY player_id
                   ORDER BY gameday DESC, season DESC, rowid DESC
                 ) AS rn
          FROM player_games
        )
        WHERE rn = 1
        """
    )
    conn.commit()
    count = int(conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
    print(f"  players: {count}", flush=True)
    return count


def load_player_games(
    years: list[int],
    hitting_ids: dict[int, set[int]],
    pitching_ids: dict[int, set[int]],
    teams: dict[int, dict],
) -> pd.DataFrame:
    id_to_abbr = {tid: t["abbr"] for tid, t in teams.items()}
    jobs: list[tuple[int, int, str]] = []
    for year in years:
        for pid in hitting_ids[year]:
            jobs.append((year, pid, "hitting"))
        for pid in pitching_ids[year]:
            jobs.append((year, pid, "pitching"))
    urls = [player_log_url(pid, group, year) for year, pid, group in jobs]
    print(f"  player game logs: {len(urls)}")
    by_key: dict[tuple[str, str], dict] = {}
    done = 0
    for url, payload, err in get_many(urls):
        done += 1
        if done % 400 == 0:
            print(f"    {done}/{len(urls)}")
        if err or not payload:
            continue
        for split in _log_splits(payload):
            row = _player_row_from_split(split, id_to_abbr)
            if not row:
                continue
            key = (row["player_id"], row["game_id"])
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = row
            else:
                _merge_player_row(existing, row)
    print(f"  player-game rows: {len(by_key)}")
    return pd.DataFrame(list(by_key.values()))


def load_team_games(years: list[int], teams: dict[int, dict]) -> pd.DataFrame:
    id_to_abbr = {tid: t["abbr"] for tid, t in teams.items()}
    jobs = []
    for year in years:
        for team_id in teams:
            jobs.append((year, team_id, "hitting"))
            jobs.append((year, team_id, "pitching"))
    urls = [team_log_url(tid, group, year) for year, tid, group in jobs]
    print(f"  team game logs: {len(urls)}")
    by_key: dict[tuple[str, str], dict] = {}
    for url, payload, err in get_many(urls):
        if err or not payload:
            continue
        for split in _log_splits(payload):
            game = split.get("game") or {}
            team = split.get("team") or {}
            opp = split.get("opponent") or {}
            gid = str(game.get("gamePk") or "")
            abbr = team.get("abbreviation") or id_to_abbr.get(team.get("id"))
            if not gid or not abbr:
                continue
            key = (gid, abbr)
            row = by_key.setdefault(
                key,
                {
                    "game_id": gid,
                    "team": abbr,
                    "opponent": opp.get("abbreviation") or id_to_abbr.get(opp.get("id")),
                    "season": _int(split.get("season")),
                    "gameday": split.get("date"),
                    "season_type": "REG",
                    "is_home": int(bool(split.get("isHome"))),
                },
            )
            stat = split.get("stat") or {}
            if "inningsPitched" in stat or "earnedRuns" in stat:
                row["earned_runs"] = _num(stat.get("earnedRuns"))
                row["hits_allowed"] = _num(stat.get("hits"))
                row["pitching_strikeouts"] = _num(stat.get("strikeOuts"))
                row["pitching_walks"] = _num(stat.get("baseOnBalls"))
                outs = _int(stat.get("outs")) or innings_to_outs(stat.get("inningsPitched"))
                row["innings_pitched"] = None if outs is None else round(outs / 3.0, 3)
                row["home_runs_allowed"] = _num(stat.get("homeRuns"))
            else:
                row["runs"] = _num(stat.get("runs"))
                row["hits"] = _num(stat.get("hits"))
                row["home_runs"] = _num(stat.get("homeRuns"))
                row["walks"] = _num(stat.get("baseOnBalls"))
                row["strikeouts"] = _num(stat.get("strikeOuts"))
                row["doubles"] = _num(stat.get("doubles"))
                row["stolen_bases"] = _num(stat.get("stolenBases"))
    print(f"  team-game rows: {len(by_key)}")
    return pd.DataFrame(list(by_key.values()))


def load_il_intervals(years: list[int], teams: dict[int, dict]) -> list[dict]:
    id_to_abbr = {tid: t["abbr"] for tid, t in teams.items()}
    urls = []
    for year in years:
        urls.extend(transactions_url(start, end) for start, end in month_windows(year))
    print(f"  transaction windows: {len(urls)}")
    events = []
    for url, payload, err in get_many(urls, workers=6):
        if err or not payload:
            continue
        for row in payload.get("transactions") or []:
            desc = str(row.get("description") or "")
            low = desc.lower()
            if "injured list" not in low and " injured list" not in low:
                continue
            person = row.get("person") or {}
            team = row.get("toTeam") or row.get("fromTeam") or {}
            abbr = team.get("abbreviation") or id_to_abbr.get(team.get("id"))
            placed = "placed" in low and "injured list" in low
            activated = "activated" in low and "injured list" in low
            if not placed and not activated:
                continue
            injury = None
            if "." in desc:
                tail = desc.split(".")[-1].strip()
                if tail and "injured list" not in tail.lower():
                    injury = tail.rstrip(".")
            events.append(
                {
                    "player_id": str(person.get("id") or ""),
                    "player_name": person.get("fullName"),
                    "team": abbr,
                    "date": row.get("effectiveDate") or row.get("date"),
                    "placed": placed,
                    "activated": activated,
                    "injury": injury,
                    "description": desc,
                }
            )
    events.sort(key=lambda e: (e.get("date") or "", e["player_id"]))
    open_il: dict[tuple[str, str], dict] = {}
    intervals = []
    for event in events:
        if not event["player_id"] or not event["team"] or not event["date"]:
            continue
        key = (event["player_id"], event["team"])
        if event["placed"]:
            open_il[key] = event
        elif event["activated"] and key in open_il:
            start = open_il.pop(key)
            intervals.append(
                {
                    "player_id": event["player_id"],
                    "player_name": event["player_name"] or start["player_name"],
                    "team": event["team"],
                    "start": start["date"],
                    "end": event["date"],
                    "injury": start.get("injury") or event.get("injury"),
                }
            )
    today = "9999-12-31"
    for start in open_il.values():
        intervals.append(
            {
                "player_id": start["player_id"],
                "player_name": start["player_name"],
                "team": start["team"],
                "start": start["date"],
                "end": today,
                "injury": start.get("injury"),
            }
        )
    print(f"  IL intervals: {len(intervals)}")
    return intervals


def prepare_missing_regulars(
    games: pd.DataFrame,
    player_games: pd.DataFrame,
    intervals: list[dict],
) -> pd.DataFrame:
    if games.empty or player_games.empty or not intervals:
        return pd.DataFrame()
    logs = player_games.dropna(subset=["player_id", "team", "gameday"]).copy()
    logs["_day"] = pd.to_datetime(logs["gameday"], errors="coerce")
    logs = logs.dropna(subset=["_day"]).sort_values("_day")
    by_player: dict[tuple[str, str], pd.DataFrame] = {}
    for (pid, team), chunk in logs.groupby(["player_id", "team"], sort=False):
        by_player[(str(pid), str(team))] = chunk

    il_by_team: dict[str, list[dict]] = defaultdict(list)
    for item in intervals:
        il_by_team[item["team"]].append(item)

    rows = []
    for game in games.itertuples(index=False):
        gameday = str(game.gameday or "")[:10]
        if not gameday:
            continue
        for team in (game.home_team, game.away_team):
            for item in il_by_team.get(team, []):
                if not (item["start"] <= gameday < item["end"]):
                    continue
                hist = by_player.get((item["player_id"], team))
                pa = ip = 0.0
                position = None
                if hist is not None:
                    prior = hist[hist["_day"] < pd.Timestamp(gameday)].tail(REGULAR_LOOKBACK_GAMES)
                    pa = float(prior["plate_appearances"].fillna(0).sum()) if "plate_appearances" in prior else 0.0
                    ip = float(prior["innings_pitched"].fillna(0).sum()) if "innings_pitched" in prior else 0.0
                    if not prior.empty:
                        position = prior.iloc[-1].get("position")
                if pa < REGULAR_PA and ip < REGULAR_IP:
                    continue
                rows.append(
                    {
                        "game_id": game.game_id,
                        "gameday": gameday,
                        "season": game.season,
                        "team": team,
                        "player_id": item["player_id"],
                        "player_name": item["player_name"],
                        "position": position or ("P" if ip >= pa else None),
                        "side": "pitching" if ip >= REGULAR_IP and ip >= pa else "hitting",
                        "pa_recent": pa,
                        "ip_recent": ip,
                        "status": "IL",
                        "injury": item.get("injury"),
                    }
                )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates(["game_id", "team", "player_id"])


def write_frame(conn, table: str, frame: pd.DataFrame, columns: list[str]) -> None:
    conn.execute(f"DELETE FROM {table}")
    if frame.empty:
        conn.commit()
        print(f"  {table}: 0 rows")
        return
    subset = frame.reindex(columns=columns)
    records = [tuple(_cell(v) for v in row) for row in subset.itertuples(index=False, name=None)]
    placeholders = ",".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        records,
    )
    conn.commit()
    print(f"  {table}: {len(records)} rows")


GAME_COLS = [
    "game_id", "season", "gameday", "weekday", "gametime", "season_type",
    "home_team", "away_team", "home_score", "away_score", "result", "total",
    "roof", "surface", "surface_group", "temp", "wind", "condition", "day_night",
    "home_rest", "away_rest", "home_ml_streak", "away_ml_streak",
    "home_rl_streak", "away_rl_streak", "stadium", "stadium_id", "location",
    "div_game", "is_overseas", "is_night", "is_early_window", "is_altitude",
    "home_travel", "away_travel", "home_travel_miles", "away_travel_miles",
    "home_tz_change", "away_tz_change", "home_road_streak", "away_road_streak",
    "home_sp_id", "home_sp_name", "away_sp_id", "away_sp_name", "elevation",
]

PLAYER_GAME_COLS = [
    "player_id", "player_name", "position", "team", "opponent", "season",
    "gameday", "season_type", "game_id", "is_home",
    "hits", "home_runs", "rbi", "runs", "doubles", "triples", "stolen_bases",
    "total_bases", "walks", "strikeouts", "at_bats", "plate_appearances",
    "pitching_strikeouts", "pitching_walks", "earned_runs", "hits_allowed",
    "innings_pitched", "pitcher_outs", "pitches_thrown", "batters_faced",
    "home_runs_allowed", "games_started",
]

TEAM_GAME_COLS = [
    "season", "gameday", "season_type", "game_id", "team", "opponent", "is_home",
    "runs", "hits", "home_runs", "walks", "strikeouts", "doubles", "stolen_bases",
    "earned_runs", "hits_allowed", "pitching_strikeouts", "pitching_walks",
    "innings_pitched", "home_runs_allowed",
]


def run_ingest(years: list[int] | None = None, resume: bool = False) -> dict:
    years = years or SEASONS
    print(f"Ingesting seasons {years[0]}-{years[-1]}", flush=True)
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("ingest_complete", "0"))
    conn.commit()
    existing_games = 0
    if resume:
        try:
            existing_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        except Exception:
            existing_games = 0

    if existing_games:
        print(f"Resuming; keeping {existing_games} games", flush=True)
        teams = load_teams(years)
        write_frame(
            conn,
            "teams",
            pd.DataFrame(list(teams.values())),
            ["team_id", "abbr", "name", "league_id", "division_id"],
        )
        games = pd.read_sql_query(
            "SELECT game_id, season, gameday, season_type, home_team, away_team FROM games",
            conn,
        )
    else:
        reset_schema(conn)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("ingest_complete", "0"))
        conn.commit()

        print("Teams", flush=True)
        teams = load_teams(years)
        write_frame(
            conn,
            "teams",
            pd.DataFrame(list(teams.values())),
            ["team_id", "abbr", "name", "league_id", "division_id"],
        )

        print("Schedules", flush=True)
        raw_games = load_schedule(years)
        venue_ids = set()
        for game in raw_games:
            vid = (game.get("venue") or {}).get("id")
            if vid:
                venue_ids.add(int(vid))
        for team in teams.values():
            if team.get("venue_id"):
                venue_ids.add(int(team["venue_id"]))
        print("Venues", flush=True)
        venues = load_venues(venue_ids)
        games = prepare_games(raw_games, teams, venues)
        write_frame(conn, "games", games, GAME_COLS)
        del raw_games, venues
        gc.collect()

    existing_tg = int(conn.execute("SELECT COUNT(*) FROM team_games").fetchone()[0])
    if existing_tg:
        print(f"Keeping {existing_tg} team games", flush=True)
        team_games_n = existing_tg
    else:
        print("Team game logs", flush=True)
        team_games = load_team_games(years, teams)
        if not team_games.empty and not games.empty:
            gmap = games.set_index("game_id")[["season_type", "gameday", "season"]]
            for col in ("season_type", "gameday", "season"):
                team_games[col] = team_games["game_id"].map(gmap[col]).combine_first(team_games[col])
            team_games = team_games[team_games["game_id"].isin(set(games["game_id"]))]
        write_frame(conn, "team_games", team_games, TEAM_GAME_COLS)
        team_games_n = len(team_games)
        del team_games
        gc.collect()

    player_done = conn.execute(
        "SELECT value FROM meta WHERE key='player_ingest_done'"
    ).fetchone()
    if player_done and str(player_done[0]) == "1":
        player_games_n = int(conn.execute("SELECT COUNT(*) FROM player_games").fetchone()[0])
        print(f"Keeping {player_games_n} player games", flush=True)
    else:
        print("Player IDs", flush=True)
        hitting_ids, pitching_ids = season_player_ids(years)
        print("Player game logs", flush=True)
        game_ids = set(str(gid) for gid in games["game_id"])
        home_teams = {str(gid): team for gid, team in zip(games["game_id"], games["home_team"])}
        game_meta = {
            str(gid): (stype, gday)
            for gid, stype, gday in zip(games["game_id"], games["season_type"], games["gameday"])
        }
        player_games_n = ingest_player_games(
            conn, years, hitting_ids, pitching_ids, teams, game_ids, home_teams, game_meta
        )
        rebuild_players(conn)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("player_ingest_done", "1"),
        )
        conn.commit()
        del hitting_ids, pitching_ids, game_ids, home_teams, game_meta
        gc.collect()

    print("Injured list", flush=True)
    intervals = load_il_intervals(years, teams)
    player_games = pd.read_sql_query(
        """
        SELECT player_id, team, gameday, plate_appearances, innings_pitched, position
        FROM player_games
        """,
        conn,
    )
    il_games = games[games["season"].isin(years)] if not games.empty else games
    missing = prepare_missing_regulars(il_games, player_games, intervals)
    write_frame(
        conn,
        "missing_regulars",
        missing,
        [
            "game_id", "gameday", "season", "team", "player_id", "player_name",
            "position", "side", "pa_recent", "ip_recent", "status", "injury",
        ],
    )
    del player_games, missing, intervals
    gc.collect()

    print("Pitcher / batter hands", flush=True)
    from diamond.hands import enrich_hands

    hands_n = enrich_hands(conn)
    print(f"  hands updated: {hands_n}", flush=True)

    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        ("ingested_at", datetime.now(timezone.utc).isoformat()),
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        ("seasons", ",".join(str(y) for y in years)),
    )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("ingest_complete", "1"))
    conn.commit()
    conn.close()
    print("Done.", flush=True)
    return {
        "seasons": years,
        "games": len(games),
        "team_games": team_games_n,
        "player_games": player_games_n,
    }


if __name__ == "__main__":
    run_ingest()
