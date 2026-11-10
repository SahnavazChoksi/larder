import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, Modal, Pill, fmtDate, fmtDateTime, money, useAction, useApi } from "../ui";

export default function Guests() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useApi(`/guests/?q=${encodeURIComponent(search)}`);
  const [selId, setSelId] = useState(null);
  const [adding, setAdding] = useState(false);

  return (
    <div className="split">
      <Card title="Guests" actions={<button className="btn primary" type="button" onClick={() => setAdding(true)}>Add guest</button>}>
        <form onSubmit={(e) => { e.preventDefault(); setSearch(q); }} className="row">
          <input type="search" placeholder="Name, phone or email" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search guests" style={{ flex: 1 }} />
          <button className="btn" type="submit">Search</button>
        </form>
        {list.error && <ErrorBox>{list.error}</ErrorBox>}
        {!list.data ? <Loading /> : !list.data.length ? <Empty>No guests found.</Empty> : (
          <table>
            <thead><tr><th>Guest</th><th className="r">Visits</th><th className="r">Spent</th><th className="r">Points</th><th>Last visit</th></tr></thead>
            <tbody>
              {list.data.map((g) => (
                <tr key={g.id} className={`click ${selId === g.id ? "sel" : ""}`} onClick={() => setSelId(g.id)}>
                  <td><b>{g.name}</b> {g.is_member && <Pill kind="accent">Member</Pill>}<div className="small muted">{g.phone}</div></td>
                  <td className="r">{g.visits}</td><td className="r">{money(g.total_spent, 0)}</td>
                  <td className="r">{g.is_member ? g.points : "—"}</td><td>{fmtDate(g.last_visit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {selId && <Profile key={selId} id={selId} onSaved={list.reload} />}
      {adding && <GuestForm onClose={() => setAdding(false)} onSaved={(g) => { setAdding(false); setSelId(g.id); list.reload(); }} />}
    </div>
  );
}

function Profile({ id, onSaved }) {
  const { can } = useAuth();
  const { data: g, error, reload } = useApi(`/guests/${id}/`);
  const [editing, setEditing] = useState(false);
  const [adj, setAdj] = useState({ points: "", reason: "" });
  const [run, busy] = useAction();
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!g) return <Loading />;
  async function adjust(e) {
    e.preventDefault();
    if (await run(() => api.post(`/guests/${id}/points/`, adj), "Points adjusted.")) { setAdj({ points: "", reason: "" }); reload(); }
  }
  return (
    <Card title={g.name} actions={<button className="btn" type="button" onClick={() => setEditing(true)}>Edit</button>}>
      <div className="row">
        {g.is_member ? <Pill kind="accent">Loyalty member since {fmtDate(g.joined_on)}</Pill> : <Pill>Not in loyalty</Pill>}
        {g.marketing_opt_in && <Pill kind="info">Agreed to offers</Pill>}
      </div>
      {g.allergies && <div className="note error">Allergy: {g.allergies}</div>}
      <div className="tiles">
        <div className="tile"><span className="l">Visits</span><span className="v">{g.visits}</span></div>
        <div className="tile"><span className="l">Spent</span><span className="v">{money(g.total_spent, 0)}</span></div>
        <div className="tile"><span className="l">Points</span><span className="v">{g.points}</span><span className="d">{g.reward_points} = {money(g.reward_value)} off</span></div>
      </div>
      <p className="small" style={{ margin: 0 }}>{g.phone} · {g.email || "no email"}{g.birthday && ` · birthday ${fmtDate(g.birthday)}`}</p>
      {g.notes && <p className="small muted" style={{ margin: 0 }}>{g.notes}</p>}
      <h3>Recent orders</h3>
      {!g.history.length ? <Empty>No orders yet.</Empty> : (
        <table><tbody>{g.history.map((o) => <tr key={o.id}><td>{fmtDate(o.date)}</td><td>{o.location}</td><td>{o.number}</td><td className="r">{money(o.total)}</td></tr>)}</tbody></table>
      )}
      <h3>Points</h3>
      {!g.points_history.length ? <Empty>No points activity.</Empty> : (
        <table><tbody>{g.points_history.map((p, i) => <tr key={i}><td className="small">{fmtDateTime(p.at)}</td><td>{p.reason}</td><td className="r">{p.points > 0 ? "+" : ""}{p.points}</td></tr>)}</tbody></table>
      )}
      {can("manager") && g.is_member && (
        <form className="row" onSubmit={adjust}>
          <label className="f">Adjust points<input type="number" step="1" value={adj.points} required onChange={(e) => setAdj({ ...adj, points: e.target.value })} /></label>
          <label className="f" style={{ flex: 1 }}>Reason<input value={adj.reason} required onChange={(e) => setAdj({ ...adj, reason: e.target.value })} placeholder="Goodwill, correction…" /></label>
          <button className="btn" type="submit" disabled={busy}>Apply</button>
        </form>
      )}
      {editing && <GuestForm initial={g} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload(); onSaved(); }} />}
    </Card>
  );
}

function GuestForm({ initial, onClose, onSaved }) {
  const [g, setG] = useState(initial || { name: "", phone: "", email: "", birthday: "", allergies: "", notes: "", is_member: true, marketing_opt_in: false });
  const [run, busy] = useAction();
  const set = (k, v) => setG({ ...g, [k]: v });
  async function save(e) {
    e.preventDefault();
    const body = { name: g.name, phone: g.phone, email: g.email, birthday: g.birthday || null, allergies: g.allergies, notes: g.notes,
      is_member: g.is_member, marketing_opt_in: g.marketing_opt_in };
    const res = await run(() => (initial ? api.patch(`/guests/${initial.id}/`, body) : api.post("/guests/", body)), "Guest saved.");
    if (res) onSaved(res);
  }
  return (
    <Modal title={initial ? `Edit ${initial.name}` : "Add guest"} onClose={onClose}>
      <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="row">
          <label className="f">Name<input value={g.name} required onChange={(e) => set("name", e.target.value)} /></label>
          <label className="f">Phone<input value={g.phone} onChange={(e) => set("phone", e.target.value)} /></label>
        </div>
        <div className="row">
          <label className="f">Email<input type="email" value={g.email} onChange={(e) => set("email", e.target.value)} /></label>
          <label className="f">Birthday<input type="date" value={g.birthday || ""} onChange={(e) => set("birthday", e.target.value)} /></label>
        </div>
        <label className="f">Allergies<input value={g.allergies} onChange={(e) => set("allergies", e.target.value)} /></label>
        <label className="f">Notes<input value={g.notes} placeholder="Favourite table, spice level…" onChange={(e) => set("notes", e.target.value)} /></label>
        <label className="row small"><input type="checkbox" checked={g.is_member} onChange={(e) => set("is_member", e.target.checked)} /> Join loyalty program</label>
        <label className="row small"><input type="checkbox" checked={g.marketing_opt_in} onChange={(e) => set("marketing_opt_in", e.target.checked)} /> Guest agreed to receive offers by email/text</label>
        <div className="row end"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="submit" disabled={busy}>Save</button></div>
      </form>
    </Modal>
  );
}
