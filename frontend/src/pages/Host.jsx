import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, Modal, Pill, Tile, daysAgo, minutesSince, useAction, useApi, useNow } from "../ui";

const RES = { booked: "info", arrived: "warn", seated: "good", no_show: "bad", cancelled: "neutral" };

export default function Host() {
  const { location } = useAuth();
  const wait = useApi(location.kind === "outlet" ? `/guests/waitlist/?location=${location.id}` : null, 20000);
  const [day, setDay] = useState(daysAgo(0));
  const res = useApi(location.kind === "outlet" ? `/guests/reservations/?location=${location.id}&date=${day}` : null);
  const floor = useApi(location.kind === "outlet" ? `/pos/floor/?location=${location.id}` : null, 20000);
  const [seating, setSeating] = useState(null);
  const now = useNow();
  const [run, busy] = useAction();

  if (location.kind !== "outlet") return <Card title="Host stand"><p className="muted" style={{ margin: 0 }}>Pick an outlet at the top.</p></Card>;
  if (wait.error) return <ErrorBox>{wait.error}</ErrorBox>;
  const freeTables = (floor.data?.tables || []).filter((t) => !t.order);
  const reload = () => { wait.reload(); res.reload(); floor.reload(); };
  const act = async (url, msg) => { if (await run(() => api.post(url), msg)) reload(); };

  return (
    <>
      <div className="tiles">
        <Tile label="Waiting now" value={wait.data?.waiting.length ?? "—"} />
        <Tile label="Avg wait today" value={wait.data?.today.avg_wait != null ? `${Math.round(wait.data.today.avg_wait)} min` : "—"} note={`${wait.data?.today.seated ?? 0} parties seated`} />
        <Tile label="Free tables" value={freeTables.length} note={freeTables.map((t) => t.name).join(", ")} />
        <Tile label="Bookings" value={(res.data || []).filter((r) => r.status === "booked").length} note="Still to arrive" />
      </div>
      <div className="split">
        <Card title="Waitlist">
          <AddWaiting location={location} onDone={reload} />
          {!wait.data ? <Loading /> : !wait.data.waiting.length ? <Empty>Nobody waiting.</Empty> : (
            <table>
              <thead><tr><th>Party</th><th className="r">Size</th><th className="r">Waited</th><th /></tr></thead>
              <tbody>
                {wait.data.waiting.map((w) => {
                  const m = Math.round(minutesSince(w.added_at, now));
                  return (
                    <tr key={w.id}>
                      <td><b>{w.name}</b><div className="small muted">{w.phone} {w.notes}</div>{w.status === "notified" && <Pill kind="good">Told table's ready</Pill>}</td>
                      <td className="r">{w.party_size}</td>
                      <td className="r"><span className={m > w.quoted_minutes ? "worse" : ""}>{m} min</span><div className="small muted">quoted {w.quoted_minutes}</div></td>
                      <td className="r">
                        <div className="row end">
                          {w.status === "waiting" && <button className="btn sm" type="button" disabled={busy} onClick={() => act(`/guests/waitlist/${w.id}/notify/`, "Guest notified.")}>Table ready</button>}
                          <button className="btn sm primary" type="button" onClick={() => setSeating({ kind: "waitlist", entry: w })}>Seat</button>
                          <button className="btn sm" type="button" disabled={busy} onClick={() => act(`/guests/waitlist/${w.id}/left/`, "Marked as left.")}>Left</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <span className="small muted">"Table ready" logs a text to the guest; real SMS is switched on in settings.</span>
        </Card>
        <Card title="Reservations">
          <div className="row">
            <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Reservation date" />
            <Book location={location} day={day} tables={floor.data?.tables || []} onDone={reload} />
          </div>
          {!res.data ? <Loading /> : !res.data.length ? <Empty>No bookings.</Empty> : (
            <table>
              <thead><tr><th>Time</th><th>Name</th><th className="r">Size</th><th>Table</th><th>Status</th><th /></tr></thead>
              <tbody>
                {res.data.map((r) => (
                  <tr key={r.id}>
                    <td>{new Date(r.starts_at).toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" })}</td>
                    <td><b>{r.name}</b>{r.notes && <div className="small muted">{r.notes}</div>}</td>
                    <td className="r">{r.party_size}</td><td>{r.table_name || "—"}</td>
                    <td><Pill kind={RES[r.status]}>{r.status_label}</Pill></td>
                    <td className="r">
                      {(r.status === "booked" || r.status === "arrived") && (
                        <div className="row end">
                          {r.status === "booked" && <button className="btn sm" type="button" disabled={busy} onClick={() => act(`/guests/reservations/${r.id}/arrive/`, "Arrived.")}>Arrived</button>}
                          <button className="btn sm primary" type="button" onClick={() => setSeating({ kind: "reservation", entry: r })}>Seat</button>
                          <button className="btn sm" type="button" disabled={busy} onClick={() => act(`/guests/reservations/${r.id}/no_show/`, "Marked no-show.")}>No-show</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
      {seating && (
        <SeatModal seating={seating} tables={freeTables} onClose={() => setSeating(null)} onDone={() => { setSeating(null); reload(); }} />
      )}
    </>
  );
}

function AddWaiting({ location, onDone }) {
  const blank = { name: "", phone: "", party_size: 2, quoted_minutes: 15, notes: "" };
  const [f, setF] = useState(blank);
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    if (await run(() => api.post("/guests/waitlist/", { ...f, location: location.id }), `${f.name} added.`)) { setF(blank); onDone(); }
  }
  return (
    <form className="row" onSubmit={submit}>
      <label className="f">Name<input value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label className="f">Phone<input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
      <label className="f">Size<input type="number" min="1" value={f.party_size} onChange={(e) => setF({ ...f, party_size: e.target.value })} /></label>
      <label className="f">Quote (min)<input type="number" min="0" step="5" value={f.quoted_minutes} onChange={(e) => setF({ ...f, quoted_minutes: e.target.value })} /></label>
      <button className="btn" type="submit" disabled={busy}>Add</button>
    </form>
  );
}

function Book({ location, day, tables, onDone }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", phone: "", party_size: 2, time: "19:00", table: "", notes: "" });
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    const starts_at = new Date(`${day}T${f.time}:00`).toISOString();
    const ok = await run(() => api.post("/guests/reservations/", { location: location.id, name: f.name, phone: f.phone, party_size: f.party_size,
      starts_at, table: f.table || null, notes: f.notes }), "Booked.");
    if (ok) { setOpen(false); onDone(); }
  }
  return (
    <>
      <button className="btn primary" type="button" onClick={() => setOpen(true)}>New booking</button>
      {open && (
        <Modal title="New booking" onClose={() => setOpen(false)}>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="row">
              <label className="f">Name<input value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
              <label className="f">Phone<input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
            </div>
            <div className="row">
              <label className="f">Party<input type="number" min="1" value={f.party_size} onChange={(e) => setF({ ...f, party_size: e.target.value })} /></label>
              <label className="f">Time<input type="time" value={f.time} required onChange={(e) => setF({ ...f, time: e.target.value })} /></label>
              <label className="f">Table<select value={f.table} onChange={(e) => setF({ ...f, table: e.target.value })}><option value="">Decide later</option>{tables.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.seats})</option>)}</select></label>
            </div>
            <label className="f">Notes<input value={f.notes} placeholder="Birthday, high chair, allergy…" onChange={(e) => setF({ ...f, notes: e.target.value })} /></label>
            <div className="row end"><button className="btn" type="button" onClick={() => setOpen(false)}>Cancel</button><button className="btn primary" type="submit" disabled={busy}>Book</button></div>
          </form>
        </Modal>
      )}
    </>
  );
}

function SeatModal({ seating, tables, onClose, onDone }) {
  const e = seating.entry;
  const fits = tables.filter((t) => t.seats + 2 >= e.party_size).sort((a, b) => a.seats - b.seats);
  const [table, setTable] = useState(e.table || fits[0]?.id || "");
  const [run, busy] = useAction();
  const url = seating.kind === "waitlist" ? `/guests/waitlist/${e.id}/seat/` : `/guests/reservations/${e.id}/seat/`;
  async function seat() {
    if (await run(() => api.post(url, { table }), `${e.name} seated. Their check is open on the POS.`)) onDone();
  }
  return (
    <Modal title={`Seat ${e.name} (${e.party_size})`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy || !table} onClick={seat}>Seat</button></>}>
      {!fits.length ? <p className="muted">No free table fits {e.party_size}. Free one up on the POS first.</p> : (
        <div className="row">
          {fits.map((t) => <button key={t.id} type="button" className={`chip ${String(table) === String(t.id) ? "on" : ""}`} onClick={() => setTable(t.id)}>{t.name} · {t.seats}</button>)}
        </div>
      )}
    </Modal>
  );
}
