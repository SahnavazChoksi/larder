import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Pill, daysAgo, money, money0, pct, useApi } from "../ui";

const KIND = { star: "good", plowhorse: "warn", puzzle: "info", dog: "bad" };
const COLOR = { star: "var(--good)", plowhorse: "var(--warn)", puzzle: "var(--info)", dog: "var(--bad)" };

export default function MenuEngineering() {
  const { location } = useAuth();
  const cats = useApi("/menu-categories/");
  const [category, setCategory] = useState("All");
  const [scope, setScope] = useState("all");
  const [days, setDays] = useState(30);
  const params = new URLSearchParams({ start: daysAgo(days), end: daysAgo(1) });
  if (category !== "All") params.set("category", category);
  if (scope === "one") params.set("location", location.id);
  const { data, error } = useApi(`/reports/menu-engineering/?${params}`);

  const controls = (
    <div className="row" style={{ justifyContent: "space-between" }}>
      <Chips options={[["All", "All"], ...(cats.data || []).map((c) => [c.name, `${c.icon} ${c.name}`])]} value={category} onChange={setCategory} />
      <div className="row">
        <Chips options={[["all", "All outlets"], ...(location.kind === "outlet" ? [["one", location.name]] : [])]} value={scope} onChange={setScope} />
        <Chips options={[[30, "30 days"], [90, "90 days"]]} value={days} onChange={setDays} />
      </div>
    </div>
  );
  if (error) return <>{controls}<ErrorBox>{error}</ErrorBox></>;
  if (!data) return <>{controls}<Loading /></>;
  const rows = data.rows.filter((r) => r.qty > 0);

  return (
    <>
      {controls}
      <p className="small muted" style={{ margin: 0 }}>Compare dishes within one category. A dish is popular if it sells at least 70% of a fair share; profitable if its margin beats the category's average.</p>
      {!rows.length ? <Empty>No sales for this category in the range.</Empty> : (
        <>
          <div className="split">
            <Card title="Popularity vs margin"><Scatter rows={rows} qtyLine={data.popularity_threshold} marginLine={data.average_margin} /></Card>
            <Card title="What to do">
              {Object.entries(data.classes).map(([k, [label, advice]]) => {
                const dishes = rows.filter((r) => r.class === k);
                return (
                  <div key={k} style={{ borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
                    <div className="row"><Pill kind={KIND[k]}>{label}</Pill><span className="small muted">{dishes.length} dish{dishes.length === 1 ? "" : "es"}</span></div>
                    <p style={{ margin: "4px 0" }}>{advice}</p>
                    <p className="small muted" style={{ margin: 0 }}>{dishes.map((d) => d.name).join(", ") || "None"}</p>
                  </div>
                );
              })}
            </Card>
          </div>
          <Card title="Dishes">
            <div className="tablewrap">
              <table>
                <thead><tr><th>Dish</th><th className="r">Sold</th><th className="r">Mix</th><th className="r">Avg price</th><th className="r">Plate cost</th><th className="r">Food cost</th><th className="r">Margin</th><th className="r">Total margin</th><th>Class</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td><b>{r.name}</b></td><td className="r">{r.qty.toLocaleString("en-CA")}</td><td className="r">{pct(r.mix)}</td>
                      <td className="r">{money(r.price)}</td><td className="r">{money(r.cost)}</td><td className="r">{pct(r.food_cost_pct)}</td>
                      <td className="r">{money(r.margin)}</td><td className="r">{money0(r.total_margin)}</td>
                      <td><Pill kind={KIND[r.class]}>{data.classes[r.class][0]}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </>
  );
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v || 1));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function Scatter({ rows, qtyLine, marginLine }) {
  const w = 640, h = 330, L = 56, R = 20, T = 16, B = 40;
  const maxQ = niceMax(Math.max(...rows.map((r) => r.qty)) * 1.1);
  const maxM = niceMax(Math.max(...rows.map((r) => r.margin)) * 1.15);
  const x = (q) => L + ((w - L - R) * q) / maxQ;
  const y = (m) => T + (h - T - B) * (1 - m / maxM);
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Menu engineering chart">
      {[0, 1, 2, 3, 4].map((k) => (
        <g key={k}>
          <line x1={L} x2={w - R} y1={y((maxM * k) / 4)} y2={y((maxM * k) / 4)} stroke="var(--line)" />
          <text x={L - 6} y={y((maxM * k) / 4) + 4} textAnchor="end">${((maxM * k) / 4).toFixed(0)}</text>
          <text x={x((maxQ * k) / 4)} y={h - 22} textAnchor="middle">{Math.round((maxQ * k) / 4)}</text>
        </g>
      ))}
      <text x={(L + w) / 2} y={h - 4} textAnchor="middle">Portions sold</text>
      <line x1={x(qtyLine)} x2={x(qtyLine)} y1={T} y2={h - B} stroke="var(--muted)" strokeDasharray="4 4" />
      <line x1={L} x2={w - R} y1={y(marginLine)} y2={y(marginLine)} stroke="var(--muted)" strokeDasharray="4 4" />
      {rows.map((r) => {
        const px = x(r.qty), py = y(r.margin), right = px < w - 150;
        return (
          <g key={r.id}>
            <circle cx={px} cy={py} r="6" fill={COLOR[r.class]} />
            <text className="lbl" x={right ? px + 9 : px - 9} y={py + 4} textAnchor={right ? "start" : "end"}>{r.name}</text>
          </g>
        );
      })}
    </svg>
  );
}
