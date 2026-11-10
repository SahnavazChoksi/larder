import { useState } from "react";
import api, { errorText } from "../api";
import { useAuth } from "../auth";
import { Card, Chips, daysAgo, useToast } from "../ui";

export default function Exports() {
  const { location } = useAuth();
  const toast = useToast();
  const [range, setRange] = useState({ start: daysAgo(30), end: daysAgo(1) });
  const [scope, setScope] = useState("all");
  const [busy, setBusy] = useState(false);

  async function download(kind) {
    setBusy(true);
    try {
      const params = new URLSearchParams({ kind, start: range.start, end: range.end });
      if (scope === "one") params.set("location", location.id);
      const res = await api.get(`/reports/accounting-export/?${params}`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(res.data);
      a.download = `larder-${kind}-${range.start}-to-${range.end}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Accounting export">
      <p className="small muted" style={{ margin: 0 }}>
        CSV files your bookkeeper can import into QuickBooks or Xero. <b>Sales</b>: one row per location per day with net sales by category,
        discounts, service charge, HST collected, tips, voids, refunds and payments by method. <b>Purchases</b>: every received delivery with vendor and invoice number.
      </p>
      <div className="row">
        <label className="f">From<input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} /></label>
        <label className="f">To<input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} /></label>
        <Chips options={[["all", "All my locations"], ["one", location.name]]} value={scope} onChange={setScope} />
      </div>
      <div className="row">
        <button className="btn primary" type="button" disabled={busy} onClick={() => download("sales")}>Download sales CSV</button>
        <button className="btn" type="button" disabled={busy} onClick={() => download("purchases")}>Download purchases CSV</button>
      </div>
      <span className="small muted">Days imported from another POS by CSV show net sales only; tax, tips and payments come from orders rung on Larder's POS.</span>
    </Card>
  );
}
