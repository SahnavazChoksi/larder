/* The POS while the server can't be reached: same menu and tables, orders kept on this tablet until it's back. */
import { useMemo, useState } from "react";
import { DishInfo, MenuBrowser, OptionPicker, conflictsFor, useMenuIndex } from "../menu";
import * as off from "../offline";
import { Card, Chips, Empty, Modal, Pill, money, useToast } from "../ui";

const SYNC = {
  pending: ["warn", "Waiting to upload"],
  synced: ["good", "Uploaded"],
  open: ["info", "Uploaded, still open"],
  error: ["bad", "Needs attention"],
};

function time(iso) {
  return iso ? new Date(iso).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" }) : "";
}

export function SyncPill({ o }) {
  const [kind, label] = SYNC[o.sync.status] || SYNC.pending;
  return <Pill kind={kind}>{label}{o.sync.number ? ` as ${o.sync.number}` : ""}</Pill>;
}

/** List of orders this tablet took offline, with upload status. Shown offline, and online until they're all in. */
export function OfflineOrders({ location, onOpen }) {
  const { outbox, syncing, online } = off.useOffline();
  const mine = outbox.filter((o) => o.location === location.id).slice().reverse();
  const toast = useToast();
  if (!mine.length) return <Empty>No orders taken offline on this tablet.</Empty>;
  return (
    <div className="tablewrap">
      <table>
        <thead><tr><th>Order</th><th>Table / name</th><th>Opened</th><th className="r">Items</th><th>Status</th><th /></tr></thead>
        <tbody>
          {mine.map((o) => (
            <tr key={o.client_id} className={onOpen && !o.closed_at && o.sync.status === "pending" ? "click" : ""}
              onClick={() => onOpen && !o.closed_at && o.sync.status === "pending" && onOpen(o.client_id)}>
              <td><b>{o.local_no}</b>{o.closed_at && <div className="small muted">Paid {time(o.closed_at)}</div>}</td>
              <td>{o.table_name ? `Table ${o.table_name}` : o.customer_name || "Takeout"}</td>
              <td className="small">{time(o.opened_at)}</td>
              <td className="r">{o.lines.reduce((s, l) => s + l.qty, 0)}</td>
              <td><SyncPill o={o} />{o.sync.message && <div className="small worse">{o.sync.message}</div>}
                {o.sync.status === "open" && o.sync.balance > 0 && <div className="small muted">{money(o.sync.balance)} left to pay: open it on the floor plan</div>}</td>
              <td className="r">
                {o.sync.status === "error" && online && (
                  <button className="btn sm" type="button" disabled={syncing} onClick={(e) => { e.stopPropagation(); off.retry(o.client_id).then(() => toast("Tried again.")); }}>Try again</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OfflinePOS({ location }) {
  const kit = useMemo(() => off.loadKit(location.id), [location.id]);
  const { outbox } = off.useOffline();
  const [openId, setOpenId] = useState(null);
  const [view, setView] = useState("floor");
  const [seating, setSeating] = useState(null);
  const toast = useToast();

  if (!kit) {
    return (
      <Card title="Offline">
        <p style={{ margin: 0 }}>This tablet hasn’t saved {location.name}’s menu yet, so it can’t take orders offline.</p>
        <p className="small muted" style={{ margin: 0 }}>Open the POS once while the connection works; it saves a copy automatically. Until then, use paper tickets and the card terminal.</p>
      </Card>
    );
  }
  const current = outbox.find((o) => o.client_id === openId);
  if (current) return <OfflineOrder order={current} kit={kit} onBack={() => setOpenId(null)} />;

  const openHere = outbox.filter((o) => o.location === location.id && !o.closed_at && o.sync.status === "pending");
  const busy = Object.fromEntries(openHere.filter((o) => o.table).map((o) => [o.table, o]));
  function start(fields) {
    try {
      const o = off.newOrder({ location: location.id, ...fields });
      setOpenId(o.client_id);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  return (
    <>
      <div className="note warn-box">
        <b>Offline.</b> Orders are saved on this tablet and upload by themselves when the connection is back.
        The kitchen screen can’t see them: <b>print a kitchen ticket</b> for every send. Take card payments on the card terminal.
        <span className="small muted"> Menu saved {new Date(kit.saved_at).toLocaleString("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}.</span>
      </div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Chips options={[["floor", "Floor plan"], ["orders", `Offline orders (${outbox.filter((o) => o.location === location.id).length})`]]} value={view} onChange={setView} />
        <button className="btn primary" type="button" onClick={() => start({ type: "takeout", customerName: "" })}>New takeout order</button>
      </div>
      {view === "floor" && (
        <div className="floor">
          {kit.tables.map((t) => {
            const o = busy[t.id];
            return (
              <button key={t.id} type="button" className={`tbl ${o ? (o.lines.some((l) => l.sent_at) ? "eating" : "seated") : "free"} ${t.shape === "round" ? "round" : ""}`}
                style={{ gridColumn: `${t.x + 1} / span ${t.shape === "long" ? 2 : 1}`, gridRow: t.y + 1 }}
                onClick={() => (o ? setOpenId(o.client_id) : setSeating(t))}>
                <b>{t.name}</b>
                {o ? <span>{o.guests} · {o.local_no}</span> : <span className="muted">{t.seats} seats</span>}
              </button>
            );
          })}
        </div>
      )}
      {view === "orders" && <Card title="Taken offline on this tablet"><OfflineOrders location={location} onOpen={setOpenId} /></Card>}
      {seating && (
        <SeatOffline table={seating} onClose={() => setSeating(null)}
          onSeat={(guests) => { setSeating(null); start({ type: "dine_in", table: seating.id, tableName: seating.name, guests }); }} />
      )}
      <p className="small muted">Tables that are busy on the server aren’t shown as busy here. Check the room before seating.</p>
    </>
  );
}

function SeatOffline({ table, onClose, onSeat }) {
  const [guests, setGuests] = useState(Math.min(2, table.seats));
  return (
    <Modal title={`Seat ${table.name} (offline)`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" onClick={() => onSeat(guests)}>Open check</button></>}>
      <div className="row">
        <span>Guests</span>
        <button className="qtybtn" type="button" onClick={() => setGuests(Math.max(1, guests - 1))} aria-label="Fewer guests">−</button>
        <b className="big-timer">{guests}</b>
        <button className="qtybtn" type="button" onClick={() => setGuests(guests + 1)} aria-label="More guests">+</button>
      </div>
    </Modal>
  );
}

function OfflineOrder({ order, kit, onBack }) {
  const menu = useMenuIndex(kit.menu);
  const [avoid, setAvoid] = useState(() => new Set());
  const [picking, setPicking] = useState(null);
  const [info, setInfo] = useState(null);
  const [paying, setPaying] = useState(false);
  const toast = useToast();
  const t = off.totals(order, kit);
  const closed = Boolean(order.closed_at);
  const unsent = order.lines.filter((l) => !l.sent_at);

  const save = (patch) => {
    try {
      off.updateOrder({ ...order, ...patch });
      return true;
    } catch (e) {
      toast(e.message, "error");
      return false;
    }
  };
  function add(dish, mods = [], qty = 1, note = "") {
    const options = mods.map((id) => dish.groups.flatMap((g) => menu.groups[g]?.options || []).find((o) => o.id === id)).filter(Boolean);
    const unit = dish.price + options.reduce((s, o) => s + o.price, 0);
    const line = { key: `${Date.now()}-${Math.random()}`, menu_item: dish.id, name: dish.name, qty, price: dish.price, unit, modifiers: mods,
      mod_names: options.map((o) => o.name), note, sent_at: null };
    if (save({ lines: [...order.lines, line] })) toast(`${dish.name} added.`);
  }
  const tap = (dish) => {
    const needsChoice = dish.groups.some((g) => menu.groups[g]?.min > 0);
    if (needsChoice || conflictsFor(dish.allergens, avoid).length) setPicking(dish);
    else add(dish);
  };
  const qty = (l, q) => save({ lines: q <= 0 ? order.lines.filter((x) => x.key !== l.key) : order.lines.map((x) => (x.key === l.key ? { ...x, qty: Math.min(99, q) } : x)) });
  function send() {
    const now = new Date().toISOString();
    const lines = order.lines.map((l) => (l.sent_at ? l : { ...l, sent_at: now }));
    if (save({ lines })) printKitchen(order, unsent, kit);
  }

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <button className="btn" type="button" onClick={onBack}>← Floor</button>
        <div className="row">
          <Pill kind="warn">Offline</Pill>
          <b>{order.table_name ? `Table ${order.table_name}` : order.customer_name || "Takeout"} · {order.local_no}</b>
        </div>
      </div>
      <div className="pos">
        <Card title="Menu">
          <MenuBrowser menu={menu} avoid={avoid} setAvoid={setAvoid} onTap={tap} onInfo={setInfo} onCustomise={setPicking} disabled={closed} />
        </Card>
        <Card title="Check">
          {order.type === "dine_in" ? (
            <div className="row">
              <span className="small muted">Guests</span>
              <button className="qtybtn" type="button" disabled={closed} onClick={() => save({ guests: Math.max(1, order.guests - 1) })} aria-label="Fewer guests">−</button>
              <b>{order.guests}</b>
              <button className="qtybtn" type="button" disabled={closed} onClick={() => save({ guests: order.guests + 1 })} aria-label="More guests">+</button>
            </div>
          ) : (
            <label className="f">Name for the bag<input value={order.customer_name} disabled={closed} onChange={(e) => save({ customer_name: e.target.value.slice(0, 100) })} /></label>
          )}
          {!order.lines.length ? <Empty>Tap dishes to add them.</Empty> : order.lines.map((l) => (
            <div key={l.key} className="check-line">
              {!l.sent_at && !closed ? (
                <span className="row" style={{ flexWrap: "nowrap", gap: 4 }}>
                  <button className="qtybtn" type="button" onClick={() => qty(l, l.qty - 1)} aria-label="One fewer">−</button>
                  <b>{l.qty}</b>
                  <button className="qtybtn" type="button" onClick={() => qty(l, l.qty + 1)} aria-label="One more">+</button>
                </span>
              ) : <b>{l.qty}×</b>}
              <span>
                {l.name}
                {l.mod_names.length > 0 && <span className="small mods">{l.mod_names.join(", ")}</span>}
                {l.note && <span className="small muted"> · {l.note}</span>}
                {l.sent_at && <span className="small muted"> · sent {time(l.sent_at)}</span>}
              </span>
              <span>{money(l.qty * l.unit)}</span>
            </div>
          ))}
          <table className="totals">
            <tbody>
              <tr><td>Subtotal</td><td className="r">{money(t.subtotal)}</td></tr>
              {t.rate > 0 && <tr><td>Service charge {(t.rate * 100).toFixed(0)}%</td><td className="r">{money(t.sc)}</td></tr>}
              <tr><td>HST {(kit.location.tax_rate * 100).toFixed(0)}%</td><td className="r">{money(t.tax)}</td></tr>
              <tr><td><b>Total</b></td><td className="r"><b>{money(t.total)}</b></td></tr>
              {t.paid > 0 && <tr><td>Paid</td><td className="r">{money(t.paid)}</td></tr>}
              {t.tips > 0 && <tr><td>Tips</td><td className="r">{money(t.tips)}</td></tr>}
              {!closed && t.paid > 0 && <tr><td><b>Left to pay</b></td><td className="r"><b>{money(t.balance)}</b></td></tr>}
            </tbody>
          </table>
          {!closed ? (
            <>
              <div className="row">
                <button className="btn primary" type="button" disabled={!unsent.length} onClick={send}>Send &amp; print kitchen ticket{unsent.length ? ` (${unsent.reduce((s, l) => s + l.qty, 0)})` : ""}</button>
                <button className="btn primary" type="button" disabled={!order.lines.length} onClick={() => setPaying(true)}>Pay</button>
              </div>
              {!order.lines.length && (
                <div><button className="btn sm danger" type="button" onClick={() => { off.discardOrder(order.client_id); onBack(); }}>Cancel this empty order</button></div>
              )}
              <span className="small muted">Discounts, voids of sent items, loyalty and removing the service charge need the server: do them once it’s back.</span>
            </>
          ) : (
            <div className="row"><Pill kind="good">Paid</Pill><SyncPill o={order} /><button className="btn" type="button" onClick={() => printReceipt(order, kit)}>Print receipt</button></div>
          )}
          {unsent.length > 0 && order.lines.some((l) => l.sent_at) && <span className="small muted">Earlier items were already printed for the kitchen.</span>}
        </Card>
      </div>
      {picking && <OptionPicker dish={picking} menu={menu} avoid={avoid} onClose={() => setPicking(null)}
        onAdd={(dish, mods, n, note) => { add(dish, mods, n, note); setPicking(null); }} />}
      {info && <DishInfo dish={info} menu={menu} avoid={avoid} onClose={() => setInfo(null)}
        onAdd={closed ? null : (dish) => { setInfo(null); dish.groups.length ? setPicking(dish) : tap(dish); }} />}
      {paying && <OfflinePay order={order} t={t} onClose={() => setPaying(false)}
        onPaid={(payment) => {
          const payments = [...order.payments, payment];
          const left = t.balance - payment.amount;
          const now = new Date().toISOString();
          const patch = { payments };
          if (left <= 0.004) {
            patch.closed_at = now;
            patch.lines = order.lines.map((l) => (l.sent_at ? l : { ...l, sent_at: now }));
          }
          if (save(patch)) {
            setPaying(false);
            toast(left <= 0.004 ? "Paid in full. It uploads when the connection is back." : `Payment saved. ${money(left)} left.`);
            if (left <= 0.004 && unsent.length) printKitchen(order, unsent, kit);
          }
        }} />}
    </>
  );
}

function OfflinePay({ order, t, onClose, onPaid }) {
  const [method, setMethod] = useState("card");
  const [amount, setAmount] = useState(t.balance.toFixed(2));
  const [tip, setTip] = useState("");
  const [tendered, setTendered] = useState("");
  const [reference, setReference] = useState("");
  const amt = Number(amount || 0);
  const change = method === "cash" && tendered ? Number(tendered) - amt - Number(tip || 0) : null;
  const tipAllowed = !t.rate;
  const ok = amt > 0 && amt <= t.balance + 0.004 && (change == null || change >= 0);
  return (
    <Modal title={`Pay ${order.local_no} · ${money(t.balance)} left`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button>
        <button className="btn primary" type="button" disabled={!ok} onClick={() => onPaid({ method, amount: Math.round(amt * 100) / 100, tip: tipAllowed ? Math.round(Number(tip || 0) * 100) / 100 : 0,
          cash_tendered: method === "cash" && tendered ? Number(tendered) : null, reference, at: new Date().toISOString() })}>Record {money(amt + (tipAllowed ? Number(tip || 0) : 0))}</button></>}>
      <Chips options={[["card", "Card (terminal)"], ["cash", "Cash"], ["gift", "Gift card"], ["other", "Other"]]} value={method} onChange={setMethod} />
      <div className="row">
        <label className="f">Amount<input type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        {[2, 3, 4].map((n) => <button key={n} className="btn sm" type="button" onClick={() => setAmount((Math.ceil((t.balance / n) * 100) / 100).toFixed(2))}>Split ÷{n}</button>)}
      </div>
      {tipAllowed ? (
        <div className="row">
          <label className="f">Tip<input type="number" step="0.01" min="0" value={tip} onChange={(e) => setTip(e.target.value)} /></label>
          {[0.15, 0.18, 0.2].map((p) => <button key={p} className="btn sm" type="button" onClick={() => setTip((amt * p).toFixed(2))}>{p * 100}%</button>)}
        </div>
      ) : <span className="small muted">Service charge already added; no tip prompt.</span>}
      {method === "cash" && (
        <div className="row">
          <label className="f">Cash given<input type="number" step="0.05" min="0" value={tendered} onChange={(e) => setTendered(e.target.value)} /></label>
          {change != null && <b className={change < 0 ? "worse" : ""}>Change {money(Math.max(0, change))}{change < 0 ? " (not enough)" : ""}</b>}
        </div>
      )}
      {method === "card" && <label className="f">Approval code from the terminal slip (optional)<input value={reference} onChange={(e) => setReference(e.target.value)} /></label>}
      <span className="small muted">Run the card on the terminal first; it works without Larder. This just records it.</span>
    </Modal>
  );
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function printWindow(title, body) {
  const w = window.open("", "_blank", "width=380,height=640");
  if (!w) return false;
  w.document.write(`<html><head><title>${esc(title)}</title><style>body{font-family:monospace;padding:10px}table{width:100%}td{padding:2px 0;vertical-align:top}</style></head><body>${body}<script>window.print()</script></body></html>`);
  w.document.close();
  return true;
}

/** Big-print chit for the kitchen, since the kitchen screen can't see offline orders. */
function printKitchen(order, lines, kit) {
  const rows = lines.map((l) => `<div style="font-size:20px;margin:6px 0"><b>${l.qty}× ${esc(l.name)}</b>${l.mod_names.length ? `<div style="font-size:16px">&nbsp;&nbsp;${esc(l.mod_names.join(", "))}</div>` : ""}${l.note ? `<div style="font-size:16px">&nbsp;&nbsp;** ${esc(l.note)}</div>` : ""}</div>`).join("");
  printWindow(`Kitchen ${order.local_no}`, `<div style="font-size:22px"><b>${esc(order.table_name ? `TABLE ${order.table_name}` : `TAKEOUT ${order.customer_name || ""}`)}</b></div>
    <div>${esc(order.local_no)} · ${order.guests} guest(s) · ${new Date().toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</div>
    <div>${esc(kit.location.name)} · OFFLINE</div><hr>${rows}<hr>`);
}

function printReceipt(order, kit) {
  const t = off.totals(order, kit);
  const rows = order.lines.map((l) => `<tr><td>${l.qty}× ${esc(l.name)}${l.mod_names.length ? `<br><small>&nbsp;&nbsp;${esc(l.mod_names.join(", "))}</small>` : ""}</td><td style="text-align:right">${money(l.qty * l.unit)}</td></tr>`).join("");
  printWindow(`Receipt ${order.local_no}`, `<h3 style="text-align:center;margin:0">${esc(kit.location.name)}</h3><p style="text-align:center">Order ${esc(order.local_no)} · ${new Date(order.closed_at || Date.now()).toLocaleString("en-CA")}</p>
    <table>${rows}<tr><td colspan=2><hr></td></tr>
    <tr><td>Subtotal</td><td style="text-align:right">${money(t.subtotal)}</td></tr>
    ${t.sc > 0 ? `<tr><td>Service charge</td><td style="text-align:right">${money(t.sc)}</td></tr>` : ""}
    <tr><td>HST</td><td style="text-align:right">${money(t.tax)}</td></tr>
    <tr><td><b>Total</b></td><td style="text-align:right"><b>${money(t.total)}</b></td></tr>
    ${t.tips > 0 ? `<tr><td>Tip</td><td style="text-align:right">${money(t.tips)}</td></tr>` : ""}</table><p style="text-align:center">Thank you!</p>`);
}
