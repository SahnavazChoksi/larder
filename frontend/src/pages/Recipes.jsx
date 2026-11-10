import { useEffect, useRef, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, Loading, Modal, NumberInput, Pill, Sparkline, fmtDate, money, pct, useAction, useApi } from "../ui";

const TARGET = 0.25;

export default function Recipes() {
  const [tab, setTab] = useState("dishes");
  return (
    <>
      <Chips options={[["dishes", "Dishes"], ["options", "Options & add-ons"], ["preps", "Prep recipes"], ["ingredients", "Ingredient prices"]]} value={tab} onChange={setTab} />
      {tab === "dishes" && <Dishes />}
      {tab === "options" && <OptionGroups />}
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
                  <td><b><span aria-hidden="true">{d.icon} </span>{d.name}</b><div className="small muted">{d.category} · {d.pos_code}</div></td>
                  <td className="r">{money(d.price)}</td><td className="r">{money(d.plate_cost)}</td>
                  <td className="r"><Pill kind={d.food_cost_pct > 0.32 ? "bad" : d.food_cost_pct > TARGET ? "warn" : "good"}>{pct(d.food_cost_pct)}</Pill></td>
                  <td className="r">{money(d.margin)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {sel && (
        <div className="stack" style={{ gap: 16 }}>
          <Editor key={sel.id} kind="dish" record={sel} onSaved={list.reload} />
          <MenuCard key={`card${sel.id}`} dish={sel} dishes={list.data} onSaved={list.reload} />
        </div>
      )}
    </div>
  );
}

const ALLERGENS = ["Milk", "Egg", "Gluten", "Peanut", "Nuts", "Soy", "Sesame", "Mustard", "Mushroom", "Fish", "Shellfish", "Alcohol"];

/** What servers and online guests see: picture, description, badges, declared allergens and what to suggest. */
function MenuCard({ dish, dishes, onSaved }) {
  const { can } = useAuth();
  const owner = can("owner");
  const groups = useApi("/modifier-groups/");
  const pick = (d) => ({ icon: d.icon, description: d.description, diet: d.diet, spice_level: d.spice_level, is_chef_pick: d.is_chef_pick,
    is_new: d.is_new, contains: d.contains, dietary_note: d.dietary_note, pairs_with: d.pairs_with, modifier_groups: d.modifier_groups, is_active: d.is_active });
  const [f, setF] = useState(pick(dish));
  const [run, busy] = useAction();
  const file = useRef(null);
  const declared = f.contains.split(",").map((x) => x.trim()).filter(Boolean);
  const set = (k, v) => setF({ ...f, [k]: v });
  const toggleIn = (k, v) => set(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v]);
  const toggleAllergen = (a) => set("contains", (declared.includes(a) ? declared.filter((x) => x !== a) : [...declared, a]).join(", "));
  const dirty = JSON.stringify(f) !== JSON.stringify(pick(dish));

  async function save() {
    if (await run(() => api.patch(`/menu-items/${dish.id}/`, f), `${dish.name} updated on the POS.`)) onSaved();
  }
  async function upload() {
    const ph = file.current?.files?.[0];
    if (!ph) return;
    const body = new FormData();
    body.append("photo", ph);
    const ok = await run(() => api.post(`/menu-items/${dish.id}/photo/`, body), "Photo saved.");
    file.current.value = "";
    if (ok) onSaved();
  }
  const removePhoto = async () => { if (await run(() => api.post(`/menu-items/${dish.id}/photo/`, { remove: true }), "Photo removed.")) onSaved(); };

  return (
    <Card title="On the menu" actions={owner && <button className="btn primary" type="button" disabled={!dirty || busy} onClick={save}>Save</button>}>
      <div className="info-head">
        <span className="pic lg">{dish.photo ? <img src={dish.photo} alt="" /> : <span className="emo" aria-hidden="true">{f.icon || "🍽️"}</span>}</span>
        <div className="stack">
          <div className="row">
            <label className="f">Icon<input value={f.icon} maxLength={8} style={{ width: 70, fontSize: 22 }} disabled={!owner} onChange={(e) => set("icon", e.target.value)} /></label>
            <label className="f">Diet<select value={f.diet} disabled={!owner} onChange={(e) => set("diet", e.target.value)}><option value="veg">Veg</option><option value="non_veg">Non-veg</option></select></label>
            <label className="f">Spice<select value={f.spice_level} disabled={!owner} onChange={(e) => set("spice_level", Number(e.target.value))}>{[0, 1, 2, 3].map((n) => <option key={n} value={n}>{n ? "🌶".repeat(n) : "Not spicy"}</option>)}</select></label>
          </div>
          <div className="row">
            <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={f.is_chef_pick} disabled={!owner} onChange={(e) => set("is_chef_pick", e.target.checked)} /> Chef’s pick</label>
            <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={f.is_new} disabled={!owner} onChange={(e) => set("is_new", e.target.checked)} /> New</label>
            <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={f.is_active} disabled={!owner} onChange={(e) => set("is_active", e.target.checked)} /> On the menu</label>
          </div>
          {owner && (
            <div className="row">
              <input ref={file} type="file" accept="image/*" aria-label="Dish photo" />
              <button className="btn sm" type="button" disabled={busy} onClick={upload}>Upload photo</button>
              {dish.photo && <button className="btn sm" type="button" disabled={busy} onClick={removePhoto}>Remove photo</button>}
            </div>
          )}
        </div>
      </div>
      <label className="f">Description servers and guests see<textarea rows={2} maxLength={300} value={f.description} disabled={!owner} onChange={(e) => set("description", e.target.value)} /></label>
      <label className="f">Dietary note<input value={f.dietary_note} maxLength={160} disabled={!owner} placeholder="e.g. Eggless · Gravy contains chicken stock" onChange={(e) => set("dietary_note", e.target.value)} /></label>
      <div className="stack">
        <b className="small">Allergens</b>
        <span className="small muted">From the ingredients: {dish.ingredient_allergens.length ? dish.ingredient_allergens.join(", ") : "none"}. Tick anything else the dish must declare (a sauce you buy in, cross-contact…).</span>
        <div className="row" style={{ gap: 6 }}>
          {ALLERGENS.map((a) => {
            const fromRecipe = dish.ingredient_allergens.includes(a);
            return (
              <button key={a} type="button" disabled={!owner || fromRecipe} className={`chip ${declared.includes(a) || fromRecipe ? "on" : ""}`} aria-pressed={declared.includes(a) || fromRecipe}
                title={fromRecipe ? "Comes from an ingredient" : ""} onClick={() => toggleAllergen(a)}>{a}</button>
            );
          })}
        </div>
      </div>
      <div className="stack">
        <b className="small">Options on the POS</b>
        <div className="row" style={{ gap: 6 }}>
          {(groups.data || []).map((g) => (
            <button key={g.id} type="button" disabled={!owner} className={`chip ${f.modifier_groups.includes(g.id) ? "on" : ""}`} aria-pressed={f.modifier_groups.includes(g.id)} onClick={() => toggleIn("modifier_groups", g.id)}>{g.name}</button>
          ))}
        </div>
      </div>
      <div className="stack">
        <b className="small">Servers should suggest</b>
        <select value="" disabled={!owner} aria-label="Add a suggestion" onChange={(e) => e.target.value && toggleIn("pairs_with", Number(e.target.value))}>
          <option value="">Add a dish…</option>
          {dishes.filter((d) => d.id !== dish.id && !f.pairs_with.includes(d.id)).map((d) => <option key={d.id} value={d.id}>{d.category}: {d.name}</option>)}
        </select>
        <div className="row" style={{ gap: 6 }}>
          {f.pairs_with.map((pid) => {
            const d = dishes.find((x) => x.id === pid);
            return d && <button key={pid} type="button" className="chip on" disabled={!owner} onClick={() => toggleIn("pairs_with", pid)} aria-label={`Stop suggesting ${d.name}`}>{d.icon} {d.name} ×</button>;
          })}
        </div>
      </div>
    </Card>
  );
}

