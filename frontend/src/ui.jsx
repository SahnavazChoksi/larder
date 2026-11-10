import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import api, { errorText } from "./api";

// ---------- formatting ----------

export const money = (n, d = 2) =>
  n == null ? "—" : (n < 0 ? "−" : "") + "$" + Math.abs(n).toLocaleString("en-CA", { minimumFractionDigits: d, maximumFractionDigits: d });
export const money0 = (n) => money(n, 0);
export const pct = (n, d = 1) => (n == null ? "—" : (n * 100).toFixed(d) + "%");
export function qty(n, unit) {
  if (n == null) return "—";
  const a = Math.abs(n);
  const d = unit === "pc" ? 0 : a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return `${Number(n).toLocaleString("en-CA", { maximumFractionDigits: d })} ${unit}`;
}
export const fmtDate = (iso) =>
  iso ? new Date(iso.length === 10 ? iso + "T12:00:00" : iso).toLocaleDateString("en-CA", { month: "short", day: "numeric" }) : "—";
export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
export function isoDate(d) {
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}
export function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
}

export const STOCK_STATUS = {
  out: ["bad", "Out"],
  low: ["bad", "Low"],
  below_par: ["warn", "Below par"],
  over: ["info", "Overstock"],
  ok: ["good", "OK"],
  no_par: ["neutral", "No par"],
};

// ---------- data hook ----------

