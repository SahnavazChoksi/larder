import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, Loading, MultiLineChart, daysAgo, fmtDate, money, money0, useApi } from "../ui";

// higher = better unless lowerIsBetter. Matches the colours of a weekly ops review sheet.
const METRICS = [
  { key: "sales", label: "Net sales (4 weeks)", fmt: money0 },
  { key: "covers", label: "Covers", fmt: (v) => v.toLocaleString("en-CA") },
  { key: "apc", label: "APC (spend per cover)", fmt: money, help: "Net sales ÷ covers" },
  { key: "avg_bill", label: "Average bill", fmt: money },
  { key: "sssg_4w", label: "SSSG · 4 weeks vs last year", fmt: (v) => `${(v * 100).toFixed(1)}%`, help: "Same-store sales growth" },
  { key: "sssg_qtr", label: "SSSG · quarter vs last year", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "bev_attach", label: "Beverage attach (per cover)", fmt: (v) => v.toFixed(2), help: "Drinks sold ÷ covers" },
  { key: "dessert_attach", label: "Dessert attach (per cover)", fmt: (v) => v.toFixed(2), help: "Desserts sold ÷ covers" },
  { key: "sc_removed_pct", label: "Service charge removed", fmt: (v) => `${(v * 100).toFixed(0)}%`, lowerIsBetter: true, help: "Bills where the guest asked to remove it" },
  { key: "complaints_per_1000", label: "Complaints per 1,000 covers", fmt: (v) => v.toFixed(1), lowerIsBetter: true },
];
const NEUTRAL = new Set(["sales", "covers"]);

function verdict(m, value, avg) {
  if (value == null || avg == null || NEUTRAL.has(m.key)) return "";
  const diff = value - avg;
  if (Math.abs(diff) < Math.abs(avg) * 0.02) return "";
  const better = m.lowerIsBetter ? diff < 0 : diff > 0;
  return better ? "better" : "worse";
}

export default function Performance() {
  const { location } = useAuth();
  const [scope, setScope] = useState("all");
  const [end, setEnd] = useState(daysAgo(1));
  const params = new URLSearchParams({ end });
  if (scope === "one" && location.kind === "outlet") params.set("location", location.id);
  const { data, error } = useApi(`/reports/performance/?${params}`);

  const controls = (
    <div className="row" style={{ justifyContent: "space-between" }}>
      <Chips options={[["all", "All outlets"], ...(location.kind === "outlet" ? [["one", location.name]] : [])]} value={scope} onChange={setScope} />
      <label className="row small muted">Four weeks ending <input type="date" value={end} max={daysAgo(0)} onChange={(e) => e.target.value && setEnd(e.target.value)} /></label>
    </div>
  );
  if (error) return <>{controls}<ErrorBox>{error}</ErrorBox></>;
  if (!data) return <>{controls}<Loading /></>;

  const brands = Object.keys(data.brand_avg);
  const s = data.staffing;
  return (
    <>
      {controls}
      <p className="small muted" style={{ margin: 0 }}>
        {fmtDate(data.period.start)} – {fmtDate(data.period.end)}. Each outlet is compared with its brand average:
        <span className="better"> green is better</span>, <span className="worse">red is worse</span>.
        Growth compares the same weekdays 52 weeks earlier, for stores open both years.
      </p>
      {brands.map((b) => {
        const outlets = data.outlets.filter((o) => o.brand === b);
        const avg = data.brand_avg[b];
        return (
          <Card key={b} title={`${b} · outlet vs brand`}>
            <div className="tablewrap">
              <table className="sheet">
                <thead>
                  <tr><th>Measure</th>{outlets.map((o) => <th key={o.location}>{o.name}</th>)}<th className="brand">Brand avg</th></tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => (
                    <tr key={m.key}>
                      <td title={m.help}>{m.label}</td>
                      {outlets.map((o) => (
                        <td key={o.location} className={verdict(m, o[m.key], avg[m.key])}>{o[m.key] == null ? "—" : m.fmt(o[m.key])}</td>
                      ))}
                      <td className="brand">{avg[m.key] == null ? "—" : m.fmt(avg[m.key])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}
      <div className="split">
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
        <Card title="Staffing">
          {!s.columns.length ? <p className="muted">No staffing plan yet. Set one under Team &amp; staffing.</p> : (
            <div className="tablewrap">
              <table className="sheet">
                <thead>
                  <tr><th />{s.columns.map((c) => <th key={`${c.location}-${c.department}`}>{c.location_name}<div className="small muted">{c.department_label}</div></th>)}<th className="brand">Total</th></tr>
                </thead>
                <tbody>
                  <tr><td>Required</td>{s.columns.map((c) => <td key={c.location + c.department}>{c.required}</td>)}<td className="brand">{s.total.required}</td></tr>
                  <tr><td>Actual</td>{s.columns.map((c) => <td key={c.location + c.department} className={c.actual >= c.required ? "better" : ""}>{c.actual}</td>)}<td className="brand">{s.total.actual}</td></tr>
                  <tr><td>Short</td>{s.columns.map((c) => <td key={c.location + c.department} className={c.gap ? "worse" : ""}>{c.gap}</td>)}<td className="brand worse">{s.total.gap}</td></tr>
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
