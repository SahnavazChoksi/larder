import { useEffect } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { useAuth } from "./auth";
import Audit from "./pages/Audit";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Production from "./pages/Production";
import Purchasing from "./pages/Purchasing";
import Recipes from "./pages/Recipes";
import Sales from "./pages/Sales";
import Stock from "./pages/Stock";
import Transfers from "./pages/Transfers";
import Users from "./pages/Users";
import Variance from "./pages/Variance";
import Wastage from "./pages/Wastage";

// One place that says which role sees which page. The API enforces the same rules.
const PAGES = [
  { path: "/", label: "Dashboard", group: "Overview", min: "manager", element: <Dashboard /> },
  { path: "/stock", label: "Stock & counts", group: "Stock", min: "cook", element: <Stock /> },
  { path: "/transfers", label: "Transfers", group: "Stock", min: "cook", element: <Transfers /> },
  { path: "/production", label: "Central kitchen", group: "Stock", min: "cook", element: <Production /> },
  { path: "/wastage", label: "Wastage", group: "Stock", min: "cook", element: <Wastage /> },
  { path: "/purchasing", label: "Purchasing", group: "Buying", min: "cook", element: <Purchasing /> },
  { path: "/recipes", label: "Recipes & costing", group: "Buying", min: "manager", element: <Recipes /> },
  { path: "/sales", label: "Sales import", group: "Insights", min: "manager", element: <Sales /> },
  { path: "/variance", label: "COGS & variance", group: "Insights", min: "manager", element: <Variance /> },
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

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="empty">Loading…</div>;
  return user ? <Layout /> : <Login />;
}
