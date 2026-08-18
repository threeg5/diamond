import { useEffect, useState } from "react";
import { fetchMeta, type Meta } from "./api";
import PlayerDesk from "./PlayerDesk";
import SlateDesk from "./SlateDesk";

type Desk = "players" | "slate";

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [desk, setDesk] = useState<Desk>("slate");

  useEffect(() => {
    fetchMeta()
      .then(setMeta)
      .catch(() => setMeta({ ingested: false, stats: {} }));
  }, []);

  return (
    <div className="shell">
      <header className="masthead">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <div>
            <p className="kicker">
              {desk === "slate" ? "Team research desk" : "Baseball research desk"}
            </p>
            <h1>Diamond</h1>
          </div>
        </div>
        <nav className="desks" aria-label="Desks">
          <button
            type="button"
            className={desk === "slate" ? "active" : ""}
            onClick={() => setDesk("slate")}
          >
            Today’s Games
          </button>
          <button
            type="button"
            className={desk === "players" ? "active" : ""}
            onClick={() => setDesk("players")}
          >
            Player Stats
          </button>
        </nav>
        <p className="meta">
          {meta?.ingested
            ? `${meta.games?.toLocaleString() ?? "—"} games · ${meta.players?.toLocaleString()} players · seasons ${meta.seasons}`
            : "Database not loaded yet. Run python -m diamond.ingest from api/"}
        </p>
      </header>

      {desk === "slate" ? <SlateDesk /> : <PlayerDesk meta={meta} />}
    </div>
  );
}
