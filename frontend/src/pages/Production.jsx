import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, NumberInput, Pill, Tile, fmtDate, money, qty, useAction, useApi } from "../ui";

export default function Production() {
  const { location, locations, setLocationId, can } = useAuth();
  const kitchen = locations.find((l) => l.kind === "kitchen");
  const isKitchen = location.kind === "kitchen";
  const data = useApi(isKitchen ? `/stock/batches/?location=${location.id}` : null);
  const preps = useApi(isKitchen ? "/items/?kind=prep" : null);
  const [form, setForm] = useState({ item: "", qty: "" });
  const [edits, setEdits] = useState({});
  const [run, busy] = useAction();

  if (!isKitchen) {
    return (
      <Card title="Central kitchen">
        <p className="muted" style={{ margin: 0 }}>Production happens at the central kitchen.</p>
        {kitchen ? <div><button className="btn primary" type="button" onClick={() => setLocationId(kitchen.id)}>Switch to {kitchen.name}</button></div>
          : <p className="muted">You don't have access to a central kitchen.</p>}
      </Card>
    );
  }
  if (data.error) return <ErrorBox>{data.error}</ErrorBox>;
  if (!data.data) return <Loading />;
  const { planned, done, demand } = data.data;
  const manager = can("manager");

  async function plan(item, amount) {
    const ok = await run(() => api.post("/stock/batches/", { location: location.id, item, qty: amount }), "Batch planned.");
    if (ok) { setForm({ item: "", qty: "" }); data.reload(); }
  }
  async function saveQty(b) {
    const v = edits[b.id];
    if (v === undefined || Number(v) === b.qty) return;
    const ok = await run(() => api.patch(`/stock/batches/${b.id}/`, { qty: v }), `${b.number} updated.`);
    if (ok) data.reload();
  }
  async function remove(b) {
    if (await run(() => api.delete(`/stock/batches/${b.id}/`), `${b.number} removed.`)) data.reload();
  }
  async function cook(b) {
    if (await run(() => api.post(`/stock/batches/${b.id}/complete/`), `${b.number} cooked. Stock updated.`)) data.reload();
  }

  const blocked = planned.filter((b) => b.requirements.some((r) => r.have < r.need)).length;
  return (
    <>
      <div className="tiles">
        <Tile label="Batches planned" value={planned.length} />
        <Tile label="Missing ingredients" value={blocked} note="Batches that can't be cooked yet" stripe={blocked ? "bad" : "good"} />
        <Tile label="Cooked recently" value={done.length} />
      </div>
      <Card title="What outlets need">
        <div className="tablewrap">
          <table>
            <thead><tr><th>Prep</th><th className="r">Outlets below par</th><th className="r">Requested</th><th className="r">In kitchen</th><th className="r">Planned</th><th className="r">Still to make</th><th /></tr></thead>
            <tbody>
              {demand.map((d) => (
                <tr key={d.item}>
                  <td><b>{d.name}</b></td>
                  <td className="r">{qty(d.outlets_short, d.unit)}</td><td className="r">{qty(d.requested, d.unit)}</td>
                  <td className="r">{qty(d.in_kitchen, d.unit)}</td><td className="r">{qty(d.planned, d.unit)}</td>
                  <td className="r">{d.to_make ? <Pill kind="warn">{qty(d.to_make, d.unit)}</Pill> : <Pill kind="good">Covered</Pill>}</td>
                  <td className="r">{manager && d.to_make > 0 && <button className="btn sm" type="button" disabled={busy} onClick={() => plan(d.item, d.to_make)}>Plan batch</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Planned batches">
        {!planned.length ? <Empty>Nothing planned.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Batch</th><th>Prep</th><th className="r">Qty</th><th className="r">Cost</th><th>Ingredients</th><th /></tr></thead>
              <tbody>
                {planned.map((b) => {
                  const missing = b.requirements.filter((r) => r.have < r.need);
                  return (
                    <tr key={b.id}>
                      <td><b>{b.number}</b><div className="small muted">{fmtDate(b.planned_for)}</div></td>
                      <td>{b.item_name}</td>
                      <td className="r">
                        {manager ? (
                          <><NumberInput value={edits[b.id] ?? b.qty} label={`Quantity for ${b.number}`} step="1"
                            onChange={(v) => setEdits({ ...edits, [b.id]: v })} onBlur={() => saveQty(b)} /> {b.unit}</>
                        ) : qty(b.qty, b.unit)}
                      </td>
                      <td className="r">{money(b.cost)}</td>
                      <td className="small">
                        {missing.length ? missing.map((r) => (
                          <div key={r.item} style={{ color: "var(--bad)" }}>Short {r.name}: need {qty(r.need, r.unit)}, have {qty(r.have, r.unit)}</div>
                        )) : <Pill kind="good">All in stock</Pill>}
                      </td>
                      <td className="r">
                        <div className="row end">
                          <button className="btn sm primary" type="button" disabled={busy || missing.length > 0} onClick={() => cook(b)}>Mark cooked</button>
                          {manager && <button className="btn sm" type="button" disabled={busy} onClick={() => remove(b)}>Remove</button>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {manager && (
          <form className="row" onSubmit={(e) => { e.preventDefault(); if (form.item && Number(form.qty) > 0) plan(Number(form.item), form.qty); }}>
            <label className="f">Prep
              <select value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} required>
                <option value="">Choose…</option>
                {(preps.data || []).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.unit})</option>)}
              </select>
            </label>
            <label className="f">Quantity<NumberInput value={form.qty} step="1" label="Batch quantity" onChange={(v) => setForm({ ...form, qty: v })} /></label>
            <button className="btn" type="submit" disabled={busy}>Add batch</button>
          </form>
        )}
        <p className="small muted" style={{ margin: 0 }}>Marking a batch cooked takes its ingredients out of kitchen stock and adds the prep.</p>
      </Card>
      <Card title="Recently cooked">
        {!done.length ? <Empty>None yet.</Empty> : (
          <table>
            <thead><tr><th>Batch</th><th>Prep</th><th className="r">Qty</th><th className="r">Cost</th><th>Cooked</th></tr></thead>
            <tbody>{done.map((b) => <tr key={b.id}><td>{b.number}</td><td>{b.item_name}</td><td className="r">{qty(b.qty, b.unit)}</td><td className="r">{money(b.cost)}</td><td>{fmtDate(b.completed_on)}</td></tr>)}</tbody>
          </table>
        )}
      </Card>
    </>
  );
}
