import { useEffect, useRef, useState } from "react";
import api from "../api";
import { useAuth } from "../auth";
import { Card, Empty, ErrorBox, Loading, Pill, fmtDate, fmtDateTime, money, useAction, useApi } from "../ui";

const STATUS = { draft: "warn", approved: "good", discarded: "neutral" };

export default function Invoices() {
  const { location } = useAuth();
  const list = useApi(`/purchasing/invoices/?location=${location.id}`);
  const vendors = useApi("/vendors/");
  const [openId, setOpenId] = useState(null);
  const [vendor, setVendor] = useState("");
  const file = useRef();
  const [run, busy] = useAction();

  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return;
    const body = new FormData();
    body.append("file", f);
    body.append("location", location.id);
    if (vendor) body.append("vendor", vendor);
    const res = await run(() => api.post("/purchasing/invoices/", body), (d) => d.message || "Uploaded.");
    file.current.value = "";
    if (res) { list.reload(); setOpenId(res.id); }
  }

  if (openId) return <ScanEditor id={openId} vendors={vendors.data || []} onBack={() => { setOpenId(null); list.reload(); }} />;
  return (
    <>
      <Card title={`Scan a supplier invoice · ${location.name}`}>
        <p className="small muted" style={{ margin: 0 }}>Take a photo of the invoice or upload the PDF. Larder reads the lines, matches them to your items and converts pounds to kg. Check the draft, then a manager approves it: stock goes up and prices update.</p>
        <div className="row">
          <label className="f">Vendor (optional)
            <select value={vendor} onChange={(e) => setVendor(e.target.value)}>
              <option value="">Work it out from the invoice</option>
              {(vendors.data || []).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <input type="file" accept="image/*,application/pdf" capture="environment" ref={file} aria-label="Invoice photo or PDF" />
          <button className="btn primary" type="button" disabled={busy} onClick={upload}>{busy ? "Reading…" : "Upload and read"}</button>
        </div>
      </Card>
      <Card title="Scanned invoices">
        {list.error && <ErrorBox>{list.error}</ErrorBox>}
        {!list.data ? <Loading /> : !list.data.length ? <Empty>No invoices scanned yet.</Empty> : (
          <table>
            <thead><tr><th>Scan</th><th>Vendor</th><th>Invoice</th><th className="r">Total</th><th>Status</th><th /></tr></thead>
            <tbody>
              {list.data.map((s) => (
                <tr key={s.id} className="click" onClick={() => setOpenId(s.id)}>
                  <td><b>{s.number}</b><div className="small muted">{fmtDateTime(s.created_at)}</div></td>
                  <td>{s.vendor_name || s.vendor_text || "—"}</td>
                  <td className="small">{s.invoice_number || "—"} {s.invoice_date && `· ${fmtDate(s.invoice_date)}`}</td>
                  <td className="r">{money(s.total)}</td>
                  <td><Pill kind={STATUS[s.status]}>{s.status_label}</Pill> {s.order_number && <span className="small muted">→ {s.order_number}</span>}</td>
                  <td className="r"><button className="btn sm" type="button">Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function ScanEditor({ id, vendors, onBack }) {
  const { can } = useAuth();
  const { data, error, reload } = useApi(`/purchasing/invoices/${id}/`);
  const items = useApi("/items/?kind=raw");
  const [scan, setScan] = useState(null);
  const [run, busy] = useAction();
  useEffect(() => { if (data) setScan(data); }, [data]);

  if (error) return <><button className="btn" type="button" onClick={onBack}>← Back</button><ErrorBox>{error}</ErrorBox></>;
  if (!scan) return <Loading />;
  const draft = scan.status === "draft";
  const options = (items.data || []).filter((i) => !scan.vendor || i.vendor === Number(scan.vendor));
  const setLine = (i, k, v) => setScan({ ...scan, lines: scan.lines.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  const total = scan.lines.reduce((s, x) => s + Number(x.qty || 0) * Number(x.unit_price || 0), 0);

  async function save() {
    return run(() => api.patch(`/purchasing/invoices/${id}/`, {
      vendor: scan.vendor || null, invoice_number: scan.invoice_number, invoice_date: scan.invoice_date || null, lines: scan.lines,
    }), "Draft saved.");
  }
  async function approve() {
    if (!(await save())) return;
    const res = await run(() => api.post(`/purchasing/invoices/${id}/approve/`),
      (d) => `Booked as ${d.order_number}. Stock updated${d.price_changes?.length ? `; ${d.price_changes.length} price change(s)` : ""}.`);
    if (res) reload();
  }
  async function discard() {
    if (await run(() => api.post(`/purchasing/invoices/${id}/discard/`), "Discarded.")) reload();
  }

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <button className="btn" type="button" onClick={onBack}>← Back</button>
        <Pill kind={STATUS[scan.status]}>{scan.status_label}</Pill>
      </div>
      {scan.message && <div className="note">{scan.message}</div>}
      <div className="split">
        <Card title={`${scan.number}${scan.order_number ? ` → ${scan.order_number}` : ""}`}>
          <div className="row">
            <label className="f">Vendor
              <select value={scan.vendor || ""} disabled={!draft} onChange={(e) => setScan({ ...scan, vendor: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Choose…</option>{vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </label>
            <label className="f">Invoice #<input value={scan.invoice_number} disabled={!draft} onChange={(e) => setScan({ ...scan, invoice_number: e.target.value })} /></label>
            <label className="f">Date<input type="date" value={scan.invoice_date || ""} disabled={!draft} onChange={(e) => setScan({ ...scan, invoice_date: e.target.value })} /></label>
          </div>
          {scan.vendor_text && <span className="small muted">Printed vendor: {scan.vendor_text}</span>}
          <div className="tablewrap">
            <table>
              <thead><tr><th>On the invoice</th><th>Our item</th><th className="r">Qty</th><th className="r">Unit price</th><th className="r">Line</th><th /></tr></thead>
              <tbody>
                {scan.lines.map((x, i) => {
                  const item = options.find((o) => o.id === x.item) || (items.data || []).find((o) => o.id === x.item);
                  return (
                    <tr key={i}>
                      <td><input value={x.text} disabled={!draft} aria-label="Printed description" onChange={(e) => setLine(i, "text", e.target.value)} />
                        <div className="small muted">{x.note}{x.confidence < 70 && x.item ? " · check this match" : ""}</div></td>
                      <td>
                        <select value={x.item || ""} disabled={!draft} aria-label="Matched item" onChange={(e) => setLine(i, "item", e.target.value ? Number(e.target.value) : null)}>
                          <option value="">Choose…</option>{options.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.unit})</option>)}
                        </select>
                      </td>
                      <td className="r"><input type="number" step="0.01" value={x.qty ?? ""} disabled={!draft} aria-label="Quantity" onChange={(e) => setLine(i, "qty", e.target.value)} /> {item?.unit}</td>
                      <td className="r"><input type="number" step="0.01" value={x.unit_price ?? ""} disabled={!draft} aria-label="Unit price" onChange={(e) => setLine(i, "unit_price", e.target.value)} />
                        {item && x.unit_price && Math.abs(x.unit_price / item.last_price - 1) >= 0.05 && <div><Pill kind={x.unit_price > item.last_price ? "bad" : "good"}>{x.unit_price > item.last_price ? "+" : ""}{((x.unit_price / item.last_price - 1) * 100).toFixed(0)}% vs last</Pill></div>}</td>
                      <td className="r">{money(Number(x.qty || 0) * Number(x.unit_price || 0))}</td>
                      <td>{draft && <button className="btn sm" type="button" onClick={() => setScan({ ...scan, lines: scan.lines.filter((_, j) => j !== i) })}>Remove</button>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {draft && <div><button className="btn sm" type="button" onClick={() => setScan({ ...scan, lines: [...scan.lines, { text: "", item: null, qty: "", unit_price: "", confidence: 100, note: "" }] })}>Add line</button></div>}
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b className="num">Total {money(total)}</b>
            {draft && (
              <div className="row">
                <button className="btn" type="button" disabled={busy} onClick={discard}>Discard</button>
                <button className="btn" type="button" disabled={busy} onClick={save}>Save draft</button>
                {can("manager") ? <button className="btn primary" type="button" disabled={busy} onClick={approve}>Approve and book delivery</button>
                  : <span className="small muted">A manager approves it.</span>}
              </div>
            )}
          </div>
        </Card>
        <Card title="Invoice">
          {scan.is_pdf ? <a href={scan.file_url} target="_blank" rel="noreferrer">Open the PDF</a>
            : <img className="invoice-preview" src={scan.file_url} alt="Uploaded invoice" />}
        </Card>
      </div>
    </>
  );
}
