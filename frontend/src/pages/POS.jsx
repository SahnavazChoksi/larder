import { useMemo, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { DishInfo, MenuBrowser, OptionPicker, SuggestBar, conflictsFor, normaliseAllergies, useMenuIndex } from "../menu";
import { Card, Chips, Empty, ErrorBox, Loading, Modal, Pill, money, minutesSince, useAction, useApi, useNow } from "../ui";

function tableState(o) {
  if (!o) return "free";
  if (o.food_ready) return "ready";
  if (o.waiting_kitchen) return "cooking";
  if (o.first_sent_at) return "eating";
  return "seated";
}
const STATE_LABEL = { free: "Free", seated: "Seated, not ordered", cooking: "Waiting on kitchen", ready: "Food ready", eating: "Eating" };

export default function POS() {
  const { location, can } = useAuth();
  const floor = useApi(location.kind === "outlet" ? `/pos/floor/?location=${location.id}` : null, 15000);
  const [orderId, setOrderId] = useState(null);
  const [seating, setSeating] = useState(null);
  const [view, setView] = useState("floor");
  const now = useNow();

  if (location.kind !== "outlet") return <Card title="POS"><p className="muted" style={{ margin: 0 }}>Pick an outlet at the top to take orders.</p></Card>;
  if (orderId) return <OrderScreen id={orderId} onBack={() => { setOrderId(null); floor.reload(); }} />;
  if (floor.error) return <ErrorBox>{floor.error}</ErrorBox>;
  if (!floor.data) return <Loading />;
  const { tables, orders } = floor.data;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Chips options={[["floor", "Floor plan"], ["other", `Takeout & online (${orders.length})`], ...(can("manager") ? [["tables", "Edit tables"]] : [])]} value={view} onChange={setView} />
        <div className="legend">{Object.entries(STATE_LABEL).map(([k, l]) => <span key={k}><i className={`tbl ${k}`} style={{ display: "inline-block", width: 12, height: 12, padding: 0 }} />{l}</span>)}</div>
      </div>
      {view === "floor" && (
        <div className="floor">
          {tables.map((t) => {
            const st = tableState(t.order);
            const mins = t.order ? Math.round(minutesSince(t.order.opened_at, now)) : null;
            return (
              <button key={t.id} type="button" className={`tbl ${st} ${t.shape === "round" ? "round" : ""}`}
                style={{ gridColumn: `${t.x + 1} / span ${t.shape === "long" ? 2 : 1}`, gridRow: t.y + 1 }}
                onClick={() => (t.order ? setOrderId(t.order.id) : setSeating(t))} title={STATE_LABEL[st]}>
                <b>{t.name}</b>
                {t.order ? <span>{t.order.guests} · {mins} min</span> : <span className="muted">{t.seats} seats</span>}
                {t.order && <span>{money(t.order.total, 0)}</span>}
              </button>
            );
          })}
        </div>
      )}
      {view === "other" && <OtherOrders orders={orders} onOpen={setOrderId} onNew={(id) => setOrderId(id)} location={location} />}
      {view === "tables" && <TableEditor location={location} tables={tables} onSaved={floor.reload} />}
      {seating && <SeatDialog table={seating} location={location} onClose={() => setSeating(null)} onDone={(id) => { setSeating(null); setOrderId(id); }} />}
    </>
  );
}

function SeatDialog({ table, location, onClose, onDone }) {
  const [guests, setGuests] = useState(Math.min(2, table.seats));
  const [run, busy] = useAction();
  async function seat() {
    const res = await run(() => api.post("/pos/orders/", { location: location.id, table: table.id, guests, type: "dine_in" }));
    if (res) onDone(res.id);
  }
  return (
    <Modal title={`Seat ${table.name}`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={seat}>Open check</button></>}>
      <div className="row">
        <span>Guests</span>
        <button className="qtybtn" type="button" onClick={() => setGuests(Math.max(1, guests - 1))} aria-label="Fewer guests">−</button>
        <b className="big-timer">{guests}</b>
        <button className="qtybtn" type="button" onClick={() => setGuests(guests + 1)} aria-label="More guests">+</button>
        <span className="small muted">{table.seats} seats{guests >= 6 ? " · service charge applies" : ""}</span>
      </div>
    </Modal>
  );
}

