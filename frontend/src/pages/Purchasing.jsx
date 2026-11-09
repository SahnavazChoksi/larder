import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Modal, NumberInput, Pill, Tile, fmtDate, money, money0, qty, useAction, useApi } from "../ui";

const STATUS = { draft: "neutral", sent: "info", received: "good", cancelled: "neutral" };

export default function Purchasing() {
  const { location, can } = useAuth();
  const [tab, setTab] = useState("orders");
  const tabs = [["orders", "Orders"], ...(can("manager") ? [["reorder", "Reorder suggestions"], ["new", "New order"]] : [])];
  return (
    <>
      <Chips options={tabs} value={tab} onChange={setTab} />
      {tab === "orders" && <Orders location={location} manager={can("manager")} />}
      {tab === "reorder" && <Reorder location={location} onDone={() => setTab("orders")} />}
      {tab === "new" && <NewOrder location={location} onDone={() => setTab("orders")} />}
    </>
  );
}

function Orders({ location, manager }) {
  const list = useApi(`/purchasing/orders/?location=${location.id}`);
  const [receiving, setReceiving] = useState(null);
  const [run] = useAction();
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const rows = list.data;
  const open = rows.filter((o) => o.status === "sent");

  async function act(o, verb, msg) {
    if (await run(() => api.post(`/purchasing/orders/${o.id}/${verb}/`), msg)) list.reload();
  }

  return (
    <>
      <div className="tiles">
        <Tile label="Drafts" value={rows.filter((o) => o.status === "draft").length} />
        <Tile label="Waiting for delivery" value={open.length} note={money0(open.reduce((s, o) => s + o.total, 0))} />
        <Tile label="Late" value={open.filter((o) => o.expected_on && new Date(o.expected_on) < new Date(new Date().toDateString())).length}
          stripe={open.some((o) => o.expected_on && new Date(o.expected_on) < new Date(new Date().toDateString())) ? "warn" : ""} />
      </div>
      <Card title={`Purchase orders · ${location.name}`}>
        {!rows.length ? <Empty>No orders yet.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>PO</th><th>Vendor</th><th>Items</th><th className="r">Total</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id}>
                    <td><b>{o.number}</b><div className="small muted">{fmtDate(o.created_on)} · {o.source_label}</div></td>
                    <td>{o.vendor_name}<div className="small muted">{o.status === "received" ? `Received ${fmtDate(o.received_on)}` : `Expected ${fmtDate(o.expected_on)}`}</div></td>
                    <td className="small">{o.lines.map((l) => <div key={l.id}>{l.name} {qty(l.qty_received ?? l.qty, l.unit)}</div>)}</td>
                    <td className="r">{money(o.total)}</td>
                    <td><Pill kind={STATUS[o.status]}>{o.status_label}</Pill></td>
                    <td className="r">
                      <div className="row end">
                        {manager && o.status === "draft" && <button className="btn sm primary" type="button" onClick={() => act(o, "send", `${o.number} marked as sent.`)}>Mark sent</button>}
                        {(o.status === "sent" || o.status === "draft") && <button className="btn sm" type="button" onClick={() => setReceiving(o)}>Receive</button>}
                        {manager && (o.status === "sent" || o.status === "draft") && <button className="btn sm" type="button" onClick={() => act(o, "cancel", `${o.number} cancelled.`)}>Cancel</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="small muted" style={{ margin: 0 }}>"Mark sent" records that you placed the order with the vendor (by email, phone or their portal).</p>
      </Card>
      {receiving && <Receive order={receiving} manager={manager} onClose={() => setReceiving(null)} onDone={() => { setReceiving(null); list.reload(); }} />}
    </>
  );
}

function Receive({ order, manager, onClose, onDone }) {
  const [vals, setVals] = useState(() => Object.fromEntries(order.lines.map((l) => [l.id, { qty: l.qty, price: l.unit_price }])));
  const [invoice, setInvoice] = useState("");
  const [run, busy] = useAction();
  const total = order.lines.reduce((s, l) => s + Number(vals[l.id].qty || 0) * Number(vals[l.id].price || 0), 0);

  async function submit() {
    const lines = order.lines.map((l) => ({ id: l.id, qty: vals[l.id].qty || 0, unit_price: manager ? vals[l.id].price : null }));
    const ok = await run(() => api.post(`/purchasing/orders/${order.id}/receive/`, { invoice_number: invoice, lines }),
      `${order.number} received. Stock and prices updated.`);
    if (ok) onDone();
  }

  return (
    <Modal title={`Receive ${order.number} from ${order.vendor_name}`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={submit}>Confirm delivery</button></>}>
      <p className="small muted" style={{ margin: 0 }}>Check the delivery against the invoice. Change quantities that came short.{manager ? " Change prices that differ from the order." : ""}</p>
      <label className="f">Invoice number<input value={invoice} onChange={(e) => setInvoice(e.target.value)} placeholder="Optional" /></label>
      <table>
        <thead><tr><th>Item</th><th className="r">Ordered</th><th className="r">Received</th><th className="r">Unit price</th></tr></thead>
        <tbody>
          {order.lines.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td className="r">{qty(l.qty, l.unit)}</td>
              <td className="r"><NumberInput value={vals[l.id].qty} label={`Received ${l.name}`} onChange={(v) => setVals({ ...vals, [l.id]: { ...vals[l.id], qty: v } })} /> {l.unit}</td>
              <td className="r">
                {manager ? <NumberInput value={vals[l.id].price} step="0.01" label={`Price ${l.name}`} onChange={(v) => setVals({ ...vals, [l.id]: { ...vals[l.id], price: v } })} />
                  : money(l.unit_price)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <b className="num">Total {money(total)}</b>
    </Modal>
  );
}

function Reorder({ location, onDone }) {
  const list = useApi(`/purchasing/suggestions/?location=${location.id}`);
  const [picks, setPicks] = useState(null);
  const [run, busy] = useAction();
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const rows = list.data;
  const sel = picks || Object.fromEntries(rows.map((r) => [r.item, r.suggested]));
  const chosen = rows.filter((r) => Number(sel[r.item]) > 0);

  async function create() {
    const ok = await run(() => api.post("/purchasing/suggestions/", { location: location.id, lines: chosen.map((r) => ({ item: r.item, qty: sel[r.item] })) }),
      (d) => `${d.length} draft order${d.length > 1 ? "s" : ""} created: ${d.map((o) => o.number).join(", ")}.`);
    if (ok) onDone();
  }

  return (
    <Card title={`Below par at ${location.name}`} actions={<button className="btn primary" type="button" disabled={busy || !chosen.length} onClick={create}>Create draft orders</button>}>
      <p className="small muted" style={{ margin: 0 }}>Items under par, after counting what's already on order. Suggested amounts bring you to 1.5× par. Set a quantity to 0 to leave it out.</p>
      {!rows.length ? <Empty>Everything is at or above par.</Empty> : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Item</th><th>Vendor</th><th className="r">On hand</th><th className="r">On order</th><th className="r">Par</th><th className="r">Order</th><th className="r">Cost</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.item}>
                  <td><b>{r.name}</b></td>
                  <td className="small">{r.vendor_name}<div className="muted">{r.lead_days}-day lead time</div></td>
                  <td className="r">{qty(r.on_hand, r.unit)}</td><td className="r muted">{qty(r.on_order, r.unit)}</td><td className="r muted">{qty(r.par, r.unit)}</td>
                  <td className="r"><NumberInput value={sel[r.item]} step="0.5" label={`Order ${r.name}`} onChange={(v) => setPicks({ ...sel, [r.item]: v })} /> {r.unit}</td>
                  <td className="r">{money(Number(sel[r.item] || 0) * r.unit_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {chosen.length > 0 && <b className="num">Total {money(chosen.reduce((s, r) => s + Number(sel[r.item]) * r.unit_price, 0))} across {new Set(chosen.map((r) => r.vendor)).size} vendors</b>}
    </Card>
  );
}

function NewOrder({ location, onDone }) {
  const vendors = useApi("/vendors/");
  const items = useApi("/items/?kind=raw");
  const [vendor, setVendor] = useState("");
  const [lines, setLines] = useState({});
  const [note, setNote] = useState("");
  const [run, busy] = useAction();
  const vendorItems = (items.data || []).filter((i) => String(i.vendor) === String(vendor));
  const chosen = vendorItems.filter((i) => Number(lines[i.id]) > 0);

  async function submit() {
    const ok = await run(() => api.post("/purchasing/orders/", { vendor: Number(vendor), location: location.id, note, lines: chosen.map((i) => ({ item: i.id, qty: lines[i.id] })) }),
      (d) => `${d.number} created as a draft.`);
    if (ok) onDone();
  }

  return (
    <Card title={`New order for ${location.name}`}>
      {vendors.error && <ErrorBox>{vendors.error}</ErrorBox>}
      <div className="row">
        <label className="f">Vendor
          <select value={vendor} onChange={(e) => { setVendor(e.target.value); setLines({}); }}>
            <option value="">Choose…</option>
            {(vendors.data || []).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </label>
        <label className="f" style={{ flex: 1, minWidth: 200 }}>Note<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional" /></label>
      </div>
      {vendor && (
        <table>
          <thead><tr><th>Item</th><th className="r">Last price</th><th className="r">Quantity</th><th className="r">Line total</th></tr></thead>
          <tbody>
            {vendorItems.map((i) => (
              <tr key={i.id}>
                <td>{i.name}</td><td className="r">{money(i.last_price)}/{i.unit}</td>
                <td className="r"><NumberInput value={lines[i.id]} step="0.5" label={`Quantity ${i.name}`} onChange={(v) => setLines({ ...lines, [i.id]: v })} /> {i.unit}</td>
                <td className="r">{money(Number(lines[i.id] || 0) * i.last_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b className="num">Total {money(chosen.reduce((s, i) => s + Number(lines[i.id]) * i.last_price, 0))}</b>
        <button className="btn primary" type="button" disabled={busy || !chosen.length} onClick={submit}>Create draft</button>
      </div>
    </Card>
  );
}
