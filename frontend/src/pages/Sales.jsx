import { useRef, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Tile, daysAgo, fmtDate, fmtDateTime, money, money0, useAction, useApi } from "../ui";

export default function Sales() {
  const { location } = useAuth();
  const [days, setDays] = useState(30);
  const range = `start=${daysAgo(days - 1)}&end=${daysAgo(0)}`;
  const list = useApi(`/sales/days/?location=${location.id}&${range}`);
  const items = useApi(`/sales/items/?location=${location.id}&${range}`);
  const menu = useApi("/menu-items/");
  const file = useRef();
  const [run, busy] = useAction();

  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return;
    const body = new FormData();
    body.append("file", f);
    const ok = await run(() => api.post("/sales/import/", body), (d) => `Imported ${d.days} day${d.days > 1 ? "s" : ""} of sales. Theoretical usage booked.`);
    file.current.value = "";
    if (ok) { list.reload(); items.reload(); }
  }

  function sampleCsv() {
    const today = daysAgo(0);
    const rows = (menu.data || []).slice(0, 4).map((m) => `${today},${location.code},${m.pos_code},10,${(m.price * 10).toFixed(2)}`);
    const blob = new Blob([["date,location,pos_code,qty,net_sales", ...rows].join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "larder-sales-sample.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (location.kind !== "outlet") return <Card title="Sales import"><p className="muted" style={{ margin: 0 }}>{location.name} doesn't sell to customers. Pick an outlet at the top.</p></Card>;
  const total = (list.data || []).reduce((s, d) => s + d.net_sales, 0);
  const portions = (list.data || []).reduce((s, d) => s + d.portions, 0);

  return (
    <>
      <Chips options={[[7, "7 days"], [30, "30 days"], [90, "90 days"]]} value={days} onChange={setDays} />
      <div className="tiles">
        <Tile label="Net sales" value={money0(total)} note={location.name} />
        <Tile label="Portions sold" value={portions.toLocaleString("en-CA")} />
        <Tile label="Days imported" value={list.data?.length ?? "—"} />
      </div>
      <Card title="Import from your POS">
        <p className="small muted" style={{ margin: 0 }}>
          Export daily item sales as CSV with columns <code>date, location, pos_code, qty, net_sales</code>. Location is the code
          (this one is <b>{location.code}</b>). Importing a day again replaces it. Each import books recipe usage against stock.
        </p>
        <div className="row">
          <input type="file" accept=".csv,text/csv" ref={file} aria-label="Sales CSV file" />
          <button className="btn primary" type="button" disabled={busy} onClick={upload}>Import</button>
          <button className="btn" type="button" onClick={sampleCsv} disabled={!menu.data}>Download a sample file</button>
        </div>
      </Card>
      <div className="split">
        <Card title="Dish sales">
          {items.error && <ErrorBox>{items.error}</ErrorBox>}
          {!items.data ? <Loading /> : !items.data.length ? <Empty>No sales in this range.</Empty> : (
            <table>
              <thead><tr><th>Dish</th><th className="r">Portions</th><th className="r">Per day</th><th className="r">Net sales</th><th className="r">Share</th></tr></thead>
              <tbody>
                {items.data.map((r) => (
                  <tr key={r.menu_item}>
                    <td><b>{r.name}</b><div className="small muted">{r.category}</div></td>
                    <td className="r">{r.qty.toLocaleString("en-CA")}</td><td className="r">{(r.qty / days).toFixed(1)}</td>
                    <td className="r">{money0(r.net_sales)}</td><td className="r">{total ? ((r.net_sales / total) * 100).toFixed(1) + "%" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Imported days">
          {list.error && <ErrorBox>{list.error}</ErrorBox>}
          {!list.data ? <Loading /> : !list.data.length ? <Empty>No sales imported yet.</Empty> : (
            <div className="tablewrap">
              <table>
                <thead><tr><th>Day</th><th>Source</th><th className="r">Net sales</th><th>Imported</th></tr></thead>
                <tbody>
                  {list.data.map((d) => (
                    <tr key={d.id}>
                      <td>{fmtDate(d.business_date)}</td><td className="small">{d.source}</td><td className="r">{money(d.net_sales)}</td>
                      <td className="small muted">{fmtDateTime(d.imported_at)} · {d.imported_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
