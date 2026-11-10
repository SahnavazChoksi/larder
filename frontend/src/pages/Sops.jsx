import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, Modal, Pill, fmtDate, useAction, useApi } from "../ui";

export default function Sops() {
  const { can } = useAuth();
  const list = useApi("/checklists/sops/");
  const [selId, setSelId] = useState(null);
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const shown = list.data.filter((s) => (s.title + " " + s.category + " " + s.body).toLowerCase().includes(search.toLowerCase()));
  const cats = [...new Set(shown.map((s) => s.category))];
  const sel = list.data.find((s) => s.id === selId) || shown[0];

  return (
    <div className="split">
      <Card title="Standard operating procedures"
        actions={can("manager") && <button className="btn primary" type="button" onClick={() => setEditing({ title: "", category: "", body: "" })}>New SOP</button>}>
        <input type="search" placeholder="Search, e.g. fryer" aria-label="Search SOPs" value={search} onChange={(e) => setSearch(e.target.value)} />
        {!shown.length && <Empty>No SOPs match.</Empty>}
        {cats.map((c) => (
          <div key={c}>
            <h3 style={{ margin: "6px 0" }}>{c}</h3>
            <table>
              <tbody>
                {shown.filter((s) => s.category === c).map((s) => (
                  <tr key={s.id} className={`click ${sel?.id === s.id ? "sel" : ""}`} onClick={() => setSelId(s.id)}>
                    <td><b>{s.title}</b></td><td className="r small muted">{s.steps.length} steps</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Card>
      {sel && (
        <Card title={sel.title} actions={can("manager") && <button className="btn" type="button" onClick={() => setEditing(sel)}>Edit</button>}>
          <div className="row"><Pill kind="accent">{sel.category}</Pill><span className="small muted">Updated {fmtDate(sel.updated_at)}{sel.updated_by_name && ` by ${sel.updated_by_name}`}</span></div>
          <ol className="steps">{sel.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </Card>
      )}
      {editing && <SopForm initial={editing} onClose={() => setEditing(null)} onSaved={(s) => { setEditing(null); setSelId(s.id); list.reload(); }} />}
    </div>
  );
}

function SopForm({ initial, onClose, onSaved }) {
  const [s, setS] = useState(initial);
  const [run, busy] = useAction();
  const isNew = !initial.id;

  async function save(e) {
    e.preventDefault();
    const body = { title: s.title, category: s.category, body: s.body };
    const res = await run(() => (isNew ? api.post("/checklists/sops/", body) : api.patch(`/checklists/sops/${s.id}/`, body)), "SOP saved.");
    if (res) onSaved(res);
  }

  async function archive() {
    const res = await run(() => api.patch(`/checklists/sops/${s.id}/`, { is_active: false }), "SOP archived.");
    if (res) onSaved(res);
  }

  return (
    <Modal title={isNew ? "New SOP" : `Edit ${initial.title}`} onClose={onClose}>
      <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label className="f">Title<input value={s.title} required onChange={(e) => setS({ ...s, title: e.target.value })} /></label>
        <label className="f">Category<input value={s.category} required placeholder="e.g. Food safety, Cleaning, Cash" onChange={(e) => setS({ ...s, category: e.target.value })} /></label>
        <label className="f">Steps (one per line)<textarea rows={9} value={s.body} required onChange={(e) => setS({ ...s, body: e.target.value })} /></label>
        <div className="row end">
          {!isNew && <button className="btn danger" type="button" disabled={busy} onClick={archive}>Archive</button>}
          <button className="btn" type="button" onClick={onClose}>Cancel</button>
          <button className="btn primary" type="submit" disabled={busy}>Save</button>
        </div>
      </form>
    </Modal>
  );
}
