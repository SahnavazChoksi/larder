import { useState } from "react";
import api from "../api";
import { Card, ErrorBox, Loading, Pill, useAction, useApi } from "../ui";

const BLANK_TASK = { text: "", sop: null, requires_photo: false, value_label: "", value_unit: "", value_min: null, value_max: null, is_critical: false };
const BLANK = { name: "", kind: "opening", applies_to: "outlet", due_by: "", is_active: true, tasks: [{ ...BLANK_TASK }] };

export default function ChecklistSetup() {
  const list = useApi("/checklists/templates/?all=1");
  const sops = useApi("/checklists/sops/");
  const [editing, setEditing] = useState(null);

  if (list.error) return <ErrorBox>{list.error}</ErrorBox>;
  if (!list.data) return <Loading />;
  if (editing) {
    return <Editor initial={editing} sops={sops.data || []} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload(); }} />;
  }
  return (
    <Card title="Checklists" actions={<button className="btn primary" type="button" onClick={() => setEditing(BLANK)}>New checklist</button>}>
      <p className="small muted" style={{ margin: 0 }}>Changes apply from the next checklist started. Past checklists keep the wording they were done with.</p>
      <table>
        <thead><tr><th>Checklist</th><th>Type</th><th>Used at</th><th>Due by</th><th className="r">Tasks</th><th /></tr></thead>
        <tbody>
          {list.data.map((t) => (
            <tr key={t.id} style={{ opacity: t.is_active ? 1 : 0.5 }}>
              <td><b>{t.name}</b>{!t.is_active && <> <Pill>Off</Pill></>}</td>
              <td>{t.kind_label}</td><td>{t.applies_label}</td><td>{t.due_by ? t.due_by.slice(0, 5) : "End of day"}</td>
              <td className="r">{t.tasks.length}</td>
              <td className="r"><button className="btn sm" type="button" onClick={() => setEditing(t)}>Edit</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Editor({ initial, sops, onClose, onSaved }) {
  const [t, setT] = useState(() => ({ ...initial, due_by: initial.due_by ? initial.due_by.slice(0, 5) : "", tasks: initial.tasks.map((x) => ({ ...x })) }));
  const [run, busy] = useAction();
  const set = (k, v) => setT({ ...t, [k]: v });
  const setTask = (i, k, v) => set("tasks", t.tasks.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const move = (i, d) => {
    const tasks = [...t.tasks];
    const [x] = tasks.splice(i, 1);
    tasks.splice(i + d, 0, x);
    set("tasks", tasks);
  };
  const num = (v) => (v === "" || v == null ? null : v);

  async function save() {
    const body = {
      name: t.name, kind: t.kind, applies_to: t.applies_to, due_by: t.due_by || null, is_active: t.is_active,
      tasks: t.tasks.filter((x) => x.text.trim()).map((x) => ({
        id: x.id, text: x.text.trim(), sop: x.sop || null, requires_photo: x.requires_photo, is_critical: x.is_critical,
        value_label: x.value_label || "", value_unit: x.value_unit || "", value_min: num(x.value_min), value_max: num(x.value_max),
      })),
    };
    const ok = await run(() => (t.id ? api.put(`/checklists/templates/${t.id}/`, body) : api.post("/checklists/templates/", body)), `${t.name} saved.`);
    if (ok) onSaved();
  }

  return (
    <Card title={t.id ? `Edit ${initial.name}` : "New checklist"}
      actions={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={save}>Save</button></>}>
      <div className="row">
        <label className="f">Name<input value={t.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Outlet closing" /></label>
        <label className="f">Type
          <select value={t.kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="opening">Opening</option><option value="closing">Closing</option><option value="shift">During shift</option>
          </select>
        </label>
        <label className="f">Used at
          <select value={t.applies_to} onChange={(e) => set("applies_to", e.target.value)}>
            <option value="outlet">Outlets</option><option value="kitchen">Central kitchen</option><option value="all">Every location</option>
          </select>
        </label>
        <label className="f">Due by<input type="time" value={t.due_by} onChange={(e) => set("due_by", e.target.value)} /></label>
        <label className="row small"><input type="checkbox" checked={t.is_active} onChange={(e) => set("is_active", e.target.checked)} /> In use</label>
      </div>
      <p className="small muted" style={{ margin: 0 }}>Leave "Due by" empty for closing checklists: they're due by the end of the business day.</p>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Task</th><th>How-to (SOP)</th><th>Photo</th><th>Reading</th><th>Unit</th><th>Min</th><th>Max</th><th>Critical</th><th /></tr></thead>
          <tbody>
            {t.tasks.map((x, i) => (
              <tr key={x.id || `new-${i}`}>
                <td><input value={x.text} style={{ minWidth: 220 }} aria-label={`Task ${i + 1}`} onChange={(e) => setTask(i, "text", e.target.value)} /></td>
                <td>
                  <select value={x.sop || ""} aria-label="SOP" onChange={(e) => setTask(i, "sop", e.target.value ? Number(e.target.value) : null)}>
                    <option value="">None</option>
                    {sops.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                  </select>
                </td>
                <td><input type="checkbox" checked={x.requires_photo} aria-label="Needs a photo" onChange={(e) => setTask(i, "requires_photo", e.target.checked)} /></td>
                <td><input value={x.value_label || ""} placeholder="e.g. Walk-in temperature" aria-label="Reading label" onChange={(e) => setTask(i, "value_label", e.target.value)} /></td>
                <td><input value={x.value_unit || ""} style={{ width: 50 }} aria-label="Unit" onChange={(e) => setTask(i, "value_unit", e.target.value)} /></td>
                <td><input type="number" step="0.1" value={x.value_min ?? ""} style={{ width: 70 }} aria-label="Minimum" onChange={(e) => setTask(i, "value_min", e.target.value)} /></td>
                <td><input type="number" step="0.1" value={x.value_max ?? ""} style={{ width: 70 }} aria-label="Maximum" onChange={(e) => setTask(i, "value_max", e.target.value)} /></td>
                <td><input type="checkbox" checked={x.is_critical} aria-label="Critical" onChange={(e) => setTask(i, "is_critical", e.target.checked)} /></td>
                <td>
                  <div className="row" style={{ flexWrap: "nowrap" }}>
                    <button className="btn sm" type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up">↑</button>
                    <button className="btn sm" type="button" disabled={i === t.tasks.length - 1} onClick={() => move(i, 1)} aria-label="Move down">↓</button>
                    <button className="btn sm" type="button" onClick={() => set("tasks", t.tasks.filter((_, j) => j !== i))}>Remove</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div><button className="btn" type="button" onClick={() => set("tasks", [...t.tasks, { ...BLANK_TASK }])}>Add task</button></div>
      <p className="small muted" style={{ margin: 0 }}>
        Add a reading to ask for a number (temperature, cash over/short). Readings outside min–max are flagged; on critical tasks they alert managers on the dashboard.
      </p>
    </Card>
  );
}
