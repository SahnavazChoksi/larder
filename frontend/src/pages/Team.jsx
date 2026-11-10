import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, Loading, NumberInput, Pill, Tile, fmtDate, useAction, useApi } from "../ui";

const DEPTS = [["service", "Service"], ["kitchen", "Kitchen"], ["delivery", "Delivery / packing"], ["management", "Management"]];

export default function Team() {
  const { location } = useAuth();
  const staffing = useApi(`/ops/staffing/?location=${location.id}`);
  const [showLeft, setShowLeft] = useState(false);
  const people = useApi(`/ops/employees/?location=${location.id}${showLeft ? "&all=1" : ""}`);
  const [plan, setPlan] = useState({});
  const blank = { name: "", department: "service", position: "", started_on: "" };
  const [f, setF] = useState(blank);
  const [run, busy] = useAction();

  if (staffing.error) return <ErrorBox>{staffing.error}</ErrorBox>;
  if (!staffing.data) return <Loading />;
  const cols = staffing.data.columns;
  const required = (dept) => plan[dept] ?? cols.find((c) => c.department === dept)?.required ?? "";

  async function savePlan(dept) {
    if (plan[dept] === undefined) return;
    const ok = await run(() => api.post("/ops/staffing/plan/", { location: location.id, department: dept, required: plan[dept] || 0 }), "Staffing plan updated.");
    if (ok) { setPlan({ ...plan, [dept]: undefined }); staffing.reload(); }
  }
  async function add(e) {
    e.preventDefault();
    const ok = await run(() => api.post("/ops/employees/", { ...f, location: location.id, started_on: f.started_on || null }), `${f.name} added.`);
    if (ok) { setF(blank); people.reload(); staffing.reload(); }
  }
  async function leave(p) {
    const ok = await run(() => api.patch(`/ops/employees/${p.id}/`, { is_active: false }), `${p.name} marked as left.`);
    if (ok) { people.reload(); staffing.reload(); }
  }

  const t = staffing.data.total;
  return (
    <>
      <div className="tiles">
        <Tile label="Required" value={t.required} note={location.name} />
        <Tile label="On the team" value={t.actual} />
        <Tile label="Short" value={t.gap} stripe={t.gap ? "bad" : "good"} />
      </div>
      <Card title="Staffing plan">
        <p className="small muted" style={{ margin: 0 }}>How many people this location needs in each department. "On the team" counts active employees below.</p>
        <table>
          <thead><tr><th>Department</th><th className="r">Required</th><th className="r">On the team</th><th className="r">Short</th></tr></thead>
          <tbody>
            {DEPTS.map(([k, label]) => {
              const c = cols.find((x) => x.department === k);
              return (
                <tr key={k}>
                  <td>{label}</td>
                  <td className="r"><NumberInput value={required(k)} step="1" label={`Required ${label}`} onChange={(v) => setPlan({ ...plan, [k]: v })} onBlur={() => savePlan(k)} /></td>
                  <td className="r">{c?.actual ?? 0}</td>
                  <td className="r">{c?.gap ? <Pill kind="bad">{c.gap}</Pill> : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      <Card title="Employees">
        <Chips options={[[false, "Current"], [true, "Include people who left"]]} value={showLeft} onChange={setShowLeft} />
        {!people.data ? <Loading /> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Name</th><th>Department</th><th>Position</th><th>Started</th><th /></tr></thead>
              <tbody>
                {people.data.map((p) => (
                  <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                    <td><b>{p.name}</b>{!p.is_active && <> <Pill>Left {fmtDate(p.left_on)}</Pill></>}</td>
                    <td>{p.department_label}</td><td className="muted">{p.position}</td><td>{fmtDate(p.started_on)}</td>
                    <td className="r">{p.is_active && <button className="btn sm" type="button" onClick={() => leave(p)}>Mark as left</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <form className="row" onSubmit={add}>
          <label className="f">Name<input value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label className="f">Department<select value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })}>{DEPTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="f">Position<input value={f.position} placeholder="e.g. Server" onChange={(e) => setF({ ...f, position: e.target.value })} /></label>
          <label className="f">Start date<input type="date" value={f.started_on} onChange={(e) => setF({ ...f, started_on: e.target.value })} /></label>
          <button className="btn" type="submit" disabled={busy}>Add employee</button>
        </form>
      </Card>
    </>
  );
}
