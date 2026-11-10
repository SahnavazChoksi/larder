import { useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, Loading, MultiLineChart, daysAgo, fmtDate, money, money0, useAction, useApi } from "../ui";

const PLATFORMS = { uber_eats: "Uber Eats", doordash: "DoorDash", skip: "SkipTheDishes" };
const pctf = (d = 0) => (v) => `${(v * 100).toFixed(d)}%`;

// lowerIsBetter decides the colour: green = better than the brand average, red = worse
const METRICS = [
  { key: "sales", label: "Net sales (4 weeks)", fmt: money0, neutral: true },
  { key: "covers", label: "Covers", fmt: (v) => v.toLocaleString("en-CA"), neutral: true },
  { key: "apc", label: "APC (spend per cover)", fmt: money },
  { key: "avg_bill", label: "Average bill", fmt: money },
  { key: "sssg_4w", label: "SSSG · 4 weeks vs last year", fmt: pctf(1) },
  { key: "sssg_qtr", label: "SSSG · quarter vs last year", fmt: pctf(1) },
  { key: "bev_attach", label: "Beverage attach (per cover)", fmt: (v) => v.toFixed(2) },
  { key: "dessert_attach", label: "Dessert attach (per cover)", fmt: (v) => v.toFixed(2) },
  { key: "prep_weekday", label: "Avg prep time Mon–Thu (min)", fmt: (v) => v.toFixed(1), lowerIsBetter: true },
  { key: "prep_weekend", label: "Avg prep time Fri–Sun (min)", fmt: (v) => v.toFixed(1), lowerIsBetter: true },
  { key: "loyalty_pct", label: "Loyalty enrollment", fmt: pctf(0) },
  { key: "sc_removed_pct", label: "Service charge removed", fmt: pctf(0), lowerIsBetter: true },
  { key: "wrong", label: "Wrong items (delivery)", fmt: (v) => Math.round(v), lowerIsBetter: true },
  { key: "missing", label: "Missing items (delivery)", fmt: (v) => Math.round(v), lowerIsBetter: true },
  { key: "complaints_per_1000", label: "Complaints per 1,000 covers", fmt: (v) => v.toFixed(1), lowerIsBetter: true },
];
const M = Object.fromEntries(METRICS.map((m) => [m.key, m]));

function tone(m, value, avg) {
  if (value == null || avg == null || m.neutral) return "";
  if (Math.abs(value - avg) < Math.abs(avg) * 0.02) return "";
  return (m.lowerIsBetter ? value < avg : value > avg) ? "better" : "worse";
}
const show = (m, v) => (v == null ? "—" : m.fmt(v));

export default function Performance() {
  const { location, can } = useAuth();
  const [scope, setScope] = useState("all");
  const [end, setEnd] = useState(daysAgo(1));
  const params = new URLSearchParams({ end });
  if (scope === "one" && location.kind === "outlet") params.set("location", location.id);
  const { data, error, reload } = useApi(`/reports/performance/?${params}`);

  const controls = (
    <div className="row no-print" style={{ justifyContent: "space-between" }}>
      <Chips options={[["all", "All outlets"], ...(location.kind === "outlet" ? [["one", location.name]] : [])]} value={scope} onChange={setScope} />
      <div className="row">
        <label className="row small muted">Four weeks ending <input type="date" value={end} max={daysAgo(0)} onChange={(e) => e.target.value && setEnd(e.target.value)} /></label>
        <button className="btn" type="button" onClick={() => window.print()}>Print</button>
      </div>
    </div>
  );
  if (error) return <>{controls}<ErrorBox>{error}</ErrorBox></>;
  if (!data) return <>{controls}<Loading /></>;

  return (
    <>
      {controls}
      <p className="small muted" style={{ margin: 0 }}>
        Weekly ops review, {fmtDate(data.period.start)} – {fmtDate(data.period.end)}. Each outlet vs its brand average:
        <span className="better"> green is better</span>, <span className="worse">red is worse</span>. Growth compares the same weekdays 52 weeks earlier.
      </p>
      <Staffing s={data.staffing} />
      {Object.keys(data.brand_avg).map((b) => (
        <Sheet key={b} brand={b} outlets={data.outlets.filter((o) => o.brand === b)} avg={data.brand_avg[b]} />
      ))}
      <Card title="Weekly sales vs last year">
        <MultiLineChart
          labels={data.trend.map((t, i) => (i % 3 === 0 || i === data.trend.length - 1 ? fmtDate(t.week_start) : ""))}
          series={[
            { name: "This year", values: data.trend.map((t) => t.this_year), color: "var(--accent)" },
            { name: "Last year", values: data.trend.map((t) => t.last_year), color: "var(--muted)", dashed: true },
          ]}
          format={(v) => "$" + (v / 1000).toFixed(0) + "k"}
        />
      </Card>
      {can("manager") && <DeliveryEntry outlets={data.outlets} onSaved={reload} />}
    </>
  );
}

