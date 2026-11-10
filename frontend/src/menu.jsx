/* Shared menu pieces for the POS and the online order page: picture tiles, dish info, option picker, allergy filters. */
import { useEffect, useMemo, useRef, useState } from "react";
import { Modal, money } from "./ui";

/** Free text ("no dairy, peanuts") → canonical allergen names, using the vocabulary the server sends. */
export function normaliseAllergies(text, vocab) {
  const found = new Set();
  let rest = ` ${String(text || "").toLowerCase()} `;
  const words = (vocab || []).flatMap((a) => a.words.map((w) => [w, a.name])).sort((a, b) => b[0].length - a[0].length);
  for (const [w, name] of words) {
    const re = new RegExp(`(?<![a-z])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-z])`, "g");
    if (re.test(rest)) { found.add(name); rest = rest.replace(re, " "); }
  }
  return found;
}

/** Which of the dish's (and chosen options') allergens the guest reacts to. Peanut allergies also flag tree nuts. */
export function conflictsFor(allergens, avoid) {
  if (!avoid.size) return [];
  const hits = allergens.filter((a) => avoid.has(a));
  if (avoid.has("Peanut") && allergens.includes("Nuts") && !hits.includes("Nuts")) hits.push("Nuts");
  return hits;
}

export function useMenuIndex(menu) {
  return useMemo(() => {
    if (!menu) return null;
    const byId = Object.fromEntries(menu.items.map((d) => [d.id, d]));
    const icon = Object.fromEntries((menu.allergens || []).map((a) => [a.name, a.icon]));
    return { ...menu, byId, icon };
  }, [menu]);
}

export function DietMark({ diet }) {
  const veg = diet === "veg";
  return <span className={`diet ${veg ? "veg" : "nonveg"}`} title={veg ? "Vegetarian" : "Non-vegetarian"} aria-label={veg ? "Vegetarian" : "Non-vegetarian"}><i /></span>;
}

export function Badges({ dish }) {
  return (
    <>
      {dish.chef_pick && <span className="badge chef" title="Chef recommends">★ Chef’s pick</span>}
      {dish.new && <span className="badge new">New</span>}
      {dish.spice > 0 && <span className="badge spice" title={`Spice ${dish.spice} of 3`} aria-label={`Spice level ${dish.spice} of 3`}>{"🌶".repeat(dish.spice)}</span>}
    </>
  );
}

export function AllergenChips({ list, icon, hits = [], none = "No listed allergens" }) {
  if (!list.length) return <span className="small muted">{none}</span>;
  return (
    <span className="alg-row">
      {list.map((a) => <span key={a} className={`alg ${hits.includes(a) ? "hit" : ""}`} title={hits.includes(a) ? `Guest avoids ${a}` : `Contains ${a}`}>{icon[a] || ""} {a}</span>)}
    </span>
  );
}

function Picture({ dish, size = "md" }) {
  return (
    <span className={`pic ${size}`}>
      {dish.photo ? <img src={dish.photo} alt="" loading="lazy" /> : <span className="emo" aria-hidden="true">{dish.icon || "🍽️"}</span>}
    </span>
  );
}

/** One big tap target per dish. Tap adds (or opens options); the ⓘ corner shows what's in it. */
export function DishTile({ dish, menu, avoid, onTap, onInfo, onCustomise, disabled }) {
  const hits = conflictsFor(dish.allergens, avoid);
  const needsChoice = dish.groups.some((g) => menu.groups[g]?.min > 0);
  return (
    <div className={`dish ${hits.length ? "warn" : ""}`}>
      <button type="button" className="dish-tap" disabled={disabled} onClick={() => onTap(dish)} aria-label={`Add ${dish.name}, ${money(dish.price)}`}>
        <Picture dish={dish} />
        <span className="dish-name"><DietMark diet={dish.diet} /> {dish.name}</span>
        <span className="dish-meta"><b className="num">{money(dish.price)}</b>{needsChoice && <span className="small muted">choose…</span>}</span>
        <span className="dish-badges"><Badges dish={dish} /></span>
        {hits.length > 0 && <span className="dish-alert">⚠ {hits.join(", ")}</span>}
      </button>
      <button type="button" className="dish-info" onClick={() => onInfo(dish)} aria-label={`What's in ${dish.name}`}>i</button>
      {!needsChoice && dish.groups.length > 0 && onCustomise && (
        <button type="button" className="dish-more" disabled={disabled} onClick={() => onCustomise(dish)} aria-label={`${dish.name} with add-ons`}>+ add-ons</button>
      )}
    </div>
  );
}

