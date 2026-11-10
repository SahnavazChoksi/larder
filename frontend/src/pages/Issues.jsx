import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Modal, Pill, Tile, fmtDateTime, money, useAction, useApi } from "../ui";

const SEV = { low: "neutral", high: "warn", critical: "bad" };
const STATUS = { open: "bad", in_progress: "warn", resolved: "good" };

export default function Issues() {
  const { location, can } = useAuth();
  const [filter, setFilter] = useState("open");
  const list = useApi(`/ops/issues/?location=${location.id}${filter === "open" ? "&status=open" : ""}`);
  const equipment = useApi(`/ops/equipment/?location=${location.id}`);
  const [reporting, setReporting] = useState(false);
  const [editing, setEditing] = useState(null);
  const navigate = useNavigate();

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  const rows = list.data || [];
  const reload = () => { list.reload(); equipment.reload(); };

  return (
    <>
      <div className="tiles">
        <Tile label="Open" value={rows.filter((i) => i.status !== "resolved").length} />
        <Tile label="Critical" value={rows.filter((i) => i.severity === "critical" && i.status !== "resolved").length}
          stripe={rows.some((i) => i.severity === "critical" && i.status !== "resolved") ? "bad" : "good"} />
        <Tile label="Equipment" value={equipment.data?.length ?? "—"} note={location.name} />
      </div>
      <Card title={`Issues · ${location.name}`} actions={<button className="btn primary" type="button" onClick={() => setReporting(true)}>Report a problem</button>}>
        <Chips options={[["open", "Open"], ["all", "All"]]} value={filter} onChange={setFilter} />
        {!list.data ? <Loading /> : !rows.length ? <Empty>No issues. Everything's working.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Issue</th><th>Equipment</th><th>Severity</th><th>Status</th><th>Assigned to</th><th>Reported</th><th /></tr></thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.id}>
                    <td><b>{i.title}</b><div className="small muted" style={{ whiteSpace: "pre-line" }}>{i.detail}</div>
                      {i.resolution && <div className="small">Fix: {i.resolution}{i.repair_cost != null && ` (${money(i.repair_cost)})`}</div>}</td>
                    <td>{i.equipment_name || "—"}</td>
                    <td><Pill kind={SEV[i.severity]}>{i.severity_label}</Pill></td>
                    <td><Pill kind={STATUS[i.status]}>{i.status_label}</Pill></td>
                    <td className="small">{i.assigned_to || "—"}</td>
                    <td className="small muted">{fmtDateTime(i.created_at)}<div>{i.raised_by_name}</div></td>
                    <td className="r">
                      <div className="row end">
                        {i.checklist_run && <button className="btn sm" type="button" onClick={() => navigate(`/checklists?run=${i.checklist_run}`)}>Checklist</button>}
                        {can("manager") && <button className="btn sm" type="button" onClick={() => setEditing(i)}>Update</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Equipment">
        {!equipment.data ? <Loading /> : (
          <table>
            <thead><tr><th>Name</th><th>Type</th><th>Service contact</th><th className="r">Open issues</th></tr></thead>
            <tbody>
              {equipment.data.map((e) => (
                <tr key={e.id}><td><b>{e.name}</b></td><td className="muted">{e.category}</td><td className="small">{e.service_contact || "—"}</td>
                  <td className="r">{e.open_issues ? <Pill kind="warn">{e.open_issues}</Pill> : "—"}</td></tr>
              ))}
            </tbody>
          </table>
        )}
        {can("manager") && <AddEquipment location={location} onDone={reload} />}
      </Card>
      {reporting && <Report location={location} equipment={equipment.data || []} onClose={() => setReporting(false)} onDone={() => { setReporting(false); reload(); }} />}
      {editing && <Update issue={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function Report({ location, equipment, onClose, onDone }) {
  const [f, setF] = useState({ title: "", detail: "", severity: "high", equipment: "" });
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/ops/issues/", { ...f, location: location.id, equipment: f.equipment || null }),
      "Reported. Managers have been notified.");
    if (ok) onDone();
  }
  return (
    <Modal title="Report a problem" onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label className="f">What's wrong?<input value={f.title} required maxLength={140} placeholder="e.g. Walk-in door won't seal" onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="f">Details<textarea rows={3} value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} /></label>
        <div className="row">
          <label className="f">Equipment
            <select value={f.equipment} onChange={(e) => setF({ ...f, equipment: e.target.value })}>
              <option value="">Not equipment</option>{equipment.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </label>
          <label className="f">How urgent?
            <select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>
              <option value="low">Low: can wait</option><option value="high">High: fix this week</option><option value="critical">Critical: food safety or can't trade</option>
            </select>
          </label>
        </div>
        <div className="row end"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="submit" disabled={busy}>Report</button></div>
      </form>
    </Modal>
  );
}

function Update({ issue, onClose, onDone }) {
  const [f, setF] = useState({ status: issue.status, assigned_to: issue.assigned_to, resolution: issue.resolution, repair_cost: issue.repair_cost ?? "", severity: issue.severity });
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.patch(`/ops/issues/${issue.id}/`, { ...f, repair_cost: f.repair_cost === "" ? null : f.repair_cost }), `${issue.number} updated.`);
    if (ok) onDone();
  }
  return (
    <Modal title={issue.title} onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="row">
          <label className="f">Status
            <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              <option value="open">Open</option><option value="in_progress">Being fixed</option><option value="resolved">Fixed</option>
            </select>
          </label>
          <label className="f">Severity
            <select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}>
              <option value="low">Low</option><option value="high">High</option><option value="critical">Critical</option>
            </select>
          </label>
        </div>
        <label className="f">Assigned to<input value={f.assigned_to} placeholder="Technician or staff member" onChange={(e) => setF({ ...f, assigned_to: e.target.value })} /></label>
        <label className="f">What was done<input value={f.resolution} onChange={(e) => setF({ ...f, resolution: e.target.value })} /></label>
        <label className="f">Repair cost ($)<input type="number" step="0.01" min="0" value={f.repair_cost} onChange={(e) => setF({ ...f, repair_cost: e.target.value })} /></label>
        <div className="row end"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="submit" disabled={busy}>Save</button></div>
      </form>
    </Modal>
  );
}

function AddEquipment({ location, onDone }) {
  const [f, setF] = useState({ name: "", category: "", service_contact: "" });
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/ops/equipment/", { ...f, location: location.id }), `${f.name} added.`);
    if (ok) { setF({ name: "", category: "", service_contact: "" }); onDone(); }
  }
  return (
    <form className="row" onSubmit={submit}>
      <label className="f">Name<input value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Fryer 2" /></label>
      <label className="f">Type<input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} placeholder="Refrigeration" /></label>
      <label className="f" style={{ flex: 1, minWidth: 180 }}>Service contact<input value={f.service_contact} onChange={(e) => setF({ ...f, service_contact: e.target.value })} /></label>
      <button className="btn" type="submit" disabled={busy}>Add equipment</button>
    </form>
  );
}
