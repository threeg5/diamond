const API = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001").replace(
  /\/$/,
  "",
);

export type PlayerHit = {
  player_id: string;
  player_name: string;
  position: string | null;
  latest_team: string | null;
  throws?: string | null;
  bats?: string | null;
};

export type HandSplit = {
  games?: number | null;
  innings?: string | number | null;
  strikeouts?: number | null;
  walks?: number | null;
  hits?: number | null;
  home_runs?: number | null;
  era?: number | null;
  whip?: number | null;
  k9?: number | null;
  avg?: string | number | null;
  ops?: string | number | null;
  obp?: string | number | null;
  slg?: string | number | null;
  pa?: number | null;
  season?: number | string | null;
};

export type PlayerSummary = PlayerHit & {
  default_stat: string;
  default_line: number;
  stats: Record<string, string>;
  hand_splits?: {
    group: "hitting" | "pitching";
    season: number;
    left_label: string;
    right_label: string;
    vs_left: HandSplit | null;
    vs_right: HandSplit | null;
  } | null;
};

export type MissingRegular = {
  player_name: string;
  position: string | null;
  side: string | null;
  pa_recent: number | null;
  ip_recent: number | null;
  status: string | null;
  injury: string | null;
};

export type PropGame = {
  season: number;
  gameday: string | null;
  game_id: string;
  team: string;
  opponent: string;
  is_home: number | null;
  stat_value: number | null;
  hit: boolean;
  roof: string | null;
  temp: number | null;
  wind: number | null;
  rest_days: number | null;
  ml_streak: number | null;
  rl_streak: number | null;
  travel: string | null;
  travel_miles: number | null;
  tz_change: number | null;
  road_streak: number | null;
  div_game: number | null;
  is_night: number | null;
  is_altitude: number | null;
  is_overseas: number | null;
  surface_group: string | null;
  stadium: string | null;
  day_night: string | null;
  home_score: number | null;
  away_score: number | null;
  home_sp_name: string | null;
  away_sp_name: string | null;
  opp_sp_name: string | null;
  opp_sp_throws: string | null;
  missing_teammates: MissingRegular[];
  missing_opponents: MissingRegular[];
};

export type HandBox = {
  hand: string;
  sample_size: number;
  hits: number;
  hit_rate: number | null;
  mean: number | null;
};

export type PropResult = {
  player: PlayerHit;
  stat: string;
  stat_label: string;
  line: number;
  sample_size: number;
  hits: number;
  hit_rate: number | null;
  mean: number | null;
  median: number | null;
  vs_lhp?: HandBox;
  vs_rhp?: HandBox;
  games: PropGame[];
};

