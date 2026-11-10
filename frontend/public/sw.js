/* Larder service worker: keeps the app itself loadable without a connection.
   Only the app's own files are cached. API calls always go to the network; the POS's offline mode
   handles those with its saved menu and outbox. */
const CACHE = "larder-app-v1";

self.addEventListener("install", (event) => {
  // Save the page and every script and stylesheet it loads, so the very first visit is enough
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const res = await fetch("/", { cache: "no-store" });
    const html = await res.clone().text();
    const files = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
    await cache.put("/", res);
    await cache.addAll(["/favicon.svg", ...files]);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/") || url.pathname.startsWith("/admin/")) return;

  if (req.mode === "navigate") {
    // Pages: try the network, fall back to the saved app shell (the app routes itself)
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("/", copy));
          return res;
        })
        .catch(() => caches.match("/")),
    );
    return;
  }
  // Built files have content hashes in their names, so a saved copy is always right
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    })),
  );
});
