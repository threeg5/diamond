import { useEffect, useState } from "react";
import {
  fetchMatchup,
  fetchSlate,
  type Matchup,
  type MissingRegular,
  type SlateDay,
  type SlateGame,
  type SlateResponse,
  type TeamCard,
  type TeamProfile,
  type TpeUser,
  addFollow,
  addWager,
  lookupFollow,
  removeFollow,
  tpeAccountUrl,
} from "./api";

function num(value: number | null | undefined, digits = 1) {
  if (value == null) return "—";
  return value.toFixed(digits);
}

function signed(value: number | null | undefined, digits = 1) {
  if (value == null) return "—";
  const formatted = value.toFixed(digits);
  return value > 0 ? `+${formatted}` : formatted;
}

function spLabel(name: string | null | undefined, throws?: string | null) {
  if (!name) return "TBD";
  const last = name.split(" ").slice(-1)[0];
  return throws === "L" || throws === "R" ? `${last} (${throws})` : last;
}

function firstPitch(game: SlateGame) {
  const day = game.weekday || game.gameday || "";
  const time = game.gametime ? String(game.gametime).slice(0, 5) : "";
  const window = game.day_night ? String(game.day_night) : "";
  return [day, time, window].filter(Boolean).join(" · ") || "TBD";
}

function roofLabel(game: SlateGame) {
  const roof = (game.roof || "").toLowerCase();
  if (roof.includes("dome") || roof === "closed") return "Dome";
  if (roof === "retractable") return "Retractable";
  if (roof === "outdoors" || roof === "open") return "Outdoors";
  return game.roof || "—";
}

function formatMissing(rows: MissingRegular[]) {
  if (!rows.length) return "None listed";
  return rows
    .slice(0, 5)
    .map((row) => {
      const pos = row.position ? `${row.position} ` : "";
      const injury = row.injury ? ` · ${row.injury}` : "";
      return `${pos}${row.player_name} ${row.status ?? "IL"}${injury}`;
    })
    .join(" · ");
}

function sampleRange(profile: TeamProfile | null) {
  if (!profile) return "No completed games yet";
  return `${profile.games} REG games · ${profile.from_gameday}–${profile.to_gameday}`;
}

function expectedLabel(matchup: Matchup) {
  const expected = matchup.expected;
  if (!expected) return "Need more completed games to build an expected score.";
  if (expected.margin > 0.3) {
    return `${matchup.home.team} by ${num(expected.margin)}`;
  }
  if (expected.margin < -0.3) {
    return `${matchup.away.team} by ${num(Math.abs(expected.margin))}`;
  }
  return "Pick 'em";
}

function toBookHalf(value: number) {
  return Math.round(value * 2) / 2;
}