function Staffing({ s }) {
  if (!s.columns.length) return <Card title="Staffing"><p className="muted" style={{ margin: 0 }}>No staffing plan yet. Set one under Team &amp; staffing.</p></Card>;
  return (
    <Card title="Staffing">
      <div className="tablewrap">
        <table className="sheet">
          <thead><tr><th />{s.columns.map((c) => <th key={c.location + c.department}>{c.location_name}<div className="small muted">{c.department_label}</div></th>)}<th className="brand">Total</th></tr></thead>
          <tbody>
            <tr><td><b>Ideal</b></td>{s.columns.map((c) => <td key={c.location + c.department}>{c.required}</td>)}<td className="brand">{s.total.required}</td></tr>
            <tr><td><b>Current</b></td>{s.columns.map((c) => <td key={c.location + c.department} className={c.actual >= c.required ? "better" : ""}>{c.actual}</td>)}<td className="brand">{s.total.actual}</td></tr>
            <tr><td><b>Gap</b></td>{s.columns.map((c) => <td key={c.location + c.department} className={c.gap ? "worse" : ""}>{c.gap}</td>)}<td className={`brand ${s.total.gap ? "worse" : ""}`}>{s.total.gap}</td></tr>
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/** The ops-review sheet for one brand: small tables like the printed version. */
function Sheet({ brand, outlets, avg }) {
  const cell = (key, o) => <td className={tone(M[key], o[key], avg[key])}>{show(M[key], o[key])}</td>;
  const outletVsBrand = (title, keys, labels) => (
    <table className="sheet">
      <thead><tr><th>{title}</th>{outlets.flatMap((o) => [<th key={o.location}>{o.name}</th>, <th key={o.location + "b"} className="brand">Brand avg</th>])}</tr></thead>
      <tbody>
        {keys.map((k, i) => (
          <tr key={k}><td>{labels[i]}</td>{outlets.flatMap((o) => [<td key={o.location} className={tone(M[k], o[k], avg[k])}>{show(M[k], o[k])}</td>, <td key={o.location + "b"} className="brand">{show(M[k], avg[k])}</td>])}</tr>
        ))}
      </tbody>
    </table>
  );
  const platforms = [...new Set(outlets.flatMap((o) => Object.keys(o.delivery || {})))];

  return (
    <>
      <h2 style={{ margin: "4px 0 -4px" }}>{brand}</h2>
      <div className="grid3">
        <Card title="Average prep time (minutes)">
          <table className="sheet">
            <thead><tr><th />{outlets.map((o) => <th key={o.location}>{o.name}</th>)}</tr></thead>
            <tbody>
              <tr><td>Mon – Thu</td>{outlets.map((o) => <td key={o.location} className={tone(M.prep_weekday, o.prep_weekday, avg.prep_weekday)}>{show(M.prep_weekday, o.prep_weekday)}</td>)}</tr>
              <tr className="brand"><td><b>Mon – Thu brand avg</b></td>{outlets.map((o) => <td key={o.location}><b>{show(M.prep_weekday, avg.prep_weekday)}</b></td>)}</tr>
              <tr><td>Fri – Sun</td>{outlets.map((o) => <td key={o.location} className={tone(M.prep_weekend, o.prep_weekend, avg.prep_weekend)}>{show(M.prep_weekend, o.prep_weekend)}</td>)}</tr>
              <tr className="brand"><td><b>Fri – Sun brand avg</b></td>{outlets.map((o) => <td key={o.location}><b>{show(M.prep_weekend, avg.prep_weekend)}</b></td>)}</tr>
            </tbody>
          </table>
        </Card>
        <Card title="APC (spend per cover)">
          <table className="sheet">
            <thead><tr><th>Outlet</th><th>APC</th><th className="brand">Brand</th></tr></thead>
            <tbody>{outlets.map((o) => <tr key={o.location}><td>{o.name}</td>{cell("apc", o)}<td className="brand">{show(M.apc, avg.apc)}</td></tr>)}</tbody>
          </table>
        </Card>
        <Card title="SSSG report">
          <table className="sheet">
            <thead><tr><th>Outlet</th><th>4 week YoY</th><th>Qtr YoY</th></tr></thead>
            <tbody>
              {outlets.map((o) => (
                <tr key={o.location}><td>{o.name}</td>{cell("sssg_4w", o)}{cell("sssg_qtr", o)}</tr>
              ))}
              <tr className="brand"><td><b>Brand</b></td><td><b>{show(M.sssg_4w, avg.sssg_4w)}</b></td><td><b>{show(M.sssg_qtr, avg.sssg_qtr)}</b></td></tr>
            </tbody>
          </table>
        </Card>
        <Card title="Delivery: food-ready accuracy">
          {!platforms.length ? <p className="small muted" style={{ margin: 0 }}>No delivery app scores entered yet.</p> : (
            <table className="sheet">
              <thead><tr><th>Outlet</th>{platforms.map((p) => <th key={p}>{PLATFORMS[p] || p}</th>)}</tr></thead>
              <tbody>
                {outlets.map((o) => (
                  <tr key={o.location}><td>{o.name}</td>{platforms.map((p) => {
                    const v = o.delivery?.[p]?.ready_accuracy, a = avg.delivery?.[p]?.ready_accuracy;
                    return <td key={p} className={v == null || a == null ? "" : v >= a ? "better" : "worse"}>{v == null ? "—" : `${v.toFixed(0)}%`}</td>;
                  })}</tr>
                ))}
                <tr className="brand"><td><b>Brand</b></td>{platforms.map((p) => <td key={p}><b>{avg.delivery?.[p]?.ready_accuracy == null ? "—" : `${avg.delivery[p].ready_accuracy.toFixed(0)}%`}</b></td>)}</tr>
              </tbody>
            </table>
          )}
          <span className="small muted">Orders marked ready when the food really was ready (from the partner dashboard).</span>
        </Card>
        <Card title="Loyalty enrollment">
          <table className="sheet">
            <thead><tr><th>Outlet</th><th>Enrollment</th><th className="brand">Brand</th></tr></thead>
            <tbody>{outlets.map((o) => <tr key={o.location}><td>{o.name}</td>{cell("loyalty_pct", o)}<td className="brand">{show(M.loyalty_pct, avg.loyalty_pct)}</td></tr>)}</tbody>
          </table>
          <span className="small muted">Bills where the guest was or joined as a loyalty member.</span>
        </Card>
        <Card title="Service charge removed">
          <table className="sheet">
            <thead><tr><th>Outlet</th><th>SC removed</th><th className="brand">Brand</th></tr></thead>
            <tbody>{outlets.map((o) => <tr key={o.location}><td>{o.name}</td>{cell("sc_removed_pct", o)}<td className="brand">{show(M.sc_removed_pct, avg.sc_removed_pct)}</td></tr>)}</tbody>
          </table>
        </Card>
      </div>
      <div className="split">
        <Card title="Attach ratio (per cover)"><div className="tablewrap">{outletVsBrand("", ["bev_attach", "dessert_attach"], ["Bev", "Desserts"])}</div></Card>
        <Card title="Delivery accuracy (orders, 4 weeks)"><div className="tablewrap">{outletVsBrand("", ["wrong", "missing"], ["Wrong", "Missing"])}</div></Card>
      </div>
      <Card title={`All measures · ${brand}`}>
        <div className="tablewrap">
          <table className="sheet">
            <thead><tr><th>Measure</th>{outlets.map((o) => <th key={o.location}>{o.name}</th>)}<th className="brand">Brand avg</th></tr></thead>
            <tbody>
              {METRICS.map((m) => (
                <tr key={m.key}><td>{m.label}</td>{outlets.map((o) => <td key={o.location} className={tone(m, o[m.key], avg[m.key])}>{show(m, o[m.key])}</td>)}<td className="brand">{show(m, avg[m.key])}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function DeliveryEntry({ outlets, onSaved }) {
  const monday = (() => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7); return d.toISOString().slice(0, 10); })();
  const [f, setF] = useState({ location: outlets[0]?.location || "", platform: "uber_eats", week_start: monday, orders: "", ready_accuracy: "", rating: "" });
  const [run, busy] = useAction();
  async function submit(e) {
    e.preventDefault();
    const body = { ...f, orders: f.orders || 0, ready_accuracy: f.ready_accuracy || null, rating: f.rating || null };
    if (await run(() => api.post("/ops/delivery-scores/", body), "Delivery score saved.")) { setF({ ...f, orders: "", ready_accuracy: "", rating: "" }); onSaved(); }
  }
  return (
    <Card title="Enter delivery app scores" className="no-print">
      <p className="small muted" style={{ margin: 0 }}>Copy last week's numbers from each partner dashboard. Entering the same week again replaces it.</p>
      <form className="row" onSubmit={submit}>
        <label className="f">Outlet<select value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })}>{outlets.map((o) => <option key={o.location} value={o.location}>{o.name}</option>)}</select></label>
        <label className="f">App<select value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>{Object.entries(PLATFORMS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="f">Week starting<input type="date" value={f.week_start} onChange={(e) => setF({ ...f, week_start: e.target.value })} required /></label>
        <label className="f">Orders<input type="number" min="0" step="1" value={f.orders} onChange={(e) => setF({ ...f, orders: e.target.value })} required /></label>
        <label className="f">Food-ready accuracy %<input type="number" min="0" max="100" step="0.1" value={f.ready_accuracy} onChange={(e) => setF({ ...f, ready_accuracy: e.target.value })} /></label>
        <label className="f">Rating<input type="number" min="0" max="5" step="0.01" value={f.rating} onChange={(e) => setF({ ...f, rating: e.target.value })} /></label>
        <button className="btn primary" type="submit" disabled={busy}>Save</button>
      </form>
    </Card>
  );
}
