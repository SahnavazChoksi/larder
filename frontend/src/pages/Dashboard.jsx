import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, HBars, LineChart, Loading, Pill, Tile, daysAgo, fmtDate, money0, pct, useApi } from "../ui";

export default function Dashboard() {
  const { location } = useAuth();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [scope, setScope] = useState("all");
  const params = new URLSearchParams({ start: daysAgo(days - 1), end: daysAgo(0) });
  if (scope === "one") params.set("location", location.id);
  const { data, error, loading } = useApi(`/reports/dashboard/?${params}`);

  const controls = (
    <div className="row" style={{ justifyContent: "space-between" }}>
      <Chips options={[["all", "All my locations"], ["one", location.name]]} value={scope} onChange={setScope} />
      <Chips options={[[7, "7 days"], [30, "30 days"], [90, "90 days"]]} value={days} onChange={setDays} />
    </div>
  );
  if (error) return <>{controls}<ErrorBox>{error}</ErrorBox></>;
  if (loading || !data) return <>{controls}<Loading /></>;

  const t = data.totals;
  const gap = t.actual_pct != null && t.theoretical_pct != null ? t.actual_pct - t.theoretical_pct : null;
  const series = data.daily_revenue;
  return (
    <>
      {controls}
      <div className="tiles">
        <Tile label={`Net sales · ${days} days`} value={money0(t.revenue)} note={`${fmtDate(data.start)} – ${fmtDate(data.end)}`} />
        <Tile label="Actual food cost" value={pct(t.actual_pct)} note={`Target ${pct(t.target_pct, 0)}`}
          stripe={t.actual_pct > t.target_pct ? "bad" : "good"} />
        <Tile label="Theoretical food cost" value={pct(t.theoretical_pct)} note="What recipes say it should be" />
        <Tile label="Unexplained loss" value={money0(t.unexplained)} note={gap != null ? `${(gap * 100).toFixed(1)} pts of sales` : ""} stripe="warn" />
        <Tile label="Stock on hand" value={money0(t.stock_value)} note={`Logged waste ${money0(t.wastage)}`} />
      </div>
      <div className="split">
        <Card title="Daily sales">
          <LineChart
            values={series.map((d) => d.revenue)}
            labels={series.map((d, i) => (i % 7 === 0 && i < series.length - 4) || i === series.length - 1 ? fmtDate(d.date) : "")}
            format={(v) => "$" + (v / 1000).toFixed(1) + "k"}
          />
        </Card>
        <Card title="Needs attention">
          <div>
            {data.alerts.length === 0 && <div className="empty">All clear.</div>}
            {data.alerts.slice(0, 8).map((a, i) => (
              <div className="alert" key={i}>
                <span className={`bar ${a.severity}`} />
                <div>
                  <b>{a.title}</b>
                  <span className="small muted">{a.detail}</span>
                </div>
                <button className="btn sm" type="button" onClick={() => navigate(a.link)}>Open</button>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <div className="split">
        <Card title="Location scorecard">
          <div className="tablewrap">
            <table>
              <thead>
                <tr><th>Location</th><th className="r">Sales</th><th className="r">Theoretical</th><th className="r">Actual</th><th className="r">Gap</th><th className="r">Unexplained</th></tr>
              </thead>
              <tbody>
                {data.scorecard.map((s) => {
                  const g = s.actual_pct != null ? s.actual_pct - s.theoretical_pct : null;
                  return (
                    <tr key={s.location} className="click" onClick={() => navigate(`/variance?location=${s.location}`)}>
                      <td><b>{s.name}</b></td>
                      <td className="r">{s.revenue ? money0(s.revenue) : <span className="muted">No sales</span>}</td>
                      <td className="r">{pct(s.theoretical_pct)}</td>
                      <td className="r">{pct(s.actual_pct)}</td>
                      <td className="r">{g == null ? "—" : <Pill kind={g > 0.04 ? "bad" : g > 0.025 ? "warn" : "good"}>{(g * 100).toFixed(1)} pts</Pill>}</td>
                      <td className="r">{money0(s.unexplained)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Where the money leaks">
          <HBars rows={data.top_losses.map((r) => ({ label: r.name, value: r.value }))} format={money0} />
        </Card>
      </div>
      <Card title="Opening and closing checklists · last 7 days" actions={<button className="btn sm" type="button" onClick={() => navigate("/checklists?tab=review")}>Review</button>}>
        <div className="tiles">
          {data.checklists.map((c) => (
            <Tile key={c.location} label={c.name} value={c.rate == null ? "—" : `${Math.round(c.rate * 100)}%`}
              note={`${c.submitted} of ${c.expected} done on time`} stripe={c.rate == null ? "" : c.rate < 0.9 ? "bad" : c.rate < 1 ? "warn" : "good"} />
          ))}
        </div>
      </Card>
    </>
  );
}
