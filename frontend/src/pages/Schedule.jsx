import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Modal, Pill, Tile, daysAgo, fmtDate, fmtDateTime, isoDate, money, money0, pct, useAction, useApi } from "../ui";

const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
function monday(d = new Date()) {
  const x = new Date(d);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return isoDate(x);
}
function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

export default function Schedule() {
  const [tab, setTab] = useState("schedule");
  return (
    <>
      <Chips options={[["schedule", "Schedule"], ["timesheets", "Timesheets & labour"]]} value={tab} onChange={setTab} />
      {tab === "schedule" ? <Week /> : <Timesheets />}
    </>
  );
}

function Week() {
  const { location } = useAuth();
  const [week, setWeek] = useState(monday());
  const { data, error, reload } = useApi(`/ops/shifts/?location=${location.id}&week_start=${week}`);
  const [edit, setEdit] = useState(null);
  const [run, busy] = useAction();
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!data) return <Loading />;
  const days = WD.map((_, i) => addDays(week, i));
  const hours = data.shifts.reduce((s, x) => s + x.hours, 0);
  const rate = Object.fromEntries(data.employees.map((e) => [e.id, Number(e.hourly_rate || 0)]));
  const cost = data.shifts.reduce((s, x) => s + x.hours * (rate[x.employee] || 0), 0);
  const drafts = data.shifts.filter((s) => !s.published).length;

  async function publish() {
    if (await run(() => api.post("/ops/shifts/publish/", { location: location.id, week_start: week }), "Schedule published.")) reload();
  }
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <button className="btn sm" type="button" onClick={() => setWeek(addDays(week, -7))}>← Previous</button>
          <b>Week of {fmtDate(week)}</b>
          <button className="btn sm" type="button" onClick={() => setWeek(addDays(week, 7))}>Next →</button>
        </div>
        <button className="btn primary" type="button" disabled={busy || !drafts} onClick={publish}>{drafts ? `Publish ${drafts} draft shifts` : "All published"}</button>
      </div>
      <div className="tiles">
        <Tile label="Scheduled hours" value={hours.toFixed(1)} />
        <Tile label="Estimated wages" value={money0(cost)} note="Hours × hourly rate" />
        <Tile label="People scheduled" value={new Set(data.shifts.map((s) => s.employee)).size} note={`of ${data.employees.length}`} />
      </div>
      <Card title={`Schedule · ${location.name}`}>
        <div className="tablewrap">
          <div className="week">
            <div className="head">Employee</div>
            {days.map((d, i) => <div key={d} className="head">{WD[i]} {Number(d.slice(8))}</div>)}
            {data.employees.map((e) => (
              <Row key={e.id} e={e} days={days} shifts={data.shifts.filter((s) => s.employee === e.id)} onEdit={setEdit} />
            ))}
          </div>
        </div>
        <span className="small muted">Click a day to add a shift; click a shift to change it. Dashed shifts are drafts until you publish.</span>
      </Card>
      {edit && <ShiftDialog edit={edit} location={location} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />}
    </>
  );
}

function Row({ e, days, shifts, onEdit }) {
  const total = shifts.reduce((s, x) => s + x.hours, 0);
  return (
    <>
      <div><b>{e.name}</b><div className="muted">{e.position || e.department_label} · {total.toFixed(1)} h</div></div>
      {days.map((d) => (
        <div key={d} onClick={(ev) => ev.target === ev.currentTarget && onEdit({ employee: e, date: d })} style={{ cursor: "pointer" }}>
          {shifts.filter((s) => s.date === d).map((s) => (
            <button key={s.id} type="button" className={`shift ${s.published ? "" : "draft"}`} onClick={() => onEdit({ employee: e, date: d, shift: s })}>
              {s.start.slice(0, 5)}–{s.end.slice(0, 5)}
            </button>
          ))}
        </div>
      ))}
    </>
  );
}

function ShiftDialog({ edit, location, onClose, onDone }) {
  const s = edit.shift;
  const [f, setF] = useState({ start: s?.start.slice(0, 5) || "11:00", end: s?.end.slice(0, 5) || "17:00", role: s?.role || edit.employee.position || "" });
  const [run, busy] = useAction();
  async function save() {
    const body = { employee: edit.employee.id, location: location.id, date: edit.date, ...f };
    if (await run(() => (s ? api.patch(`/ops/shifts/${s.id}/`, body) : api.post("/ops/shifts/", body)), "Shift saved.")) onDone();
  }
  async function remove() {
    if (await run(() => api.delete(`/ops/shifts/${s.id}/`), "Shift removed.")) onDone();
  }
  return (
    <Modal title={`${edit.employee.name} · ${fmtDate(edit.date)}`} onClose={onClose}
      footer={<>{s && <button className="btn danger" type="button" disabled={busy} onClick={remove}>Remove</button>}<button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={save}>Save</button></>}>
      <div className="row">
        <label className="f">Start<input type="time" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></label>
        <label className="f">End<input type="time" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></label>
        <label className="f">Role<input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} /></label>
      </div>
      <span className="small muted">An end time earlier than the start means the shift ends after midnight.</span>
    </Modal>
  );
}