/** Size, sauce and add-on choices. Each can cost extra and use stock (a double patty uses one more patty and cheese). */
function OptionGroups() {
  const { can } = useAuth();
  const owner = can("owner");
  const list = useApi("/modifier-groups/");
  const items = useApi("/items/");
  const [selId, setSelId] = useState(null);
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const sel = list.data.find((g) => g.id === selId) || list.data[0];
  return (
    <div className="split">
      <Card title="Option groups">
        <table>
          <thead><tr><th>Group</th><th>Rule</th><th className="r">Used on</th></tr></thead>
          <tbody>
            {list.data.map((g) => (
              <tr key={g.id} className={`click ${g.id === sel?.id ? "sel" : ""}`} onClick={() => setSelId(g.id)}>
                <td><b>{g.name}</b><div className="small muted">{g.options.filter((o) => o.is_active).map((o) => o.name).join(", ")}</div></td>
                <td className="small">{g.min_choices ? "Required" : "Optional"}{g.max_choices === 1 ? ", one" : g.max_choices ? `, up to ${g.max_choices}` : ", any"}</td>
                <td className="r">{g.dishes.length} dishes</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {sel && <GroupEditor key={sel.id} group={sel} items={items.data || []} owner={owner} onSaved={list.reload} />}
    </div>
  );
}

function GroupEditor({ group, items, owner, onSaved }) {
  const [g, setG] = useState({ ...group, options: group.options.filter((o) => o.is_active).map((o) => ({ ...o })) });
  const [run, busy] = useAction();
  const setOpt = (i, k, v) => setG({ ...g, options: g.options.map((o, j) => (j === i ? { ...o, [k]: v } : o)) });
  async function save() {
    const body = { name: g.name, label: g.label, min_choices: Number(g.min_choices), max_choices: Number(g.max_choices),
      options: g.options.filter((o) => o.name.trim()).map((o) => ({ id: o.id, name: o.name.trim(), price: o.price || 0, item: o.item || null, qty: o.qty || 0,
        extra_item: o.extra_item || null, extra_qty: o.extra_qty || 0, allergens: o.allergens, is_veg: o.is_veg, is_default: o.is_default, is_active: true })) };
    if (await run(() => api.put(`/modifier-groups/${group.id}/`, body), `${g.name} saved.`)) onSaved();
  }
  return (
    <Card title={group.name} actions={owner && <button className="btn primary" type="button" disabled={busy} onClick={save}>Save</button>}>
      <div className="row">
        <label className="f">Name<input value={g.name} disabled={!owner} onChange={(e) => setG({ ...g, name: e.target.value })} /></label>
        <label className="f">Guests see<input value={g.label} disabled={!owner} onChange={(e) => setG({ ...g, label: e.target.value })} /></label>
        <label className="f">Must pick<input type="number" min="0" value={g.min_choices} style={{ width: 60 }} disabled={!owner} onChange={(e) => setG({ ...g, min_choices: e.target.value })} /></label>
        <label className="f">At most (0 = any)<input type="number" min="0" value={g.max_choices} style={{ width: 60 }} disabled={!owner} onChange={(e) => setG({ ...g, max_choices: e.target.value })} /></label>
      </div>
      <div className="small muted">On: {group.dishes.map((d) => d.name).join(", ") || "no dishes yet (pick it on a dish’s menu card)"}</div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Option</th><th className="r">Extra $</th><th>Uses stock</th><th className="r">Qty</th><th>Usual</th><th /></tr></thead>
          <tbody>
            {g.options.map((o, i) => (
              <tr key={o.id || `n${i}`}>
                <td><input value={o.name} disabled={!owner} onChange={(e) => setOpt(i, "name", e.target.value)} aria-label="Option name" /></td>
                <td className="r"><NumberInput value={o.price} step="0.25" label="Extra price" disabled={!owner} onChange={(v) => setOpt(i, "price", v)} /></td>
                <td>
                  <select value={o.item || ""} disabled={!owner} aria-label="Stock item" onChange={(e) => setOpt(i, "item", e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Nothing</option>
                    {items.map((it) => <option key={it.id} value={it.id}>{it.name} ({it.unit})</option>)}
                  </select>
                </td>
                <td className="r"><NumberInput value={o.qty} step="0.01" label="Quantity used" disabled={!owner || !o.item} onChange={(v) => setOpt(i, "qty", v)} /></td>
                <td><input type="checkbox" checked={o.is_default} disabled={!owner} aria-label="Pre-selected" onChange={(e) => setOpt(i, "is_default", e.target.checked)} /></td>
                <td>{owner && <button className="btn sm" type="button" onClick={() => setG({ ...g, options: g.options.filter((_, j) => j !== i) })}>Remove</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {owner && <div><button className="btn" type="button" onClick={() => setG({ ...g, options: [...g.options, { name: "", price: 0, item: null, qty: 0, extra_item: null, extra_qty: 0, allergens: "", is_veg: true, is_default: false }] })}>Add option</button></div>}
    </Card>
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
