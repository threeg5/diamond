from __future__ import annotations

from diamond.config import ingest_years
from diamond.mlb import get_json, people_url


def is_pitcher(position: str | None) -> bool:
    return (position or "").upper() in {"P", "SP", "RP"}


def _hand_code(block: dict | None) -> str | None:
    code = (block or {}).get("code")
    if code in {"L", "R", "S"}:
        return code
    return None


def enrich_hands(conn) -> int:
    """Fill players.throws / players.bats from the people API (starters + roster)."""
    names: dict[str, str] = {}
    for home_id, home_name, away_id, away_name in conn.execute(
        "SELECT home_sp_id, home_sp_name, away_sp_id, away_sp_name FROM games"
    ):
        if home_id:
            names[str(home_id)] = home_name or names.get(str(home_id)) or "Unknown"
        if away_id:
            names[str(away_id)] = away_name or names.get(str(away_id)) or "Unknown"
    for pid, name in conn.execute("SELECT player_id, player_name FROM players"):
        if pid:
            names.setdefault(str(pid), name or "Unknown")

    for pid, name in names.items():
        conn.execute(
            """
            INSERT INTO players (player_id, player_name, position, latest_team)
            VALUES (?, ?, 'P', NULL)
            ON CONFLICT(player_id) DO NOTHING
            """,
            (pid, name),
        )
    conn.commit()

    missing = [
        pid
        for (pid,) in conn.execute(
            "SELECT player_id FROM players WHERE throws IS NULL OR throws = ''"
        )
    ]
    if not missing:
        return 0

    updated = 0
    batch = 80
    for i in range(0, len(missing), batch):
        chunk = missing[i : i + batch]
        try:
            payload = get_json(people_url(chunk))
        except Exception as exc:
            print(f"  hands batch skip: {exc}", flush=True)
            continue
        for person in payload.get("people") or []:
            pid = str(person.get("id") or "")
            if not pid:
                continue
            throws = _hand_code(person.get("pitchHand"))
            bats = _hand_code(person.get("batSide"))
            name = person.get("fullName")
            conn.execute(
                """
                UPDATE players
                SET throws = COALESCE(?, throws),
                    bats = COALESCE(?, bats),
                    player_name = COALESCE(?, player_name)
                WHERE player_id = ?
                """,
                (throws, bats, name, pid),
            )
            updated += 1
        conn.commit()
        print(f"  hands {min(i + batch, len(missing))}/{len(missing)}", flush=True)
    return updated


def season_hand_splits(player_id: str, position: str | None) -> dict | None:
    years = ingest_years()
    season = years[-1] if years else 2026
    group = "pitching" if is_pitcher(position) else "hitting"
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats"
        f"?stats=statSplits&group={group}&sitCodes=vl,vr&season={season}"
    )
    try:
        payload = get_json(url)
    except Exception:
        return None
    vs_left = vs_right = None
    for block in payload.get("stats") or []:
        for split in block.get("splits") or []:
            code = ((split.get("split") or {}).get("code") or "").lower()
            row = _split_row(split.get("stat") or {}, group)
            row["season"] = split.get("season") or season
            if code == "vl":
                vs_left = row
            elif code == "vr":
                vs_right = row
    if not vs_left and not vs_right:
        return None
    return {
        "group": group,
        "season": season,
        "vs_left": vs_left,
        "vs_right": vs_right,
        "left_label": "vs LHB" if group == "pitching" else "vs LHP",
        "right_label": "vs RHB" if group == "pitching" else "vs RHP",
    }


def _split_row(stat: dict, group: str) -> dict:
    if group == "pitching":
        return {
            "games": stat.get("gamesPitched") or stat.get("gamesPlayed"),
            "innings": stat.get("inningsPitched"),
            "strikeouts": _num(stat.get("strikeOuts")),
            "walks": _num(stat.get("baseOnBalls")),
            "hits": _num(stat.get("hits")),
            "home_runs": _num(stat.get("homeRuns")),
            "era": _num(stat.get("era")),
            "whip": _num(stat.get("whip")),
            "k9": _num(stat.get("strikeoutsPer9Inn")),
            "avg": stat.get("avg"),
        }
    return {
        "games": stat.get("gamesPlayed"),
        "pa": _num(stat.get("plateAppearances")),
        "hits": _num(stat.get("hits")),
        "home_runs": _num(stat.get("homeRuns")),
        "strikeouts": _num(stat.get("strikeOuts")),
        "avg": stat.get("avg"),
        "ops": stat.get("ops"),
        "obp": stat.get("obp"),
        "slg": stat.get("slg"),
    }


def _num(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
