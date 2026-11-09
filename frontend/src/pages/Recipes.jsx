import { useEffect, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, Loading, Modal, NumberInput, Pill, Sparkline, fmtDate, money, pct, useAction, useApi } from "../ui";

const TARGET = 0.25;

export default function Recipes() {
  const [tab, setTab] = useState("dishes");
  return (
    <>
      <Chips options={[["dishes", "Dishes"], ["preps", "Prep recipes"], ["ingredients", "Ingredient prices"]]} value={tab} onChange={setTab} />
      {tab === "dishes" && <Dishes />}
      {tab === "preps" && <Preps />}
      {tab === "ingredients" && <Ingredients />}
    </>
  );
}

function Dishes() {
  const list = useApi("/menu-items/");
  const [selId, setSelId] = useState(null);
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const sel = list.data.find((d) => d.id === selId) || list.data[0];
  return (
    <div className="split">
      <Card title="Menu costing">
        <div className="tablewrap">
          <table>
            <thead><tr><th>Dish</th><th className="r">Price</th><th className="r">Plate cost</th><th className="r">Food cost</th><th className="r">Margin</th></tr></thead>
            <tbody>
              {list.data.map((d) => (
                <tr key={d.id} className={`click ${d.id === sel?.id ? "sel" : ""}`} onClick={() => setSelId(d.id)}>
                  <td><b>{d.name}</b><div className="small muted">{d.category} · {d.pos_code}</div></td>
                  <td className="r">{money(d.price)}</td><td className="r">{money(d.plate_cost)}</td>
                  <td className="r"><Pill kind={d.food_cost_pct > 0.32 ? "bad" : d.food_cost_pct > TARGET ? "warn" : "good"}>{pct(d.food_cost_pct)}</Pill></td>
                  <td className="r">{money(d.margin)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {sel && <Editor key={sel.id} kind="dish" record={sel} onSaved={list.reload} />}
    </div>
  );
}

function Preps() {
  const list = useApi("/items/?kind=prep");
  const [selId, setSelId] = useState(null);
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const sel = list.data.find((d) => d.id === selId) || list.data[0];
  return (
    <div className="split">
      <Card title="Prep recipes">
        <table>
          <thead><tr><th>Prep</th><th className="r">Cost per unit</th><th className="r">Usual batch</th></tr></thead>
          <tbody>
            {list.data.map((p) => (
              <tr key={p.id} className={`click ${p.id === sel?.id ? "sel" : ""}`} onClick={() => setSelId(p.id)}>
                <td><b>{p.name}</b></td><td className="r">{money(p.unit_cost)}/{p.unit}</td><td className="r">{p.batch_size ? `${p.batch_size} ${p.unit}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {sel && <Editor key={sel.id} kind="prep" record={sel} onSaved={list.reload} />}
    </div>
  );
}

/** Edit ingredient quantities (and a dish's price). Only owners can save; managers see it read-only. */
function Editor({ kind, record, onSaved }) {
  const { can } = useAuth();
  const owner = can("owner");
  const allItems = useApi("/items/");
  const initial = kind === "dish" ? record.lines : record.recipe;
  const [lines, setLines] = useState(initial.map((l) => ({ item: l.item, name: l.name, unit: l.unit, qty: l.qty, unit_cost: l.unit_cost })));
  const [price, setPrice] = useState(record.price);
  const [add, setAdd] = useState({ item: "", qty: "" });
  const [run, busy] = useAction();
  useEffect(() => setPrice(record.price), [record.price]);

  const cost = lines.reduce((s, l) => s + Number(l.qty || 0) * l.unit_cost, 0);
  const options = (allItems.data || []).filter((i) => i.id !== record.id && !lines.some((l) => l.item === i.id));
  const dirty = JSON.stringify(lines.map((l) => [l.item, Number(l.qty)])) !== JSON.stringify(initial.map((l) => [l.item, l.qty])) || (kind === "dish" && Number(price) !== record.price);

  function addLine() {
    const it = options.find((i) => String(i.id) === String(add.item));
    if (!it || !(Number(add.qty) > 0)) return;
    setLines([...lines, { item: it.id, name: it.name, unit: it.unit, qty: add.qty, unit_cost: it.unit_cost }]);
    setAdd({ item: "", qty: "" });
  }

  async function save() {
    const body = { lines: lines.map((l) => ({ item: l.item, qty: l.qty })) };
    if (kind === "dish") body.price = price;
    const url = kind === "dish" ? `/menu-items/${record.id}/recipe/` : `/items/${record.id}/recipe/`;
    if (await run(() => api.put(url, body), `${record.name} saved. Costs updated.`)) onSaved();
  }

  const fc = kind === "dish" && Number(price) ? cost / Number(price) : null;
  const allergens = kind === "dish" ? record.allergens : record.allergen_list;
  return (
    <Card title={record.name} actions={owner && <button className="btn primary" type="button" disabled={!dirty || busy} onClick={save}>Save changes</button>}>
      {!owner && <div className="note">Only the owner can change recipes and prices.</div>}
      <div className="row">
        {allergens?.length ? allergens.map((a) => <Pill key={a} kind="info">Contains {a}</Pill>) : <Pill>No allergens tagged</Pill>}
      </div>
      <div className="row">
        {kind === "dish" && <label className="f">Menu price<NumberInput value={price} step="0.05" label="Menu price" disabled={!owner} onChange={setPrice} /></label>}
        <label className="f">{kind === "dish" ? "Plate cost" : `Cost per ${record.unit}`}<b className="num" style={{ padding: "6px 0" }}>{money(cost)}</b></label>
        {fc != null && <label className="f">Food cost<b className="num" style={{ padding: "6px 0" }}>{pct(fc)}</b></label>}
        {kind === "dish" && <label className="f">Price for {pct(TARGET, 0)} food cost<b className="num" style={{ padding: "6px 0" }}>{money(cost / TARGET)}</b></label>}
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Ingredient</th><th className="r">Qty{kind === "prep" ? ` per ${record.unit}` : ""}</th><th className="r">Unit cost</th><th className="r">Line cost</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={l.item}>
                <td>{l.name}</td>
                <td className="r">
                  {owner ? <NumberInput value={l.qty} step="0.001" label={`Quantity ${l.name}`} onChange={(v) => setLines(lines.map((x, j) => (j === i ? { ...x, qty: v } : x)))} /> : l.qty} {l.unit}
                </td>
                <td className="r muted">{money(l.unit_cost)}</td>
                <td className="r">{money(Number(l.qty || 0) * l.unit_cost)}</td>
                <td className="r">{owner && <button className="btn sm" type="button" onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {owner && (
        <div className="row">
          <select value={add.item} aria-label="Ingredient to add" onChange={(e) => setAdd({ ...add, item: e.target.value })}>
            <option value="">Add an ingredient…</option>
            {options.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.unit})</option>)}
          </select>
          <NumberInput value={add.qty} step="0.01" label="Quantity to add" onChange={(v) => setAdd({ ...add, qty: v })} />
          <button className="btn" type="button" onClick={addLine}>Add</button>
        </div>
      )}
    </Card>
  );
}

function Ingredients() {
  const list = useApi("/items/?kind=raw");
  const [hist, setHist] = useState(null);
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  return (
    <Card title="Ingredient prices">
      <p className="small muted" style={{ margin: 0 }}>Prices update automatically when a delivery is received. Click an item for its history.</p>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Ingredient</th><th>Category</th><th>Vendor</th><th className="r">Latest price</th></tr></thead>
          <tbody>
            {list.data.map((i) => (
              <tr key={i.id} className="click" onClick={() => setHist(i)}>
                <td><b>{i.name}</b></td><td className="muted">{i.category}</td><td>{i.vendor_name}</td><td className="r">{money(i.last_price)}/{i.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hist && <PriceHistory item={hist} onClose={() => setHist(null)} />}
    </Card>
  );
}

function PriceHistory({ item, onClose }) {
  const { data, error } = useApi(`/items/${item.id}/price-history/`);
  return (
    <Modal title={`${item.name} price history`} onClose={onClose} footer={<button className="btn" type="button" onClick={onClose}>Close</button>}>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!data ? <Loading /> : (
        <>
          <Sparkline values={[...data].reverse().map((h) => h.price)} />
          <table>
            <thead><tr><th>Date</th><th>Source</th><th className="r">Price</th></tr></thead>
            <tbody>{data.map((h) => <tr key={h.id}><td>{fmtDate(h.recorded_on)}</td><td className="small muted">{h.source}</td><td className="r">{money(h.price)}/{item.unit}</td></tr>)}</tbody>
          </table>
        </>
      )}
    </Modal>
  );
}
