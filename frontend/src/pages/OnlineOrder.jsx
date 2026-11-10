import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import api, { errorText } from "../api";
import { DishInfo, MenuBrowser, OptionPicker, SuggestBar, useMenuIndex } from "../menu";
import { Card, Empty, Loading, money } from "../ui";

const STATES = { received: "Order received", cooking: "Being cooked", ready: "Ready for pickup", picked_up: "Picked up. Enjoy!", cancelled: "Cancelled" };

/** Public pickup-ordering page: /order/<location code>. No login. */
export default function OnlineOrder() {
  const { code } = useParams();
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState("");
  const [cart, setCart] = useState([]);          // [{key, dish, mods: [ids], qty, note}]
  const [picking, setPicking] = useState(null);
  const [info, setInfo] = useState(null);
  const [last, setLast] = useState(null);
  const [avoid, setAvoid] = useState(() => new Set());
  const [form, setForm] = useState({ name: "", phone: "", note: "" });
  const [placed, setPlaced] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/public/menu/${code}/`).then((r) => setMenu(r.data)).catch((e) => setError(errorText(e)));
  }, [code]);
  useEffect(() => {
    if (!placed) return;
    const load = () => api.get(`/public/order-status/${placed.token}/`).then((r) => setStatus(r.data)).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [placed]);

  const index = useMenuIndex(menu);
  const options = useMemo(() => {
    const out = {};
    for (const g of Object.values(index?.groups || {})) for (const o of g.options) out[o.id] = o;
    return out;
  }, [index]);
  const unit = (l) => l.dish.price + l.mods.reduce((s, id) => s + (options[id]?.price || 0), 0);
  const subtotal = cart.reduce((s, l) => s + unit(l) * l.qty, 0);
  const put = (dish, mods = [], qty = 1, note = "") => {
    const key = `${dish.id}:${[...mods].sort().join(",")}:${note}`;
    setCart((c) => (c.some((l) => l.key === key) ? c.map((l) => (l.key === key ? { ...l, qty: Math.min(20, l.qty + qty) } : l)) : [...c, { key, dish, mods, qty, note }]));
    setLast(dish);
  };
  const bump = (key, n) => setCart((c) => c.map((l) => (l.key === key ? { ...l, qty: l.qty + n } : l)).filter((l) => l.qty > 0));
  const tap = (dish) => (dish.groups.length ? setPicking(dish) : put(dish));

  async function place(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/public/orders/${code}/`, { ...form, lines: cart.map((l) => ({ menu_item: l.dish.id, qty: l.qty, modifiers: l.mods, note: l.note })) });
      setPlaced(data);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (error && !menu) return <div className="public"><div className="note error">{error}</div></div>;
  if (!menu) return <div className="public"><Loading /></div>;
  if (placed) {
    return (
      <div className="public">
        <h1>Thanks, {form.name}!</h1>
        <Card title={`Order ${placed.number} · ${menu.location.name}`}>
          <p style={{ margin: 0, fontSize: 20 }}><b>{STATES[status?.state] || "Order received"}</b></p>
          <p className="muted" style={{ margin: 0 }}>Usually ready in about {placed.estimate_minutes} minutes. Pay when you pick up: {money(placed.total)} incl. tax.</p>
          {status?.items && <ul>{status.items.map((i, k) => <li key={k}>{i.qty}× {i.name}</li>)}</ul>}
          <p className="small muted" style={{ margin: 0 }}>This page updates by itself.</p>
        </Card>
      </div>
    );
  }
  return (
    <div className="public">
      <div className="brand"><div className="brand-mark">L</div><div><b>{menu.location.name}</b><span>Order for pickup · {menu.location.city}</span></div></div>
      <SuggestBar dish={last} menu={index} avoid={avoid} inOrder={new Set(cart.map((l) => l.dish.id))} onAdd={tap} />
      <MenuBrowser menu={index} avoid={avoid} setAvoid={setAvoid} onTap={tap} onInfo={setInfo} onCustomise={setPicking} />
      {picking && <OptionPicker dish={picking} menu={index} avoid={avoid} onClose={() => setPicking(null)}
        onAdd={(dish, mods, qty, note) => { put(dish, mods, qty, note); setPicking(null); }} />}
      {info && <DishInfo dish={info} menu={index} avoid={avoid} staff={false} onClose={() => setInfo(null)} onAdd={(d) => { setInfo(null); tap(d); }} />}
      <Card title="Your order">
        {!cart.length ? <Empty>Add something tasty.</Empty> : (
          <>
            <table><tbody>{cart.map((l) => (
              <tr key={l.key}>
                <td>
                  <span className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                    <button className="qtybtn" type="button" onClick={() => bump(l.key, -1)} aria-label={`One fewer ${l.dish.name}`}>−</button>
                    <b>{l.qty}</b>
                    <button className="qtybtn" type="button" onClick={() => bump(l.key, 1)} aria-label={`One more ${l.dish.name}`}>+</button>
                    <span>{l.dish.name}</span>
                  </span>
                  {(l.mods.length > 0 || l.note) && <span className="small mods">{[...l.mods.map((id) => options[id]?.name), l.note].filter(Boolean).join(", ")}</span>}
                </td>
                <td className="r">{money(unit(l) * l.qty)}</td>
              </tr>
            ))}
              <tr><td>Tax</td><td className="r">{money(subtotal * menu.location.tax_rate)}</td></tr>
              <tr><td><b>Total</b></td><td className="r"><b>{money(subtotal * (1 + menu.location.tax_rate))}</b></td></tr></tbody></table>
            <form onSubmit={place} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row">
                <label className="f">Name<input value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
                <label className="f">Phone<input value={form.phone} required type="tel" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
              </div>
              <label className="f">Notes for the kitchen<input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Anything we should know? Tell us about allergies here too" /></label>
              {error && <div className="note error">{error}</div>}
              <button className="btn primary" type="submit" disabled={busy}>{busy ? "Placing…" : "Place order · pay at pickup"}</button>
            </form>
          </>
        )}
      </Card>
    </div>
  );
}
