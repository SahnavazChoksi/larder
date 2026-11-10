/* Offline mode for the POS.

When the server can't be reached, the tablet keeps taking orders from a saved copy of the menu and tables (the
"kit"). Orders go into an outbox in this browser's storage. When the server answers again, the outbox uploads
by itself; each order carries a client_id, so an upload that's interrupted and retried can't book it twice.

This file has no React in it: components read it through useOffline().
*/
import { useSyncExternalStore } from "react";

const OUTBOX = "larder.outbox.v1";
const DEVICE = "larder.device";
const KIT = (loc) => `larder.kit.${loc}`;
const PING_MS = 15000;
const PING_OFFLINE_MS = 5000;

function read(key, fallback) {
  try {
    const v = JSON.parse(localStorage.getItem(key));
    return v ?? fallback;
  } catch {
    return fallback;
  }
}
function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false; // storage full or blocked
  }
}

// ---------- device identity ----------

export function device() {
  let d = read(DEVICE, null);
  if (!d?.id) {
    const id = Math.random().toString(36).slice(2, 6).toUpperCase();
    d = { id, name: `Tablet ${id}`, next: 1 };
    write(DEVICE, d);
  }
  return d;
}
export function renameDevice(name) {
  write(DEVICE, { ...device(), name: name.trim().slice(0, 40) || device().name });
  emit();
}
function nextNumber() {
  const d = device();
  write(DEVICE, { ...d, next: d.next + 1 });
  return `${d.id}-${d.next}`;
}
function uuid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

// ---------- state ----------

let state = { online: navigator.onLine !== false, syncing: false, lastSync: null, outbox: read(OUTBOX, []) };
const listeners = new Set();
function emit() {
  state = { ...state };
  listeners.forEach((l) => l());
}
function set(patch) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}
function subscribe(l) {
  listeners.add(l);
  return () => listeners.delete(l);
}
export function useOffline() {
  return useSyncExternalStore(subscribe, () => state);
}
export const getState = () => state;

// ---------- is the server there? ----------

/** True for "couldn't reach the server" (no reply, or the dev proxy's 50x), not for a real error answer. */
export function isOfflineError(err) {
  const r = err?.response;
  if (!r) return true;
  if ([502, 503, 504].includes(r.status)) return true;
  return r.status === 500 && (typeof r.data !== "object" || r.data === null);
}

export function reportNetworkError() {
  if (state.online) set({ online: false });
  schedule(PING_OFFLINE_MS);
}

let timer = null;
function schedule(ms) {
  clearTimeout(timer);
  timer = setTimeout(ping, ms);
}

export async function ping() {
  let ok = false;
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 5000);
    const r = await fetch("/api/pos/ping/", { cache: "no-store", signal: ctl.signal });
    clearTimeout(t);
    ok = r.ok && (await r.json()).ok === true;
  } catch {
    ok = false;
  }
  const was = state.online;
  if (ok !== was) set({ online: ok });
  if (ok && pendingCount() > 0 && !state.syncing) sync();
  schedule(ok ? PING_MS : PING_OFFLINE_MS);
  return ok;
}

let started = false;
export function startMonitor() {
  if (started) return;
  started = true;
  window.addEventListener("offline", () => reportNetworkError());
  window.addEventListener("online", () => ping());
  ping();
}

// ---------- the saved menu, tables and tax rules ----------

export function saveKit(locationId, kit) {
  return write(KIT(locationId), kit);
}
export function loadKit(locationId) {
  return read(KIT(locationId), null);
}

// ---------- outbox ----------

function saveOutbox(outbox) {
  // keep two days of uploaded orders for reference; never drop one that isn't uploaded
  const cutoff = Date.now() - 2 * 864e5;
  const kept = outbox.filter((o) => o.sync.status !== "synced" || new Date(o.closed_at || o.opened_at).getTime() > cutoff);
  if (!write(OUTBOX, kept)) throw new Error("This tablet's storage is full. Upload or clear old offline orders.");
  set({ outbox: kept });
}