function halfLabel(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function spreadLabel(value: number) {
  if (value === 0) return "PK";
  return `${value > 0 ? "+" : "-"}${halfLabel(Math.abs(value))}`;
}

function bookTickets(expected: { total: number; margin: number }) {
  const total = toBookHalf(expected.total);
  const homeSpread = -toBookHalf(expected.margin);
  return {
    total,
    homeSpread,
    awaySpread: -homeSpread,
    totalLabel: halfLabel(total),
  };
}

function TeamFollow({
  account,
  team,
  name,
}: {
  account: TpeUser | null;
  team: string;
  name: string;
}) {
  const [followId, setFollowId] = useState<string | null>(null);

  useEffect(() => {
    if (!account) {
      setFollowId(null);
      return;
    }
    lookupFollow("team", "mlb", team).then((found) => setFollowId(found?.id ?? null));
  }, [account, team]);

  if (!account) {
    return (
      <a className="book-mini" href={tpeAccountUrl("signin")}>
        Sign in to follow {team}
      </a>
    );
  }

  return (
    <button
      type="button"
      className="book-mini"
      onClick={() => {
        if (followId) {
          void removeFollow(followId).then(() => setFollowId(null));
          return;
        }
        void addFollow({
          kind: "team",
          desk: "mlb",
          subjectId: team,
          subjectName: name || team,
        }).then((row) => setFollowId(row.id));
      }}
    >
      {followId ? `Following ${team}` : `Follow ${team}`}
    </button>
  );
}

function StatRow({
  label,
  left,
  right,
  signedValue = false,
  digits = 1,
}: {
  label: string;
  left: number | null | undefined;
  right: number | null | undefined;
  signedValue?: boolean;
  digits?: number;
}) {
  const fmt = signedValue ? signed : num;
  return (
    <div className="stat-row">
      <b>{fmt(left, digits)}</b>
      <span>{label}</span>
      <b>{fmt(right, digits)}</b>
    </div>
  );
}

function TeamFacts({
  card,
  roleLabel,
}: {
  card: TeamCard;
  roleLabel: string;
}) {
  const overall = card.overall;
  const recent = card.recent;
  const role = card.role;
  return (
    <section className="team-card">
      <p className="kicker">{roleLabel}</p>
      <h2>{card.team}</h2>
      <p className="team-name">{card.name}</p>
      <p className="sub">{sampleRange(overall)}</p>
      <dl className="team-stats">
        <div>
          <dt>Runs for</dt>
          <dd>{num(overall?.rpg)}</dd>
        </div>
        <div>
          <dt>Runs against</dt>
          <dd>{num(overall?.rapg)}</dd>
        </div>
        <div>
          <dt>Margin</dt>
          <dd>{signed(overall?.margin)}</dd>
        </div>
        <div>
          <dt>Hits / HR</dt>
          <dd>
            {num(overall?.hits)} / {num(overall?.home_runs, 2)}
          </dd>
        </div>
        <div>
          <dt>ERA</dt>
          <dd>{num(overall?.era, 2)}</dd>
        </div>
        <div>
          <dt>K/9</dt>
          <dd>{num(overall?.k9)}</dd>
        </div>
        <div>
          <dt>Hits allowed</dt>
          <dd>{num(overall?.hits_allowed)}</dd>
        </div>
        <div>
          <dt>HR allowed</dt>
          <dd>{num(overall?.home_runs_allowed, 2)}</dd>
        </div>
        <div>
          <dt>Last 10</dt>
          <dd>
            {num(recent?.rpg)} / {num(recent?.rapg)} ({signed(recent?.margin)})
          </dd>
        </div>
        <div>
          <dt>{roleLabel} split</dt>
          <dd>
            {role
              ? `${num(role.rpg)} / ${num(role.rapg)} in ${role.games}`
              : "—"}
          </dd>
        </div>
      </dl>
      <p className="missing-block">
        <span className="kicker">Regulars on IL</span>
        {formatMissing(card.missing)}
      </p>
    </section>
  );
}

function GameCard({
  game,
  onOpen,
}: {
  game: SlateGame;
  onOpen: (id: string) => void;
}) {
  const tags = [];
  if (game.div_game) tags.push("Div");
  if (game.is_night) tags.push("Night");
  if (game.is_altitude) tags.push("Coors");
  if (game.neutral) tags.push("Neutral");
  if (game.surface_group) tags.push(game.surface_group);
  return (
    <button type="button" className="game-card" onClick={() => onOpen(game.game_id)}>
      <p className="kicker">{firstPitch(game)}</p>
      <p className="matchup-line">
        <span>{game.away_team}</span>
        <small>@</small>
        <span>{game.home_team}</span>
      </p>
      <p className="sub">
        {game.away_name.split(" ").slice(-1)} at {game.home_name.split(" ").slice(-1)}
      </p>
      <p className="spot-line">
        {roofLabel(game)}
        {game.stadium ? ` · ${game.stadium}` : ""}
      </p>
      <p className="spot-line">
        {spLabel(game.away_sp_name, game.away_sp_throws)}
        {" vs "}
        {spLabel(game.home_sp_name, game.home_sp_throws)}
      </p>
      <p className="spot-line">
        Rest {game.away_rest ?? "—"}d / {game.home_rest ?? "—"}d
        {game.away_travel && game.away_travel !== "none"
          ? ` · ${game.away_travel} hop`
          : ""}
      </p>
      {game.played && (
        <p className="played">
          Played {game.away_score}–{game.home_score}
        </p>
      )}
      <div className="card-tags">
        {tags.map((tag) => (
          <span className="chip" key={tag}>
            {tag}
          </span>
        ))}
      </div>
    </button>
  );
}

export default function SlateDesk({ account }: { account: TpeUser | null }) {
  const [data, setData] = useState<SlateResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [matchup, setMatchup] = useState<Matchup | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bookNote, setBookNote] = useState<string | null>(null);

  useEffect(() => {
    fetchSlate()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Slate failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) {
      setMatchup(null);
      return;
    }
    setError(null);
    fetchMatchup(selected)
      .then(setMatchup)
      .catch((err) => setError(err instanceof Error ? err.message : "Matchup failed"));
  }, [selected]);

  function onDayChange(value: string) {
    const day = data?.days.find((item) => item.gameday === value);
    if (!day) return;
    setSelected(null);
    setLoading(true);
    fetchSlate(day.gameday)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Slate failed"))
      .finally(() => setLoading(false));
  }

  if (loading && !data) {
    return <p className="note">Loading today’s slate…</p>;
  }

  if (matchup) {
    const { game, expected, away, home } = matchup;
    const tickets = expected ? bookTickets(expected) : null;
    const gameLabel = `${game.away_team} @ ${game.home_team}`;
    return (
      <div className="matchup-desk">
        <button type="button" className="back" onClick={() => setSelected(null)}>
          ← Back to slate
        </button>
        <header className="matchup-head">
          <p className="kicker">
            {firstPitch(game)} · {roofLabel(game)}
            {game.stadium ? ` · ${game.stadium}` : ""}
          </p>
          <h2>
            {game.away_team} @ {game.home_team}
          </h2>
          <div className="book-bar">
            <TeamFollow account={account} team={game.away_team} name={game.away_name} />
            <TeamFollow account={account} team={game.home_team} name={game.home_name} />
            {account && <a href={tpeAccountUrl("book")}>My book</a>}
          </div>
          <p className="sub">
            {spLabel(game.away_sp_name, game.away_sp_throws)} vs{" "}
            {spLabel(game.home_sp_name, game.home_sp_throws)}
            {" · "}Rest {game.away_rest ?? "—"}d / {game.home_rest ?? "—"}d
            {game.div_game ? " · Division" : ""}
            {game.is_night ? " · Night" : " · Day"}
            {game.away_travel && game.away_travel !== "none"
              ? ` · Away hop ${game.away_travel}`
              : ""}
          </p>
        </header>

        <section className="expected-board">
          <p className="kicker">Expected from team numbers</p>
          {expected ? (
            <>
              <div className="expected-scores">
                <div>
                  <span>{game.away_team}</span>
                  <b>{num(expected.away_runs)}</b>
                </div>
                <div className="expected-mid">
                  <small>Total {num(expected.total)}</small>
                  <strong>{expectedLabel(matchup)}</strong>
                </div>
                <div>
                  <span>{game.home_team}</span>
                  <b>{num(expected.home_runs)}</b>
                </div>
              </div>
              <div className="book-bar log-row">
                {account && tickets ? (
                  <>
                    <div className="log-group">
                      <span>Moneyline</span>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "moneyline",
                            side: game.away_team,
                            line: null,
                          }).then(() => setBookNote(`Logged ${game.away_team} ML.`));
                        }}
                      >
                        Log {game.away_team}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "moneyline",
                            side: game.home_team,
                            line: null,
                          }).then(() => setBookNote(`Logged ${game.home_team} ML.`));
                        }}
                      >
                        Log {game.home_team}
                      </button>
                    </div>
                    <div className="log-group">
                      <span>Run line</span>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "spread",
                            side: `${game.away_team} ${spreadLabel(tickets.awaySpread)}`,
                            line: tickets.awaySpread,
                          }).then(() =>
                            setBookNote(`Logged ${game.away_team} ${spreadLabel(tickets.awaySpread)}.`),
                          );
                        }}
                      >
                        Log {game.away_team} {spreadLabel(tickets.awaySpread)}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "spread",
                            side: `${game.home_team} ${spreadLabel(tickets.homeSpread)}`,
                            line: tickets.homeSpread,
                          }).then(() =>
                            setBookNote(`Logged ${game.home_team} ${spreadLabel(tickets.homeSpread)}.`),
                          );
                        }}
                      >
                        Log {game.home_team} {spreadLabel(tickets.homeSpread)}
                      </button>
                    </div>
                    <div className="log-group">
                      <span>Total</span>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "total",
                            side: `Over ${tickets.totalLabel}`,
                            line: tickets.total,
                          }).then(() => setBookNote(`Logged over ${tickets.totalLabel}.`));
                        }}
                      >
                        Log over {tickets.totalLabel}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void addWager({
                            desk: "mlb",
                            gameLabel,
                            market: "total",
                            side: `Under ${tickets.totalLabel}`,
                            line: tickets.total,
                          }).then(() => setBookNote(`Logged under ${tickets.totalLabel}.`));
                        }}
                      >
                        Log under {tickets.totalLabel}
                      </button>
                    </div>
                    {bookNote && <span className="note">{bookNote}</span>}
                  </>
                ) : (
                  <a href={tpeAccountUrl("signin")}>
                    Sign in to log a moneyline, run line, or total
                  </a>
                )}
              </div>
              <p className="sub">
                Last {matchup.lookback_games} regular-season games before this
                first pitch. Blend of each team’s scoring and the other side’s
                runs allowed, minus league RPG
                {expected.hfa
                  ? `, plus ${num(expected.hfa, 1)} home field from the same window`
                  : ", no home-field (neutral/overseas)"}
                . Not a betting line.
              </p>
              {expected.recent && (
                <p className="note">
                  Last {matchup.recent_games}: {game.away_team} {num(expected.recent.away_runs)}{" "}
                  – {game.home_team} {num(expected.recent.home_runs)} (total{" "}
                  {num(expected.recent.total)})
                </p>
              )}
              {game.played && (
                <p className="played">
                  Final {game.away_score}–{game.home_score}
                </p>
              )}
            </>
          ) : (
            <p className="sub">Not enough completed games to build an expected score.</p>
          )}
        </section>

        <div className="compare">
          <StatRow label="RPG" left={away.overall?.rpg} right={home.overall?.rpg} />
          <StatRow label="RAPG" left={away.overall?.rapg} right={home.overall?.rapg} />
          <StatRow
            label="Margin"
            left={away.overall?.margin}
            right={home.overall?.margin}
            signedValue
          />
          <StatRow label="ERA" left={away.overall?.era} right={home.overall?.era} digits={2} />
          <StatRow label="K/9" left={away.overall?.k9} right={home.overall?.k9} />
          <StatRow
            label="HR"
            left={away.overall?.home_runs}
            right={home.overall?.home_runs}
            digits={2}
          />
        </div>

        <div className="matchup-grid">
          <TeamFacts card={away} roleLabel="Away" />
          <TeamFacts card={home} roleLabel="Home" />
        </div>
      </div>
    );
  }

  const days = data?.days ?? [];
  const current = data?.slate;

  return (
    <>
      <div className="slate-bar">
        <div>
          <p className="kicker">Today’s slate</p>
          <h2>{current?.label ?? "No games loaded"}</h2>
          <p className="sub">
            Team identity only — no run lines, totals, or moneylines. Click a
            game for each side’s numbers and an expected score from those
            numbers.
          </p>
        </div>
        {days.length > 0 && (
          <label>
            Date
            <select
              value={current?.gameday ?? ""}
              onChange={(e) => onDayChange(e.target.value)}
            >
              {days.map((day: SlateDay) => (
                <option key={day.gameday} value={day.gameday}>
                  {day.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {data?.games?.length ? (
        <div className="slate-grid">
          {data.games.map((game) => (
            <GameCard key={game.game_id} game={game} onOpen={setSelected} />
          ))}
        </div>
      ) : (
        <section className="empty">
          <h2>No slate yet</h2>
          <p>
            Run ingest so schedules are in the database, then this desk will show
            today or the next MLB date.
          </p>
        </section>
      )}
    </>
  );
}
