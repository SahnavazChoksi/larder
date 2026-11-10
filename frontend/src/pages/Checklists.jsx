import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Modal, Pill, Tile, daysAgo, fmtDate, fmtDateTime, useAction, useApi } from "../ui";
import ChecklistSetup from "./ChecklistSetup";

const STATUS = { in_progress: "warn", submitted: "info", approved: "good", flagged: "bad" };

export default function Checklists() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "today";
  const runId = Number(params.get("run")) || null;
  const go = (next) => setParams(Object.fromEntries(Object.entries({ tab, ...next }).filter(([, v]) => v)));

  if (runId) return <RunView id={runId} onBack={() => go({ run: null })} />;
  const tabs = [["today", "Today"], ...(can("manager") ? [["review", "Review & history"], ["setup", "Set up checklists"]] : [])];
  return (
    <>
      <Chips options={tabs} value={tab} onChange={(t) => go({ tab: t, run: null })} />
      {tab === "today" && <Today onOpen={(id) => go({ run: id })} />}
      {tab === "review" && <Review onOpen={(id) => go({ run: id })} />}
      {tab === "setup" && <ChecklistSetup />}
    </>
  );
}

function Today({ onOpen }) {
  const { location } = useAuth();
  const [day, setDay] = useState(daysAgo(0));
  const { data, error, reload } = useApi(`/checklists/today/?location=${location.id}&date=${day}`);
  const [run, busy] = useAction();

  async function start(template) {
    const res = await run(() => api.post("/checklists/runs/", { template, location: location.id, date: day }));
    if (res) onOpen(res.id);
    else reload();
  }

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Chips options={[[daysAgo(0), "Today"], [daysAgo(1), "Yesterday"]]} value={day} onChange={setDay} />
        <span className="small muted">Closing after midnight? Pick Yesterday so it counts for the right business day.</span>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!data ? <Loading /> : !data.checklists.length ? <Empty>No checklists are set up for {location.name}.</Empty> : (
        <div className="grid3">
          {data.checklists.map((c) => {
            const r = c.run;
            return (
              <Card key={c.template} title={c.name}>
                <div className="row">
                  <Pill kind="accent">{c.kind_label}</Pill>
                  {r ? <Pill kind={STATUS[r.status]}>{r.status_label}</Pill> : <Pill kind={c.late ? "bad" : "neutral"}>{c.late ? "Overdue" : "Not started"}</Pill>}
                  {c.due_by && <span className="small muted">Due by {c.due_by.slice(0, 5)}</span>}
                </div>
                {r ? (
                  <>
                    <div className="small muted">{r.progress.done} of {r.progress.total} tasks · {r.photos} photo{r.photos === 1 ? "" : "s"}
                      {r.submitted_by_name && ` · submitted by ${r.submitted_by_name}`}</div>
                    <Progress done={r.progress.done} total={r.progress.total} />
                    <div><button className="btn primary" type="button" onClick={() => onOpen(r.id)}>{r.status === "in_progress" ? "Continue" : "View"}</button></div>
                  </>
                ) : (
                  <>
                    <div className="small muted">{c.task_count} tasks</div>
                    <div><button className="btn primary" type="button" disabled={busy} onClick={() => start(c.template)}>Start</button></div>
                  </>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}

function Progress({ done, total }) {
  const pct = total ? (done / total) * 100 : 0;
  return (
    <div className="progress" role="progressbar" aria-valuenow={done} aria-valuemax={total}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Shrink phone photos before upload: max 1600px, JPEG. Falls back to the original file. */
async function shrink(file, max = 1600) {
  if (!file.type.startsWith("image/")) return file;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, max / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.size < 1.5e6) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

function RunView({ id, onBack }) {
  const { can } = useAuth();
  const { data, error, reload } = useApi(`/checklists/runs/${id}/`);
  const [answers, setAnswers] = useState([]);
  const [saving, setSaving] = useState({});
  const [zoom, setZoom] = useState(null);
  const [note, setNote] = useState("");
  const [run, busy] = useAction();

  useEffect(() => {
    if (data) setAnswers(data.answers);
  }, [data]);

  if (error) return <><button className="btn" type="button" onClick={onBack}>← Back</button><ErrorBox>{error}</ErrorBox></>;
  if (!data) return <Loading />;
  const editable = data.status === "in_progress";

  async function patch(a, fields) {
    setSaving((s) => ({ ...s, [a.id]: true }));
    let body = fields;
    if (fields.photo) {
      body = new FormData();
      body.append("photo", await shrink(fields.photo));
      if (fields.done !== undefined) body.append("done", fields.done ? "true" : "false");
    }
    const updated = await run(() => api.patch(`/checklists/runs/${id}/answers/${a.id}/`, body));
    setSaving((s) => ({ ...s, [a.id]: false }));
    if (updated) setAnswers((list) => list.map((x) => (x.id === a.id ? updated : x)));
  }

  async function submit() {
    const res = await run(() => api.post(`/checklists/runs/${id}/submit/`), "Checklist submitted. A manager will review it.");
    if (res) reload();
  }

  async function decide(decision) {
    const res = await run(() => api.post(`/checklists/runs/${id}/review/`, { decision, note }),
      { approve: "Approved.", flag: "Flagged. The team will see your note.", reopen: "Reopened so the team can fix it." }[decision]);
    if (res) { setNote(""); reload(); }
  }

  const done = answers.filter((a) => a.done).length;
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <button className="btn" type="button" onClick={onBack}>← Back</button>
        <Pill kind={STATUS[data.status]}>{data.status_label}</Pill>
      </div>
      <div className="tiles">
        <Tile label={data.location_name} value={data.template_name} note={fmtDate(data.business_date)} />
        <Tile label="Progress" value={`${done}/${answers.length}`} note={data.started_by_name ? `Started by ${data.started_by_name}` : ""} />
        <Tile label="Photos" value={answers.filter((a) => a.photo_url).length} />
        <Tile label="Issues" value={data.issues.length} stripe={data.issues.length ? "warn" : "good"} />
      </div>
      {data.review_note && <div className={`note ${data.status === "flagged" ? "error" : ""}`}><b>{data.reviewed_by_name}:</b> {data.review_note}</div>}
      {!editable && data.issues.length > 0 && (
        <Card title="Look at these">
          <ul style={{ margin: 0, paddingLeft: 18 }}>{data.issues.map((i) => <li key={i}>{i}</li>)}</ul>
        </Card>
      )}
      <Card title="Tasks">
        <Progress done={done} total={answers.length} />
        <div className="tasks">
          {answers.map((a) => (
            <Task key={a.id} a={a} editable={editable} saving={saving[a.id]} onPatch={(f) => patch(a, f)} onZoom={setZoom} />
          ))}
        </div>
        {editable && (
          <div className="row end">
            <span className="small muted">You can come back and finish later. Everything saves as you go.</span>
            <button className="btn primary" type="button" disabled={busy} onClick={submit}>Submit checklist</button>
          </div>
        )}
        {!editable && <p className="small muted" style={{ margin: 0 }}>Submitted by {data.submitted_by_name || "—"} · {fmtDateTime(data.submitted_at)}</p>}
      </Card>
      {!editable && can("manager") && (
        <Card title="Review">
          <textarea rows={2} placeholder="Note for the team (needed to flag)" aria-label="Review note" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="row end">
            <button className="btn" type="button" disabled={busy} onClick={() => decide("reopen")}>Reopen for changes</button>
            <button className="btn danger" type="button" disabled={busy} onClick={() => decide("flag")}>Flag a problem</button>
            <button className="btn primary" type="button" disabled={busy || data.status === "approved"} onClick={() => decide("approve")}>Approve</button>
          </div>
        </Card>
      )}
      {zoom && (
        <Modal title={zoom.task_text} onClose={() => setZoom(null)} footer={<button className="btn" type="button" onClick={() => setZoom(null)}>Close</button>}>
          <img src={zoom.photo_url} alt={zoom.task_text} style={{ width: "100%", borderRadius: 8 }} />
          <span className="small muted">{zoom.done_by_name} · {fmtDateTime(zoom.done_at)}</span>
        </Modal>
      )}
    </>
  );
}

function Task({ a, editable, saving, onPatch, onZoom }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(a.value ?? "");
  const [note, setNote] = useState(a.note);
  const limits = [a.value_min, a.value_max].every((x) => x == null) ? "" :
    a.value_min != null && a.value_max != null ? `${a.value_min} to ${a.value_max}` : a.value_min != null ? `${a.value_min} or more` : `${a.value_max} or less`;

  return (
    <div className={`task ${a.done ? "done" : ""}`}>
      <label className="check">
        <input type="checkbox" checked={a.done} disabled={!editable || saving} onChange={(e) => onPatch({ done: e.target.checked })} />
        <span>
          <b>{a.task_text}</b>
          {a.is_critical && <> <Pill kind="bad">Critical</Pill></>}
          {a.requires_photo && <> <Pill kind="info">Photo</Pill></>}
          {a.done_by_name && <span className="small muted"> · {a.done_by_name}, {fmtDateTime(a.done_at)}</span>}
        </span>
      </label>
      <div className="row task-body">
        {a.value_label && (
          <label className="f">{a.value_label}{limits && ` (${limits} ${a.value_unit})`}
            <span className="row">
              <input type="number" step="0.1" value={value} disabled={!editable} aria-label={a.value_label}
                onChange={(e) => setValue(e.target.value)}
                onBlur={() => String(value) !== String(a.value ?? "") && onPatch({ value: value === "" ? null : value })} />
              {a.value_unit}
              {a.value != null && (a.out_of_range ? <Pill kind="bad">Out of range</Pill> : <Pill kind="good">OK</Pill>)}
            </span>
          </label>
        )}
        {a.photo_url && (
          <button type="button" className="thumb" onClick={() => onZoom(a)} aria-label={`Open photo for ${a.task_text}`}>
            <img src={a.photo_url} alt="" />
          </button>
        )}
        {editable && (
          <label className="btn sm">
            {saving ? "Uploading…" : a.photo_url ? "Retake photo" : "Add photo"}
            <input type="file" accept="image/*" capture="environment" hidden disabled={saving}
              onChange={(e) => e.target.files[0] && onPatch({ photo: e.target.files[0], done: a.done || a.requires_photo })} />
          </label>
        )}
        {a.sop && <button type="button" className="btn sm" onClick={() => setOpen(!open)}>{open ? "Hide how-to" : "How to"}</button>}
      </div>
      {open && a.sop && (
        <div className="note"><b>{a.sop.title}</b><ol style={{ margin: "6px 0 0", paddingLeft: 18 }}>{a.sop.steps.map((s) => <li key={s}>{s}</li>)}</ol></div>
      )}
      {(editable || a.note) && (
        <input type="text" placeholder="Note (optional): anything the manager should know" aria-label={`Note for ${a.task_text}`}
          value={note} disabled={!editable} onChange={(e) => setNote(e.target.value)}
          onBlur={() => note !== a.note && onPatch({ note })} />
      )}
    </div>
  );
}

function Review({ onOpen }) {
  const { location } = useAuth();
  const [status, setStatus] = useState("submitted");
  const [scope, setScope] = useState("all");
  const params = new URLSearchParams({ start: daysAgo(30) });
  if (status) params.set("status", status);
  if (scope === "one") params.set("location", location.id);
  const { data, error } = useApi(`/checklists/runs/?${params}`);
  const compliance = useApi(`/checklists/compliance/?start=${daysAgo(6)}&end=${daysAgo(0)}`);

  return (
    <>
      {compliance.data && (
        <div className="tiles">
          {compliance.data.locations.map((l) => (
            <Tile key={l.location} label={`${l.name} · 7 days`} value={l.rate == null ? "—" : `${Math.round(l.rate * 100)}%`}
              note={`${l.submitted} of ${l.expected} checklists done`} stripe={l.rate == null ? "" : l.rate < 0.9 ? "bad" : l.rate < 1 ? "warn" : "good"} />
          ))}
        </div>
      )}
      {compliance.data?.missing.length > 0 && (
        <div className="note error">
          Missed: {compliance.data.missing.map((m) => `${m.template} at ${m.location_name} (${fmtDate(m.date)})`).join("; ")}
        </div>
      )}
      <Card title="Checklists">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <Chips options={[["submitted", "Waiting for review"], ["flagged", "Flagged"], ["", "All"]]} value={status} onChange={setStatus} />
          <Chips options={[["all", "All locations"], ["one", location.name]]} value={scope} onChange={setScope} />
        </div>
        {error && <ErrorBox>{error}</ErrorBox>}
        {!data ? <Loading /> : !data.length ? <Empty>Nothing here.</Empty> : (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Day</th><th>Location</th><th>Checklist</th><th>Submitted by</th><th className="r">Photos</th><th className="r">Issues</th><th>Status</th></tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id} className="click" onClick={() => onOpen(r.id)}>
                    <td>{fmtDate(r.business_date)}</td><td>{r.location_name}</td><td><b>{r.template_name}</b></td>
                    <td className="small">{r.submitted_by_name || "—"}<div className="muted">{fmtDateTime(r.submitted_at)}</div></td>
                    <td className="r">{r.photos}</td>
                    <td className="r">{r.issue_count ? <Pill kind="warn">{r.issue_count}</Pill> : "—"}</td>
                    <td><Pill kind={STATUS[r.status]}>{r.status_label}</Pill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
