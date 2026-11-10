import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Pill, fmtDate, fmtDateTime, useApi } from "../ui";

/** Temperature and other readings from checklists, as charts plus a printable log for inspectors. */
export default function Readings() {
  const { location } = useAuth();
  const [days, setDays] = useState(30);
  const { data, error } = useApi(`/checklists/readings/?location=${location.id}&days=${days}`);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  return (
    <>
      <div className="row no-print" style={{ justifyContent: "space-between" }}>
        <Chips options={[[7, "7 days"], [30, "30 days"], [90, "90 days"]]} value={days} onChange={setDays} />
        <button className="btn" type="button" onClick={() => window.print()}>Print log</button>
      </div>
      {!data ? <Loading /> : !data.series.length ? <Empty>No readings recorded at {location.name} yet.</Empty> : data.series.map((s) => (
        <Card key={s.label} title={`${s.label} · ${location.name}`} actions={s.out_of_range ? <Pill kind="bad">{s.out_of_range} out of range</Pill> : <Pill kind="good">All in range</Pill>}>
          <ReadingChart s={s} />
          <details>
            <summary className="small">Show the log ({s.points.length} readings)</summary>
            <table>
              <thead><tr><th>Day</th><th>Checklist</th><th className="r">Reading</th><th>By</th><th>Recorded</th></tr></thead>
              <tbody>
                {[...s.points].reverse().map((p, i) => (
                  <tr key={i}>
                    <td>{fmtDate(p.date)}</td><td>{p.checklist}</td>
                    <td className="r">{p.ok ? `${p.value}${s.unit}` : <Pill kind="bad">{p.value}{s.unit}</Pill>}</td>
                    <td className="small">{p.by || "—"}</td><td className="small muted">{fmtDateTime(p.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </Card>
      ))}
    </>
  );
}

function ReadingChart({ s }) {
  const w = 760, h = 200, L = 46, R = 16, T = 12, B = 26;
  const vals = s.points.map((p) => p.value);
  const bounds = [s.min, s.max].filter((b) => b != null);
  let lo = Math.min(...vals, ...bounds), hi = Math.max(...vals, ...bounds);
  const pad = (hi - lo || 1) * 0.15;
  lo -= pad; hi += pad;
  const n = s.points.length;
  const x = (i) => L + (n === 1 ? 0 : (i * (w - L - R)) / (n - 1));
  const y = (v) => T + (h - T - B) * (1 - (v - lo) / (hi - lo));
  const ticks = [0, 1, 2, 3].map((k) => lo + ((hi - lo) * k) / 3);
  const every = Math.max(1, Math.ceil(n / 8));
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${s.label} readings`}>
      {s.min != null && s.max != null && (
        <rect x={L} y={y(s.max)} width={w - L - R} height={y(s.min) - y(s.max)} fill="var(--good)" opacity=".08" />
      )}
      {ticks.map((t, k) => (
        <g key={k}><line x1={L} x2={w - R} y1={y(t)} y2={y(t)} stroke="var(--line)" /><text x={L - 6} y={y(t) + 4} textAnchor="end">{t.toFixed(1)}</text></g>
      ))}
      {bounds.map((b) => <line key={b} x1={L} x2={w - R} y1={y(b)} y2={y(b)} stroke="var(--good)" strokeDasharray="4 4" />)}
      <polyline points={s.points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      {s.points.map((p, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(p.value)} r={p.ok ? 3 : 5} fill={p.ok ? "var(--accent)" : "var(--bad)"} />
          {i % every === 0 && <text x={x(i)} y={h - 6} textAnchor="middle">{fmtDate(p.date)}</text>}
        </g>
      ))}
    </svg>
  );
}