function Timesheets() {
  const { location } = useAuth();
  const [range, setRange] = useState({ start: monday(), end: daysAgo(0) });
  const { data, error, reload } = useApi(`/ops/timesheets/?location=${location.id}&start=${range.start}&end=${range.end}`);
  const [edit, setEdit] = useState(null);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  const t = data?.totals;
  return (
    <>
      <div className="row">
        <label className="f">From<input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></label>
        <label className="f">To<input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></label>
        <button className="btn sm" type="button" onClick={() => setRange({ start: addDays(monday(), -7), end: addDays(monday(), -1) })}>Last week</button>
      </div>
      {!data ? <Loading /> : (
        <>
          <div className="tiles">
            <Tile label="Hours worked" value={t.hours.toFixed(1)} />
            <Tile label="Wages" value={money0(t.cost)} />
            <Tile label="Labour % of sales" value={pct(t.labour_pct)} stripe={t.labour_pct > 0.32 ? "bad" : t.labour_pct > 0.28 ? "warn" : "good"} note="Most restaurants aim for 25–30%" />
            <Tile label="Sales per labour hour" value={t.splh ? money(t.splh) : "—"} />
            <Tile label="Tips to share" value={money(data.tips.total)} note="From card and cash tips on the POS" />
          </div>
          <div className="split">
            <Card title="By day">
              <table>
                <thead><tr><th>Day</th><th className="r">Sales</th><th className="r">Hours</th><th className="r">Wages</th><th className="r">Labour %</th><th className="r">SPLH</th></tr></thead>
                <tbody>{data.days.map((d) => (
                  <tr key={d.date}><td>{fmtDate(d.date)}</td><td className="r">{money0(d.sales)}</td><td className="r">{d.hours.toFixed(1)}</td><td className="r">{money0(d.cost)}</td>
                    <td className="r">{d.labour_pct == null ? "—" : <Pill kind={d.labour_pct > 0.32 ? "bad" : d.labour_pct > 0.28 ? "warn" : "good"}>{pct(d.labour_pct)}</Pill>}</td>
                    <td className="r">{d.splh ? money(d.splh, 0) : "—"}</td></tr>
                ))}</tbody>
              </table>
            </Card>
            <Card title="Tip pool">
              <p className="small muted" style={{ margin: 0 }}>Each day's tips split among tip-sharing staff by hours worked that day.</p>
              {!data.tips.shares.length ? <Empty>No tips to share in this range.</Empty> : (
                <table><tbody>{data.tips.shares.map((s) => <tr key={s.employee}><td>{s.name}</td><td className="r">{money(s.amount)}</td></tr>)}</tbody></table>
              )}
              {data.tips.unassigned > 0 && <div className="note">{money(data.tips.unassigned)} of tips fell on days nobody in the pool clocked in.</div>}
            </Card>
          </div>
          <Card title="People">
            <table>
              <thead><tr><th>Name</th><th>Department</th><th className="r">Rate</th><th className="r">Scheduled</th><th className="r">Worked</th><th className="r">Wages</th></tr></thead>
              <tbody>{data.people.map((p) => (
                <tr key={p.employee}><td>{p.name}</td><td>{p.department}</td><td className="r">{money(p.rate)}</td><td className="r">{p.scheduled.toFixed(1)}</td>
                  <td className={`r ${p.worked > p.scheduled + 2 ? "worse" : ""}`}>{p.worked.toFixed(1)}</td><td className="r">{money0(p.cost)}</td></tr>
              ))}</tbody>
            </table>
          </Card>
          <Card title="Clock-ins">
            <div className="tablewrap">
              <table>
                <thead><tr><th>Name</th><th>In</th><th>Out</th><th className="r">Break</th><th className="r">Hours</th><th /></tr></thead>
                <tbody>{data.entries.map((e) => (
                  <tr key={e.id}><td>{e.name}{e.edited && <> <Pill>Edited</Pill></>}</td><td>{fmtDateTime(e.clock_in)}</td><td>{e.clock_out ? fmtDateTime(e.clock_out) : <Pill kind="good">On shift</Pill>}</td>
                    <td className="r">{e.break_minutes} min</td><td className="r">{e.hours == null ? "—" : e.hours.toFixed(2)}</td>
                    <td className="r"><button className="btn sm" type="button" onClick={() => setEdit(e)}>Edit</button></td></tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      {edit && <EntryDialog entry={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />}
    </>
  );
}

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function EntryDialog({ entry, onClose, onDone }) {
  const [f, setF] = useState({ clock_in: toLocalInput(entry.clock_in), clock_out: toLocalInput(entry.clock_out), break_minutes: entry.break_minutes, note: entry.note });
  const [run, busy] = useAction();
  async function save() {
    const body = { clock_in: new Date(f.clock_in).toISOString(), clock_out: f.clock_out ? new Date(f.clock_out).toISOString() : null, break_minutes: f.break_minutes, note: f.note };
    if (await run(() => api.patch(`/ops/time-entries/${entry.id}/`, body), "Time entry updated. The change is in the change log.")) onDone();
  }
  return (
    <Modal title={`Edit ${entry.name}`} onClose={onClose}
      footer={<><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn primary" type="button" disabled={busy} onClick={save}>Save</button></>}>
      <div className="row">
        <label className="f">Clock in<input type="datetime-local" value={f.clock_in} onChange={(e) => setF({ ...f, clock_in: e.target.value })} /></label>
        <label className="f">Clock out<input type="datetime-local" value={f.clock_out} onChange={(e) => setF({ ...f, clock_out: e.target.value })} /></label>
        <label className="f">Break (min)<input type="number" min="0" value={f.break_minutes} onChange={(e) => setF({ ...f, break_minutes: e.target.value })} /></label>
      </div>
      <label className="f">Note (why it was changed)<input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
    </Modal>
  );
}
