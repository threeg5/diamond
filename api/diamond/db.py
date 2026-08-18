from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from diamond.config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS teams (
  team_id INTEGER PRIMARY KEY,
  abbr TEXT NOT NULL,
  name TEXT,
  league_id INTEGER,
  division_id INTEGER
);

CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  gameday TEXT,
  weekday TEXT,
  gametime TEXT,
  season_type TEXT,
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  home_score INTEGER,
  away_score INTEGER,
  result INTEGER,
  total INTEGER,
  roof TEXT,
  surface TEXT,
  surface_group TEXT,
  temp REAL,
  wind REAL,
  condition TEXT,
  day_night TEXT,
  home_rest INTEGER,
  away_rest INTEGER,
  home_ml_streak INTEGER,
  away_ml_streak INTEGER,
  home_rl_streak INTEGER,
  away_rl_streak INTEGER,
  stadium TEXT,
  stadium_id TEXT,
  location TEXT,
  div_game INTEGER,
  is_overseas INTEGER,
  is_night INTEGER,
  is_early_window INTEGER,
  is_altitude INTEGER,
  home_travel TEXT,
  away_travel TEXT,
  home_travel_miles REAL,
  away_travel_miles REAL,
  home_tz_change INTEGER,
  away_tz_change INTEGER,
  home_road_streak INTEGER,
  away_road_streak INTEGER,
  home_sp_id TEXT,
  home_sp_name TEXT,
  away_sp_id TEXT,
  away_sp_name TEXT,
  elevation REAL
);

CREATE INDEX IF NOT EXISTS idx_games_gameday ON games(gameday);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season, season_type);
CREATE INDEX IF NOT EXISTS idx_games_teams ON games(home_team, away_team);

CREATE TABLE IF NOT EXISTS players (
  player_id TEXT PRIMARY KEY,
  player_name TEXT NOT NULL,
  position TEXT,
  latest_team TEXT,
  throws TEXT,
  bats TEXT
);

CREATE INDEX IF NOT EXISTS idx_players_name ON players(player_name);

CREATE TABLE IF NOT EXISTS player_games (
  player_id TEXT NOT NULL,
  player_name TEXT,
  position TEXT,
  team TEXT,
  opponent TEXT,
  season INTEGER NOT NULL,
  gameday TEXT,
  season_type TEXT,
  game_id TEXT,
  is_home INTEGER,
  hits REAL,
  home_runs REAL,
  rbi REAL,
  runs REAL,
  doubles REAL,
  triples REAL,
  stolen_bases REAL,
  total_bases REAL,
  walks REAL,
  strikeouts REAL,
  at_bats REAL,
  plate_appearances REAL,
  pitching_strikeouts REAL,
  pitching_walks REAL,
  earned_runs REAL,
  hits_allowed REAL,
  innings_pitched REAL,
  pitcher_outs REAL,
  pitches_thrown REAL,
  batters_faced REAL,
  home_runs_allowed REAL,
  games_started REAL,
  PRIMARY KEY (player_id, game_id)
);

CREATE INDEX IF NOT EXISTS idx_pg_game ON player_games(game_id);
CREATE INDEX IF NOT EXISTS idx_pg_name ON player_games(player_name);
CREATE INDEX IF NOT EXISTS idx_pg_team_day ON player_games(team, season, gameday);

CREATE TABLE IF NOT EXISTS team_games (
  season INTEGER NOT NULL,
  gameday TEXT,
  season_type TEXT,
  game_id TEXT,
  team TEXT NOT NULL,
  opponent TEXT,
  is_home INTEGER,
  runs REAL,
  hits REAL,
  home_runs REAL,
  walks REAL,
  strikeouts REAL,
  doubles REAL,
  stolen_bases REAL,
  earned_runs REAL,
  hits_allowed REAL,
  pitching_strikeouts REAL,
  pitching_walks REAL,
  innings_pitched REAL,
  home_runs_allowed REAL,
  PRIMARY KEY (game_id, team)
);

CREATE INDEX IF NOT EXISTS idx_tg_team ON team_games(team, season, gameday);
CREATE INDEX IF NOT EXISTS idx_tg_game ON team_games(game_id);

CREATE TABLE IF NOT EXISTS missing_regulars (
  game_id TEXT NOT NULL,
  gameday TEXT,
  season INTEGER,
  team TEXT,
  player_id TEXT,
  player_name TEXT,
  position TEXT,
  side TEXT,
  pa_recent REAL,
  ip_recent REAL,
  status TEXT,
  injury TEXT,
  PRIMARY KEY (game_id, team, player_id)
);

CREATE INDEX IF NOT EXISTS idx_miss_day_team ON missing_regulars(gameday, team);
"""


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS missing_regulars;
        DROP TABLE IF EXISTS team_games;
        DROP TABLE IF EXISTS player_games;
        DROP TABLE IF EXISTS players;
        DROP TABLE IF EXISTS games;
        DROP TABLE IF EXISTS teams;
        DROP TABLE IF EXISTS meta;
        """
    )
    init_db(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, decl: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _ensure_column(conn, "players", "throws", "TEXT")
    _ensure_column(conn, "players", "bats", "TEXT")
    conn.commit()


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