export type Meta = {
  ingested: boolean;
  stats: Record<string, string>;
  ingested_at?: string;
  seasons?: string;
  games?: number;
  players?: number;
  player_games?: number;
  team_games?: number;
  missing_regulars?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export function fetchMeta() {
  return getJson<Meta>("/api/meta");
}

export function searchPlayers(q: string) {
  return getJson<PlayerHit[]>(`/api/players/search?q=${encodeURIComponent(q)}`);
}

export function fetchPlayer(id: string) {
  return getJson<PlayerSummary>(`/api/players/${encodeURIComponent(id)}`);
}

export type PropQuery = {
  stat: string;
  line: number;
  home: "" | "1" | "0";
  minRest: string;
  maxWind: string;
  roof: "" | "outdoors" | "indoor";
  mlStreak: "" | "win" | "loss";
  rlStreak: "" | "win" | "loss";
  travel: "" | "none" | "short" | "long" | "overseas";
  divGame: "" | "1" | "0";
  night: "" | "1" | "0";
  extraRest: "" | "1";
  surface: "" | "grass" | "turf";
  altitude: "" | "1";
  westCoastEarly: "" | "1";
  consecRoad: "" | "1";
  oppHand: "" | "L" | "R";
};

export function fetchProp(playerId: string, q: PropQuery) {
  const params = new URLSearchParams({
    stat: q.stat,
    line: String(q.line),
  });
  if (q.home) params.set("home", q.home);
  if (q.minRest) params.set("min_rest", q.minRest);
  if (q.maxWind) params.set("max_wind", q.maxWind);
  if (q.roof) params.set("roof", q.roof);
  if (q.mlStreak) params.set("ml_streak", q.mlStreak);
  if (q.rlStreak) params.set("rl_streak", q.rlStreak);
  if (q.travel) params.set("travel", q.travel);
  if (q.divGame) params.set("div_game", q.divGame);
  if (q.night) params.set("night", q.night);
  if (q.extraRest) params.set("extra_rest", q.extraRest);
  if (q.surface) params.set("surface", q.surface);
  if (q.altitude) params.set("altitude", q.altitude);
  if (q.westCoastEarly) params.set("west_coast_early", q.westCoastEarly);
  if (q.consecRoad) params.set("consec_road", q.consecRoad);
  if (q.oppHand) params.set("opp_hand", q.oppHand);
  return getJson<PropResult>(
    `/api/players/${encodeURIComponent(playerId)}/prop?${params}`,
  );
}

export type SlateDay = {
  gameday: string;
  season: number;
  games: number;
  unplayed: number | null;
  label: string;
};

export type SlateGame = {
  game_id: string;
  season: number;
  gameday: string | null;
  weekday: string | null;
  gametime: string | null;
  season_type: string | null;
  home_team: string;
  away_team: string;
  home_name: string;
  away_name: string;
  home_score: number | null;
  away_score: number | null;
  played: boolean;
  roof: string | null;
  surface_group: string | null;
  temp: number | null;
  wind: number | null;
  stadium: string | null;
  location: string | null;
  home_rest: number | null;
  away_rest: number | null;
  div_game: number | null;
  is_night: number | null;
  is_altitude: number | null;
  is_overseas: number | null;
  home_travel: string | null;
  away_travel: string | null;
  home_travel_miles: number | null;
  away_travel_miles: number | null;
  home_tz_change: number | null;
  away_tz_change: number | null;
  home_sp_name: string | null;
  away_sp_name: string | null;
  home_sp_throws: string | null;
  away_sp_throws: string | null;
  day_night: string | null;
  neutral: boolean;
};

export type SlateResponse = {
  slate: SlateDay | null;
  days: SlateDay[];
  games: SlateGame[];
};

export type TeamProfile = {
  games: number;
  from_gameday: string | null;
  to_gameday: string | null;
  from_season: number | null;
  to_season: number | null;
  rpg: number | null;
  rapg: number | null;
  margin: number | null;
  hits: number | null;
  home_runs: number | null;
  hits_allowed: number | null;
  home_runs_allowed: number | null;
  era: number | null;
  k9: number | null;
  walks: number | null;
  strikeouts: number | null;
};

export type TeamCard = {
  team: string;
  name: string;
  is_home: number;
  overall: TeamProfile | null;
  recent: TeamProfile | null;
  role: TeamProfile | null;
  missing: MissingRegular[];
};

export type ExpectedScore = {
  away_runs: number;
  home_runs: number;
  total: number;
  margin: number;
  hfa: number | null;
  league_rpg: number | null;
  method: string;
  recent: {
    away_runs: number;
    home_runs: number;
    total: number;
    margin: number;
  } | null;
};

export type Matchup = {
  game: SlateGame;
  away: TeamCard;
  home: TeamCard;
  environment: {
    league_rpg: number | null;
    hfa: number | null;
    games: number;
  };
  expected: ExpectedScore | null;
  lookback_games: number;
  recent_games: number;
};

export function fetchSlate(gameday?: string) {
  const params = new URLSearchParams();
  if (gameday) params.set("gameday", gameday);
  const qs = params.toString();
  return getJson<SlateResponse>(`/api/slate${qs ? `?${qs}` : ""}`);
}

export function fetchMatchup(gameId: string) {
  return getJson<Matchup>(`/api/games/${encodeURIComponent(gameId)}/matchup`);
}

const TPE_API = (
  import.meta.env.DEV
    ? "/tpe-api"
    : (import.meta.env.VITE_TPE_API_URL ?? "https://wagechecker-api.onrender.com")
).replace(/\/$/, "");

export type Tier = "amateur" | "player" | "owner";

export type LastSearch = {
  desk?: string;
  player_id?: string;
  player_name?: string;
  position?: string | null;
  latest_team?: string | null;
  stat?: string;
  line?: number;
};

export type TpeUser = {
  id: string;
  email: string;
  display_name: string;
  tier: Tier;
  last_desk: string | null;
  last_search: LastSearch | null;
  created_at: string;
};

const SESSION_KEY = "tpe_session";
const SESSION_MAX_AGE = 30 * 24 * 60 * 60;
const TPE_HOME = import.meta.env.DEV
  ? "http://127.0.0.1:5175"
  : "https://theprofitengineer.com";

export function tpeAccountUrl(hash: "signin" | "account" | "book" = "account") {
  return `${TPE_HOME}/#${hash}`;
}

function readCookie(name: string) {
  const prefix = `${name}=`;
  for (const part of document.cookie.split("; ")) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length));
  }
  return null;
}