/** Search, category chips with icons, veg-only and "hide allergens" filters, then the tile grid. */
export function MenuBrowser({ menu, avoid, setAvoid, onTap, onInfo, onCustomise, disabled, guestAvoid }) {
  const [cat, setCat] = useState(null);
  const [q, setQ] = useState("");
  const [vegOnly, setVegOnly] = useState(false);
  const [hide, setHide] = useState(false);
  const search = useRef(null);
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { e.preventDefault(); search.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const active = cat || menu.categories[0]?.name;
  const term = q.trim().toLowerCase();
  let list = term
    ? menu.items.filter((d) => d.name.toLowerCase().includes(term) || d.pos_code.toLowerCase() === term || d.description.toLowerCase().includes(term))
    : menu.items.filter((d) => d.category === active);
  if (vegOnly) list = list.filter((d) => d.diet === "veg");
  if (hide) list = list.filter((d) => !conflictsFor(d.allergens, avoid).length);
  const toggle = (name) => { const next = new Set(avoid); next.has(name) ? next.delete(name) : next.add(name); setAvoid(next); };

  return (
    <div className="menu-browser">
      <div className="row">
        <input ref={search} className="menu-search" type="search" placeholder="Find a dish or code  ( / )" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Find a dish" />
        <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={vegOnly} onChange={(e) => setVegOnly(e.target.checked)} /> Veg only</label>
      </div>
      <div className="cats" role="tablist" aria-label="Menu sections">
        {menu.categories.map((c) => (
          <button key={c.name} type="button" role="tab" aria-selected={!term && c.name === active} className={`cat ${!term && c.name === active ? "on" : ""}`} onClick={() => { setCat(c.name); setQ(""); }}>
            <span className="emo" aria-hidden="true">{c.icon || "🍽️"}</span>{c.name}
          </button>
        ))}
      </div>
      <details className="alg-filter" open={avoid.size > 0}>
        <summary>
          Allergies{avoid.size ? `: ${[...avoid].join(", ")}` : ""}
          {guestAvoid?.size > 0 && <span className="small muted"> (from the guest’s profile)</span>}
        </summary>
        <div className="row" style={{ gap: 6 }}>
          {(menu.allergens || []).map((a) => (
            <button key={a.name} type="button" className={`chip ${avoid.has(a.name) ? "on" : ""}`} aria-pressed={avoid.has(a.name)} onClick={() => toggle(a.name)}>{a.icon} {a.name}</button>
          ))}
          {avoid.size > 0 && <label className="row small" style={{ gap: 4 }}><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Hide dishes that contain them</label>}
        </div>
        <span className="small muted">Dishes with these get a warning. Always confirm with the kitchen for severe allergies: we share fryers and grills.</span>
      </details>
      {!list.length ? <div className="empty">{term ? `Nothing matches “${q}”.` : "Nothing here with these filters."}</div> : (
        <div className="dish-grid">
          {list.map((d) => <DishTile key={d.id} dish={d} menu={menu} avoid={avoid} onTap={onTap} onInfo={onInfo} onCustomise={onCustomise} disabled={disabled} />)}
        </div>
      )}
    </div>
  );
}

/** What's in it: for the server to answer "does this have…?" and to suggest something that goes with it. */
export function DishInfo({ dish, menu, avoid, onClose, onAdd, staff = true }) {
  const hits = conflictsFor(dish.allergens, avoid);
  const pairs = dish.pairs.map((id) => menu.byId[id]).filter(Boolean);
  return (
    <Modal title={dish.name} onClose={onClose} footer={<><button className="btn" type="button" onClick={onClose}>Close</button>{onAdd && <button className="btn primary" type="button" onClick={() => onAdd(dish)}>Add {money(dish.price)}</button>}</>}>
      <div className="info-head">
        <Picture dish={dish} size="lg" />
        <div className="stack">
          <span className="row" style={{ gap: 6 }}><DietMark diet={dish.diet} /><b>{dish.diet === "veg" ? "Vegetarian" : "Non-vegetarian"}</b><Badges dish={dish} /></span>
          {dish.description && <p style={{ margin: 0 }}>{dish.description}</p>}
          {dish.note && <div className="note">{dish.note}</div>}
        </div>
      </div>
      {hits.length > 0 && <div className="note error">⚠ Contains {hits.join(", ")}, which this guest avoids. Check with the kitchen before you suggest it.</div>}
      <div className="stack">
        <b className="small">Allergens</b>
        <AllergenChips list={dish.allergens} icon={menu.icon} hits={hits} />
      </div>
      {staff && dish.ingredients?.length > 0 && (
        <div className="stack"><b className="small">Made with</b><span className="small muted">{dish.ingredients.join(" · ")}</span></div>
      )}
      {dish.groups.length > 0 && (
        <div className="stack">
          <b className="small">Options</b>
          {dish.groups.map((g) => menu.groups[g]).filter(Boolean).map((g) => (
            <span key={g.id} className="small"><b>{g.name}</b>{g.min ? " (pick one)" : ""}: <span className="muted">{g.options.map((o) => `${o.name}${o.price ? ` +${money(o.price)}` : ""}`).join(" · ")}</span></span>
          ))}
        </div>
      )}
      {pairs.length > 0 && (
        <div className="stack">
          <b className="small">{staff ? "Suggest with it" : "Goes well with"}</b>
          <div className="pair-row">
            {pairs.map((p) => {
              const ph = conflictsFor(p.allergens, avoid);
              return (
                <button key={p.id} type="button" className={`pair ${ph.length ? "warn" : ""}`} onClick={() => onAdd?.(p)} disabled={!onAdd}>
                  <span aria-hidden="true">{p.icon || "🍽️"}</span> {p.name} <span className="muted num">{money(p.price)}</span>{ph.length > 0 && <span className="small"> ⚠ {ph.join(", ")}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </Modal>
  );
}

/** Choose size, sauce and add-ons. Required groups start on their usual choice so it's one tap for the common order. */
export function OptionPicker({ dish, menu, avoid, onClose, onAdd, busy, withNote = true, initialQty = 1 }) {
  const groups = dish.groups.map((g) => menu.groups[g]).filter(Boolean);
  const [picked, setPicked] = useState(() => {
    const start = {};
    for (const g of groups) {
      const d = g.options.find((o) => o.is_default) || (g.min > 0 ? g.options[0] : null);
      start[g.id] = d && g.min > 0 ? [d.id] : [];
    }
    return start;
  });
  const [qty, setQty] = useState(initialQty);
  const [note, setNote] = useState("");
  const chosen = groups.flatMap((g) => g.options.filter((o) => picked[g.id].includes(o.id)));
  const unit = dish.price + chosen.reduce((s, o) => s + o.price, 0);
  const allergens = [...new Set([...dish.allergens, ...chosen.flatMap((o) => o.allergens)])].sort();
  const hits = conflictsFor(allergens, avoid);
  const missing = groups.filter((g) => picked[g.id].length < g.min);

  function choose(g, o) {
    const cur = picked[g.id];
    let next;
    if (g.max === 1) next = cur.includes(o.id) && g.min === 0 ? [] : [o.id];
    else if (cur.includes(o.id)) next = cur.filter((x) => x !== o.id);
    else next = g.max && cur.length >= g.max ? cur : [...cur, o.id];
    setPicked({ ...picked, [g.id]: next });
  }

  return (
    <Modal title={dish.name} onClose={onClose}
      footer={<>
        <button className="btn" type="button" onClick={onClose}>Cancel</button>
        <button className={`btn primary ${hits.length ? "danger-fill" : ""}`} type="button" disabled={busy || missing.length > 0}
          onClick={() => onAdd(dish, chosen.map((o) => o.id), qty, note)}>
          {hits.length ? "Add anyway" : "Add"} {qty > 1 ? `${qty} × ` : ""}{money(unit * qty)}
        </button>
      </>}>
      {dish.description && <p className="small muted" style={{ margin: 0 }}>{dish.description}</p>}
      {hits.length > 0 && <div className="note error">⚠ Contains {hits.join(", ")}, which this guest avoids. Check with the kitchen.</div>}
      {groups.map((g) => (
        <fieldset key={g.id} className="opt-group">
          <legend>{g.name} <span className="small muted">{g.min > 0 ? (g.max === 1 ? "pick one" : `pick at least ${g.min}`) : g.max === 1 ? "optional" : "optional, any number"}</span></legend>
          <div className="opt-grid">
            {g.options.map((o) => {
              const on = picked[g.id].includes(o.id);
              const oh = conflictsFor(o.allergens, avoid);
              return (
                <button key={o.id} type="button" className={`opt ${on ? "on" : ""} ${oh.length ? "warn" : ""}`} aria-pressed={on} onClick={() => choose(g, o)}>
                  <span>{!o.is_veg && <DietMark diet="non_veg" />} {o.name}</span>
                  <span className="muted num">{o.price ? `+${money(o.price)}` : ""}</span>
                  {oh.length > 0 && <span className="small">⚠ {oh.join(", ")}</span>}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="row" style={{ gap: 6 }}>
          <button className="qtybtn" type="button" onClick={() => setQty(Math.max(1, qty - 1))} aria-label="One fewer">−</button>
          <b>{qty}</b>
          <button className="qtybtn" type="button" onClick={() => setQty(Math.min(20, qty + 1))} aria-label="One more">+</button>
        </span>
        <AllergenChips list={allergens} icon={menu.icon} hits={hits} />
      </div>
      {withNote && <label className="f">Note for the kitchen<input value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} placeholder="No pickles, sauce on the side…" /></label>}
    </Modal>
  );
}

/** "Goes well with…" after a dish is added: one tap to upsell. */
export function SuggestBar({ dish, menu, avoid, onAdd, inOrder }) {
  if (!dish) return null;
  const pairs = dish.pairs.map((id) => menu.byId[id]).filter((p) => p && !inOrder.has(p.id)).slice(0, 4);
  if (!pairs.length) return null;
  return (
    <div className="suggest" aria-live="polite">
      <span className="small"><b>Suggest with {dish.name}:</b></span>
      {pairs.map((p) => {
        const ph = conflictsFor(p.allergens, avoid);
        return (
          <button key={p.id} type="button" className={`pair ${ph.length ? "warn" : ""}`} onClick={() => onAdd(p)} title={ph.length ? `Contains ${ph.join(", ")}` : p.description}>
            <span aria-hidden="true">{p.icon || "🍽️"}</span> {p.name} <span className="muted num">{money(p.price)}</span>{ph.length > 0 && " ⚠"}
          </button>
        );
      })}
    </div>
  );
}
