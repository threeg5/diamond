from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Home park approx lat, lon, timezone hours from UTC (standard time).
TEAM_HOMES: dict[str, tuple[float, float, int]] = {
    "AZ": (33.445, -112.067, -7),
    "ATH": (38.580, -121.514, -8),
    "ATL": (33.891, -84.468, -5),
    "BAL": (39.284, -76.622, -5),
    "BOS": (42.346, -71.098, -5),
    "CHC": (41.948, -87.656, -6),
    "CIN": (39.097, -84.507, -5),
    "CLE": (41.496, -81.685, -5),
    "COL": (39.756, -104.994, -7),
    "CWS": (41.830, -87.634, -6),
    "DET": (42.339, -83.049, -5),
    "HOU": (29.757, -95.355, -6),
    "KC": (39.051, -94.480, -6),
    "LAA": (33.800, -117.883, -8),
    "LAD": (34.074, -118.240, -8),
    "MIA": (25.778, -80.220, -5),
    "MIL": (43.028, -87.971, -6),
    "MIN": (44.982, -93.278, -6),
    "NYM": (40.757, -73.846, -5),
    "NYY": (40.829, -73.926, -5),
    "PHI": (39.906, -75.167, -5),
    "PIT": (40.447, -80.006, -5),
    "SD": (32.708, -117.157, -8),
    "SEA": (47.591, -122.333, -8),
    "SF": (37.778, -122.389, -8),
    "STL": (38.623, -90.193, -6),
    "TB": (27.768, -82.653, -5),
    "TEX": (32.747, -97.084, -6),
    "TOR": (43.641, -79.389, -5),
    "WSH": (38.873, -77.007, -5),
}

PACIFIC_TEAMS = {"ATH", "LAA", "LAD", "SD", "SEA", "SF"}
ALTITUDE_TEAMS = {"COL"}
SHORT_MILES = 700.0
ET = ZoneInfo("America/New_York")

TEAM_NAMES: dict[str, str] = {
    "AZ": "Arizona Diamondbacks",
    "ATH": "Athletics",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "CWS": "Chicago White Sox",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
}

OVERSEAS_HINTS = (
    "london",
    "mexico",
    "tokyo",
    "seoul",
    "sydney",
    "melbourne",
    "san juan",
    "puerto rico",
    "estadio",
    "azteca",
)


def team_name(abbr: str | None) -> str:
    if not abbr:
        return "—"
    return TEAM_NAMES.get(abbr, abbr)


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _norm(text) -> str:
    if text is None:
        return ""
    if isinstance(text, float) and math.isnan(text):
        return ""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def parse_wind(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(text))
    return float(match.group(1)) if match else None


def parse_temp(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_roof(roof: str | None) -> str | None:
    text = _norm(roof)
    if not text:
        return None
    if text in {"dome", "closed", "indoor"}:
        return "dome"
    if "retractable" in text:
        return "retractable"
    if text in {"open", "outdoors", "outdoor"}:
        return "outdoors"
    return text


def surface_group(surface: str | None) -> str | None:
    text = _norm(surface)
    if not text:
        return None
    if "grass" in text:
        return "grass"
    if any(token in text for token in ("turf", "artificial", "fieldturf")):
        return "turf"
    return text


def is_overseas_venue(stadium: str | None, country: str | None) -> int:
    if country and str(country).upper() not in {"USA", "US", "UNITED STATES", "CANADA", "CAN"}:
        return 1
    name = _norm(stadium)
    return int(any(hint in name for hint in OVERSEAS_HINTS))


def classify_travel(miles: float, is_overseas: bool, same_city: bool) -> str:
    if is_overseas:
        return "overseas"
    if same_city or miles < 40:
        return "none"
    if miles < SHORT_MILES:
        return "short"
    return "long"


def team_travel_from_origin(
    origin: tuple[float, float, int] | None,
    venue_xy: tuple[float, float],
    venue_tz: int,
    is_overseas: bool,
    at_true_home: bool,
) -> dict:
    if origin is None:
        miles = 0.0 if at_true_home else None
        tz_change = 0
    else:
        miles = 0.0 if at_true_home else round(haversine_miles((origin[0], origin[1]), venue_xy), 0)
        tz_change = 0 if at_true_home else abs(venue_tz - origin[2])
    return {
        "travel": classify_travel(miles or 0.0, is_overseas, at_true_home),
        "travel_miles": miles,
        "tz_change": tz_change,
        "is_overseas": int(is_overseas),
    }


def hop_travel(
    prev_xy: tuple[float, float] | None,
    prev_tz: int | None,
    venue_xy: tuple[float, float],
    venue_tz: int,
    is_overseas: bool,
) -> dict:
    if prev_xy is None:
        return {"travel": "none", "travel_miles": 0.0, "tz_change": 0, "is_overseas": int(is_overseas)}
    miles = round(haversine_miles(prev_xy, venue_xy), 0)
    tz_change = abs(venue_tz - (prev_tz or venue_tz))
    same_city = miles < 40
    return {
        "travel": classify_travel(miles, is_overseas, same_city),
        "travel_miles": miles,
        "tz_change": tz_change,
        "is_overseas": int(is_overseas),
    }


def is_night_game(day_night: str | None) -> int:
    return int(_norm(day_night) == "night")


def hour_et(game_date_iso: str | None) -> int | None:
    if not game_date_iso:
        return None
    text = str(game_date_iso).replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(ET).hour


def is_early_window(day_night: str | None, game_date_iso: str | None) -> int:
    if _norm(day_night) == "night":
        return 0
    hour = hour_et(game_date_iso)
    return int(hour is not None and hour < 16)


def is_altitude_game(home_team: str, elevation: float | None, stadium: str | None) -> int:
    if home_team in ALTITUDE_TEAMS:
        return 1
    if elevation is not None and elevation >= 3000:
        return 1
    name = _norm(stadium)
    if "coors" in name or "denver" in name:
        return 1
    return 0
