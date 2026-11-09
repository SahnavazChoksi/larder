import { useEffect, useState } from "react";
import api, { errorText } from "../api";
import { useAuth } from "../auth";
import { Card, Chips, Empty, ErrorBox, Loading, Pill, fmtDateTime } from "../ui";

const ROLE_KIND = { owner: "accent", manager: "info", cook: "neutral" };

export default function Audit() {
  const { location } = useAuth();
  const [role, setRole] = useState("");
  const [scope, setScope] = useState("all");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState(null);
  const [next, setNext] = useState(null);
  const [error, setError] = useState("");

  const params = new URLSearchParams();
  if (role) params.set("role", role);
  if (scope === "one") params.set("location", location.id);
  if (query) params.set("q", query);
  const url = `/audit/?${params}`;

  useEffect(() => {
    let alive = true;
    setRows(null);
    api.get(url).then((r) => { if (alive) { setRows(r.data.results); setNext(r.data.next); } })
      .catch((e) => alive && setError(errorText(e)));
    return () => { alive = false; };
  }, [url]);

  async function more() {
    // DRF returns an absolute "next" URL; keep only the part after /api.
    const r = await api.get(next.slice(next.indexOf("/api") + 4));
    setRows([...rows, ...r.data.results]);
    setNext(r.data.next);
  }

  return (
    <Card title="Change log">
      <p className="small muted" style={{ margin: 0 }}>Every change made in Larder, with who, when and where. Entries can't be edited or deleted.</p>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <Chips options={[["", "Everyone"], ["cook", "Cooks"], ["manager", "Managers"], ["owner", "Owners"]]} value={role} onChange={setRole} />
          <Chips options={[["all", "All locations"], ["one", location.name]]} value={scope} onChange={setScope} />
        </div>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <input type="search" placeholder="Search, e.g. chicken" aria-label="Search the change log" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!rows ? <Loading /> : !rows.length ? <Empty>No changes match.</Empty> : (
        <div className="tablewrap">
          <table>
            <thead><tr><th>When</th><th>Who</th><th>Location</th><th>What</th><th>Details</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="small" style={{ whiteSpace: "nowrap" }}>{fmtDateTime(e.created_at)}</td>
                  <td><Pill kind={ROLE_KIND[e.user_role] || "neutral"}>{e.user_name}</Pill></td>
                  <td className="small">{e.location_name || "—"}</td>
                  <td><b>{e.action}</b></td>
                  <td className="small">{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {next && <div><button className="btn" type="button" onClick={more}>Load more</button></div>}
    </Card>
  );
}
