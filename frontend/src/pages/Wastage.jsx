import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, HBars, Loading, NumberInput, Pill, Tile, fmtDate, money, qty, useAction, useApi } from "../ui";

const REASONS = [
  ["spoiled", "Spoiled"], ["expired", "Expired"], ["overprep", "Over-prepped"], ["dropped", "Dropped / spilled"],
  ["quality", "Quality reject"], ["staff", "Staff meal"], ["return", "Customer return"],
];

export default function Wastage() {
  const { location } = useAuth();
  const list = useApi(`/stock/wastage/?location=${location.id}`);
  const levels = useApi(`/stock/levels/?location=${location.id}`);
  const [form, setForm] = useState({ item: "", qty: "", reason: "spoiled", note: "" });
  const [run, busy] = useAction();

  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/stock/wastage/", { location: location.id, ...form, item: Number(form.item) }),
      (d) => `Logged ${qty(d.qty, d.unit)} ${d.item_name} (${money(d.cost)}).`);
    if (ok) { setForm({ ...form, qty: "", note: "" }); list.reload(); levels.reload(); }
  }

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  const rows = list.data || [];
  const total = rows.reduce((s, w) => s + w.cost, 0);
  const byReason = REASONS.map(([k, label]) => ({ label, value: rows.filter((w) => w.reason === k).reduce((s, w) => s + w.cost, 0) }))
    .filter((r) => r.value > 0).sort((a, b) => b.value - a.value);

  return (
    <>
      <div className="tiles">
        <Tile label="Wastage logged" value={money(total)} note={location.name} />
        <Tile label="Entries" value={rows.length} />
        <Tile label="Biggest reason" value={byReason[0]?.label || "—"} />
      </div>
      <div className="split">
        <Card title="Log wastage">
          <form className="row" onSubmit={submit}>
            <label className="f">Item
              <select value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} required>
                <option value="">Choose…</option>
                {(levels.data || []).map((r) => <option key={r.item} value={r.item}>{r.name} ({r.unit})</option>)}
              </select>
            </label>
            <label className="f">Quantity<NumberInput value={form.qty} label="Quantity" min="0.01" onChange={(v) => setForm({ ...form, qty: v })} required /></label>
            <label className="f">Reason
              <select value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>
                {REASONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </label>
            <label className="f" style={{ flex: 1, minWidth: 160 }}>Note<input value={form.note} placeholder="Optional" onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
            <button className="btn primary" type="submit" disabled={busy}>Log it</button>
          </form>
          <p className="small muted" style={{ margin: 0 }}>Logged waste comes off stock and shows as explained loss in the variance report.</p>
        </Card>
        <Card title="Cost by reason"><HBars rows={byReason} format={money} color="var(--warn)" /></Card>
      </div>
      <Card title="Wastage log">
        {!list.data ? <Loading /> : !rows.length ? <Empty>No wastage logged.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Date</th><th>Item</th><th className="r">Qty</th><th>Reason</th><th>Note</th><th>By</th><th className="r">Cost</th></tr></thead>
              <tbody>
                {rows.map((w) => (
                  <tr key={w.id}>
                    <td>{fmtDate(w.occurred_on)}</td><td>{w.item_name}</td><td className="r">{qty(w.qty, w.unit)}</td>
                    <td><Pill>{w.reason_label}</Pill></td><td className="muted">{w.note}</td><td className="small">{w.created_by_name}</td>
                    <td className="r">{money(w.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
