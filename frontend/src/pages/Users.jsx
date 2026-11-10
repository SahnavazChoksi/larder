import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, ErrorBox, Loading, Modal, Pill, fmtDateTime, useAction, useApi } from "../ui";

const ROLES = [["cook", "Cook"], ["server", "Server / host"], ["manager", "Manager"], ["owner", "Owner"]];
const BLANK = { username: "", first_name: "", last_name: "", email: "", role: "cook", locations: [], is_active: true, password: "" };

export default function Users() {
  const { locations } = useAuth();
  const list = useApi("/auth/users/");
  const [editing, setEditing] = useState(null);
  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  const rows = list.data.results || list.data;

  return (
    <Card title="Staff accounts" actions={<button className="btn primary" type="button" onClick={() => setEditing(BLANK)}>Add person</button>}>
      <p className="small muted" style={{ margin: 0 }}>Cooks count stock, log waste and receive deliveries. Managers also order, plan production and see costs. Owners can do everything, including recipes and prices.</p>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Locations</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.5 }}>
                <td><b>{`${u.first_name} ${u.last_name}`.trim() || u.username}</b>{!u.is_active && <> <Pill>Deactivated</Pill></>}</td>
                <td>{u.username}</td>
                <td><Pill kind={u.role === "owner" ? "accent" : u.role === "manager" ? "info" : "neutral"}>{ROLES.find((r) => r[0] === u.role)?.[1]}</Pill></td>
                <td className="small">{u.location_names.join(", ") || "None"}</td>
                <td className="small muted">{u.last_login ? fmtDateTime(u.last_login) : "Never"}</td>
                <td className="r"><button className="btn sm" type="button" onClick={() => setEditing({ ...u, password: "" })}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && <UserForm initial={editing} locations={locations} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />}
    </Card>
  );
}

function UserForm({ initial, locations, onClose, onSaved }) {
  const [u, setU] = useState(initial);
  const [run, busy] = useAction();
  const isNew = !initial.id;
  const set = (k, v) => setU({ ...u, [k]: v });

  async function save(e) {
    e.preventDefault();
    const body = { username: u.username, first_name: u.first_name, last_name: u.last_name, email: u.email, role: u.role, locations: u.locations, is_active: u.is_active };
    if (u.password) body.password = u.password;
    const ok = await run(() => (isNew ? api.post("/auth/users/", body) : api.patch(`/auth/users/${u.id}/`, body)), `${u.username} saved.`);
    if (ok) onSaved();
  }

  return (
    <Modal title={isNew ? "Add person" : `Edit ${initial.username}`} onClose={onClose}>
      <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="row">
          <label className="f">First name<input value={u.first_name} onChange={(e) => set("first_name", e.target.value)} /></label>
          <label className="f">Last name<input value={u.last_name} onChange={(e) => set("last_name", e.target.value)} /></label>
        </div>
        <div className="row">
          <label className="f">Username<input value={u.username} required onChange={(e) => set("username", e.target.value)} /></label>
          <label className="f">{isNew ? "Password" : "New password"}
            <input type="password" value={u.password} minLength={8} required={isNew} placeholder={isNew ? "" : "Leave blank to keep"} autoComplete="new-password" onChange={(e) => set("password", e.target.value)} />
          </label>
        </div>
        <label className="f">Role
          <select value={u.role} onChange={(e) => set("role", e.target.value)}>{ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </label>
        {u.role !== "owner" && (
          <fieldset style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
            <legend className="small muted">Works at</legend>
            {locations.map((l) => (
              <label key={l.id} className="row small">
                <input type="checkbox" checked={u.locations.includes(l.id)}
                  onChange={(e) => set("locations", e.target.checked ? [...u.locations, l.id] : u.locations.filter((x) => x !== l.id))} />
                {l.name}
              </label>
            ))}
          </fieldset>
        )}
        {!isNew && (
          <label className="row small"><input type="checkbox" checked={u.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Account active (untick to block sign-in; history is kept)</label>
        )}
        <div className="row end">
          <button className="btn" type="button" onClick={onClose}>Cancel</button>
          <button className="btn primary" type="submit" disabled={busy}>Save</button>
        </div>
      </form>
    </Modal>
  );
}
