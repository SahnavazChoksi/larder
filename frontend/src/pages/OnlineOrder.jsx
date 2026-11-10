import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import api, { errorText } from "../api";
import { Card, Chips, Empty, Loading, money } from "../ui";

const STATES = { received: "Order received", cooking: "Being cooked", ready: "Ready for pickup", picked_up: "Picked up. Enjoy!", cancelled: "Cancelled" };

/** Public pickup-ordering page: /order/<location code>. No login. */
export default function OnlineOrder() {
  const { code } = useParams();
  const [menu, setMenu] = useState(null);
  const [error, setError] = useState("");
  const [cart, setCart] = useState({});
  const [cat, setCat] = useState(null);
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

  const items = useMemo(() => (menu ? menu.menu : []), [menu]);
  const categories = [...new Set(items.map((m) => m.category))];
  const lines = items.filter((m) => cart[m.id]);
  const subtotal = lines.reduce((s, m) => s + m.price * cart[m.id], 0);
  const add = (m, n) => setCart((c) => ({ ...c, [m.id]: Math.max(0, (c[m.id] || 0) + n) }));

  async function place(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post(`/public/orders/${code}/`, { ...form, lines: lines.map((m) => ({ menu_item: m.id, qty: cart[m.id] })) });
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
  const active = cat || categories[0];
  return (
    <div className="public">
      <div className="brand"><div className="brand-mark">L</div><div><b>{menu.location.name}</b><span>Order for pickup · {menu.location.city}</span></div></div>
      <Chips options={categories.map((c) => [c, c])} value={active} onChange={setCat} />
      <div className="menu-grid">
        {items.filter((m) => m.category === active).map((m) => (
          <div key={m.id} className="menu-btn">
            <b>{m.name}</b>
            {m.allergens.length > 0 && <span className="small muted">Contains {m.allergens.join(", ")}</span>}
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span>{money(m.price)}</span>
              <span className="row" style={{ flexWrap: "nowrap", gap: 4 }}>
                {cart[m.id] > 0 && <><button className="qtybtn" type="button" onClick={() => add(m, -1)} aria-label={`Remove one ${m.name}`}>−</button><b>{cart[m.id]}</b></>}
                <button className="qtybtn" type="button" onClick={() => add(m, 1)} aria-label={`Add ${m.name}`}>+</button>
              </span>
            </div>
          </div>
        ))}
      </div>
      <Card title="Your order">
        {!lines.length ? <Empty>Add something tasty.</Empty> : (
          <>
            <table><tbody>{lines.map((m) => <tr key={m.id}><td>{cart[m.id]}× {m.name}</td><td className="r">{money(m.price * cart[m.id])}</td></tr>)}
              <tr><td>Tax</td><td className="r">{money(subtotal * menu.location.tax_rate)}</td></tr>
              <tr><td><b>Total</b></td><td className="r"><b>{money(subtotal * (1 + menu.location.tax_rate))}</b></td></tr></tbody></table>
            <form onSubmit={place} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row">
                <label className="f">Name<input value={form.name} required onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
                <label className="f">Phone<input value={form.phone} required type="tel" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
              </div>
              <label className="f">Notes for the kitchen<input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Spice level, allergies…" /></label>
              {error && <div className="note error">{error}</div>}
              <button className="btn primary" type="submit" disabled={busy}>{busy ? "Placing…" : "Place order · pay at pickup"}</button>
            </form>
          </>
        )}
      </Card>
    </div>
  );
}
