import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, Modal, NumberInput, Pill, Tile, fmtDate, money, qty, useAction, useApi } from "../ui";

const STATUS = { requested: "warn", dispatched: "info", received: "good", cancelled: "neutral" };

export default function Transfers() {
  const { user, location, can } = useAuth();
  const list = useApi(`/stock/transfers/?location=${location.id}`);
  const [dialog, setDialog] = useState(null); // {mode: dispatch|receive|request, transfer?}
  const [run] = useAction();
  const kitchen = user.kitchens?.[0];

  async function cancel(t) {
    if (await run(() => api.post(`/stock/transfers/${t.id}/cancel/`), `${t.number} cancelled.`)) list.reload();
  }

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const rows = list.data;
  const shortValue = rows.filter((t) => t.has_shortage).length;

  return (
    <>
      <div className="tiles">
        <Tile label="Waiting to dispatch" value={rows.filter((t) => t.status === "requested").length} />
        <Tile label="On the way" value={rows.filter((t) => t.status === "dispatched").length} />
        <Tile label="Arrived short" value={shortValue} note="Recent transfers" stripe={shortValue ? "warn" : "good"} />
      </div>
      <Card
        title={`Transfers · ${location.name}`}
        actions={location.kind === "outlet" && kitchen && (
          <button className="btn primary" type="button" onClick={() => setDialog({ mode: "request" })}>Request prep from {kitchen.name}</button>
        )}
      >
        {!rows.length ? <Empty>No transfers yet.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Transfer</th><th>Route</th><th>Items</th><th className="r">Value</th><th>Status</th><th /></tr></thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id}>
                    <td><b>{t.number}</b><div className="small muted">{fmtDate(t.requested_on)} · {t.requested_by_name}</div></td>
                    <td>{t.from_name} → {t.to_name}</td>
                    <td className="small">
                      {t.lines.map((l) => (
                        <div key={l.id}>
                          {l.name}: {qty(l.qty_requested, l.unit)}
                          {l.qty_sent != null && l.qty_sent !== l.qty_requested && ` (sent ${qty(l.qty_sent, l.unit)})`}
                          {l.qty_received != null && l.qty_received < l.qty_sent && <span style={{ color: "var(--bad)" }}> · got {qty(l.qty_received, l.unit)}</span>}
                        </div>
                      ))}
                    </td>
                    <td className="r">{money(t.value)}</td>
                    <td><Pill kind={STATUS[t.status]}>{t.status_label}</Pill> {t.has_shortage && <Pill kind="bad">Short</Pill>}</td>
                    <td className="r">
                      <div className="row end">
                        {t.status === "requested" && t.from_location === location.id && (
                          <button className="btn sm primary" type="button" onClick={() => setDialog({ mode: "dispatch", transfer: t })}>Dispatch</button>
                        )}
                        {t.status === "dispatched" && t.to_location === location.id && (
                          <button className="btn sm primary" type="button" onClick={() => setDialog({ mode: "receive", transfer: t })}>Receive</button>
                        )}
                        {t.status === "requested" && can("manager") && (
                          <button className="btn sm" type="button" onClick={() => cancel(t)}>Cancel</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {dialog?.mode === "request" && (
        <RequestDialog from={kitchen} to={location} onClose={() => setDialog(null)} onDone={() => { setDialog(null); list.reload(); }} />
      )}
      {(dialog?.mode === "dispatch" || dialog?.mode === "receive") && (
        <QtyDialog {...dialog} onClose={() => setDialog(null)} onDone={() => { setDialog(null); list.reload(); }} />
      )}
    </>
  );
}

function RequestDialog({ from, to, onClose, onDone }) {
  const levels = useApi(`/stock/levels/?location=${to.id}`);
  const preps = useApi("/items/?kind=prep");
  const [lines, setLines] = useState({});
  const [run, busy] = useAction();

  function fillToPar() {
    const next = {};
    (levels.data || []).filter((r) => r.kind === "prep" && r.par != null && r.on_hand < r.par)
      .forEach((r) => { next[r.item] = Math.ceil((r.par - r.on_hand) * 2) / 2; });
    setLines(next);
  }

  async function submit() {
    const payload = Object.entries(lines).filter(([, v]) => Number(v) > 0).map(([item, v]) => ({ item: Number(item), qty: v }));
    const ok = await run(() => api.post("/stock/transfers/", { from_location: from.id, to_location: to.id, lines: payload }),
      (d) => `${d.number} requested from ${from.name}.`);
    if (ok) onDone();
  }

  const onHand = Object.fromEntries((levels.data || []).map((r) => [r.item, r]));
  return (
    <Modal title={`Request prep for ${to.name}`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={submit}>Send request</button></>}>
      <div className="row"><button className="btn sm" type="button" onClick={fillToPar}>Fill everything below par</button></div>
      {!preps.data ? <Loading /> : (
        <table>
          <thead><tr><th>Prep</th><th className="r">Have</th><th className="r">Par</th><th className="r">Request</th></tr></thead>
          <tbody>
            {preps.data.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="r">{qty(onHand[p.id]?.on_hand ?? 0, p.unit)}</td>
                <td className="r muted">{qty(onHand[p.id]?.par, p.unit)}</td>
                <td className="r"><NumberInput value={lines[p.id]} label={`Request ${p.name}`} step="0.5" onChange={(v) => setLines({ ...lines, [p.id]: v })} /> {p.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  );
}

function QtyDialog({ mode, transfer, onClose, onDone }) {
  const [vals, setVals] = useState(() =>
    Object.fromEntries(transfer.lines.map((l) => [l.id, mode === "dispatch" ? l.qty_requested : l.qty_sent])));
  const [run, busy] = useAction();
  const dispatching = mode === "dispatch";

  async function submit() {
    const lines = Object.entries(vals).map(([id, v]) => ({ id: Number(id), qty: v === "" ? 0 : v }));
    const ok = await run(() => api.post(`/stock/transfers/${transfer.id}/${mode}/`, { lines }),
      dispatching ? `${transfer.number} dispatched.` : `${transfer.number} received.`);
    if (ok) onDone();
  }

  return (
    <Modal title={`${dispatching ? "Dispatch" : "Receive"} ${transfer.number}`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={submit}>{dispatching ? "Dispatch" : "Confirm receipt"}</button></>}>
      <p className="small muted" style={{ margin: 0 }}>
        {dispatching ? "Enter what you are actually sending. Stock leaves this location now." : "Weigh or count what arrived. Anything less than what was sent is flagged."}
      </p>
      <table>
        <thead><tr><th>Item</th><th className="r">{dispatching ? "Requested" : "Sent"}</th><th className="r">{dispatching ? "Sending" : "Received"}</th></tr></thead>
        <tbody>
          {transfer.lines.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td className="r">{qty(dispatching ? l.qty_requested : l.qty_sent, l.unit)}</td>
              <td className="r"><NumberInput value={vals[l.id]} label={l.name} onChange={(v) => setVals({ ...vals, [l.id]: v })} /> {l.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}
