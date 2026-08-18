import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchPlayer,
  fetchProp,
  searchPlayers,
  type Meta,
  type MissingRegular,
  type PlayerHit,
  type PlayerSummary,
  type PropQuery,
  type PropResult,
} from "./api";

const EMPTY_QUERY: PropQuery = {
  stat: "hits",
  line: 0.5,
  home: "",
  minRest: "",
  maxWind: "",
  roof: "",
  mlStreak: "",
  rlStreak: "",
  travel: "",
  divGame: "",
  night: "",
  extraRest: "",
  surface: "",
  altitude: "",
  westCoastEarly: "",
  consecRoad: "",
};

function streakLabel(value: number | null) {
  if (value == null || value === 0) return "—";
  const n = Math.abs(value);
  return value > 0 ? `${n}W` : `${n}L`;
}

function formatMissing(rows: MissingRegular[]) {
  if (!rows.length) return "—";
  return rows
    .slice(0, 4)
    .map((row) => {
      const pos = row.position ? `${row.position} ` : "";
      const injury = row.injury ? ` · ${row.injury}` : "";
      return `${pos}${row.player_name} ${row.status ?? "IL"}${injury}`;
    })
    .join(" · ");
}

function pct(value: number | null) {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

function travelLabel(game: {
  travel: string | null;
  travel_miles: number | null;
  tz_change: number | null;
}) {
  if (!game.travel) return "—";
  const bits = [game.travel];
  if (game.travel !== "none" && game.travel_miles != null) {
    bits.push(`${Math.round(game.travel_miles)}mi`);
  }
  if (game.tz_change) bits.push(`${game.tz_change}tz`);
  return bits.join(" · ");
}

function spotTags(game: PropResult["games"][number]) {
  const tags = [];
  if (game.div_game) tags.push("Div");
  if (game.is_night) tags.push("Night");
  if (game.is_altitude) tags.push("Coors");
  if (game.surface_group) tags.push(game.surface_group);
  if (!tags.length) return "—";
  return tags.map((tag) => (
    <span className="chip" key={tag}>
      {tag}
    </span>
  ));
}

export default function PlayerDesk({ meta }: { meta: Meta | null }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PlayerHit[]>([]);
  const [player, setPlayer] = useState<PlayerSummary | null>(null);
  const [filters, setFilters] = useState<PropQuery>(EMPTY_QUERY);
  const [result, setResult] = useState<PropResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits([]);
      return;
    }
    const handle = window.setTimeout(() => {
      searchPlayers(query.trim())
        .then(setHits)
        .catch(() => setHits([]));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) {
        setHits([]);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function selectPlayer(hit: PlayerHit) {
    setQuery(hit.player_name);
    setHits([]);
    setError(null);
    const summary = await fetchPlayer(hit.player_id);
    setPlayer(summary);
    const next = {
      ...EMPTY_QUERY,
      stat: summary.default_stat,
      line: summary.default_line,
    };
    setFilters(next);
    setLoading(true);
    try {
      setResult(await fetchProp(summary.player_id, next));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!player) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await fetchProp(player.player_id, filters));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  }

  const stats = player?.stats ?? meta?.stats ?? {};
  const sampleNote = useMemo(() => {
    if (!result) return null;
    if (result.sample_size < 12) return "Small sample — treat as a sketch, not a rate.";
    if (result.sample_size < 30) return "Modest sample — splits can swing a lot.";
    return "Sample is large enough to browse; still not a future guarantee.";
  }, [result]);

  return (
    <>
      <div className="search" ref={boxRef}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search a player — Ohtani, Judge, Skubal…"
          autoFocus
        />
        {hits.length > 0 && (
          <ul className="suggest">
            {hits.map((hit) => (
              <li key={hit.player_id}>
                <button type="button" onClick={() => selectPlayer(hit)}>
                  <strong>{hit.player_name}</strong>
                  <span>
                    {hit.position} · {hit.latest_team}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {player && (
        <form className="filters" onSubmit={onSubmit}>
          <label>
            Stat
            <select
              value={filters.stat}
              onChange={(e) => setFilters({ ...filters, stat: e.target.value })}
            >
              {Object.entries(stats).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Line
            <input
              type="number"
              step="0.5"
              value={filters.line}
              onChange={(e) =>
                setFilters({ ...filters, line: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Home / away
            <select
              value={filters.home}
              onChange={(e) =>
                setFilters({ ...filters, home: e.target.value as PropQuery["home"] })
              }
            >
              <option value="">All</option>
              <option value="1">Home</option>
              <option value="0">Away</option>
            </select>
          </label>
          <label>
            Extra rest
            <select
              value={filters.extraRest}
              onChange={(e) => setFilters({ ...filters, extraRest: e.target.value as PropQuery["extraRest"] })}
            >
              <option value="">Any</option>
              <option value="1">Off day (2+ rest)</option>
            </select>
          </label>
          <label>
            Roof
            <select
              value={filters.roof}
              onChange={(e) =>
                setFilters({ ...filters, roof: e.target.value as PropQuery["roof"] })
              }
            >
              <option value="">Any</option>
              <option value="outdoors">Outdoors</option>
              <option value="indoor">Dome / roof</option>
            </select>
          </label>
          <label>
            Max wind
            <select
              value={filters.maxWind}
              onChange={(e) => setFilters({ ...filters, maxWind: e.target.value })}
            >
              <option value="">Any</option>
              <option value="8">≤ 8 mph</option>
              <option value="12">≤ 12 mph</option>
            </select>
          </label>
          <label>
            W/L streak in
            <select
              value={filters.mlStreak}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  mlStreak: e.target.value as PropQuery["mlStreak"],
                })
              }
            >
              <option value="">Any</option>
              <option value="win">2+ wins</option>
              <option value="loss">2+ losses</option>
            </select>
          </label>
          <label>
            RL -1.5 streak in
            <select
              value={filters.rlStreak}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  rlStreak: e.target.value as PropQuery["rlStreak"],
                })
              }
            >
              <option value="">Any</option>
              <option value="win">2+ covers</option>
              <option value="loss">2+ RL losses</option>
            </select>
          </label>
          <label>
            Travel hop
            <select
              value={filters.travel}
              onChange={(e) =>
                setFilters({ ...filters, travel: e.target.value as PropQuery["travel"] })
              }
            >
              <option value="">Any</option>
              <option value="none">None (same city)</option>
              <option value="short">Short (&lt;700 mi)</option>
              <option value="long">Long</option>
              <option value="overseas">Overseas</option>
            </select>
          </label>
          <label>
            Division
            <select
              value={filters.divGame}
              onChange={(e) =>
                setFilters({ ...filters, divGame: e.target.value as PropQuery["divGame"] })
              }
            >
              <option value="">Any</option>
              <option value="1">Division</option>
              <option value="0">Non-division</option>
            </select>
          </label>
          <label>
            Window
            <select
              value={filters.night}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  night: e.target.value as PropQuery["night"],
                })
              }
            >
              <option value="">Any</option>
              <option value="1">Night</option>
              <option value="0">Day</option>
            </select>
          </label>
          <label>
            Surface
            <select
              value={filters.surface}
              onChange={(e) =>
                setFilters({ ...filters, surface: e.target.value as PropQuery["surface"] })
              }
            >
              <option value="">Any</option>
              <option value="grass">Grass</option>
              <option value="turf">Turf</option>
            </select>
          </label>
          <label>
            Altitude
            <select
              value={filters.altitude}
              onChange={(e) =>
                setFilters({
                  ...filters,
                  altitude: e.target.value as PropQuery["altitude"],
                })
              }
            >
              <option value="">Any</option>
              <option value="1">Coors / altitude</option>
            </select>
          </label>
          <label>
            Extra
            <select
              value={filters.westCoastEarly ? "early" : filters.consecRoad ? "road" : ""}
              onChange={(e) => {
                const value = e.target.value;
                setFilters({
                  ...filters,
                  westCoastEarly: value === "early" ? "1" : "",
                  consecRoad: value === "road" ? "1" : "",
                });
              }}
            >
              <option value="">None</option>
              <option value="early">West Coast day game</option>
              <option value="road">2nd+ straight road</option>
            </select>
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Crunching…" : "Run"}
          </button>
        </form>
      )}

      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <section className="hero">
            <div className="scoreboard">
              <p className="kicker">
                {result.player.player_name} · {result.stat_label} over {result.line}
              </p>
              <p className="rate">{pct(result.hit_rate)}</p>
              <p className="sub">historical hit rate in matching games</p>
              {sampleNote && <p className="note">{sampleNote}</p>}
            </div>
            <div className="hero-side">
              <p className="kicker">Box</p>
              <div className="stat-pills">
                <span className="pill">
                  Hits <b>{result.hits}</b>
                </span>
                <span className="pill">
                  Games <b>{result.sample_size}</b>
                </span>
                <span className="pill">
                  Mean <b>{result.mean ?? "—"}</b>
                </span>
                <span className="pill">
                  Median <b>{result.median ?? "—"}</b>
                </span>
              </div>
            </div>
          </section>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Spot</th>
                  <th>Travel</th>
                  <th>Rest</th>
                  <th>Park / wx</th>
                  <th>Context</th>
                  <th>W/L</th>
                  <th>RL</th>
                  <th>{result.stat_label}</th>
                  <th>Teammates IL</th>
                  <th>Opponents IL</th>
                </tr>
              </thead>
              <tbody>
                {result.games.map((game) => (
                  <tr key={`${game.game_id}-${game.opponent}`} className={game.hit ? "hit" : "miss"}>
                    <td>
                      {game.gameday ?? String(game.season)}
                      <small>{game.season}</small>
                    </td>
                    <td>
                      {game.is_home === 1 ? "vs" : "@"} {game.opponent}
                    </td>
                    <td>{travelLabel(game)}</td>
                    <td>{game.rest_days ?? "—"}d</td>
                    <td>
                      {game.roof ?? "—"}
                      {game.wind != null ? ` · ${game.wind}mph` : ""}
                      {game.temp != null ? ` · ${game.temp}°` : ""}
                    </td>
                    <td className="missing">{spotTags(game)}</td>
                    <td>{streakLabel(game.ml_streak)}</td>
                    <td>{streakLabel(game.rl_streak)}</td>
                    <td className="stat">
                      {game.stat_value ?? "—"}
                      <span className={game.hit ? "chip hit" : "chip miss"}>
                        {game.hit ? "over" : "under"}
                      </span>
                    </td>
                    <td className="missing">{formatMissing(game.missing_teammates)}</td>
                    <td className="missing">{formatMissing(game.missing_opponents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!player && (
        <section className="empty">
          <h2>Call a player</h2>
          <p>
            Search a batter or pitcher, set a line, then see how often it hit in
            comparable games. Travel, rest, park, weather, and injured-list
            regulars sit on each row so you can judge the spot — this desk does
            not pick the bet.
          </p>
        </section>
      )}
    </>
  );
}
