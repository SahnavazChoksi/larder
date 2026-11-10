import { useState } from "react";
import api, { errorText } from "../api";
import { useAuth } from "../auth";
import { Card, Empty, fmtDateTime, minutesSince, useApi, useNow } from "../ui";

/** A kiosk for the restaurant tablet: staff clock in and out with their PIN. */
export default function TimeClock() {
  const { location } = useAuth();
  const { data, reload } = useApi(`/ops/clock/?location=${location.id}`, 30000);
  const [pin, setPin] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const now = useNow(30000);

  async function submit() {
    setBusy(true);
    try {
      const { data: r } = await api.post("/ops/clock/", { location: location.id, pin });
      setMsg({ ok: true, text: r.direction === "in" ? `Welcome, ${r.name}. Clocked in.` : `Bye, ${r.name}. Clocked out after ${r.hours} h.` });
      reload();
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    } finally {
      setPin("");
      setBusy(false);
      setTimeout(() => setMsg(null), 6000);
    }
  }
  const press = (k) => (k === "⌫" ? setPin(pin.slice(0, -1)) : k === "OK" ? submit() : pin.length < 8 && setPin(pin + k));

  return (
    <div className="split">
      <Card title={`Time clock · ${location.name}`}>
        <div className="pin-dots" aria-live="polite">{"●".repeat(pin.length) || <span className="muted small">Enter your PIN</span>}</div>
        <div className="keypad">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "OK"].map((k) => (
            <button key={k} type="button" disabled={busy || (k === "OK" && pin.length < 4)} onClick={() => press(k)}
              aria-label={k === "⌫" ? "Delete" : k === "OK" ? "Clock in or out" : k}>{k}</button>
          ))}
        </div>
        {msg && <div className={`note ${msg.ok ? "" : "error"}`} role="status">{msg.text}</div>}
        <span className="small muted">Your PIN is set by your manager under Team &amp; staffing. Breaks over 5 hours are added automatically and can be corrected by a manager.</span>
      </Card>
      <Card title="On shift now">
        {!data ? null : !data.on_shift.length ? <Empty>Nobody clocked in.</Empty> : (
          <table><tbody>{data.on_shift.map((p, i) => (
            <tr key={i}><td><b>{p.name}</b><div className="small muted">{p.department}</div></td><td className="r small">since {fmtDateTime(p.since)}<div className="muted">{(minutesSince(p.since, now) / 60).toFixed(1)} h</div></td></tr>
          ))}</tbody></table>
        )}
        <h3>Scheduled today</h3>
        {!data?.today.length ? <Empty>No published shifts today.</Empty> : (
          <table><tbody>{data.today.map((s) => <tr key={s.id}><td>{s.employee_name}</td><td className="r">{s.start.slice(0, 5)}–{s.end.slice(0, 5)}</td></tr>)}</tbody></table>
        )}
      </Card>
    </div>
  );
}
