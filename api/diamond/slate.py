from __future__ import annotations

from datetime import date, datetime

from diamond.config import TEAM_LOOKBACK_GAMES, TEAM_RECENT_GAMES
from diamond.venues import team_name

TEAM_GAMES_SQL = """
SELECT
  game_id, season, gameday, season_type,
  home_team AS team, away_team AS opponent,
  1 AS is_home,
  home_score AS runs_for, away_score AS runs_against
FROM games
WHERE home_score IS NOT NULL AND away_score IS NOT NULL
UNION ALL
SELECT
  game_id, season, gameday, season_type,
  away_team AS team, home_team AS opponent,
  0 AS is_home,
  away_score AS runs_for, home_score AS runs_against
FROM games
WHERE home_score IS NOT NULL AND away_score IS NOT NULL
"""

SLATE_GAME_COLS = """
  game_id, season, gameday, weekday, gametime, season_type,
  home_team, away_team, home_score, away_score,
  roof, surface, surface_group, temp, wind, condition, day_night, stadium, location,
  home_rest, away_rest, div_game, is_night, is_early_window,
  is_altitude, is_overseas,
  home_travel, away_travel, home_travel_miles, away_travel_miles,
  home_tz_change, away_tz_change,
  home_sp_id, home_sp_name, away_sp_id, away_sp_name, elevation
"""


def rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn, sql: str, params: tuple = ()) -> dict | None:
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found else None


def _round(value, digits: int = 1):
    if value is None:
        return None
    try:
        if value != value:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _mean(values: list, digits: int = 1):
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), digits)


def _as_date(value) -> date | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def day_label(gameday: str | None, games: int, unplayed: int | None) -> str:
    parsed = _as_date(gameday)
    if not parsed:
        return gameday or "—"
    label = parsed.strftime("%a %b %d, %Y").replace(" 0", " ")
    suffix = f"{games} games"
    if unplayed:
        suffix += f" · {unplayed} unplayed"
    return f"{label} · {suffix}"


def list_days(conn) -> list[dict]:
    found = rows(
        conn,
        """
        SELECT gameday,
               MIN(season) AS season,
               COUNT(*) AS games,
               SUM(CASE WHEN home_score IS NULL THEN 1 ELSE 0 END) AS unplayed
        FROM games
        GROUP BY gameday
        ORDER BY gameday DESC
        """,
    )
    for item in found:
        item["label"] = day_label(item["gameday"], item["games"], item["unplayed"])
    return found


def resolve_slate(conn, gameday: str | None = None) -> dict | None:
    days = list_days(conn)
    if not days:
        return None
    if gameday:
        match = next((d for d in days if d["gameday"] == gameday), None)
        if match:
            return match
    today = date.today()
    lookup = {_as_date(d["gameday"]): d for d in days}
    if today in lookup:
        return lookup[today]
    upcoming = [d for d in days if (_as_date(d["gameday"]) or date.min) >= today]
    upcoming.sort(key=lambda d: _as_date(d["gameday"]) or date.max)
    if upcoming:
        first = _as_date(upcoming[0]["gameday"])
        if first and (first - today).days <= 14:
            return upcoming[0]
    past = [d for d in days if (_as_date(d["gameday"]) or date.max) < today]
    return past[0] if past else days[0]


def decorate_game(game: dict) -> dict:
    game = dict(game)
    game["home_name"] = team_name(game.get("home_team"))
    game["away_name"] = team_name(game.get("away_team"))
    game["played"] = game.get("home_score") is not None and game.get("away_score") is not None
    game["neutral"] = str(game.get("location") or "Home").lower() == "neutral" or bool(game.get("is_overseas"))
    return game


def slate_games(conn, gameday: str) -> list[dict]:
    games = rows(
        conn,
        f"""
        SELECT {SLATE_GAME_COLS}
        FROM games
        WHERE gameday = ?
        ORDER BY gametime, away_team
        """,
        (gameday,),
    )
    return [decorate_game(game) for game in games]


def missing_for(conn, game_id: str, team: str) -> list[dict]:
    return rows(
        conn,
        """
        SELECT player_name, position, side, pa_recent, ip_recent, status, injury
        FROM missing_regulars
        WHERE game_id = ? AND team = ?
        ORDER BY COALESCE(pa_recent, 0) + COALESCE(ip_recent, 0) DESC
        """,
        (game_id, team),
    )