/** GET a URL and keep the result. Pass null to skip. */
export function useApi(url) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(url) });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .get(url)
      .then((r) => alive && setState({ data: r.data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: errorText(e), loading: false }));
    return () => {
      alive = false;
    };
  }, [url, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

// ---------- toasts ----------

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef();
  const show = useCallback((text, kind = "ok") => {
    clearTimeout(timer.current);
    setToast({ text, kind });
    timer.current = setTimeout(() => setToast(null), 4500);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && (
        <div className={`toast ${toast.kind}`} role="status">
          {toast.text}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/** Run an API call, show success/failure as a toast. Returns the response data or undefined. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async (fn, success) => {
      setBusy(true);
      try {
        const res = await fn();
        if (success) toast(typeof success === "function" ? success(res?.data) : success);
        return res?.data ?? true;
      } catch (e) {
        toast(errorText(e), "error");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );
  return [run, busy];
}

// ---------- small components ----------

export const Pill = ({ kind = "neutral", children }) => <span className={`pill ${kind}`}>{children}</span>;

export function Tile({ label, value, note, stripe }) {
  return (
    <div className={`tile ${stripe ? "stripe-" + stripe : ""}`}>
      <span className="l">{label}</span>
      <span className="v">{value}</span>
      {note && <span className="d">{note}</span>}
    </div>
  );
}

export function Card({ title, actions, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-h">
          {title && <h2>{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export const Loading = () => <div className="empty">Loading…</div>;
export const ErrorBox = ({ children }) => <div className="note error">{children}</div>;
export const Empty = ({ children }) => <div className="empty">{children}</div>;

export function Chips({ options, value, onChange }) {
  return (
    <div className="chips">
      {options.map(([v, label]) => (
        <button key={v} type="button" className={`chip ${value === v ? "on" : ""}`} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Modal({ title, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
        {footer && <div className="row end">{footer}</div>}
      </div>
    </div>
  );
}

export function NumberInput({ value, onChange, step = "0.1", min = "0", label, ...rest }) {
  return (
    <input
      type="number"
      step={step}
      min={min}
      value={value ?? ""}
      aria-label={label}
      onChange={(e) => onChange(e.target.value === "" ? "" : e.target.value)}
      {...rest}
    />
  );
}

// ---------- charts (plain SVG) ----------

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 1.5 ? 1.5 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

export function LineChart({ values, labels, format }) {
  const w = 760, h = 230, L = 56, R = 60, T = 14, B = 26;
  if (!values.length) return <Empty>No sales in this range.</Empty>;
  const max = niceMax(Math.max(...values) * 1.05);
  const n = values.length;
  const x = (i) => L + (n === 1 ? 0 : (i * (w - L - R)) / (n - 1));
  const y = (v) => T + (h - T - B) * (1 - v / max);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[n - 1];
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Line chart">
      {[0, 1, 2, 3, 4].map((k) => (
        <g key={k}>
          <line x1={L} x2={w - R} y1={y((max * k) / 4)} y2={y((max * k) / 4)} stroke="var(--line)" />
          <text x={L - 8} y={y((max * k) / 4) + 4} textAnchor="end">{format((max * k) / 4)}</text>
        </g>
      ))}
      {labels.map((lb, i) => lb && <text key={i} x={x(i)} y={h - 6} textAnchor="middle">{lb}</text>)}
      <polygon points={`${x(0)},${y(0)} ${pts} ${x(n - 1)},${y(0)}`} fill="var(--accent)" opacity=".12" />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="2" />
      <circle cx={x(n - 1)} cy={y(last)} r="4" fill="var(--accent)" />
      <text className="lbl" x={x(n - 1) + 8} y={y(last) + 4}>{format(last)}</text>
    </svg>
  );
}

export function HBars({ rows, format, color = "var(--bad)" }) {
  if (!rows.length) return <Empty>Nothing to show.</Empty>;
  const max = Math.max(...rows.map((r) => Math.abs(r.value))) || 1;
  const w = 560, rh = 26, L = 180;
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${rows.length * rh + 6}`} role="img" aria-label="Bar chart">
      {rows.map((r, i) => {
        const bw = Math.max(2, ((w - L - 80) * Math.abs(r.value)) / max);
        return (
          <g key={r.label + i}>
            <text className="lbl" x={L - 8} y={i * rh + 17} textAnchor="end">{r.label}</text>
            <rect x={L} y={i * rh + 5} width={bw} height="16" rx="3" fill={color} />
            <text x={L + bw + 6} y={i * rh + 17}>{format(r.value)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function Sparkline({ values }) {
  if (values.length < 2) return null;
  const w = 90, h = 22;
  const mn = Math.min(...values), mx = Math.max(...values), r = mx - mn || 1;
  const pts = values.map((v, i) => [(i * (w - 4)) / (values.length - 1) + 2, h - 3 - ((v - mn) / r) * (h - 6)]);
  const [lx, ly] = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      <circle cx={lx} cy={ly} r="2.5" fill="var(--accent)" />
    </svg>
  );
}

/** Two or more series on one axis, e.g. this year vs last year. series: [{name, values, color, dashed}] */
export function MultiLineChart({ series, labels, format }) {
  const w = 760, h = 240, L = 56, R = 16, T = 14, B = 44;
  const all = series.flatMap((s) => s.values);
  if (!all.length) return <Empty>No data in this range.</Empty>;
  const max = niceMax(Math.max(...all) * 1.05);
  const n = labels.length;
  const x = (i) => L + (n === 1 ? 0 : (i * (w - L - R)) / (n - 1));
  const y = (v) => T + (h - T - B) * (1 - v / max);
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Comparison chart">
        {[0, 1, 2, 3, 4].map((k) => (
          <g key={k}>
            <line x1={L} x2={w - R} y1={y((max * k) / 4)} y2={y((max * k) / 4)} stroke="var(--line)" />
            <text x={L - 8} y={y((max * k) / 4) + 4} textAnchor="end">{format((max * k) / 4)}</text>
          </g>
        ))}
        {labels.map((lb, i) => lb && <text key={i} x={x(i)} y={h - 26} textAnchor="middle">{lb}</text>)}
        {series.map((s) => (
          <g key={s.name}>
            <polyline points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={s.color}
              strokeWidth="2" strokeDasharray={s.dashed ? "5 4" : undefined} />
            <circle cx={x(s.values.length - 1)} cy={y(s.values[s.values.length - 1])} r="3.5" fill={s.color} />
          </g>
        ))}
      </svg>
      <div className="legend">
        {series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}
      </div>
    </>
  );
}

/** Vertical bars with a value label on each. */
export function Bars({ values, labels, format = (v) => Math.round(v) }) {
  const w = 560, h = 200, L = 40, T = 18, B = 26;
  if (!values.length) return <Empty>No data.</Empty>;
  const max = niceMax(Math.max(...values, 1));
  const slot = (w - L - 10) / values.length, bw = slot * 0.6;
  const y = (v) => T + (h - T - B) * (1 - v / max);
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Bar chart">
      {[0, 1, 2, 3, 4].map((k) => (
        <g key={k}>
          <line x1={L} x2={w - 10} y1={y((max * k) / 4)} y2={y((max * k) / 4)} stroke="var(--line)" />
          <text x={L - 6} y={y((max * k) / 4) + 4} textAnchor="end">{Math.round((max * k) / 4)}</text>
        </g>
      ))}
      {values.map((v, i) => {
        const cx = L + slot * i + slot / 2;
        return (
          <g key={i}>
            <rect x={cx - bw / 2} y={y(v)} width={bw} height={y(0) - y(v)} rx="3" fill="var(--accent)" />
            <text className="lbl" x={cx} y={y(v) - 5} textAnchor="middle">{format(v)}</text>
            <text x={cx} y={h - 7} textAnchor="middle">{labels[i]}</text>
          </g>
        );
      })}
    </svg>
  );
}
