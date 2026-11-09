import { useMemo, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import {
  Card, Chips, Empty, ErrorBox, Loading, Modal, NumberInput, Pill, STOCK_STATUS, Tile,
  fmtDate, money, money0, qty, useAction, useApi,
} from "../ui";

export default function Stock() {
  const { location, can } = useAuth();
  const levels = useApi(`/stock/levels/?location=${location.id}`);
  const counts = useApi(`/stock/counts/?location=${location.id}`);
  const [mode, setMode] = useState("view"); // view | count | par
  const [inputs, setInputs] = useState({});
  const [cat, setCat] = useState("All");
  const [search, setSearch] = useState("");
  const [ledgerItem, setLedgerItem] = useState(null);
  const [run, busy] = useAction();

  const rows = useMemo(() => levels.data || [], [levels.data]);
  const cats = ["All", ...new Set(rows.map((r) => r.category))];
  const shown = rows.filter((r) => (cat === "All" || r.category === cat) && r.name.toLowerCase().includes(search.toLowerCase()));

  function start(next) {
    setInputs(next === "par" ? Object.fromEntries(rows.map((r) => [r.item, r.par ?? ""])) : {});
    setMode(next);
  }

  async function save() {
    if (mode === "count") {
      const lines = Object.entries(inputs).filter(([, v]) => v !== "").map(([item, v]) => ({ item: Number(item), qty: v }));
      if (!lines.length) return setMode("view");
      const ok = await run(() => api.post("/stock/counts/", { location: location.id, lines }),
        (d) => `Count saved: ${lines.length} items, difference ${money(d.value_difference)}.`);
      if (ok) { setMode("view"); levels.reload(); counts.reload(); }
    } else {
      const pars = rows
        .filter((r) => String(inputs[r.item] ?? "") !== String(r.par ?? ""))
        .map((r) => ({ item: r.item, par: inputs[r.item] === "" ? null : inputs[r.item] }));
      if (!pars.length) return setMode("view");
      const ok = await run(() => api.post("/stock/pars/", { location: location.id, pars }), (d) => `${d.changed} par levels updated.`);
      if (ok) { setMode("view"); levels.reload(); }
    }
  }

  if (levels.error) return <ErrorBox>{levels.error}</ErrorBox>;
  if (levels.loading && !levels.data) return <Loading />;

  const low = rows.filter((r) => r.status === "low" || r.status === "out").length;
  const expiring = rows.filter((r) => r.days_left != null && r.days_left <= 2).length;
  const actions = mode === "view" ? (
    <>
      {can("manager") && <button className="btn" type="button" onClick={() => start("par")}>Edit par levels</button>}
      <button className="btn primary" type="button" onClick={() => start("count")}>Start stock count</button>
    </>
  ) : (
    <>
      <button className="btn" type="button" onClick={() => setMode("view")}>Cancel</button>
      <button className="btn primary" type="button" disabled={busy} onClick={save}>{mode === "count" ? "Save count" : "Save par levels"}</button>
    </>
  );

  return (
    <>
      <div className="tiles">
        <Tile label="Stock value" value={money0(rows.reduce((s, r) => s + r.value, 0))} note={location.name} />
        <Tile label="Low or out" value={low} note="Below half of par" stripe={low ? "bad" : "good"} />
        <Tile label="Expiring in 48 h" value={expiring} note="Use first" stripe={expiring ? "warn" : "good"} />
        <Tile label="Last count" value={counts.data?.[0] ? fmtDate(counts.data[0].counted_on) : "—"} note={counts.data?.[0]?.created_by_name || ""} />
      </div>
      <Card title={`${location.name} stock`} actions={actions}>
        {mode === "count" && <div className="note">Enter what is physically on the shelf. Leave a box empty to skip that item. The difference to the system figure is recorded as a count adjustment.</div>}
        {mode === "par" && <div className="note">Par is how much this location should hold. It drives low-stock flags, reorder suggestions and prep requests. Clear a box to remove the par.</div>}
        <div className="row" style={{ justifyContent: "space-between" }}>
          <Chips options={cats.map((c) => [c, c])} value={cat} onChange={setCat} />
          <input type="search" placeholder="Search items" aria-label="Search items" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Category</th><th className="r">On hand</th><th className="r">Par</th><th>Status</th>
                <th>Shelf life left</th><th className="r">Value</th>{mode === "count" && <th className="r">Counted</th>}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const [kind, label] = STOCK_STATUS[r.status];
                return (
                  <tr key={r.item}>
                    <td>
                      <button className="btn sm" type="button" style={{ border: 0, padding: 0, background: "none", fontWeight: 600 }}
                        onClick={() => setLedgerItem(r)} title="Show every movement for this item">{r.name}</button>
                      {r.kind === "prep" && <> <Pill kind="accent">Prep</Pill></>}
                    </td>
                    <td className="muted">{r.category}</td>
                    <td className="r">{qty(r.on_hand, r.unit)}</td>
                    <td className="r">
                      {mode === "par"
                        ? <NumberInput value={inputs[r.item]} label={`Par for ${r.name}`} step="0.5" onChange={(v) => setInputs({ ...inputs, [r.item]: v })} />
                        : <span className="muted">{qty(r.par, r.unit)}</span>}
                    </td>
                    <td><Pill kind={kind}>{label}</Pill></td>
                    <td>{r.days_left == null ? <span className="muted">—</span> : <Pill kind={r.days_left <= 1 ? "bad" : r.days_left <= 2 ? "warn" : "neutral"}>{r.days_left <= 0 ? "Expired" : `${r.days_left} day${r.days_left > 1 ? "s" : ""}`}</Pill>}</td>
                    <td className="r">{money(r.value)}</td>
                    {mode === "count" && (
                      <td className="r"><NumberInput value={inputs[r.item]} label={`Counted ${r.name}`} onChange={(v) => setInputs({ ...inputs, [r.item]: v })} /></td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!shown.length && <Empty>No items match.</Empty>}
      </Card>
      <Card title="Recent counts">
        {counts.data?.length ? (
          <table>
            <thead><tr><th>Count</th><th>Date</th><th>By</th><th className="r">Items</th><th className="r">Difference</th><th>Note</th></tr></thead>
            <tbody>
              {counts.data.slice(0, 10).map((c) => (
                <tr key={c.id}>
                  <td>{c.number}</td><td>{fmtDate(c.counted_on)}</td><td>{c.created_by_name}</td><td className="r">{c.item_count}</td>
                  <td className="r"><Pill kind={c.value_difference < 0 ? "bad" : "good"}>{money(c.value_difference)}</Pill></td>
                  <td className="muted">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>No counts yet.</Empty>}
      </Card>
      {ledgerItem && <Ledger location={location} item={ledgerItem} onClose={() => setLedgerItem(null)} />}
    </>
  );
}

function Ledger({ location, item, onClose }) {
  const { data, error } = useApi(`/stock/movements/?location=${location.id}&item=${item.item}`);
  return (
    <Modal title={`${item.name} · ${location.name}`} onClose={onClose} footer={<button className="btn" type="button" onClick={onClose}>Close</button>}>
      <p className="small muted" style={{ margin: 0 }}>Every change to this item's stock, newest first. On hand now: {qty(item.on_hand, item.unit)}.</p>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!data ? <Loading /> : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Date</th><th>What</th><th>Ref</th><th className="r">Qty</th><th className="r">Value</th><th>By</th></tr></thead>
            <tbody>
              {data.results.map((m) => (
                <tr key={m.id}>
                  <td>{fmtDate(m.occurred_on)}</td><td>{m.kind_label}</td><td className="small muted">{m.reference}</td>
                  <td className="r" style={{ color: m.qty < 0 ? "var(--bad)" : "var(--good)" }}>{m.qty > 0 ? "+" : ""}{qty(m.qty, m.unit)}</td>
                  <td className="r">{money(m.value)}</td><td className="small">{m.created_by_name || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
