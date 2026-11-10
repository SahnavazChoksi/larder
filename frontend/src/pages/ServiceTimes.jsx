import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, MultiLineChart, Tile, daysAgo, pct, useApi } from "../ui";

const fmt = (m) => (m == null ? "—" : `${m.toFixed(1)} min`);
const COLORS = { seating: "var(--info)", order: "var(--warn)", prep: "var(--accent)", pass: "var(--bad)" };

export default function ServiceTimes() {
  const { location } = useAuth();
  const [days, setDays] = useState(14);
  const { data, error } = useApi(location.kind === "outlet" ? `/reports/service-times/?location=${location.id}&start=${daysAgo(days - 1)}&end=${daysAgo(0)}` : null);

  if (location.kind !== "outlet") return <Card title="Service times"><p className="muted" style={{ margin: 0 }}>Pick an outlet at the top.</p></Card>;
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!data) return <Loading />;
  const has = data.stages.some((s) => s.count);
  const hourLabel = (h) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <Chips options={[[7, "7 days"], [14, "14 days"], [30, "30 days"]]} value={days} onChange={setDays} />
        <span className="small muted">From POS, kitchen display and waitlist timestamps at {location.name}.</span>
      </div>
      {!has ? <Empty>No timed orders yet. Take orders on the POS and use the kitchen display, and this fills in by itself.</Empty> : (
        <>
          <div className="tiles">
            {data.stages.map((s) => (
              <Tile key={s.key} label={s.label} value={fmt(s.avg)}
                note={s.count ? `90% within ${fmt(s.p90)} · Mon–Thu ${fmt(s.weekday)} · Fri–Sun ${fmt(s.weekend)}` : "No data"} />
            ))}
          </div>
          <div className="split">
            <Card title="By hour of day">
              <MultiLineChart
                labels={data.hours.map(hourLabel)}
                series={["seating", "order", "prep", "pass"].filter((k) => data.by_hour[k].some((h) => h.avg != null)).map((k) => ({
                  name: data.stages.find((s) => s.key === k).label, color: COLORS[k], values: data.by_hour[k].map((h) => h.avg ?? 0),
                }))}
                format={(v) => `${v.toFixed(0)}m`}
              />
            </Card>
            <Card title="Kitchen and host stand">
              <div className="tiles">
                <Tile label={`Tickets over ${data.kitchen.target} min`} value={pct(data.kitchen.late_pct, 0)} note={`${data.kitchen.late} of ${data.kitchen.tickets}`}
                  stripe={data.kitchen.late_pct > 0.2 ? "bad" : data.kitchen.late_pct > 0.1 ? "warn" : "good"} />
                <Tile label="Waits longer than quoted" value={data.quotes.parties ? `${data.quotes.over_quote} of ${data.quotes.parties}` : "—"}
                  note={data.quotes.parties ? `Quoted ${fmt(data.quotes.avg_quoted)}, waited ${fmt(data.quotes.avg_actual)}` : "No waitlist data"} />
              </div>
              <p className="small muted" style={{ margin: 0 }}>
                Long "waiting for a cook" means the line is short-staffed; long "ready → served" means food sits at the pass, so add a runner;
                long "seated → order sent" points at the floor team.
              </p>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
