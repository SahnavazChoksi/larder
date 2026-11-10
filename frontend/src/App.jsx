import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import api from "./api";
import { useAuth } from "./auth";
import Audit from "./pages/Audit";
import Checklists from "./pages/Checklists";
import Complaints from "./pages/Complaints";
import Dashboard from "./pages/Dashboard";
import Forecast from "./pages/Forecast";
import Invoices from "./pages/Invoices";
import Issues from "./pages/Issues";
import Logbook from "./pages/Logbook";
import Login from "./pages/Login";
import MenuEngineering from "./pages/MenuEngineering";
import Performance from "./pages/Performance";
import Production from "./pages/Production";
import Purchasing from "./pages/Purchasing";
import Recipes from "./pages/Recipes";
import Sales from "./pages/Sales";
import Sops from "./pages/Sops";
import Stock from "./pages/Stock";
import Team from "./pages/Team";
import Transfers from "./pages/Transfers";
import Users from "./pages/Users";
import Variance from "./pages/Variance";
import Wastage from "./pages/Wastage";

// One place that says which role sees which page. The API enforces the same rules.
const PAGES = [
  { path: "/", label: "Dashboard", group: "Overview", min: "manager", element: <Dashboard /> },
  { path: "/performance", label: "Outlet performance", group: "Overview", min: "manager", element: <Performance /> },
  { path: "/checklists", label: "Checklists", group: "Daily operations", min: "cook", element: <Checklists /> },
  { path: "/logbook", label: "Shift logbook", group: "Daily operations", min: "cook", element: <Logbook /> },
  { path: "/issues", label: "Issues & equipment", group: "Daily operations", min: "cook", element: <Issues /> },
  { path: "/complaints", label: "Guest complaints", group: "Daily operations", min: "cook", element: <Complaints /> },
  { path: "/sops", label: "SOPs", group: "Daily operations", min: "cook", element: <Sops /> },
  { path: "/stock", label: "Stock & counts", group: "Stock", min: "cook", element: <Stock /> },
  { path: "/transfers", label: "Transfers", group: "Stock", min: "cook", element: <Transfers /> },
  { path: "/production", label: "Central kitchen", group: "Stock", min: "cook", element: <Production /> },
  { path: "/wastage", label: "Wastage", group: "Stock", min: "cook", element: <Wastage /> },
  { path: "/purchasing", label: "Purchasing", group: "Buying", min: "cook", element: <Purchasing /> },
  { path: "/invoices", label: "Invoice scan", group: "Buying", min: "cook", element: <Invoices /> },
  { path: "/recipes", label: "Recipes & costing", group: "Buying", min: "manager", element: <Recipes /> },
  { path: "/menu-engineering", label: "Menu engineering", group: "Insights", min: "manager", element: <MenuEngineering /> },
  { path: "/forecast", label: "Forecast & reorder", group: "Insights", min: "manager", element: <Forecast /> },
  { path: "/variance", label: "COGS & variance", group: "Insights", min: "manager", element: <Variance /> },
  { path: "/sales", label: "Sales import", group: "Insights", min: "manager", element: <Sales /> },
  { path: "/team", label: "Team & staffing", group: "Admin", min: "manager", element: <Team /> },
  { path: "/audit", label: "Change log", group: "Admin", min: "manager", element: <Audit /> },
  { path: "/users", label: "Users", group: "Admin", min: "owner", element: <Users /> },
];

const ROLE_LABEL = { cook: "Cook", manager: "Manager", owner: "Owner" };

function Layout() {
  const { user, logout, locations, location, setLocationId, can } = useAuth();
  const [params] = useSearchParams();
  const routerLocation = useLocation();
  const visible = PAGES.filter((p) => can(p.min));
  const groups = [...new Set(visible.map((p) => p.group))];
  const title = PAGES.find((p) => p.path === routerLocation.pathname)?.label || "";

  // Links like /variance?location=3 switch the location picker.
  useEffect(() => {
    const id = Number(params.get("location"));
    if (id && locations.some((l) => l.id === id)) setLocationId(id);
  }, [params, locations, setLocationId]);

  return (
    <div className="app">
      <nav className="rail" aria-label="Modules">
        <div className="brand">
          <div className="brand-mark">L</div>
          <div>
            <b>Larder</b>
            <span>Back office</span>
          </div>
        </div>
        {groups.map((g) => (
          <div className="navgroup" key={g}>
            <div>{g}</div>
            {visible
              .filter((p) => p.group === g)
              .map((p) => (
                <NavLink key={p.path} to={p.path} end className={({ isActive }) => `nav ${isActive ? "on" : ""}`}>
                  {p.label}
                </NavLink>
              ))}
          </div>
        ))}
      </nav>
      <main className="main">
        <header className="top">
          <h1>{title}</h1>
          <div className="row">
            <label className="row small muted" htmlFor="loc">
              Location
              <select id="loc" value={location?.id || ""} onChange={(e) => setLocationId(Number(e.target.value))}>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <Bell />
            <span className="small">
              {user.display_name} <span className="pill neutral">{ROLE_LABEL[user.role]}</span>
            </span>
            <button className="btn sm" type="button" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <div className="page">
          {!location ? (
            <div className="note error">Your account isn't linked to any location yet. Ask the owner to add you to one.</div>
          ) : (
            <Routes>
              {visible.map((p) => (
                <Route key={p.path} path={p.path} element={p.element} />
              ))}
              <Route path="*" element={<Navigate to={visible[0]?.path || "/stock"} replace />} />
            </Routes>
          )}
        </div>
      </main>
    </div>
  );
}

function Bell() {
  const [data, setData] = useState({ unread: 0, items: [] });
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/ops/notifications/").then((r) => alive && setData(r.data)).catch(() => {});
    load();
    const timer = setInterval(load, 60000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  async function go(n) {
    setOpen(false);
    if (!n.read_at) {
      await api.post("/ops/notifications/read/", { ids: [n.id] }).catch(() => {});
      setData((d) => ({ unread: Math.max(0, d.unread - 1), items: d.items.map((x) => (x.id === n.id ? { ...x, read_at: "now" } : x)) }));
    }
    if (n.link) navigate(n.link);
  }
  async function readAll() {
    await api.post("/ops/notifications/read/", {}).catch(() => {});
    setData((d) => ({ unread: 0, items: d.items.map((x) => ({ ...x, read_at: x.read_at || "now" })) }));
  }

  return (
    <div className="bell">
      <button className="btn sm" type="button" aria-label={`Notifications, ${data.unread} unread`} onClick={() => setOpen(!open)}>
        Alerts{data.unread > 0 && <span className="dot">{data.unread}</span>}
      </button>
      {open && (
        <div className="dropdown" role="menu">
          <div className="row" style={{ justifyContent: "space-between", padding: "8px 12px" }}>
            <b>Notifications</b>
            {data.unread > 0 && <button className="btn sm" type="button" onClick={readAll}>Mark all read</button>}
          </div>
          {!data.items.length && <div className="empty">Nothing yet.</div>}
          {data.items.map((n) => (
            <button key={n.id} type="button" className={`item ${n.read_at ? "" : "unread"}`} onClick={() => go(n)}>
              <b>{n.title}</b>
              <div className="small muted">{n.body}</div>
              <div className="small muted">{new Date(n.created_at).toLocaleString("en-CA", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="empty">Loading…</div>;
  return user ? <Layout /> : <Login />;
}
