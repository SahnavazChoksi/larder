import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Pill, daysAgo, fmtDate, fmtDateTime, useAction, useApi } from "../ui";

export default function Logbook() {
  const { location } = useAuth();
  const [days, setDays] = useState(7);
  const list = useApi(`/ops/handover/?location=${location.id}&days=${days}`);
  const [f, setF] = useState({ shift: "closing", body: "", is_important: false, business_date: daysAgo(0) });
  const [run, busy] = useAction();

  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/ops/handover/", { ...f, location: location.id }), "Note added for the next shift.");
    if (ok) { setF({ ...f, body: "", is_important: false }); list.reload(); }
  }
  async function markRead(n) {
    if (await run(() => api.post(`/ops/handover/${n.id}/read/`))) list.reload();
  }

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  const notes = list.data || [];
  const byDay = [...new Set(notes.map((n) => n.business_date))];

  return (
    <div className="split">
      <Card title={`Logbook · ${location.name}`}>
        <Chips options={[[3, "3 days"], [7, "7 days"], [30, "30 days"]]} value={days} onChange={setDays} />
        {!list.data ? <Loading /> : !notes.length ? <Empty>No notes yet.</Empty> : byDay.map((d) => (
          <div key={d}>
            <h3 style={{ margin: "8px 0 4px" }}>{fmtDate(d)}</h3>
            {notes.filter((n) => n.business_date === d).map((n) => (
              <div key={n.id} className="alert" style={{ gridTemplateColumns: "4px 1fr auto" }}>
                <span className={`bar ${n.is_important ? "bad" : "info"}`} />
                <div>
                  <div className="row"><Pill kind="accent">{n.shift_label}</Pill>{n.is_important && <Pill kind="bad">Important</Pill>}
                    <span className="small muted">{n.author_name} · {fmtDateTime(n.created_at)} · read by {n.read_count}</span></div>
                  <p style={{ margin: "6px 0 0", whiteSpace: "pre-line" }}>{n.body}</p>
                </div>
                {!n.read && <button className="btn sm" type="button" onClick={() => markRead(n)}>Mark read</button>}
              </div>
            ))}
          </div>
        ))}
      </Card>
      <Card title="Leave a note for the next shift">
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row">
            <label className="f">Shift
              <select value={f.shift} onChange={(e) => setF({ ...f, shift: e.target.value })}>
                <option value="opening">Opening / day</option><option value="closing">Closing / night</option><option value="general">General</option>
              </select>
            </label>
            <label className="f">Business day<input type="date" value={f.business_date} max={daysAgo(0)} onChange={(e) => setF({ ...f, business_date: e.target.value })} /></label>
          </div>
          <label className="f">Note<textarea rows={5} required value={f.body} placeholder="What does the next team need to know? Low stock, broken equipment, big bookings, guest issues…" onChange={(e) => setF({ ...f, body: e.target.value })} /></label>
          <label className="row small"><input type="checkbox" checked={f.is_important} onChange={(e) => setF({ ...f, is_important: e.target.checked })} /> Important: notify managers</label>
          <div className="row end"><button className="btn primary" type="submit" disabled={busy}>Add note</button></div>
        </form>
      </Card>
    </div>
  );
}