export function readSessionToken() {
  return localStorage.getItem(SESSION_KEY) || readCookie(SESSION_KEY);
}

export function writeSessionToken(token: string | null) {
  if (token) {
    localStorage.setItem(SESSION_KEY, token);
    document.cookie = `${SESSION_KEY}=${encodeURIComponent(token)}; Path=/; Max-Age=${SESSION_MAX_AGE}; SameSite=Lax`;
  } else {
    localStorage.removeItem(SESSION_KEY);
    document.cookie = `${SESSION_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
}

async function authError(res: Response) {
  const text = await res.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* use raw text */
  }
  return text || res.statusText;
}

async function authJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = readSessionToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${TPE_API}${path}`, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401) writeSessionToken(null);
    throw new Error(await authError(res));
  }
  return res.json() as Promise<T>;
}

export function claimHandedSession() {
  const params = new URLSearchParams(window.location.search);
  const handed = params.get("tpe");
  if (!handed) return;
  writeSessionToken(handed);
  params.delete("tpe");
  const search = params.toString();
  history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`);
}

export async function login(input: { email: string; password: string }) {
  const data = await authJson<{ token: string; user: TpeUser }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  writeSessionToken(data.token);
  return data.user;
}

export async function fetchMe() {
  if (!readSessionToken()) return null;
  try {
    return await authJson<TpeUser>("/api/auth/me");
  } catch {
    return null;
  }
}

export async function patchMe(input: {
  displayName?: string;
  lastDesk?: string;
  lastSearch?: LastSearch | null;
}) {
  return authJson<TpeUser>("/api/auth/me", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export type Follow = {
  id: string;
  kind: "athlete" | "team";
  desk: string;
  subject_id: string;
  subject_name: string;
};

export async function lookupFollow(kind: "athlete" | "team", desk: string, subjectId: string) {
  if (!readSessionToken()) return null;
  try {
    const found = await authJson<Follow | Record<string, never>>(
      `/api/book/follows/lookup?kind=${kind}&desk=${desk}&subject_id=${encodeURIComponent(subjectId)}`,
    );
    return found.id ? (found as Follow) : null;
  } catch {
    return null;
  }
}

export function addFollow(input: {
  kind: "athlete" | "team";
  desk: string;
  subjectId: string;
  subjectName: string;
}) {
  return authJson<Follow>("/api/book/follows", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function removeFollow(id: string) {
  return authJson(`/api/book/follows/${id}`, { method: "DELETE" });
}

export function addSpot(input: {
  desk: string;
  label: string;
  payload?: LastSearch & Record<string, unknown>;
}) {
  return authJson("/api/book/spots", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function addWager(input: {
  desk: string;
  gameLabel: string;
  market: string;
  side: string;
  line?: number | null;
  placedAt?: string;
  note?: string;
}) {
  return authJson("/api/book/wagers", {
    method: "POST",
    body: JSON.stringify({
      ...input,
      placedAt: input.placedAt ?? new Date().toISOString().slice(0, 10),
    }),
  });
}