def _profile_from_games(games: list[dict], limit: int) -> dict | None:
    sample = games[:limit]
    if not sample:
        return None
    runs_for = [g["runs_for"] for g in sample]
    runs_against = [g["runs_against"] for g in sample]
    rpg = _mean(runs_for)
    rapg = _mean(runs_against)
    margin = None if rpg is None or rapg is None else round(rpg - rapg, 1)
    first = sample[-1]
    last = sample[0]
    k9 = []
    for game in sample:
        k = game.get("pitching_strikeouts")
        inn = game.get("innings_pitched")
        if k is None or not inn:
            continue
        k9.append(float(k) * 9.0 / float(inn))
    era = []
    for game in sample:
        er = game.get("earned_runs")
        inn = game.get("innings_pitched")
        if er is None or not inn:
            continue
        era.append(float(er) * 9.0 / float(inn))
    return {
        "games": len(sample),
        "from_gameday": first.get("gameday"),
        "to_gameday": last.get("gameday"),
        "from_season": first.get("season"),
        "to_season": last.get("season"),
        "rpg": rpg,
        "rapg": rapg,
        "margin": margin,
        "hits": _mean([g.get("hits") for g in sample], 1),
        "home_runs": _mean([g.get("home_runs") for g in sample], 2),
        "runs": rpg,
        "hits_allowed": _mean([g.get("hits_allowed") for g in sample], 1),
        "home_runs_allowed": _mean([g.get("home_runs_allowed") for g in sample], 2),
        "era": _mean(era, 2),
        "k9": _mean(k9, 1),
        "walks": _mean([g.get("walks") for g in sample], 1),
        "strikeouts": _mean([g.get("strikeouts") for g in sample], 1),
    }


def load_team_log(conn, team: str, before: str | None, season_type: str = "REG") -> list[dict]:
    params: list = [team, season_type]
    before_clause = ""
    if before:
        before_clause = "AND tg.gameday < ?"
        params.append(before)
    return rows(
        conn,
        f"""
        SELECT
          tg.game_id, tg.season, tg.gameday, tg.season_type,
          tg.team, tg.opponent, tg.is_home, tg.runs_for, tg.runs_against,
          tw.runs, tw.hits, tw.home_runs, tw.walks, tw.strikeouts, tw.doubles, tw.stolen_bases,
          tw.earned_runs, tw.hits_allowed, tw.pitching_strikeouts, tw.pitching_walks,
          tw.innings_pitched, tw.home_runs_allowed
        FROM ({TEAM_GAMES_SQL}) tg
        LEFT JOIN team_games tw
          ON tw.team = tg.team
         AND tw.game_id = tg.game_id
        WHERE tg.team = ?
          AND COALESCE(tg.season_type, 'REG') = ?
          {before_clause}
        ORDER BY tg.gameday DESC, tg.game_id DESC
        """,
        tuple(params),
    )


def build_team_card(
    conn,
    team: str,
    is_home: bool,
    game_id: str,
    before: str | None,
    season_type: str = "REG",
) -> dict:
    log = load_team_log(conn, team, before, "REG")
    if not log:
        log = load_team_log(conn, team, before, season_type or "REG")
    overall = _profile_from_games(log, TEAM_LOOKBACK_GAMES)
    recent = _profile_from_games(log, TEAM_RECENT_GAMES)
    role_games = [g for g in log if bool(g.get("is_home")) == is_home]
    role = _profile_from_games(role_games, TEAM_LOOKBACK_GAMES)
    return {
        "team": team,
        "name": team_name(team),
        "is_home": int(is_home),
        "overall": overall,
        "recent": recent,
        "role": role,
        "missing": missing_for(conn, game_id, team),
    }


