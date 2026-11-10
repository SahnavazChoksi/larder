import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, HBars, Loading, Pill, Tile, daysAgo, fmtDate, money, useAction, useApi } from "../ui";

const CATEGORIES = [["food", "Food quality"], ["service", "Service"], ["wait", "Wait time"], ["wrong", "Wrong item"], ["missing", "Missing item"], ["clean", "Cleanliness"], ["price", "Price / bill"]];
const CHANNELS = [["in_person", "In person"], ["phone", "Phone"], ["review", "Online review"], ["delivery", "Delivery app"]];

export default function Complaints() {
  const { location } = useAuth();
  const [days, setDays] = useState(30);
  const list = useApi(`/ops/complaints/?location=${location.id}&days=${days}`);
  const blank = { occurred_on: daysAgo(0), category: "food", channel: "in_person", detail: "", action_taken: "", comped: "" };
  const [f, setF] = useState(blank);
  const [run, busy] = useAction();

  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/ops/complaints/", { ...f, location: location.id, comped: f.comped || 0 }), "Complaint logged.");
    if (ok) { setF(blank); list.reload(); }
  }

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  const rows = list.data || [];
  const byCat = CATEGORIES.map(([k, label]) => ({ label, value: rows.filter((r) => r.category === k).length })).filter((r) => r.value).sort((a, b) => b.value - a.value);

  return (
    <>
      <Chips options={[[7, "7 days"], [30, "30 days"], [60, "60 days"]]} value={days} onChange={setDays} />
      <div className="tiles">
        <Tile label="Complaints" value={rows.length} note={location.name} />
        <Tile label="Comped to guests" value={money(rows.reduce((s, r) => s + Number(r.comped), 0))} />
        <Tile label="Top reason" value={byCat[0]?.label || "—"} />
      </div>
      <div className="split">
        <Card title="Log a complaint">
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="row">
              <label className="f">Date<input type="date" value={f.occurred_on} max={daysAgo(0)} onChange={(e) => setF({ ...f, occurred_on: e.target.value })} /></label>
              <label className="f">About<select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
              <label className="f">Came in by<select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>{CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            </div>
            <label className="f">What happened<input value={f.detail} required maxLength={300} onChange={(e) => setF({ ...f, detail: e.target.value })} /></label>
            <label className="f">What we did<input value={f.action_taken} maxLength={300} onChange={(e) => setF({ ...f, action_taken: e.target.value })} /></label>
            <label className="f">Comped ($)<input type="number" step="0.01" min="0" value={f.comped} onChange={(e) => setF({ ...f, comped: e.target.value })} /></label>
            <div className="row end"><button className="btn primary" type="submit" disabled={busy}>Log complaint</button></div>
          </form>
        </Card>
        <Card title="By reason"><HBars rows={byCat} format={(v) => v} color="var(--warn)" /></Card>
      </div>
      <Card title="Complaints">
        {!list.data ? <Loading /> : !rows.length ? <Empty>None in this range.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Date</th><th>About</th><th>Channel</th><th>What happened</th><th>What we did</th><th className="r">Comped</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}><td>{fmtDate(r.occurred_on)}</td><td><Pill kind="warn">{r.category_label}</Pill></td><td className="small">{r.channel_label}</td>
                    <td>{r.detail}</td><td className="small muted">{r.action_taken}</td><td className="r">{Number(r.comped) ? money(r.comped) : "—"}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