export function newOrder({ location, type, table = null, tableName = "", guests = 1, customerName = "" }) {
  const o = {
    client_id: `${device().id}-${uuid()}`, local_no: nextNumber(), location, type, table, table_name: tableName, guests,
    customer_name: customerName, opened_at: new Date().toISOString(), closed_at: null, lines: [], payments: [],
    sync: { status: "pending" },
  };
  saveOutbox([...state.outbox, o]);
  return o;
}
export function updateOrder(order) {
  saveOutbox(state.outbox.map((o) => (o.client_id === order.client_id ? { ...order, sync: { status: "pending" } } : o)));
}
export function discardOrder(clientId) {
  saveOutbox(state.outbox.filter((o) => o.client_id !== clientId));
}
export function pendingCount() {
  return state.outbox.filter((o) => o.sync.status === "pending").length;
}

/** Upload everything waiting. Called automatically when the server comes back. */
export async function sync() {
  const byLocation = {};
  for (const o of state.outbox) if (o.sync.status === "pending") (byLocation[o.location] ||= []).push(o);
  if (!Object.keys(byLocation).length || state.syncing) return null;
  set({ syncing: true });
  const { default: api } = await import("./api");
  let done = 0;
  try {
    for (const [loc, orders] of Object.entries(byLocation)) {
      for (let i = 0; i < orders.length; i += 50) {
        const batch = orders.slice(i, i + 50);
        const { data } = await api.post("/pos/offline-orders/", {
          location: Number(loc), device: device().name,
          orders: batch.map((o) => ({
            client_id: o.client_id, type: o.type, table: o.table, guests: o.guests, customer_name: o.customer_name,
            opened_at: o.opened_at, closed_at: o.closed_at,
            lines: o.lines.map((l) => ({ menu_item: l.menu_item, qty: l.qty, price: l.price, modifiers: l.modifiers, note: l.note, sent_at: l.sent_at })),
            payments: o.payments.map((p) => ({ method: p.method, amount: p.amount, tip: p.tip, cash_tendered: p.cash_tendered, reference: p.reference })),
          })),
        });
        const results = Object.fromEntries(data.results.map((r) => [r.client_id, r]));
        saveOutbox(state.outbox.map((o) => {
          const r = results[o.client_id];
          if (!r) return o;
          done += 1;
          if (r.status === "error") return { ...o, sync: { status: "error", message: r.message } };
          return { ...o, sync: { status: r.status === "open" ? "open" : "synced", order: r.order, number: r.number, balance: r.balance } };
        }));
      }
    }
    set({ lastSync: new Date().toISOString() });
  } catch (err) {
    if (isOfflineError(err)) reportNetworkError();
  } finally {
    set({ syncing: false });
  }
  return done;
}

/** Try an order that failed again (after fixing the cause on the server, e.g. re-adding a table). */
export function retry(clientId) {
  saveOutbox(state.outbox.map((o) => (o.client_id === clientId ? { ...o, sync: { status: "pending" } } : o)));
  return sync();
}

// ---------- money, the same way the server works it out ----------

const r2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;

export function totals(order, kit) {
  const loc = kit.location;
  const subtotal = r2(order.lines.reduce((s, l) => s + l.qty * l.unit, 0));
  const rate = order.type === "dine_in" && order.guests >= loc.service_charge_party ? loc.service_charge_rate : 0;
  const sc = r2(subtotal * rate);
  const tax = r2((subtotal + sc) * loc.tax_rate);
  const total = r2(subtotal + sc + tax);
  const paid = r2(order.payments.reduce((s, p) => s + p.amount, 0));
  const tips = r2(order.payments.reduce((s, p) => s + p.tip, 0));
  return { subtotal, rate, sc, tax, total, paid, tips, balance: r2(total - paid) };
}