def league_environment(conn, since: str | None, before: str | None, season_type: str = "REG") -> dict:
    clauses = ["home_score IS NOT NULL", "away_score IS NOT NULL", "COALESCE(season_type, 'REG') = ?"]
    params: list = [season_type]
    if since:
        clauses.append("gameday >= ?")
        params.append(since)
    if before:
        clauses.append("gameday < ?")
        params.append(before)
    where = " AND ".join(clauses)
    env = one(
        conn,
        f"""
        SELECT
          AVG((home_score + away_score) / 2.0) AS league_rpg,
          AVG(CASE
                WHEN LOWER(COALESCE(location, 'Home')) = 'home' AND COALESCE(is_overseas, 0) = 0
                THEN home_score - away_score
              END) AS hfa,
          COUNT(*) AS games
        FROM games
        WHERE {where}
        """,
        tuple(params),
    ) or {}
    return {
        "league_rpg": _round(env.get("league_rpg"), 2),
        "hfa": _round(env.get("hfa"), 2),
        "games": env.get("games") or 0,
    }


def expected_runs(offense_rpg, defense_rapg, league_rpg, extra: float = 0.0):
    if offense_rpg is None or defense_rapg is None or league_rpg is None:
        return None
    return round(float(offense_rpg) + float(defense_rapg) - float(league_rpg) + extra, 1)


def expected_from_profiles(home: dict, away: dict, env: dict, neutral: bool) -> dict | None:
    home_over = (home or {}).get("overall") or {}
    away_over = (away or {}).get("overall") or {}
    league = env.get("league_rpg")
    hfa = 0.0 if neutral else float(env.get("hfa") or 0)
    home_pts = expected_runs(home_over.get("rpg"), away_over.get("rapg"), league, hfa)
    away_pts = expected_runs(away_over.get("rpg"), home_over.get("rapg"), league, 0.0)
    if home_pts is None or away_pts is None:
        return None
    home_recent = (home or {}).get("recent") or {}
    away_recent = (away or {}).get("recent") or {}
    recent_home = expected_runs(home_recent.get("rpg"), away_recent.get("rapg"), league, hfa)
    recent_away = expected_runs(away_recent.get("rpg"), home_recent.get("rapg"), league, 0.0)
    recent = None
    if recent_home is not None and recent_away is not None:
        recent = {
            "away_runs": recent_away,
            "home_runs": recent_home,
            "total": round(recent_away + recent_home, 1),
            "margin": round(recent_home - recent_away, 1),
        }
    return {
        "away_runs": away_pts,
        "home_runs": home_pts,
        "total": round(away_pts + home_pts, 1),
        "margin": round(home_pts - away_pts, 1),
        "hfa": round(hfa, 2),
        "league_rpg": league,
        "recent": recent,
        "method": "team RPG + opponent RAPG - league RPG, plus home-field from the same window",
    }


def get_slate(conn, gameday: str | None = None) -> dict:
    current = resolve_slate(conn, gameday)
    if not current:
        return {"slate": None, "days": [], "games": []}
    games = slate_games(conn, current["gameday"])
    days = list_days(conn)
    today = date.today()
    nearby = []
    for item in days:
        parsed = _as_date(item["gameday"])
        if parsed and abs((parsed - today).days) <= 45:
            nearby.append(item)
    nearby.sort(key=lambda d: d["gameday"] or "", reverse=True)
    if current["gameday"] not in {d["gameday"] for d in nearby}:
        nearby.insert(0, current)
    return {"slate": current, "days": nearby[:90], "games": games}


def get_matchup(conn, game_id: str) -> dict | None:
    game = one(conn, f"SELECT {SLATE_GAME_COLS} FROM games WHERE game_id = ?", (game_id,))
    if not game:
        return None
    game = decorate_game(game)
    before = game.get("gameday")
    away = build_team_card(conn, game["away_team"], False, game["game_id"], before, "REG")
    home = build_team_card(conn, game["home_team"], True, game["game_id"], before, "REG")
    since_candidates = [
        (away.get("overall") or {}).get("from_gameday"),
        (home.get("overall") or {}).get("from_gameday"),
    ]
    since = min((d for d in since_candidates if d), default=None)
    env = league_environment(conn, since, before, "REG")
    expected = expected_from_profiles(home, away, env, bool(game.get("neutral")))
    return {
        "game": game,
        "away": away,
        "home": home,
        "environment": env,
        "expected": expected,
        "lookback_games": TEAM_LOOKBACK_GAMES,
        "recent_games": TEAM_RECENT_GAMES,
    }