function OtherOrders({ orders, onOpen, onNew, location }) {
  const [name, setName] = useState("");
  const [run, busy] = useAction();
  async function create(e) {
    e.preventDefault();
    const res = await run(() => api.post("/pos/orders/", { location: location.id, type: "takeout", customer_name: name }));
    if (res) { setName(""); onNew(res.id); }
  }
  return (
    <Card title="Takeout, online and delivery">
      <form className="row" onSubmit={create}>
        <label className="f">Customer name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="For the bag label" /></label>
        <button className="btn primary" type="submit" disabled={busy}>New takeout order</button>
      </form>
      {!orders.length ? <Empty>No open takeout or online orders.</Empty> : (
        <table>
          <thead><tr><th>Order</th><th>Type</th><th>Customer</th><th className="r">Total</th><th>Opened</th><th /></tr></thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} className="click" onClick={() => onOpen(o.id)}>
                <td><b>{o.number}</b></td><td><Pill kind={o.type === "online" ? "info" : "neutral"}>{o.type_label}</Pill></td>
                <td>{o.customer_name || "—"}</td><td className="r">{money(o.total)}</td>
                <td className="small muted">{new Date(o.opened_at).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</td>
                <td className="r"><button className="btn sm" type="button">Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function OrderScreen({ id, onBack }) {
  const { can } = useAuth();
  const { data: order, error, reload } = useApi(`/pos/orders/${id}/`);
  const menuApi = useApi("/pos/menu/");
  const menu = useMenuIndex(menuApi.data);
  const [dialog, setDialog] = useState(null);
  const [picking, setPicking] = useState(null);   // dish whose options are open
  const [info, setInfo] = useState(null);         // dish whose details are open
  const [last, setLast] = useState(null);         // last dish added, for "suggest with"
  const [avoidOverride, setAvoid] = useState(null);
  const [run, busy] = useAction();

  const guestText = order?.guest_profile?.allergies || "";
  const guestAvoid = useMemo(() => normaliseAllergies(guestText, menu?.allergens), [guestText, menu]);
  const avoid = avoidOverride ?? guestAvoid;
  if (error) return <><button className="btn" type="button" onClick={onBack}>← Floor</button><ErrorBox>{error}</ErrorBox></>;
  if (!order) return <Loading />;
  const open = order.status === "open";
  const newLines = order.lines.filter((l) => l.status === "new");
  const inOrder = new Set(order.lines.filter((l) => l.status !== "void").map((l) => l.menu_item));

  const act = async (fn, msg) => { const ok = await run(fn, msg); if (ok) reload(); return ok; };
  const post = (dish, modifiers = [], qtyN = 1, note = "") =>
    act(() => api.post(`/pos/orders/${id}/lines/`, { menu_item: dish.id, qty: qtyN, modifiers, note }), `${qtyN > 1 ? `${qtyN} × ` : ""}${dish.name} added.`);
  // Tap: straight in unless it needs a choice, or the guest is allergic (then confirm in the picker)
  const tap = (dish) => {
    const needsChoice = dish.groups.some((g) => menu.groups[g]?.min > 0);
    if (needsChoice || conflictsFor(dish.allergens, avoid).length) setPicking(dish);
    else post(dish).then((ok) => ok && setLast(dish));
  };
  const customise = (dish) => setPicking(dish);
  const qty = (l, q) => act(() => api.patch(`/pos/orders/${id}/lines/${l.id}/`, { qty: q }));
  const send = () => act(() => api.post(`/pos/orders/${id}/send/`), "Sent to the kitchen.");
  const guests = (n) => act(() => api.patch(`/pos/orders/${id}/`, { guests: n }));

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <button className="btn" type="button" onClick={onBack}>← Floor</button>
        <div className="row">
          <Pill kind={open ? "info" : order.status === "closed" ? "good" : "neutral"}>{order.status_label}</Pill>
          <b>{order.table_name ? `Table ${order.table_name}` : order.type_label} · {order.number}</b>
        </div>
      </div>
      <div className="pos">
        <Card title="Menu">
          {menuApi.error ? <ErrorBox>{menuApi.error}</ErrorBox> : !menu ? <Loading /> : (
            <>
              <SuggestBar dish={last} menu={menu} avoid={avoid} inOrder={inOrder} onAdd={tap} />
              <MenuBrowser menu={menu} avoid={avoid} setAvoid={setAvoid} guestAvoid={avoidOverride ? null : guestAvoid}
                onTap={tap} onInfo={setInfo} onCustomise={customise} disabled={!open || busy} />
            </>
          )}
        </Card>
        <Card title="Check">
          <div className="row" style={{ justifyContent: "space-between" }}>
            {order.type === "dine_in" ? (
              <div className="row">
                <span className="small muted">Guests</span>
                <button className="qtybtn" type="button" disabled={!open} onClick={() => guests(Math.max(1, order.guests - 1))} aria-label="Fewer guests">−</button>
                <b>{order.guests}</b>
                <button className="qtybtn" type="button" disabled={!open} onClick={() => guests(order.guests + 1)} aria-label="More guests">+</button>
              </div>
            ) : <span>{order.customer_name || "Walk-in"} {order.channel !== "larder" && <Pill>{order.channel}</Pill>}</span>}
            <GuestTag order={order} onChange={reload} />
          </div>
          {order.guest_profile?.allergies && <div className="note error">Allergy: {order.guest_profile.allergies}</div>}
          {!order.lines.length ? <Empty>Tap dishes to add them.</Empty> : order.lines.map((l) => (
            <div key={l.id} className={`check-line ${l.status === "void" ? "void" : ""}`}>
              {l.status === "new" && open ? (
                <span className="row" style={{ flexWrap: "nowrap", gap: 4 }}>
                  <button className="qtybtn" type="button" onClick={() => qty(l, l.qty - 1)} aria-label="One fewer">−</button>
                  <b>{l.qty}</b>
                  <button className="qtybtn" type="button" onClick={() => qty(l, l.qty + 1)} aria-label="One more">+</button>
                </span>
              ) : <b>{l.qty}×</b>}
              <span>
                {l.name}
                {l.modifiers?.length > 0 && <span className="small mods">{l.modifiers.map((m) => m.name).join(", ")}</span>}
                {l.note && <span className="small muted"> · {l.note}</span>}
                {l.status === "sent" && <span className="small muted"> · sent</span>}
                {l.status === "void" && <span className="small"> · void ({l.void_reason || "removed"})</span>}
              </span>
              <span className="row" style={{ flexWrap: "nowrap" }}>
                {money(l.qty * l.unit_price)}
                {open && l.status !== "void" && (
                  <button className="btn sm" type="button" title={l.status === "sent" ? "Needs a manager" : "Add a note"} onClick={() => setDialog({ type: l.status === "new" ? "note" : "void", line: l })}>
                    {l.status === "new" ? "Note" : "Void"}
                  </button>
                )}
              </span>
            </div>
          ))}
          <table className="totals">
            <tbody>
              <tr><td>Subtotal</td><td className="r">{money(order.subtotal)}</td></tr>
              {order.discount > 0 && <tr><td>Discount <span className="small muted">{order.discount_reason}</span></td><td className="r">−{money(order.discount)}</td></tr>}
              {order.service_charge_rate > 0 && (
                <tr><td>Service charge {(order.service_charge_rate * 100).toFixed(0)}% {order.service_charge_removed && <Pill kind="warn">Removed: {order.service_charge_removed_reason}</Pill>}</td>
                  <td className="r">{money(order.service_charge)}</td></tr>
              )}
              <tr><td>HST {(order.tax_rate * 100).toFixed(0)}%</td><td className="r">{money(order.tax)}</td></tr>
              <tr><td><b>Total</b></td><td className="r"><b>{money(order.total)}</b></td></tr>
              {order.paid > 0 && <tr><td>Paid</td><td className="r">{money(order.paid)}</td></tr>}
              {order.tips > 0 && <tr><td>Tips</td><td className="r">{money(order.tips)}</td></tr>}
              {open && order.paid > 0 && <tr><td><b>Left to pay</b></td><td className="r"><b>{money(order.balance)}</b></td></tr>}
            </tbody>
          </table>
          {open ? (
            <>
              <div className="row">
                <button className="btn primary" type="button" disabled={!newLines.length || busy} onClick={send}>Send to kitchen{newLines.length ? ` (${newLines.reduce((s, l) => s + l.qty, 0)})` : ""}</button>
                <button className="btn primary" type="button" disabled={!order.lines.length || busy} onClick={() => setDialog({ type: "pay" })}>Pay</button>
              </div>
              <div className="row">
                {order.service_charge_rate > 0 && !order.service_charge_removed && <button className="btn sm" type="button" onClick={() => setDialog({ type: "sc" })}>Remove service charge</button>}
                {order.guest_profile?.is_member && <button className="btn sm" type="button" onClick={() => setDialog({ type: "redeem" })}>Redeem points ({order.guest_profile.points})</button>}
                {can("manager") && <button className="btn sm" type="button" onClick={() => setDialog({ type: "discount" })}>Discount</button>}
                {can("manager") && !order.paid && <button className="btn sm danger" type="button" onClick={() => setDialog({ type: "voidorder" })}>Void order</button>}
              </div>
            </>
          ) : (
            <div className="row"><button className="btn" type="button" onClick={() => printReceipt(order)}>Print receipt</button></div>
          )}
          {order.tickets.length > 0 && (
            <div className="small muted">Kitchen: {order.tickets.map((t) => t.status_label).join(", ")}</div>
          )}
          {order.payments.length > 0 && (
            <div className="small muted">Payments: {order.payments.map((p) => `${p.method_label} ${money(p.amount)}${p.tip ? ` + ${money(p.tip)} tip` : ""}${p.refunded_amount ? ` (refunded ${money(p.refunded_amount)})` : ""}`).join(" · ")}</div>
          )}
        </Card>
      </div>
      {picking && menu && (
        <OptionPicker dish={picking} menu={menu} avoid={avoid} busy={busy} onClose={() => setPicking(null)}
          onAdd={async (dish, mods, n, note) => { if (await post(dish, mods, n, note)) { setPicking(null); setLast(dish); } }} />
      )}
      {info && menu && (
        <DishInfo dish={info} menu={menu} avoid={avoid} onClose={() => setInfo(null)}
          onAdd={open ? (dish) => { setInfo(null); dish.groups.length ? customise(dish) : tap(dish); } : null} />
      )}
      {dialog?.type === "pay" && <PayDialog order={order} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
      {dialog && dialog.type !== "pay" && <SmallDialog dialog={dialog} order={order} onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload(); }} />}
    </>
  );
}

function GuestTag({ order, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const results = useApi(open && q.length >= 2 ? `/guests/?q=${encodeURIComponent(q)}` : null);
  const [run] = useAction();
  async function attach(g) {
    if (await run(() => api.patch(`/pos/orders/${order.id}/`, { guest: g ? g.id : null }))) { setOpen(false); onChange(); }
  }
  const g = order.guest_profile;
  return (
    <>
      <button className="btn sm" type="button" disabled={order.status !== "open"} onClick={() => setOpen(true)}>
        {g ? `${g.name}${g.is_member ? ` · ${g.points} pts` : ""}` : "Add guest"}
      </button>
      {open && (
        <Modal title="Find guest" onClose={() => setOpen(false)} footer={<>{g && <button className="btn" type="button" onClick={() => attach(null)}>Remove guest</button>}<button className="btn" type="button" onClick={() => setOpen(false)}>Close</button></>}>
          <input autoFocus placeholder="Name or phone" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search guests" />
          {(results.data || []).map((x) => (
            <button key={x.id} type="button" className="btn" style={{ justifyContent: "space-between" }} onClick={() => attach(x)}>
              <span>{x.name} <span className="small muted">{x.phone}</span></span>{x.is_member && <Pill kind="accent">{x.points} pts</Pill>}
            </button>
          ))}
          {q.length >= 2 && results.data?.length === 0 && <span className="small muted">No match. Add them under Guests.</span>}
        </Modal>
      )}
    </>
  );
}

function SmallDialog({ dialog, order, onClose, onDone }) {
  const [text, setText] = useState(dialog.line?.note || "");
  const [amount, setAmount] = useState("");
  const [run, busy] = useAction();
  const cfg = {
    note: { title: `Note for ${dialog.line?.name}`, label: "Note for the kitchen", call: () => api.patch(`/pos/orders/${order.id}/lines/${dialog.line.id}/`, { note: text }) },
    void: { title: `Void ${dialog.line?.name}`, label: "Why? (kitchen error, guest changed mind…)", call: () => api.post(`/pos/orders/${order.id}/lines/${dialog.line.id}/void/`, { reason: text }), msg: "Item voided." },
    sc: { title: "Remove service charge", label: "Why did the guest ask?", call: () => api.post(`/pos/orders/${order.id}/service-charge/`, { reason: text }), msg: "Service charge removed." },
    discount: { title: "Discount", label: "Reason", amount: true, call: () => api.post(`/pos/orders/${order.id}/discount/`, { amount, reason: text }), msg: "Discount applied." },
    redeem: { title: "Redeem loyalty points", label: null, rewards: true, call: () => api.post(`/pos/orders/${order.id}/redeem/`, { rewards: amount || 1 }), msg: "Reward applied." },
    voidorder: { title: `Void order ${order.number}`, label: "Why?", call: () => api.post(`/pos/orders/${order.id}/void/`, { reason: text }), msg: "Order voided." },
  }[dialog.type];
  async function save() {
    if (await run(cfg.call, cfg.msg)) onDone();
  }
  return (
    <Modal title={cfg.title} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={save}>Save</button></>}>
      {cfg.amount && <label className="f">Amount ($)<input type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>}
      {cfg.rewards && <label className="f">Rewards to use<input type="number" step="1" min="1" value={amount || 1} onChange={(e) => setAmount(e.target.value)} /></label>}
      {cfg.label && <label className="f">{cfg.label}<input autoFocus value={text} onChange={(e) => setText(e.target.value)} /></label>}
    </Modal>
  );
}

function PayDialog({ order, onClose, onDone }) {
  const providers = useApi("/pos/providers/");
  const [method, setMethod] = useState("card");
  const [amount, setAmount] = useState(order.balance.toFixed(2));
  const [tip, setTip] = useState("");
  const [tendered, setTendered] = useState("");
  const [reference, setReference] = useState("");
  const [run, busy] = useAction();
  const provider = (providers.data || []).find((p) => p.methods.includes(method)) || { key: "manual" };
  const change = method === "cash" && tendered ? Number(tendered) - Number(amount || 0) - Number(tip || 0) : null;

  async function pay() {
    const res = await run(() => api.post(`/pos/orders/${order.id}/payments/`, {
      provider: provider.key, method, amount, tip: tip || 0, cash_tendered: method === "cash" ? tendered || null : null, reference,
    }), (d) => (d.closed ? "Paid in full. Table closed." : d.payment.status === "approved" ? "Payment taken." : d.message || "Waiting for the card reader."));
    if (res) onDone(res.closed);
  }

  return (
    <Modal title={`Pay ${order.number} · ${money(order.balance)} left`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy || !(Number(amount) > 0)} onClick={pay}>Take {money(Number(amount || 0) + Number(tip || 0))}</button></>}>
      <Chips options={[["card", "Card"], ["cash", "Cash"], ["gift", "Gift card"], ["other", "Other"]]} value={method} onChange={setMethod} />
      <div className="row">
        <label className="f">Amount<input type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <div className="row">
          {[2, 3, 4].map((n) => <button key={n} className="btn sm" type="button" onClick={() => setAmount((Math.ceil((order.balance / n) * 100) / 100).toFixed(2))}>Split ÷{n}</button>)}
        </div>
      </div>
      {!order.service_charge_rate || order.service_charge_removed ? (
        <div className="row">
          <label className="f">Tip<input type="number" step="0.01" min="0" value={tip} onChange={(e) => setTip(e.target.value)} /></label>
          {[0.15, 0.18, 0.2].map((p) => <button key={p} className="btn sm" type="button" onClick={() => setTip((Number(amount || 0) * p).toFixed(2))}>{p * 100}%</button>)}
        </div>
      ) : <span className="small muted">Service charge already added; no tip prompt.</span>}
      {method === "cash" && (
        <div className="row">
          <label className="f">Cash given<input type="number" step="0.05" min="0" value={tendered} onChange={(e) => setTendered(e.target.value)} /></label>
          {change != null && <b className={change < 0 ? "worse" : ""}>Change {money(Math.max(0, change))}{change < 0 ? " (not enough)" : ""}</b>}
        </div>
      )}
      {method === "card" && provider.key === "manual" && (
        <label className="f">Terminal approval code (optional)<input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="From the card terminal slip" /></label>
      )}
      <span className="small muted">{provider.key === "manual" ? "Run the card on your card terminal, then confirm here. Larder never sees card numbers." : `Paying with ${provider.label}.`}</span>
    </Modal>
  );
}

function printReceipt(o) {
  const w = window.open("", "_blank", "width=380,height=640");
  if (!w) return;
  const rows = o.lines.filter((l) => l.status !== "void").map((l) => `<tr><td>${l.qty}× ${escapeHtml(l.name)}${l.modifiers?.length ? `<br><small>&nbsp;&nbsp;${escapeHtml(l.modifiers.map((m) => m.name).join(", "))}</small>` : ""}</td><td style="text-align:right">${money(l.qty * l.unit_price)}</td></tr>`).join("");
  w.document.write(`<html><head><title>Receipt ${o.number}</title><style>body{font-family:monospace;font-size:13px;padding:12px}table{width:100%}td{padding:2px 0}</style></head><body>
    <h3 style="text-align:center;margin:0">${escapeHtml(o.location_name)}</h3><p style="text-align:center">Order ${o.number} · ${new Date(o.closed_at || Date.now()).toLocaleString("en-CA")}</p>
    <table>${rows}<tr><td colspan=2><hr></td></tr>
    <tr><td>Subtotal</td><td style="text-align:right">${money(o.subtotal)}</td></tr>
    ${o.discount > 0 ? `<tr><td>Discount</td><td style="text-align:right">-${money(o.discount)}</td></tr>` : ""}
    ${o.service_charge > 0 ? `<tr><td>Service charge</td><td style="text-align:right">${money(o.service_charge)}</td></tr>` : ""}
    <tr><td>HST</td><td style="text-align:right">${money(o.tax)}</td></tr>
    <tr><td><b>Total</b></td><td style="text-align:right"><b>${money(o.total)}</b></td></tr>
    ${o.tips > 0 ? `<tr><td>Tip</td><td style="text-align:right">${money(o.tips)}</td></tr>` : ""}</table>
    <p style="text-align:center">Thank you!</p><script>window.print()</script></body></html>`);
  w.document.close();
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function TableEditor({ location, tables, onSaved }) {
  const [rows, setRows] = useState(tables.map((t) => ({ ...t })));
  const [run, busy] = useAction();
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  async function save(r) {
    const body = { location: location.id, name: r.name, area: r.area, seats: Number(r.seats), x: Number(r.x), y: Number(r.y), shape: r.shape, is_active: r.is_active ?? true };
    const ok = await run(() => (r.id ? api.patch(`/pos/tables/${r.id}/`, body) : api.post("/pos/tables/", body)), `${r.name} saved.`);
    if (ok) onSaved();
  }
  return (
    <Card title="Tables">
      <p className="small muted" style={{ margin: 0 }}>Position is on a 12 × 8 grid: across 0–11, down 0–7. Long tables take two squares.</p>
      <table>
        <thead><tr><th>Name</th><th>Area</th><th>Seats</th><th>Across</th><th>Down</th><th>Shape</th><th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || `n${i}`}>
              <td><input value={r.name} style={{ width: 70 }} onChange={(e) => set(i, "name", e.target.value)} aria-label="Table name" /></td>
              <td><input value={r.area} style={{ width: 90 }} onChange={(e) => set(i, "area", e.target.value)} aria-label="Area" /></td>
              <td><input type="number" min="1" value={r.seats} onChange={(e) => set(i, "seats", e.target.value)} aria-label="Seats" /></td>
              <td><input type="number" min="0" max="11" value={r.x} onChange={(e) => set(i, "x", e.target.value)} aria-label="Across" /></td>
              <td><input type="number" min="0" max="7" value={r.y} onChange={(e) => set(i, "y", e.target.value)} aria-label="Down" /></td>
              <td><select value={r.shape} onChange={(e) => set(i, "shape", e.target.value)} aria-label="Shape"><option value="square">Square</option><option value="round">Round</option><option value="long">Long</option></select></td>
              <td><button className="btn sm" type="button" disabled={busy} onClick={() => save(r)}>Save</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div><button className="btn" type="button" onClick={() => setRows([...rows, { name: "", area: "Main", seats: 4, x: 0, y: 0, shape: "square" }])}>Add table</button></div>
    </Card>
  );
}
