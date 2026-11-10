import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Chips, Empty, ErrorBox, Loading, Pill, Tile, minutesSince, useAction, useApi, useNow } from "../ui";

/** Kitchen display: tickets in the order they were sent. Every tap is timed. Refreshes every 5 seconds. */
export default function Kitchen() {
  const { location } = useAuth();
  const [view, setView] = useState("kitchen");
  const { data, error, reload } = useApi(`/pos/kds/?location=${location.id}&view=${view}`, 5000);
  const now = useNow(5000);
  const [run, busy] = useAction();

  if (error) return <ErrorBox>{error}</ErrorBox>;
  const step = async (t, s) => { if (await run(() => api.post(`/pos/tickets/${t.id}/${s}/`))) reload(); };
  const target = data?.target_minutes || 15;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Chips options={[["kitchen", "Kitchen (to cook)"], ["expo", "Pass (ready to serve)"]]} value={view} onChange={setView} />
        <span className="small muted">Target {target} min from send to ready. Updates every 5 seconds.</span>
      </div>
      {data && (
        <div className="tiles">
          <Tile label="On the board" value={data.tickets.length} />
          <Tile label="Done today" value={data.today.done} />
          <Tile label="Avg prep today" value={data.today.avg_prep != null ? `${data.today.avg_prep.toFixed(1)} min` : "—"}
            stripe={data.today.avg_prep > target ? "bad" : "good"} />
          <Tile label="Late today" value={data.today.late} note={`Over ${target} min`} stripe={data.today.late ? "warn" : "good"} />
        </div>
      )}
      {!data ? <Loading /> : !data.tickets.length ? <Empty>{view === "kitchen" ? "Nothing to cook." : "Nothing waiting at the pass."}</Empty> : (
        <div className="kds">
          {data.tickets.map((t) => {
            const mins = view === "expo" ? minutesSince(t.ready_at, now) : minutesSince(t.sent_at, now);
            const late = view === "kitchen" && mins > target;
            const warn = view === "kitchen" && mins > target * 0.75;
            return (
              <div key={t.id} className={`ticket ${late ? "late" : warn ? "warn" : ""} ${t.is_rush ? "rush" : ""}`}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <b>{t.table ? `Table ${t.table}` : t.order_type}{t.customer && !t.table ? ` · ${t.customer}` : ""}</b>
                  <span className={`big-timer ${late ? "worse" : ""}`}>{Math.floor(mins)}:{String(Math.floor((mins % 1) * 60)).padStart(2, "0")}</span>
                </div>
                <div className="small muted">{t.order_number} · {t.guests} guest{t.guests > 1 ? "s" : ""}{t.server ? ` · ${t.server}` : ""}
                  {t.channel !== "larder" && <> · <Pill>{t.channel}</Pill></>} {t.is_rush && <Pill kind="bad">Rush</Pill>}</div>
                {t.allergies && <div className="kds-allergy">⚠ ALLERGY: {t.allergies}</div>}
                <div className="lines">
                  {t.lines.map((l) => (
                    <div key={l.id} style={l.void ? { textDecoration: "line-through", opacity: 0.5 } : {}}>
                      <b>{l.qty}×</b> {l.name}{l.seat ? <span className="small muted"> (seat {l.seat})</span> : ""}
                      {l.modifiers?.length > 0 && <div className="kds-mods">{l.modifiers.join(" · ")}</div>}
                      {l.note && <div className="note">{l.note}</div>}
                    </div>
                  ))}
                </div>
                <div className="row">
                  {view === "kitchen" && t.status === "new" && <button className="btn" type="button" disabled={busy} onClick={() => step(t, "start")}>Start</button>}
                  {view === "kitchen" && <button className="btn primary" type="button" disabled={busy} onClick={() => step(t, "ready")}>Ready</button>}
                  {view === "expo" && <button className="btn primary" type="button" disabled={busy} onClick={() => step(t, "served")}>Served</button>}
                  {view === "expo" && <button className="btn" type="button" disabled={busy} onClick={() => step(t, "recall")}>Back to kitchen</button>}
                  {t.status === "started" && <Pill kind="warn">Cooking</Pill>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
