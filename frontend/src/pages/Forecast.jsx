import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api";
import { useAuth } from "../auth";
import { Bars, Card, Empty, ErrorBox, Loading, NumberInput, Tile, fmtDate, money, money0, qty, useAction, useApi } from "../ui";

const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dayLabel = (iso) => WD[new Date(iso + "T12:00:00").getDay()];

export default function Forecast() {
  const { location, locations, setLocationId } = useAuth();
  const isOutlet = location.kind === "outlet";
  const { data, error } = useApi(isOutlet ? `/reports/forecast/?location=${location.id}` : null);
  const [picks, setPicks] = useState(null);
  const [run, busy] = useAction();
  const navigate = useNavigate();

  if (!isOutlet) {
    return (
      <Card title="Forecast & reorder">
        <p className="muted" style={{ margin: 0 }}>Forecasts are per outlet. Pick one:</p>
        <div className="row">{locations.filter((l) => l.kind === "outlet").map((l) => <button key={l.id} className="btn" type="button" onClick={() => setLocationId(l.id)}>{l.name}</button>)}</div>
      </Card>
    );
  }
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!data) return <Loading />;

  const reorder = data.reorder;
  const sel = picks || Object.fromEntries(reorder.map((r) => [r.item, r.suggested]));
  const chosen = reorder.filter((r) => Number(sel[r.item]) > 0);
  const busiest = data.totals.indexOf(Math.max(...data.totals));

  async function createOrders() {
    const res = await run(() => api.post("/purchasing/suggestions/", { location: location.id, lines: chosen.map((r) => ({ item: r.item, qty: sel[r.item] })) }),
      (d) => `${d.length} draft order${d.length > 1 ? "s" : ""} created: ${d.map((o) => o.number).join(", ")}.`);
    if (res) navigate("/purchasing");
  }

  return (
    <>
      <p className="small muted" style={{ margin: 0 }}>
        Each day = the average of the same weekday over the last 4 weeks × the recent trend ({((data.trend - 1) * 100).toFixed(1)}%).
        Orders cover each vendor's lead time plus 2 days, minus stock on hand and what's already on order.
      </p>
      <div className="tiles">
        <Tile label="Portions, next 7 days" value={data.totals.reduce((a, b) => a + b, 0).toLocaleString("en-CA")} />
        <Tile label="Expected sales" value={money0(data.revenue.reduce((a, b) => a + b, 0))} />
        <Tile label="Busiest day" value={`${dayLabel(data.dates[busiest])} ${fmtDate(data.dates[busiest])}`} />
        <Tile label="Items to order" value={reorder.length} stripe={reorder.length ? "warn" : "good"} />
      </div>
      <div className="split">
        <Card title={`Portions forecast · ${location.name}`}>
          <Bars values={data.totals} labels={data.dates.map((d) => `${dayLabel(d)} ${Number(d.slice(8))}`)} />
          <div className="tablewrap">
            <table>
              <thead><tr><th>Dish</th>{data.dates.map((d) => <th key={d} className="r">{dayLabel(d)}</th>)}<th className="r">Week</th></tr></thead>
              <tbody>
                {data.dishes.filter((d) => d.total > 0).map((d) => (
                  <tr key={d.id}><td>{d.name}</td>{d.days.map((q, i) => <td key={i} className="r">{q}</td>)}<td className="r"><b>{d.total}</b></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Smart reorder" actions={<button className="btn primary" type="button" disabled={busy || !chosen.length} onClick={createOrders}>Create draft orders</button>}>
          {!reorder.length ? <Empty>Stock and open orders cover the forecast.</Empty> : (
            <div className="tablewrap">
              <table>
                <thead><tr><th>Item</th><th className="r">Need</th><th className="r">Have</th><th className="r">On order</th><th className="r">Order</th><th className="r">Cost</th></tr></thead>
                <tbody>
                  {reorder.map((r) => (
                    <tr key={r.item}>
                      <td><b>{r.name}</b><div className="small muted">{r.vendor_name} · {r.lead_days}-day lead</div></td>
                      <td className="r">{qty(r.need, r.unit)}</td><td className="r">{qty(r.on_hand, r.unit)}</td><td className="r muted">{qty(r.on_order, r.unit)}</td>
                      <td className="r"><NumberInput value={sel[r.item]} step="0.5" label={`Order ${r.name}`} onChange={(v) => setPicks({ ...sel, [r.item]: v })} /> {r.unit}</td>
                      <td className="r">{money(Number(sel[r.item] || 0) * r.unit_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {chosen.length > 0 && <b className="num">Total {money(chosen.reduce((s, r) => s + Number(sel[r.item]) * r.unit_price, 0))}</b>}
        </Card>
      </div>
    </>
  );
}
