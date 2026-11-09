import { useState } from "react";
import { useAuth } from "../auth";
import { Card, Chips, ErrorBox, HBars, Loading, Pill, Tile, daysAgo, fmtDate, money, money0, pct, qty, useApi } from "../ui";

export default function Variance() {
  const { location } = useAuth();
  const [days, setDays] = useState(30);
  const [sort, setSort] = useState("unexplained_value");
  const { data, error } = useApi(`/reports/variance/?location=${location.id}&start=${daysAgo(days - 1)}&end=${daysAgo(0)}`);

  const controls = <Chips options={[[7, "7 days"], [30, "30 days"], [90, "90 days"]]} value={days} onChange={setDays} />;
  if (error) return <>{controls}<ErrorBox>{error}</ErrorBox></>;
  if (!data) return <>{controls}<Loading /></>;
  const s = data.summary;
  const rows = [...data.items].sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1));
  const SortTh = ({ k, children }) => (
    <th className="r"><button type="button" className={`chip ${sort === k ? "on" : ""}`} onClick={() => setSort(k)}>{children}</button></th>
  );

  return (
    <>
      {controls}
      <div className="tiles">
        <Tile label="Actual usage (COGS)" value={money0(s.actual_cost)} note={`${fmtDate(data.start)} – ${fmtDate(data.end)}`} />
        <Tile label="Theoretical usage" value={money0(s.theoretical_cost)} note={s.revenue ? "Recipes × POS sales" : "Recipes × what was made"} />
        <Tile label="Logged wastage" value={money0(s.wastage)} note="Explained loss" stripe="warn" />
        <Tile label="Unexplained" value={money0(s.unexplained)} note="Found missing at stock counts" stripe="bad" />
        {s.revenue > 0 && <Tile label="Food cost" value={pct(s.actual_pct)} note={`Should be ${pct(s.theoretical_pct)} · target ${pct(s.target_pct, 0)}`} stripe={s.actual_pct > s.target_pct ? "bad" : "good"} />}
      </div>
      <Card title="How the cost adds up">
        <div className="tablewrap">
          <table>
            <tbody>
              <tr><td>Opening stock</td><td className="r">{money(s.opening_value)}</td></tr>
              <tr><td>+ Deliveries</td><td className="r">{money(s.purchases)}</td></tr>
              <tr><td>+ Transfers in</td><td className="r">{money(s.transfers_in)}</td></tr>
              <tr><td>− Transfers out</td><td className="r">{money(-s.transfers_out)}</td></tr>
              {s.production_net !== 0 && <tr><td>± Production (prep made minus ingredients used)</td><td className="r">{money(s.production_net)}</td></tr>}
              <tr><td>− Closing stock</td><td className="r">{money(-s.closing_value)}</td></tr>
              <tr><td><b>= Actual usage</b> (sold + wasted + unexplained)</td><td className="r"><b>{money(s.actual_cost)}</b></td></tr>
            </tbody>
          </table>
        </div>
      </Card>
      <div className="split">
        <Card title={`Item variance · ${data.location_name}`}>
          <div className="tablewrap">
            <table>
              <thead>
                <tr><th>Item</th><th className="r">Should use</th><th className="r">Used</th><th className="r">Wasted</th>
                  <SortTh k="unexplained_pct">Unexplained %</SortTh><SortTh k="unexplained_value">Unexplained $</SortTh></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.item}>
                    <td><b>{r.name}</b></td>
                    <td className="r">{qty(r.theoretical_qty, r.unit)}</td><td className="r">{qty(r.actual_qty, r.unit)}</td>
                    <td className="r muted">{r.wastage_qty ? qty(r.wastage_qty, r.unit) : "—"}</td>
                    <td className="r">{r.unexplained_pct == null ? "—" : <Pill kind={r.unexplained_pct > 0.1 ? "bad" : r.unexplained_pct > 0.05 ? "warn" : "good"}>{pct(r.unexplained_pct)}</Pill>}</td>
                    <td className="r">{money(r.unexplained_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Biggest unexplained losses">
          <HBars rows={data.items.filter((r) => r.unexplained_value > 0).slice(0, 8).map((r) => ({ label: r.name, value: r.unexplained_value }))} format={money0} />
          <div className="note">
            "Should use" is recipes × what the POS sold. "Used" adds logged waste and what stock counts found missing. Unexplained loss
            usually means over-portioning, theft, receiving mistakes or a recipe that's wrong.
          </div>
        </Card>
      </div>
    </>
  );
}
