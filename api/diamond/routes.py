from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from diamond.config import DATA_DIR, DB_PATH
from diamond.db import connect
from diamond.slate import get_matchup, get_slate
from diamond.hands import season_hand_splits
from diamond.venues import PACIFIC_TEAMS

router = APIRouter()

STATS = {
    "hits": "Hits",
    "home_runs": "Home runs",
    "rbi": "RBI",
    "runs": "Runs",
    "doubles": "Doubles",
    "triples": "Triples",
    "stolen_bases": "Stolen bases",
    "total_bases": "Total bases",
    "walks": "Walks",
    "strikeouts": "Strikeouts (bat)",
    "at_bats": "At bats",
    "plate_appearances": "Plate appearances",
    "pitching_strikeouts": "Strikeouts (pit)",
    "pitching_walks": "Walks allowed",
    "earned_runs": "Earned runs",
    "hits_allowed": "Hits allowed",
    "innings_pitched": "Innings",
    "pitcher_outs": "Outs recorded",
    "pitches_thrown": "Pitches",
    "batters_faced": "Batters faced",
    "home_runs_allowed": "HR allowed",
}

DEFAULT_LINES = {
    "P": ("pitching_strikeouts", 5.5),
    "SP": ("pitching_strikeouts", 5.5),
    "RP": ("pitching_strikeouts", 2.5),
}


def rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn, sql: str, params: tuple = ()) -> dict | None:
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found else None


@router.get("/health")
def health():
    return {"ok": True, "db": DB_PATH.exists()}


@router.get("/api/meta")
def meta():
    if not DB_PATH.exists():
        return {"ingested": False, "stats": STATS}
    conn = connect()
    try:
        kv = {r["key"]: r["value"] for r in rows(conn, "SELECT key, value FROM meta")}
        counts = one(
            conn,
            """
            SELECT
              (SELECT COUNT(*) FROM games) AS games,
              (SELECT COUNT(*) FROM players) AS players,
              (SELECT COUNT(*) FROM player_games) AS player_games,
              (SELECT COUNT(*) FROM team_games) AS team_games,
              (SELECT COUNT(*) FROM missing_regulars) AS missing_regulars
            """,
        )
        return {
            "ingested": True,
            "stats": STATS,
            "ingest_lock": (DATA_DIR / "ingest.lock").exists(),
            **kv,
            **(counts or {}),
        }
    finally:
        conn.close()


@router.get("/api/players/search")
def search_players(q: str = Query(..., min_length=2), limit: int = 15):
    conn = connect()
    try:
        return rows(
            conn,
            """
            SELECT player_id, player_name, position, latest_team, throws, bats
            FROM players
            WHERE player_name LIKE ?
            ORDER BY
              CASE WHEN player_name LIKE ? THEN 0 ELSE 1 END,
              player_name
            LIMIT ?
            """,
            (f"%{q}%", f"{q}%", limit),
        )
    finally:
        conn.close()


@router.get("/api/players/{player_id}")
def player_summary(player_id: str):
    conn = connect()
    try:
        player = one(
            conn,
            "SELECT player_id, player_name, position, latest_team, throws, bats FROM players WHERE player_id = ?",
            (player_id,),
        )
        if not player:
            raise HTTPException(404, "Player not found")
        default_stat, default_line = DEFAULT_LINES.get(player["position"] or "", ("hits", 0.5))
        return {
            **player,
            "default_stat": default_stat,
            "default_line": default_line,
            "stats": STATS,
            "hand_splits": season_hand_splits(player_id, player.get("position")),
        }
    finally:
        conn.close()


def _streak_clause(column: str, direction: str | None, params: list) -> str:
    if direction == "win":
        params.append(2)
        return f"AND {column} >= ?"
    if direction == "loss":
        params.append(-2)
        return f"AND {column} <= ?"
    return ""


@router.get("/api/players/{player_id}/prop")
def player_prop(
    player_id: str,
    stat: str = "hits",
    line: float = 0.5,
    home: int | None = None,
    min_rest: int | None = None,
    max_wind: float | None = None,
    roof: str | None = None,
    ml_streak: str | None = None,
    rl_streak: str | None = None,
    travel: str | None = None,
    div_game: int | None = None,
    night: int | None = None,
    extra_rest: int | None = None,
    surface: str | None = None,
    altitude: int | None = None,
    west_coast_early: int | None = None,
    consec_road: int | None = None,
    opp_hand: str | None = None,
    season_from: int | None = None,
    season_to: int | None = None,
    season_type: str = "REG",
):
    if stat not in STATS:
        raise HTTPException(400, f"Unknown stat. Choose from: {', '.join(STATS)}")

    conn = connect()
    try:
        player = one(
            conn,
            "SELECT player_id, player_name, position, latest_team, throws, bats FROM players WHERE player_id = ?",
            (player_id,),
        )
        if not player:
            raise HTTPException(404, "Player not found")

        params: list = [player_id]
        where = ["pg.player_id = ?", f"pg.{stat} IS NOT NULL"]

        if season_type:
            where.append("pg.season_type = ?")
            params.append(season_type)
        if home is not None:
            where.append("pg.is_home = ?")
            params.append(home)
        if season_from is not None:
            where.append("pg.season >= ?")
            params.append(season_from)
        if season_to is not None:
            where.append("pg.season <= ?")
            params.append(season_to)
        if min_rest is not None:
            where.append(
                "((pg.is_home = 1 AND g.home_rest >= ?) OR (pg.is_home = 0 AND g.away_rest >= ?))"
            )
            params.extend([min_rest, min_rest])
        if max_wind is not None:
            where.append("(g.wind IS NULL OR g.wind <= ?)")
            params.append(max_wind)
        if roof == "outdoors":
            where.append("g.roof IN ('outdoors', 'open')")
        elif roof == "indoor":
            where.append("g.roof IN ('dome', 'closed', 'retractable')")
        elif roof:
            where.append("g.roof = ?")
            params.append(roof)

        ml_col = "CASE WHEN pg.is_home = 1 THEN g.home_ml_streak ELSE g.away_ml_streak END"
        rl_col = "CASE WHEN pg.is_home = 1 THEN g.home_rl_streak ELSE g.away_rl_streak END"
        travel_col = "CASE WHEN pg.is_home = 1 THEN g.home_travel ELSE g.away_travel END"
        miles_col = "CASE WHEN pg.is_home = 1 THEN g.home_travel_miles ELSE g.away_travel_miles END"
        tz_col = "CASE WHEN pg.is_home = 1 THEN g.home_tz_change ELSE g.away_tz_change END"
        road_col = "CASE WHEN pg.is_home = 1 THEN g.home_road_streak ELSE g.away_road_streak END"
        rest_col = "CASE WHEN pg.is_home = 1 THEN g.home_rest ELSE g.away_rest END"
        pacific = ",".join(f"'{t}'" for t in sorted(PACIFIC_TEAMS))
        where.append(_streak_clause(ml_col, ml_streak, params).lstrip("AND ").strip() or "1=1")
        where.append(_streak_clause(rl_col, rl_streak, params).lstrip("AND ").strip() or "1=1")

        if travel:
            where.append(f"{travel_col} = ?")
            params.append(travel)
        if div_game is not None:
            where.append("g.div_game = ?")
            params.append(div_game)
        if night is not None:
            where.append("g.is_night = ?")
            params.append(night)
        if extra_rest:
            where.append(f"{rest_col} >= 2")
        if surface:
            where.append("g.surface_group = ?")
            params.append(surface)
        if altitude is not None:
            where.append("g.is_altitude = ?")
            params.append(altitude)
        if west_coast_early:
            where.append(f"g.is_early_window = 1 AND pg.team IN ({pacific})")
        if consec_road:
            where.append(f"{road_col} >= ?")
            params.append(consec_road)

        opp_throws_sql = "CASE WHEN pg.is_home = 1 THEN ap.throws ELSE hp.throws END"
        opp_sp_sql = "CASE WHEN pg.is_home = 1 THEN g.away_sp_name ELSE g.home_sp_name END"
        if opp_hand in {"L", "R"}:
            where.append(f"{opp_throws_sql} = ?")
            params.append(opp_hand)

        where = [clause for clause in where if clause != "1=1"]

        join_sql = """
            FROM player_games pg
            LEFT JOIN games g ON g.game_id = pg.game_id
            LEFT JOIN players hp ON hp.player_id = g.home_sp_id
            LEFT JOIN players ap ON ap.player_id = g.away_sp_id
        """

        sql = f"""
            SELECT
              pg.season, pg.gameday, pg.season_type,
              pg.game_id, pg.team, pg.opponent, pg.is_home, pg.position,
              pg.{stat} AS stat_value,
              g.weekday, g.gametime, g.roof, g.temp, g.wind, g.condition, g.day_night,
              g.surface, g.surface_group, g.stadium, g.div_game,
              g.is_overseas, g.is_night, g.is_early_window, g.is_altitude,
              {rest_col} AS rest_days,
              {ml_col} AS ml_streak,
              {rl_col} AS rl_streak,
              {travel_col} AS travel,
              {miles_col} AS travel_miles,
              {tz_col} AS tz_change,
              {road_col} AS road_streak,
              g.home_score, g.away_score,
              g.home_team, g.away_team,
              g.home_sp_name, g.away_sp_name,
              {opp_sp_sql} AS opp_sp_name,
              {opp_throws_sql} AS opp_sp_throws
            {join_sql}
            WHERE {' AND '.join(where)}
            ORDER BY pg.gameday DESC
        """

        games = rows(conn, sql, tuple(params))
        for game in games:
            value = game.get("stat_value")
            game["hit"] = value is not None and float(value) > line

        missing_map: dict[str, dict[str, list[dict]]] = {}
        if games:
            game_ids = {g["game_id"] for g in games if g.get("game_id")}
            placeholders = ",".join("?" for _ in game_ids)
            missing_rows = rows(
                conn,
                f"""
                SELECT game_id, team, player_name, position, side,
                       pa_recent, ip_recent, status, injury
                FROM missing_regulars
                WHERE game_id IN ({placeholders})
                ORDER BY COALESCE(pa_recent, 0) + COALESCE(ip_recent, 0) DESC
                """,
                tuple(game_ids),
            )
            for row in missing_rows:
                missing_map.setdefault(row["game_id"], {}).setdefault(row["team"], []).append(row)

        for game in games:
            by_team = missing_map.get(game.get("game_id") or "", {})
            game["missing_teammates"] = by_team.get(game["team"], [])
            game["missing_opponents"] = by_team.get(game["opponent"], [])

        hits = sum(1 for g in games if g["hit"])
        values = [float(g["stat_value"]) for g in games if g["stat_value"] is not None]
        values_sorted = sorted(values)
        median = values_sorted[len(values_sorted) // 2] if values_sorted else None

        def _vs_box(hand: str) -> dict:
            subset = [g for g in games if g.get("opp_sp_throws") == hand]
            sub_hits = sum(1 for g in subset if g["hit"])
            sub_vals = [float(g["stat_value"]) for g in subset if g["stat_value"] is not None]
            return {
                "hand": hand,
                "sample_size": len(subset),
                "hits": sub_hits,
                "hit_rate": round(sub_hits / len(subset), 3) if subset else None,
                "mean": round(sum(sub_vals) / len(sub_vals), 2) if sub_vals else None,
            }

        return {
            "player": player,
            "stat": stat,
            "stat_label": STATS[stat],
            "line": line,
            "sample_size": len(games),
            "hits": hits,
            "hit_rate": round(hits / len(games), 3) if games else None,
            "mean": round(sum(values) / len(values), 2) if values else None,
            "median": median,
            "vs_lhp": _vs_box("L"),
            "vs_rhp": _vs_box("R"),
            "games": games,
        }
    finally:
        conn.close()


@router.get("/api/slate")
def slate(gameday: str | None = None):
    if not DB_PATH.exists():
        return {"slate": None, "days": [], "games": []}
    conn = connect()
    try:
        return get_slate(conn, gameday)
    finally:
        conn.close()


@router.get("/api/games/{game_id}/matchup")
def matchup(game_id: str):
    conn = connect()
    try:
        found = get_matchup(conn, game_id)
        if not found:
            raise HTTPException(404, "Game not found")
        return found
    finally:
        conn.close()
